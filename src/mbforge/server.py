"""MBForge Model Server — FastAPI app with fixed local model backends.

Python sidecar hosts local models:
    - MolScribe         (backends.molscribe)
    - MolDet            (backends.moldet)

All API-based models (OpenAI, Anthropic, etc.) are called directly.
Knowledge base uses OpenKB + PageIndex (vectorless, reasoning-based).
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import inspect
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

from .backends import moldet, molscribe
from .core.resource_manager import ResourceManager
from .parsers.molecule.coref_alt import (
    CorefResult as CorefResultData,
)
from .parsers.molecule.coref_alt import (
    coref_to_rust_dict,
    detect_coref_via_moldet_ocr,
    get_rapid_ocr,
)
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
_BACKENDS = [molscribe, moldet]


def _prewarm() -> None:
    pass  # MolDet/MolScribe are lazy-loaded on first use


def _check_environment() -> None:
    try:
        report = ResourceManager.check_all()
        logger.info("Environment check: %s", report.summary)
        for r in report.resources:
            icon = "✓" if r.status.value == "ready" else "✗"
            logger.info("  %s %s: %s", icon, r.name, r.status.value)
    except Exception as e:
        logger.warning("Environment check failed: %s", e)


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
        pending = [
            t
            for t in asyncio.all_tasks()
            if t is not asyncio.current_task() and not t.done()
        ]
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

        # FastAPI >=0.95 follows __wrapped__ when resolving call signatures,
        # which would incorrectly inject ``body`` as a dependency. Expose only
        # the wrapper's ``(request: Request)`` signature to the router.
        wrapper.__signature__ = inspect.signature(wrapper, follow_wrapped=False)  # type: ignore[attr-defined]
        del wrapper.__wrapped__
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(ModelNotAvailableError)
async def _model_error_handler(
    request: Request, exc: ModelNotAvailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.message, "error_code": exc.error_code},
    )


@app.exception_handler(Exception)
async def _generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": str(exc), "error_code": "internal_error"},
    )


# ---------------------------------------------------------------------------
# PDF rendering (PyMuPDF page images for MoldDet)
# ---------------------------------------------------------------------------


def _render_pages_sync(
    pdf_path: str, page_numbers: list[int], dpi: float
) -> list[dict[str, Any]]:
    """Render selected pages of a PDF to base64-encoded PNG images using PyMuPDF."""
    doc = fitz.open(pdf_path)
    try:
        screenshots: list[dict[str, Any]] = []
        for page_num in page_numbers:
            page_index = int(page_num) - 1  # 1-based to 0-based
            if page_index < 0 or page_index >= doc.page_count:
                logger.warning("Invalid page number %s for %s", page_num, pdf_path)
                continue
            page = doc.load_page(page_index)
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            encoded = base64.b64encode(img_bytes).decode("utf-8")
            screenshots.append(
                {
                    "page_num": int(page_num),
                    "width": pix.width,
                    "height": pix.height,
                    "image_base64": encoded,
                }
            )
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
        logger.error("PDF render failed for %s: %s", pdf_path, e, exc_info=True)
        raise ModelNotAvailableError(str(e)) from e


# ---------------------------------------------------------------------------
# Figure bbox extraction (PyMuPDF image positions on PDF page)
# ---------------------------------------------------------------------------


def _extract_figure_bboxes_sync(pdf_path: str) -> dict[str, Any]:
    """Return every embedded image's on-page bbox for the whole document.

    Used by the coref overlay to project figure-local OCR bboxes (0–1 in
    the extracted figure image) onto PDF page coordinates.

    PyMuPDF `Page.get_image_info(xrefs=True)` returns one record per drawn
    image instance; we keep the union bbox when the same image xref is
    referenced multiple times on one page.

    Returns:
        {
            "pages": [
                {"page_num": int, "figures": [
                    {"xref": int, "bbox_pdf": [x1, y1, x2, y2], "width": int, "height": int}
                ]},
                ...
            ],
            "count": int,  # total figure instances
        }
    """
    doc = fitz.open(pdf_path)
    try:
        pages_out: list[dict[str, Any]] = []
        total = 0
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            try:
                infos = page.get_image_info(xrefs=True)
            except Exception as e:
                logger.debug("get_image_info failed on page %d: %s", page_index + 1, e)
                infos = []

            # 按 xref 合并 bbox（同一 image 被多次引用时取并集）
            by_xref: dict[int, dict[str, Any]] = {}
            for info in infos:
                xref = info.get("xref")
                bbox = info.get(
                    "bbox"
                )  # fitz.Rect-like: (x0, y0, x1, y1) in PDF points
                if xref is None or bbox is None:
                    continue
                try:
                    x0, y0, x1, y1 = (
                        float(bbox[0]),
                        float(bbox[1]),
                        float(bbox[2]),
                        float(bbox[3]),
                    )
                except (TypeError, ValueError):
                    continue
                entry = by_xref.get(int(xref))
                if entry is None:
                    by_xref[int(xref)] = {
                        "xref": int(xref),
                        "bbox_pdf": [x0, y0, x1, y1],
                        "width": info.get("width"),
                        "height": info.get("height"),
                    }
                else:
                    ex0, ey0, ex1, ey1 = entry["bbox_pdf"]
                    entry["bbox_pdf"] = [
                        min(ex0, x0),
                        min(ey0, y0),
                        max(ex1, x1),
                        max(ey1, y1),
                    ]

            figures = list(by_xref.values())
            total += len(figures)
            pages_out.append({"page_num": page_index + 1, "figures": figures})
        return {"pages": pages_out, "count": total}
    finally:
        doc.close()


@app.post("/api/v1/pdf/figure-bboxes")
async def figure_bboxes(request: Request) -> dict[str, Any]:
    """Extract on-page bbox for every embedded image in a PDF.

    Request body:
        - pdf_path: absolute path to the PDF file

    Returns:
        - pages: list of {page_num, figures: [{xref, bbox_pdf, width, height}]}
        - count: total figure instances
    """
    pdf_path = ""
    try:
        body = await request.json()
        pdf_path = body.get("pdf_path", "")
        if not pdf_path:
            raise ValidationError("pdf_path is required")
        if not Path(pdf_path).exists():
            raise ValidationError(f"PDF not found: {pdf_path}")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: _extract_figure_bboxes_sync(pdf_path)
        )
        return result
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        logger.error("figure-bboxes failed for %s: %s", pdf_path, e, exc_info=True)
        raise ModelNotAvailableError(str(e)) from e


# ---------------------------------------------------------------------------
# MolDet
# ---------------------------------------------------------------------------
@app.post("/api/v1/moldet/detect-page")
@with_model_status("moldet")
async def detect_page(request: Request, body: dict) -> dict[str, Any]:
    """检测分子 bbox。支持两种模式：
    1. 图像模式: {image_base64: "..."}  (兼容旧接口)
    2. PDF模式: {pdf_path: "...", page_numbers: [1,2,...], dpi: 300}
    """
    pdf_path = body.get("pdf_path", "")
    image_base64 = body.get("image_base64", "")

    if pdf_path:
        # PDF 模式：渲染 + 检测一步完成
        page_numbers = body.get("page_numbers", [1])
        dpi = body.get("dpi", 300.0)
        if not Path(pdf_path).exists():
            raise ValidationError(f"PDF not found: {pdf_path}")
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, lambda: _detect_from_pdf_sync(pdf_path, page_numbers, dpi)
        )
        return results
    elif image_base64:
        # 图像模式：兼容旧接口
        image = decode_base64_image(image_base64)
        pipeline = moldet.get_moldet()
        if pipeline is None or not pipeline.is_available():
            raise ModelNotAvailableError("MolDet pipeline not available")
        loop = asyncio.get_running_loop()
        boxes = await loop.run_in_executor(
            None, lambda: pipeline.doc_detector.detect(image)
        )
        return {
            "boxes": [
                {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "conf": conf}
                for x1, y1, x2, y2, conf in boxes
            ],
            "count": len(boxes),
        }
    else:
        raise ValidationError("image_base64 or pdf_path is required")


def _detect_from_pdf_sync(
    pdf_path: str, page_numbers: list[int], dpi: float
) -> dict[str, Any]:
    """渲染 PDF 页面并检测分子 bbox（一步完成，无 PNG/base64 中间格式）。"""
    import fitz
    import numpy as np
    from PIL import Image

    pipeline = moldet.get_moldet()
    if pipeline is None or not pipeline.is_available():
        raise ModelNotAvailableError("MolDet pipeline not available")

    doc = fitz.open(pdf_path)
    try:
        all_results = []
        for page_num in page_numbers:
            page_index = int(page_num) - 1
            if page_index < 0 or page_index >= doc.page_count:
                continue
            page = doc.load_page(page_index)
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # 直接转 numpy，不经过 PNG
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            image = Image.fromarray(img_array)

            # YOLO 检测
            boxes = pipeline.doc_detector.detect(image)
            all_results.append(
                {
                    "page_num": int(page_num),
                    "width": pix.width,
                    "height": pix.height,
                    "boxes": [
                        {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "conf": conf}
                        for x1, y1, x2, y2, conf in boxes
                    ],
                    "count": len(boxes),
                }
            )
        return {"results": all_results, "total": len(all_results)}
    finally:
        doc.close()


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
            None,
            lambda: pipeline.extract_page(
                image, page_idx, page_w_pts, page_h_pts, image_w, image_h, dpi
            ),
        )

        # 2. Coref 增强（可选，coref_alt 实现）
        if use_coref and results:
            try:
                if (
                    pipeline.doc_detector is not None
                    and pipeline.doc_detector.is_available()
                ):
                    ocr_adapter = get_rapid_ocr()
                    coref_result = await loop.run_in_executor(
                        None,
                        lambda: detect_coref_via_moldet_ocr(
                            image,
                            pipeline.doc_detector,
                            ocr_adapter,
                            page_w_pts,
                            page_h_pts,
                        ),
                    )
                    _enrich_results_with_coref(results, coref_result)
                    logger.debug(
                        "[extract-page] Coref enriched %d molecules",
                        len(coref_result.corefs),
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
        raise ModelNotAvailableError(str(e)) from e


def _enrich_results_with_coref(
    results: list,
    coref_result: CorefResultData,
) -> None:
    """用 coref 结果增强 ExtractionResult 的 context_text。

    Args:
        results: ExtractionResult 列表
        coref_result: coref_alt 输出的 CorefResult
    """
    if not coref_result or not coref_result.corefs:
        return

    # 构建 mol_idx → idt 文本列表映射
    mol_idt_map: dict[int, list[str]] = {}
    for mol_idx, idt_idx in coref_result.corefs:
        if 0 <= idt_idx < len(coref_result.bboxes):
            text = coref_result.bboxes[idt_idx].text
            if text is None:
                continue
            mol_idt_map.setdefault(mol_idx, []).append(text)

    # 增强每个 molecule 的 context_text
    for i, result in enumerate(results):
        labels = mol_idt_map.get(i)
        if not labels:
            continue
        if len(labels) == 1:
            result.context_text = f"关联标号: {labels[0]}"
        else:
            result.context_text = f"关联 {len(labels)} 个标号: {', '.join(labels)}"


# ---------------------------------------------------------------------------
# MolDetect Coref（coref_alt 实现）
# ---------------------------------------------------------------------------
@app.post("/api/v1/moldet/coref")
@with_model_status("moldet_coref")
async def detect_coref(request: Request, body: dict) -> dict[str, Any]:
    """检测分子和标识符的共指关系（moldet + RapidOCR 实现）。

    返回格式对齐 vlm_chem.rs 解析期望：
      bboxes[*]: {category_id, bbox[4], smiles?, molfile?, text?, score}
      corefs[*]: [mol_idx, idt_idx]
    """
    image_base64 = body.get("image_base64", "")
    if not image_base64:
        raise ValidationError("image_base64 is required")

    image = decode_base64_image(image_base64)
    pipeline = moldet.get_moldet()
    if (
        pipeline is None
        or pipeline.doc_detector is None
        or not pipeline.doc_detector.is_available()
    ):
        raise ModelNotAvailableError("MolDet doc detector not available")

    ocr_adapter = get_rapid_ocr()
    loop = asyncio.get_running_loop()
    coref_result = await loop.run_in_executor(
        None,
        lambda: detect_coref_via_moldet_ocr(
            image,
            pipeline.doc_detector,
            ocr_adapter,
        ),
    )
    return coref_to_rust_dict(coref_result)


def _dbscan_preprocess(pil_image):
    """DBSCAN 提取分子主体，去除周围文字。"""
    import cv2
    import numpy as np
    from PIL import Image
    from sklearn.cluster import DBSCAN

    img = np.array(pil_image.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    side = max(h, w)

    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    bw_sq = cv2.resize(bw, (side, side), interpolation=cv2.INTER_NEAREST)

    ys, xs = np.where(bw_sq > 0)
    if len(xs) == 0:
        return pil_image
    coords = np.column_stack([xs, ys])
    db = DBSCAN(eps=13, min_samples=5, n_jobs=-1)
    labels = db.fit_predict(coords)

    unique, counts = np.unique(labels, return_counts=True)
    mask = unique != -1
    if not mask.any():
        return pil_image
    uc, cc = unique[mask], counts[mask]
    best = uc[np.argmax(cc)]

    mol_mask = np.zeros((side, side), dtype=np.uint8)
    main_pts = coords[labels == best]
    mol_mask[main_pts[:, 1], main_pts[:, 0]] = 255

    output = np.where(mol_mask == 255, 0, 255).astype(np.uint8)
    output = cv2.resize(output, (w, h), interpolation=cv2.INTER_NEAREST)
    return Image.fromarray(output).convert("RGB")


# ---------------------------------------------------------------------------
# MolExtract — 全流程 PDF→MolDet→Coref→MolScribe
# ---------------------------------------------------------------------------
@app.post("/api/v1/moldet/extract-pdf-page")
async def extract_pdf_page(request: Request, body: dict) -> dict[str, Any]:
    """单页 PDF 全流程：渲染→MolDet→Coref→MolScribe，返回规整 JSON。

    Request:
        pdf_path: str    PDF 文件路径
        page: int        页码（从 1 开始）
        dpi: float       渲染 DPI（默认 300）
        use_coref: bool  是否启用 Coref 配对（默认 True）

    Response:
        {
            page_num, width, height, dpi,
            molecules: [{bbox, bbox_pdf, confidence, smiles, scribe_conf, context_text}],
            corefs: [[mol_idx, idt_idx], ...],
            bboxes: [{category_id, bbox, text?, score}],
            count
        }
    """
    import numpy as np
    from PIL import Image

    pdf_path = body.get("pdf_path", "")
    if not pdf_path or not Path(pdf_path).exists():
        raise ValidationError("pdf_path is required and must exist")

    page_num = body.get("page", 1)
    dpi = body.get("dpi", 300.0)
    use_coref = body.get("use_coref", True)

    # 1. 渲染 PDF 页面
    doc = fitz.open(pdf_path)
    try:
        page_index = int(page_num) - 1
        if page_index < 0 or page_index >= doc.page_count:
            raise ValidationError(f"Page {page_num} out of range (1-{doc.page_count})")
        page = doc.load_page(page_index)
        page_w_pts = page.rect.width
        page_h_pts = page.rect.height

        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        image = Image.fromarray(img_array)
        img_w, img_h = pix.width, pix.height
    finally:
        doc.close()

    # 2. MolDet 检测 + Coref
    pipeline = moldet.get_moldet()
    if pipeline is None or not pipeline.is_available():
        raise ModelNotAvailableError("MolDet pipeline not available")

    loop = asyncio.get_running_loop()

    # MolDet 检测（仅检测 bbox，不识别 SMILES）
    boxes = await loop.run_in_executor(
        None,
        lambda: pipeline.doc_detector.detect(image),
    )

    scale_x = page_w_pts / img_w if img_w > 0 else 0
    scale_y = page_h_pts / img_h if img_h > 0 else 0

    # Coref 配对（可选）
    coref_result = None
    coref_dict: dict[str, Any] = {"bboxes": [], "corefs": []}
    if use_coref and boxes:
        try:
            ocr_adapter = get_rapid_ocr()
            coref_result = await loop.run_in_executor(
                None,
                lambda: detect_coref_via_moldet_ocr(
                    image,
                    pipeline.doc_detector,
                    ocr_adapter,
                    page_w_pts,
                    page_h_pts,
                ),
            )
            coref_dict = coref_to_rust_dict(coref_result)
        except Exception as e:
            logger.warning("[extract-pdf-page] Coref failed: %s", e)

    # 3. 裁剪 + MolScribe 识别每个分子
    await loop.run_in_executor(None, molscribe.load)

    async def _recognize_one(x1, y1, x2, y2):
        px1, py1 = max(0, int(x1)), max(0, int(y1))
        px2, py2 = min(img_w, int(x2)), min(img_h, int(y2))
        if px2 <= px1 or py2 <= py1:
            return ""
        crop = image.crop((px1, py1, px2, py2))
        crop_gray = crop.convert("L")
        sr = await loop.run_in_executor(None, lambda: molscribe.predict(crop_gray))
        return sr.esmiles if sr.esmiles else ""

    smiles_list = []
    for b in boxes:
        smi = await _recognize_one(*b[:4])
        smiles_list.append(smi)

    # 4. 用 coref 关联标号到分子
    coref_label_map: dict[int, str] = {}
    if coref_result:
        for mol_idx, idt_idx in coref_result.corefs:
            if 0 <= idt_idx < len(coref_result.bboxes):
                text = coref_result.bboxes[idt_idx].text
                if text:
                    coref_label_map[mol_idx] = text

    # 5. 组装结果
    molecules = []
    for i, (b, smi) in enumerate(zip(boxes, smiles_list)):
        x1, y1, x2, y2, conf = b
        label = coref_label_map.get(i, "")
        molecules.append(
            {
                "index": i,
                "bbox": {
                    "x1": round(x1 * scale_x, 2),
                    "y1": round(page_h_pts - y2 * scale_y, 2),
                    "x2": round(x2 * scale_x, 2),
                    "y2": round(page_h_pts - y1 * scale_y, 2),
                },
                "confidence": round(conf, 4),
                "smiles": smi,
                "scribe_conf": 0.0,
                "context_text": f"关联标号: {label}" if label else "",
            }
        )

    return {
        "page_num": int(page_num),
        "width": img_w,
        "height": img_h,
        "page_w_pts": page_w_pts,
        "page_h_pts": page_h_pts,
        "dpi": dpi,
        "molecules": molecules,
        "corefs": coref_dict.get("corefs", []),
        "bboxes": coref_dict.get("bboxes", []),
        "count": len(molecules),
    }


# ---------------------------------------------------------------------------
# MolScribe
# ---------------------------------------------------------------------------
@app.post("/api/v1/molscribe")
@with_model_status("molscribe")
async def molscribe_predict(request: Request) -> dict[str, Any]:
    tmp_path = None
    try:
        import numpy as np
        from PIL import Image

        content_type = request.headers.get("content-type", "")

        if content_type == "application/octet-stream":
            # 二进制模式：header 传宽高，body 是灰度字节
            width = int(request.headers.get("x-image-width", "0"))
            height = int(request.headers.get("x-image-height", "0"))
            if width <= 0 or height <= 0:
                raise ValidationError("X-Image-Width and X-Image-Height required")
            raw_bytes = await request.body()
            arr = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(height, width)
            image = Image.fromarray(arr, "L")
        else:
            # JSON 模式：兼容旧接口
            body = await request.json()
            image_base64 = body.get("image_base64", "")
            if not image_base64:
                raise ValidationError("image_base64 is required")
            ext = body.get("ext", "png")
            tmp_path = decode_base64_to_tempfile(image_base64, ext)
            image = Image.open(tmp_path)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, molscribe.load)
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
    - molscribe  : 384x384 灰图预测，检查 esmiles 是 str
    - moldet     : 与 input_size 匹配的灰图检测，检查返回 list
    - moldet_coref: 480x480 灰图检测，检查返回 dict
    """
    import time

    import numpy as np

    start = time.perf_counter()
    try:
        rid = resource_id

        if rid == "molscribe":
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

            path = ResourceManager.resolve_model_for_backend("moldet", subpath=subpath)
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
                return {
                    "ok": False,
                    "error": f"YOLO detect 返回非列表: {type(boxes).__name__}",
                }

        elif rid == "moldet_coref":
            # coref_alt 不需额外模型，验证 moldet doc detector + RapidOCR 可用
            from PIL import Image

            from mbforge.parsers.molecule.coref_alt import (
                detect_coref_via_moldet_ocr,
                get_rapid_ocr,
            )

            pipeline = moldet.get_moldet()
            if (
                pipeline is None
                or pipeline.doc_detector is None
                or not pipeline.doc_detector.is_available()
            ):
                return {"ok": False, "error": "MolDet doc detector 不可用"}
            img = Image.new("RGB", (480, 480), color=0)
            result = detect_coref_via_moldet_ocr(
                img, pipeline.doc_detector, get_rapid_ocr()
            )
            if not hasattr(result, "bboxes") or not hasattr(result, "corefs"):
                return {
                    "ok": False,
                    "error": f"coref 输出结构异常: {type(result).__name__}",
                }

        else:
            return {"ok": False, "error": f"未知资源: {rid}"}
    except Exception as e:
        logger.warning("Test %s failed: %s", resource_id, e, exc_info=True)
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
        result = await loop.run_in_executor(
            None, lambda: _test_loading_sync(resource_id, subpath)
        )
        return result
    except ValidationError:
        raise
    except Exception as e:
        logger.error("test_model failed: %s", e, exc_info=True)
        return {"ok": False, "error": str(e), "duration_ms": 0}


