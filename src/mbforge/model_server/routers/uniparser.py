"""UniParser 代理路由."""

from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from ...utils.exceptions import ConfigError, ValidationError
from ...utils.logger import get_logger
from .health import set_model_status

logger = get_logger(__name__)
router = APIRouter()


# UniParser 客户端（延迟初始化）
_uniparser_client: Any = None


def _get_client() -> Any:
    global _uniparser_client
    if _uniparser_client is None:
        from mbforge.parsers.uniparser.uniparser_client import ParserClient
        from mbforge.parsers.uniparser.uniparser_config import ParserConfig

        host = os.environ.get("UNIPARSER_HOST", "")
        api_key = os.environ.get("UNIPARSER_API_KEY", "")
        if not host or not api_key:
            raise ConfigError("UNIPARSER_HOST or UNIPARSER_API_KEY not set")
        config = ParserConfig(host=host, api_key=api_key)
        _uniparser_client = ParserClient(config)
    return _uniparser_client


@router.post("/parse")
async def parse_pdf(request: Request) -> dict:
    tmp_path = None
    try:
        body = await request.json()
        pdf_base64 = body.get("pdf_base64", "")
        pdf_path = body.get("pdf_path", "")
        sync = body.get("sync", True)
        textual = body.get("textual", 2)
        table = body.get("table", 2)
        equation = body.get("equation", 2)
        chart = body.get("chart", -1)
        figure = body.get("figure", -1)
        expression = body.get("expression", -1)
        molecule = body.get("molecule", 1)

        # 优先使用 pdf_path，否则解码 base64
        if pdf_path and Path(pdf_path).exists():
            target_path = pdf_path
        elif pdf_base64:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(base64.b64decode(pdf_base64))
                tmp_path = f.name
            target_path = tmp_path
        else:
            raise ValidationError("pdf_path or pdf_base64 required")

        client = _get_client()
        result = client.parse_pdf(
            target_path,
            sync=sync,
            textual=textual,
            table=table,
            equation=equation,
            chart=chart,
            figure=figure,
            expression=expression,
            molecule=molecule,
        )
        set_model_status("uniparser", "ready")
        return {
            "status": result.status,
            "token": result.token,
            "raw_data": result.raw_data,
        }
    except (ValidationError, ConfigError):
        raise
    except Exception as e:
        set_model_status("uniparser", "error")
        logger.error(f"UniParser parse failed: {e}", exc_info=True)
        return {"error": str(e)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/result")
async def get_result(request: Request) -> dict:
    try:
        body = await request.json()
        token = body.get("token", "")
        if not token:
            raise ValidationError("token required")

        client = _get_client()
        result = client.get_result(
            token,
            content=body.get("content", True),
            objects=body.get("objects", False),
            pages_dict=body.get("pages_dict", False),
            pages_tree=body.get("pages_tree", False),
            molecule_source=body.get("molecule_source", False),
        )
        set_model_status("uniparser", "ready")
        return result
    except (ValidationError, ConfigError):
        raise
    except Exception as e:
        set_model_status("uniparser", "error")
        logger.error(f"UniParser result failed: {e}", exc_info=True)
        return {"error": str(e)}


@router.post("/formatted")
async def get_formatted(request: Request) -> dict:
    try:
        body = await request.json()
        token = body.get("token", "")
        if not token:
            raise ValidationError("token required")

        client = _get_client()
        result = client.get_formatted(
            token,
            content=body.get("content", True),
            textual=body.get("textual", 4),
            table=body.get("table", 4),
            equation=body.get("equation", 4),
        )
        set_model_status("uniparser", "ready")
        return result
    except (ValidationError, ConfigError):
        raise
    except Exception as e:
        set_model_status("uniparser", "error")
        logger.error(f"UniParser formatted failed: {e}", exc_info=True)
        return {"error": str(e)}


@router.get("/health")
async def uniparser_health() -> dict:
    try:
        client = _get_client()
        result = client.health()
        set_model_status("uniparser", "ready")
        return {"status": "ok", "detail": result}
    except Exception as e:
        set_model_status("uniparser", "error")
        logger.error(f"UniParser health check failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
