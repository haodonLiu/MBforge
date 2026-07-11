"""Pipeline stages — modular executors for document processing.

Each stage is a self-contained class implementing the StageExecutor protocol:
- Reads from PipelineContext
- Performs one logical step
- Writes results back to PipelineContext
- Returns StageResult

Usage:
    from .stages import ExtractStage, DensityStage, ...

    ctx = PipelineContext(...)
    stage = ExtractStage()
    result = stage.execute(ctx)
"""

from .activity_stage import ActivityStage
from .base import StageExecutor
from .density_stage import DensityStage
from .extract_stage import ExtractStage
from .index_stage import IndexStage
from .markdown_stage import MarkdownStage
from .persist_stage import PersistStage
from .reorganize_stage import ReorganizeStage

__all__ = [
    "StageExecutor",
    "ExtractStage",
    "DensityStage",
    "MarkdownStage",
    "ReorganizeStage",
    "ActivityStage",
    "IndexStage",
    "PersistStage",
]
