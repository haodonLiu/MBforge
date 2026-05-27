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
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore

from PIL import Image

from ..core.document import ExtractedContent
from ..core.knowledge_base import KnowledgeBase
from ..core.mol_database import MoleculeDatabase, MoleculeRecord
from .molecule.association_engine import AssociationEngine
from .molecule.extraction_result import ExtractionResult
from .molecule.mol_image_pipeline import MolImagePipeline
from .molecule.molecule_extractor import MoleculeExtractor
from .molecule.roi_text_extractor import ROITextExtractor
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
        knowledge_base: KnowledgeBase | None = None,
        mol_db: MoleculeDatabase | None = None,
        mol_image_pipeline: MolImagePipeline | None = None,
        roi_text_extractor: ROITextExtractor | None = None,
        association_engine: AssociationEngine | None = None,
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
        image_pipeline_dpi: float = 150.0,
    ) -> ExtractedContent:
        """解析单个 PDF 文件.

        Args:
            pdf_path: PDF 文件路径
            doc_id: 文档 ID，为空时自动生成
            extract_molecules: 是否提取分子
            summarize: 是否生成 LLM 摘要
            index_kb: 是否索引到知识库
            use_image_pipeline: 是否启用 MolDetv2 图像检测管线
            image_pipeline_dpi: 图像检测渲染 DPI（默认 150）
        """
        pdf_path = Path(pdf_path)
        doc_id = doc_id or generate_uuid()

        if fitz is None:
            raise ImportError("PyMuPDF (fitz) 未安装，无法处理 PDF")

        # 顶层只打开一次 PDF，所有操作复用该句柄
        with fitz.open(str(pdf_path)) as doc:
            # 1. 基础提取
            content = ExtractedContent()
            content.metadata["source"] = str(pdf_path)
            content.metadata["filename"] = pdf_path.name
            content.metadata["doc_id"] = doc_id
            content.metadata["pages"] = len(doc)

            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            content.text = "\n\n".join(text_parts)

            # 1.5. Classify PDF type
            from .pdf_classifier import PDFClassifier
            from .ocr_router import OCRMethodRouter

            classifier = PDFClassifier()
            router = OCRMethodRouter()

            doc_classification = classifier.classify_document_from_pages(
                text_parts,
                metadata=content.metadata,
            )

            content.metadata["classification"] = {
                "is_scanned": doc_classification.is_scanned,
                "has_molecules": doc_classification.has_molecular_patterns,
                "text_density": doc_classification.text_density,
                "needs_confirmation": doc_classification.needs_confirmation,
                "pages": [
                    {
                        "page_idx": p.page_idx,
                        "is_scanned": p.is_scanned,
                        "has_molecular_patterns": p.has_molecular_patterns,
                        "text_density": p.text_density,
                    }
                    for p in doc_classification.pages
                ],
            }

            if content.text:
                from ..utils.helpers import split_text_chunks

                content.chunks = split_text_chunks(content.text)

            # 2. 提取图片（限制数量/大小）+ VLM 分析
            with tempfile.TemporaryDirectory() as tmpdir:
                img_dir = Path(tmpdir) / "images"
                images = self._extract_limited_images(doc, img_dir)
                content.images = images

                # 3. VLM 分析图片（串行，避免并发内存堆积）
                if self.vlm is not None and images:
                    img_descriptions = []
                    target_images = images[:5]  # 限制数量避免太慢
                    for img_path in target_images:
                        try:
                            desc = self.vlm.describe_pdf_page(
                                str(img_path),
                                f"Document: {pdf_path.name}",
                            )
                            img_descriptions.append(
                                f"[Image {img_path.name}]: {desc}"
                            )
                        except Exception as e:
                            logger.warning(
                                "VLM analysis failed for %s: %s", img_path, e
                            )
                    if img_descriptions:
                        content.text += "\n\n## Image Analysis\n\n" + "\n\n".join(
                            img_descriptions
                        )
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
                        logger.info("Saved L0/L1 summary for %s", doc_id)
                    except Exception as e:
                        logger.error("Summary save failed for %s: %s", doc_id, e)
                content.summary = summary.l1_overview

            # 5. 分子提取
            if extract_molecules and self.mol_db is not None:
                # 5a. 图像检测管线（MolDetv2 优先）
                pending_results: list[ExtractionResult] = []
                if use_image_pipeline and self.mol_image_pipeline is not None:
                    if self.mol_image_pipeline.is_available():
                        try:
                            pending_results = self._extract_molecules_from_images(
                                doc,
                                pdf_path,
                                doc_id,
                                dpi=image_pipeline_dpi,
                            )
                        except Exception as e:
                            logger.error("图像分子检测失败：%s", e)
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
                    content.metadata["pending_extraction_count"] = len(
                        pending_results
                    )
                    content.metadata["pending_extraction_path"] = str(
                        self._pending_extractions_path(doc_id)
                    )
                    logger.info(
                        "文档 %s 图像检测发现 %d 个待确认分子",
                        doc_id,
                        len(pending_results),
                    )

            # 6. 索引到知识库（已内部分批）
            if index_kb and self.kb is not None:
                try:
                    self.kb.index_document(
                        doc_id, content, metadata={"source": str(pdf_path)}
                    )
                except Exception as e:
                    logger.error("KB indexing failed for %s: %s", doc_id, e)

        return content

    # ------------------------------------------------------------------
    # 图像分子提取（MolDetv2 + MolScribe）
    # ------------------------------------------------------------------

    def _extract_limited_images(
        self,
        doc: "fitz.Document",
        output_dir: Path,
        max_images: int = 20,
        max_size_mb: float = 2.0,
    ) -> list[Path]:
        """提取 PDF 中的图片，限制数量和单张大小以控制内存/磁盘占用."""
        output_dir.mkdir(parents=True, exist_ok=True)
        images: list[Path] = []
        max_bytes = int(max_size_mb * 1024 * 1024)

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            img_list = page.get_images(full=True)
            for img_idx, img in enumerate(img_list, start=1):
                if len(images) >= max_images:
                    logger.debug("Reached max image limit (%d)", max_images)
                    return images
                xref = img[0]
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue
                img_bytes = base_image["image"]
                if len(img_bytes) > max_bytes:
                    logger.debug(
                        "Skipping oversized image %s bytes > %s bytes",
                        len(img_bytes),
                        max_bytes,
                    )
                    continue
                ext = base_image["ext"]
                img_path = (
                    output_dir / f"page_{page_idx + 1}_img_{img_idx}.{ext}"
                )
                with open(img_path, "wb") as f:
                    f.write(img_bytes)
                images.append(img_path)
        return images

    def _extract_molecules_from_images(
        self,
        doc: "fitz.Document",
        pdf_path: Path,
        doc_id: str,
        dpi: float = 150.0,
    ) -> list[ExtractionResult]:
        """渲染 PDF 页面为图像，运行 MolDetv2 检测 + MolScribe 识别 + ROI 文本提取.

        Args:
            doc: 已打开的 fitz Document 对象（由上层统一打开，避免重复）
            pdf_path: PDF 路径（用于 ROI 文本提取）
            doc_id: 文档 ID
            dpi: 渲染 DPI（默认 150，降低内存占用）

        Returns:
            ExtractionResult 列表（status=pending）
        """
        all_results: list[ExtractionResult] = []
        crop_cache_dir = self._crop_cache_dir(doc_id)
        crop_cache_dir.mkdir(parents=True, exist_ok=True)

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            pix = page.get_pixmap(dpi=dpi)
            try:
                img = Image.frombytes(
                    "RGB", [pix.width, pix.height], pix.samples
                )
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
                    logger.warning("页面 %d 图像检测失败：%s", page_idx, exc)
                finally:
                    img.close()
            finally:
                del pix

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
        results: list[ExtractionResult],
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
    def load_pending_extractions(cls, path: Path) -> list[ExtractionResult]:
        """从 JSON 加载 pending 结果."""
        with open(path, encoding="utf-8") as f:
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
    ) -> list[MoleculeRecord]:
        """从文本提取分子信息并入库（捡漏角色）."""
        records = self._extractor.extract_from_text(text, doc_id=doc_id)
        for rec in records:
            self.mol_db.add_molecule(rec)
        return records
