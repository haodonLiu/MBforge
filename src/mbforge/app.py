"""MBForge GUI 应用入口."""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

# 优先加载项目根目录的 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# .env 中的 HF_HOME / MODELSCOPE_CACHE / TORCH_HOME / OLLAMA_MODELS
# 会在 load_dotenv() 后注入 os.environ，
# sentence-transformers / modelscope / torch 内部会读取这些变量确定缓存路径，
# 因此库首次 import 前就已生效，无需额外代码。

from .ui.main_window import MainWindow
from .utils.logger import setup_logging


def run_app(argv: list[str] | None = None) -> int:
    """启动 MBForge GUI."""
    if argv is None:
        argv = sys.argv

    # 启用高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 初始化日志
    setup_logging()

    app = QApplication(argv)
    app.setApplicationName("MBForge")
    app.setApplicationVersion("0.2.0")
    app.setOrganizationName("MBForge")

    # 全局字体
    font = app.font()
    # Windows 上默认字体可能使用 pixel size，pointSize() 返回 -1，
    # 直接使用 setPointSize 会触发 Qt 警告，改用 setPointSizeF
    font.setPointSizeF(10.0)
    app.setFont(font)

    window = MainWindow()
    window.show()

    return app.exec()
