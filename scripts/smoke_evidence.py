"""One-shot smoke test for the evidence-linked infrastructure.

Not a pytest test (the project has no tests/ dir in this snapshot). Run
directly:

    uv run python scripts/smoke_evidence.py

Exits 0 on success, non-zero on the first failed assertion.
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path


def main() -> int:
    # Late imports — keep the script self-contained.
    from mbforge.core.database import DatabaseManager
    from mbforge.core.artifact import ArtifactResolver
    from mbforge.routers.molecule import mol_list, mol_evidence
    from mbforge.routers.library import _resolve_doc_artifact, _resolve_crop_artifact
    from mbforge.pipeline.persist_molecules import persist_molecule_candidates
    from mbforge.pipeline.normalize import DetectionSource, NormalizedMolecule
    from mbforge.models.molecule import MoleculeListRequest

    td = Path(tempfile.mkdtemp())
    try:
        # 1. Initialize DB
        db = DatabaseManager(td)
        db.initialize()
        with db.mol_conn() as conn:
            sv = conn.execute("SELECT version FROM schema_version").fetchone()[0]
            assert sv == 5, f"expected schema_version=5, got {sv}"
            print(f"[1] DB initialized, schema_version={sv}")

        # 2. Create storage layout for doc1, doc2
        storage1 = ArtifactResolver(td).storage_dir("doc1")
        storage2 = ArtifactResolver(td).storage_dir("doc2")
        storage1.mkdir(parents=True)
        storage2.mkdir(parents=True)
        (storage1 / "source.pdf").write_bytes(b"%PDF-1.4 fake")
        (storage2 / "source.pdf").write_bytes(b"%PDF-1.4 fake")
        print(f"[2] storage layout created at {storage1}")

        # 3. Persist molecules (figure kind) — same canonical_smiles in two docs
        candidates = [
            NormalizedMolecule(
                canonical_smiles="CCO",
                esmiles="CCO",
                name="ethanol",
                sources=["image"],
                detections=[
                    DetectionSource(
                        source="image",
                        page=3,
                        bbox=(10.0, 20.0, 50.0, 60.0),
                        image_path=str(storage1 / "crops" / "doc1_p3_m0.png"),
                        confidence=0.92,
                    )
                ],
                status="pending",
            ),
            NormalizedMolecule(
                canonical_smiles="CCO",
                esmiles="CCO",
                name="ethanol",
                sources=["image"],
                detections=[
                    DetectionSource(
                        source="image",
                        page=7,
                        bbox=(100.0, 200.0, 200.0, 300.0),
                        image_path=str(storage2 / "crops" / "doc2_p7_m0.png"),
                        confidence=0.88,
                    )
                ],
                status="pending",
            ),
            NormalizedMolecule(
                canonical_smiles="CCN",
                esmiles="CCN",
                name="ethylamine",
                sources=["image"],
                detections=[
                    DetectionSource(
                        source="image",
                        page=1,
                        bbox=(5.0, 5.0, 25.0, 25.0),
                        image_path=str(storage1 / "crops" / "doc1_p1_m0.png"),
                        confidence=0.75,
                    )
                ],
                status="pending",
            ),
        ]
        persist_molecule_candidates(str(td), "doc1", [candidates[0], candidates[2]])
        persist_molecule_candidates(str(td), "doc2", [candidates[1]])
        print("[3] Persisted: 2 distinct canonical SMILES, 3 detections across 2 docs")

        # 4. Verify counts
        with db.mol_conn() as conn:
            nm = conn.execute("SELECT COUNT(*) FROM molecules").fetchone()[0]
            ne = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            assert nm == 2, f"expected 2 molecules, got {nm}"
            assert ne == 3, f"expected 3 evidence rows, got {ne}"
            print(f"[4] molecules={nm}, evidence={ne}")

        # 5. List endpoint - each row should have evidence
        body = MoleculeListRequest(
            library_root=str(td), page=1, page_size=10, status=""
        )
        r = asyncio.run(mol_list(body))
        assert r["success"], r
        assert len(r["items"]) == 2
        cco = next(i for i in r["items"] if i["mol_id"] == "CCO")
        ccn = next(i for i in r["items"] if i["mol_id"] == "CCN")
        assert cco["evidence_total"] == 2, cco
        assert ccn["evidence_total"] == 1, ccn
        assert cco["evidence"][0]["crop_url"] is not None
        print(
            f"[5] list: CCO evidence_total={cco['evidence_total']}, "
            f"crop_url present={cco['evidence'][0]['crop_url'] is not None}"
        )

        # 6. Evidence endpoint - full chain
        r2 = asyncio.run(mol_evidence({"library_root": str(td), "canonical_smiles": "CCO"}))
        assert r2["success"], r2
        assert len(r2["evidence"]) == 2
        print(f"[6] evidence CCO count={len(r2['evidence'])}")

        # 7. Artifact resolver — read source PDF
        p = _resolve_doc_artifact(td, "doc1", "source.pdf")
        assert p.is_file(), f"source PDF not found: {p}"
        print(f"[7] source PDF resolves: {p.name}")

        # 8. Legacy + new crop coexistence
        legacy = td / ".mbforge" / "crops" / "doc1"
        legacy.mkdir(parents=True)
        (legacy / "old_crop.png").write_bytes(b"old")
        new_crops = ArtifactResolver(td).crops_dir("doc1")
        new_crops.mkdir(parents=True, exist_ok=True)
        (new_crops / "new_crop.png").write_bytes(b"new")
        found_new = _resolve_crop_artifact(td, "doc1", "new_crop.png")
        found_legacy = _resolve_crop_artifact(td, "doc1", "old_crop.png")
        assert found_new.is_file()
        assert found_legacy.is_file()
        print(f"[8] crop resolve new={found_new.is_file()}, legacy={found_legacy.is_file()}")

        # 9. Migration script moves legacy crops and updates DB
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import importlib

        import migrate_artifact_paths

        importlib.reload(migrate_artifact_paths)
        from migrate_artifact_paths import migrate

        rc = migrate(td)
        assert rc == 0
        legacy_root = td / ".mbforge" / "crops"
        assert not legacy_root.exists() or not any(legacy_root.iterdir())
        assert (new_crops / "old_crop.png").is_file()
        print("[9] migration moved legacy crop to canonical location")

        # 10. Path traversal rejected
        from fastapi import HTTPException

        try:
            _resolve_doc_artifact(td, "../etc", "x")
        except HTTPException as e:
            assert e.status_code == 400
            print(f"[10] traversal rejected: HTTP {e.status_code}")
        else:
            raise AssertionError("expected HTTPException for traversal")

        print()
        print("ALL CHECKS PASSED")
        return 0
    finally:
        shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
