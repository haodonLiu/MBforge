"""
OKF Harness — End-to-end PDF → molecules DB with activity, OKF bundle.

Stages (each writes to out/{patent_id}/{stage}/ and logs/errors.jsonl):
  1. text       extract per-page text via pypdf
  2. render     render pages to PNG via sidecar
  3. coref      moldet + molscribe + ocr + coref via sidecar → per-page JSON
  4. llm        extract activity records from text via SenseNova (model poll)
  5. join       map LLM compound labels → coref bboxes/SMILES
  6. register   insert molecules + activity into molecules.db
  7. okf        write OKF bundle (index.md + per-entry .md)

Per CLAUDE.md:
  - fail loud (no silent skip)
  - surgical (reuses sidecar + sqlite, no new infra)
  - simplicity (one file)
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import logging
import os
import re
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import requests

# PyMuPDF for text extraction (already a server dep)
import fitz  # type: ignore


# ─── Config ────────────────────────────────────────────────────────────────

SIDECAR_URL = os.environ.get("MBFORGE_SIDECAR", "http://127.0.0.1:18792")
LLM_URL = os.environ.get("SENSENOVA_URL", "https://token.sensenova.cn/v1/chat/completions")
LLM_KEY = os.environ.get(
    "SENSENOVA_KEY", "sk-J2BtXkGi9JrTWVhjfCx2TyUayC1HDOJH"
)
LLM_MODELS = ["sensenova-6.7-flash-lite", "deepseek-v4-flash"]

# PaddleOCR-VL (fallback for scanned PDFs)
PADDLE_JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
PADDLE_TOKEN = "947fd81e4e52810d8755a23174d50cc5b1780944"
PADDLE_MODEL = "PaddleOCR-VL-1.6"


# ─── Logging ───────────────────────────────────────────────────────────────

def _make_logger(out_dir: Path) -> logging.Logger:
    log_path = out_dir / "harness.log"
    lg = logging.getLogger("okf_harness")
    lg.setLevel(logging.INFO)
    # avoid duplicate handlers if re-invoked
    if lg.handlers:
        return lg
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    lg.addHandler(fh)
    lg.addHandler(sh)
    return lg


# ─── Data classes ──────────────────────────────────────────────────────────

@dataclass
class CorefBox:
    category_id: int  # 1=mol, 3=identifier
    bbox: list[float]  # normalized [x1,y1,x2,y2]
    smiles: str | None = None
    text: str | None = None
    score: float = 0.0


@dataclass
class CorefPage:
    page: int
    width: int
    height: int
    bboxes: list[CorefBox] = field(default_factory=list)
    corefs: list[tuple[int, int]] = field(default_factory=list)
    error: str | None = None

    def mols(self) -> list[tuple[int, CorefBox]]:
        return [(i, b) for i, b in enumerate(self.bboxes) if b.category_id == 1]

    def idts(self) -> list[tuple[int, CorefBox]]:
        return [(i, b) for i, b in enumerate(self.bboxes) if b.category_id == 3]


@dataclass
class ActivityRecord:
    compound_label: str
    smiles: str | None
    assay: str | None
    target: str | None
    activity_type: str | None  # IC50 / EC50 / Ki / %inhibition / etc.
    value: float | None
    unit: str | None
    page: int | None
    quote: str
    raw: dict[str, Any] = field(default_factory=dict)


# ─── Per-stage error capture ───────────────────────────────────────────────

class ErrorLog:
    """Append-only JSONL of all errors per stage. Fail loud = always capture."""

    def __init__(self, out_dir: Path):
        self.path = out_dir / "errors.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, stage: str, msg: str, ctx: dict[str, Any] | None = None) -> None:
        entry = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "stage": stage,
            "msg": msg,
            "ctx": ctx or {},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ─── Stage 1: text extraction ──────────────────────────────────────────────

def stage_text(
    pdf_path: Path, out_dir: Path, err: ErrorLog, lg: logging.Logger
) -> dict[int, str]:
    """Extract text per page. fitz first; if scanned (no text layer), PaddleOCR-VL fallback."""
    text_dir = out_dir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    pages: dict[int, str] = {}
    try:
        doc = fitz.open(str(pdf_path))
        total = doc.page_count
        for i, page in enumerate(doc, start=1):
            try:
                t = page.get_text("text") or ""
            except Exception as e:
                err.record("text", f"page {i} fitz extract failed", {"err": str(e)})
                t = ""
            pages[i] = t
            (text_dir / f"{i:04d}.txt").write_text(t, encoding="utf-8")
        doc.close()
    except Exception as e:
        err.record("text", f"fitz open failed: {e}", {"pdf": str(pdf_path)})
        raise
    nonempty = sum(1 for v in pages.values() if v.strip())
    lg.info("text: %d pages, %d non-empty (fitz)", total, nonempty)
    # Fallback if scanned: use PaddleOCR-VL on full PDF
    if nonempty < total * 0.3:
        lg.info("text: fitz mostly empty (%d/%d), falling back to PaddleOCR-VL", nonempty, total)
        try:
            ocr_pages = paddle_ocr_pdf(pdf_path, out_dir, err, lg)
        except Exception as e:
            err.record("text", f"PaddleOCR-VL fallback failed: {e}")
            return pages
        # Replace empty pages with OCR markdown
        for i, md in ocr_pages.items():
            if not (pages.get(i) or "").strip() and md.strip():
                pages[i] = md
                (text_dir / f"{i:04d}.txt").write_text(md, encoding="utf-8")
        nonempty2 = sum(1 for v in pages.values() if v.strip())
        lg.info("text: %d/%d non-empty after PaddleOCR-VL", nonempty2, total)
    return pages


def paddle_ocr_pdf(
    pdf_path: Path, out_dir: Path, err: ErrorLog, lg: logging.Logger
) -> dict[int, str]:
    """Submit PDF to PaddleOCR-VL, poll, return {page_num: markdown}."""
    headers = {"Authorization": f"bearer {PADDLE_TOKEN}"}
    data = {
        "model": PADDLE_MODEL,
        "optionalPayload": json.dumps(
            {"useDocOrientationClassify": False, "useDocUnwarping": False, "useChartRecognition": False}
        ),
    }
    lg.info("paddle: submitting %s", pdf_path.name)
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        r = requests.post(PADDLE_JOB_URL, headers=headers, data=data, files=files, timeout=120)
    r.raise_for_status()
    job = r.json()
    if job.get("code", 0) != 0 and "data" not in job:
        raise RuntimeError(f"PaddleOCR submit error: {job}")
    job_id = job["data"]["jobId"]
    lg.info("paddle: jobId=%s", job_id)
    # Poll
    t0 = time.time()
    jsonl_url = ""
    while time.time() - t0 < 1800:  # 30 min cap
        rr = requests.get(f"{PADDLE_JOB_URL}/{job_id}", headers=headers, timeout=60)
        rr.raise_for_status()
        jd = rr.json()["data"]
        state = jd.get("state")
        if state == "done":
            jsonl_url = jd["resultUrl"]["jsonUrl"]
            lg.info("paddle: done, jsonUrl=%s", jsonl_url[:80])
            break
        if state == "failed":
            raise RuntimeError(f"PaddleOCR job failed: {jd.get('errorMsg')}")
        ep = jd.get("extractProgress") or {}
        lg.info(
            "paddle: state=%s pages=%s/%s",
            state, ep.get("extractedPages"), ep.get("totalPages"),
        )
        time.sleep(8)
    if not jsonl_url:
        raise RuntimeError("PaddleOCR job timed out")
    # Fetch JSONL — PaddleOCR-VL often returns Chinese in GBK; re-decode per line
    resp = requests.get(jsonl_url, timeout=180)
    resp.raise_for_status()
    raw_bytes = resp.content
    pages: dict[int, str] = {}
    page_num = 0
    for raw_line in raw_bytes.splitlines():
        if not raw_line.strip():
            continue
        # Try UTF-8 first; on mojibake markers fall back to GB18030
        for enc in ("utf-8", "gb18030"):
            try:
                line = raw_line.decode(enc)
                # mojibake sentinel: characters that only appear when bytes are mis-decoded
                if "�" in line or any(c in line for c in ("ʵ", "ʩ", "��")):
                    if enc == "utf-8":
                        continue  # try GB18030
                break
            except UnicodeDecodeError:
                if enc == "utf-8":
                    continue
                line = raw_line.decode("utf-8", errors="replace")
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            err.record("paddle", f"jsonl line parse failed: {e}", {"line": line[:120]})
            continue
        for res in rec.get("result", {}).get("layoutParsingResults", []):
            md = res.get("markdown", {}).get("text", "")
            if md:
                pages[page_num + 1] = md  # 1-based page
                page_num += 1
    lg.info("paddle: extracted %d pages", len(pages))
    return pages


# ─── Stage 2: page render ──────────────────────────────────────────────────

def stage_render(
    pdf_path: Path,
    out_dir: Path,
    sidecar: str,
    err: ErrorLog,
    lg: logging.Logger,
    max_pages: int = 200,
) -> list[tuple[int, Path]]:
    """Render via sidecar /api/v1/pdf/render-pages. Returns (page, png_path)."""
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Get page count via fitz
    try:
        doc = fitz.open(str(pdf_path))
        total = doc.page_count
        doc.close()
    except Exception as e:
        err.record("render", "page count failed", {"err": str(e)})
        raise

    total = min(total, max_pages)
    results: list[tuple[int, Path]] = []
    BATCH = 16
    for start in range(1, total + 1, BATCH):
        chunk = list(range(start, min(start + BATCH, total + 1)))
        try:
            r = requests.post(
                f"{sidecar}/api/v1/pdf/render-pages",
                json={"pdf_path": str(pdf_path), "page_numbers": chunk, "dpi": 200},
                timeout=180,
            )
            r.raise_for_status()
            for shot in r.json().get("screenshots", []):
                p = shot["page_num"]
                path = pages_dir / f"{p:04d}.png"
                path.write_bytes(base64.b64decode(shot["image_base64"]))
                results.append((p, path))
        except Exception as e:
            err.record("render", f"batch {chunk[0]}-{chunk[-1]} failed", {"err": str(e)})
            # fall through; do not raise — keep partial results
    lg.info("render: %d pages saved", len(results))
    return sorted(results, key=lambda x: x[0])


# ─── Stage 3: moldet (batch) + molscribe (per crop) ───────────────────────

def _molscribe_one(args) -> tuple[int, int, str | None, str | None]:
    """Worker: molscribe on one crop. Returns (page, idx, smiles, err)."""
    p, idx, crop_path, sidecar = args
    try:
        cb = base64.b64encode(Path(crop_path).read_bytes()).decode()
        r = requests.post(
            f"{sidecar}/api/v1/molscribe",
            json={"image_base64": cb, "ext": "png"},
            timeout=120,
        )
        r.raise_for_status()
        ms = r.json()
        esmiles = (ms.get("esmiles") or "").strip()
        if esmiles and "*" not in esmiles[:20] and len(esmiles) < 1500:
            return p, idx, esmiles, None
        return p, idx, None, "empty_or_garbage"
    except Exception as e:
        return p, idx, None, str(e)


def stage_moldet(
    page_paths: list[tuple[int, Path]],
    out_dir: Path,
    sidecar: str,
    err: ErrorLog,
    lg: logging.Logger,
    parallel: int = 4,
) -> list[CorefPage]:
    """Phase A: moldet+ocr (no molscribe) for all pages, parallel. Caches to coref/{p}.json."""
    from concurrent.futures import ThreadPoolExecutor

    coref_dir = out_dir / "coref"
    coref_dir.mkdir(parents=True, exist_ok=True)

    def _run(p_png: tuple[int, Path]) -> CorefPage:
        p, png = p_png
        cp_path = coref_dir / f"{p:04d}.json"
        # Cache hit (skip molscribe-populated to avoid re-call)
        if cp_path.exists():
            try:
                d = json.loads(cp_path.read_text(encoding="utf-8"))
                boxes = [
                    CorefBox(
                        category_id=int(b["category_id"]),
                        bbox=list(b["bbox"]),
                        smiles=b.get("smiles"),
                        text=b.get("text"),
                        score=float(b.get("score", 0.0)),
                    )
                    for b in d.get("bboxes", [])
                ]
                return CorefPage(
                    page=p,
                    width=int(d.get("image_width", 0)),
                    height=int(d.get("image_height", 0)),
                    bboxes=boxes,
                    corefs=[(int(a), int(b)) for a, b in d.get("corefs", [])],
                )
            except Exception:
                pass
        try:
            b64 = base64.b64encode(png.read_bytes()).decode()
            r = requests.post(
                f"{sidecar}/api/v1/moldet/coref",
                json={"image_base64": b64, "use_molscribe": False, "use_ocr": True},
                timeout=300,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            err.record("moldet", f"page {p} failed", {"err": str(e)})
            return CorefPage(page=p, width=0, height=0, error=str(e))

        boxes: list[CorefBox] = []
        for b in data.get("bboxes", []):
            try:
                boxes.append(
                    CorefBox(
                        category_id=int(b["category_id"]),
                        bbox=list(b["bbox"]),
                        smiles=None,
                        text=b.get("text"),
                        score=float(b.get("score", 0.0)),
                    )
                )
            except Exception as e:
                err.record("moldet", f"page {p} bbox parse failed", {"err": str(e), "b": b})

        pairs: list[tuple[int, int]] = []
        for pair in data.get("corefs", []):
            try:
                pairs.append((int(pair[0]), int(pair[1])))
            except Exception as e:
                err.record("moldet", f"page {p} coref pair parse failed", {"err": str(e)})

        cp = CorefPage(
            page=p,
            width=int(data.get("image_width", 0)),
            height=int(data.get("image_height", 0)),
            bboxes=boxes,
            corefs=pairs,
        )
        cp_path.write_text(
            json.dumps(
                {
                    "page": p,
                    "image_width": cp.width,
                    "image_height": cp.height,
                    "bboxes": [asdict(b) for b in boxes],
                    "corefs": pairs,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return cp

    out: list[CorefPage] = []
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        for cp in ex.map(_run, page_paths):
            out.append(cp)
    out.sort(key=lambda c: c.page)
    ok = sum(1 for c in out if c.error is None)
    lg.info("moldet: %d/%d pages ok", ok, len(out))
    return out


def stage_molscribe(
    coref_pages: list[CorefPage],
    page_paths: list[tuple[int, Path]],
    out_dir: Path,
    sidecar: str,
    err: ErrorLog,
    lg: logging.Logger,
    parallel: int = 2,
    pad_frac: float = 0.10,
) -> list[CorefPage]:
    """Phase B: crop + molscribe per category_id=1 bbox, parallel. Mutates in place."""
    from concurrent.futures import ThreadPoolExecutor
    from PIL import Image

    crops_dir = out_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    page_png = {p: path for p, path in page_paths}
    work: list[tuple[int, int, Path]] = []
    img_cache: dict[int, Image.Image] = {}
    for cp in coref_pages:
        for idx, b in enumerate(cp.bboxes):
            if b.category_id != 1 or b.smiles:
                continue
            p = cp.page
            if p not in page_png:
                continue
            try:
                if p not in img_cache:
                    img_cache[p] = Image.open(page_png[p])
                img = img_cache[p]
                iw, ih = img.size
                x1, y1, x2, y2 = b.bbox
                w, h = x2 - x1, y2 - y1
                pad_x, pad_y = w * pad_frac, h * pad_frac
                x1e, y1e = max(0.0, x1 - pad_x), max(0.0, y1 - pad_y)
                x2e, y2e = min(1.0, x2 + pad_x), min(1.0, y2 + pad_y)
                px1, py1 = max(0, int(x1e * iw)), max(0, int(y1e * ih))
                px2, py2 = min(iw, int(x2e * iw)), min(ih, int(y2e * ih))
                if px2 - px1 < 8 or py2 - py1 < 8:
                    continue
                crop = img.crop((px1, py1, px2, py2))
                crop_path = crops_dir / f"page_{p:04d}_mol_{idx:03d}.png"
                crop.save(crop_path)
                work.append((p, idx, crop_path))
            except Exception as e:
                err.record("molscribe", f"page {p} crop {idx} failed", {"err": str(e)})

    page_to_cp = {cp.page: cp for cp in coref_pages}

    def _assign(result):
        p, idx, smi, e = result
        cp = page_to_cp.get(p)
        if not cp:
            return
        if smi:
            cp.bboxes[idx].smiles = smi
        elif e and e != "empty_or_garbage":
            err.record("molscribe", f"page {p} mol {idx}", {"err": e})

    args = [(p, idx, str(cp_path), sidecar) for p, idx, cp_path in work]
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        for r in ex.map(_molscribe_one, args):
            _assign(r)

    for cp in coref_pages:
        cp_path = out_dir / "coref" / f"{cp.page:04d}.json"
        cp_path.write_text(
            json.dumps(
                {
                    "page": cp.page,
                    "image_width": cp.width,
                    "image_height": cp.height,
                    "bboxes": [asdict(b) for b in cp.bboxes],
                    "corefs": cp.corefs,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    smiles_n = sum(1 for c in coref_pages for b in c.bboxes if b.smiles)
    lg.info("molscribe: %d/%d crops done with SMILES", smiles_n, len(work))
    return coref_pages


# ─── Stage 4: LLM extract activity ────────────────────────────────────────

ACTIVITY_PROMPT = """You are a patent-parsing assistant. Read the following text from one page of a pharmaceutical patent (may be in Chinese OR English) and extract EVERY quantitative activity record (IC50, EC50, Ki, Kd, GI50, MIC, %inhibition, %activity, ED50, LD50, etc.) for EVERY named compound.

