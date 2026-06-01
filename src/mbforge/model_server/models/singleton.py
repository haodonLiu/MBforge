"""泛型模型单例工厂 — 消除 get_*/reset_* 重复模板."""

from __future__ import annotations

from typing import TypeVar, Generic, Callable, Any

T = TypeVar("T")


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
    ) -> None:
        self._base_type = base_type
        self._config_accessor = config_accessor
        self._factory = factory
        self._instance: T | None = None

    def get(self, config: Any | None = None) -> T:
        if self._instance is None:
            if config is None:
                from mbforge.utils.config import load_global_config
                config = self._config_accessor(load_global_config())
            self._instance = self._factory(config)
        return self._instance

    def reset(self) -> None:
        self._instance = None
