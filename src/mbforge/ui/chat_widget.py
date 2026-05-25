"""LLM 对话框组件（集成 Agent 框架，支持 Markdown 渲染）."""

from __future__ import annotations

from typing import TYPE_CHECKING

import markdown

if TYPE_CHECKING:
    from ..agent.agent import ProjectAgent
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..utils.logger import get_logger
from .theme import ThemeManager, create_button, create_input, create_label

logger = get_logger(__name__)


class ChatMessage(QWidget):
    """单条消息气泡，支持 Markdown 渲染."""

    def __init__(self, role: str, content: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.role = role
        self._renderer = ChatMessageRenderer()
        self._setup_ui()
        self.set_content(content)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        is_user = self.role == "user"
        header_text = "用户" if is_user else "AI"

        self.header = QLabel(f"<b>{header_text}</b>")
        p = ThemeManager.instance().palette()
        header_color = p["text_secondary"] if is_user else p["brand_primary"]
        self.header.setStyleSheet(f"color: {header_color}; font-size: 13px;")
        layout.addWidget(self.header)

        # 消息内容容器（带背景色圆角）
        self.body_container = QFrame()
        bg_color = p["bg_hover"] if is_user else p["bg_card"]
        self.body_container.setStyleSheet(f"""
            QFrame {{
                background: {bg_color};
                border: 1px solid {p['border']};
                border-radius: 12px;
            }}
        """)
        body_layout = QVBoxLayout(self.body_container)
        body_layout.setContentsMargins(12, 10, 12, 10)
        body_layout.setSpacing(0)

        # 使用 WebEngine 渲染 Markdown
        self.body = QWebEngineView()
        self.body.setMinimumHeight(40)
        self.body.setMaximumHeight(600)
        self.body.setStyleSheet("background: transparent; border: none;")
        settings = self.body.settings()
        if settings is not None:
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        body_layout.addWidget(self.body)

        layout.addWidget(self.body_container)

    def set_content(self, content: str) -> None:
        """设置消息内容（Markdown 格式）."""
        html = self._renderer.render(content)
        self.body.setHtml(html)
        # 自适应高度：通过 JS 获取内容高度
        self.body.page().runJavaScript(
            "document.body.scrollHeight",
            lambda h: self._adjust_height(h),
        )

    def append_content(self, content: str) -> None:
        """追加内容（用于流式输出）."""
        html = self._renderer.render_stream(content)
        self.body.setHtml(html)
        self.body.page().runJavaScript(
            "document.body.scrollHeight",
            lambda h: self._adjust_height(h),
        )

    def _adjust_height(self, content_height: int) -> None:
        """根据内容高度调整 WebView 高度."""
        if content_height and content_height > 0:
            new_height = min(content_height + 24, 600)
            self.body.setMinimumHeight(new_height)
            self.body.setMaximumHeight(new_height)


# ---------- Markdown 渲染器 ----------

class ChatMessageRenderer:
    """聊天消息 Markdown → HTML 渲染器."""

    def __init__(self):
        self._md = markdown.Markdown(
            extensions=[
                "tables",
                "fenced_code",
                "toc",
                "nl2br",
            ]
        )

    def render(self, text: str) -> str:
        """将 Markdown 文本渲染为完整 HTML."""
        self._md.reset()
        body_html = self._md.convert(text)
        return self._wrap_html(body_html)

    def render_stream(self, text: str) -> str:
        """流式渲染：未闭合的代码块需要特殊处理."""
        # 简单处理：如果文本以 ``` 结尾但没有闭合，补一个临时代码块
        processed = text
        code_fence_count = processed.count("```")
        if code_fence_count % 2 == 1:
            processed = processed + "\n```"
        self._md.reset()
        body_html = self._md.convert(processed)
        return self._wrap_html(body_html)

    def _wrap_html(self, body: str) -> str:
        p = ThemeManager.instance().palette()
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    :root {{
        --bg-card: {p['bg_card']};
        --bg-base: {p['bg_base']};
        --bg-hover: {p['bg_hover']};
        --text-primary: {p['text_primary']};
        --text-secondary: {p['text_secondary']};
        --border: {p['border']};
        --brand: {p['brand_primary']};
        --code-bg: {p['bg_hover']};
    }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        font-size: 14px;
        line-height: 1.7;
        color: var(--text-primary);
        background: transparent;
        padding: 0;
        margin: 0;
        word-wrap: break-word;
    }}
    h1, h2, h3, h4 {{ margin-top: 16px; margin-bottom: 10px; font-weight: 600; }}
    h1 {{ font-size: 20px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
    h2 {{ font-size: 17px; border-bottom: 1px solid var(--border); padding-bottom: 5px; }}
    h3 {{ font-size: 15px; }}
    code {{ background: var(--code-bg); padding: 2px 6px; border-radius: 4px; font-family: "Consolas", "Monaco", monospace; font-size: 0.9em; color: {p['accent_coral']}; }}
    pre {{ background: var(--bg-base); padding: 12px; border-radius: 8px; overflow-x: auto; border: 1px solid var(--border); margin: 8px 0; }}
    pre code {{ background: none; padding: 0; color: var(--text-primary); }}
    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); font-size: 13px; }}
    th, td {{ border: 1px solid var(--border); padding: 8px 10px; text-align: left; }}
    th {{ background: var(--bg-base); font-weight: 600; }}
    blockquote {{ border-left: 3px solid var(--brand); margin: 8px 0; padding: 8px 14px; background: var(--bg-base); border-radius: 0 8px 8px 0; }}
    a {{ color: var(--brand); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    ul, ol {{ padding-left: 20px; margin: 6px 0; }}
    p {{ margin: 6px 0; }}
</style>
</head>
<body>{body}</body>
</html>"""


# ---------- 流式输出工作线程 ----------

class StreamWorker(QThread):
    """LLM 流式输出工作线程."""

    chunk_received = pyqtSignal(str)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, agent: ProjectAgent, user_input: str):
        super().__init__()
        self.agent = agent
        self.user_input = user_input
        self._stopped = False

    def run(self):
        try:
            for text in self.agent.chat_stream(self.user_input):
                if self._stopped:
                    break
                self.chunk_received.emit(text)
            self.finished_signal.emit()
        except Exception as e:
            logger.exception("Stream worker error")
            self.error_signal.emit(str(e))

    def stop(self):
        self._stopped = True


# ---------- 聊天面板 ----------

class ChatWidget(QWidget):
    """LLM 对话面板（Agent 集成版，支持 Markdown 渲染）."""

    # 最大保留消息数，超出时归档旧消息
    MAX_MESSAGES = 50

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.agent: ProjectAgent | None = None
        self._current_reply_widget: ChatMessage | None = None
        self._worker: StreamWorker | None = None
        self._pending_text = ""
        self._flush_timer: QTimer | None = None
        self._setup_ui()
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        self.title_label = create_label("AI 助手", level="header")
        toolbar.addWidget(self.title_label)
        toolbar.addStretch()

        self.clear_btn = create_button("清空", style="default")
        self.clear_btn.clicked.connect(self.clear_chat)
        toolbar.addWidget(self.clear_btn)
        layout.addLayout(toolbar)

        # 消息区域
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border: none; background: #ffffff;")
        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.messages_layout.setSpacing(8)
        self.messages_layout.addStretch()
        self.scroll.setWidget(self.messages_container)
        layout.addWidget(self.scroll, 1)

        # 输入区域
        input_frame = QFrame()
        p = ThemeManager.instance().palette()
        input_frame.setStyleSheet(f"background: {p['bg_base']}; border-top: 1px solid {p['border']};")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 8, 8, 8)

        self.input_box = create_input(placeholder="输入问题，按 Enter 发送...")
        self.input_box.returnPressed.connect(self._send_message)
        input_layout.addWidget(self.input_box)

        self.send_btn = create_button("发送", style="primary")
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)

        self.stop_btn = create_button("停止", style="danger")
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self._stop_generation)
        input_layout.addWidget(self.stop_btn)

        layout.addWidget(input_frame)

        # 批量刷新定时器（减少 repaint 频率）
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(80)
        self._flush_timer.timeout.connect(self._flush_pending_text)

    def _on_theme_changed(self, mode: str):
        """Refresh styles when theme changes."""
        # Force re-render of all messages by clearing and re-adding
        self.clear_chat()

    def set_agent(self, agent: ProjectAgent):
        """设置 Agent 实例."""
        logger.info(f"ChatWidget.set_agent | agent_type={type(agent).__name__}")
        self.agent = agent

    def set_system_prompt(self, prompt: str):
        """修改系统提示（会清空历史）."""
        logger.info(f"ChatWidget.set_system_prompt | prompt_len={len(prompt)}")
        if self.agent is not None:
            self.agent.context.set_system_prompt(prompt)

    def add_context(self, context: str):
        """添加知识库检索结果作为上下文."""
        logger.debug(f"ChatWidget.add_context | context_len={len(context)}")
        if self.agent is None or not context:
            return
        self.agent.context.update_project_context(context)

    def _send_message(self):
        text = self.input_box.text().strip()
        if not text:
            return
        if self.agent is None:
            logger.warning("ChatWidget._send_message | Agent 未初始化")
            self._add_message("assistant", "Agent 未初始化，请先打开项目。")
            return
        logger.info(f"ChatWidget._send_message | text_len={len(text)}")

        self.input_box.clear()
        self._add_message("user", text)

        # 创建回复气泡
        self._current_reply_widget = ChatMessage("assistant", "")
        self.messages_layout.insertWidget(
            self.messages_layout.count() - 1, self._current_reply_widget
        )
        self._scroll_to_bottom()

        self.send_btn.setVisible(False)
        self.stop_btn.setVisible(True)

        # 确保旧 worker 已停止
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(2000)
            self._worker = None

        self._pending_text = ""
        self._flush_timer.start()

        self._worker = StreamWorker(self.agent, text)
        self._worker.chunk_received.connect(self._on_chunk)
        self._worker.finished_signal.connect(self._on_stream_finished)
        self._worker.error_signal.connect(self._on_stream_error)
        self._worker.start()
        logger.debug("StreamWorker 已启动")

    def _on_chunk(self, text: str):
        """接收流式块，累积到 pending_text 中，由定时器批量刷新."""
        self._pending_text += text

    def _flush_pending_text(self):
        """批量刷新 UI，减少 repaint 频率."""
        if self._current_reply_widget and self._pending_text:
            self._current_reply_widget.append_content(self._pending_text)
            self._scroll_to_bottom()

    def _on_stream_finished(self):
        logger.info(f"ChatWidget._on_stream_finished | reply_len={len(self._pending_text)}")
        self._flush_timer.stop()
        # 最后一次刷新，确保所有内容都已显示
        if self._current_reply_widget and self._pending_text:
            self._current_reply_widget.set_content(self._pending_text)
        self._current_reply_widget = None
        self._pending_text = ""
        self.send_btn.setVisible(True)
        self.stop_btn.setVisible(False)
        self._worker = None

    def _on_stream_error(self, error: str):
        logger.error(f"ChatWidget._on_stream_error | {error}")
        self._flush_timer.stop()
        if self._current_reply_widget:
            self._current_reply_widget.set_content(f"[X] **错误**\n\n{error}")
        self._on_stream_finished()

    def _stop_generation(self):
        logger.info("ChatWidget._stop_generation | 用户停止生成")
        if self._worker:
            self._worker.stop()
            self._worker.wait(2000)
        self._flush_timer.stop()
        self.send_btn.setVisible(True)
        self.stop_btn.setVisible(False)

    def _add_message(self, role: str, content: str):
        logger.debug(f"ChatWidget._add_message | role={role} | content_len={len(content)}")
        msg = ChatMessage(role, content)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, msg)
        self._prune_old_messages()
        self._scroll_to_bottom()

    def _prune_old_messages(self):
        """当消息数超过上限时，移除最旧的消息以释放内存."""
        # 计算当前消息 widget 数量（排除最后的 stretch）
        count = self.messages_layout.count() - 1
        while count > self.MAX_MESSAGES:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            count -= 1

    def _scroll_to_bottom(self):
        vsb = self.scroll.verticalScrollBar()
        if vsb:
            vsb.setValue(vsb.maximum())

    def clear_chat(self):
        logger.info("ChatWidget.clear_chat")
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if self.agent is not None:
            self.agent.clear()
