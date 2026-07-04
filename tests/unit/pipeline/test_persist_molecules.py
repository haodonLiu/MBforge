from pathlib import Path

from mbforge.core.database import DatabaseManager
from mbforge.pipeline.normalize import DetectionSource, NormalizedMolecule
from mbforge.pipeline.persist_molecules import persist_molecule_candidates


def _init_db(tmp_path: Path) -> DatabaseManager:
    project_root = str(tmp_path)
    db = DatabaseManager(project_root)
    db.initialize()
    return db


def _make_candidate(
    *,
    esmiles: str = "CCO",
    canonical_smiles: str = "CCO",
    status: str = "pending",
    detections: list[DetectionSource] | None = None,
) -> NormalizedMolecule:
    if detections is None:
        detections = [
            DetectionSource(
                source="image",
                page=0,
                bbox=(10.0, 20.0, 30.0, 40.0),
                image_path="crops/doc1/crop.png",
                confidence=0.72,
            )
        ]
    return NormalizedMolecule(
        canonical_smiles=canonical_smiles,
        esmiles=esmiles,
        name="ethanol",
        sources=["image"],
        detections=detections,
        status=status,  # type: ignore[arg-type]
    )


def test_persist_creates_detection_rows(tmp_path: Path) -> None:
    db = _init_db(tmp_path)
    candidates = [_make_candidate()]

    persist_molecule_candidates(str(tmp_path), "doc1", candidates)

    with db.mol_conn() as conn:
        rows = conn.execute(
            """
            SELECT doc_id, page, bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                   crop_relpath, conf_moldet, conf_molscribe, vlm_verified_esmiles
            FROM molecule_detections
            """
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["doc_id"] == "doc1"
    assert rows[0]["page"] == 0
    assert rows[0]["bbox_x0"] == 10.0
    assert rows[0]["bbox_y0"] == 20.0
    assert rows[0]["bbox_x1"] == 30.0
    assert rows[0]["bbox_y1"] == 40.0
    assert rows[0]["crop_relpath"] == "crops/doc1/crop.png"
    assert rows[0]["conf_moldet"] == 0.72
    assert rows[0]["conf_molscribe"] is None
    assert rows[0]["vlm_verified_esmiles"] == "CCO"


def test_persist_empty_candidates_list_inserts_nothing(tmp_path: Path) -> None:
    db = _init_db(tmp_path)

    persist_molecule_candidates(str(tmp_path), "doc1", [])

    with db.mol_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM molecule_detections").fetchone()[0]

    assert count == 0


def test_persist_skips_rejected_candidates(tmp_path: Path) -> None:
    db = _init_db(tmp_path)
    candidates = [_make_candidate(status="rejected")]

    persist_molecule_candidates(str(tmp_path), "doc1", candidates)

    with db.mol_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM molecule_detections").fetchone()[0]

    assert count == 0


def test_persist_skips_candidates_without_detections(tmp_path: Path) -> None:
    db = _init_db(tmp_path)
    candidates = [_make_candidate(detections=[])]

    persist_molecule_candidates(str(tmp_path), "doc1", candidates)

    with db.mol_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM molecule_detections").fetchone()[0]

    assert count == 0


def test_persist_inserts_multiple_candidates(tmp_path: Path) -> None:
    db = _init_db(tmp_path)
    candidates = [
        _make_candidate(esmiles="CCO", canonical_smiles="CCO"),
        _make_candidate(
            esmiles="c1ccccc1",
            canonical_smiles="c1ccccc1",
            detections=[
                DetectionSource(
                    source="image",
                    page=1,
                    bbox=(1.0, 2.0, 3.0, 4.0),
                    image_path="crops/doc1/benzene.png",
                    confidence=0.91,
                )
            ],
        ),
    ]

    persist_molecule_candidates(str(tmp_path), "doc1", candidates)

    with db.mol_conn() as conn:
        rows = conn.execute(
            "SELECT vlm_verified_esmiles, page FROM molecule_detections ORDER BY page"
        ).fetchall()

    assert len(rows) == 2
    assert rows[0]["page"] == 0
    assert rows[0]["vlm_verified_esmiles"] == "CCO"
    assert rows[1]["page"] == 1
    assert rows[1]["vlm_verified_esmiles"] == "c1ccccc1"
