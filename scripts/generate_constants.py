#!/usr/bin/env python3
"""从 constants.yaml 生成 Rust 和 Python 常量文件.

用法:
    python scripts/generate_constants.py

生成:
    src-tauri/src/core/constants.rs
    src/mbforge/utils/constants.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
YAML_PATH = ROOT / "constants.yaml"
RUST_REF = ROOT / ".generated" / "rust_constants.rs"  # 参考文件，需人工合并到 constants.rs
PYTHON_OUT = ROOT / "src" / "mbforge" / "utils" / "constants.py"


def load_yaml() -> dict:
    with open(YAML_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Rust 生成
# ---------------------------------------------------------------------------

def generate_rust(data: dict) -> str:
    lines = []
    lines.append("// ============================================================")
    lines.append("// AUTO-GENERATED from constants.yaml — DO NOT EDIT MANUALLY")
    lines.append("// Run: python scripts/generate_constants.py")
    lines.append("// ============================================================")
    lines.append("")
    lines.append("use std::path::PathBuf;")
    lines.append("")
    lines.append("// NOTE: Keep in sync with src/mbforge/utils/constants.py (Python sidecar).")
    lines.append("// When changing a value here, update the corresponding Python constant.")
    lines.append("")

    # App
    lines.append(f'pub const APP_NAME: &str = "{data["app"]["name"]}";')
    lines.append(f'pub const APP_VERSION: &str = "{data["app"]["version"]}";')
    lines.append(f'pub const PROJECT_FORMAT_VERSION: u32 = {data["project"]["format_version"]};')
    lines.append(f'pub const PROJECT_META_DIR: &str = "{data["project"]["meta_dir"]}";')
    lines.append("")

    # Default models
    m = data["models"]
    lines.append(f'pub const DEFAULT_EMBED_MODEL: &str = "{m["default_embed"]}";')
    lines.append(f'pub const DEFAULT_RERANK_MODEL: &str = "{m["default_rerank"]}";')
    lines.append("")

    # HF mirror
    lines.append(f'pub const DEFAULT_HF_ENDPOINT: &str = "{m["default_hf_endpoint"]}";')
    lines.append("")

    # PDF
    p = data["pdf"]
    lines.append(f'pub const PDF_CHUNK_SIZE: usize = {p["chunk_size"]};')
    lines.append(f'pub const PDF_CHUNK_OVERLAP: usize = {p["chunk_overlap"]};')
    lines.append("")

    # LLM
    l = data["llm"]
    lines.append(f'pub const LLM_MAX_TOKENS: u32 = {l["max_tokens"]};')
    lines.append(f'pub const LLM_TEMPERATURE: f32 = {l["temperature"]};')
    lines.append(f'pub const LLM_TOP_P: f32 = {l["top_p"]};')
    lines.append("")

    # Providers
    pv = data["providers"]
    lines.append(f'pub const PROVIDER_OPENAI_COMPATIBLE: &str = "{pv["openai_compatible"]}";')
    lines.append(f'pub const PROVIDER_ANTHROPIC: &str = "{pv["anthropic"]}";')
    lines.append(f'pub const PROVIDER_QWEN3: &str = "{pv["qwen3"]}";')
    lines.append(f'pub const PROVIDER_SENTENCE_TRANSFORMERS: &str = "{pv["sentence_transformers"]}";')
    lines.append(f'pub const PROVIDER_OLLAMA: &str = "{pv["ollama"]}";')
    lines.append(f'pub const PROVIDER_API: &str = "{pv["api"]}";')
    lines.append(f'pub const PROVIDER_LOCAL: &str = "{pv["local"]}";')
    lines.append("")

    # Directories
    d = data["directories"]
    lines.append(f'pub const MEMORY_DIR: &str = "{d["memory"]}";')
    lines.append(f'pub const TRAJECTORY_DIR: &str = "{d["trajectory"]}";')
    lines.append(f'pub const TRAJECTORY_FILE: &str = "{d["trajectory_file"]}";')
    lines.append(f'pub const SUMMARY_DIR: &str = "{d["summary"]}";')
    lines.append(f'pub const INDEX_FILE: &str = "{d["index_file"]}";')
    lines.append(f'pub const SETTINGS_FILE: &str = "{d["settings_file"]}";')
    lines.append(f'pub const MOL_DB_FILENAME: &str = "{d["mol_db_filename"]}";')
    lines.append("")

    # Sidecar
    sc = data["sidecar"]
    lines.append(f'pub const DEFAULT_SIDECAR_PORT: u16 = {sc["default_port"]};')
    lines.append(f'pub const DEFAULT_SIDECAR_URL: &str = "{sc["default_url"]}";')
    lines.append("")

    # Extensions (Rust: no dot)
    doc_exts = ", ".join(f'"{e}"' for e in data["supported_doc_exts"])
    mol_exts = ", ".join(f'"{e}"' for e in data["supported_mol_exts"])
    lines.append(f"pub const SUPPORTED_DOC_EXTS: &[&str] = &[{doc_exts}];")
    lines.append(f"pub const SUPPORTED_MOL_EXTS: &[&str] = &[{mol_exts}];")
    lines.append("")

    # Rust-only constants (Tauri events, agent config)
    lines.append("// ===== Rust-only constants (not shared with Python) =====")
    lines.append("")
    lines.append("// Metadata keys")
    lines.append('pub const META_SOURCE: &str = "source";')
    lines.append('pub const META_FILENAME: &str = "filename";')
    lines.append('pub const META_DOC_ID: &str = "doc_id";')
    lines.append("")
    lines.append("// Tauri IPC event names")
    lines.append('pub const EVT_DOC_PROGRESS: &str = "doc-progress";')
    lines.append('pub const EVT_DOC_RESULT: &str = "doc-result";')
    lines.append('pub const EVT_SIDECAR_LOG: &str = "sidecar://log";')
    lines.append('pub const EVT_SIDECAR_STATUS: &str = "sidecar://status";')
    lines.append('pub const EVT_AGENT_STREAM_CHUNK: &str = "agent-stream-chunk";')
    lines.append('pub const EVT_AGENT_STREAM_DONE: &str = "agent-stream-done";')
    lines.append('pub const EVT_KB_SEARCH_CHUNK: &str = "kb-search-chunk";')
    lines.append('pub const EVT_MODEL_DOWNLOAD_PROGRESS: &str = "model-download-progress";')
    lines.append('pub const EVT_INGEST_PROGRESS: &str = "ingest-progress";')
    lines.append('pub const EVT_INGEST_QUEUE_UPDATE: &str = "ingest-queue-update";')
    lines.append('pub const EVT_INGEST_WORKER_HEARTBEAT: &str = "ingest-worker-heartbeat";')
    lines.append("")
    lines.append("// Agent config")
    lines.append("pub const AGENT_MAX_ITERATIONS: usize = 5;")
    lines.append("pub const AGENT_MAX_HISTORY_ROUNDS: usize = 20;")
    lines.append("pub const AGENT_MAX_TOTAL_TOKENS: usize = 32000;")
    lines.append("")
    lines.append("// Embedding base URL (same as sidecar URL)")
    lines.append(f'pub const DEFAULT_EMBED_BASE_URL: &str = "{sc["default_url"]}";')
    lines.append("")

    # Path functions
    lines.append("// ===== Path helpers =====")
    lines.append("")
    lines.append("pub fn sidecar_url() -> String {")
    lines.append('    std::env::var("MBFORGE_SIDECAR_URL").unwrap_or_else(|_| DEFAULT_SIDECAR_URL.to_string())')
    lines.append("}")
    lines.append("")
    lines.append("pub fn model_cache_dir() -> PathBuf {")
    lines.append('    if let Ok(dir) = std::env::var("MBFORGE_MODEL_CACHE_DIR") {')
    lines.append("        return PathBuf::from(dir);")
    lines.append("    }")
    lines.append("    if let Some(home) = directories::UserDirs::new().map(|u| u.home_dir().to_path_buf()) {")
    lines.append('        return home.join("mbforge").join("models");')
    lines.append("    }")
    lines.append('    PathBuf::from("mbforge/models")')
    lines.append("}")
    lines.append("")
    lines.append("pub fn global_config_dir() -> PathBuf {")
    lines.append("    directories::ProjectDirs::from(\"\", \"\", \"MBForge\")")
    lines.append("        .map(|d| d.config_dir().to_path_buf())")
    lines.append("        .unwrap_or_else(|| PathBuf::from(\".\").join(\".config\").join(\"MBForge\"))")
    lines.append("}")
    lines.append("")
    lines.append("pub fn global_data_dir() -> PathBuf {")
    lines.append("    directories::ProjectDirs::from(\"\", \"\", \"MBForge\")")
    lines.append("        .map(|d| d.data_dir().to_path_buf())")
    lines.append("        .unwrap_or_else(|| PathBuf::from(\".\").join(\".local\").join(\"share\").join(\"MBForge\"))")
    lines.append("}")
    lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Python 生成
# ---------------------------------------------------------------------------

def generate_python(data: dict) -> str:
    lines = []
    lines.append('"""MBForge 全局常量 — 从 constants.yaml 自动生成."""')
    lines.append("")
    lines.append("# ============================================================")
    lines.append("# AUTO-GENERATED from constants.yaml — DO NOT EDIT MANUALLY")
    lines.append("# Run: python scripts/generate_constants.py")
    lines.append("# ============================================================")
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("import os")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append("try:")
    lines.append("    from platformdirs import user_config_dir, user_data_dir")
    lines.append("except ImportError:")
    lines.append("    user_config_dir = user_data_dir = lambda *a, **kw: str(Path.home() / \".config\" / a[0] if a else \".config\")")
    lines.append("")
    lines.append("# NOTE: Keep in sync with src-tauri/src/core/constants.rs (Rust side).")
    lines.append("# When changing a value here, update the corresponding Rust constant.")
    lines.append("")

    # App
    a = data["app"]
    lines.append(f'APP_NAME = "{a["name"]}"')
    lines.append(f'APP_VERSION = "{a["version"]}"')
    lines.append(f'APP_AUTHOR = "{a["author"]}"')
    lines.append("")

    # Project
    p = data["project"]
    lines.append(f'PROJECT_FORMAT_VERSION = {p["format_version"]}')
    lines.append(f'PROJECT_META_DIR = "{p["meta_dir"]}"')
    lines.append("")

    # Directories
    d = data["directories"]
    lines.append(f'MEMORY_DIR = "{d["memory"]}"')
    lines.append(f'TRAJECTORY_DIR = "{d["trajectory"]}"')
    lines.append(f'TRAJECTORY_FILE = "{d["trajectory_file"]}"')
    lines.append(f'SUMMARY_DIR = "{d["summary"]}"')
    lines.append(f'INDEX_FILE = "{d["index_file"]}"')
    lines.append(f'SETTINGS_FILE = "{d["settings_file"]}"')
    lines.append(f'MOL_DB_FILENAME = "{d["mol_db_filename"]}"')
    lines.append(f'KB_COLLECTION_DOCS = "{d["kb_collection_docs"]}"')
    lines.append("")

    # Models
    m = data["models"]
    lines.append(f'DEFAULT_EMBED_MODEL = "{m["default_embed"]}"')
    lines.append(f'DEFAULT_RERANK_MODEL = "{m["default_rerank"]}"')
    lines.append(f'DEFAULT_HF_ENDPOINT = "{m["default_hf_endpoint"]}"')
    lines.append("")

    # Providers
    pv = data["providers"]
    lines.append(f'PROVIDER_OPENAI_COMPATIBLE = "{pv["openai_compatible"]}"')
    lines.append(f'PROVIDER_ANTHROPIC = "{pv["anthropic"]}"')
    lines.append(f'PROVIDER_QWEN3 = "{pv["qwen3"]}"')
    lines.append(f'PROVIDER_SENTENCE_TRANSFORMERS = "{pv["sentence_transformers"]}"')
    lines.append(f'PROVIDER_OLLAMA = "{pv["ollama"]}"')
    lines.append(f'PROVIDER_API = "{pv["api"]}"')
    lines.append(f'PROVIDER_LOCAL = "{pv["local"]}"')
    lines.append(f'OCR_PROVIDER_NONE = "{pv["ocr_none"]}"')
    lines.append("")

    # LLM
    l = data["llm"]
    lines.append(f'LLM_MAX_TOKENS = {l["max_tokens"]}')
    lines.append(f'LLM_TEMPERATURE = {l["temperature"]}')
    lines.append(f'LLM_TOP_P = {l["top_p"]}')
    lines.append("")

    # PDF
    p = data["pdf"]
    lines.append(f'PDF_CHUNK_SIZE = {p["chunk_size"]}')
    lines.append(f'PDF_CHUNK_OVERLAP = {p["chunk_overlap"]}')
    lines.append("")

    # Sidecar
    sc = data["sidecar"]
    lines.append(f'DEFAULT_SIDECAR_PORT = {sc["default_port"]}')
    lines.append(f'DEFAULT_SIDECAR_URL = "{sc["default_url"]}"')
    lines.append("")

    # Extensions (Python: with dot)
    doc_exts = ", ".join(f'".{e}"' for e in data["supported_doc_exts"])
    mol_exts = ", ".join(f'".{e}"' for e in data["supported_mol_exts"])
    lines.append(f"SUPPORTED_DOC_EXTS: set[str] = {{{doc_exts}}}")
    lines.append(f"SUPPORTED_MOL_EXTS: set[str] = {{{mol_exts}}}")
    lines.append("")

    # Python-only constants
    lines.append("# ===== Python-only constants (not shared with Rust) =====")
    lines.append("")
    lines.append("# Qwen3 Embedding/Reranker 指令前缀")
    lines.append('EMBED_INSTRUCTION_RETRIEVAL = "Given a web search query, retrieve relevant passages that answer the query"')
    lines.append('EMBED_INSTRUCTION_CLUSTER = "Given a document, retrieve relevant passages that are semantically similar"')
    lines.append('RERANK_DEFAULT_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"')
    lines.append("")

    # Path helpers
    lines.append("# ===== Path helpers =====")
    lines.append("")
    lines.append("GLOBAL_CONFIG_DIR = Path(user_config_dir(APP_NAME, APP_AUTHOR))")
    lines.append("GLOBAL_DATA_DIR = Path(user_data_dir(APP_NAME, APP_AUTHOR))")
    lines.append("")
    lines.append("")
    lines.append("def get_model_cache_dir() -> str:")
    lines.append('    """获取模型缓存目录（优先配置文件，其次默认路径）."""')
    lines.append("    try:")
    lines.append("        from .config import load_global_config")
    lines.append("        cfg = load_global_config()")
    lines.append("        if cfg.model_cache_dir:")
    lines.append("            # 展开前导 ~ 到用户主目录（兼容 Windows 和 Unix）")
    lines.append("            result = cfg.model_cache_dir")
    lines.append("            if result.startswith('~/') or result.startswith('~\\\\'):")
    lines.append("                return str(Path.home() / Path(result[2:]))")
    lines.append("            elif result == '~':")
    lines.append("                return str(Path.home())")
    lines.append("            return result")
    lines.append("    except Exception:")
    lines.append("        pass")
    lines.append("    return str(Path.home() / Path(MODEL_CACHE_DIR))")
    lines.append("")
    lines.append("")
    lines.append("# MODEL_CACHE_DIR is the relative path fragment used by get_model_cache_dir()")
    lines.append(f'MODEL_CACHE_DIR = "{m["cache_dir"]}"')
    lines.append("")
    lines.append("")
    lines.append("def ensure_hf_mirror() -> None:")
    lines.append('    """设置 HuggingFace 镜像环境变量（如果未设置）。"""')
    lines.append('    if not os.environ.get("HF_ENDPOINT"):')
    lines.append('        os.environ["HF_ENDPOINT"] = DEFAULT_HF_ENDPOINT')
    lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    data = load_yaml()

    # Generate Rust reference — constants.rs 已手动扩展，不再自动覆盖。
    # 将参考输出到 .generated/rust_constants.rs，由开发者 diff 后手动合并。
    RUST_REF.parent.mkdir(exist_ok=True)
    rust_code = generate_rust(data)
    RUST_REF.write_text(rust_code, encoding="utf-8")
    print(f"Generated Rust reference: {RUST_REF.relative_to(ROOT)}")
    print("  [WARNING] constants.rs is now manually maintained.")
    print("            Please diff and manually merge changes from the reference file.")

    # Generate Python — 完整覆盖（Python 侧无常量文件的手动扩展）
    python_code = generate_python(data)
    PYTHON_OUT.write_text(python_code, encoding="utf-8")
    print(f"Generated {PYTHON_OUT.relative_to(ROOT)}")

    print(f"\nSource: {YAML_PATH.relative_to(ROOT)}")
    print("Done. Run 'cargo check' and 'uv run python -c \"from mbforge.utils.constants import *\"' to verify.")


if __name__ == "__main__":
    main()
