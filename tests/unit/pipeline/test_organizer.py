"""Tests for organizer.py: MoleCode insertion, LLM reorganization, and molecule registration.

The LLM reorganization test is a smoke test that verifies signature and the fallback
path (litellm unavailable / API failure → input is copied to output verbatim).
"""

from __future__ import annotations

import inspect
from pathlib import Path

from mbforge.pipeline.extract_text import PageContent, TextSpan
from mbforge.pipeline.normalize import DetectionSource, NormalizedMolecule
from mbforge.pipeline.organizer import (
    insert_molecode_blocks,
    register_molecules_from_text,
    reorganize_with_llm,
)


def test_insert_molecode_bbox_match(tmp_path: Path) -> None:
    """Molecule bbox overlaps a text span → MoleCode inserted near that span."""
    rough_md = tmp_path / "rough.md"
    rough_md.write_text("<!-- PAGE 1 -->\n# Abstract\nThis is a test molecule.\n\n")

    pages = [
        PageContent(
            page_num=1,
            text="This is a test molecule.",
            text_spans=[
                TextSpan(text="Abstract", bbox=(0, 0, 200, 20), block_type=0),
                TextSpan(
                    text="This is a test molecule.",
                    bbox=(0, 20, 200, 100),
                    block_type=0,
                ),
            ],
        )
    ]
    mol = NormalizedMolecule(
        canonical_smiles="CCO",
        esmiles="CCO",
        name="Ethanol",
        status="pending",
        detections=[
            DetectionSource(source="image", page=0, bbox=(10, 30, 50, 70)),
        ],
    )
    out = tmp_path / "enriched.md"
    insert_molecode_blocks(str(rough_md), pages, [mol], str(out))
    content = out.read_text(encoding="utf-8")
    assert "molecode" in content or "subgraph" in content
    assert "Ethanol" in content


def test_insert_molecode_no_bbox_fallback(tmp_path: Path) -> None:
    """Molecule bbox doesn't overlap any span → MoleCode appended at page-end with annotation."""
    rough_md = tmp_path / "rough.md"
    rough_md.write_text("<!-- PAGE 1 -->\n# Test\nContent.\n<!-- PAGE 2 -->\nMore.\n")

    pages = [
        PageContent(
            page_num=1,
            text="Content.",
            text_spans=[TextSpan(text="Content.", bbox=(0, 0, 100, 50), block_type=0)],
        ),
        PageContent(
            page_num=2,
            text="More.",
            text_spans=[TextSpan(text="More.", bbox=(0, 0, 100, 50), block_type=0)],
        ),
    ]
    mol = NormalizedMolecule(
        canonical_smiles="CCO",
        esmiles="CCO",
        name="Ethanol",
        status="pending",
        detections=[
            DetectionSource(source="image", page=0, bbox=(500, 500, 600, 550)),
        ],
    )
    out = tmp_path / "enriched.md"
    insert_molecode_blocks(str(rough_md), pages, [mol], str(out))
    content = out.read_text(encoding="utf-8")
    assert "molecode" in content or "subgraph" in content
    # Fallback should mention the page number
    assert "Page 1" in content or "(Page 1)" in content


def test_insert_molecode_skips_rejected(tmp_path: Path) -> None:
    """Rejected molecules must not produce MoleCode blocks."""
    rough_md = tmp_path / "rough.md"
    rough_md.write_text("<!-- PAGE 1 -->\n# Test\nContent.\n")

    pages = [
        PageContent(
            page_num=1,
            text="Content.",
            text_spans=[TextSpan(text="Content.", bbox=(0, 0, 100, 50), block_type=0)],
        ),
    ]
    rejected = NormalizedMolecule(
        canonical_smiles="invalid",
        esmiles="invalid",
        name="Bad",
        status="rejected",
        reject_reason="sanitize_failed:AtomValenceException",
        detections=[DetectionSource(source="image", page=0, bbox=(10, 10, 50, 50))],
    )
    out = tmp_path / "enriched.md"
    insert_molecode_blocks(str(rough_md), pages, [rejected], str(out))
    content = out.read_text(encoding="utf-8")
    assert "```molecode" not in content


