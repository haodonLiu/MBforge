"""文件处理 TODO 队列管理.

导入文件到 raw/ 后，自动或手动加入 TODO 队列。
逐个处理，输出存入 output/<doc_id>/ 文件夹。
"""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..utils.constants import PROJECT_META_DIR
from ..utils.helpers import generate_uuid
from ..utils.logger import get_logger

logger = get_logger(__name__)

TODO_FILE = "todo.json"
OUTPUT_DIR = "output"


class TodoStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class TodoEntry:
    """单个 TODO 条目."""

    doc_id: str
    filename: str
    source_path: str  # raw/ 中的相对路径
    status: str = TodoStatus.PENDING
    added_at: str = field(default_factory=lambda: datetime.now().isoformat())
    processed_at: Optional[str] = None
    error: Optional[str] = None
    output_dir: Optional[str] = None  # output/<doc_id>/ 相对路径

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TodoEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TodoManager:
    """项目级 TODO 队列管理器."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.todo_path = self.project_root / PROJECT_META_DIR / TODO_FILE
        self.output_dir = self.project_root / OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._entries: List[TodoEntry] = []
        self._lock = threading.Lock()
        self._processing = False
        self._load()

    def _load(self) -> None:
        if self.todo_path.exists():
            try:
                with open(self.todo_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = [TodoEntry.from_dict(e) for e in data.get("entries", [])]
            except Exception as e:
                logger.warning(f"Failed to load todo: {e}")
                self._entries = []

    def save(self) -> None:
        with self._lock:
            self.todo_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.todo_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"entries": [e.to_dict() for e in self._entries]},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

    def add_file(self, filename: str, source_rel_path: str) -> TodoEntry:
        """添加文件到 TODO 队列."""
        # 检查是否已存在
        for e in self._entries:
            if e.source_path == source_rel_path and e.status != TodoStatus.FAILED:
                logger.debug(f"File already in todo: {filename}")
                return e

        entry = TodoEntry(
            doc_id=generate_uuid(),
            filename=filename,
            source_path=source_rel_path,
        )
        self._entries.append(entry)
        self.save()
        logger.info(f"Todo added: {filename} ({entry.doc_id})")
        return entry

    def get_pending(self) -> List[TodoEntry]:
        """获取所有待处理条目."""
        return [e for e in self._entries if e.status == TodoStatus.PENDING]

    def get_all(self) -> List[TodoEntry]:
        """获取所有条目."""
        return list(self._entries)

    def get_entry(self, doc_id: str) -> Optional[TodoEntry]:
        """按 doc_id 获取条目."""
        for e in self._entries:
            if e.doc_id == doc_id:
                return e
        return None

    def update_status(self, doc_id: str, status: str, error: str = None) -> None:
        """更新条目状态."""
        entry = self.get_entry(doc_id)
        if entry:
            entry.status = status
            if status == TodoStatus.DONE:
                entry.processed_at = datetime.now().isoformat()
                entry.output_dir = str(self.output_dir / doc_id)
            if error:
                entry.error = error
            self.save()

    def get_output_path(self, doc_id: str) -> Path:
        """获取文件的输出目录."""
        return self.output_dir / doc_id

    def remove_entry(self, doc_id: str) -> bool:
        """移除条目."""
        for i, e in enumerate(self._entries):
            if e.doc_id == doc_id:
                self._entries.pop(i)
                self.save()
                return True
        return False

    def clear_done(self) -> int:
        """清除所有已完成条目，返回清除数量."""
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.status != TodoStatus.DONE]
        self.save()
        return before - len(self._entries)

    @property
    def is_processing(self) -> bool:
        return self._processing

    def process_next(
        self,
        file_processor: Callable[[TodoEntry, Path, Path], Dict[str, Any]],
    ) -> Optional[TodoEntry]:
        """处理下一个待处理条目.

        Args:
            file_processor: 处理函数，接收 (entry, source_path, output_dir)，
                           返回要保存的 dict（写入 output/<doc_id>/index.json）

        Returns:
            处理的条目，或 None（无待处理项）
        """
        pending = self.get_pending()
        if not pending:
            return None

        entry = pending[0]
        entry.status = TodoStatus.PROCESSING
        self.save()

        source_path = self.project_root / entry.source_path
        out_dir = self.output_dir / entry.doc_id
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            result = file_processor(entry, source_path, out_dir)
            # 保存处理结果索引
            index_path = out_dir / "index.json"
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            self.update_status(entry.doc_id, TodoStatus.DONE)
            logger.info(f"Processed: {entry.filename} -> {out_dir}")
        except Exception as e:
            self.update_status(entry.doc_id, TodoStatus.FAILED, error=str(e))
            logger.error(f"Failed to process {entry.filename}: {e}")

        return entry

    def process_all(
        self,
        file_processor: Callable[[TodoEntry, Path, Path], Dict[str, Any]],
        on_progress: Optional[Callable[[int, int, TodoEntry], None]] = None,
    ) -> None:
        """批量处理所有待处理条目（同步）.

        Args:
            file_processor: 处理函数
            on_progress: 进度回调 (current, total, entry)
        """
        pending = self.get_pending()
        total = len(pending)
        for i, entry in enumerate(pending):
            if on_progress:
                on_progress(i + 1, total, entry)
            self.process_next(file_processor)

    def process_all_async(
        self,
        file_processor: Callable[[TodoEntry, Path, Path], Dict[str, Any]],
        on_progress: Optional[Callable[[int, int, TodoEntry], None]] = None,
        on_done: Optional[Callable[[], None]] = None,
    ) -> None:
        """异步批量处理（后台线程）."""
        if self._processing:
            logger.warning("Already processing")
            return

        def _worker():
            self._processing = True
            try:
                self.process_all(file_processor, on_progress)
            finally:
                self._processing = False
                if on_done:
                    on_done()

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
