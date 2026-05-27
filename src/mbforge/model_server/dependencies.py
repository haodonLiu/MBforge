"""FastAPI dependencies for model_server routers."""

from __future__ import annotations

from pathlib import Path

from ..core.project import Project
from ..utils.exceptions import ProjectNotValidError


async def get_project_from_root(project_root: str) -> Project:
    """FastAPI dependency: validate project_root and return a Project instance.

    Raises ProjectNotValidError (HTTP 400) if the path is not a valid project.
    """
    project = Project.open(Path(project_root))
    if project is None:
        raise ProjectNotValidError(
            f"Not a valid MBForge project at: {project_root}"
        )
    return project