Output rules (STRICT):
- Return JSON only. No markdown fence. No prose before/after.
- Schema: {{"records":[{{"compound_label":"<string>","activity_type":"<IC50|EC50|Ki|Kd|GI50|MIC|%inhibition|%activity|ED50|other>","value":<number|null>,"unit":"<nM|uM|uM|%|ug/mL|mg/kg|other>","assay":"<cell-line / enzyme / target / 'cell-based IP1 assay'>","target":"<protein name or null>","quote":"<verbatim sentence/clause>"}}]}}
- `compound_label` is the compound's figure-label or table-编号 as it appears in the text (e.g. "1", "1a", "I-3", "实施例1", "化合物1"). Use the SHORTEST label that uniquely identifies the compound within the patent.
- Tables: PaddleOCR emits <table>...<tr><td>...</td></tr>...</table> — parse EVERY row: each (compound_label, value) cell pair is one record.
- "抑制活性" / "inhibitory activity" / "MRGPRX2抑制活性" → target="MRGPRX2", assay="cell-based IP1 assay" (or whatever the text says).
- IC50 values expressed as "< 500" or "<50 nM" — set value=number (e.g. 500), unit="nM", and put "<" in quote, OR if LLM can express it: value=500, quote="<500 nM".
- Values with explicit qualifier like "inactive", ">", ">10" — set value=number and include qualifier in quote.
- Skip claims (typically long legal language starting with numbered "1、" or "1."); focus on examples, tables, biological data.
- If no activity data is present on this page, return {{"records":[]}}.

