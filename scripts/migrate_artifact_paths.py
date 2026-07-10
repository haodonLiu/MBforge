"""One-shot migration: move crop files from legacy .mbforge/crops/ to storage/{doc_id}/crops/.

Background
==========

Before 2026-07-10 the pipeline wrote molecule crop images to
``{library_root}/.mbforge/crops/{doc_id}/{filename}.png`` while the library
router served artifacts from ``{library_root}/storage/{doc_id}/...``. This
script unifies the layout so all artifacts live under
``{library_root}/storage/{doc_id}/`` — a prerequisite for the new
``ArtifactResolver`` (see ``src/mbforge/core/artifact.py``).

Usage
=====

::

    uv run python scripts/migrate_artifact_paths.py {library_root}

The script is idempotent:

* If a destination file already exists in ``storage/{doc_id}/crops/``, the
  source is left in place (the destination wins; the source can be removed
  by hand later).
* If ``.mbforge/crops/`` does not exist at all, the script logs and exits 0.

The script also updates the ``evidence.crop_relpath`` and
``molecule_detections.crop_relpath`` columns in
``{library_root}/index/molecules.db`` so the new crop paths take effect on
the next read.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path


def migrate(library_root: Path) -> int:
    """Run the migration. Returns the number of files moved."""
    if not library_root.is_dir():
        print(f"ERROR: library_root is not a directory: {library_root}", file=sys.stderr)
        return 1

    legacy_root = library_root / ".mbforge" / "crops"
    if not legacy_root.is_dir():
        print(f"No legacy crops at {legacy_root}; nothing to migrate.")
        return 0

    db_path = library_root / "index" / "molecules.db"
    if not db_path.is_file():
        print(
            f"WARNING: {db_path} not found; skipping DB updates. "
            f"Files will still be moved on disk."
        )
        conn = None
    else:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")

    moved = 0
    skipped = 0
    for doc_dir in sorted(p for p in legacy_root.iterdir() if p.is_dir()):
        doc_id = doc_dir.name
        # Validate doc_id; skip directories with unsafe names.
        if not doc_id or "/" in doc_id or ".." in doc_id:
            print(f"WARNING: skipping unsafe doc_id: {doc_id!r}")
            continue
        canonical_dir = library_root / "storage" / doc_id / "crops"
        canonical_dir.mkdir(parents=True, exist_ok=True)
        for crop in sorted(doc_dir.iterdir()):
            if not crop.is_file():
                continue
            target = canonical_dir / crop.name
            if target.is_file():
                print(f"  [skip] {crop.relative_to(library_root)} (target exists)")
                skipped += 1
                continue
            try:
                shutil.move(str(crop), str(target))
                print(f"  [moved] {crop.relative_to(library_root)} -> {target.relative_to(library_root)}")
                moved += 1
            except Exception as exc:  # pragma: no cover - defensive
                print(f"  ERROR: failed to move {crop}: {exc}", file=sys.stderr)
        # If the source directory is empty, drop it.
        try:
            if not any(doc_dir.iterdir()):
                doc_dir.rmdir()
        except OSError:
            pass

    # Update crop_relpath in the DB to the canonical prefix. Each table is
    # updated independently so a missing table does not roll back the rest.
    if conn is not None:
        for table in ("evidence", "molecule_detections"):
            try:
                before = conn.execute(
                    f"SELECT COUNT(*) FROM {table} "
                    f"WHERE crop_relpath LIKE '.mbforge/crops/%'"
                ).fetchone()[0]
            except sqlite3.OperationalError as exc:
                print(f"  [skip] {table}: {exc}")
                continue
            try:
                conn.execute(
                    f"""
                    UPDATE {table}
                    SET crop_relpath = 'storage/' || doc_id || '/crops/' ||
                        REPLACE(crop_relpath, '.mbforge/crops/' || doc_id || '/', '')
                    WHERE crop_relpath LIKE '.mbforge/crops/%'
                    """
                )
                conn.commit()
                after = conn.execute(
                    f"SELECT COUNT(*) FROM {table} "
                    f"WHERE crop_relpath LIKE '.mbforge/crops/%'"
                ).fetchone()[0]
                print(
                    f"  {table} rows updated: {before - after} "
                    f"(remaining legacy: {after})"
                )
            except Exception as exc:  # pragma: no cover - defensive
                print(f"  ERROR: {table} update failed: {exc}", file=sys.stderr)
                conn.rollback()
        conn.close()

    print(f"Done. moved={moved} skipped={skipped}")
    # If the legacy root is empty, drop it.
    try:
        if legacy_root.is_dir() and not any(legacy_root.iterdir()):
            legacy_root.rmdir()
            print(f"Removed empty legacy root: {legacy_root}")
    except OSError:
        pass
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "library_root",
        type=Path,
        help="Path to the library root directory",
    )
    args = parser.parse_args()
    return migrate(args.library_root.resolve())


if __name__ == "__main__":
    sys.exit(main())
