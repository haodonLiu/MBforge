"""Text reorganization and molecule registration for the pipeline.

Three entry points:

1. ``insert_molecode_blocks`` — Insert MoleCode into rough markdown at bbox positions.
2. ``reorganize_with_llm`` — LLM-based full-text reorganization; preserves MoleCode blocks.
3. ``register_molecules_from_text`` — Extract text context for each molecule and persist links.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from ..utils.logger import get_logger
from .extract_text import PageContent
from .normalize import NormalizedMolecule

logger = get_logger("mbforge.pipeline.organizer")

_PAGE_MARKER_RE = re.compile(r"<!-- PAGE (\d+) -->")
_MOLECODE_BLOCK_RE = re.compile(r"```molecode\n(.*?)\n```", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _bbox_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Intersection over min-area for two bounding boxes.

    Returns 0.0 if the boxes do not overlap, otherwise the intersection area
    divided by the smaller of the two box areas. Bounding boxes are in PDF
    points and follow the ``(x0, y0, x1, y1)`` convention.
    """
    x_left = max(a[0], b[0])
    y_top = max(a[1], b[1])
    x_right = min(a[2], b[2])
    y_bottom = min(a[3], b[3])
    if x_right <= x_left or y_bottom <= y_top:
        return 0.0
    inter = (x_right - x_left) * (y_bottom - y_top)
    area_a = max((a[2] - a[0]) * (a[3] - a[1]), 1.0)
    area_b = max((b[2] - b[0]) * (b[3] - b[1]), 1.0)
    return inter / min(area_a, area_b)