PAGE {page}/{total_pages}
----- TEXT -----
{text}
----- END -----
"""


def llm_call(prompt: str, lg: logging.Logger, max_tokens: int = 4096) -> tuple[str, str]:
    """Call SenseNova with model polling. Returns (model_used, content)."""
    headers = {"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"}
    last_err: Exception | None = None
    for model in LLM_MODELS:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        try:
            r = requests.post(LLM_URL, headers=headers, json=body, timeout=180)
            r.raise_for_status()
            j = r.json()
            content = j["choices"][0]["message"]["content"]
            lg.info("llm: model=%s prompt_tokens=%s",
                    model, j.get("usage", {}).get("prompt_tokens"))
            return model, content
        except Exception as e:
            last_err = e
            lg.warning("llm: model=%s failed: %s", model, e)
            continue
    raise RuntimeError(f"All LLM models failed: {last_err}")


def _extract_json(text: str) -> Any:
    """Tolerantly find first JSON object/array in text."""
    text = text.strip()
    if text.startswith("```"):
        # strip code fence
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    # try direct
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # find first balanced { ... }
    for opener, closer in [("{", "}"), ("[", "]")]:
        start = text.find(opener)
        if start < 0:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    cand = text[start : i + 1]
                    try:
                        return json.loads(cand)
                    except json.JSONDecodeError:
                        continue
    raise ValueError(f"no valid JSON in LLM output: {text[:300]}")


def stage_llm(
    pages: dict[int, str],
    out_dir: Path,
    err: ErrorLog,
    lg: logging.Logger,
    page_batch: int = 1,
    max_pages: int | None = None,
) -> list[ActivityRecord]:
    """One LLM call per page (per-page accuracy)."""
    llm_dir = out_dir / "llm"
    llm_dir.mkdir(parents=True, exist_ok=True)
    records: list[ActivityRecord] = []
    page_items = sorted(pages.items())
    if max_pages:
        page_items = page_items[:max_pages]
    total = len(page_items)
    for idx, (p, text) in enumerate(page_items, start=1):
        if not text.strip():
            continue
        prompt = ACTIVITY_PROMPT.format(page=p, total_pages=total, text=text[:12_000])
        try:
            model, content = llm_call(prompt, lg)
        except Exception as e:
            err.record("llm", f"page {p} call failed", {"err": str(e)})
            continue
        (llm_dir / f"{p:04d}_raw.txt").write_text(content, encoding="utf-8")
        try:
            data = _extract_json(content)
        except Exception as e:
            err.record("llm", f"page {p} JSON parse failed", {"err": str(e), "raw_head": content[:200]})
            continue
        recs_raw = data.get("records", []) if isinstance(data, dict) else []
        for r in recs_raw:
            if not isinstance(r, dict):
                err.record("llm", f"page {p} non-dict record", {"r": r})
                continue
            label = str(r.get("compound_label") or "").strip()
            if not label:
                err.record("llm", f"page {p} missing compound_label", {"r": r})
                continue
            try:
                val = r.get("value")
                if val is not None and not isinstance(val, (int, float)):
                    val = float(val)
            except (TypeError, ValueError):
                val = None
            records.append(
                ActivityRecord(
                    compound_label=label,
                    smiles=r.get("smiles"),
                    assay=r.get("assay"),
                    target=r.get("target"),
                    activity_type=r.get("activity_type"),
                    value=val,
                    unit=r.get("unit"),
                    page=p,
                    quote=str(r.get("quote") or "")[:500],
                    raw=r,
                )
            )
    lg.info("llm: %d activity records across %d pages", len(records), total)
    (out_dir / "llm_records.json").write_text(
        json.dumps([asdict(r) for r in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return records


# ─── Stage 5: join LLM ↔ coref ─────────────────────────────────────────────

def stage_join(
    records: list[ActivityRecord],
    coref_pages: list[CorefPage],
    pages: dict[int, str],
    lg: logging.Logger,
) -> list[ActivityRecord]:
    """Map compound_label → SMILES via two strategies:
    1) direct label match in coref idt text (works if OCR caught compound numbers)
    2) cross-page: for activity records on a table page, find page that mentions
       '化合物<label>的制备' (preparation) and take SMILES from that page.
    """
    # Strategy 1: direct label → (smiles, page) from OCR idt text
    label_idx: dict[str, dict[str, Any]] = {}
    for cp in coref_pages:
        idt_by_idx = {i: b for i, b in enumerate(cp.bboxes) if b.category_id == 3}
        for i, b in enumerate(cp.bboxes):
            if b.category_id != 1:
                continue
            for mol_i, idt_i in cp.corefs:
                if mol_i != i:
                    continue
                idt = idt_by_idx.get(idt_i)
                if not idt or not idt.text:
                    continue
                txt = idt.text.strip()
                smi = (b.smiles or "").strip() or None
                if smi:
                    label_idx.setdefault(
                        txt, {"smiles": smi, "page": cp.page, "bbox": b.bbox}
                    )

    # Strategy 2: cross-page lookup. Build label → list of (page, smiles, bbox)
    # from any coref page where the label can be inferred from text "化合物 LABEL 的制备"
    prep_re = re.compile(
        r"化合物\s*([0-9]+[a-zA-Z]?)\s*的\s*制备|实施例\s*\d+[：:]\s*化合物\s*([0-9]+[a-zA-Z]?)",
        re.UNICODE,
    )
    # label → list of pages that "prepare" it
    prep_pages: dict[str, list[int]] = {}
    for p, t in pages.items():
        for m in prep_re.finditer(t or ""):
            lab = (m.group(1) or m.group(2) or "").strip()
            if lab:
                prep_pages.setdefault(lab, []).append(p)

    # Also build label → list of (smiles, page) from mols on each page (no idt pairing)
    page_mols: dict[int, list[CorefBox]] = {}
    for cp in coref_pages:
        page_mols[cp.page] = [b for b in cp.bboxes if b.category_id == 1 and b.smiles]

    matched = 0
    for r in records:
        if r.smiles:
            matched += 1
            continue
        lab = (r.compound_label or "").strip()
        # Strategy 1
        hit = label_idx.get(lab)
        if hit and hit["smiles"]:
            r.smiles = hit["smiles"]
            matched += 1
            continue
        # Strategy 2: find preparation page
        cand_pages = prep_pages.get(lab, [])
        for cp_p in cand_pages:
            mols = page_mols.get(cp_p, [])
            if len(mols) == 1:
                r.smiles = mols[0].smiles
                matched += 1
                break
            elif len(mols) > 1:
                # heuristic: pick the mol whose bbox is roughly centered (often the "main" structure)
                mols.sort(key=lambda b: abs((b.bbox[0]+b.bbox[2])/2 - 0.5) + abs((b.bbox[1]+b.bbox[3])/2 - 0.5))
                r.smiles = mols[0].smiles
                matched += 1
                break
    lg.info("join: %d/%d records linked to coref SMILES", matched, len(records))
    if matched < len(records):
        miss = [r.compound_label for r in records if not r.smiles]
        lg.info("join misses: %s", miss[:10])
    return records


# ─── Stage 6: register to molecules.db ─────────────────────────────────────

MOL_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS molecules (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    smiles        TEXT    NOT NULL,
    esmiles       TEXT,
    name          TEXT,
    source_doc    TEXT,
    source_page   INTEGER,
    coref_label   TEXT,
    coref_bbox    TEXT,
    confidence    REAL,
    created_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mol_smiles ON molecules(smiles);

CREATE TABLE IF NOT EXISTS activities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    molecule_id   INTEGER NOT NULL,
    compound_label TEXT,
    activity_type TEXT,
    value         REAL,
    unit          TEXT,
    assay         TEXT,
    target        TEXT,
    source_page   INTEGER,
    quote         TEXT,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (molecule_id) REFERENCES molecules(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_act_mol ON activities(molecule_id);
"""


