"""Internationalization for MBForge GUI."""

from __future__ import annotations

# ── Translation dictionaries ────────────────────────────────

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh-CN": {
        # Navigation
        "nav.workspace": "工作区",
        "nav.discover": "发现",
        "nav.molecules": "分子库",
        "nav.queue": "处理队列",
        "nav.notes": "笔记",
        "nav.settings": "设置",
        "nav.switch_project": "切换项目",
        # Welcome
        "welcome.title": "MBForge",
        "welcome.subtitle": "分子知识库与 AI 工作台",
        "welcome.create_project": "创建项目",
        "welcome.open_project": "打开项目",
        "welcome.recent_libraries": "最近库",
        "welcome.no_libraries": "暂无库",
        # Workspace
        "workspace.dashboard": "仪表盘",
        "workspace.documents": "文档",
        "workspace.sections": "段落",
        "workspace.indexed": "已索引",
        "workspace.molecules": "分子",
        "workspace.sync": "同步",
        "workspace.scan": "扫描",
        "workspace.file_tree": "文件树",
        # Discover
        "discover.search": "搜索",
        "discover.chat": "对话",
        "discover.search_hint": "输入搜索关键词...",
        "discover.chat_hint": "输入消息...",
        "discover.no_results": "无搜索结果",
        "discover.send": "发送",
        # Molecules
        "molecules.list": "分子列表",
        "molecules.analysis": "分析",
        "molecules.search": "搜索分子...",
        "molecules.add": "添加分子",
        "molecules.smiles": "SMILES",
        "molecules.name": "名称",
        "molecules.activity": "活性",
        "molecules.source": "来源",
        "molecules.status": "状态",
        "molecules.total": "共 {count} 个分子",
        # Queue
        "queue.title": "处理队列",
        "queue.all": "全部",
        "queue.pending": "待处理",
        "queue.processing": "处理中",
        "queue.done": "完成",
        "queue.failed": "失败",
        "queue.cancel": "取消",
        "queue.retry": "重试",
        "queue.delete": "删除",
        "queue.logs": "日志",
        # Notes
        "notes.title": "笔记",
        "notes.new": "新建笔记",
        "notes.search": "搜索笔记...",
        "notes.backlinks": "双向链接",
        "notes.no_notes": "暂无笔记",
        # Settings
        "settings.title": "设置",
        "settings.general": "通用",
        "settings.ai_models": "AI 模型",
        "settings.pdf_processing": "PDF 处理",
        "settings.models": "模型",
        "settings.system": "系统",
        "settings.cache": "缓存",
        "settings.about": "关于",
        "settings.save": "保存",
        "settings.cancel": "取消",
        "settings.language": "语言",
        "settings.theme": "主题",
        "settings.dark": "暗色",
        "settings.light": "亮色",
        # Common
        "common.loading": "加载中...",
        "common.error": "错误",
        "common.success": "成功",
        "common.confirm": "确认",
        "common.close": "关闭",
        "common.back": "返回",
        "common.next": "下一步",
        "common.refresh": "刷新",
        "common.empty": "暂无数据",
    },
    "en": {
        # Navigation
        "nav.workspace": "Workspace",
        "nav.discover": "Discover",
        "nav.molecules": "Molecules",
        "nav.queue": "Queue",
        "nav.notes": "Notes",
        "nav.settings": "Settings",
        "nav.switch_project": "Switch Project",
        # Welcome
        "welcome.title": "MBForge",
        "welcome.subtitle": "Molecular Knowledge Base & AI Workbench",
        "welcome.create_project": "Create Project",
        "welcome.open_project": "Open Project",
        "welcome.recent_libraries": "Recent Libraries",
        "welcome.no_libraries": "No libraries yet",
        # Workspace
        "workspace.dashboard": "Dashboard",
        "workspace.documents": "Documents",
        "workspace.sections": "Sections",
        "workspace.indexed": "Indexed",
        "workspace.molecules": "Molecules",
        "workspace.sync": "Sync",
        "workspace.scan": "Scan",
        "workspace.file_tree": "File Tree",
        # Discover
        "discover.search": "Search",
        "discover.chat": "Chat",
        "discover.search_hint": "Enter search keywords...",
        "discover.chat_hint": "Enter message...",
        "discover.no_results": "No results found",
        "discover.send": "Send",
        # Molecules
        "molecules.list": "Molecule List",
        "molecules.analysis": "Analysis",
        "molecules.search": "Search molecules...",
        "molecules.add": "Add Molecule",
        "molecules.smiles": "SMILES",
        "molecules.name": "Name",
        "molecules.activity": "Activity",
        "molecules.source": "Source",
        "molecules.status": "Status",
        "molecules.total": "{count} molecules total",
        # Queue
        "queue.title": "Processing Queue",
        "queue.all": "All",
        "queue.pending": "Pending",
        "queue.processing": "Processing",
        "queue.done": "Done",
        "queue.failed": "Failed",
        "queue.cancel": "Cancel",
        "queue.retry": "Retry",
        "queue.delete": "Delete",
        "queue.logs": "Logs",
        # Notes
        "notes.title": "Notes",
        "notes.new": "New Note",
        "notes.search": "Search notes...",
        "notes.backlinks": "Backlinks",
        "notes.no_notes": "No notes yet",
        # Settings
        "settings.title": "Settings",
        "settings.general": "General",
        "settings.ai_models": "AI Models",
        "settings.pdf_processing": "PDF Processing",
        "settings.models": "Models",
        "settings.system": "System",
        "settings.cache": "Cache",
        "settings.about": "About",
        "settings.save": "Save",
        "settings.cancel": "Cancel",
        "settings.language": "Language",
        "settings.theme": "Theme",
        "settings.dark": "Dark",
        "settings.light": "Light",
        # Common
        "common.loading": "Loading...",
        "common.error": "Error",
        "common.success": "Success",
        "common.confirm": "Confirm",
        "common.close": "Close",
        "common.back": "Back",
        "common.next": "Next",
        "common.refresh": "Refresh",
        "common.empty": "No data",
    },
}

_current_lang = "zh-CN"


def set_language(lang: str):
    global _current_lang
    _current_lang = lang


def get_language() -> str:
    return _current_lang


def t(key: str, **kwargs) -> str:
    """Translate a key, with optional format arguments."""
    translations = _TRANSLATIONS.get(_current_lang, _TRANSLATIONS["en"])
    text = translations.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