def test_insert_molecode_multiple_pages(tmp_path: Path) -> None:
    """Multiple molecules on different pages each get a MoleCode block."""
    rough_md = tmp_path / "rough.md"
    rough_md.write_text(
        "<!-- PAGE 1 -->\n# P1\nFirst paragraph.\n\n"
        "<!-- PAGE 2 -->\n# P2\nSecond paragraph.\n\n"
    )
    pages = [
        PageContent(
            page_num=1,
            text="First paragraph.",
            text_spans=[
                TextSpan(text="P1", bbox=(0, 0, 100, 20), block_type=0),
                TextSpan(text="First paragraph.", bbox=(0, 20, 200, 100), block_type=0),
            ],
        ),
        PageContent(
            page_num=2,
            text="Second paragraph.",
            text_spans=[
                TextSpan(text="P2", bbox=(0, 0, 100, 20), block_type=0),
                TextSpan(
                    text="Second paragraph.", bbox=(0, 20, 200, 100), block_type=0
                ),
            ],
        ),
    ]
    mols = [
        NormalizedMolecule(
            canonical_smiles="CCO",
            esmiles="CCO",
            name="Ethanol",
            status="pending",
            detections=[DetectionSource(source="image", page=0, bbox=(10, 30, 50, 70))],
        ),
        NormalizedMolecule(
            canonical_smiles="CCN",
            esmiles="CCN",
            name="Ethylamine",
            status="pending",
            detections=[DetectionSource(source="image", page=1, bbox=(10, 30, 50, 70))],
        ),
    ]
    out = tmp_path / "enriched.md"
    insert_molecode_blocks(str(rough_md), pages, mols, str(out))
    content = out.read_text(encoding="utf-8")
    assert content.count("```molecode") == 2
    assert "Ethanol" in content
    assert "Ethylamine" in content


def test_reorganize_signature() -> None:
    """reorganize_with_llm must accept md_path, output_path, model."""
    sig = inspect.signature(reorganize_with_llm)
    params = list(sig.parameters.keys())
    assert "md_path" in params
    assert "output_path" in params
    assert "model" in params


