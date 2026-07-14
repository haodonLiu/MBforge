"""Core path-sanitization helpers.

These helpers live in ``core`` so that core modules (e.g. ``LibraryStore``)
can sanitize filenames without importing from the router layer.
"""

from __future__ import annotations

import re

from ..utils.helpers import MBForgeError


class InvalidPathError(MBForgeError):
    """Raised when a request path is empty, malformed, or escapes the library."""

    status_code = 400
    error_code = "invalid_path"


def sanitize_upload_filename(filename: str) -> str:
    """Return a safe upload filename.

    Rejects empty names and any path segment that is ``.`` or ``..`` after
    splitting on ``/`` and ``\\``. All other names are reduced to their final
    segment, so names like ``report..pdf`` are allowed but ``../passwd`` is
    rejected.
    """
    if not filename:
        raise InvalidPathError("filename is required")

    segments = re.split(r"[/\\]", filename)
    if any(seg in (".", "..") for seg in segments):
        raise InvalidPathError(
            f"filename contains path traversal: {filename!r}"
        )

    safe = filename.replace("\\", "/").split("/")[-1]
    if not safe or safe in (".", ".."):
        raise InvalidPathError(f"invalid filename: {filename!r}")
    return safe
