"""CLI entry point: ``python -m mbforge.migrate-library <library_root>``.

Phase 4 of the path-migration plan. See
``src/mbforge/core/migration.py`` for the full migration flow.
"""

from __future__ import annotations

import sys

from .core.migration import main

if __name__ == "__main__":
    sys.exit(main())
