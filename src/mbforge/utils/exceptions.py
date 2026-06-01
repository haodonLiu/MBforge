"""Centralized exception hierarchy for MBForge.

All domain exceptions inherit from MBForgeError, which carries
an HTTP status code and a machine-readable error code.
The model_server global exception handler converts these to
structured JSON responses automatically.
"""

from __future__ import annotations


class MBForgeError(Exception):
    """Base exception with HTTP status code and error code."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class ProjectNotValidError(MBForgeError):
    """Path exists but is not a valid MBForge project."""

    status_code = 400
    error_code = "project_not_valid"


class ModelNotAvailableError(MBForgeError):
    """AI model failed to load or is not configured."""

    status_code = 503
    error_code = "model_not_available"


class ConfigError(MBForgeError):
    """Configuration file is missing or malformed."""

    status_code = 400
    error_code = "config_error"


class ValidationError(MBForgeError):
    """Request validation failed."""

    status_code = 422
    error_code = "validation_error"


class FileAccessError(MBForgeError):
    """File read/write failed."""

    status_code = 400
    error_code = "file_access_error"


class PathTraversalError(MBForgeError):
    """Path traversal attack detected."""

    status_code = 403
    error_code = "path_traversal"


class ResourceNotAvailableError(MBForgeError):
    """External resource (model, package) not downloaded or unavailable."""

    status_code = 503
    error_code = "resource_not_available"


class ToolExecutionError(MBForgeError):
    """Agent tool execution failed."""

    status_code = 500
    error_code = "tool_execution_error"
