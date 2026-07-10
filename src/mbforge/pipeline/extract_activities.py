"""Activity data extraction from reorganized markdown.

Extracts IC50/Ki/EC50/Kd values from tables and text using LLM-based parsing.
Phase 0 baseline: ~70% accuracy (requires human validation).

Reorganized markdown uses ``<!-- PAGE N -->`` markers (inserted by
``pipeline/organizer.py:insert_molecode_blocks`` before the LLM reorganize
step or stripped by ``_rule_based_reorganize``). We use those markers to
attribute each extracted table to a page so downstream persistence can
do page-proximity linking to detected molecules.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ..utils.logger import get_logger

logger = get_logger("mbforge.pipeline.extract_activities")


_PAGE_MARKER_RE = re.compile(r"<!--\s*PAGE\s+(\d+)\s*-->")
"""Regex matching the ``<!-- PAGE N -->`` markers in reorganized markdown."""


@dataclass
class ActivityRecord:
    """Single activity measurement extracted from text."""

    activity_type: str  # IC50, Ki, EC50, Kd, ED50
    value: float  # Normalized to nM
    value_original: float
    unit: str  # Original unit
    operator: str  # =, <, >, ~, >=, <=
    target: str | None
    assay_type: str | None
    raw_text: str
    confidence: float
    page_num: int | None
    evidence_kind: str  # table, text, figure_caption
    evidence_bbox: dict[str, float] | None
    # Phase 1: row-alignment fields. All None by default → Phase 0 back-compat.
    table_idx: int | None = None   # 文档内表格序号（0-based）
    row_idx: int | None = None     # 表格内行序号（1-based，跳过分隔行）
    col_idx: int | None = None     # 表格内列序号
    row_label: str | None = None   # 第一列的原始文本（如 "1a"、"1b"）
    row_smiles: str | None = None  # 第一列的 SMILES（如有 SMILES 列）


def extract_activities_from_document(
    reorganized_md_path: str,
    doc_id: str,
    llm_model: str = "gpt-4o-mini",
) -> list[ActivityRecord]:
    """Extract activity data from reorganized markdown.

    Args:
        reorganized_md_path: Path to reorganized.md
        doc_id: Document ID
        llm_model: LLM model name for extraction

    Returns:
        List of ActivityRecord objects (may be empty if no activities found)
    """
    from pathlib import Path

    md_text = Path(reorganized_md_path).read_text(encoding="utf-8")

    # Phase 0: 简化实现 — 只做表格抽取，不做 figure caption
    # Phase 1 可扩展到 caption/正文段落
    # Parse page boundaries from the markdown so each table can be attributed
    # to the page it was extracted from. The reorganized markdown uses
    # ``<!-- PAGE N -->`` markers (inserted by insert_molecode_blocks before
    # the LLM reorganize step). When markers are missing (rule-based
    # reorganize strips them) the page is recorded as ``None`` and the
    # downstream persistence layer skips the activity.
    page_boundaries = _collect_page_boundaries(md_text)
    tables = _extract_tables_from_markdown(md_text, page_boundaries)
    if not tables:
        logger.info("No tables found in %s, skipping activity extraction", doc_id)
        return []

    # 使用 LLM 批量解析表格
    records: list[ActivityRecord] = []
    for table_idx, (table_md, page_num) in enumerate(tables):
        try:
            activities = _parse_table_with_llm(
                table_md, table_idx, llm_model, page_num=page_num
            )
            records.extend(activities)
        except Exception as exc:
            logger.warning("Failed to parse table %d in %s: %s", table_idx, doc_id, exc)

    # Phase 1: enrich each record with table row/col coordinates from the
    # raw markdown text, enabling row-alignment persistence downstream.
    records = _enrich_records_with_row_positions(tables, records)

    logger.info("Extracted %d activity records from %s", len(records), doc_id)
    return records


def _collect_page_boundaries(md_text: str) -> list[tuple[int, int]]:
    """Return ordered ``(page_num, line_index)`` for every ``<!-- PAGE N -->`` marker.

    Used by :func:`_extract_tables_from_markdown` to attribute each
    extracted table to the page it lives on.
    """
    boundaries: list[tuple[int, int]] = []
    for lineno, line in enumerate(md_text.split("\n")):
        m = _PAGE_MARKER_RE.match(line.strip())
        if m:
            boundaries.append((int(m.group(1)), lineno))
    return boundaries


def _extract_tables_from_markdown(
    md_text: str,
    page_boundaries: list[tuple[int, int]] | None = None,
) -> list[tuple[str, int | None]]:
    """Extract Markdown tables from text, attributing each to a page.

    Args:
        md_text: Reorganized markdown.
        page_boundaries: Optional list of ``(page_num, line_index)`` from
            :func:`_collect_page_boundaries`. When ``None`` or empty, every
            table is recorded with ``page_num=None``.

    Returns:
        List of ``(table_text, page_num)`` tuples. ``page_num`` is the most
        recent page-marker line index at or before the table's first row.
    """
    # Markdown table pattern: lines starting with '|'
    lines = md_text.split("\n")
    tables: list[tuple[str, int | None]] = []
    current_table: list[str] = []

    # Build a (line_index -> page_num) map from the boundaries so we can
    # look up the page for any line in O(log n) via bisect in larger docs;
    # for Phase 0 (small markdown files) a linear scan is fine and clearer.
    # Build a (line_index -> page_num) map from the boundaries so we can
    # look up the page for any line. Phase 0 (small markdown files) uses
    # a dict keyed by line index; for larger docs a bisect over a sorted
    # list would be O(log n), but the linear scan below dominates only on
    # multi-thousand-line docs that we don't currently produce.
    boundary_by_line: dict[int, int] = {
        line_idx: page for page, line_idx in (page_boundaries or [])
    }

    def _page_for_line(lineno: int) -> int | None:
        if not boundary_by_line:
            return None
        # Latest page boundary at or before this line: pick the boundary
        # whose line index is the largest one that is still <= lineno,
        # and return that boundary's page number.
        best_line: int | None = None
        best_page: int | None = None
        for line_idx, page in boundary_by_line.items():
            if line_idx <= lineno and (best_line is None or line_idx > best_line):
                best_line = line_idx
                best_page = page
        return best_page

    for lineno, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            current_table.append(line)
        else:
            if current_table:
                page_num = _page_for_line(lineno - len(current_table))
                tables.append(("\n".join(current_table), page_num))
                current_table = []

    if current_table:
        page_num = _page_for_line(len(lines) - len(current_table))
        tables.append(("\n".join(current_table), page_num))


def _enrich_records_with_row_positions(
    tables: list[tuple[str, int | None]],
    records: list[ActivityRecord],
) -> list[ActivityRecord]:
    """Fill in row_idx / col_idx for each record by parsing the markdown table.

    For each record that has a ``row_label``, we locate the corresponding
    row in the original table text, assign a 1-based ``row_idx`` (skipping
    the header and separator rows), and determine ``col_idx`` by searching
    which column cell contains the activity value.

    Records without a ``row_label`` or without a matching row retain
    ``row_idx=None`` / ``col_idx=None`` and fall back to page-proximity
    in the persistence layer.
    """
    # Build a (table_idx → raw_table_text) map for fast lookup.
    table_text_by_idx: dict[int, str] = {
        i: md for i, (md, _page) in enumerate(tables)
    }

    separator_re = re.compile(r"^\|[-| ]+\|$")

    for rec in records:
        if rec.table_idx is None or rec.row_label is None:
            continue

        raw_table = table_text_by_idx.get(rec.table_idx)
        if raw_table is None:
            continue

        lines = raw_table.split("\n")
        row_idx = 0
        found = False
        for line in lines:
            stripped = line.strip()
            # Skip separator rows (e.g. |---|---|)
            if separator_re.match(stripped):
                continue
            # Skip header row (first data-bearing row after separator is
            # row 1). Actually, header is the first row, separator is second,
            # data starts at third line. We count data rows only.
            if not stripped.startswith("|") or not stripped.endswith("|"):
                continue
            row_idx += 1
            # First column content
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cells and (
                cells[0].strip().lower() == rec.row_label.strip().lower()
                or (rec.row_smiles and cells[0].strip() == rec.row_smiles.strip())
            ):
                rec.row_idx = row_idx
                # Determine col_idx: search each cell for the numeric
                # activity value string to find the target column.
                for ci, cell in enumerate(cells):
                    if str(rec.value_original) in cell:
                        rec.col_idx = ci
                        break
                found = True
                break

        if not found:
            logger.debug(
                "Row label %r not found in table %d; keeping row_idx=None",
                rec.row_label, rec.table_idx,
            )

    return records

def _parse_table_with_llm(
    table_md: str, table_idx: int, model: str, page_num: int | None = None
) -> list[ActivityRecord]:
    """Parse a Markdown table using LLM.

    Prompt strategy:
    - Few-shot examples from ChEMBL-like SAR tables
    - Structured JSON output (activity_type, value, unit, target, confidence)
    - Confidence scoring based on text clarity

    Args:
        table_md: Markdown table text
        table_idx: Table index in document
        model: LLM model name

    Returns:
        List of ActivityRecord objects
    """
    from ..utils.config import load_global_config

    cfg = load_global_config()

    # Lazy import to avoid circular dependencies
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning("LangChain not available, skipping activity extraction")
        return []

    llm = ChatOpenAI(
        model=model,
        api_key=cfg.llm.api_key or "dummy",
        base_url=cfg.llm.base_url or None,
        temperature=0.0,  # Deterministic extraction
    )

    prompt = _build_extraction_prompt(table_md)

    try:
        response = llm.invoke(prompt)
        result_text = (
            response.content if hasattr(response, "content") else str(response)
        )
        activities_json = _extract_json_from_response(result_text)

        records: list[ActivityRecord] = []
        for item in activities_json:
            # Normalize unit to nM
            value_nm = _normalize_to_nm(item.get("value", 0), item.get("unit", "nM"))
            records.append(
                ActivityRecord(
                    activity_type=item.get("activity_type", "IC50"),
                    value=value_nm,
                    value_original=item.get("value", 0),
                    unit=item.get("unit", "nM"),
                    operator=item.get("operator", "="),
                    target=item.get("target"),
                    assay_type=item.get("assay_type"),
                    raw_text=item.get("raw_text", ""),
                    confidence=item.get("confidence", 0.5),
                    page_num=page_num,
                    evidence_kind="table",
                    evidence_bbox=None,  # TODO: 表格 bbox 需要从 PDF 解析
                    table_idx=table_idx,
                    row_label=item.get("row_label"),
                    row_smiles=item.get("row_smiles"),
                )
            )
        return records
    except Exception as exc:
        logger.warning("LLM parsing failed for table %d: %s", table_idx, exc)
        return []
    return f"""Extract bioactivity data from the following SAR table.

