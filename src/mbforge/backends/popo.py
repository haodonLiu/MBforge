"""MinerU-Popo backend — OCR output post-processing.

MinerU-Popo (https://github.com/opendatalab/MinerU-Popo) bridges page-level
OCR (MinerU/MonkeyOCR/PaddleOCR-VL/GLM-OCR) and document-level semantic
structure. It performs:

- Table truncation analysis (跨页表格续接)
- Text truncation analysis (跨页段落续接)
- Title hierarchy analysis (heading 层级)
- Image-text association (图说关联)

The 4B Qwen3-VL-based model runs locally via HuggingFace transformers or
remotely via OpenAI-compatible API.

This module exposes a single ``apply_popo_postprocess`` function that takes
a page-level OCR markdown and returns the Popo-enhanced markdown.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from pathlib import Path

from ..utils.logger import get_logger

logger = get_logger(__name__)


POPO_REPO_URL = "https://github.com/opendatalab/MinerU-Popo.git"
# Local clone location (separate from MBForge source)
POPO_INSTALL_DIR = Path.home() / "mbforge" / "third_party" / "MinerU-Popo"


def popo_installed() -> bool:
    """Return True if the MinerU-Popo repo + its model are present locally."""
    if not POPO_INSTALL_DIR.exists():
        return False
    if not (POPO_INSTALL_DIR / "post_processing" / "model_utils.py").exists():
        return False
    model_path = os.environ.get("POPO_MODEL_PATH", "")
    if not model_path:
        # Default: under MBForge model cache
        from .moldet_v2_ft import default_model_dir

        candidate = default_model_dir() / "MinerU-Popo"
        return candidate.exists()
    return Path(model_path).exists()


def ensure_popo_installed() -> tuple[bool, str]:
    """Clone MinerU-Popo and download model weights. Returns (ok, message)."""
    if popo_installed():
        return True, "MinerU-Popo already installed"

    # 1. Clone repo
    try:
        POPO_INSTALL_DIR.parent.mkdir(parents=True, exist_ok=True)
        if not POPO_INSTALL_DIR.exists():
            logger.info("Cloning MinerU-Popo into %s ...", POPO_INSTALL_DIR)
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth=1",
                    POPO_REPO_URL,
                    str(POPO_INSTALL_DIR),
                ],
                check=True,
                timeout=300,
            )
    except Exception as exc:  # noqa: BLE001
        return False, f"git clone failed: {exc}"

    # 2. Download model from ModelScope (faster in CN than HuggingFace)
    try:
        from modelscope import snapshot_download
    except ImportError:
        return False, "modelscope not installed; run: uv add modelscope"

    try:
        from .moldet_v2_ft import default_model_dir

        dest = default_model_dir() / "MinerU-Popo"
        dest.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading MinerU-Popo weights from ModelScope to %s ...", dest)
        snapshot_download(
            "DreamEternal/MinerU-Popo",
            local_dir=str(dest),
            allow_patterns=[
                "*.json",
                "*.txt",
                "*.jinja",
                "*.md",
                "*.safetensors",
            ],
        )
        os.environ["POPO_MODEL_PATH"] = str(dest)
    except Exception as exc:  # noqa: BLE001
        return False, f"modelscope download failed: {exc}"

    return True, "MinerU-Popo installed"


def popo_postprocess_markdown(
    md_text: str,
    *,
    image_b64: str | None = None,
    timeout_s: int = 600,
) -> str | None:
    """Run MinerU-Popo on a markdown blob.

    Args:
        md_text: OCR-extracted markdown text.
        image_b64: Optional base64 PNG of the first page (used when Popo
            expects a screenshot — most callsites pass None).
        timeout_s: Wall-clock timeout for the popo_generate subprocess.

    Returns:
        Enhanced markdown, or None if Popo is unavailable / failed.
    """
    if not popo_installed():
        logger.warning("MinerU-Popo not installed; skipping post-process")
        return None

    model_path = os.environ.get(
        "POPO_MODEL_PATH",
        str(POPO_INSTALL_DIR.parent.parent / "models" / "MinerU-Popo"),
    )

    # We do NOT call MinerU-Popo's `popo_generate` directly because it has
    # upstream bugs (missing chat_template on AutoProcessor). Instead, run our
    # own driver that loads model + processor with the chat template
    # explicitly injected.
    driver = POPO_INSTALL_DIR / "_mbforge_driver.py"
    driver.write_text(
        f"""
import os, sys, json
os.environ['POPO_INFERENCE_BACKEND'] = 'transformers'
os.environ['POPO_MODEL_PATH'] = r'{model_path}'

import torch
from pathlib import Path
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

model_path = r'{model_path}'

# Load processor and inject chat template (upstream bug: missing)
processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
template_file = Path(model_path) / 'chat_template.jinja'
if template_file.exists():
    processor.chat_template = template_file.read_text(encoding='utf-8')
if hasattr(processor, 'tokenizer'):
    processor.tokenizer.padding_side = 'left'

# Load model
model = Qwen3VLForConditionalGeneration.from_pretrained(
    model_path,
    torch_dtype=torch.bfloat16,
    device_map='cuda:0' if torch.cuda.is_available() else 'cpu',
    trust_remote_code=True,
)
model.eval()

# Build multimodal content
content = []
if {image_b64!r}:
    content.append({{'type': 'image', 'image': f'data:image/jpeg;base64,{{{image_b64!r}}}'}})
content.append({{'type': 'text', 'text': sys.stdin.read()[:100000]}})
messages = [{{'role': 'user', 'content': content}}]

inputs = processor.apply_chat_template(
    messages, tokenize=True, add_generation_prompt=True,
    return_dict=True, return_tensors='pt',
)
inputs = inputs.to(model.device)

max_new = int(os.environ.get('POPO_MAX_NEW_TOKENS', '2048'))
with torch.no_grad():
    out = model.generate(**inputs, max_new_tokens=max_new, do_sample=False)

generated_ids = [
    out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, out)
]
result = processor.batch_decode(
    generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False,
)
print(result[0] if result else '')
""",
        encoding="utf-8",
    )

    try:
        proc = subprocess.run(
            [sys.executable, str(driver)],
            input=md_text,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(POPO_INSTALL_DIR),
        )
    except subprocess.TimeoutExpired:
        logger.error("MinerU-Popo timed out after %ds", timeout_s)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.error("MinerU-Popo invocation failed: %s", exc)
        return None
    finally:
        with contextlib.suppress(OSError):
            driver.unlink()

    if proc.returncode != 0:
        logger.error(
            "MinerU-Popo exited %d; stderr: %s",
            proc.returncode,
            proc.stderr[-500:] if proc.stderr else "",
        )
        return None

    return proc.stdout.strip() or None
