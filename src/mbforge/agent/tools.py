"""工具注册与定义.

使用方式:
    @tool("搜索知识库", {"query": {"type": "string", "description": "搜索关键词"}})
    def search_kb(query: str) -> str:
        return "结果..."
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)


class ToolInfo:
    """工具元信息."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters_schema: Dict[str, Any],
        func: Callable,
    ):
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema
        self.func = func

    def to_openai_schema(self) -> Dict[str, Any]:
        """生成 OpenAI function calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                    "required": list(self.parameters_schema.keys()),
                },
            },
        }


class ToolRegistry:
    """工具注册表."""

    def __init__(self):
        self._tools: Dict[str, ToolInfo] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters_schema: Dict[str, Any],
        func: Callable,
    ) -> ToolInfo:
        """注册工具."""
        info = ToolInfo(name, description, parameters_schema, func)
        self._tools[name] = info
        logger.info(f"Tool registered: {name}")
        return info

    def get(self, name: str) -> Optional[ToolInfo]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolInfo]:
        return list(self._tools.values())

    def to_openai_schemas(self) -> List[Dict[str, Any]]:
        """导出所有工具的 OpenAI schema."""
        return [t.to_openai_schema() for t in self._tools.values()]

    def call(self, name: str, arguments: Dict[str, Any]) -> str:
        """调用工具."""
        info = self._tools.get(name)
        if info is None:
            return f"错误: 工具 '{name}' 不存在"
        try:
            result = info.func(**arguments)
            return str(result) if result is not None else ""
        except Exception as e:
            logger.exception(f"Tool execution failed: {name}")
            return f"工具执行错误: {e}"


def tool(description: str, parameters: Optional[Dict[str, Any]] = None):
    """工具装饰器.

    Args:
        description: 工具功能描述
        parameters: 参数 schema，如 {"query": {"type": "string"}}

    使用示例:
        registry = ToolRegistry()

        @tool("搜索知识库", {"query": {"type": "string", "description": "关键词"}})
        def search_kb(query: str) -> str:
            return "result"

        registry.register_tool(search_kb)
    """
    def decorator(func: Callable) -> Callable:
        func._tool_description = description
        func._tool_parameters = parameters or {}
        return func
    return decorator


class ToolMixin:
    """供函数使用的工具注册混入.

    使用方式:
        @tool("搜索")
        def search(query: str) -> str: ...

        registry = ToolRegistry()
        registry.register_from_function(search)
    """

    @staticmethod
    def register_from_function(registry: ToolRegistry, func: Callable) -> ToolInfo:
        """从被 @tool 装饰的函数注册."""
        desc = getattr(func, "_tool_description", func.__doc__ or "")
        params = getattr(func, "_tool_parameters", {})
        name = func.__name__
        return registry.register(name, desc, params, func)
