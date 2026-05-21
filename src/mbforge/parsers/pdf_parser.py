"""PDF 解析流水线.

本质：OCR/文本提取 -> 分子识别 -> 分块 -> Embedding -> 建库
"""

from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

from ..core.document import DocumentProcessor, ExtractedContent
from ..core.knowledge_base import KnowledgeBase
from ..core.mol_database import MoleculeDatabase, MoleculeRecord
from ..parsers.molecule_extractor import MoleculeExtractor
from ..utils.helpers import generate_uuid
from ..utils.logger import get_logger

logger = get_logger(__name__)


class PDFParserPipeline:
    """PDF 解析与处理流水线.

    流程：
    1. PyMuPDF 提取文本和图片
    2. 分子结构识别（从文本提取 SMILES / 化学名）
    3. 可选：VLM 描述图片（图表、分子结构图）
    4. LLM 归纳摘要
    5. 分块存入知识库
    6. 分子数据存入分子数据库
    """

    def __init__(
        self,
        llm=None,
        embedder=None,
        vlm=None,
        knowledge_base: Optional[KnowledgeBase] = None,
        mol_db: Optional[MoleculeDatabase] = None,
    ):
        self.llm = llm
        self.embedder = embedder
        self.vlm = vlm
        self.kb = knowledge_base
        self.mol_db = mol_db
        self._extractor = MoleculeExtractor()

    def parse(
        self,
        pdf_path: Path,
        doc_id: str = "",
        extract_molecules: bool = True,
        summarize: bool = True,
        index_kb: bool = True,
    ) -> ExtractedContent:
        """解析单个 PDF 文件."""
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
            molecules = self._extract_molecules(content.text, doc_id)
            content.molecules = [m.to_dict() for m in molecules]

        # 6. 索引到知识库
        if index_kb and self.kb is not None:
            try:
                self.kb.index_document(
                    doc_id, content, metadata={"source": str(pdf_path)}
                )
            except Exception as e:
                logger.error(f"KB indexing failed for {doc_id}: {e}")

        return content

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

    def _extract_molecules(self, text: str, doc_id: str) -> List[MoleculeRecord]:
        """从文本提取分子信息并入库."""
        records = self._extractor.extract_from_text(text, doc_id=doc_id)
        for rec in records:
            self.mol_db.add_molecule(rec)
        return records
