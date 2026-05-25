"""通用对话框."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..utils.config import AppConfig, EmbedConfig, ModelConfig, RerankConfig, VLMConfig
from .components import InfoRow
from .theme import ThemeManager, create_input


class NewProjectDialog(QDialog):
    """创建新项目对话框."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("新建项目")
        self.setMinimumWidth(500)
        ThemeManager.apply_dialog(self)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = create_input(placeholder="项目名称")
        form.addRow("名称:", self.name_edit)

        path_layout = QHBoxLayout()
        self.path_edit = create_input(placeholder="选择项目文件夹")
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

    def __init__(
        self,
        config: AppConfig,
        project_root: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.config = config
        self.project_root = project_root
        self.setWindowTitle("设置")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        ThemeManager.apply_dialog(self)
        self._setup_ui()
        self._load_config()
        self._load_theme_config()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("")  # 继承全局 tab 样式

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

        # 主题 标签
        self.theme_tab = QWidget()
        self._setup_theme_tab()
        self.tabs.addTab(self.theme_tab, "主题")

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
        self.llm_provider.addItems(
            ["openai_compatible", "anthropic", "local", "ollama"]
        )
        layout.addRow("Provider:", self.llm_provider)

        self.llm_base_url = create_input(placeholder="https://...")
        layout.addRow("Base URL:", self.llm_base_url)

        self.llm_api_key = create_input(placeholder="sk-...", password=True)
        layout.addRow("API Key:", self.llm_api_key)

        self.llm_model = create_input(placeholder="模型名称")
        layout.addRow("Model:", self.llm_model)

        self.llm_max_tokens = QSpinBox()
        self.llm_max_tokens.setRange(256, 9000000)
        self.llm_max_tokens.setSingleStep(1024)
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

        self.embed_model = create_input(placeholder="模型名称或路径")
        layout.addRow("Model:", self.embed_model)

        self.embed_device = QComboBox()
        self.embed_device.addItems(["cpu", "cuda", "mps"])
        layout.addRow("Device:", self.embed_device)

    def _setup_rerank_tab(self):
        layout = QFormLayout(self.rerank_tab)
        self.rerank_model = create_input(placeholder="模型名称或路径")
        layout.addRow("Model:", self.rerank_model)

        self.rerank_device = QComboBox()
        self.rerank_device.addItems(["cpu", "cuda", "mps"])
        layout.addRow("Device:", self.rerank_device)

    def _setup_vlm_tab(self):
        layout = QFormLayout(self.vlm_tab)
        self.vlm_base_url = create_input(placeholder="https://...")
        layout.addRow("Base URL:", self.vlm_base_url)

        self.vlm_api_key = create_input(placeholder="sk-...", password=True)
        layout.addRow("API Key:", self.vlm_api_key)

        self.vlm_model = create_input(placeholder="模型名称")
        layout.addRow("Model:", self.vlm_model)

    def _setup_theme_tab(self):
        layout = QVBoxLayout(self.theme_tab)
        form = QFormLayout()
        self.theme_group = QButtonGroup()
        self.theme_system = QRadioButton("跟随系统")
        self.theme_light = QRadioButton("浅色")
        self.theme_dark = QRadioButton("深色")
        self.theme_group.addButton(self.theme_system, 0)
        self.theme_group.addButton(self.theme_light, 1)
        self.theme_group.addButton(self.theme_dark, 2)
        form.addRow("主题:", self.theme_system)
        form.addRow("", self.theme_light)
        form.addRow("", self.theme_dark)
        layout.addLayout(form)
        layout.addStretch()

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

    def _load_theme_config(self):
        theme_mode = "system"
        if self.project_root:
            from ..core.settings import ProjectSettings

            ps = ProjectSettings.load(self.project_root)
            theme_mode = ps.theme_override
        # Map mode to button id
        mode_map = {"system": 0, "light": 1, "dark": 2}
        btn_id = mode_map.get(theme_mode, 0)
        self.theme_group.button(btn_id).setChecked(True)

    def _save_and_accept(self):
        self.config.llm = ModelConfig(
            provider=self.llm_provider.currentText().strip().lower(),
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
        # Save theme override to project settings
        mode_map = {0: "system", 1: "light", 2: "dark"}
        selected_id = self.theme_group.checkedId()
        selected_mode = mode_map.get(selected_id, "system")
        if self.project_root:
            from ..core.settings import ProjectSettings

            ps = ProjectSettings.load(self.project_root)
            ps.theme_override = selected_mode
            ps.save(self.project_root)
        ThemeManager.instance().set_mode(selected_mode)
        from ..utils.config import save_global_config

        save_global_config(self.config)
        self.accept()


class MoleculeInfoDialog(QDialog):
    """分子详细信息对话框（含结构图片预览）."""

    def __init__(self, record, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.record = record
        self.setWindowTitle(f"分子详情 - {record.name or record.smiles[:30]}")
        self.setMinimumWidth(500)
        ThemeManager.apply_dialog(self)
        self._setup_ui()

    def _setup_ui(self):
        import html

        from .mol_renderer import MoleculeImageWidget

        layout = QVBoxLayout(self)
        rec = self.record

        # 分子结构图片
        img_widget = MoleculeImageWidget(rec.smiles, size=(400, 300))
        layout.addWidget(img_widget)

        # 详细信息
        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setSpacing(4)

        fields = [
            ("SMILES", html.escape(rec.smiles)),
            ("名称", html.escape(rec.name or "-")),
            ("活性", f"{rec.activity} {rec.units}" if rec.activity is not None else "-"),
            ("活性类型", rec.activity_type or "-"),
            ("来源", html.escape(rec.source_doc or "-")),
            ("性质", html.escape(str(rec.properties))),
            ("标签", ", ".join(rec.tags) or "-"),
            ("备注", html.escape(rec.notes or "-")),
        ]
        for key, value in fields:
            info_layout.addWidget(InfoRow(key, value))

        layout.addWidget(info_container)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