def stage_register(
    records: list[ActivityRecord],
    pdf_path: Path,
    project_dir: Path,
    err: ErrorLog,
    lg: logging.Logger,
) -> dict[str, int]:
    """Insert/upsert molecules + activities into project_dir/.mbforge/index/molecules.db."""
    idx_dir = project_dir / ".mbforge" / "index"
    idx_dir.mkdir(parents=True, exist_ok=True)
    db_path = idx_dir / "molecules.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(MOL_DB_SCHEMA)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    src = str(pdf_path.resolve())
    n_mol = 0
    n_act = 0
    for r in records:
        smi = (r.smiles or "").strip()
        if not smi:
            # log records without SMILES — OKF bundle still has them
            err.record("register", "record skipped: no SMILES", {"label": r.compound_label, "page": r.page})
            continue
        cur = conn.execute("SELECT id FROM molecules WHERE smiles = ?", (smi,))
        row = cur.fetchone()
        if row:
            mol_id = row[0]
        else:
            cur = conn.execute(
                """INSERT INTO molecules
                   (smiles, esmiles, name, source_doc, source_page,
                    coref_label, coref_bbox, confidence, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    smi,
                    None,
                    r.compound_label,
                    src,
                    r.page,
                    r.compound_label,
                    None,
                    None,
                    now,
                ),
            )
            mol_id = cur.lastrowid
            n_mol += 1
        conn.execute(
            """INSERT INTO activities
               (molecule_id, compound_label, activity_type, value, unit,
                assay, target, source_page, quote, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                mol_id,
                r.compound_label,
                r.activity_type,
                r.value,
                r.unit,
                r.assay,
                r.target,
                r.page,
                r.quote,
                now,
            ),
        )
        n_act += 1
    conn.commit()
    conn.close()
    lg.info("register: %d new mols, %d activities → %s", n_mol, n_act, db_path)
    return {"new_molecules": n_mol, "activities": n_act, "db": str(db_path)}