def _mol_to_molecode(smiles: str, name: str) -> str:
    """Convert SMILES to a MoleCode Mermaid block via RDKit + molecode.

    Falls back to a plain ``# MoleCode not available for {name}`` block when
    RDKit cannot parse the SMILES, and to ``# MoleCode error for {name}: ...``
    when the molecode call itself raises.
    """
    try:
        from molecode import mol_to_mermaid
        from rdkit import Chem
    except ImportError:
        logger.warning(
            "rdkit/molecode not available; emitting placeholder for %s", name
        )
        return f"```\n# MoleCode not available for {name}\n```\n"

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("MoleCode conversion failed for SMILES: %s", smiles)
        return f"```\n# MoleCode not available for {name}\n```\n"
    try:
        mcode = mol_to_mermaid(mol, name=name, kekulize=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MoleCode error for %s: %s", name, exc)
        return f"```\n# MoleCode error for {name}: {exc}\n```\n"
    return f"```molecode\n{mcode}\n```\n"


def _find_position_in_pages(
    mol_page: int,
    mol_bbox: tuple[float, float, float, float] | None,
    pages: list[PageContent],
) -> int | None:
    """Find the text-span index whose bbox overlaps ``mol_bbox`` by IoM > 0.3.

    ``mol_page`` is the 0-based PDF page index into ``pages``. Returns ``None``
    when no overlap is found (caller falls back to page-end append).
    """
    if mol_bbox is None or mol_page < 0 or mol_page >= len(pages):
        return None
    page = pages[mol_page]
    for i, span in enumerate(page.text_spans):
        if span.block_type != 0:
            continue
        if _bbox_overlap(mol_bbox, span.bbox) > 0.3:
            return i
    return None


def _collect_page_boundaries(lines: list[str]) -> dict[int, int]:
    """Map ``page_num`` to the line index of its ``<!-- PAGE N -->`` marker."""
    boundaries: dict[int, int] = {}
    for lineno, line in enumerate(lines):
        m = _PAGE_MARKER_RE.match(line)
        if m:
            boundaries[int(m.group(1))] = lineno
    return boundaries


def _collect_page_ranges(lines: list[str]) -> dict[int, list[int]]:
    """Map ``page_num`` to its content line indices (excluding the marker itself)."""
    ranges: dict[int, list[int]] = {}
    current_page = 1
    ranges[current_page] = []
    for lineno, line in enumerate(lines):
        m = _PAGE_MARKER_RE.match(line)
        if m:
            current_page = int(m.group(1))
            ranges.setdefault(current_page, [])
        else:
            ranges[current_page].append(lineno)
    return ranges


def insert_molecode_blocks(
    md_path: str,
    pages: list[PageContent],
    molecules: list[NormalizedMolecule],
    output_path: str,
) -> str:
    """Insert MoleCode blocks into rough markdown at bbox-determined positions.

    Strategy:
        * bbox overlaps a text span → MoleCode inserted just after that span's line.
        * bbox doesn't overlap any span on the molecule's page → fallback to
          page-end with ``(Page Y)`` annotation.
        * page has no marker at all → appended at end of file.
    """
    md_text = Path(md_path).read_text(encoding="utf-8")
    lines = md_text.split("\n")

    insertions: list[tuple[int, int | None, NormalizedMolecule]] = []
    for mol in molecules:
        if mol.status == "rejected":
            continue
        primary = mol.detections[0] if mol.detections else None
        if primary is None:
            continue
        page_idx = primary.page or 0
        span_idx = _find_position_in_pages(page_idx, primary.bbox, pages)
        insertions.append((page_idx, span_idx, mol))

    # sort by (page, span_idx); None span indexes are pushed to end of their page
    insertions.sort(key=lambda x: (x[0], x[1] if x[1] is not None else 9999))

    page_boundaries = _collect_page_boundaries(lines)
    page_ranges = _collect_page_ranges(lines)

    reverse_insertions: list[tuple[int, str]] = []
    for page_idx, span_idx, mol in reversed(insertions):
        name = mol.name or f"Mol_{mol.canonical_smiles[:8]}"
        block = _mol_to_molecode(mol.canonical_smiles, name)
        page_num = page_idx + 1  # 1-based page number, matches `<!-- PAGE N -->`

        if span_idx is not None and page_num in page_ranges:
            plines = page_ranges[page_num]
            last_line = max(plines) if plines else page_boundaries.get(page_num, 0)
            insert_at = max(last_line, page_boundaries.get(page_num, 0))
            reverse_insertions.append((insert_at, block))
            continue

        # Strategy C — append to page-end (just before next page marker, if any).
        next_boundary = page_boundaries.get(page_num + 1, len(lines))
        if page_num in page_boundaries:
            fallback = f"\n<!-- Molecule {name} (Page {page_num}) -->\n{block}"
            insert_at = max(0, next_boundary - 1)
            reverse_insertions.append((insert_at, fallback))
        else:
            reverse_insertions.append((len(lines), f"\n{block}"))

    for insert_at, block in reverse_insertions:
        insert_at = max(0, min(insert_at, len(lines)))
        lines.insert(insert_at + 1, block)

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    logger.info(
        "insert_molecode_blocks: %d insertions written to %s",
        len(reverse_insertions),
        output_path,
    )
    return output_path


_SYSTEM_PROMPT = """You are reorganizing a scientific document extracted from a PDF.

Rules:
1. Keep ALL ```molecode ... ``` blocks intact. Do NOT modify, move, remove,
   or "fix" any MoleCode content.
2. Reorganize paragraphs into logical sections with Markdown headings (#, ##, ###).
3. Merge content from the same section that was split across pages.
4. Move MoleCode blocks into the section where they semantically belong,
   using the molecular name as context.
5. Fix obvious OCR errors (common substitution patterns only).
6. Preserve all factual content. Do not invent information.
7. Remove page markers (<!-- PAGE N -->).
8. Output valid Markdown."""


def _llm_complete(model: str, prompt: str) -> str:
    """Call an LLM via litellm and return its completion text.

    ``model`` is the raw model name from config (e.g. ``sensenova-6.7-flash-lite``).
    The full LiteLLM model string (including provider prefix and api_base) and
    api_key are resolved from ``load_global_config().llm`` via ``to_litellm_config``.

    On any failure (import error, network error, API error, bad model), logs
    and returns the *input prompt* verbatim so the caller can fall back to a
    pass-through copy of the document.
    """
    # Resolve api_key and base_url from config, set env vars for litellm.
    # The ?api_base= query-param approach causes TCP connection timeout on
    # some networks, so env vars are preferred.
    try:
        from ..utils.config import load_global_config

        llm_cfg = load_global_config().llm
        if llm_cfg.api_key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = llm_cfg.api_key
        if llm_cfg.base_url and not os.environ.get("OPENAI_API_BASE"):
            os.environ["OPENAI_API_BASE"] = llm_cfg.base_url
        litellm_model = f"openai/{llm_cfg.model}"
    except Exception:  # noqa: BLE001 — never let config resolution crash the pipeline
        litellm_model = f"openai/{model}"

    try:
        from litellm import completion
    except ImportError:
        logger.warning("litellm not available — reorganize skipped, copying input")
        return prompt
    try:
        response = completion(
            model=litellm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM call failed (%s) — falling back to input copy", exc)
        return prompt
    try:
        return response.choices[0].message.content or prompt
    except (AttributeError, IndexError, KeyError) as exc:
        logger.error("LLM response malformed (%s) — falling back to input copy", exc)
        return prompt


def reorganize_with_llm(
    md_path: str,
    output_path: str,
    model: str | None = None,
) -> str:
    """Reorganize a rough markdown document with MoleCode blocks via LLM.

    Reads ``md_path``, sends it to the configured LLM, and writes the response
    to ``output_path``. All ``\\`\\`\\`molecode`` blocks are required to be
    preserved verbatim by the system prompt; chunked processing (for documents
    over ~4000 tokens) splits on MoleCode block boundaries so they are never
    broken across chunks.

    Args:
        md_path: Path to the enriched markdown (with MoleCode blocks).
        output_path: Where to write the reorganized markdown.
        model: LLM model name. Defaults to ``load_global_config().llm.reorganize_model``
            (falling back to ``load_global_config().llm.model``).

    Returns:
        The ``output_path``.
    """
    if model is None:
        from ..utils.config import load_global_config

        cfg = load_global_config()
        model = getattr(cfg.llm, "reorganize_model", None) or cfg.llm.model

    md_text = Path(md_path).read_text(encoding="utf-8")
    estimated_tokens = len(md_text) // 4

    if estimated_tokens < 4000:
        prompt = f"{_SYSTEM_PROMPT}\n\nDocument:\n{md_text}\n\nReorganized:"
        response = _llm_complete(model, prompt)
        Path(output_path).write_text(response, encoding="utf-8")
        return output_path

    # Long doc: split on MoleCode boundaries so blocks are never broken.
    segments = re.split(r"(```molecode\n.*?\n```)", md_text, flags=re.DOTALL)
    chunk_budget = 6000  # approximate token budget per chunk
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0
    for seg in segments:
        seg_len = len(seg) // 4
        if current_len + seg_len > chunk_budget and current_chunk:
            chunks.append("".join(current_chunk))
            current_chunk = [seg]
            current_len = seg_len
        else:
            current_chunk.append(seg)
            current_len += seg_len
    if current_chunk:
        chunks.append("".join(current_chunk))

    reorganized_chunks: list[str] = []
    for i, chunk in enumerate(chunks):
        chunk_prompt = (
            f"{_SYSTEM_PROMPT}\n\n"
            f"This is chunk {i + 1} of {len(chunks)}. "
            f"Focus on reorganizing this chunk.\n\n"
            f'Context: The beginning of the chunk is "{chunk[:200]}..."\n\n'
            f"Chunk text:\n{chunk}\n\n"
            f"Reorganized (chunk {i + 1} of {len(chunks)}):"
        )
        reorganized_chunks.append(_llm_complete(model, chunk_prompt))

    Path(output_path).write_text("\n\n".join(reorganized_chunks), encoding="utf-8")
    return output_path


def _find_molecode_in_text(
    text: str, name: str, smiles: str
) -> tuple[int, int, str] | None:
    """Find a MoleCode block by name or SMILES prefix in ``text``.

    Returns ``(block_start, block_end, nearest_section_title)`` where the
    section title is the most-recent Markdown heading before the block, or
    an empty string if there is no preceding heading. Returns ``None`` if no
    MoleCode block contains the molecule's name or the first 12 chars of its
    SMILES.
    """
    for match in _MOLECODE_BLOCK_RE.finditer(text):
        block = match.group(1)
        if name and name in block:
            start = match.start()
            end = match.end()
            before = text[:start]
            headings = list(_HEADING_RE.finditer(before))
            section_title = headings[-1].group(2) if headings else ""
            return (start, end, section_title)
        if smiles and smiles[:12] in block:
            start = match.start()
            end = match.end()
            before = text[:start]
            headings = list(_HEADING_RE.finditer(before))
            section_title = headings[-1].group(2) if headings else ""
            return (start, end, section_title)
    return None


def register_molecules_from_text(
    fine_md_path: str,
    molecules: list[NormalizedMolecule],
    doc_id: str,
    project_root: str,
) -> None:
    """Find each molecule's text context in the reorganized markdown and persist links.

    Searches the fine markdown for each molecule's MoleCode block (by name or
    SMILES prefix), extracts a ~200-char context window, identifies the nearest
    preceding Markdown heading, and inserts one row per molecule into
    ``text_molecule_links``. The full set of inserts runs in a single
    transaction; any error rolls back the whole batch.

    Molecules with ``status == "rejected"`` are skipped.
    """
    from ..core.database import DatabaseManager

    md_text = Path(fine_md_path).read_text(encoding="utf-8")
    db = DatabaseManager.get(project_root)
    db.initialize()

    now_ms = int(time.time() * 1000)
    with db.mol_conn() as conn:
        conn.execute("BEGIN")
        try:
            for mol in molecules:
                if mol.status == "rejected":
                    continue
                name = mol.name or f"Mol_{mol.canonical_smiles[:8]}"
                position = _find_molecode_in_text(md_text, name, mol.canonical_smiles)
                if position is not None:
                    block_start, block_end, _section_title = position
                    excerpt_start = max(0, block_start - 200)
                    excerpt_end = min(len(md_text), block_end + 200)
                    text_excerpt = md_text[excerpt_start:excerpt_end].replace("\n", " ")
                    code_text = md_text[block_start:block_end]
                    char_start, char_end = block_start, block_end
                else:
                    text_excerpt = "position unresolved"
                    code_text = ""
                    char_start, char_end = 0, 0
                conn.execute(
                    """INSERT INTO text_molecule_links
                       (doc_id, mol_id, text_excerpt, role,
                        code_text, char_start, char_end, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        doc_id,
                        mol.canonical_smiles,
                        text_excerpt[:500],
                        "mentioned",
                        code_text[:1000],
                        char_start,
                        char_end,
                        now_ms,
                    ),
                )
            conn.commit()
            logger.info(
                "register_molecules_from_text: %d rows inserted for doc_id=%s",
                len(molecules),
                doc_id,
            )
        except Exception:
            conn.rollback()
            raise
