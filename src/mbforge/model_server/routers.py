"""Consolidated FastAPI routers for MBForge Model Server."""

from __future__ import annotations

import asyncio
import importlib
import os
import subprocess
import sys
import time
from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mbforge.models.base import run_sync_async
from mbforge.models.embedding import get_embedder
from mbforge.models.rerank import get_reranker
from mbforge.models.vlm import get_vlm
from mbforge.parsers.molecule.mol_image_pipeline import get_moldet
from mbforge.parsers.molecule.molscribe import get_molscribe
from mbforge.core.resource_manager import ResourceManager
from mbforge.utils.helpers import ModelNotAvailableError, ValidationError
from mbforge.utils.helpers import decode_base64_image, decode_base64_to_tempfile
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# Embed
# ============================================================================
embed_router = APIRouter()


@embed_router.post("/embed")
async def embed(request: Request) -> dict[str, Any]:
    trace_id = request.headers.get("X-Trace-Id")
    span_id = request.headers.get("X-Span-Id")
    if trace_id:
        logger.info(f"[trace={trace_id} span={span_id}] embed started")
    try:
        body = await request.json()
        texts = body.get("texts", [])
        if isinstance(texts, str):
            texts = [texts]
        if trace_id:
            logger.info(f"[trace={trace_id} span={span_id}] embedding {len(texts)} texts")
        embedder = get_embedder()
        embeddings = await run_sync_async(embedder.embed, texts)
        set_model_status("embedder", "ready")
        dim = len(embeddings[0]) if embeddings else 0
        if trace_id:
            logger.info(f"[trace={trace_id} span={span_id}] embed done, dim={dim}")
        return {"embeddings": embeddings}
    except Exception as e:
        set_model_status("embedder", "error")
        log_extra = f" trace={trace_id}" if trace_id else ""
        logger.error(f"Embedding failed{log_extra}: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))


# ============================================================================
# Health + Model Status
# ============================================================================
health_router = APIRouter()

_model_status = {
    "embedder": "loading",
    "reranker": "loading",
    "vlm": "loading",
    "uniparser": "loading",
    "moldet": "loading",
}
_resource_cache: dict[str, str] = {}
_resource_cache_time: float = 0.0
_RESOURCE_CACHE_TTL = 60.0
_RETRY_COOLDOWN = 30.0
_last_failure: dict[str, float] = {}


def _should_skip_due_to_cooldown(model_name: str) -> bool:
    last = _last_failure.get(model_name)
    if last is None:
        return False
    return (time.monotonic() - last) < _RETRY_COOLDOWN


def _mark_failure(model_name: str) -> None:
    _last_failure[model_name] = time.monotonic()


def _clear_failure(model_name: str) -> None:
    _last_failure.pop(model_name, None)


def set_model_status(name: str, status: str) -> None:
    _model_status[name] = status
    if status == "ready":
        _clear_failure(name)


@health_router.get("/health")
async def health_check() -> dict[str, Any]:
    # Embedder
    if not _should_skip_due_to_cooldown("embedder"):
        try:
            get_embedder()
            _model_status["embedder"] = "ready"
            _clear_failure("embedder")
        except Exception as e:
            _model_status["embedder"] = "error"
            _mark_failure("embedder")
            logger.debug(f"Embedder health check failed: {e}")

    # Reranker
    if not _should_skip_due_to_cooldown("reranker"):
        try:
            get_reranker()
            _model_status["reranker"] = "ready"
            _clear_failure("reranker")
        except Exception as e:
            _model_status["reranker"] = "error"
            _mark_failure("reranker")
            logger.debug(f"Reranker health check failed: {e}")

    # VLM
    if not _should_skip_due_to_cooldown("vlm"):
        try:
            get_vlm()
            _model_status["vlm"] = "ready"
            _clear_failure("vlm")
        except Exception as e:
            _model_status["vlm"] = "error"
            _mark_failure("vlm")
            logger.debug(f"VLM health check failed: {e}")

    # UniParser
    if not _should_skip_due_to_cooldown("uniparser"):
        try:
            host = os.environ.get("UNIPARSER_HOST", "")
            api_key = os.environ.get("UNIPARSER_API_KEY", "")
            if host and api_key:
                import requests
                resp = requests.get(
                    f"{host.rstrip('/')}/health",
                    headers={"X-API-Key": api_key},
                    timeout=10,
                )
                if resp.ok:
                    _model_status["uniparser"] = "ready"
                    _clear_failure("uniparser")
                else:
                    _model_status["uniparser"] = "error"
                    _mark_failure("uniparser")
            else:
                _model_status["uniparser"] = "error"
        except Exception as e:
            _model_status["uniparser"] = "error"
            _mark_failure("uniparser")
            logger.debug(f"UniParser health check failed: {e}")

    # MolDet
    if not _should_skip_due_to_cooldown("moldet"):
        try:
            pipeline = get_moldet()
            if pipeline and pipeline.is_available():
                _model_status["moldet"] = "ready"
                _clear_failure("moldet")
            else:
                _model_status["moldet"] = "error"
                _mark_failure("moldet")
        except Exception as e:
            _model_status["moldet"] = "error"
            _mark_failure("moldet")
            logger.debug(f"MolDet health check failed: {e}")

    statuses = list(_model_status.values())
    if all(s == "ready" for s in statuses):
        overall = "online"
    elif any(s == "ready" for s in statuses):
        overall = "partial"
    elif any(s == "error" for s in statuses):
        overall = "error"
    else:
        overall = "loading"

    global _resource_cache, _resource_cache_time
    now = time.monotonic()
    if now - _resource_cache_time > _RESOURCE_CACHE_TTL:
        try:
            _resource_cache = {}
            for rid in ResourceManager.catalog:
                res = ResourceManager.check(rid)
                _resource_cache[rid] = res.status.value
            _resource_cache_time = now
        except Exception as e:
            logger.debug(f"Resource status check failed: {e}")

    return {
        "status": overall,
        "models": dict(_model_status),
        "resources": dict(_resource_cache),
        "error": None,
    }


# ============================================================================
# Environment
# ============================================================================
environment_router = APIRouter()


class CapabilityStatus(BaseModel):
    name: str
    available: bool
    version: Optional[str] = None
    description: str
    category: str


class EnvironmentCheckResult(BaseModel):
    python_version: str
    gpu_available: bool
    gpu_name: Optional[str] = None
    gpu_memory_mb: Optional[int] = None
    cuda_version: Optional[str] = None
    capabilities: list[CapabilityStatus]


def _check_package(pkg_name: str) -> tuple[bool, Optional[str]]:
    try:
        m = importlib.import_module(pkg_name)
        ver = getattr(m, '__version__', None)
        return True, ver
    except ImportError:
        return False, None


_ALLOWED_COMMANDS: frozenset[str] = frozenset(["vina", "nvidia-smi"])


def _check_command(cmd: str) -> bool:
    if cmd not in _ALLOWED_COMMANDS:
        raise ValueError(f"Command '{cmd}' is not in the allowed list")
    try:
        subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


@environment_router.get("/check", response_model=EnvironmentCheckResult)
async def check_environment() -> EnvironmentCheckResult:
    capabilities: list[CapabilityStatus] = []
    for pkg, version, desc, cat in [
        ("rdkit", None, "分子信息学: SMILES 解析、分子属性计算", "core"),
        ("numpy", None, "数值计算: 数组运算、线性代数", "core"),
        ("scipy", None, "科学计算: 优化、插值、统计", "core"),
        ("pandas", None, "数据分析: 表格处理", "core"),
    ]:
        available, ver = _check_package(pkg)
        capabilities.append(CapabilityStatus(
            name=pkg, available=available, version=ver, description=desc, category=cat
        ))
    for pkg, desc in [("openmm", "分子动力学模拟 (GPU 加速)")]:
        available, ver = _check_package(pkg)
        capabilities.append(CapabilityStatus(
            name=pkg, available=available, version=ver, description=desc, category="md"
        ))
    for cmd, pkg, desc in [("vina", "autodock_vina", "分子对接 (命令行)")]:
        available = _check_command(cmd)
        _, ver = _check_package(pkg)
        capabilities.append(CapabilityStatus(
            name=cmd, available=available, version=ver, description=desc, category="docking"
        ))
    for pkg, desc in [("deepchem", "深度学习 ADMET 预测")]:
        available, ver = _check_package(pkg)
        capabilities.append(CapabilityStatus(
            name=pkg, available=available, version=ver, description=desc, category="admet"
        ))

    gpu_available = False
    gpu_name = None
    gpu_memory_mb = None
    cuda_version = None
    try:
        import torch
        if torch.cuda.is_available():
            gpu_available = True
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory_mb = int(torch.cuda.get_device_properties(0).total_memory / 1024 / 1024)
            cuda_version = torch.version.cuda
    except ImportError:
        pass
    if not gpu_available:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(',')
                if parts:
                    gpu_available = True
                    gpu_name = parts[0].strip()
                    if len(parts) > 1:
                        mem_str = parts[1].strip().replace(' MiB', '').replace('MiB', '').strip()
                        try:
                            gpu_memory_mb = int(mem_str)
                        except ValueError:
                            pass
                    if len(parts) > 2:
                        cuda_version = parts[2].strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

    return EnvironmentCheckResult(
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        gpu_memory_mb=gpu_memory_mb,
        cuda_version=cuda_version,
        capabilities=capabilities,
    )


# ============================================================================
# MolDet
# ============================================================================
moldet_router = APIRouter()


@moldet_router.post("/detect-page")
async def detect_page(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        if not image_base64:
            raise ValidationError("image_base64 is required")
        image = decode_base64_image(image_base64)
        pipeline = get_moldet()
        if pipeline is None or not pipeline.is_available():
            raise ModelNotAvailableError("MolDet pipeline not available")
        loop = asyncio.get_running_loop()
        boxes = await loop.run_in_executor(None, lambda: pipeline.doc_detector.detect(image))
        set_model_status("moldet", "ready")
        return {
            "boxes": [{"x1": x1, "y1": y1, "x2": x2, "y2": y2, "conf": conf} for x1, y1, x2, y2, conf in boxes],
            "count": len(boxes),
        }
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("moldet", "error")
        logger.error(f"MolDet detect-page failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))


@moldet_router.post("/extract-page")
async def extract_page(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        if not image_base64:
            raise ValidationError("image_base64 is required")
        page_idx = body.get("page_idx", 0)
        page_w_pts = body.get("page_w_pts", 595.0)
        page_h_pts = body.get("page_h_pts", 842.0)
        image_w = body.get("image_w", 0)
        image_h = body.get("image_h", 0)
        dpi = body.get("dpi", 300.0)
        if image_w == 0 or image_h == 0:
            raise ValidationError("image_w and image_h are required")
        image = decode_base64_image(image_base64)
        pipeline = get_moldet()
        if pipeline is None or not pipeline.is_available():
            raise ModelNotAvailableError("MolDet pipeline not available")
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, lambda: pipeline.extract_page(image, page_idx, page_w_pts, page_h_pts, image_w, image_h, dpi)
        )
        set_model_status("moldet", "ready")
        return {"results": [r.to_dict() for r in results], "count": len(results)}
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("moldet", "error")
        logger.error(f"MolDet extract-page failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))


# ============================================================================
# VLM
# ============================================================================
vlm_router = APIRouter()


@vlm_router.post("/describe")
async def describe(request: Request) -> dict[str, Any]:
    tmp_path = None
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        prompt = body.get("prompt", "")
        if not image_base64:
            raise ValidationError("image_base64 is required")
        ext = body.get("ext", "png")
        tmp_path = decode_base64_to_tempfile(image_base64, ext)
        vlm = get_vlm()
        description = await run_sync_async(vlm.describe_image, tmp_path, prompt=prompt)
        set_model_status("vlm", "ready")
        return {"description": description}
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("vlm", "error")
        logger.error(f"VLM describe failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@vlm_router.post("/molscribe")
async def molscribe(request: Request) -> dict[str, Any]:
    tmp_path = None
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        if not image_base64:
            raise ValidationError("image_base64 is required")
        ext = body.get("ext", "png")
        tmp_path = decode_base64_to_tempfile(image_base64, ext)
        from PIL import Image
        image = Image.open(tmp_path)
        model = get_molscribe()
        if not model.is_available:
            raise ModelNotAvailableError(f"MolScribe not available: {model.error}")
        result = await run_sync_async(model.predict, image)
        set_model_status("vlm", "ready")
        return {
            "esmiles": result.esmiles,
            "confidence": result.confidence,
            "success": result.success and bool(result.esmiles),
        }
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("vlm", "error")
        logger.error(f"MolScribe predict failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
