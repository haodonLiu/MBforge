"""VLM 模型实现."""

from __future__ import annotations

import base64
from pathlib import Path

import openai

from .base import BaseVLM
from ..utils.config import VLMConfig


class APIVLM(BaseVLM):
    """通过 API 调用的 VLM（OpenAI 兼容格式，支持 vision）."""

    def __init__(self, base_url: str, api_key: str, model_name: str = ""):
        self.client = openai.OpenAI(
            base_url=base_url, api_key=api_key or "empty", timeout=120
        )
        self.model_name = model_name

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def describe_image(self, image_path: str, prompt: str = "") -> str:
        prompt = prompt or "请详细描述这张图片的内容。"
        b64 = self._encode_image(image_path)
        ext = Path(image_path).suffix.lstrip(".")
        if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
            ext = "png"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{ext};base64,{b64}"},
                    },
                ],
            }
        ]
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=2048,
        )
        return response.choices[0].message.content or ""

    def describe_pdf_page(self, image_path: str, context: str = "") -> str:
        prompt = "这是一篇科学论文的页面截图。"
        if context:
            prompt += f"\n上下文：{context}\n"
        prompt += "请提取页面中的关键信息，包括：标题、结论、分子结构描述、表格数据等。"
        return self.describe_image(image_path, prompt)


def create_vlm_from_config(config: VLMConfig) -> BaseVLM:
    """从配置创建 VLM 实例."""
    cfg = config
    return APIVLM(base_url=cfg.base_url, api_key=cfg.api_key, model_name=cfg.model_name)
