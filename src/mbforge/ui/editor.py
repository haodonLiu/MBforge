"""Markdown 编辑器."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QPlainTextEdit,
    QWidget,
)


class MarkdownEditor(QPlainTextEdit):
    """简易 Markdown 编辑器."""

    content_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.file_path: Optional[Path] = None
        self._modified = False

        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setStyleSheet("""
            QPlainTextEdit {
                background: #f8f9fa;
                color: #212529;
                border: 1px solid #e9ecef;
                border-radius: 10px;
                padding: 12px;
                font-size: 14px;
                line-height: 1.6;
            }
            QPlainTextEdit:focus {
                border-color: #74c0fc;
                background: #ffffff;
            }
        """)
        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self):
        if not self._modified:
            self._modified = True
            self.content_changed.emit()

    def load_file(self, path: Path):
        self.file_path = Path(path)
        try:
            text = self.file_path.read_text(encoding="utf-8")
            self.setPlainText(text)
            self._modified = False
        except Exception as e:
            self.setPlainText(f"无法读取文件: {e}")

    def save_file(self) -> bool:
        if self.file_path is None:
            return False
        try:
            self.file_path.write_text(self.toPlainText(), encoding="utf-8")
            self._modified = False
            return True
        except Exception as e:
            from ..utils.logger import get_logger
            get_logger(__name__).error(f"保存失败: {e}")
            return False

    def is_modified(self) -> bool:
        return self._modified

    def insert_text(self, text: str):
        cursor = self.textCursor()
        cursor.insertText(text)
        self.setTextCursor(cursor)
