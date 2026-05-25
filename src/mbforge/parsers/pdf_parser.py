"""PDF 解析流水线.

本质：OCR/文本提取 -> 分子识别 -> 分块 -> Embedding -> 建库

MolDetv2 优先重构（Week 1）：
- 新增图像检测管线入口（MolImagePipeline）
- 图像检测结果为 pending，保存到 .mbforge/extractions/ 等待人工确认
- 文本正则降级为捡漏，结果直接入库
"""

from __future__ import annotations

import json
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore

from PIL import Image

from ..core.document import DocumentProcessor, ExtractedContent
from ..core.knowledge_base import KnowledgeBase
from ..core.mol_database import MoleculeDatabase, MoleculeRecord
from ..parsers.association_engine import AssociationEngine
from ..parsers.extraction_result import ExtractionResult
from ..parsers.mol_image_pipeline import MolImagePipeline
from ..parsers.molecule_extractor import MoleculeExtractor
from ..parsers.roi_text_extractor import ROITextExtractor
from ..utils.constants import PROJECT_META_DIR
from ..utils.helpers import generate_uuid
from ..utils.logger import get_logger

logger = get_logger(__name__)


class PDFParserPipeline:
    """PDF 解析与处理流水线.

    流程：
    1. PyMuPDF 提取文本和图片
    2. 分子结构识别（图像检测优先 + 文本正则捡漏）
    3. 可选：VLM 描述图片（图表、分子结构图）
    4. LLM 归纳摘要
    5. 分块存入知识库
    6. 分子数据存入分子数据库（文本来源直接入库；图像来源 pending）
    """

    def __init__(
        self,
        llm=None,
        embedder=None,
        vlm=None,
        knowledge_base: Optional[KnowledgeBase] = None,
        mol_db: Optional[MoleculeDatabase] = None,
        mol_image_pipeline: Optional[MolImagePipeline] = None,
        roi_text_extractor: Optional[ROITextExtractor] = None,
        association_engine: Optional[AssociationEngine] = None,
    ):
        self.llm = llm
        self.embedder = embedder
        self.vlm = vlm
        self.kb = knowledge_base
        self.mol_db = mol_db
        self.mol_image_pipeline = mol_image_pipeline
        self.roi_text_extractor = roi_text_extractor or ROITextExtractor()
        self.association_engine = association_engine or AssociationEngine()
        self._extractor = MoleculeExtractor()

    def parse(
        self,
        pdf_path: Path,
        doc_id: str = "",
        extract_molecules: bool = True,
        summarize: bool = True,
        index_kb: bool = True,
        use_image_pipeline: bool = False,
        image_pipeline_dpi: float = 300.0,
    ) -> ExtractedContent:
        """解析单个 PDF 文件.

        Args:
            pdf_path: PDF 文件路径
            doc_id: 文档 ID，为空时自动生成
            extract_molecules: 是否提取分子
            summarize: 是否生成 LLM 摘要
            index_kb: 是否索引到知识库
            use_image_pipeline: 是否启用 MolDetv2 图像检测管线
            image_pipeline_dpi: 图像检测渲染 DPI（默认 300）
        """
        pdf_path = Path(pdf_path)
        doc_id = doc_id or generate_uuid()

        # 1. 基础提取
        content = DocumentProcessor.process(pdf_path)
        content.metadata["doc_id"] = doc_id

        # 2. 提取图片（用于 VLM 分析）
        with tempfile.TemporaryDirectory() as tmpdir:
            img_dir = Path(tmpdir) / "images"
            images = DocumentProcessor.extract_pdf_images(pdf_path, img_dir)
            content.images = images

            # 3. VLM 分析图片（如果可用，并行化）
            if self.vlm is not None and images:
                img_descriptions = []
                target_images = images[:5]  # 限制数量避免太慢
                with ThreadPoolExecutor(max_workers=len(target_images)) as pool:
                    futures = {
                        pool.submit(
                            self.vlm.describe_pdf_page,
                            str(img_path),
                            f"Document: {pdf_path.name}",
                        ): img_path
                        for img_path in target_images
                    }
                    for future in as_completed(futures):
                        img_path = futures[future]
                        try:
                            desc = future.result()
                            img_descriptions.append(f"[Image {img_path.name}]: {desc}")
                        except Exception as e:
                            logger.warning(f"VLM analysis failed for {img_path}: {e}")
                if img_descriptions:
                    content.text += "\n\n## Image Analysis\n\n" + "\n\n".join(
                        img_descriptions
                    )
                    # 重新分块
                    from ..utils.helpers import split_text_chunks

                    content.chunks = split_text_chunks(content.text)

        # 4. LLM 摘要 + L0/L1/L2 三层摘要
        if summarize and content.text:
            from ..core.summarizer import DocumentSummarizer, SummaryManager

            summarizer = DocumentSummarizer(llm=self.llm)
            summary = summarizer.summarize(content, doc_id)
            if self.kb is not None:
                try:
                    sm = SummaryManager(self.kb.project_root)
                    sm.save(summary)
                    logger.info(f"Saved L0/L1 summary for {doc_id}")
                except Exception as e:
                    logger.error(f"Summary save failed for {doc_id}: {e}")
            content.summary = summary.l1_overview

        # 5. 分子提取
        if extract_molecules and self.mol_db is not None:
            # 5a. 图像检测管线（MolDetv2 优先）
            pending_results: List[ExtractionResult] = []
            if use_image_pipeline and self.mol_image_pipeline is not None:
                if self.mol_image_pipeline.is_available():
                    try:
                        pending_results = self._extract_molecules_from_images(
                            pdf_path,
                            doc_id,
                            dpi=image_pipeline_dpi,
                        )
                    except Exception as e:
                        logger.error(f"图像分子检测失败：{e}")
                else:
                    logger.warning(
                        "MolImagePipeline 不可用（模型未下载），跳过图像检测"
                    )

            # 5b. 文本正则捡漏（直接入库）
            text_records = self._extract_molecules_from_text(content.text, doc_id)
            content.molecules = [m.to_dict() for m in text_records]

            # 5c. 保存 pending 结果（图像来源，等待人工确认）
            if pending_results:
                self._save_pending_extractions(pending_results, doc_id)
                content.metadata["pending_extraction_count"] = len(pending_results)
                content.metadata["pending_extraction_path"] = str(
                    self._pending_extractions_path(doc_id)
                )
                logger.info(
                    "文档 %s 图像检测发现 %d 个待确认分子",
                    doc_id,
                    len(pending_results),
                )

        # 6. 索引到知识库
        if index_kb and self.kb is not None:
            try:
                self.kb.index_document(
                    doc_id, content, metadata={"source": str(pdf_path)}
                )
            except Exception as e:
                logger.error(f"KB indexing failed for {doc_id}: {e}")

        return content

    # ------------------------------------------------------------------
    # 图像分子提取（MolDetv2 + MolScribe）
    # ------------------------------------------------------------------

    def _extract_molecules_from_images(
        self,
        pdf_path: Path,
        doc_id: str,
        dpi: float = 300.0,
    ) -> List[ExtractionResult]:
        """渲染 PDF 页面为图像，运行 MolDetv2 检测 + MolScribe 识别 + ROI 文本提取.

        Returns:
            ExtractionResult 列表（status=pending）
        """
        if fitz is None:
            raise ImportError("PyMuPDF 未安装，无法渲染 PDF 页面")

        all_results: List[ExtractionResult] = []
        crop_cache_dir = self._crop_cache_dir(doc_id)
        crop_cache_dir.mkdir(parents=True, exist_ok=True)

        with fitz.open(str(pdf_path)) as doc:
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                # 渲染页面为图像
                pix = page.get_pixmap(dpi=dpi)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                try:
                    results = self.mol_image_pipeline.extract_page(  # type: ignore[union-attr]
                        image=img,
                        page_idx=page_idx,
                        page_w_pts=page.rect.width,
                        page_h_pts=page.rect.height,
                        image_w=pix.width,
                        image_h=pix.height,
                        dpi=dpi,
                        cache_prefix=f"{doc_id}_page_{page_idx:04d}",
                    )
                    # ROI 文本提取 + 关联
                    for result in results:
                        if result.bbox_pdf is not None:
                            context = self.roi_text_extractor.extract_context(
                                pdf_path=pdf_path,
                                page_idx=page_idx,
                                bbox_pdf=result.bbox_pdf,
                                page_w_pts=page.rect.width,
                                page_h_pts=page.rect.height,
                            )
                            result.context_text = context
                    if results:
                        self.association_engine.associate_all(results)

                    all_results.extend(results)
                except Exception as exc:
                    logger.warning(
                        "页面 %d 图像检测失败：%s", page_idx, exc
                    )

        return all_results

    def _crop_cache_dir(self, doc_id: str) -> Path:
        """分子裁剪图像缓存目录."""
        if self.mol_db is not None:
            return (
                self.mol_db.project_root
                / PROJECT_META_DIR
                / "extractions"
                / doc_id
                / "crops"
            )
        # fallback：系统临时目录
        return Path(tempfile.gettempdir()) / "mbforge" / "extractions" / doc_id / "crops"

    def _pending_extractions_path(self, doc_id: str) -> Path:
        """pending 提取结果保存路径."""
        if self.mol_db is not None:
            return (
                self.mol_db.project_root
                / PROJECT_META_DIR
                / "extractions"
                / doc_id
                / "pending.json"
            )
        return Path(tempfile.gettempdir()) / "mbforge" / "extractions" / doc_id / "pending.json"

    def _save_pending_extractions(
        self,
        results: List[ExtractionResult],
        doc_id: str,
    ) -> None:
        """将 pending 结果序列化保存到 JSON."""
        path = self._pending_extractions_path(doc_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"doc_id": doc_id, "results": [r.to_dict() for r in results]}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug("Pending 结果已保存：%s", path)

    @classmethod
    def load_pending_extractions(cls, path: Path) -> List[ExtractionResult]:
        """从 JSON 加载 pending 结果."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [ExtractionResult.from_dict(r) for r in data.get("results", [])]

    def _summarize(self, text: str) -> str:
        """使用 LLM 归纳文本."""
        from ..models.base import Message

        prompt = (
            "请对以下科学文献内容进行归纳总结，提取关键信息包括：\n"
            "1. 研究目的\n"
            "2. 主要方法\n"
            "3. 关键分子/化合物\n"
            "4. 主要结论\n"
            "5. 生物活性数据（如有）\n\n"
            f"内容：\n{text[:8000]}\n\n"
            "请用中文输出结构化摘要。"
        )
        messages = [
            Message(role="system", content="你是一位专业的药物化学文献分析助手。"),
            Message(role="user", content=prompt),
        ]
        return self.llm.chat(messages)

    def _extract_molecules_from_text(
        self, text: str, doc_id: str
    ) -> List[MoleculeRecord]:
        """从文本提取分子信息并入库（捡漏角色）."""
        records = self._extractor.extract_from_text(text, doc_id=doc_id)
        for rec in records:
            self.mol_db.add_molecule(rec)
        return records
