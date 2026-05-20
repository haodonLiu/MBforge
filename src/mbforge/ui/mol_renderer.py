"""分子结构渲染组件.

使用 RDKit 将 SMILES 渲染为图片，在 PyQt 界面中显示。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

try:
    from rdkit import Chem
    from rdkit.Chem import Draw
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False
    Chem = None  # type: ignore
    Draw = None  # type: ignore


class MoleculeRenderer:
    """分子渲染器，将 SMILES 转换为 QPixmap."""

    DEFAULT_SIZE = (320, 240)

    @classmethod
    def smiles_to_pixmap(
        cls,
        smiles: str,
        size: tuple[int, int] | None = None,
        legend: str = "",
    ) -> Optional[QPixmap]:
        """将 SMILES 渲染为 QPixmap.

        Args:
            smiles: SMILES 字符串
            size: 图片尺寸 (宽, 高)
            legend: 图片底部图例文字

        Returns:
            QPixmap 或 None（渲染失败/RDKit 未安装）
        """
        if not RDKIT_AVAILABLE or not smiles:
            return None

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        width, height = size or cls.DEFAULT_SIZE

        try:
            # RDKit 生成 PNG 字节
            img_bytes = Draw.MolToImage(
                mol,
                size=(width, height),
                legend=legend,
                kekulize=True,
            )
            # PIL Image → PNG bytes
            buf = io.BytesIO()
            img_bytes.save(buf, format="PNG")
            buf.seek(0)

            # PNG bytes → QPixmap
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue())
            return pixmap
        except Exception:
            return None

    @classmethod
    def smiles_to_file(
        cls,
        smiles: str,
        path: Path,
        size: tuple[int, int] | None = None,
        legend: str = "",
    ) -> bool:
        """将 SMILES 渲染为图片文件."""
        if not RDKIT_AVAILABLE:
            return False

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False

        width, height = size or cls.DEFAULT_SIZE
        try:
            Draw.MolToFile(
                mol,
                filename=str(path),
                size=(width, height),
                legend=legend,
                kekulize=True,
            )
            return True
        except Exception:
            return False


class MoleculeImageWidget(QWidget):
    """显示分子结构图片的组件."""

    def __init__(
        self,
        smiles: str = "",
        size: tuple[int, int] | None = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._smiles = smiles
        self._size = size or MoleculeRenderer.DEFAULT_SIZE
        self._setup_ui()
        if smiles:
            self.set_smiles(smiles)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(*self._size)
        self.image_label.setStyleSheet("""
            QLabel {
                background: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 12px;
            }
        """)
        layout.addWidget(self.image_label)

    def set_smiles(self, smiles: str, legend: str = ""):
        """设置并渲染新的 SMILES."""
        self._smiles = smiles
        pixmap = MoleculeRenderer.smiles_to_pixmap(smiles, self._size, legend)
        if pixmap:
            self.image_label.setPixmap(pixmap)
        else:
            self.image_label.setText("无法渲染分子结构\n" + (smiles or "-"))
            self.image_label.setStyleSheet("""
                QLabel {
                    background: #f8f9fa;
                    border: 1px solid #e9ecef;
                    border-radius: 12px;
                    color: #868e96;
                    padding: 20px;
                }
            """)

    def clear(self):
        """清空显示."""
        self.image_label.clear()
        self._smiles = ""
