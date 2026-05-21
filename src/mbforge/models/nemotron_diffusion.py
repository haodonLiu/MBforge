"""Nemotron-Labs-Diffusion-3B 本地 LLM 实现.

基于 NVIDIA Nemotron 扩散语言模型，支持三种推理模式：
- AR (自回归): 传统解码方式
- dLM (扩散语言模型): 块级并行生成
- Linear Self-Speculation: 线性自推测加速

模型规格:
    - nv-community/Nemotron-Labs-Diffusion-3B: 3B 参数
    - 需要 transformers>=5.0.0
    - 支持 CUDA + bfloat16
"""

from __future__ import annotations

import os
from typing import AsyncGenerator, Iterator, List, Optional

import torch

from .base import BaseLLM, Message, StreamChunk
from ..utils.constants import ensure_hf_mirror
from ..utils.logger import get_logger

logger = get_logger(__name__)


class NemotronDiffusionLLM(BaseLLM):
    """Nemotron-Labs-Diffusion-3B 本地推理.

    使用 ModelScope 缓存加载，支持 AR/dLM/Linear-Self-Speculation 三种模式。
    """

    def __init__(
        self,
        model_path: str = "nv-community/Nemotron-Labs-Diffusion-3B",
        device: str = "cuda",
        dtype: str = "bfloat16",  # bfloat16 | float16 | float32
        max_new_tokens: int = 4096,
        mode: str = "ar",  # ar | dlm | linear_spec
    ):
        self.model_path = model_path
        self.device = device
        self.dtype = dtype
        self.max_new_tokens = max_new_tokens
        self.mode = mode
        self._model = None
        self._tokenizer = None

    def _resolve_dtype(self) -> torch.dtype:
        return {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }.get(self.dtype, torch.bfloat16)

    def _load(self) -> None:
        if self._model is not None:
            return

        ensure_hf_mirror()
        from modelscope import AutoModel, AutoTokenizer
        from .embedding import _resolve_model_path

        resolved = _resolve_model_path(self.model_path, self.model_path)
        dtype = self._resolve_dtype()
        logger.info(f"Loading Nemotron-Diffusion: {resolved} (device={self.device}, dtype={dtype})")

        self._tokenizer = AutoTokenizer.from_pretrained(
            resolved, trust_remote_code=True
        )
        self._model = AutoModel.from_pretrained(
            resolved, trust_remote_code=True, dtype=dtype
        )
        self._model = self._model.to(self.device)
        self._model.eval()
        logger.info("Nemotron-Diffusion model loaded successfully")

    def _generate(self, messages: List[Message]) -> str:
        self._load()
        assert self._tokenizer is not None
        assert self._model is not None

        history = [{"role": m.role, "content": m.content} for m in messages]
        prompt = self._tokenizer.apply_chat_template(
            history, tokenize=False, add_generation_prompt=True
        )
        prompt_ids = self._tokenizer(
            prompt, return_tensors="pt"
        ).input_ids.to(device=self.device)

        if self.mode == "dlm":
            out_ids, nfe = self._model.generate(
                prompt_ids,
                max_new_tokens=self.max_new_tokens,
                block_length=32,
                threshold=0.9,
                eos_token_id=self._tokenizer.eos_token_id,
            )
        elif self.mode == "linear_spec":
            out_ids, nfe = self._model.linear_spec_generate(
                prompt_ids,
                max_new_tokens=self.max_new_tokens,
                block_length=32,
                eos_token_id=self._tokenizer.eos_token_id,
            )
        else:  # ar
            out_ids, nfe = self._model.ar_generate(
                prompt_ids, max_new_tokens=self.max_new_tokens
            )

        result = self._tokenizer.batch_decode(
            out_ids[:, prompt_ids.shape[1]:], skip_special_tokens=True
        )[0]
        logger.debug(f"[NFE={nfe}] {result[:100]}...")
        return result

    def chat(self, messages: List[Message], **kwargs) -> str:
        return self._generate(messages)

    def chat_stream(self, messages: List[Message], **kwargs) -> Iterator[StreamChunk]:
        result = self._generate(messages)
        yield StreamChunk(delta=result, finish_reason="stop")

    async def achat(self, messages: List[Message], **kwargs) -> str:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._generate, messages)

    async def achat_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        result = await self.achat(messages, **kwargs)
        yield StreamChunk(delta=result, finish_reason="stop")
