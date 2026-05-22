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

# .env 中的 HF_HOME / MODELSCOPE_CACHE / TORCH_HOME / OLLAMA_MODELS
# 会在 load_dotenv() 后注入 os.environ，
# sentence-transformers / modelscope / torch 内部会读取这些变量确定缓存路径，
# 因此库首次 import 前就已生效，无需额外代码。

from .ui.main_window import MainWindow
from .utils.logger import setup_logging


def run_app(argv: list[str] | None = None) -> int:
    """启动 MBForge GUI."""
    if argv is None or not argv:
        argv = sys.argv
    # 确保至少有一个元素（程序名），QWebEngine/Chromium 子进程需要它
    if not argv:
        argv = ["mbforge"]
    # Chromium 子进程通过 argv[0] 定位主程序。如果 argv[0] 以 '-' 开头
    # （如 python -m mbforge 时 argv[0]='-m'），会导致子进程初始化失败。
    # 替换为 Python 解释器路径确保子进程能正确启动。
    if argv[0].startswith("-"):
        argv = [sys.executable, *argv]

    # 启用高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 初始化日志
    setup_logging()

    app = QApplication(argv)
    app.setApplicationName("MBForge")
    from .utils.constants import APP_VERSION

    app.setApplicationVersion(APP_VERSION)
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