# ─── Stage 7: OKF bundle ──────────────────────────────────────────────────

def stage_okf(
    records: list[ActivityRecord],
    pages: dict[int, str],
    pdf_path: Path,
    patent_id: str,
    out_dir: Path,
    lg: logging.Logger,
) -> Path:
    """Write OKF bundle: index.md + per-entry .md. OKF v0.1: frontmatter only."""
    bundle = out_dir / "okf"
    bundle.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    # Dedup molecules by SMILES for index
    mols_seen: dict[str, dict[str, Any]] = {}
    for r in records:
        smi = (r.smiles or "").strip()
        if not smi:
            continue
        mols_seen.setdefault(
            smi,
            {
                "smiles": smi,
                "labels": set(),
                "pages": set(),
                "activities": [],
            },
        )
        mols_seen[smi]["labels"].add(r.compound_label)
        if r.page:
            mols_seen[smi]["pages"].add(r.page)
        mols_seen[smi]["activities"].append(
            {k: v for k, v in asdict(r).items() if k != "raw"}
        )

    # Write per-molecule .md
    for slug, m in mols_seen.items():
        labels = sorted(m["labels"])
        first_label = labels[0]
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", first_label)[:60] or "mol"
        path = bundle / "molecules" / f"{safe}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        front = {
            "type": "molecule",
            "title": f"Compound {first_label}",
            "resource": str(pdf_path.resolve()),
            "tags": ["okf:0.1", "patent:" + patent_id],
            "timestamp": now,
            "smiles": m["smiles"],
            "labels": labels,
            "pages": sorted(m["pages"]),
        }
        body_lines = [
            f"# {first_label}",
            "",
            f"- SMILES: `{m['smiles']}`",
            f"- Labels: {', '.join(labels)}",
            f"- Pages: {sorted(m['pages'])}",
            "",
            "## Activities",
            "",
        ]
        for a in m["activities"]:
            val = a.get("value")
            unit = a.get("unit") or ""
            atype = a.get("activity_type") or "?"
            body_lines.append(f"- **{atype}** = {val}{unit} — assay: {a.get('assay') or '?'} — page {a.get('page')}")
            if a.get("quote"):
                body_lines.append(f"  - > {a['quote'][:200]}")
        content = "---\n" + json.dumps(front, ensure_ascii=False) + "\n---\n\n" + "\n".join(body_lines) + "\n"
        path.write_text(content, encoding="utf-8")

    # Write patent index
    index_path = bundle / "index.md"
    front = {
        "okf_version": "0.1",
        "type": "index",
        "title": f"Patent {patent_id}",
        "resource": str(pdf_path.resolve()),
        "tags": ["okf:0.1", "patent:" + patent_id],
        "timestamp": now,
        "molecule_count": len(mols_seen),
        "activity_count": len(records),
    }
    body = ["# Patent " + patent_id, "", "## Molecules", ""]
    for slug, m in mols_seen.items():
        first_label = sorted(m["labels"])[0]
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", first_label)[:60] or "mol"
        body.append(f"- [{first_label}](molecules/{safe}.md) — `{m['smiles'][:60]}`")
    body.append("")
    content = "---\n" + json.dumps(front, ensure_ascii=False) + "\n---\n\n" + "\n".join(body) + "\n"
    index_path.write_text(content, encoding="utf-8")
    lg.info("okf: bundle written → %s", bundle)
    return bundle


