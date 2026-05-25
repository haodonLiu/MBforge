"""分子提取统一数据契约.

所有提取来源（图像检测、文本正则、手动录入）都输出此统一结构，
供下游审核、入库、展示使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Tuple


@dataclass
class ExtractionResult:
    """分子提取结果.

    Attributes:
        smiles: 识别出的 SMILES 字符串（待确认或已确认）
        name: 化合物名称（可选）
        source: 来源类型：image=图像检测, text=文本正则, manual=手动录入
        moldet_conf: MolDetv2 检测置信度（图像来源时有效）
        scribe_conf: MolScribe 识别置信度（图像来源时有效）
        composite_conf: 综合置信度（默认 moldet_conf * scribe_conf）
        bbox_pdf: PDF 坐标系中的边界框（点单位，左下原点）
        page_idx: PDF 页码（从 0 开始）
        context_text: 关联到的文本上下文（caption / 段落 / 表格单元格）
        mol_img_path: 裁剪保存的分子图像路径（图像来源时有效）
        status: 审核状态：pending=待确认, confirmed=已入库, rejected=已丢弃
    """

    smiles: str
    name: str = ""
    source: Literal["image", "text", "manual"] = "image"
    moldet_conf: float = 0.0
    scribe_conf: float = 0.0
    composite_conf: float = 0.0
    bbox_pdf: Optional[Tuple[float, float, float, float]] = None
    page_idx: Optional[int] = None
    context_text: str = ""
    mol_img_path: Optional[Path] = None
    status: Literal["pending", "confirmed", "rejected"] = "pending"
    properties: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """自动计算综合置信度."""
        if self.composite_conf == 0.0 and (self.moldet_conf or self.scribe_conf):
            self.composite_conf = self.moldet_conf * self.scribe_conf

    def to_dict(self) -> dict:
        """序列化为字典."""
        return {
            "smiles": self.smiles,
            "name": self.name,
            "source": self.source,
            "moldet_conf": self.moldet_conf,
            "scribe_conf": self.scribe_conf,
            "composite_conf": self.composite_conf,
            "bbox_pdf": self.bbox_pdf,
            "page_idx": self.page_idx,
            "context_text": self.context_text,
            "mol_img_path": str(self.mol_img_path) if self.mol_img_path else None,
            "status": self.status,
            "properties": self.properties,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExtractionResult":
        """从字典反序列化."""
        img_path = data.get("mol_img_path")
        return cls(
            smiles=data.get("smiles", ""),
            name=data.get("name", ""),
            source=data.get("source", "image"),
            moldet_conf=data.get("moldet_conf", 0.0),
            scribe_conf=data.get("scribe_conf", 0.0),
            composite_conf=data.get("composite_conf", 0.0),
            bbox_pdf=tuple(data["bbox_pdf"]) if data.get("bbox_pdf") else None,
            page_idx=data.get("page_idx"),
            context_text=data.get("context_text", ""),
            mol_img_path=Path(img_path) if img_path else None,
            status=data.get("status", "pending"),
            properties=data.get("properties", {}),
        )