Output a JSON array where each element has:
- activity_type: IC50 | Ki | EC50 | Kd | ED50
- value: numeric value (float)
- unit: nM | μM | mM | pM | M
- operator: = | < | > | ~ | >= | <=
- target: protein/enzyme name (e.g. "EGFR", "HER2", "CDK4/6")
- assay_type: enzymatic | cellular | binding (if mentioned)
- raw_text: exact text from the table
- confidence: 0.0-1.0 (your confidence in this extraction)
- row_label: the first-column cell content of the row this entry came from
  (e.g. "1a", "1b", "Compound 12"). Critical for row-alignment — DO NOT omit.
- row_smiles: the SMILES string if the table has a SMILES column; omit if absent.

Example input:
| Compound | IC50 (nM) EGFR | IC50 (nM) HER2 |
|----------|----------------|----------------|
| 1a       | 10.2           | >1000          |
| 1b       | 5.3            | 450            |

Example output:
```json
[
  {{"activity_type": "IC50", "value": 10.2, "unit": "nM", "operator": "=", "target": "EGFR", "assay_type": "enzymatic", "raw_text": "IC50 (nM) EGFR: 10.2", "confidence": 0.9, "row_label": "1a"}},
  {{"activity_type": "IC50", "value": 1000, "unit": "nM", "operator": ">", "target": "HER2", "assay_type": "enzymatic", "raw_text": "IC50 (nM) HER2: >1000", "confidence": 0.8, "row_label": "1a"}},
  {{"activity_type": "IC50", "value": 5.3, "unit": "nM", "operator": "=", "target": "EGFR", "assay_type": "enzymatic", "raw_text": "IC50 (nM) EGFR: 5.3", "confidence": 0.95, "row_label": "1b"}},
  {{"activity_type": "IC50", "value": 450, "unit": "nM", "operator": "=", "target": "HER2", "assay_type": "enzymatic", "raw_text": "IC50 (nM) HER2: 450", "confidence": 0.9, "row_label": "1b"}}
]
```

Now extract from this table:

{table_md}

Output only the JSON array, no explanations."""


def _extract_json_from_response(text: str) -> list[dict[str, Any]]:
    """Extract JSON array from LLM response (handles markdown code blocks)."""
    # Remove markdown code fences
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    text = text.strip()

    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError as exc:
        logger.warning("JSON decode failed: %s", exc)
        return []


def _normalize_to_nm(value: float, unit: str) -> float:
    """Convert activity value to nM."""
    unit_lower = unit.lower()
    if unit_lower in ("nm", "nanomolar"):
        return value
    if unit_lower in ("um", "μm", "micromolar"):
        return value * 1000
    if unit_lower in ("mm", "millimolar"):
        return value * 1_000_000
    if unit_lower in ("pm", "picomolar"):
        return value / 1000
    if unit_lower in ("m", "molar"):
        return value * 1_000_000_000
    logger.warning("Unknown unit %s, assuming nM", unit)
    return value
