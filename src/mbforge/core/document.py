"""Document types — backward-compatibility re-export.

ExtractedContent has moved to `mbforge.core.types`.
New code should import directly from there:

    from mbforge.core.types import ExtractedContent

This file is kept only to avoid breaking any stale imports.
"""

from .types import ExtractedContent

__all__ = ["ExtractedContent"]
