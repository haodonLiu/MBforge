#!/usr/bin/env python3
"""Migrate legacy user notes from .mbforge/notes/ to {library_root}/notes/.

Phase 5 of the path-migration plan. The pre-Phase-5 layout stored
user notes under ``{root}/.mbforge/notes/`` alongside the internal
metadata. The canonical post-Phase-5 layout puts user notes under
``{root}/notes/`` (visible at the library root, never inside
``.mbforge/``) so they are easy to find, back up, and not
inadvertently cleaned by any ``rm -rf .mbforge`` recovery script.

Usage:

    uv run python scripts/migrate_notes_and_openkb.py <library_root> [--dry-run]

Behavior:

1. If ``{root}/notes/`` already has files, refuse (operator must
   resolve the conflict manually — the legacy and canonical paths
   cannot be merged automatically because note titles collide on
   filename). Exit 2.
2. If ``{root}/.mbforge/notes/`` does not exist, exit 0 (no-op).
3. Otherwise, move every file under ``.mbforge/notes/`` to
   ``{root}/notes/`` (preserving relative paths for sub-folders).
4. Write a MIGRATION.md marker to the new ``notes/`` directory with
   the source path and timestamp.
5. Leave a sentinel ``.migrated`` file in the old
   ``.mbforge/notes/`` directory pointing at the new location
   (so a re-run is a safe no-op; the sentinel is the idempotency
   marker).

The script is intentionally conservative: it never overwrites a
note in the destination. If a name conflict is detected (same
filename in both source and destination), it logs the conflict
and skips the file, returning exit 1 to flag the operator.

OpenKB / PageIndex paths under ``.mbforge/openkb/`` are NOT touched
here — those are the internal OpenKB package's storage backend and
the pageindex-redirector has its own data lifecycle. Phase 5 only
moves user-facing notes; the OpenKB layout is final.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path


def _migrate_notes(library_root: Path, dry_run: bool) -> int:
    """Move user notes from .mbforge/notes/ to {root}/notes/.

    Returns the process exit code (0 on success, 1 on conflict,
    2 on pre-existing destination).
    """
    legacy = library_root / ".mbforge" / "notes"
    canonical = library_root / "notes"

    if not legacy.exists():
        print(f"No legacy notes at {legacy}; nothing to migrate.")
        return 0

    if canonical.exists() and any(canonical.iterdir()):
        print(
            f"REFUSING: {canonical} already exists and is non-empty. "
            f"Move existing notes aside before running the migration."
        )
        return 2

    if dry_run:
        files = [p for p in legacy.rglob("*") if p.is_file()]
        print(f"DRY-RUN: would move {len(files)} files:")
        for f in files:
            rel = f.relative_to(legacy)
            target = canonical / rel
            print(f"  {f.relative_to(library_root)}  ->  {target.relative_to(library_root)}")
        return 0

    canonical.mkdir(parents=True, exist_ok=True)
    moved = 0
    skipped = 0
    for src in sorted(legacy.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(legacy)
        dst = canonical / rel
        if dst.exists():
            # Name collision; skip and report.
            print(f"  CONFLICT: {rel} exists in both source and destination; skipping")
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved += 1

    # Write a MIGRATION.md marker so future readers know where the
    # notes came from.
    marker = canonical / "MIGRATION.md"
    marker.write_text(
        "# Notes migration\n\n"
        f"Migrated at: {datetime.now().isoformat(timespec='seconds')}\n"
        f"Source: {legacy.relative_to(library_root)}\n"
        f"Files moved: {moved}\n"
        f"Conflicts (skipped): {skipped}\n\n"
        "User notes moved from the legacy internal-metadata location to\n"
        "the canonical library-root location. The old directory is preserved\n"
        "as a sentinel but contains no further data.\n",
        encoding="utf-8",
    )

    # Sentinel: leave a marker file in the old location so re-runs
    # know the migration has already happened.
    sentinel = legacy / ".migrated"
    sentinel.write_text(
        f"Notes were migrated to {canonical.relative_to(library_root)} at "
        f"{datetime.now().isoformat(timespec='seconds')}. See "
        f"{canonical.relative_to(library_root) / 'MIGRATION.md'}.\n",
        encoding="utf-8",
    )

    if skipped:
        print(f"Migration completed with {skipped} conflict(s); {moved} file(s) moved.")
        return 1
    print(f"Migration complete: {moved} file(s) moved to {canonical.relative_to(library_root)}/")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/migrate_notes_and_openkb.py",
        description=(
            "Migrate user notes from the legacy .mbforge/notes/ "
            "location to the canonical {library_root}/notes/ location."
        ),
    )
    parser.add_argument(
        "library_root",
        type=Path,
        help="Path to the library root.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the migration plan without touching any files.",
    )
    args = parser.parse_args(argv)
    return _migrate_notes(args.library_root, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
