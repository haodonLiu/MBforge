"""Embedding 模型实现."""

from __future__ import annotations

import os

from .base import BaseEmbedder, run_sync_async
from ..utils.constants import (
    DEFAULT_EMBED_MODEL,
    EMBED_INSTRUCTION_RETRIEVAL,
    EMBED_INSTRUCTION_CLUSTER,
    PROVIDER_SENTENCE_TRANSFORMERS,
    PROVIDER_QWEN3,
    ensure_hf_mirror,
)
from ..utils.helpers import get_default_device
from ..utils.logger import get_logger

logger = get_logger(__name__)


def _resolve_model_path(model_name: str, cache_name: str) -> str:
    """解析模型路径，按优先级搜索多个缓存目录.

    搜索顺序（与 Rust resource_manager.rs check_model_snapshot 对齐）:
    1. 绝对/相对路径 → 直接用
    2. MBForge 缓存目录
    3. ModelScope 缓存（$MODELSCOPE_CACHE + 默认路径）
    4. HuggingFace 缓存（$HF_HOME）
    5. 找不到 → 返回原名（走 HuggingFace 下载）
    """
    from pathlib import Path

    # 已经是本地路径
    p = Path(model_name)
    if p.is_absolute() or (p.exists() and p.is_dir()):
        return model_name

    # 从 model_name 提取匹配用的 key
    # "Qwen/Qwen3-Embedding-0.6B" → key_name = "Qwen3-Embedding-0"
    name_parts = cache_name.replace("/", " ").split()
    last_part = name_parts[-1] if name_parts else cache_name
    key_name = last_part.rsplit(".", 1)[0]

    # org 名（用于 ModelScope 目录结构 <org>/<model>）
    org = cache_name.split("/")[0] if "/" in cache_name else ""

    # 构建搜索目录列表（与 Rust resource_manager.rs 对齐）
    search_dirs = []

    # ① MBForge 缓存
    try:
        from ..utils.constants import get_model_cache_dir
        mbforge_dir = Path(get_model_cache_dir())
        if mbforge_dir.exists():
            search_dirs.append(mbforge_dir)
    except ImportError:
        pass

    # ② ModelScope 缓存
    ms_cache = os.environ.get("MODELSCOPE_CACHE", "")
    if ms_cache:
        search_dirs.append(Path(ms_cache))
    search_dirs.append(Path.home() / "Models" / "ModelScope")
    search_dirs.append(Path.home() / ".cache" / "modelscope")

    # ③ HuggingFace 缓存
    hf_home = os.environ.get("HF_HOME", "")
    if hf_home:
        search_dirs.append(Path(hf_home))

    # 在每个搜索目录中查找
    for cache_dir in search_dirs:
        if not cache_dir.exists():
            continue

        # ModelScope 布局: <cache>/<org>/<name>___<version>/
        # 也可能直接在 <cache>/<name>/ 下
        candidates = []
        if org:
            candidates.append(cache_dir / org)
        candidates.append(cache_dir)

        for base in candidates:
            if not base.exists():
                continue
            for item in base.iterdir():
                if item.is_dir() and key_name.lower() in item.name.lower():
                    # 确认目录里有权重文件
                    has_weights = (
                        any(item.glob("*.safetensors"))
                        or any(item.glob("*.bin"))
                        or any(item.glob("*.pt"))
                        or any(item.glob("*.pth"))
                    )
                    if has_weights:
                        logger.info(f"Found model in cache: {item}")
                        return str(item)

        # HF 布局: hub/models--<org>--<name>/snapshots/<commit>/
        if org:
            hf_encoded = f"models--{org}--{last_part}"
            snapshots = cache_dir / "hub" / hf_encoded / "snapshots"
            if snapshots.exists():
                for snap in snapshots.iterdir():
                    if snap.is_dir() and any(snap.glob("*.safetensors")):
                        logger.info(f"Found model in HF cache: {snap}")
                        return str(snap)

    return model_name


