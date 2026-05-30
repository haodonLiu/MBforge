"""项目级别设置管理."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from ..utils.constants import PROJECT_META_DIR, SETTINGS_FILE
from ..utils.helpers import load_json, save_json


@dataclass
class ProjectSettings:
    """单个项目的配置."""

    name: str = "Untitled Project"
    description: str = ""
    created_at: str = ""
    llm_model: str = "default"
    embed_model: str = "default"
    auto_index: bool = True  # 自动索引新文档
    auto_process: bool = True  # 导入文件后自动处理（False = 手动触发）
    pdf_ocr_enabled: bool = True
    pdf_extract_molecules: bool = True
    theme_override: str = "system"  # "system" | "light" | "dark"
    # 工作流开关
    workflows_enabled: dict[str, bool] = field(
        default_factory=lambda: {
            "generation": False,
            "docking": False,
            "qsar": False,
            "md": False,
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectSettings:
        return cls(
            name=data.get("name", "Untitled Project"),
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            llm_model=data.get("llm_model", "default"),
            embed_model=data.get("embed_model", "default"),
            auto_index=data.get("auto_index", True),
            auto_process=data.get("auto_process", True),
            pdf_ocr_enabled=data.get("pdf_ocr_enabled", True),
            pdf_extract_molecules=data.get("pdf_extract_molecules", True),
            theme_override=data.get("theme_override", "system"),
            workflows_enabled=data.get(
                "workflows_enabled",
                {"generation": False, "docking": False, "qsar": False, "md": False},
            ),
        )

    @classmethod
    def load(cls, project_root: Path) -> ProjectSettings:
        path = project_root / PROJECT_META_DIR / SETTINGS_FILE
        data = load_json(path)
        if data is not None:
            return cls.from_dict(data)
        return cls()

    def save(self, project_root: Path) -> None:
        path = project_root / PROJECT_META_DIR / SETTINGS_FILE
        save_json(path, self.to_dict())