# ─── Driver ────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="PDF → OKF + molecules DB")
    ap.add_argument("pdf", type=Path, help="path to PDF (e.g. WO2026037254A1.PDF)")
    ap.add_argument("--out", type=Path, default=Path("out"), help="output root")
    ap.add_argument("--project", type=Path, default=Path("out/_project"),
                    help="project dir (gets .mbforge/index/molecules.db)")
    ap.add_argument("--sidecar", default=SIDECAR_URL, help="sidecar base URL")
    ap.add_argument("--max-pages", type=int, default=200, help="max PDF pages to process")
    ap.add_argument("--moldet-workers", type=int, default=4, help="parallel moldet+ocr workers")
    ap.add_argument("--molscribe-workers", type=int, default=2, help="parallel molscribe workers (per crop)")
    args = ap.parse_args()

    pdf: Path = args.pdf.resolve()
    if not pdf.exists():
        print(f"FATAL: PDF not found: {pdf}", file=sys.stderr)
        return 2
    patent_id = re.sub(r"[^A-Za-z0-9]+", "", pdf.stem)[:32] or "patent"
    out_dir = (args.out / patent_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    project_dir = args.project.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    err = ErrorLog(out_dir)
    lg = _make_logger(out_dir)
    lg.info("harness start pdf=%s out=%s", pdf, out_dir)

    t0 = time.time()
    try:
        pages = stage_text(pdf, out_dir, err, lg)
        page_paths = stage_render(pdf, out_dir, args.sidecar, err, lg, max_pages=args.max_pages)
        coref_pages = stage_moldet(page_paths, out_dir, args.sidecar, err, lg, parallel=args.moldet_workers)
        coref_pages = stage_molscribe(coref_pages, page_paths, out_dir, args.sidecar, err, lg, parallel=args.molscribe_workers)
        records = stage_llm(pages, out_dir, err, lg, max_pages=args.max_pages)
        records = stage_join(records, coref_pages, pages, lg)
        reg = stage_register(records, pdf, project_dir, err, lg)
        bundle = stage_okf(records, pages, pdf, patent_id, out_dir, lg)
    except Exception as e:
        err.record("fatal", str(e), {"trace": True})
        lg.exception("harness failed: %s", e)
        return 1

    summary = {
        "patent_id": patent_id,
        "pages_text": len(pages),
        "pages_rendered": len(page_paths),
        "pages_with_coref": sum(1 for c in coref_pages if c.error is None),
        "mols_with_smiles": sum(1 for c in coref_pages for b in c.bboxes if b.smiles),
        "activity_records": len(records),
        "register": reg,
        "okf_bundle": str(bundle),
        "errors_jsonl": str(err.path),
        "elapsed_s": round(time.time() - t0, 1),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lg.info("DONE %s", json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