# ---------------------------------------------------------------------------
# Health + Circuit Breaker
# ---------------------------------------------------------------------------
_model_status = {
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
            logger.debug("MolDet health check failed: %s", e)

    # MolDet Coref (coref_alt: 复用 MolDet doc detector + RapidOCR，无独立模型)
    if not _should_skip_due_to_cooldown("moldet_coref"):
        try:
            pipeline = moldet.get_moldet()
            if (
                pipeline is not None
                and pipeline.doc_detector is not None
                and pipeline.doc_detector.is_available()
            ):
                # 触发 RapidOCR 懒加载（首次较慢）
                get_rapid_ocr()
                _model_status["moldet_coref"] = "ready"
                _clear_failure("moldet_coref")
            else:
                _model_status["moldet_coref"] = "error"
                _mark_failure("moldet_coref")
        except Exception as e:
            _model_status["moldet_coref"] = "error"
            _mark_failure("moldet_coref")
            logger.debug("MolDet coref health check failed: %s", e)

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
            logger.debug("Resource status check failed: %s", e)

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


# ---------------------------------------------------------------------------
# Mol Image Generation (SMILES → 2D structure)
# ---------------------------------------------------------------------------
@app.post("/api/v1/mol/render")
async def render_molecule(request: Request, body: dict) -> dict[str, Any]:
    """Generate a 2D structure image from SMILES.

    Returns base64-encoded PNG.
    """
    smiles = body.get("smiles", "")
    if not smiles:
        raise ValidationError("smiles is required")

    width = body.get("width", 300)
    height = body.get("height", 200)

    loop = asyncio.get_running_loop()

    def _render() -> str:
        from rdkit import Chem
        from rdkit.Chem import AllChem, Draw

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValidationError(f"Invalid SMILES: {smiles}")

        AllChem.Compute2DCoords(mol)
        img = Draw.MolToImage(mol, size=(width, height))
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    b64 = await loop.run_in_executor(None, _render)
    return {"success": True, "image_base64": b64}


@app.get("/api/v1/environment/check", response_model=_EnvironmentCheckResult)
async def check_environment() -> _EnvironmentCheckResult:
    capabilities: list[_CapabilityStatus] = []
    for pkg, _version, desc, cat in [
        ("rdkit", None, "分子信息学: SMILES 解析、分子属性计算", "core"),
        ("numpy", None, "数值计算: 数组运算、线性代数", "core"),
        ("scipy", None, "科学计算: 优化、插值、统计", "core"),
        ("pandas", None, "数据分析: 表格处理", "core"),
    ]:
        available, ver = _check_package(pkg)
        capabilities.append(
            _CapabilityStatus(
                name=pkg,
                available=available,
                version=ver,
                description=desc,
                category=cat,
            )
        )
    for pkg, desc in [("openmm", "分子动力学模拟 (GPU 加速)")]:
        available, ver = _check_package(pkg)
        capabilities.append(
            _CapabilityStatus(
                name=pkg,
                available=available,
                version=ver,
                description=desc,
                category="md",
            )
        )
    for cmd, pkg, desc in [("vina", "autodock_vina", "分子对接 (命令行)")]:
        available = _check_command(cmd)
        _, ver = _check_package(pkg)
        capabilities.append(
            _CapabilityStatus(
                name=cmd,
                available=available,
                version=ver,
                description=desc,
                category="docking",
            )
        )
    for pkg, desc in [("deepchem", "深度学习 ADMET 预测")]:
        available, ver = _check_package(pkg)
        capabilities.append(
            _CapabilityStatus(
                name=pkg,
                available=available,
                version=ver,
                description=desc,
                category="admet",
            )
        )

    gpu_available = False
    gpu_name = None
    gpu_memory_mb = None
    cuda_version = None
    try:
        import torch

        if torch.cuda.is_available():
            gpu_available = True
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory_mb = int(
                torch.cuda.get_device_properties(0).total_memory / 1024 / 1024
            )
            cuda_version = torch.version.cuda
    except ImportError:
        pass
    if not gpu_available:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                if parts:
                    gpu_available = True
                    gpu_name = parts[0].strip()
                    if len(parts) > 1:
                        mem_str = (
                            parts[1]
                            .strip()
                            .replace(" MiB", "")
                            .replace("MiB", "")
                            .strip()
                        )
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