class SentenceTransformerEmbedder(BaseEmbedder):
    """基于 sentence-transformers 的本地 Embedding.

    兼容 BGE、GTE 等 sentence-transformers 格式模型。
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", device: str | None = None):
        self.model_name = model_name
        self.device = device or get_default_device()
        self._model = None
        self._dim = None

    def _load_model(self):
        if self._model is None:
            ensure_hf_mirror()
            from sentence_transformers import SentenceTransformer

            resolved = _resolve_model_path(self.model_name, self.model_name)
            self._model = SentenceTransformer(
                resolved, device=self.device, trust_remote_code=True
            )
            self._dim = self._model.get_embedding_dimension()
        return self._model

    @property
    def dim(self) -> int:
        self._load_model()
        return self._dim or 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        embeddings = model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return embeddings.tolist()

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        return await run_sync_async(self.embed, texts)


class Qwen3Embedder(BaseEmbedder):
    """基于 Qwen3-Embedding 的本地 Embedding.

    支持 Instruction Aware（不同任务前缀）和 MRL（Matryoshka Representation Learning）。

    模型规格:
        - Qwen/Qwen3-Embedding-0.6B: 768-dim, 32K context, 100+ 语言
        - 支持 MRL: 可输出 768/512/256/128/64 维子向量
        - 支持 Instruction Aware: 检索/聚类/分类等任务前缀

    使用示例:
        >>> embedder = Qwen3Embedder(device="cuda")
        >>> embeddings = embedder.embed(["化合物 A 的活性如何？"])
        >>> len(embeddings[0])
        768
    """

    # 任务指令前缀（必须添加以获得最佳检索效果）
    INSTRUCTION_RETRIEVAL = EMBED_INSTRUCTION_RETRIEVAL
    INSTRUCTION_CLUSTER = EMBED_INSTRUCTION_CLUSTER
    INSTRUCTION_CLASSIFICATION = "Classify the user query."

    def __init__(
        self,
        model_name: str = DEFAULT_EMBED_MODEL,
        device: str | None = None,
        mrl_dim: int | None = None,
        instruction: str | None = None,
    ):
        self.model_name = model_name
        self.device = device or get_default_device()
        self.mrl_dim = mrl_dim  # MRL 输出维度，如 256
        self.instruction = instruction or self.INSTRUCTION_RETRIEVAL
        self._model = None
        self._dim = None

    def _load_model(self):
        if self._model is None:
            ensure_hf_mirror()
            from sentence_transformers import SentenceTransformer

            resolved = _resolve_model_path(self.model_name, self.model_name)
            logger.info(
                f"Loading Qwen3-Embedding model: {resolved} (device={self.device})"
            )
            self._model = SentenceTransformer(
                resolved,
                device=self.device,
                trust_remote_code=True,
            )
            full_dim = self._model.get_embedding_dimension()
            self._dim = (
                self.mrl_dim if (self.mrl_dim and self.mrl_dim < full_dim) else full_dim
            )
            logger.info(f"Model loaded. Full dim={full_dim}, output dim={self._dim}")
        return self._model

    @property
    def dim(self) -> int:
        self._load_model()
        return self._dim or 768

    def embed(self, texts: list[str]) -> list[list[float]]:
        """编码文本，自动添加 instruction 前缀."""
        model = self._load_model()
        # 为每个文本添加 instruction 前缀
        prefixed = [f"{self.instruction}\n{t}" for t in texts]
        embeddings = model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        # MRL: 截取指定维度
        if self.mrl_dim and self.mrl_dim < embeddings.shape[1]:
            embeddings = embeddings[:, : self.mrl_dim]
        return embeddings.tolist()

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        return await run_sync_async(self.embed, texts)


class APIEmbedder(BaseEmbedder):
    """通过 API 调用的 Embedding（OpenAI 兼容格式）."""

    def __init__(self, base_url: str, api_key: str, model_name: str = ""):
        import openai

        self.client = openai.OpenAI(base_url=base_url, api_key=api_key or "empty")
        self.model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model_name,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        return await run_sync_async(self.embed, texts)


def create_embedder_from_config(config) -> BaseEmbedder:
    """从配置创建 Embedder 实例."""
    from ..utils.config import EmbedConfig
    from ..utils.constants import PROVIDER_API

    cfg: EmbedConfig = config

    if cfg.provider == PROVIDER_QWEN3:
        mrl = cfg.mrl_dim if cfg.mrl_dim else None
        return Qwen3Embedder(
            model_name=cfg.model_name,
            device=cfg.device,
            mrl_dim=mrl,
            instruction=cfg.instruction or None,
        )
    elif cfg.provider == PROVIDER_SENTENCE_TRANSFORMERS:
        return SentenceTransformerEmbedder(model_name=cfg.model_name, device=cfg.device)
    elif cfg.provider in ("openai", PROVIDER_API):
        return APIEmbedder(
            base_url=cfg.base_url, api_key=cfg.api_key, model_name=cfg.model_name
        )
    else:
        # fallback to Qwen3
        return Qwen3Embedder(model_name=cfg.model_name, device=cfg.device)
