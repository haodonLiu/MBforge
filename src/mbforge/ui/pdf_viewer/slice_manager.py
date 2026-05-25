"""PDF 分片管理器."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # PyMuPDF

from mbforge.utils.logger import get_logger, log_exception

logger = get_logger(__name__)


class PDFSliceManager:
    """大PDF分片管理器：将超长PDF切成多份子PDF，按需加载.

    分片存储在项目目录 .mbforge/pdf_slices/<hash>/ 下：
        part_000.pdf  (页 0-49)
        part_001.pdf  (页 50-99)
        ...
        metadata.json (页尺寸等元数据)
    """

    SLICE_SIZE = 50  # 每 50 页一份
    MIN_PAGES_TO_SLICE = 100  # 超过此页数才触发切片

    def __init__(self, pdf_path: Path, project_root: Path):
        self.pdf_path = Path(pdf_path)
        self.project_root = Path(project_root)

        # hash 基于绝对路径 + 修改时间，文件变化自动重建缓存
        mtime = self.pdf_path.stat().st_mtime
        hash_input = f"{self.pdf_path.resolve()}:{mtime}"
        self.doc_hash = hashlib.md5(hash_input.encode()).hexdigest()[:16]
        self.cache_dir = self.project_root / ".mbforge" / "pdf_slices" / self.doc_hash

        self._meta: Optional[dict] = None
        self._total_pages = 0
        self._page_sizes: List[Tuple[float, float]] = []

    def ensure_sliced(self) -> bool:
        """检查并执行切片。返回 True 表示已就绪并启用分片模式。"""
        logger.info(f"PDFSliceManager.ensure_sliced | pdf={self.pdf_path} | cache_dir={self.cache_dir}")
        meta_path = self.cache_dir / "metadata.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    self._meta = json.load(f)
                # 验证源文件未变化
                if self._meta.get("mtime") == self.pdf_path.stat().st_mtime:
                    self._total_pages = self._meta["total_pages"]
                    self._page_sizes = [tuple(p) for p in self._meta["page_sizes"]]
                    return self._total_pages >= self.MIN_PAGES_TO_SLICE
            except (json.JSONDecodeError, KeyError, OSError):
                pass  # 缓存损坏，重新切片

        return self._do_slicing()

    def _do_slicing(self) -> bool:
        """执行实际切片操作。"""
        logger.info(f"开始切片: {self.pdf_path}")
        doc = fitz.open(str(self.pdf_path))
        try:
            self._total_pages = len(doc)
            if self._total_pages < self.MIN_PAGES_TO_SLICE:
                return False  # 小文件不需要切片

            self.cache_dir.mkdir(parents=True, exist_ok=True)

            # 收集所有页原始尺寸（避免后续再打开完整PDF）
            self._page_sizes = []
            for i in range(self._total_pages):
                rect = doc[i].mediabox
                self._page_sizes.append((rect.width, rect.height))

            # 生成分片
            num_slices = (self._total_pages + self.SLICE_SIZE - 1) // self.SLICE_SIZE
            for s in range(num_slices):
                start = s * self.SLICE_SIZE
                end = min(start + self.SLICE_SIZE, self._total_pages)
                slice_doc = fitz.open()
                slice_doc.insert_pdf(doc, from_page=start, to_page=end - 1)
                slice_path = self.cache_dir / f"part_{s:03d}.pdf"
                slice_doc.save(str(slice_path))
                slice_doc.close()

            # 保存 metadata
            self._meta = {
                "source": str(self.pdf_path.resolve()),
                "mtime": self.pdf_path.stat().st_mtime,
                "slice_size": self.SLICE_SIZE,
                "total_pages": self._total_pages,
                "page_sizes": self._page_sizes,
            }
            with open(self.cache_dir / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(self._meta, f, ensure_ascii=False)

            logger.info(f"切片完成: {self.pdf_path} | {num_slices} 个分片 | 总页数={self._total_pages}")
            return True
        except Exception:
            log_exception(logger, f"切片失败: {self.pdf_path}")
            return False
        finally:
            doc.close()

    @property
    def total_pages(self) -> int:
        return self._total_pages

    @property
    def page_sizes(self) -> List[Tuple[float, float]]:
        return self._page_sizes

    def get_slice_path(self, global_page: int) -> Path:
        """获取指定全局页码所在的分片文件路径。"""
        slice_idx = global_page // self.SLICE_SIZE
        return self.cache_dir / f"part_{slice_idx:03d}.pdf"

    def get_local_index(self, global_page: int) -> int:
        """将全局页码映射为分片内局部页码。"""
        return global_page % self.SLICE_SIZE
