"""UniParser 客户端封装."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union

from uniparser_tools.api.clients import UniParserClient as UniParserClientBase
from uniparser_tools.common.constant import ParseMode, ParseModeTextual

from .config import ParserConfig
from .models import ParseResult


class ParserClient:
    """UniParser 客户端封装."""

    def __init__(self, config: ParserConfig):
        self.config = config
        self._client = UniParserClientBase(
            host=config.host,
            api_key=config.api_key,
        )

    def parse_pdf(
        self,
        pdf_path: Union[str, Path],
        *,
        sync: bool = True,
        textual: Union[ParseModeTextual, bool] = ParseModeTextual.DigitalExported,
        table: Union[ParseMode, bool] = ParseMode.Disable,
        molecule: Union[ParseMode, bool] = ParseMode.Disable,
        figure: Union[ParseMode, bool] = ParseMode.Disable,
        **kwargs,
    ) -> ParseResult:
        """解析 PDF 文件."""
        pdf_path = str(Path(pdf_path).resolve())

        response = self._client.trigger_file(
            file_path=pdf_path,
            sync=sync,
            textual=textual,
            table=table,
            molecule=molecule,
            figure=figure,
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
        """获取解析结果."""
        return self._client.get_result(
            token=token,
            content=content,
            objects=objects,
            pages_dict=pages_dict,
            pages_tree=pages_tree,
            molecule_source=molecule_source,
        )

    def parse_and_wait(
        self,
        pdf_path: Union[str, Path],
        *,
        timeout: int = 300,
        poll_interval: int = 2,
        **kwargs,
    ) -> ParseResult:
        """同步解析 PDF，等待完成."""
        import time

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
