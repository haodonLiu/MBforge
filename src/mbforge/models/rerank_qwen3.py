"""Qwen3-Reranker 实现.

基于 CausalLM 的生成式重排序器，通过 yes/no 概率判断 query-document 相关性。
与 BGE CrossEncoder 架构完全不同。

模型规格:
    - Qwen/Qwen3-Reranker-0.6B: 0.6B 参数, 32K context
    - 架构: CausalLM (非 CrossEncoder)
    - 推理: 构造 yes/no 判断 prompt, 取 yes token 的 logits 概率
    - 依赖: transformers>=4.51.0

参考实现:
    https://huggingface.co/Qwen/Qwen3-Reranker-0.6B
"""

from __future__ import annotations

import os
from typing import List, Optional

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

from .base import BaseReranker
from ..utils.constants import DEFAULT_RERANK_MODEL, DEFAULT_HF_ENDPOINT
from ..utils.logger import get_logger

logger = get_logger(__name__)


def _ensure_hf_mirror() -> None:
    if "HF_ENDPOINT" not in os.environ:
        os.environ["HF_ENDPOINT"] = DEFAULT_HF_ENDPOINT


class Qwen3Reranker(BaseReranker):
    """Qwen3-Reranker 重排序器.

    使用 CausalLM 的 yes/no 判断机制对候选文档进行相关性评分。
    推理流程:
        1. 为每个 (query, doc) 构造判断 prompt
        2. 取模型最后一个 token 位置 yes/no 的 logits
        3. 计算 yes 的归一化概率作为相关性分数
    """

    # 默认任务指令
    DEFAULT_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"

    # Prompt 模板
    _PREFIX = (
        "<|im_start|>system\n"
        'Judge whether the Document meets the requirements based on the Query and the Instruct provided. '
        'Note that the answer can only be "yes" or "no".'
        "<|im_end|>\n<|im_start|>user\n"
    )
    _SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    def __init__(
        self,
        model_name: str = DEFAULT_RERANK_MODEL,
        device: str = "cpu",
        max_length: int = 8192,
        instruction: Optional[str] = None,
    ):
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self.instruction = instruction or self.DEFAULT_INSTRUCTION
        self._tokenizer: Optional[AutoTokenizer] = None
        self._model: Optional[AutoModelForCausalLM] = None
        self._prefix_tokens: Optional[List[int]] = None
        self._suffix_tokens: Optional[List[int]] = None
        self._token_true_id: Optional[int] = None
        self._token_false_id: Optional[int] = None

    def _load(self) -> None:
        """懒加载模型和 tokenizer."""
        if self._model is not None:
            return

        _ensure_hf_mirror()
        logger.info(f"Loading Qwen3-Reranker model: {self.model_name} (device={self.device})")

        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            padding_side="left",
            trust_remote_code=True,
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            trust_remote_code=True,
        )
        self._model.eval()
        if self.device != "cpu":
            self._model = self._model.to(self.device)

        # 获取 yes/no token ID
        self._token_true_id = self._tokenizer.convert_tokens_to_ids("yes")
        self._token_false_id = self._tokenizer.convert_tokens_to_ids("no")

        # 预编码 prefix/suffix
        self._prefix_tokens = self._tokenizer.encode(self._PREFIX, add_special_tokens=False)
        self._suffix_tokens = self._tokenizer.encode(self._SUFFIX, add_special_tokens=False)

        logger.info("Qwen3-Reranker model loaded successfully")

    def _format_pair(self, query: str, doc: str, instruction: Optional[str] = None) -> str:
        """格式化 (instruction, query, doc) 为模型输入文本."""
        inst = instruction or self.instruction
        return f"<Instruct>: {inst}\n<Query>: {query}\n<Document>: {doc}"

    def rerank(self, query: str, passages: List[str]) -> List[tuple[int, float]]:
        """对候选文档进行重排序.

        Args:
            query: 用户查询
            passages: 候选文档列表

        Returns:
            [(原始索引, 相关性分数), ...]，按分数降序排列
        """
        if not passages:
            return []

        self._load()
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._prefix_tokens is not None
        assert self._suffix_tokens is not None

        # 1. 构造 prompt 列表
        pairs = [self._format_pair(query, p) for p in passages]

        # 2. Tokenize（先不加 prefix/suffix，以便正确计算截断长度）
        max_content_len = self.max_length - len(self._prefix_tokens) - len(self._suffix_tokens)
        inputs = self._tokenizer(
            pairs,
            padding=False,
            truncation="longest_first",
            return_attention_mask=False,
            max_length=max_content_len,
        )

        # 3. 包裹 prefix + suffix
        for i, ids in enumerate(inputs["input_ids"]):
            inputs["input_ids"][i] = self._prefix_tokens + ids + self._suffix_tokens

        # 4. Pad 到统一长度
        inputs = self._tokenizer.pad(
            inputs,
            padding=True,
            return_tensors="pt",
            max_length=self.max_length,
        )
        for key in inputs:
            inputs[key] = inputs[key].to(self.device)

        # 5. 前向传播，取最后一个 token 的 logits
        with torch.no_grad():
            outputs = self._model(**inputs)
            logits = outputs.logits[:, -1, :]  # [batch_size, vocab_size]

            # 取 yes/no 的 logits
            false_vec = logits[:, self._token_false_id]
            true_vec = logits[:, self._token_true_id]

            # log_softmax 归一化后取 yes 的概率
            batch_scores = torch.stack([false_vec, true_vec], dim=1)  # [batch_size, 2]
            batch_scores = torch.nn.functional.log_softmax(batch_scores, dim=1)
            scores = batch_scores[:, 1].exp().tolist()  # yes 的概率

        # 6. 排序
        indexed = [(i, float(scores[i])) for i in range(len(passages))]
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed
