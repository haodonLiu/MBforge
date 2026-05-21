"""GLM-OCR 文档解析后端.

支持多种部署方式:
1. Ollama 本地部署 (推荐): 通过 OpenAI 兼容 API 调用本地 Ollama 服务
2. vLLM/SGLang 本地部署: 通过 OpenAI 兼容 API 调用
3. MaaS API: 智谱云托管服务
4. transformers 直接加载: 本地 GPU 推理

输出结构化 Markdown/JSON，化学结构图像位置保留占位符。
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List

import requests

from ..utils.logger import get_logger
from .base_parser import BaseDocumentParser, ParseOutput

logger = get_logger(__name__)


class GlmOcrClient(BaseDocumentParser):
    """GLM-OCR 客户端封装.

    优先通过 HTTP API (Ollama/vLLM) 调用，不可用则 fallback 到 PyMuPDF。
    """

    def __init__(
        self,
        provider: str = "glm_ocr_ollama",  # glm_ocr_ollama | glm_ocr_vllm | glm_ocr_maas
        base_url: str = "http://localhost:11434/v1",  # Ollama 默认地址
        api_key: str = "",
        model_name: str = "glm-ocr",  # Ollama 模型名
        timeout: int = 120,
    ):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout

    def _encode_image(self, image_path: Path) -> str:
        """将图像编码为 base64 data URI."""
        with open(image_path, "rb") as f:
            data = f.read()
        ext = image_path.suffix.lstrip(".").lower()
        if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
            ext = "png"
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:image/{ext};base64,{b64}"

    def _call_api(self, image_b64: str, prompt: str = "") -> str:
        """通过 OpenAI 兼容 API 调用 GLM-OCR."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # 化学结构识别专用 prompt
        ocr_prompt = prompt or (
            "请对这份文档进行 OCR 识别，输出结构化 Markdown。\n"
            "注意：\n"
            "1. 保留原文的标题层级结构\n"
            "2. 表格转换为 Markdown 表格格式\n"
            "3. 化学结构图像的位置用占位符标记：`<molecule_image>[描述]</molecule_image>`\n"
            "4. 公式转换为 LaTeX 格式\n"
            "5. 尽可能提取化学结构对应的 SMILES（如有）"
        )

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": ocr_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_b64},
                        },
                    ],
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.1,  # OCR 任务低温度
        }

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""
        except Exception as e:
            logger.warning(f"GLM-OCR API call failed: {e}")
            raise

    def parse(self, pdf_path: Path, **kwargs) -> ParseOutput:
        """解析 PDF，返回统一 ParseOutput。"""
        try:
            result = self._parse_with_glm(pdf_path)
        except Exception as e:
            logger.warning(f"GLM-OCR parsing failed ({e}), falling back to PyMuPDF")
            result = self._fallback_pymupdf(pdf_path)
        return ParseOutput(
            text=result.get("text", ""),
            markdown=result.get("markdown", ""),
            pages=result.get("pages", []),
            metadata={"parser": result.get("parser", "glm_ocr")},
        )

    def parse_pdf(self, pdf_path: Path, **kwargs) -> Dict[str, Any]:
        """向后兼容：返回旧格式 dict。"""
        out = self.parse(pdf_path, **kwargs)
        return {
            "text": out.text,
            "markdown": out.markdown,
            "pages": out.pages,
            "parser": out.metadata.get("parser", "glm_ocr"),
        }

    def _parse_with_glm(self, pdf_path: Path) -> Dict[str, Any]:
        """使用 GLM-OCR 解析 PDF."""
        import shutil

        page_images = self._pdf_to_images(pdf_path)
        tmpdir = page_images[0].parent if page_images else None

        try:
            pages_md = []
            molecule_placeholders = []

            for idx, img_path in enumerate(page_images):
                try:
                    b64 = self._encode_image(img_path)
                    page_md = self._call_api(b64)
                    pages_md.append(page_md)
                    placeholders = self._extract_molecule_placeholders(
                        page_md, page_idx=idx
                    )
                    molecule_placeholders.extend(placeholders)
                except Exception as e:
                    logger.warning(f"Page {idx} OCR failed: {e}")
                    pages_md.append(f"<!-- Page {idx} OCR failed -->")

            full_markdown = "\n\n---\n\n".join(pages_md)
            return {
                "markdown": full_markdown,
                "text": self._markdown_to_text(full_markdown),
                "pages": pages_md,
                "molecule_placeholders": molecule_placeholders,
                "parser": "glm_ocr",
            }
        finally:
            if tmpdir and tmpdir.exists():
                shutil.rmtree(tmpdir, ignore_errors=True)

    def _fallback_pymupdf(self, pdf_path: Path) -> Dict[str, Any]:
        """Fallback 到 PyMuPDF."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(pdf_path))
            texts = []
            for page in doc:
                texts.append(page.get_text())
            full_text = "\n\n".join(texts)
            return {
                "markdown": full_text,
                "text": full_text,
                "pages": texts,
                "molecule_placeholders": [],
                "parser": "pymupdf",
            }
        except Exception as e:
            logger.error(f"PyMuPDF fallback also failed: {e}")
            raise

    def _pdf_to_images(self, pdf_path: Path, dpi: int = 200) -> List[Path]:
        """将 PDF 转为图像列表."""
        import tempfile

        try:
            import fitz

            doc = fitz.open(str(pdf_path))
            tmpdir = Path(tempfile.mkdtemp(prefix="mbforge_glm_ocr_"))
            images = []
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=dpi)
                img_path = tmpdir / f"page_{i:04d}.png"
                pix.save(str(img_path))
                images.append(img_path)
            return images
        except Exception as e:
            logger.error(f"PDF to image conversion failed: {e}")
            raise

    def _extract_molecule_placeholders(
        self, markdown: str, page_idx: int
    ) -> List[Dict[str, Any]]:
        """从 Markdown 中提取分子占位符.

        占位符格式: `<molecule_image>[描述]</molecule_image>`
        """
        import re

        placeholders = []
        pattern = re.compile(r"<molecule_image>\[(.*?)\]</molecule_image>")
        for match in pattern.finditer(markdown):
            placeholders.append(
                {
                    "page": page_idx,
                    "description": match.group(1),
                    "position": match.start(),
                }
            )
        return placeholders

    def _markdown_to_text(self, markdown: str) -> str:
        """简单 Markdown 转纯文本（用于兼容现有流程）."""
        import re

        text = markdown
        # 移除 HTML 标签
        text = re.sub(r"<[^>]+>", "", text)
        # 简化表格
        text = re.sub(r"\|[^\n]*\|", "", text)
        # 移除 Markdown 标记
        text = re.sub(r"[#*_`\[\]\(\)!]", "", text)
        return text.strip()
