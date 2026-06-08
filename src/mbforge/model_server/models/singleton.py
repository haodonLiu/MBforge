"""泛型模型单例工厂 — 消除 get_*/reset_* 重复模板."""

from __future__ import annotations

import logging
from typing import TypeVar, Generic, Callable, Any

T = TypeVar("T")
logger = logging.getLogger("mbforge.singleton")

# 全局注册表：所有已创建的 ModelSingleton 实例。
# Phase 3 用于优雅退出时统一调用每个实例的 close 钩子。
_REGISTRY: list["ModelSingleton[Any]"] = []


class ModelSingleton(Generic[T]):
    """懒加载单例，支持可选 config 参数。

    用法:
        _llm = ModelSingleton(BaseLLM, lambda cfg: cfg.llm, create_llm_from_config)
        get_llm = _llm.get
        reset_llm = _llm.reset
    """

    def __init__(
        self,
        base_type: type[T],
        config_accessor: Callable[[Any], Any],
        factory: Callable[[Any], T],
        on_close: Callable[[T], None] | None = None,
    ) -> None:
        self._base_type = base_type
        self._config_accessor = config_accessor
        self._factory = factory
        self._on_close = on_close
        self._instance: T | None = None
        _REGISTRY.append(self)

    def get(self, config: Any | None = None) -> T:
        if self._instance is None:
            if config is None:
                from mbforge.utils.config import load_global_config
                config = self._config_accessor(load_global_config())
            self._instance = self._factory(config)
        return self._instance

    def reset(self) -> None:
        if self._on_close and self._instance is not None:
            try:
                self._on_close(self._instance)
            except Exception as e:
                logger.warning(f"on_close hook failed: {e}")
        self._instance = None


async def close_all_singletons() -> None:
    """Phase 3 优雅退出：调用所有已注册 singleton 的 on_close 钩子并重置。

    每个 model 可选地提供 `on_close(instance)` 异步或同步函数，
    用于关闭 httpx client、释放 GPU 上下文等。
    """
    for singleton in _REGISTRY:
        if singleton._instance is not None and singleton._on_close is not None:
            try:
                singleton._on_close(singleton._instance)
            except Exception as e:
                logger.warning(f"Singleton close failed: {e}")
        singleton._instance = None
    logger.info(f"Closed {len(_REGISTRY)} registered singletons")

