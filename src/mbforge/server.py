"""MBForge Model Server — FastAPI app with fixed local model backends.

Python sidecar hosts only five fixed local models:
    - Qwen3-Embedding   (backends.qwen3_embed)
    - Qwen3-Reranker    (backends.qwen3_rerank)
    - MolScribe         (backends.molscribe)
    - MolDet            (backends.moldet)
    - MolDet Coref      (backends.moldet_coref)

All API-based models (OpenAI, Anthropic, etc.) are called directly from Rust.
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import logging
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import fitz

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .backends import moldet, moldet_coref, molscribe, qwen3_embed, qwen3_rerank
from .core.resource_manager import ResourceManager
from .utils.helpers import (
    ModelNotAvailableError,
    ValidationError,
    decode_base64_image,
    decode_base64_to_tempfile,
)
from .utils.logger import get_logger

logger = get_logger("mbforge.server")

# ---------------------------------------------------------------------------
# Backend registry — add a new backend here to register it for lifespan
# ---------------------------------------------------------------------------
_BACKENDS = [qwen3_embed, qwen3_rerank, molscribe, moldet, moldet_coref]


def _prewarm() -> None:
    for mod in _BACKENDS:
        try:
            mod.load()
            logger.info(f"{mod.__name__} prewarmed")
        except Exception as e:
            logger.warning(f"{mod.__name__} prewarm failed: {e}")


def _check_environment() -> None:
    try:
        report = ResourceManager.check_all()
        logger.info(f"Environment check: {report.summary}")
        for r in report.resources:
            icon = "✓" if r.status.value == "ready" else "✗"
            logger.info(f"  {icon} {r.name}: {r.status.value}")
    except Exception as e:
        logger.warning(f"Environment check failed: {e}")


def _shutdown() -> None:
    for mod in _BACKENDS:
        try:
            mod.unload()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _check_environment)
    loop.run_in_executor(None, _prewarm)
    try:
        yield
    finally:
        _shutdown()
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
        if pending:
            for t in pending:
                t.cancel()
            await asyncio.wait(pending, timeout=1.0)
        logger.info("Sidecar shutdown complete")


app = FastAPI(title="MBForge Model Server", version="1.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(ModelNotAvailableError)
async def _model_error_handler(request: Request, exc: ModelNotAvailableError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.message, "error_code": exc.error_code},
    )


@app.exception_handler(Exception)
async def _generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": str(exc), "error_code": "internal_error"},
    )


# ---------------------------------------------------------------------------
# PDF rendering (PyMuPDF page images for MoldDet)
# ---------------------------------------------------------------------------

def _render_pages_sync(pdf_path: str, page_numbers: list[int], dpi: float) -> list[dict[str, Any]]:
    """Render selected pages of a PDF to base64-encoded PNG images using PyMuPDF."""
    doc = fitz.open(pdf_path)
    try:
        screenshots: list[dict[str, Any]] = []
        for page_num in page_numbers:
            page_index = int(page_num) - 1  # 1-based to 0-based
            if page_index < 0 or page_index >= doc.page_count:
                logger.warning(f"Invalid page number {page_num} for {pdf_path}")
                continue
            page = doc.load_page(page_index)
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            encoded = base64.b64encode(img_bytes).decode("utf-8")
            screenshots.append({
                "page_num": int(page_num),
                "width": pix.width,
                "height": pix.height,
                "image_base64": encoded,
            })
        return screenshots
    finally:
        doc.close()


@app.post("/api/v1/pdf/render-pages")
async def render_pages(request: Request) -> dict[str, Any]:
    """Render selected PDF pages to PNG images.

    Request body:
        - pdf_path: absolute path to the PDF file
        - page_numbers: list of 1-based page numbers to render
        - dpi: rendering DPI (default 300)

    Returns:
        - screenshots: list of {page_num, width, height, image_base64}
        - count: number of screenshots returned
    """
    pdf_path = ""
    try:
        body = await request.json()
        pdf_path = body.get("pdf_path", "")
        page_numbers = body.get("page_numbers", [])
        dpi = body.get("dpi", 300.0)
        if not pdf_path:
            raise ValidationError("pdf_path is required")
        if not isinstance(page_numbers, list) or not page_numbers:
            raise ValidationError("page_numbers must be a non-empty list")
        if not Path(pdf_path).exists():
            raise ValidationError(f"PDF not found: {pdf_path}")
        loop = asyncio.get_running_loop()
        screenshots = await loop.run_in_executor(
            None, lambda: _render_pages_sync(pdf_path, page_numbers, dpi)
        )
        return {"screenshots": screenshots, "count": len(screenshots)}
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        logger.error(f"PDF render failed for {pdf_path}: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))


# ---------------------------------------------------------------------------
# Embed
# ---------------------------------------------------------------------------
@app.post("/api/v1/embed")
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
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(None, lambda: qwen3_embed.embed(texts))
        set_model_status("embedder", "ready")
        dim = len(embeddings[0]) if embeddings else 0
        if trace_id:
            logger.info(f"[trace={trace_id} span={span_id}] embed done, dim={dim}")
        return {"embeddings": embeddings}
    except Exception as e:
        set_model_status("embedder", "error")
        raise ModelNotAvailableError(str(e))


# ---------------------------------------------------------------------------
# Rerank
# ---------------------------------------------------------------------------
@app.post("/api/v1/rerank")
async def rerank(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        query = body.get("query", "")
        passages = body.get("passages", [])
        if not query or not passages:
            raise ValidationError("query and passages are required")
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, lambda: qwen3_rerank.rerank(query, passages)
        )
        set_model_status("reranker", "ready")
        return {"results": [{"index": i, "score": s} for i, s in results]}
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("reranker", "error")
        raise ModelNotAvailableError(str(e))


# ---------------------------------------------------------------------------
# MolDet
# ---------------------------------------------------------------------------
@app.post("/api/v1/moldet/detect-page")
async def detect_page(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        if not image_base64:
            raise ValidationError("image_base64 is required")
        image = decode_base64_image(image_base64)
        pipeline = moldet.get_moldet()
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
        raise ModelNotAvailableError(str(e))


@app.post("/api/v1/moldet/detect-batch")
async def detect_batch(request: Request) -> dict[str, Any]:
    """批量检测多页图像中的分子 bbox.

    请求体：
        - image_base64_list: base64 编码的图像列表

    返回：
        - results: 每页的检测结果列表，每项包含 page_index、boxes、count
        - total: 输入图像总数
    """
    try:
        body = await request.json()
        image_base64_list = body.get("image_base64_list", [])
        if not isinstance(image_base64_list, list) or not image_base64_list:
            raise ValidationError("image_base64_list must be a non-empty list")
        images = [decode_base64_image(b64) for b64 in image_base64_list]
        pipeline = moldet.get_moldet()
        if pipeline is None or not pipeline.is_available():
            raise ModelNotAvailableError("MolDet pipeline not available")
        loop = asyncio.get_running_loop()
        batch_boxes = await loop.run_in_executor(
            None, lambda: pipeline.doc_detector.detect_batch(images)
        )
        set_model_status("moldet", "ready")
        return {
            "results": [
                {
                    "page_index": i,
                    "boxes": [
                        {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "conf": conf}
                        for x1, y1, x2, y2, conf in boxes
                    ],
                    "count": len(boxes),
                }
                for i, boxes in enumerate(batch_boxes)
            ],
            "total": len(batch_boxes),
        }
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("moldet", "error")
        raise ModelNotAvailableError(str(e))


@app.post("/api/v1/moldet/extract-page")
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
        pipeline = moldet.get_moldet()
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
        raise ModelNotAvailableError(str(e))


# ---------------------------------------------------------------------------
# MolDetect Coref
# ---------------------------------------------------------------------------
@app.post("/api/v1/moldet/coref")
async def detect_coref(request: Request) -> dict[str, Any]:
    """检测分子和标识符的共指关系.

    请求体：
        - image_base64: base64 编码的图像
        - mol_bboxes: MolDetv2 检测到的分子 bbox 列表（可选）
          格式: [{"x1": 100, "y1": 200, "x2": 300, "y2": 400}, ...]

    响应：
        - corefs: 共指对列表 [{mol_idx, idt_bbox}, ...]
          mol_idx: 对应输入 mol_bboxes 的索引
          idt_bbox: 标识符的归一化坐标
    """
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        if not image_base64:
            raise ValidationError("image_base64 is required")
        mol_bboxes = body.get("mol_bboxes", [])

        image = decode_base64_image(image_base64)
        backend = moldet_coref.get_coref()
        if backend is None or not backend.is_available():
            raise ModelNotAvailableError("MolDetect coref backend not available")

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: backend.detect_coref_with_mapping(
                image,
                mol_bboxes=mol_bboxes,
            ),
        )
        set_model_status("moldet_coref", "ready")
        return result
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("moldet_coref", "error")
        raise ModelNotAvailableError(str(e))


# ---------------------------------------------------------------------------
# MolScribe
# ---------------------------------------------------------------------------
@app.post("/api/v1/molscribe")
async def molscribe_predict(request: Request) -> dict[str, Any]:
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
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: molscribe.predict(image))
        if not result.success:
            raise ModelNotAvailableError(f"MolScribe not available: {result.error}")
        return {
            "esmiles": result.esmiles,
            "confidence": result.confidence,
            "success": bool(result.esmiles),
        }
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        raise ModelNotAvailableError(str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# ---------------------------------------------------------------------------
# Health + Circuit Breaker
# ---------------------------------------------------------------------------
_model_status = {
    "embedder": "loading",
    "reranker": "loading",
    "moldet": "loading",
    "moldet_coref": "loading",
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


@app.get("/api/v1/health")
async def health_check() -> dict[str, Any]:
    # Embedder
    if not _should_skip_due_to_cooldown("embedder"):
        try:
            qwen3_embed.load()
            _model_status["embedder"] = "ready"
            _clear_failure("embedder")
        except Exception as e:
            _model_status["embedder"] = "error"
            _mark_failure("embedder")
            logger.debug(f"Embedder health check failed: {e}")

    # Reranker
    if not _should_skip_due_to_cooldown("reranker"):
        try:
            qwen3_rerank.load()
            _model_status["reranker"] = "ready"
            _clear_failure("reranker")
        except Exception as e:
            _model_status["reranker"] = "error"
            _mark_failure("reranker")
            logger.debug(f"Reranker health check failed: {e}")

    # MolDet
    if not _should_skip_due_to_cooldown("moldet"):
        try:
            pipeline = moldet.get_moldet()
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

    # MolDet Coref
    if not _should_skip_due_to_cooldown("moldet_coref"):
        try:
            backend = moldet_coref.get_coref()
            if backend and backend.is_available():
                _model_status["moldet_coref"] = "ready"
                _clear_failure("moldet_coref")
            else:
                _model_status["moldet_coref"] = "error"
                _mark_failure("moldet_coref")
        except Exception as e:
            _model_status["moldet_coref"] = "error"
            _mark_failure("moldet_coref")
            logger.debug(f"MolDet coref health check failed: {e}")

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


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
class _CapabilityStatus(BaseModel):
    name: str
    available: bool
    version: Optional[str] = None
    description: str
    category: str


class _EnvironmentCheckResult(BaseModel):
    python_version: str
    gpu_available: bool
    gpu_name: Optional[str] = None
    gpu_memory_mb: Optional[int] = None
    cuda_version: Optional[str] = None
    capabilities: list[_CapabilityStatus]


def _check_package(pkg_name: str) -> tuple[bool, Optional[str]]:
    try:
        m = importlib.import_module(pkg_name)
        ver = getattr(m, "__version__", None)
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


@app.get("/api/v1/environment/check", response_model=_EnvironmentCheckResult)
async def check_environment() -> _EnvironmentCheckResult:
    capabilities: list[_CapabilityStatus] = []
    for pkg, version, desc, cat in [
        ("rdkit", None, "分子信息学: SMILES 解析、分子属性计算", "core"),
        ("numpy", None, "数值计算: 数组运算、线性代数", "core"),
        ("scipy", None, "科学计算: 优化、插值、统计", "core"),
        ("pandas", None, "数据分析: 表格处理", "core"),
    ]:
        available, ver = _check_package(pkg)
        capabilities.append(_CapabilityStatus(
            name=pkg, available=available, version=ver, description=desc, category=cat
        ))
    for pkg, desc in [("openmm", "分子动力学模拟 (GPU 加速)")]:
        available, ver = _check_package(pkg)
        capabilities.append(_CapabilityStatus(
            name=pkg, available=available, version=ver, description=desc, category="md"
        ))
    for cmd, pkg, desc in [("vina", "autodock_vina", "分子对接 (命令行)")]:
        available = _check_command(cmd)
        _, ver = _check_package(pkg)
        capabilities.append(_CapabilityStatus(
            name=cmd, available=available, version=ver, description=desc, category="docking"
        ))
    for pkg, desc in [("deepchem", "深度学习 ADMET 预测")]:
        available, ver = _check_package(pkg)
        capabilities.append(_CapabilityStatus(
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
                parts = result.stdout.strip().split(",")
                if parts:
                    gpu_available = True
                    gpu_name = parts[0].strip()
                    if len(parts) > 1:
                        mem_str = parts[1].strip().replace(" MiB", "").replace("MiB", "").strip()
                        try:
                            gpu_memory_mb = int(mem_str)
                        except ValueError:
                            pass
                    if len(parts) > 2:
                        cuda_version = parts[2].strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

    return _EnvironmentCheckResult(
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        gpu_memory_mb=gpu_memory_mb,
        cuda_version=cuda_version,
        capabilities=capabilities,
    )
