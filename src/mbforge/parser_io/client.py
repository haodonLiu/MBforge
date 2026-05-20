"""UniParser 客户端封装.

对 UniParser-Tools 的 UniParserClient 进行封装，提供简化的接口，
用于 PDF 解析和结果获取。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Union

try:
    from uniparser_tools.api.clients import UniParserClient as UniParserClientBase
    from uniparser_tools.common.constant import ParseMode, ParseModeTextual
    _UNIPARSER_AVAILABLE = True
except ImportError:
    UniParserClientBase = None  # type: ignore
    ParseMode = None  # type: ignore
    ParseModeTextual = None  # type: ignore
    _UNIPARSER_AVAILABLE = False

from .config import ParserConfig
from .models import ParseResult


class ParserClient:
    """UniParser 客户端封装.

    提供简化的接口来解析 PDF 文件并获取结果。

    Example:
        >>> config = load_config()
        >>> client = ParserClient(config)
        >>> result = client.parse_pdf("document.pdf")
        >>> print(f"Token: {result.token}")
    """

    def __init__(self, config: ParserConfig):
        self.config = config
        if UniParserClientBase is None:
            raise ImportError(
                "UniParser-Tools is not installed. "
                "Please install it with: pip install uniparser-tools"
            )
        self._client = UniParserClientBase(
            host=config.host,
            api_key=config.api_key,
        )

    def parse_pdf(
        self,
        pdf_path: Union[str, Path],
        *,
        sync: bool = True,
        textual: int = 2,  # ParseModeTextual.OCRHighQuality
        table: int = 2,    # ParseMode.OCRHighQuality
        equation: int = 2, # ParseMode.OCRHighQuality
        chart: int = -1,   # ParseMode.DumpBase64
        figure: int = -1,  # ParseMode.DumpBase64
        expression: int = -1,  # ParseMode.DumpBase64
        molecule: int = 1, # ParseMode.OCRFast
        **kwargs,
    ) -> ParseResult:
        """解析 PDF 文件.

        默认使用科学文献推荐配置：高质 OCR 文本/表格/公式，快速分子识别。

        Args:
            pdf_path: PDF 文件路径
            sync: 是否同步等待解析完成
            textual: 文本解析模式
            table: 表格解析模式
            equation: 公式解析模式
            chart: 图表解析模式
            figure: 图片解析模式
            expression: 化学反应式解析模式
            molecule: 分子结构解析模式
            **kwargs: 其他参数（如 callback_url）

        Returns:
            ParseResult 对象
        """
        pdf_path = str(Path(pdf_path).resolve())

        response = self._client.trigger_file(
            file_path=pdf_path,
            sync=sync,
            textual=textual,
            table=table,
            equation=equation,
            chart=chart,
            figure=figure,
            expression=expression,
            molecule=molecule,
            **kwargs,
        )

        return ParseResult(
            status=response.get("status", "unknown"),
            token=response.get("token", ""),
            raw_data=response,
        )

    def get_result(
        self,
        token: str,
        *,
        content: bool = True,
        objects: bool = False,
        pages_dict: bool = False,
        pages_tree: bool = False,
        molecule_source: bool = False,
    ) -> Dict[str, Any]:
        """获取解析结果.

        Args:
            token: parse_pdf 返回的 token
            content: 是否返回文档文本内容
            objects: 是否返回语义对象列表
            pages_dict: 是否返回每页原始布局字典
            pages_tree: 是否返回嵌套树结构
            molecule_source: 是否包含分子 SMILES 源

        Returns:
            解析结果字典
        """
        return self._client.get_result(
            token=token,
            content=content,
            objects=objects,
            pages_dict=pages_dict,
            pages_tree=pages_tree,
            molecule_source=molecule_source,
        )

    def get_formatted(
        self,
        token: str,
        *,
        content: bool = True,
        textual: int = 4,  # FormatFlag.Markdown
        table: int = 4,
        equation: int = 4,
    ) -> Dict[str, Any]:
        """获取格式化结果.

        Args:
            token: parse_pdf 返回的 token
            content: 是否返回格式化文本
            textual: 文本格式（4=Markdown）
            table: 表格格式（4=Markdown）
            equation: 公式格式（4=Markdown）

        Returns:
            格式化结果字典
        """
        return self._client.get_formatted(
            token=token,
            content=content,
            textual=textual,
            table=table,
            equation=equation,
        )

    def parse_and_wait(
        self,
        pdf_path: Union[str, Path],
        *,
        timeout: int = 300,
        poll_interval: int = 2,
        **kwargs,
    ) -> ParseResult:
        """异步解析 PDF 并等待完成.

        发送异步解析请求后，轮询直到完成或超时。

        Args:
            pdf_path: PDF 文件路径
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）
            **kwargs: 传递给 parse_pdf 的其他参数

        Returns:
            ParseResult 对象

        Raises:
            TimeoutError: 解析超时
        """
        result = self.parse_pdf(pdf_path, sync=False, **kwargs)

        elapsed = 0
        while elapsed < timeout:
            response = self._client.get_result(token=result.token, content=True)

            if response.get("status") == "completed":
                result.raw_data = response
                return result

            time.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Parsing timed out after {timeout} seconds")

    def health(self) -> Dict[str, Any]:
        """检查服务健康状态."""
        return self._client.health()

    def version(self) -> Dict[str, Any]:
        """获取服务版本信息."""
        return self._client.version()
