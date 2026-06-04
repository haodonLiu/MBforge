"""PDF 分子提取工作流（Python 侧）.

默认通过 sidecar HTTP 调用 MolDet + MolScribe（零额外 GPU 内存），
`--no-sidecar` 模式下直接加载模型（用于离线调试）。

用法:
    from mbforge.parsers.workflow import extract_pdf_workflow

    result = extract_pdf_workflow("paper.pdf", "./output")
    print(result)
"""

from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..utils.logger import get_logger

logger = get_logger(__name__)

_SIDECAR_URL = "http://127.0.0.1:18792"


@dataclass
class MoleculeEntry:
    """单个分子的元数据."""

    index: int
    smiles: str
    esmiles: str | None
    name: str
    page: int
    moldet_confidence: float
    molscribe_confidence: float
    image_file: str


@dataclass
class Manifest:
    """manifest.json 结构."""

    source: str
    parser: str
    page_count: int
    text_file: str
    molecules: list[MoleculeEntry] = field(default_factory=list)


@dataclass
class WorkflowResult:
    """工作流输出结果."""

    output_dir: str
    text_path: str
    manifest_path: str
    page_count: int
    molecule_count: int
    parser: str


def extract_pdf_workflow(
    pdf_path: str,
    output_dir: str,
    *,
    use_sidecar: bool = True,
    sidecar_url: str = _SIDECAR_URL,
) -> WorkflowResult:
    """完整 PDF 分子提取工作流.

    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录
        use_sidecar: 是否通过 sidecar HTTP 调用（默认 True）
        sidecar_url: sidecar 地址

    Returns:
        WorkflowResult 包含输出路径和统计信息
    """
    pdf = Path(pdf_path)
    if not pdf.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pdf_name = pdf.stem
    base_dir = Path(output_dir) / pdf_name
    mol_dir = base_dir / "molecules"
    mol_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting extraction: %s → %s", pdf_path, base_dir)

    # Stage 1: 文本提取
    text, page_count, parser_name = _extract_text(pdf_path)

    text_path = base_dir / "text.md"
    text_path.write_text(text, encoding="utf-8")
    logger.info(
        "Text extracted: %d pages, %d chars, parser=%s",
        page_count, len(text), parser_name,
    )

    # Stage 2: 分子检测 + 识别
    if use_sidecar:
        detected = _detect_molecules_via_sidecar(pdf_path, mol_dir, sidecar_url)
    else:
        detected = _detect_molecules_direct(pdf_path, mol_dir)
    logger.info("Detected %d molecules", len(detected))

    # Stage 3: 生成 manifest.json
    molecules = [
        MoleculeEntry(
            index=i,
            smiles=mol["smiles"],
            esmiles=mol.get("esmiles"),
            name=f"IMG-{pdf_name}-P{mol['page']}",
            page=mol["page"],
            moldet_confidence=mol["moldet_conf"],
            molscribe_confidence=mol["confidence"],
            image_file=mol["image_file"],
        )
        for i, mol in enumerate(detected)
    ]

    manifest = Manifest(
        source=pdf_name,
        parser=parser_name,
        page_count=page_count,
        text_file="text.md",
        molecules=molecules,
    )

    manifest_path = mol_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(asdict(manifest), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    result = WorkflowResult(
        output_dir=str(base_dir),
        text_path=str(text_path),
        manifest_path=str(manifest_path),
        page_count=page_count,
        molecule_count=len(detected),
        parser=parser_name,
    )

    logger.info(
        "Done: %d pages, %d molecules → %s",
        result.page_count, result.molecule_count, result.output_dir,
    )
    return result


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def _extract_text(pdf_path: str) -> tuple[str, int, str]:
    """提取 PDF 文本.

    Returns:
        (text, page_count, parser_name)
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(pdf_path)
        pages = [page.get_text() for page in doc]
        page_count = len(doc)
        doc.close()
        return "\n\n".join(pages), page_count, "pymupdf"
    except ImportError:
        pass

    try:
        import pdf_inspector  # type: ignore[import-untyped]

        result = pdf_inspector.process_pdf(pdf_path)
        return result.markdown or "", result.page_count, "pdf_inspector"
    except (ImportError, Exception) as e:
        logger.warning("pdf_inspector not available: %s", e)

    raise RuntimeError("No PDF parser available. Install PyMuPDF: pip install pymupdf")


# ---------------------------------------------------------------------------
# Molecule detection — sidecar HTTP (preferred)
# ---------------------------------------------------------------------------


def _is_sidecar_alive(url: str) -> bool:
    """检查 sidecar 是否在运行."""
    try:
        import urllib.request

        resp = urllib.request.urlopen(f"{url}/api/v1/moldet/health", timeout=3)
        data = json.loads(resp.read())
        return data.get("status") == "ready"
    except Exception:
        return False


def _detect_molecules_via_sidecar(
    pdf_path: str, output_dir: Path, sidecar_url: str,
) -> list[dict]:
    """通过 sidecar HTTP 检测分子（零额外 GPU 内存）.

    流程: PDF 渲染页面 → POST detect-page → 裁剪 → POST molscribe
    """
    if not _is_sidecar_alive(sidecar_url):
        logger.warning(
            "Sidecar not available at %s, falling back to direct mode",
            sidecar_url,
        )
        return _detect_molecules_direct(pdf_path, output_dir)

    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF not available for page rendering")
        return []

    doc = fitz.open(pdf_path)
    results = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pix = page.get_pixmap(dpi=200)
        img_path = output_dir / f"page_{page_idx + 1:04}_raw.png"
        pix.save(str(img_path))

        try:
            page_results = _call_sidecar_extract_page(
                str(img_path), page_idx + 1, output_dir, sidecar_url,
            )
            results.extend(page_results)
        except Exception as e:
            logger.warning("Sidecar extraction failed on page %d: %s", page_idx + 1, e)

        img_path.unlink(missing_ok=True)

    doc.close()
    return results


def _call_sidecar_extract_page(
    image_path: str, page_idx: int, output_dir: Path, sidecar_url: str,
) -> list[dict]:
    """调用 sidecar 的 detect-page + molscribe 完成单页分子提取."""
    import urllib.request

    # 1. detect-page
    img_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    detect_body = json.dumps({"image_base64": img_b64}).encode()
    req = urllib.request.Request(
        f"{sidecar_url}/api/v1/moldet/detect-page",
        data=detect_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=120)
    detect_data = json.loads(resp.read())
    boxes = detect_data.get("boxes", [])

    if not boxes:
        return []

    # 2. 对每个 bbox 裁剪 + molscribe
    try:
        from PIL import Image

        img = Image.open(image_path)
    except ImportError:
        logger.warning("PIL not available for cropping")
        return []

    results = []
    for i, box in enumerate(boxes):
        x1, y1 = int(box["x1"]), int(box["y1"])
        x2, y2 = int(box["x2"]), int(box["y2"])
        if x2 <= x1 or y2 <= y1:
            continue

        crop = img.crop((x1, y1, x2, y2))
        crop_path = output_dir / f"page_{page_idx:04}_mol_{i:03}.png"
        crop.save(str(crop_path))

        # molscribe
        try:
            crop_b64 = base64.b64encode(crop_path.read_bytes()).decode()
            scribe_body = json.dumps({"image_base64": crop_b64, "ext": "png"}).encode()
            req = urllib.request.Request(
                f"{sidecar_url}/api/v1/vlm/molscribe",
                data=scribe_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=60)
            scribe_data = json.loads(resp.read())

            esmiles = scribe_data.get("esmiles", "")
            if esmiles:
                from ..parsers.molecule.molscribe_inference.chemistry import (
                    sanitize_smiles,
                )

                smiles = sanitize_smiles(esmiles) or esmiles
                results.append({
                    "smiles": smiles,
                    "esmiles": esmiles,
                    "page": page_idx,
                    "moldet_conf": box.get("conf", 0.0),
                    "confidence": scribe_data.get("confidence", 0.0),
                    "image_file": crop_path.name,
                })
        except Exception as e:
            logger.warning("MolScribe failed for page %d mol %d: %s", page_idx, i, e)

    return results


# ---------------------------------------------------------------------------
# Molecule detection — direct model loading (fallback)
# ---------------------------------------------------------------------------


def _detect_molecules_direct(pdf_path: str, output_dir: Path) -> list[dict]:
    """直接加载模型检测分子（用于离线/无 sidecar 模式）.

    警告: 会额外占用 ~2GB GPU 内存。
    """
    try:
        from .molecule.mol_image_pipeline import MolImagePipeline

        pipeline = MolImagePipeline()
        if not pipeline.is_available():
            logger.warning("MolDet/MolScribe pipeline not available")
            return []
    except (ImportError, Exception) as e:
        logger.warning("MolDet pipeline not available: %s", e)
        return []

    try:
        import fitz

        doc = fitz.open(pdf_path)
    except ImportError:
        logger.warning("PyMuPDF not available for page rendering")
        return []

    results = []
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pix = page.get_pixmap(dpi=200)
        img_path = output_dir / f"page_{page_idx + 1:04}_raw.png"
        pix.save(str(img_path))

        try:
            page_results = pipeline.process_page(
                str(img_path),
                page_idx=page_idx + 1,
                output_dir=str(output_dir),
            )
            for r in page_results:
                results.append({
                    "smiles": r.get("smiles", ""),
                    "esmiles": r.get("esmiles"),
                    "page": page_idx + 1,
                    "moldet_conf": r.get("moldet_conf", 0.0),
                    "confidence": r.get("confidence", 0.0),
                    "image_file": r.get("image_file", ""),
                })
        except Exception as e:
            logger.warning("MolDet failed on page %d: %s", page_idx + 1, e)

        img_path.unlink(missing_ok=True)

    doc.close()
    return results
