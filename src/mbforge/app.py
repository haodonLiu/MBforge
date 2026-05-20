"""MBForge GUI 应用入口."""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

# 优先加载项目根目录的 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .ui.main_window import MainWindow


def run_app(argv: list[str] | None = None) -> int:
    """启动 MBForge GUI."""
    if argv is None:
        argv = sys.argv

    # 启用高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(argv)
    app.setApplicationName("MBForge")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("MBForge")

    # 全局字体
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    return app.exec()