def test_reorganize_short_doc_no_llm_fallback(tmp_path: Path) -> None:
    """When litellm fails or is unavailable, function must fall back to rule-based reorganization, NOT write the prompt."""
    md = tmp_path / "in.md"
    md.write_text(
        "# Test\nThis is short text.\n```molecode\nsubgraph X\nend\n```\nEnd.\n"
    )
    out = tmp_path / "out.md"
    # Use a definitely-broken model name to trigger the failure path
    result = reorganize_with_llm(str(md), str(out), model="nonexistent/model-xyz-999")
    assert result == str(out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "This is short text." in content
    assert "```molecode" in content
    # Critical: the LLM prompt must NOT be present
    assert "Document:" not in content
    assert "Reorganized:" not in content


def test_register_molecules_signature() -> None:
    """register_molecules_from_text must accept fine_md_path, molecules, doc_id, project_root."""
    sig = inspect.signature(register_molecules_from_text)
    params = list(sig.parameters.keys())
    assert "fine_md_path" in params
    assert "molecules" in params
    assert "doc_id" in params
    assert "project_root" in params


def test_register_molecules_writes_text_links(tmp_path: Path) -> None:
    """register_molecules_from_text inserts text_molecule_links rows with proper excerpts."""
    from mbforge.core.database import DatabaseManager

    fine_md = tmp_path / "fine.md"
    fine_md.write_text(
        "# Section 1\n"
        "Some intro text that surrounds the molecule.\n"
        "```molecode\n"
        'subgraph Ethanol["Ethanol"]\n'
        "end\n"
        "```\n"
        "End.\n"
    )
    mols = [
        NormalizedMolecule(
            canonical_smiles="CCO",
            esmiles="CCO",
            name="Ethanol",
            status="pending",
            detections=[DetectionSource(source="image")],
        )
    ]
    project_root = tmp_path / "proj"
    project_root.mkdir()
    register_molecules_from_text(str(fine_md), mols, "doc-1", str(project_root))

    db = DatabaseManager.get(str(project_root))
    db.initialize()
    with db.mol_conn() as conn:
        rows = conn.execute(
            "SELECT doc_id, text_excerpt, role FROM text_molecule_links WHERE doc_id=?",
            ("doc-1",),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "doc-1"
    assert "Ethanol" in rows[0][1] or "molecode" in rows[0][1]
    assert rows[0][2] == "mentioned"


def test_register_molecules_unresolved_position(tmp_path: Path) -> None:
    """Molecule not present in text → text_excerpt records 'position unresolved'."""
    from mbforge.core.database import DatabaseManager

    fine_md = tmp_path / "fine.md"
    fine_md.write_text("# Section A\nNo molecules here.\n")

    mols = [
        NormalizedMolecule(
            canonical_smiles="CCC",
            esmiles="CCC",
            name="Propane",
            status="pending",
            detections=[DetectionSource(source="image")],
        )
    ]
    project_root = tmp_path / "proj"
    project_root.mkdir()
    register_molecules_from_text(str(fine_md), mols, "doc-2", str(project_root))

    db = DatabaseManager.get(str(project_root))
    db.initialize()
    with db.mol_conn() as conn:
        rows = conn.execute(
            "SELECT text_excerpt FROM text_molecule_links WHERE doc_id=?",
            ("doc-2",),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "position unresolved"


def test_register_molecules_skips_rejected(tmp_path: Path) -> None:
    """Rejected molecules must NOT produce text_molecule_links rows."""
    from mbforge.core.database import DatabaseManager

    fine_md = tmp_path / "fine.md"
    fine_md.write_text("# Test\n```molecode\nsubgraph Bad\nend\n```\n")

    mols = [
        NormalizedMolecule(
            canonical_smiles="x",
            esmiles="x",
            name="Bad",
            status="rejected",
            reject_reason="sanitize_failed",
            detections=[DetectionSource(source="image")],
        )
    ]
    project_root = tmp_path / "proj"
    project_root.mkdir()
    register_molecules_from_text(str(fine_md), mols, "doc-3", str(project_root))

    db = DatabaseManager.get(str(project_root))
    db.initialize()
    with db.mol_conn() as conn:
        rows = conn.execute(
            "SELECT count(*) FROM text_molecule_links WHERE doc_id=?",
            ("doc-3",),
        ).fetchone()
    assert rows[0] == 0


def test_looks_degenerate_strips_molecode() -> None:
    """LLM output that loses MoleCode blocks must trigger fallback."""
    from mbforge.pipeline.organizer import _looks_degenerate

    original = "intro\n```molecode\nsubgraph M\n  C --> N\nend\n```\nmore text"
    stripped = "intro\n```mermaid\ngraph TD\n  A-->B\nend\n```\nmore text"
    assert _looks_degenerate(stripped, original) is True


def test_looks_degenerate_repetitive_output() -> None:
    """LLM output filled with repeated fragments must trigger fallback."""
    from mbforge.pipeline.organizer import _looks_degenerate

    original = "real content with lots of varied text " * 20
    repetitive = ("In some embodiments, A is. " * 80) + (
        "Feel free to adjust the chunks further. " * 30
    )
    assert _looks_degenerate(repetitive, original) is True


def test_looks_degenerate_accepts_clean_output() -> None:
    """Clean reorganized output (MoleCode preserved, varied language) is OK."""
    from mbforge.pipeline.organizer import _looks_degenerate

    original = "intro\n```molecode\nsubgraph M\nend\n```\nmore text"
    clean = "Intro\n```molecode\nsubgraph M\nend\n```\nMore text"
    assert _looks_degenerate(clean, original) is False


def test_looks_degenerate_short_output_not_flagged() -> None:
    """Short outputs (<200 chars) bypass the repetition check entirely."""
    from mbforge.pipeline.organizer import _looks_degenerate

    # Short output without MoleCode but also without repetition
    assert _looks_degenerate("ok", "anything") is False


def test_insert_molecode_respects_bbox_line_position(tmp_path: Path) -> None:
    """Two molecules on the same page must be inserted near their overlapping spans, not both at page end."""
    rough_md = tmp_path / "rough.md"
    rough_md.write_text(
        "<!-- PAGE 1 -->\n"
        "Paragraph one has molecule A.\n"
        "Paragraph two has molecule B.\n"
    )

    pages = [
        PageContent(
            page_num=1,
            text="Paragraph one has molecule A.\nParagraph two has molecule B.",
            text_spans=[
                TextSpan(text="Paragraph one has molecule A.", bbox=(0, 0, 300, 30), block_type=0),
                TextSpan(text="Paragraph two has molecule B.", bbox=(0, 40, 300, 70), block_type=0),
            ],
        )
    ]

    mols = [
        NormalizedMolecule(
            canonical_smiles="CCO",
            esmiles="CCO",
            name="A",
            status="pending",
            detections=[DetectionSource(source="image", page=0, bbox=(10, 5, 50, 25))],
        ),
        NormalizedMolecule(
            canonical_smiles="CCN",
            esmiles="CCN",
            name="B",
            status="pending",
            detections=[DetectionSource(source="image", page=0, bbox=(10, 45, 50, 65))],
        ),
    ]

    out = tmp_path / "enriched.md"
    insert_molecode_blocks(str(rough_md), pages, mols, str(out))
    content = out.read_text(encoding="utf-8")
    lines = content.split("\n")

    molecode_indices = [i for i, line in enumerate(lines) if line.startswith("```molecode")]
    assert len(molecode_indices) == 2
    mol_a_idx, mol_b_idx = molecode_indices

    # The block right after mol_a_idx should contain molecule A's name
    block_a = "\n".join(lines[mol_a_idx:mol_a_idx + 10])
    block_b = "\n".join(lines[mol_b_idx:mol_b_idx + 10])
    assert "A" in block_a
    assert "B" in block_b

    # MoleCode A must appear after paragraph one but before paragraph two
    para_one_idx = next(i for i, line in enumerate(lines) if "Paragraph one" in line)
    para_two_idx = next(i for i, line in enumerate(lines) if "Paragraph two" in line)
    assert para_one_idx < mol_a_idx < para_two_idx
    assert para_two_idx < mol_b_idx
