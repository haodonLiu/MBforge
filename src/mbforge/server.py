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
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path
from typing import Any

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
# Endpoint 装饰器：统一 JSON 解析 + try/except + set_model_status
# ---------------------------------------------------------------------------


def with_model_status(model_id: str):
    """装饰器：自动解析 request body、统一异常处理、设置 model 状态。

    包装后的函数签名为 ``async def fn(request: Request, body: dict) -> Any``。
    request 保留给需要读 header 的端点（如 embed 的 X-Trace-Id）。
    - 成功 → set_model_status(model_id, "ready")
    - ValidationError / ModelNotAvailableError → 原样抛出
    - 其他异常 → set_model_status("error") + 抛 ModelNotAvailableError
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(request: Request) -> dict[str, Any]:
            try:
                body = await request.json()
            except Exception as e:
                raise ValidationError(f"Invalid JSON body: {e}") from e
            try:
                return await fn(request, body)
            except (ValidationError, ModelNotAvailableError):
                raise
            except Exception as e:
                set_model_status(model_id, "error")
                raise ModelNotAvailableError(str(e)) from e
        return wrapper
    return decorator


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
@with_model_status("embedder")
async def embed(request: Request, body: dict) -> dict[str, Any]:
    # Rust 侧通过 X-Trace-Id / X-Span-Id header 传递 tracing 上下文
    trace_id = request.headers.get("x-trace-id") or request.headers.get("X-Trace-Id")
    span_id = request.headers.get("x-span-id") or request.headers.get("X-Span-Id")
    texts = body.get("texts", [])
    if isinstance(texts, str):
        texts = [texts]
    if not texts:
        raise ValidationError("texts is required")
    mrl_dim = body.get("mrl_dim")
    if isinstance(mrl_dim, (int, float)) and mrl_dim > 0:
        mrl_dim = int(mrl_dim)
    else:
        mrl_dim = None
    if trace_id:
        logger.info(f"[trace={trace_id} span={span_id}] embed started")
    loop = asyncio.get_running_loop()
    embeddings = await loop.run_in_executor(
        None, lambda: qwen3_embed.embed(texts, mrl_dim=mrl_dim)
    )
    dim = len(embeddings[0]) if embeddings else 0
    if trace_id:
        logger.info(f"[trace={trace_id} span={span_id}] embed done, dim={dim}")
    return {"embeddings": embeddings}


# ---------------------------------------------------------------------------
# Rerank
# ---------------------------------------------------------------------------
@app.post("/api/v1/rerank")
@with_model_status("reranker")
async def rerank(request: Request, body: dict) -> dict[str, Any]:
    query = body.get("query", "")
    passages = body.get("passages", [])
    if not query or not passages:
        raise ValidationError("query and passages are required")
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None, lambda: qwen3_rerank.rerank(query, passages)
    )
    return {"results": [{"index": i, "score": s} for i, s in results]}


# ---------------------------------------------------------------------------
# MolDet
# ---------------------------------------------------------------------------
@app.post("/api/v1/moldet/detect-page")
@with_model_status("moldet")
async def detect_page(request: Request, body: dict) -> dict[str, Any]:
    image_base64 = body.get("image_base64", "")
    if not image_base64:
        raise ValidationError("image_base64 is required")
    image = decode_base64_image(image_base64)
    pipeline = moldet.get_moldet()
    if pipeline is None or not pipeline.is_available():
        raise ModelNotAvailableError("MolDet pipeline not available")
    loop = asyncio.get_running_loop()
    boxes = await loop.run_in_executor(None, lambda: pipeline.doc_detector.detect(image))
    return {
        "boxes": [{"x1": x1, "y1": y1, "x2": x2, "y2": y2, "conf": conf} for x1, y1, x2, y2, conf in boxes],
        "count": len(boxes),
    }


@app.post("/api/v1/moldet/detect-batch")
@with_model_status("moldet")
async def detect_batch(request: Request, body: dict) -> dict[str, Any]:
    """批量检测多页图像中的分子 bbox."""
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
        use_coref = body.get("use_coref", True)

        if image_w == 0 or image_h == 0:
            raise ValidationError("image_w and image_h are required")

        image = decode_base64_image(image_base64)
        pipeline = moldet.get_moldet()
        if pipeline is None or not pipeline.is_available():
            raise ModelNotAvailableError("MolDet pipeline not available")

        loop = asyncio.get_running_loop()

        # 1. 基础检测
        results = await loop.run_in_executor(
            None, lambda: pipeline.extract_page(image, page_idx, page_w_pts, page_h_pts, image_w, image_h, dpi)
        )

        # 2. Coref 增强（可选）
        if use_coref and results:
            try:
                coref_backend = moldet_coref.get_coref()
                if coref_backend and coref_backend.is_available():
                    # 提取 MolDet 检测到的 bbox
                    mol_bboxes = []
                    for r in results:
                        if r.bbox_pdf:
                            # 转换为归一化坐标（coref 需要）
                            x1, y1, x2, y2 = r.bbox_pdf
                            # bbox_pdf 是 PDF 坐标（左下原点），需要转换
                            # 这里传入原始 bbox，由 coref_to_molecules 处理
                            mol_bboxes.append({
                                "x1": x1, "y1": y1, "x2": x2, "y2": y2
                            })

                    # 并行执行 coref 检测
                    coref_result = await loop.run_in_executor(
                        None,
                        lambda: coref_backend.detect_coref_with_mapping(
                            image,
                            mol_bboxes=mol_bboxes,
                        )
                    )

                    # 用 coref 结果增强 context_text
                    if coref_result and "corefs" in coref_result:
                        _enrich_results_with_coref(results, coref_result)
                        logger.debug(
                            "[extract-page] Coref enriched %d molecules",
                            len(coref_result.get("corefs", []))
                        )
            except Exception as e:
                # Coref 失败不影响基础检测结果
                logger.warning("[extract-page] Coref enrichment failed: %s", e)

        set_model_status("moldet", "ready")
        return {"results": [r.to_dict() for r in results], "count": len(results)}
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        set_model_status("moldet", "error")
        raise ModelNotAvailableError(str(e))


def _enrich_results_with_coref(
    results: list,
    coref_result: dict,
) -> None:
    """用 coref 结果增强 ExtractionResult 的 context_text。

    Args:
        results: ExtractionResult 列表
        coref_result: coref 检测结果
    """
    if not coref_result or "corefs" not in coref_result:
        return

    # 构建 mol_idx → idt_bbox 映射
    mol_idt_map: dict[int, list[dict]] = {}
    for coref in coref_result.get("corefs", []):
        mol_idx = coref.get("mol_idx")
        idt_bbox = coref.get("idt_bbox")
        if mol_idx is not None and idt_bbox is not None:
            if mol_idx not in mol_idt_map:
                mol_idt_map[mol_idx] = []
            mol_idt_map[mol_idx].append(idt_bbox)

    # 增强每个 molecule 的 context_text
    for i, result in enumerate(results):
        if i in mol_idt_map and mol_idt_map[i]:
            # 使用 idt_bbox 的位置信息作为 context 提示
            idt_bboxes = mol_idt_map[i]
            if len(idt_bboxes) == 1:
                result.context_text = f"关联标号位置: {idt_bboxes[0]}"
            else:
                result.context_text = f"关联 {len(idt_bboxes)} 个标号位置"


# ---------------------------------------------------------------------------
# MolDetect Coref
# ---------------------------------------------------------------------------
@app.post("/api/v1/moldet/coref")
@with_model_status("moldet_coref")
async def detect_coref(request: Request, body: dict) -> dict[str, Any]:
    """检测分子和标识符的共指关系."""
    image_base64 = body.get("image_base64", "")
    if not image_base64:
        raise ValidationError("image_base64 is required")
    mol_bboxes = body.get("mol_bboxes", [])

    image = decode_base64_image(image_base64)
    backend = moldet_coref.get_coref()
    if backend is None or not backend.is_available():
        raise ModelNotAvailableError("MolDetect coref backend not available")

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: backend.detect_coref_with_mapping(
            image,
            mol_bboxes=mol_bboxes,
        ),
    )


# ---------------------------------------------------------------------------
# MolScribe
# ---------------------------------------------------------------------------
@app.post("/api/v1/molscribe")
@with_model_status("molscribe")
async def molscribe_predict(request: Request, body: dict) -> dict[str, Any]:
    tmp_path = None
    try:
        image_base64 = body.get("image_base64", "")
        if not image_base64:
            raise ValidationError("image_base64 is required")
        ext = body.get("ext", "png")
        tmp_path = decode_base64_to_tempfile(image_base64, ext)
        from PIL import Image
        image = Image.open(tmp_path)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: molscribe.predict(image))
        if not result.esmiles:
            err_msg = result.properties.get("error", "unknown error")
            raise ModelNotAvailableError(f"MolScribe not available: {err_msg}")
        return {
            "esmiles": result.esmiles,
            "confidence": result.scribe_conf,
            "success": True,
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# ---------------------------------------------------------------------------
# 模型测试端点：实际加载模型到内存并做最小推理，验证文件路径 + 权重有效
# ---------------------------------------------------------------------------
def _test_loading_sync(resource_id: str, subpath: str | None) -> dict[str, Any]:
    """同步部分：在 executor 里跑。返回 ok/error + 错误详情。

    每个后端跑最小真实推理（不仅是 load()）：
    - embedding  : encode 1 个字符串，检查输出是 (1, dim) 向量
    - reranker   : rerank 1 query + 1 passage，检查返回 [(idx, score), ...]
    - molscribe  : 384x384 灰图预测，检查 esmiles 是 str
    - moldet     : 与 input_size 匹配的灰图检测，检查返回 list
    - moldet_coref: 480x480 灰图检测，检查返回 dict
    """
    import time

    import numpy as np
    start = time.perf_counter()
    try:
        rid = resource_id

        if rid == "embedding":
            qwen3_embed.load()
            if qwen3_embed._MODEL is None:
                return {"ok": False, "error": qwen3_embed._ERROR or "未加载到内存"}
            vecs = qwen3_embed.embed(["test"])
            if not isinstance(vecs, list) or len(vecs) != 1 or not isinstance(vecs[0], list) or len(vecs[0]) == 0:
                return {"ok": False, "error": f"embed 输出异常: shape={getattr(vecs, 'shape', len(vecs) if hasattr(vecs, '__len__') else type(vecs).__name__)}"}

        elif rid == "reranker":
            qwen3_rerank.load()
            if qwen3_rerank._MODEL is None:
                return {"ok": False, "error": qwen3_rerank._ERROR or "未加载到内存"}
            results = qwen3_rerank.rerank("test query", ["test passage"])
            if not isinstance(results, list) or len(results) != 1:
                return {"ok": False, "error": f"rerank 输出异常: {results}"}

        elif rid == "molscribe":
            molscribe.load()
            if not molscribe._AVAILABLE:
                return {"ok": False, "error": molscribe._ERROR or "未就绪"}
            from PIL import Image
            # MolScribe input_size 默认 384（从 checkpoint 读取，构造时已存到 args）
            input_size = getattr(molscribe._MODEL, "input_size", 384) or 384
            img = Image.new("RGB", (input_size, input_size), color=0)
            result = molscribe.predict(img)
            if result is None or not getattr(result, "success", False):
                err = getattr(result, "error", None) if result else "predict 返回 None"
                return {"ok": False, "error": f"molscribe 推理失败: {err}"}

        elif rid == "moldet":
            from mbforge.core.resource_manager import ResourceManager
            path = ResourceManager.resolve_model_for_backend(
                "moldet", subpath=subpath
            )
            if path is None:
                return {"ok": False, "error": f"模型文件未找到 (subpath={subpath})"}
            from mbforge.backends.moldet import (
                MolDetv2DocDetector,
                MolDetv2GeneralDetector,
            )
            is_doc = bool(subpath and subpath.startswith("doc"))
            if is_doc:
                det = MolDetv2DocDetector(model_path=path)
                size = (960, 960)
            else:
                det = MolDetv2GeneralDetector(model_path=path)
                size = (640, 640)
            if not det.is_available():
                return {"ok": False, "error": f"YOLO 加载失败: {det.model_path}"}
            # 真实推理：与 input_size 匹配的全黑图
            img = np.zeros((*size, 3), dtype=np.uint8)
            boxes = det.detect(img)
            if not isinstance(boxes, list):
                return {"ok": False, "error": f"YOLO detect 返回非列表: {type(boxes).__name__}"}

        elif rid == "moldet_coref":
            from mbforge.core.resource_manager import ResourceManager
            path = ResourceManager.resolve_model_for_backend("moldet_coref")
            if path is None:
                return {"ok": False, "error": "模型文件未找到"}
            from mbforge.backends.moldet_coref import MolDetectCorefBackend
            backend = MolDetectCorefBackend(model_path=str(path))
            if not backend.is_available():
                return {"ok": False, "error": "coref 加载失败"}
            from PIL import Image
            img = Image.new("RGB", (480, 480), color=0)
            result = backend.detect_coref_with_mapping(img, mol_bboxes=[])
            if not isinstance(result, dict):
                return {"ok": False, "error": f"coref 输出非 dict: {type(result).__name__}"}

        else:
            return {"ok": False, "error": f"未知资源: {rid}"}
    except Exception as e:
        logger.warning(f"Test {resource_id} failed: {e}", exc_info=True)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    duration_ms = int((time.perf_counter() - start) * 1000)
    return {"ok": True, "error": "", "duration_ms": duration_ms}


@app.post("/api/v1/test/model")
async def test_model(request: Request) -> dict[str, Any]:
    """测试单个模型是否能正常加载。返回 {ok, error, duration_ms}."""
    try:
        body = await request.json()
        resource_id = body.get("resource_id", "")
        subpath = body.get("subpath")
        if not resource_id:
            raise ValidationError("resource_id is required")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: _test_loading_sync(resource_id, subpath))
        return result
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"test_model failed: {e}", exc_info=True)
        return {"ok": False, "error": str(e), "duration_ms": 0}


# ---------------------------------------------------------------------------
# Health + Circuit Breaker
# ---------------------------------------------------------------------------
_model_status = {
    "embedder": "loading",
    "reranker": "loading",
    "moldet": "loading",
    "moldet_coref": "loading",
    "molscribe": "loading",
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
    version: str | None = None
    description: str
    category: str


class _EnvironmentCheckResult(BaseModel):
    python_version: str
    gpu_available: bool
    gpu_name: str | None = None
    gpu_memory_mb: int | None = None
    cuda_version: str | None = None
    capabilities: list[_CapabilityStatus]


def _check_package(pkg_name: str) -> tuple[bool, str | None]:
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
