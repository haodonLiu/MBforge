"""MBForge 主窗口."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..core.document import DocumentProcessor
from ..core.knowledge_base import KnowledgeBase
from ..core.mol_database import MoleculeDatabase
from ..core.project import Project
from ..models import create_embedder_from_config, create_llm_from_config, create_reranker_from_config
from ..parsers.pdf_parser import PDFParserPipeline
from ..utils.config import load_global_config
from .chat_widget import ChatWidget
from .dialogs import NewProjectDialog, SettingsDialog
from .editor import MarkdownEditor
from .file_tree import FileTreeWidget
from .mol_panel import MoleculePanel
from .pdf_viewer import PDFViewer
from .preview import MarkdownPreview


class IndexWorker(QThread):
    """后台索引工作线程."""

    progress = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, pipeline: PDFParserPipeline, entries):
        super().__init__()
        self.pipeline = pipeline
        self.entries = entries

    def run(self):
        for entry in self.entries:
            if entry.doc_type == "pdf":
                self.progress.emit(f"索引: {entry.path.name}")
                try:
                    self.pipeline.parse(
                        entry.path,
                        doc_id=entry.doc_id,
                        extract_molecules=True,
                        summarize=True,
                        index_kb=True,
                    )
                    entry.indexed = True
                except Exception as e:
                    self.progress.emit(f"失败: {entry.path.name} - {e}")
        self.progress.emit("索引完成")
        self.finished_signal.emit()


class MainWindow(QMainWindow):
    """MBForge 主窗口."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MBForge - Molecular Knowledge Base")
        self.setMinimumSize(1400, 900)

        self.project: Optional[Project] = None
        self.kb: Optional[KnowledgeBase] = None
        self.mol_db: Optional[MoleculeDatabase] = None
        self.llm = None
        self.embedder = None
        self.reranker = None
        self.vlm = None
        self.pdf_pipeline: Optional[PDFParserPipeline] = None

        self._setup_models()
        self._setup_ui()
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_statusbar()
        self._apply_theme()

    # ---- 初始化 ----

    def _setup_models(self):
        config = load_global_config()
        try:
            self.embedder = create_embedder_from_config(config.embed)
        except Exception as e:
            print(f"Embedder init failed: {e}")
        try:
            self.llm = create_llm_from_config(config.llm)
        except Exception as e:
            print(f"LLM init failed: {e}")
        try:
            self.reranker = create_reranker_from_config(config.rerank)
        except Exception as e:
            print(f"Reranker init failed: {e}")

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：文件树
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.project_label = QLabel("未打开项目")
        self.project_label.setStyleSheet("padding: 8px; background: #252526; color: #d4d4d4; font-weight: bold;")
        left_layout.addWidget(self.project_label)

        self.file_tree = FileTreeWidget()
        self.file_tree.file_opened.connect(self._open_file)
        self.file_tree.file_selected.connect(self._index_single_file)
        left_layout.addWidget(self.file_tree)

        left_btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton("🔄 扫描")
        self.scan_btn.setStyleSheet("background: #3c3c3c; color: #d4d4d4; border: none; padding: 4px;")
        self.scan_btn.clicked.connect(self._scan_project)
        self.index_btn = QPushButton("📚 索引")
        self.index_btn.setStyleSheet("background: #3c3c3c; color: #d4d4d4; border: none; padding: 4px;")
        self.index_btn.clicked.connect(self._index_project)
        left_btn_layout.addWidget(self.scan_btn)
        left_btn_layout.addWidget(self.index_btn)
        left_layout.addLayout(left_btn_layout)

        self.splitter.addWidget(self.left_panel)
        self.splitter.setStretchFactor(0, 0)

        # 中间：标签页工作区
        self.center_tabs = QTabWidget()
        self.center_tabs.setTabsClosable(True)
        self.center_tabs.tabCloseRequested.connect(self._close_tab)
        self.center_tabs.setStyleSheet("""
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background: #2d2d2d;
                color: #969696;
                padding: 6px 16px;
                border: none;
            }
            QTabBar::tab:selected {
                background: #1e1e1e;
                color: #d4d4d4;
            }
            QTabBar::tab:hover {
                background: #3c3c3c;
            }
        """)
        self.splitter.addWidget(self.center_tabs)
        self.splitter.setStretchFactor(1, 3)

        # 右侧：LLM + KB 搜索
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        # KB 搜索
        kb_frame = QWidget()
        kb_frame.setMaximumHeight(200)
        kb_layout = QVBoxLayout(kb_frame)
        kb_layout.setContentsMargins(8, 8, 8, 8)
        kb_layout.setSpacing(4)

        kb_header = QLabel("🔍 知识库检索")
        kb_header.setStyleSheet("color: #d4d4d4; font-weight: bold;")
        kb_layout.addWidget(kb_header)

        kb_input_layout = QHBoxLayout()
        self.kb_search_input = QLineEdit()
        self.kb_search_input.setPlaceholderText("输入查询...")
        self.kb_search_input.setStyleSheet("""
            QLineEdit {
                background: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        self.kb_search_input.returnPressed.connect(self._search_kb)
        kb_input_layout.addWidget(self.kb_search_input)

        self.kb_search_btn = QPushButton("搜索")
        self.kb_search_btn.setStyleSheet("background: #0e639c; color: white; border: none; padding: 4px 12px;")
        self.kb_search_btn.clicked.connect(self._search_kb)
        kb_input_layout.addWidget(self.kb_search_btn)
        kb_layout.addLayout(kb_input_layout)

        self.kb_results = QLabel("未检索")
        self.kb_results.setWordWrap(True)
        self.kb_results.setStyleSheet("color: #d4d4d4; background: #252526; padding: 6px;")
        self.kb_results.setAlignment(Qt.AlignmentFlag.AlignTop)
        kb_layout.addWidget(self.kb_results)
        right_layout.addWidget(kb_frame)

        # LLM 对话框
        self.chat_widget = ChatWidget()
        self.chat_widget.set_llm(self.llm)
        right_layout.addWidget(self.chat_widget, 1)

        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(2, 1)
        self.splitter.setSizes([240, 800, 360])

        main_layout.addWidget(self.splitter)

    def _setup_menubar(self):
        menubar = self.menuBar()
        if menubar is None:
            return

        # 文件菜单
        file_menu = menubar.addMenu("文件")
        new_project_action = QAction("新建项目", self)
        new_project_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        new_project_action.triggered.connect(self._new_project)
        file_menu.addAction(new_project_action)

        open_project_action = QAction("打开项目", self)
        open_project_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_project_action.triggered.connect(self._open_project)
        file_menu.addAction(open_project_action)

        file_menu.addSeparator()

        open_file_action = QAction("打开文件", self)
        open_file_action.setShortcut(QKeySequence("Ctrl+O"))
        open_file_action.triggered.connect(self._open_external_file)
        file_menu.addAction(open_file_action)

        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._save_current)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        exit_action = QAction("退出", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 编辑菜单
        edit_menu = menubar.addMenu("编辑")
        settings_action = QAction("设置", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._show_settings)
        edit_menu.addAction(settings_action)

        # 视图菜单
        view_menu = menubar.addMenu("视图")
        self.toggle_chat_action = QAction("显示/隐藏 AI 面板", self)
        self.toggle_chat_action.setCheckable(True)
        self.toggle_chat_action.setChecked(True)
        self.toggle_chat_action.triggered.connect(self._toggle_chat_panel)
        view_menu.addAction(self.toggle_chat_action)

        # 工具菜单
        tools_menu = menubar.addMenu("工具")
        index_action = QAction("索引当前项目", self)
        index_action.triggered.connect(self._index_project)
        tools_menu.addAction(index_action)

        mol_db_action = QAction("分子数据库", self)
        mol_db_action.triggered.connect(self._show_mol_db)
        tools_menu.addAction(mol_db_action)

    def _setup_toolbar(self):
        toolbar = QToolBar("主工具栏")
        toolbar.setStyleSheet("""
            QToolBar {
                background: #333;
                border: none;
                spacing: 4px;
                padding: 4px;
            }
            QToolButton {
                background: #3c3c3c;
                color: #d4d4d4;
                border: none;
                padding: 4px 12px;
            }
            QToolButton:hover { background: #505050; }
        """)
        self.addToolBar(toolbar)

        toolbar.addAction("📝 新建", self._new_project)
        toolbar.addAction("📂 打开", self._open_project)
        toolbar.addSeparator()
        toolbar.addAction("💾 保存", self._save_current)
        toolbar.addSeparator()
        toolbar.addAction("🔍 搜索", self._search_kb)
        toolbar.addAction("🤖 发送", lambda: self.chat_widget._send_message())

    def _setup_statusbar(self):
        self.statusbar = QStatusBar()
        self.statusbar.setStyleSheet("background: #007acc; color: white; padding: 4px;")
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("就绪")

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background: #1e1e1e;
            }
            QMenuBar {
                background: #3c3c3c;
                color: #d4d4d4;
            }
            QMenuBar::item:selected {
                background: #505050;
            }
            QMenu {
                background: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
            }
            QMenu::item:selected {
                background: #094771;
            }
            QLabel {
                color: #d4d4d4;
            }
        """)

    # ---- 项目操作 ----

    def _new_project(self):
        dlg = NewProjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        if not data["name"] or not data["path"]:
            QMessageBox.warning(self, "错误", "项目名称和路径不能为空")
            return
        try:
            project = Project.create(Path(data["path"]), name=data["name"])
            project.settings.description = data["description"]
            project.save_settings()
            self._load_project(project)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建项目失败: {e}")

    def _open_project(self):
        path = QFileDialog.getExistingDirectory(self, "打开项目文件夹")
        if not path:
            return
        project = Project.open(Path(path))
        if project is None:
            reply = QMessageBox.question(
                self,
                "新项目",
                "该目录不是 MBForge 项目，是否创建为新项目？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                project = Project.create(Path(path))
            else:
                return
        self._load_project(project)

    def _load_project(self, project: Project):
        self.project = project
        self.project_label.setText(f"📁 {project.name}")

        # 初始化知识库和分子库
        self.kb = KnowledgeBase(project.root, embedder=self.embedder)
        self.mol_db = MoleculeDatabase(project.root)

        # 更新 PDF 流水线
        self.pdf_pipeline = PDFParserPipeline(
            llm=self.llm,
            embedder=self.embedder,
            vlm=None,  # TODO
            knowledge_base=self.kb,
            mol_db=self.mol_db,
        )

        # 刷新 UI
        self.file_tree.set_project(project)
        self.statusbar.showMessage(f"已打开项目: {project.root}")

        # 添加到最近项目
        config = load_global_config()
        path_str = str(project.root)
        if path_str not in config.recent_projects:
            config.recent_projects.insert(0, path_str)
            config.recent_projects = config.recent_projects[:10]
            from ..utils.config import save_global_config
            save_global_config(config)

    def _scan_project(self):
        if self.project is None:
            return
        entries = self.project.scan_files()
        self.file_tree.refresh()
        self.statusbar.showMessage(f"扫描完成，发现 {len(entries)} 个文件")

    def _index_project(self):
        if self.project is None or self.pdf_pipeline is None:
            QMessageBox.warning(self, "提示", "请先打开项目")
            return
        entries = self.project.list_documents()
        to_index = [e for e in entries if not e.indexed]
        if not to_index:
            self.statusbar.showMessage("所有文件已索引")
            return

        self.statusbar.showMessage(f"开始索引 {len(to_index)} 个文件...")
        self.index_worker = IndexWorker(self.pdf_pipeline, to_index)
        self.index_worker.progress.connect(self.statusbar.showMessage)
        self.index_worker.finished_signal.connect(self._on_index_finished)
        self.index_worker.start()

    def _index_single_file(self, path: Path):
        if self.project is None or self.pdf_pipeline is None:
            return
        entry = self.project.get_document_by_path(path)
        if entry is None:
            entry = self.project.add_file(path)
        if entry.doc_type == "pdf":
            self.pdf_pipeline.parse(entry.path, doc_id=entry.doc_id)
            entry.indexed = True
            self.statusbar.showMessage(f"已索引: {path.name}")

    def _on_index_finished(self):
        self.statusbar.showMessage("索引完成")
        if self.project:
            self.file_tree.refresh()

    # ---- 文件操作 ----

    def _open_file(self, path: Path):
        path = Path(path)
        ext = path.suffix.lower()

        # 检查是否已打开
        for i in range(self.center_tabs.count()):
            widget = self.center_tabs.widget(i)
            if hasattr(widget, "file_path") and widget.file_path == path:
                self.center_tabs.setCurrentIndex(i)
                return

        if ext == ".pdf":
            viewer = PDFViewer()
            viewer.load_pdf(path)
            self.center_tabs.addTab(viewer, f"📄 {path.name}")
            self.center_tabs.setCurrentIndex(self.center_tabs.count() - 1)
        elif ext in {".md", ".txt", ".json", ".yaml", ".yml"}:
            self._open_text_file(path)
        else:
            QMessageBox.information(self, "提示", f"暂不支持的文件类型: {ext}")

    def _open_text_file(self, path: Path):
        # 编辑器 + 预览 分割视图
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        editor = MarkdownEditor()
        editor.load_file(path)
        preview = MarkdownPreview()
        preview.set_markdown(editor.toPlainText())
        editor.textChanged.connect(lambda: preview.set_markdown(editor.toPlainText()))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(editor)
        splitter.addWidget(preview)
        splitter.setSizes([400, 400])
        layout.addWidget(splitter)

        self.center_tabs.addTab(container, f"📝 {path.name}")
        self.center_tabs.setCurrentIndex(self.center_tabs.count() - 1)

    def _open_external_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开文件",
            "",
            "所有支持文件 (*.md *.txt *.pdf *.json *.yaml *.yml);;所有文件 (*)",
        )
        if path:
            self._open_file(Path(path))

    def _close_tab(self, index: int):
        widget = self.center_tabs.widget(index)
        if isinstance(widget, PDFViewer):
            widget.close_document()
        self.center_tabs.removeTab(index)
        if widget:
            widget.deleteLater()

    def _save_current(self):
        current = self.center_tabs.currentWidget()
        if current is None:
            return
        # 找到编辑器
        editor = None
        if hasattr(current, "findChild"):
            editor = current.findChild(MarkdownEditor)
        if editor and editor.is_modified():
            if editor.save_file():
                self.statusbar.showMessage(f"已保存: {editor.file_path}")
            else:
                self.statusbar.showMessage("保存失败")

    # ---- 知识库搜索 ----

    def _search_kb(self):
        if self.kb is None:
            QMessageBox.warning(self, "提示", "请先打开项目")
            return
        query = self.kb_search_input.text().strip()
        if not query:
            return
        self.statusbar.showMessage(f"搜索: {query}")
        try:
            results = self.kb.hybrid_search(query, top_k=5, reranker=self.reranker)
            if not results:
                self.kb_results.setText("未找到相关结果")
                return
            lines = []
            for i, r in enumerate(results, 1):
                text = r["text"].replace("\n", " ")
                lines.append(f"{i}. {text[:200]}...")
            self.kb_results.setText("\n\n".join(lines))

            # 将结果加入 LLM 上下文
            context = "\n\n".join([f"[片段{i+1}] {r['text'][:500]}" for i, r in enumerate(results)])
            self.chat_widget.add_context(context)
            self.statusbar.showMessage(f"找到 {len(results)} 条结果，已加入对话上下文")
        except Exception as e:
            self.kb_results.setText(f"搜索出错: {e}")
            self.statusbar.showMessage(f"搜索失败: {e}")

    # ---- 其他功能 ----

    def _show_settings(self):
        config = load_global_config()
        dlg = SettingsDialog(config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._setup_models()
            self.chat_widget.set_llm(self.llm)
            if self.kb:
                self.kb.embedder = self.embedder
            if self.pdf_pipeline:
                self.pdf_pipeline.llm = self.llm
                self.pdf_pipeline.embedder = self.embedder

    def _toggle_chat_panel(self):
        self.right_panel.setVisible(self.toggle_chat_action.isChecked())

    def _show_mol_db(self):
        if self.mol_db is None:
            QMessageBox.warning(self, "提示", "请先打开项目")
            return
        panel = MoleculePanel()
        panel.set_database(self.mol_db)
        self.center_tabs.addTab(panel, "🧪 分子数据库")
        self.center_tabs.setCurrentIndex(self.center_tabs.count() - 1)

    def closeEvent(self, event):
        if self.project:
            self.project.save_settings()
        event.accept()
