"""LLM 对话框组件."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFrame,
)

from ..models.base import BaseLLM, Message


class ChatMessage(QWidget):
    """单条消息气泡."""

    def __init__(self, role: str, content: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.role = role
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        header = QLabel(f"<b>{'🤖 AI' if role == 'assistant' else '🧑 用户'}</b>")
        header.setStyleSheet(
            "color: #1971c2; font-size: 13px;" if role == "assistant" else "color: #495057; font-size: 13px;"
        )
        layout.addWidget(header)

        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.body.setPlainText(content)
        self.body.setMaximumHeight(400)
        self.body.setStyleSheet("""
            QTextEdit {
                background: #f1f3f5;
                color: #212529;
                border: 1px solid #e9ecef;
                padding: 12px;
                border-radius: 12px;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        layout.addWidget(self.body)


class StreamWorker(QThread):
    """LLM 流式输出工作线程."""

    chunk_received = pyqtSignal(str)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, llm: BaseLLM, messages: list[Message]):
        super().__init__()
        self.llm = llm
        self.messages = messages
        self._stopped = False

    def run(self):
        try:
            for chunk in self.llm.chat_stream(self.messages):
                if self._stopped:
                    break
                self.chunk_received.emit(chunk.delta)
            self.finished_signal.emit()
        except Exception as e:
            self.error_signal.emit(str(e))

    def stop(self):
        self._stopped = True


class ChatWidget(QWidget):
    """LLM 对话面板."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.llm: Optional[BaseLLM] = None
        self.messages: list[Message] = [
            Message(role="system", content="你是一位专业的药物化学和分子生物学研究助手。请用中文回答。")
        ]
        self._current_reply_widget: Optional[ChatMessage] = None
        self._worker: Optional[StreamWorker] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        self.title_label = QLabel("💬 AI 助手")
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #212529;")
        toolbar.addWidget(self.title_label)
        toolbar.addStretch()

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background: #f1f3f5;
                color: #495057;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background: #e9ecef;
            }
        """)
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
        input_frame.setStyleSheet("background: #f8f9fa; border-top: 1px solid #e9ecef;")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 8, 8, 8)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("输入问题，按 Enter 发送...")
        self.input_box.setStyleSheet("""
            QLineEdit {
                background: #f8f9fa;
                color: #212529;
                border: 1px solid #e9ecef;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #74c0fc;
                background: #ffffff;
            }
        """)
        self.input_box.returnPressed.connect(self._send_message)
        input_layout.addWidget(self.input_box)

        self.send_btn = QPushButton("发送")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: #1971c2;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 8px 18px;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover { background: #1864ab; }
            QPushButton:pressed { background: #1565c0; }
        """)
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background: #fa5252;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 8px 18px;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover { background: #f03e3e; }
        """)
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self._stop_generation)
        input_layout.addWidget(self.stop_btn)

        layout.addWidget(input_frame)

        self.setStyleSheet("background: #ffffff;")

    def set_llm(self, llm: BaseLLM):
        self.llm = llm

    def set_system_prompt(self, prompt: str):
        self.messages = [Message(role="system", content=prompt)]

    def add_context(self, context: str):
        """添加知识库检索结果作为上下文.

        会清理之前的检索上下文，避免消息列表无限膨胀。
        """
        if not context:
            return
        # 清理旧的检索上下文，避免消息列表无限膨胀
        self.messages = [m for m in self.messages if not (
            m.role == "system" and m.content.startswith("[知识库检索结果]")
        )]
        self.messages.append(Message(role="system", content=f"[知识库检索结果]\n{context}"))

    def _send_message(self):
        text = self.input_box.text().strip()
        if not text:
            return
        if self.llm is None:
            self._add_message("assistant", "LLM 未配置，请在设置中配置模型。")
            return

        self.input_box.clear()
        self._add_message("user", text)
        self.messages.append(Message(role="user", content=text))

        # 限制历史消息长度，避免OOM（保留system + 最近20轮）
        MAX_HISTORY = 20
        system_msgs = [m for m in self.messages if m.role == "system"]
        non_system = [m for m in self.messages if m.role != "system"]
        if len(non_system) > MAX_HISTORY * 2:
            non_system = non_system[-MAX_HISTORY * 2:]
        self.messages = system_msgs + non_system

        # 创建回复气泡
        self._current_reply_widget = ChatMessage("assistant", "")
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, self._current_reply_widget)
        self._scroll_to_bottom()

        self.send_btn.setVisible(False)
        self.stop_btn.setVisible(True)

        # 确保旧worker已停止
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(2000)
            self._worker = None

        self._worker = StreamWorker(self.llm, list(self.messages))
        self._worker.chunk_received.connect(self._on_chunk)
        self._worker.finished_signal.connect(self._on_stream_finished)
        self._worker.error_signal.connect(self._on_stream_error)
        self._worker.start()

    def _on_chunk(self, text: str):
        if self._current_reply_widget:
            cursor = self._current_reply_widget.body.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text)
            self._current_reply_widget.body.setTextCursor(cursor)
            self._current_reply_widget.body.ensureCursorVisible()
        self._scroll_to_bottom()

    def _on_stream_finished(self):
        if self._current_reply_widget:
            full_text = self._current_reply_widget.body.toPlainText()
            self.messages.append(Message(role="assistant", content=full_text))
        self._current_reply_widget = None
        self.send_btn.setVisible(True)
        self.stop_btn.setVisible(False)
        # 只清理引用，不deleteLater，让Qt自动管理
        self._worker = None

    def _on_stream_error(self, error: str):
        if self._current_reply_widget:
            self._current_reply_widget.body.setPlainText(f"[错误] {error}")
        self._on_stream_finished()

    def _stop_generation(self):
        if self._worker:
            self._worker.stop()
            self._worker.wait(2000)
        self.send_btn.setVisible(True)
        self.stop_btn.setVisible(False)

    def _add_message(self, role: str, content: str):
        msg = ChatMessage(role, content)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, msg)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        vsb = self.scroll.verticalScrollBar()
        if vsb:
            vsb.setValue(vsb.maximum())

    def clear_chat(self):
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        system_msg = self.messages[0] if self.messages else Message(role="system", content="")
        self.messages = [system_msg]
