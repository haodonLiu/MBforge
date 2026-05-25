"""PDF 标注数据模型 — 检测框与用户高亮独立存储."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Literal


@dataclass
class DetectionBox:
    """AI 检测出的分子框，独立于用户高亮."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    page_idx: int = 0
    bbox_pdf: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    smiles: str = ""
    name: str = ""
    status: Literal["pending", "confirmed", "rejected", "corrected"] = "pending"
    moldet_conf: float = 0.0
    scribe_conf: float = 0.0
    corrected_esmiles: str = ""
    comment: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> DetectionBox:
        return cls(**d)


@dataclass
class TextHighlight:
    """用户划词高亮，支持颜色、下划线、批注."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    page_idx: int = 0
    bbox_pdf: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    text: str = ""
    color: tuple[float, float, float] = (1.0, 1.0, 0.0)
    style: Literal["background", "underline"] = "background"
    comment: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> TextHighlight:
        return cls(**d)


class AnnotationStore:
    """管理单份 PDF 的全部标注，提供 JSON 持久化."""

    def __init__(self) -> None:
        self.detections: list[DetectionBox] = []
        self.highlights: list[TextHighlight] = []

    def get_page_detections(self, page_idx: int) -> list[DetectionBox]:
        return [d for d in self.detections if d.page_idx == page_idx]

    def get_page_highlights(self, page_idx: int) -> list[TextHighlight]:
        return [h for h in self.highlights if h.page_idx == page_idx]

    def get_detection_by_id(self, det_id: str) -> DetectionBox | None:
        for d in self.detections:
            if d.id == det_id:
                return d
        return None

    def get_highlight_by_id(self, hl_id: str) -> TextHighlight | None:
        for h in self.highlights:
            if h.id == hl_id:
                return h
        return None

    def remove_detection(self, det_id: str) -> bool:
        for i, d in enumerate(self.detections):
            if d.id == det_id:
                self.detections.pop(i)
                return True
        return False

    def remove_highlight(self, hl_id: str) -> bool:
        for i, h in enumerate(self.highlights):
            if h.id == hl_id:
                self.highlights.pop(i)
                return True
        return False

    def clear_page(self, page_idx: int) -> None:
        self.detections = [d for d in self.detections if d.page_idx != page_idx]
        self.highlights = [h for h in self.highlights if h.page_idx != page_idx]

    def clear_all(self) -> None:
        self.detections.clear()
        self.highlights.clear()

    def to_dict(self) -> dict:
        return {
            "version": 2,
            "detections": [d.to_dict() for d in self.detections],
            "highlights": [h.to_dict() for h in self.highlights],
        }

    @classmethod
    def from_dict(cls, data: dict) -> AnnotationStore:
        store = cls()
        ver = data.get("version", 1)
        if ver == 1:
            for page_str, anns in data.get("annotations", {}).items():
                pidx = int(page_str)
                for ann in anns:
                    rect = tuple(ann.get("rect", [0.0, 0.0, 0.0, 0.0]))
                    text = ann.get("text", "")
                    color = tuple(ann.get("color", [1.0, 1.0, 0.0]))
                    if ann.get("source") == "detection" or (
                        text.startswith("SMILES:") or ann.get("type") == "detection"
                    ):
                        store.detections.append(
                            DetectionBox(
                                page_idx=pidx,
                                bbox_pdf=rect,
                                smiles=text,
                            )
                        )
                    else:
                        store.highlights.append(
                            TextHighlight(
                                page_idx=pidx,
                                bbox_pdf=rect,
                                text=text,
                                color=color,
                            )
                        )
        else:
            store.detections = [
                DetectionBox.from_dict(d) for d in data.get("detections", [])
            ]
            store.highlights = [
                TextHighlight.from_dict(h) for h in data.get("highlights", [])
            ]
        return store
