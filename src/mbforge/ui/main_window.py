"""MBForge 主窗口."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..core.knowledge_base import KnowledgeBase
    from ..core.mol_database import MoleculeDatabase
    from ..core.project import Project
    from ..core.todo_manager import TodoManager

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..utils.config import load_global_config
from ..utils.logger import get_logger, log_exception
from .chat_widget import ChatWidget
from .components import ProgressBar
from .dialogs import NewProjectDialog, SettingsDialog, UniDockConfigDialog
from .editor import MarkdownEditor
from .file_tree import FileTreeWidget
from .preview import MarkdownPreview
from .panels.status_indicator import ServiceStatusIndicator
from .theme import (
    SearchBox,
    ThemeManager,
    create_button,
    create_label,
)
from .panels.welcome import WelcomeWidget

logger = get_logger(__name__)


class IndexWorker(QThread):
    """后台索引工作线程."""

    progress = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, pipeline: Any, entries):
        super().__init__()
        self.pipeline = pipeline
        self.entries = entries
        logger.info(f"IndexWorker 创建 | 待索引文件数={len(entries)}")

    def run(self):
        logger.info("IndexWorker 开始运行")
        total = len(self.entries)
        for idx, entry in enumerate(self.entries, 1):
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
                    logger.debug(f"索引成功 [{idx}/{total}]: {entry.path.name}")
                except Exception:
                    log_exception(logger, f"索引失败 [{idx}/{total}]: {entry.path.name}")
                    self.progress.emit(f"失败: {entry.path.name}")
        self.progress.emit("索引完成")
        logger.info("IndexWorker 运行结束")
        self.finished_signal.emit()

    def __del__(self):
        logger.debug("IndexWorker 销毁")


class ModelInitWorker(QThread):
    """后台线程：异步加载 Embedder / LLM / Reranker，避免阻塞 UI."""

    progress = pyqtSignal(str)
    finished_signal = pyqtSignal(object, object, object)  # embedder, llm, reranker
    error_signal = pyqtSignal(str)

    def run(self):
        logger.info("ModelInitWorker 开始加载模型")
        from ..models import (
            create_embedder_from_config,
            create_llm_from_config,
            create_reranker_from_config,
        )

        config = load_global_config()
        embedder = None
        llm = None
        reranker = None
        try:
            self.progress.emit("加载 Embedder...")
            embedder = create_embedder_from_config(config.embed)
            logger.info(f"Embedder 初始化成功: {type(embedder).__name__}")
        except Exception:
            log_exception(logger, "Embedder 初始化失败")
            self.error_signal.emit("Embedder 初始化失败，知识库搜索将不可用")
        try:
            self.progress.emit("加载 LLM...")
            llm = create_llm_from_config(config.llm)
            logger.info(f"LLM 初始化成功: {type(llm).__name__} (provider={config.llm.provider})")
        except Exception:
            log_exception(logger, "LLM 初始化失败")
            self.error_signal.emit("LLM 初始化失败，AI 对话将不可用")
        try:
            self.progress.emit("加载 Reranker...")
            reranker = create_reranker_from_config(config.rerank)
            logger.info(f"Reranker 初始化成功: {type(reranker).__name__}")
        except Exception:
            log_exception(logger, "Reranker 初始化失败")
            self.error_signal.emit("Reranker 初始化失败，搜索结果排序将不可用")
        self.finished_signal.emit(embedder, llm, reranker)
        logger.info("ModelInitWorker 完成")


class MainWindow(QMainWindow):
    """MBForge 主窗口."""

    def __init__(self):
        super().__init__()
        logger.info("MainWindow.__init__ 开始")
        self.setWindowTitle("MBForge - Molecular Knowledge Base")
        self.setMinimumSize(1400, 900)

        self.project: Project | None = None
        self.kb: KnowledgeBase | None = None
        self.mol_db: MoleculeDatabase | None = None
        self.todo_manager: TodoManager | None = None
        self.llm = None
        self.embedder = None
        self.reranker = None
        self.vlm = None
        self.pdf_pipeline: Any | None = None

        self._setup_ui()
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_statusbar()
        ThemeManager.apply_global(self)
        ThemeManager.instance().set_mode("system")
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

        # 状态标记
        self._models_ready = False

    def _start_model_worker(self):
        """手动启动后台模型加载."""
        if self._models_ready or (hasattr(self, "_model_worker") and self._model_worker is not None and self._model_worker.isRunning()):
            return
        self._model_worker = ModelInitWorker()
        self._model_worker.progress.connect(self.statusbar.showMessage)
        self._model_worker.finished_signal.connect(self._on_models_ready)
        self._model_worker.error_signal.connect(self._on_models_error)
        self.statusbar.showMessage("正在加载 AI 模型...")
        self._model_worker.start()

        logger.info("MainWindow.__init__ 完成")

    # ---- 初始化 ----

    def _on_models_ready(self, embedder, llm, reranker):
        """后台模型加载完成后的回调."""
        self.embedder = embedder
        self.llm = llm
        self.reranker = reranker
        self._models_ready = True
        self.statusbar.showMessage("AI 模型加载完成")

        # 如果项目已经打开，更新模型引用
        if self.kb is not None and self.embedder is not None:
            self.kb.embedder = self.embedder
        if self.pdf_pipeline is not None:
            self.pdf_pipeline.llm = self.llm
            self.pdf_pipeline.embedder = self.embedder
        if getattr(self, "agent", None) is not None:
            self.agent.llm = self.llm
            self.chat_widget.set_agent(self.agent)

        # 更新仪表盘
        if self.project is not None:
            self.service_indicator.set_status("LLM", self.llm is not None)
            self.service_indicator.set_status("Embedding", self.embedder is not None)
            self.service_indicator.set_status("知识库", True)
            self.service_indicator.set_status("分子库", True)

        # 延迟加载最近项目（如果还没有加载）
        if self.project is None:
            QTimer.singleShot(100, self._open_recent_project)

    def _on_models_error(self, msg: str):
        """后台模型加载出错."""
        logger.warning(msg)
        self.statusbar.showMessage(msg)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：文件树
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.project_label = create_label("未打开项目", level="header")
        self.project_label.setStyleSheet(
            f"padding: 10px 14px; background: {ThemeManager.instance().get_color('bg_base')}; "
            f"border-bottom: 1px solid {ThemeManager.instance().get_color('border')}; border-radius: 0;"
            f"color: {ThemeManager.instance().get_color('text_primary')};"
        )
        left_layout.addWidget(self.project_label)

        # 首页按钮
        self.home_btn = create_button("Home", style="default")
        self.home_btn.setStyleSheet(
            f"padding: 6px 12px; font-size: 12px; "
            f"background: {ThemeManager.instance().get_color('bg_hover')}; "
            f"color: {ThemeManager.instance().get_color('text_primary')}; "
            f"border: 1px solid {ThemeManager.instance().get_color('border')}; border-radius: 6px;"
        )
        self.home_btn.clicked.connect(self._go_home)
        left_layout.addWidget(self.home_btn)

        self.file_tree = FileTreeWidget()
        self.file_tree.file_opened.connect(self._open_file)
        self.file_tree.file_selected.connect(self._index_single_file)
        left_layout.addWidget(self.file_tree)

        left_btn_layout = QHBoxLayout()
        self.scan_btn = create_button("扫描")
        self.scan_btn.clicked.connect(self._scan_project)
        self.index_btn = create_button("索引")
        self.index_btn.clicked.connect(self._index_project)
        left_btn_layout.addWidget(self.scan_btn)
        left_btn_layout.addWidget(self.index_btn)
        left_layout.addLayout(left_btn_layout)

        self.splitter.addWidget(self.left_panel)
        self.splitter.setStretchFactor(0, 0)

        # 中间：标签页工作区（支持欢迎页 + 标签页切换）
        self.center_stack = QStackedWidget()

        # 欢迎页
        self.welcome_widget = WelcomeWidget()
        self.welcome_widget.open_project_requested.connect(self._load_project_from_path)
        self.welcome_widget.new_project_requested.connect(self._new_project)
        self.welcome_widget.open_settings_requested.connect(self._show_settings)
        self.welcome_widget.start_services_requested.connect(self._start_model_worker)
        self.center_stack.addWidget(self.welcome_widget)

        # 标签页工作区
        self.center_tabs = QTabWidget()
        self.center_tabs.setTabsClosable(True)
        self.center_tabs.tabCloseRequested.connect(self._close_tab)
        self.center_stack.addWidget(self.center_tabs)
        self.splitter.addWidget(self.center_stack)
        self.splitter.setStretchFactor(1, 3)

        # 右侧：LLM + KB 搜索
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        # KB 搜索（合并输入框+按钮为 SearchBox）
        kb_frame = QWidget()
        kb_frame.setMaximumHeight(200)
        kb_layout = QVBoxLayout(kb_frame)
        kb_layout.setContentsMargins(8, 8, 8, 8)
        kb_layout.setSpacing(4)

        kb_header = create_label("知识库检索", level="header")
        kb_layout.addWidget(kb_header)

        self.kb_search_input = SearchBox(placeholder="输入查询...")
        self.kb_search_input.returnPressed.connect(self._search_kb)
        kb_layout.addWidget(self.kb_search_input)

        self.kb_results = create_label("未检索", level="body")
        self.kb_results.setWordWrap(True)
        p = ThemeManager.instance().palette()
        self.kb_results.setStyleSheet(
            f"color: {p['text_secondary']}; background: {p['bg_base']}; padding: 10px; "
            f"border-radius: 10px; border: 1px solid {p['border']}; font-size: 13px;"
        )
        self.kb_results.setAlignment(Qt.AlignmentFlag.AlignTop)
        kb_layout.addWidget(self.kb_results)
        right_layout.addWidget(kb_frame)

        # LLM 对话框
        self.chat_widget = ChatWidget()
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

        import_action = QAction("导入文件", self)
        import_action.setShortcut(QKeySequence("Ctrl+I"))
        import_action.triggered.connect(self._import_files)
        file_menu.addAction(import_action)

        process_action = QAction("处理 TODO 队列", self)
        process_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        process_action.triggered.connect(self._start_process_todo)
        file_menu.addAction(process_action)

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

        kb_action = QAction("知识库管理", self)
        kb_action.triggered.connect(self._show_kb_panel)
        tools_menu.addAction(kb_action)

        todo_action = QAction("TODO 队列", self)
        todo_action.triggered.connect(self._show_todo_panel)
        tools_menu.addAction(todo_action)

        workflow_action = QAction("工作流中心", self)
        workflow_action.triggered.connect(self._show_workflow_panel)
        tools_menu.addAction(workflow_action)

        tools_menu.addSeparator()

        unidock_action = QAction("UniDock 对接", self)
        unidock_action.triggered.connect(self._show_unidock_config)
        tools_menu.addAction(unidock_action)

        tools_menu.addSeparator()

        mol_editor_action = QAction("分子编辑器", self)
        mol_editor_action.setShortcut(QKeySequence("Ctrl+E"))
        mol_editor_action.triggered.connect(self._open_mol_editor)
        tools_menu.addAction(mol_editor_action)

    def _setup_toolbar(self):
        """快速跳转工具栏：文献库 / 分子库 / 知识库 + 服务状态指示器."""
        p = ThemeManager.instance().palette()
        toolbar = QToolBar("快速跳转")
        toolbar.setMovable(True)
        toolbar.setStyleSheet(f"""
            QToolBar {{
                background: {p['bg_base']};
                border: none;
                border-bottom: 1px solid {p['border']};
                padding: 4px 8px;
                spacing: 4px;
            }}
            QToolButton {{
                background: transparent;
                color: {p['text_primary']};
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 13px;
            }}
            QToolButton:hover {{
                background: {p['bg_hover']};
                color: {p['brand_primary']};
            }}
            QWidget#service_indicator {{
                background: transparent;
            }}
        """)
        self.addToolBar(toolbar)

        toolbar.addAction("文献库", self._show_pdf_library)
        toolbar.addAction("分子库", self._show_mol_db)
        toolbar.addAction("知识库", self._show_kb_panel)
        toolbar.addSeparator()
        toolbar.addAction("TODO", self._show_todo_panel)
        toolbar.addAction("工作流", self._show_workflow_panel)
        toolbar.addAction("UniDock", self._show_unidock_config)

        # 服务状态指示器添加到工具栏最右侧
        toolbar.addSeparator()
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.service_indicator = ServiceStatusIndicator()
        self.service_indicator.setObjectName("service_indicator")
        toolbar.addWidget(self.service_indicator)

    def _trigger_chat_send(self):
        """触发 LLM 发送."""
        self.chat_widget._send_message()

    def _setup_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)

        # 资源监控标签（状态栏右侧，永久显示）
        self.cpu_label = create_label("CPU: -", level="caption")
        self.mem_label = create_label("内存: -", level="caption")
        p = ThemeManager.instance().palette()
        self.cpu_label.setStyleSheet(f"color: {p['text_secondary']}; padding: 0 4px; font-size: 12px;")
        self.mem_label.setStyleSheet(f"color: {p['text_secondary']}; padding: 0 4px; font-size: 12px;")
        self.statusbar.addPermanentWidget(self.cpu_label)
        self.statusbar.addPermanentWidget(self.mem_label)

        # 定时刷新资源监控
        self._res_timer = QTimer(self)
        self._res_timer.timeout.connect(self._refresh_resources)
        self._res_timer.setInterval(5000)
        self._res_timer.start()

        # 进度条
        self.progress_bar = ProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.hide()
        self.statusbar.addPermanentWidget(self.progress_bar)

        self.statusbar.showMessage("就绪")

        # 分子编辑器独立窗口
        self._mol_editor_dialog: Any | None = None

    def _open_mol_editor(self):
        """打开分子编辑器独立窗口."""
        from .mol_editor.dock import MoleculeEditorDialog

        if self._mol_editor_dialog is None:
            self._mol_editor_dialog = MoleculeEditorDialog(self)
            self._mol_editor_dialog.molecule_changed.connect(self._on_molecule_edited)
        self._mol_editor_dialog.show()
        self._mol_editor_dialog.raise_()
        self._mol_editor_dialog.activateWindow()

    def _go_home(self):
        """返回欢迎首页."""
        self.center_stack.setCurrentIndex(0)

    def _on_molecule_edited(self, esmiles: str):
        """分子编辑器中分子发生变化时的回调."""
        logger.debug(f"分子编辑器 E-SMILES 变化: {esmiles[:50]}...")

    def _refresh_resources(self):
        """刷新状态栏资源监控."""
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            self.cpu_label.setText(f"CPU: {cpu_percent:.1f}%")
            self.mem_label.setText(
                f"内存: {mem.used // (1024**3)}G / {mem.total // (1024**3)}G ({mem.percent:.0f}%)"
            )
        except ImportError:
            self.cpu_label.setText("CPU: psutil 未安装")
            self.mem_label.setText("内存: -")
        except Exception:
            pass

    def _on_theme_changed(self, mode: str):
        """Refresh widget styles when theme changes."""
        p = ThemeManager.instance().palette()
        self.cpu_label.setStyleSheet(f"color: {p['text_secondary']}; padding: 0 4px; font-size: 12px;")
        self.mem_label.setStyleSheet(f"color: {p['text_secondary']}; padding: 0 4px; font-size: 12px;")
        self.home_btn.setStyleSheet(
            f"padding: 6px 12px; font-size: 12px; "
            f"background: {p['bg_hover']}; color: {p['text_primary']}; "
            f"border: 1px solid {p['border']}; border-radius: 6px;"
        )
        self.project_label.setStyleSheet(
            f"padding: 10px 14px; background: {p['bg_base']}; "
            f"border-bottom: 1px solid {p['border']}; border-radius: 0;"
            f"color: {p['text_primary']};"
        )

    # ---- 项目操作 ----

    def _new_project(self):
        from ..core.project import Project

        logger.info("打开新建项目对话框")
        dlg = NewProjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            logger.debug("新建项目对话框取消")
            return
        data = dlg.get_data()
        logger.info(f"创建项目: name={data['name']}, path={data['path']}")
        if not data["name"] or not data["path"]:
            QMessageBox.warning(self, "错误", "项目名称和路径不能为空")
            return
        try:
            project = Project.create(Path(data["path"]), name=data["name"])
            project.settings.description = data["description"]
            project.save_settings()
            self._load_project(project)
            logger.info(f"项目创建成功: {project.root}")
        except Exception:
            log_exception(logger, "创建项目失败")
            QMessageBox.critical(self, "错误", "创建项目失败")

    def _open_project(self):
        from ..core.project import Project

        logger.info("打开项目文件夹对话框")
        path = QFileDialog.getExistingDirectory(self, "打开项目文件夹")
        if not path:
            logger.debug("打开项目对话框取消")
            return
        logger.info(f"尝试打开项目: {path}")
        project = Project.open(Path(path))
        if project is None:
            reply = QMessageBox.question(
                self,
                "新项目",
                "该目录不是 MBForge 项目，是否创建为新项目？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                logger.info(f"目录不存在项目，创建新项目: {path}")
                project = Project.create(Path(path))
            else:
                logger.debug("用户取消创建新项目")
                return
        self._load_project(project)

    def _open_recent_project(self):
        """启动时自动打开最近项目."""
        from ..core.project import Project

        config = load_global_config()
        while config.recent_projects:
            path_str = config.recent_projects[0]
            path = Path(path_str)
            if not path.exists():
                config.recent_projects.pop(0)
                continue
            try:
                project = Project.open(path)
                self._load_project(project)
                return
            except Exception as e:
                logger.warning(f"Failed to open recent project {path}: {e}")
                config.recent_projects.pop(0)
        # 没有有效最近项目，静默跳过

    def _load_project_from_path(self, path: Path):
        """从路径加载项目（供 WelcomeWidget 调用）."""
        from ..core.project import Project

        project = Project.open(path)
        if project:
            self._load_project(project)

    def _load_project(self, project: Project):
        from ..core.knowledge_base import KnowledgeBase
        from ..core.mol_database import MoleculeDatabase
        from ..core.todo_manager import TodoManager
        from ..core.memory import ProjectMemory
        from ..agent.agent import ProjectAgent
        from ..agent.context import LayeredContext
        from ..agent.executor import ToolExecutor

        # 释放旧项目资源
        if self.kb is not None:
            self.kb.close()
            self.kb = None
        if self.mol_db is not None:
            self.mol_db.close()
            self.mol_db = None

        self.project = project
        self.project_label.setText(f"{project.name}")

        # 切换到标签页视图
        self.center_stack.setCurrentIndex(1)

        # 初始化知识库和分子库
        self.kb = KnowledgeBase(project.root, embedder=self.embedder)
        self.mol_db = MoleculeDatabase(project.root)
        self.todo_manager = TodoManager(project.root)

        # 更新 PDF 流水线
        from ..parsers.pdf_parser import PDFParserPipeline

        self.pdf_pipeline = PDFParserPipeline(
            llm=self.llm,
            embedder=self.embedder,
            vlm=None,
            knowledge_base=self.kb,
            mol_db=self.mol_db,
        )

        # 初始化 Agent（带工具调用能力）
        tool_executor = ToolExecutor(
            project=project,
            knowledge_base=self.kb,
            mol_db=self.mol_db,
        )
        self.agent = ProjectAgent(
            llm=self.llm,
            tool_executor=tool_executor,
            project_root=project.root,
        )
        self.agent.set_project_context(project.name, str(project.root))
        self.chat_widget.set_agent(self.agent)

        # 加载项目记忆
        memory = ProjectMemory(project.root)
        saved_data = memory.load_dict()
        if saved_data is not None:
            saved_ctx = LayeredContext.from_dict(saved_data)
            self.agent.context = saved_ctx
            self.chat_widget.clear_chat()
            for msg in saved_ctx._history.messages:
                self.chat_widget._add_message(msg.role, msg.content)

        # 刷新 UI
        self.file_tree.set_project(project)
        self.statusbar.showMessage(f"已打开项目: {project.root}")

        # 更新仪表盘
        self.service_indicator.set_status("LLM", self.llm is not None)
        self.service_indicator.set_status("Embedding", self.embedder is not None)
        self.service_indicator.set_status("知识库", True)
        self.service_indicator.set_status("分子库", True)

        # 添加到最近项目
        config = load_global_config()
        path_str = str(project.root)
        if path_str not in config.recent_projects:
            config.recent_projects.insert(0, path_str)
            config.recent_projects = config.recent_projects[:10]
            from ..utils.config import save_global_config

            save_global_config(config)

        # 应用项目主题覆盖
        ps = self.project.settings
        if ps.theme_override != "system":
            ThemeManager.instance().set_mode(ps.theme_override)

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
        from .pdf_viewer import PDFViewer

        path = Path(path)
        ext = path.suffix.lower()
        logger.info(f"打开文件: {path} (类型={ext})")

        # 检查是否已打开
        for i in range(self.center_tabs.count()):
            widget = self.center_tabs.widget(i)
            if hasattr(widget, "file_path") and widget.file_path == path:
                logger.debug(f"文件已在标签页 {i} 中打开，直接切换")
                self.center_tabs.setCurrentIndex(i)
                return

        if ext == ".pdf":
            logger.debug(f"以 PDF 查看器打开: {path}")
            viewer = PDFViewer()
            viewer.load_pdf(path, project_root=self.project.root if self.project else None)
            self._add_tab(viewer, f"{path.name}")
        elif ext in {".md", ".txt", ".json", ".yaml", ".yml"}:
            self._open_text_file(path)
        else:
            logger.warning(f"不支持的文件类型: {ext}")
            QMessageBox.information(self, "提示", f"暂不支持的文件类型: {ext}")

    def _open_text_file(self, path: Path):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        editor = MarkdownEditor()
        editor.file_path = path
        editor.load_file(path)
        preview = MarkdownPreview()
        preview.set_markdown(editor.toPlainText())

        def _update_preview():
            if editor and preview:
                preview.set_markdown(editor.toPlainText())

        editor.textChanged.connect(_update_preview)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(editor)
        splitter.addWidget(preview)
        splitter.setSizes([400, 400])
        layout.addWidget(splitter)

        self.center_tabs.addTab(container, f"{path.name}")
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

    def _import_files(self):
        """导入文件到项目 raw 目录，并加入 TODO 队列."""
        if self.project is None:
            QMessageBox.warning(self, "提示", "请先打开项目")
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "导入文件到项目",
            "",
            "所有支持文件 (*.md *.txt *.pdf *.json *.yaml *.yml *.sdf *.mol *.mol2 *.pdb *.smi *.csv);;所有文件 (*)",
        )
        if not paths:
            return

        raw_dir = self.project.root / "raw"
        raw_dir.mkdir(exist_ok=True)

        imported = []
        failed = []
        for src in paths:
            src = Path(src)
            dst = raw_dir / src.name
            try:
                import shutil

                shutil.copy2(src, dst)
                self.project.add_file(dst)
                imported.append(src.name)
                self.todo_manager.add_file(src.name, f"raw/{src.name}")
            except Exception as e:
                failed.append(f"{src.name}: {e}")

        self.file_tree.set_project(self.project)

        msg = f"成功导入 {len(imported)} 个文件到 raw/"
        if failed:
            msg += f"\n失败 {len(failed)} 个:\n" + "\n".join(failed)
        self.statusbar.showMessage(msg)
        logger.info(msg)

        if imported and self._should_auto_process():
            self._start_process_todo()

    def _close_tab(self, index: int):
        from .pdf_viewer import PDFViewer

        widget = self.center_tabs.widget(index)
        if isinstance(widget, PDFViewer):
            widget.close_document()
        self.center_tabs.removeTab(index)
        if widget:
            widget.deleteLater()

    def _should_auto_process(self) -> bool:
        from ..core.settings import ProjectSettings

        settings = ProjectSettings.load(self.project.root)
        return settings.auto_process

    def _start_process_todo(self):
        """启动 TODO 处理（后台线程）."""
        from ..parsers.file_processor import process_file

        pending = self.todo_manager.get_pending()
        total = len(pending)
        if total == 0:
            self.statusbar.showMessage("没有待处理的文件")
            return

        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.progress_bar.show()

        def _on_progress(current, total_count, entry):
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{current}/{total_count}")
            self.statusbar.showMessage(
                f"处理中: {entry.filename} ({current}/{total_count})"
            )

        def _on_done():
            self.progress_bar.hide()
            self.statusbar.showMessage("所有文件处理完成")
            self.file_tree.set_project(self.project)
            self._run_archive_agent()

        self.todo_manager.process_all_async(
            file_processor=lambda e, s, o: process_file(
                e,
                s,
                o,
                llm=self.llm,
                embedder=self.embedder,
                knowledge_base=self.kb,
                mol_db=self.mol_db,
            ),
            on_progress=_on_progress,
            on_done=_on_done,
        )
        self.statusbar.showMessage(f"开始处理 {total} 个文件...")

    def _run_archive_agent(self):
        """启动归档 Agent 后台整理已处理文件."""
        from ..agent.archive_agent import ArchiveAgent

        agent = ArchiveAgent(
            llm=self.llm,
            knowledge_base=self.kb,
            mol_db=self.mol_db,
            project_root=self.project.root,
        )
        agent.run_async(on_done=lambda: self.statusbar.showMessage("归档整理完成"))

    def _save_current(self):
        current = self.center_tabs.currentWidget()
        if current is None:
            return
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
        logger.info(f"知识库搜索: query='{query}'")
        self.statusbar.showMessage(f"搜索: {query}")
        try:
            results = self.kb.hybrid_search(query, top_k=5, reranker=self.reranker)
            logger.info(f"知识库搜索完成: 找到 {len(results)} 条结果")
            if not results:
                self.kb_results.setText("未找到相关结果")
                return
            lines = []
            for i, r in enumerate(results, 1):
                text = r["text"].replace("\n", " ")
                lines.append(f"{i}. {text[:200]}...")
            self.kb_results.setText("\n\n".join(lines))

            context = "\n\n".join(
                [f"[片段{i + 1}] {r['text'][:500]}" for i, r in enumerate(results)]
            )
            self.chat_widget.add_context(context)
            self.statusbar.showMessage(f"找到 {len(results)} 条结果，已加入对话上下文")
        except Exception:
            log_exception(logger, f"知识库搜索失败: query='{query}'")
            self.kb_results.setText("搜索出错")
            self.statusbar.showMessage("搜索失败")

    # ---- 其他功能 ----

    def _show_settings(self):
        config = load_global_config()
        dlg = SettingsDialog(
            config, self.project.root if self.project else None, self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.statusbar.showMessage("设置已更新，正在重新加载模型...")
            self._models_ready = False
            # 如果已有模型加载线程在运行，先停止并等待
            if hasattr(self, "_model_worker") and self._model_worker is not None and self._model_worker.isRunning():
                self._model_worker.quit()
                self._model_worker.wait(3000)
            self._model_worker = ModelInitWorker()
            self._model_worker.progress.connect(self.statusbar.showMessage)
            self._model_worker.finished_signal.connect(self._on_models_ready)
            self._model_worker.error_signal.connect(self._on_models_error)
            self._model_worker.start()

    def _toggle_chat_panel(self):
        self.right_panel.setVisible(self.toggle_chat_action.isChecked())

    def _show_mol_db(self):
        from .panels.mol import MoleculePanel

        if self.mol_db is None:
            QMessageBox.warning(self, "提示", "请先打开项目")
            return
        panel = MoleculePanel()
        panel.set_database(self.mol_db)
        self._add_tab(panel, "分子数据库")

    def _show_kb_panel(self):
        from .panels.kb import KnowledgeBasePanel

        if self.kb is None:
            QMessageBox.warning(self, "提示", "请先打开项目")
            return
        panel = KnowledgeBasePanel()
        panel.set_knowledge_base(self.kb)
        self._add_tab(panel, "知识库")

    def _show_pdf_library(self):
        if self.project is None:
            QMessageBox.warning(self, "提示", "请先打开项目")
            return
        from .panels.pdf_library import PDFLibraryPanel
        panel = PDFLibraryPanel()
        panel.set_project(self.project)
        panel.pdf_opened.connect(self._open_file)
        self._add_tab(panel, "文献库")

    def _show_todo_panel(self):
        from .panels.todo import TodoPanel

        if self.todo_manager is None:
            QMessageBox.warning(self, "提示", "请先打开项目")
            return
        panel = TodoPanel()
        panel.set_todo_manager(self.todo_manager)
        panel.process_requested.connect(self._start_process_todo)
        self._add_tab(panel, "TODO")

    def _show_workflow_panel(self):
        from .panels.workflow import WorkflowPanel

        panel = WorkflowPanel()
        self._add_tab(panel, "工作流")

    def _show_unidock_config(self):
        """显示 UniDock 对接配置对话框."""
        dlg = UniDockConfigDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            config = dlg.get_config()
            logger.info(f"UniDock 配置: {config}")
            # TODO: 调用 UniDock 执行对接
            self.statusbar.showMessage(f"UniDock 对接配置已设置: {config['receptor_file']}")

    def _add_tab(self, widget: QWidget, title: str):
        """安全添加标签页（避免重复）."""
        # 检查是否已有相同标题的标签
        for i in range(self.center_tabs.count()):
            if self.center_tabs.tabText(i) == title:
                self.center_tabs.setCurrentIndex(i)
                return
        self.center_tabs.addTab(widget, title)
        self.center_tabs.setCurrentIndex(self.center_tabs.count() - 1)
        # 确保切换到标签页视图
        self.center_stack.setCurrentIndex(1)

    def closeEvent(self, event):
        if hasattr(self, "index_worker") and self.index_worker is not None:
            self.index_worker.terminate()
            self.index_worker.wait(3000)
        if hasattr(self, "_model_worker") and self._model_worker is not None and self._model_worker.isRunning():
            self._model_worker.quit()
            self._model_worker.wait(3000)
        if hasattr(self.chat_widget, "_worker") and self.chat_widget._worker is not None and self.chat_widget._worker.isRunning():
            self.chat_widget._worker.stop()
            self.chat_widget._worker.wait(3000)
        event.accept()
