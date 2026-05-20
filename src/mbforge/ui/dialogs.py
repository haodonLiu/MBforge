"""通用对话框."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QGroupBox,
    QCheckBox,
)

from ..utils.config import AppConfig, ModelConfig, EmbedConfig, RerankConfig, VLMConfig


class NewProjectDialog(QDialog):
    """创建新项目对话框."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("新建项目")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("项目名称")
        form.addRow("名称:", self.name_edit)

        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择项目文件夹")
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.browse_btn)
        form.addRow("路径:", path_layout)

        self.desc_edit = QTextEdit()
        self.desc_edit.setMaximumHeight(80)
        self.desc_edit.setPlaceholderText("项目描述（可选）")
        form.addRow("描述:", self.desc_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择项目文件夹")
        if path:
            self.path_edit.setText(path)
            if not self.name_edit.text():
                self.name_edit.setText(Path(path).name)

    def get_data(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "path": self.path_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip(),
        }


class SettingsDialog(QDialog):
    """全局设置对话框."""

    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("设置")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        # LLM 标签
        self.llm_tab = QWidget()
        self._setup_llm_tab()
        self.tabs.addTab(self.llm_tab, "LLM")

        # Embedding 标签
        self.embed_tab = QWidget()
        self._setup_embed_tab()
        self.tabs.addTab(self.embed_tab, "Embedding")

        # Rerank 标签
        self.rerank_tab = QWidget()
        self._setup_rerank_tab()
        self.tabs.addTab(self.rerank_tab, "Rerank")

        # VLM 标签
        self.vlm_tab = QWidget()
        self._setup_vlm_tab()
        self.tabs.addTab(self.vlm_tab, "VLM")

        layout.addWidget(self.tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _setup_llm_tab(self):
        layout = QFormLayout(self.llm_tab)
        self.llm_provider = QComboBox()
        self.llm_provider.addItems(["openai_compatible", "local", "ollama"])
        layout.addRow("Provider:", self.llm_provider)

        self.llm_base_url = QLineEdit()
        layout.addRow("Base URL:", self.llm_base_url)

        self.llm_api_key = QLineEdit()
        self.llm_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("API Key:", self.llm_api_key)

        self.llm_model = QLineEdit()
        layout.addRow("Model:", self.llm_model)

        self.llm_max_tokens = QSpinBox()
        self.llm_max_tokens.setRange(256, 32768)
        self.llm_max_tokens.setSingleStep(256)
        layout.addRow("Max Tokens:", self.llm_max_tokens)

        self.llm_temperature = QDoubleSpinBox()
        self.llm_temperature.setRange(0.0, 2.0)
        self.llm_temperature.setSingleStep(0.1)
        layout.addRow("Temperature:", self.llm_temperature)

    def _setup_embed_tab(self):
        layout = QFormLayout(self.embed_tab)
        self.embed_provider = QComboBox()
        self.embed_provider.addItems(["sentence_transformers", "openai", "api"])
        layout.addRow("Provider:", self.embed_provider)

        self.embed_model = QLineEdit()
        layout.addRow("Model:", self.embed_model)

        self.embed_device = QComboBox()
        self.embed_device.addItems(["cpu", "cuda", "mps"])
        layout.addRow("Device:", self.embed_device)

    def _setup_rerank_tab(self):
        layout = QFormLayout(self.rerank_tab)
        self.rerank_model = QLineEdit()
        layout.addRow("Model:", self.rerank_model)

        self.rerank_device = QComboBox()
        self.rerank_device.addItems(["cpu", "cuda", "mps"])
        layout.addRow("Device:", self.rerank_device)

    def _setup_vlm_tab(self):
        layout = QFormLayout(self.vlm_tab)
        self.vlm_base_url = QLineEdit()
        layout.addRow("Base URL:", self.vlm_base_url)

        self.vlm_api_key = QLineEdit()
        self.vlm_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("API Key:", self.vlm_api_key)

        self.vlm_model = QLineEdit()
        layout.addRow("Model:", self.vlm_model)

    def _load_config(self):
        c = self.config
        self.llm_provider.setCurrentText(c.llm.provider)
        self.llm_base_url.setText(c.llm.base_url)
        self.llm_api_key.setText(c.llm.api_key)
        self.llm_model.setText(c.llm.model_name)
        self.llm_max_tokens.setValue(c.llm.max_tokens)
        self.llm_temperature.setValue(c.llm.temperature)

        self.embed_provider.setCurrentText(c.embed.provider)
        self.embed_model.setText(c.embed.model_name)
        self.embed_device.setCurrentText(c.embed.device)

        self.rerank_model.setText(c.rerank.model_name)
        self.rerank_device.setCurrentText(c.rerank.device)

        self.vlm_base_url.setText(c.vlm.base_url)
        self.vlm_api_key.setText(c.vlm.api_key)
        self.vlm_model.setText(c.vlm.model_name)

    def _save_and_accept(self):
        self.config.llm = ModelConfig(
            provider=self.llm_provider.currentText(),
            base_url=self.llm_base_url.text(),
            api_key=self.llm_api_key.text(),
            model_name=self.llm_model.text(),
            max_tokens=self.llm_max_tokens.value(),
            temperature=self.llm_temperature.value(),
        )
        self.config.embed = EmbedConfig(
            provider=self.embed_provider.currentText(),
            model_name=self.embed_model.text(),
            device=self.embed_device.currentText(),
        )
        self.config.rerank = RerankConfig(
            model_name=self.rerank_model.text(),
            device=self.rerank_device.currentText(),
        )
        self.config.vlm = VLMConfig(
            base_url=self.vlm_base_url.text(),
            api_key=self.vlm_api_key.text(),
            model_name=self.vlm_model.text(),
        )
        from ..utils.config import save_global_config
        save_global_config(self.config)
        self.accept()


class MoleculeInfoDialog(QDialog):
    """分子详细信息对话框."""

    def __init__(self, record, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.record = record
        self.setWindowTitle(f"分子详情 - {record.name or record.smiles[:30]}")
        self.setMinimumWidth(450)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        text = f"""
<b>SMILES:</b> <code>{self.record.smiles}</code><br>
<b>名称:</b> {self.record.name or '-'}<br>
<b>活性:</b> {self.record.activity or '-'} {self.record.activity_type} {self.record.units}<br>
<b>来源:</b> {self.record.source_doc or '-'}<br>
<b>性质:</b> {self.record.properties}<br>
<b>标签:</b> {', '.join(self.record.tags) or '-'}<br>
<b>备注:</b> {self.record.notes or '-'}<br>
        """
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
