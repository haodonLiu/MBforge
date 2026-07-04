from pathlib import Path

from mbforge.pipeline.normalize import DetectionSource, NormalizedMolecule
from mbforge.pipeline.persist_molecules import persist_molecule_candidates


def test_persist_creates_detection_rows(tmp_path: Path) -> None:
    from mbforge.core.database import DatabaseManager

    project_root = str(tmp_path)
    db = DatabaseManager(project_root)
    db.initialize()

    candidates = [
        NormalizedMolecule(
            canonical_smiles="CCO",
            esmiles="CCO",
            name="ethanol",
            sources=["image"],
            detections=[
                DetectionSource(
                    source="image",
                    page=0,
                    bbox=(10.0, 20.0, 30.0, 40.0),
                    image_path="crops/doc1/crop.png",
                    confidence=0.72,
                )
            ],
            status="pending",
        )
    ]

    persist_molecule_candidates(project_root, "doc1", candidates)

    with db.mol_conn() as conn:
        rows = conn.execute(
            "SELECT doc_id, page, conf_moldet, conf_molscribe, vlm_verified_esmiles FROM molecule_detections"
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["doc_id"] == "doc1"
    assert rows[0]["page"] == 0
    assert rows[0]["vlm_verified_esmiles"] == "CCO"
