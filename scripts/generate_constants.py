#!/usr/bin/env python3
"""MBForge constants codegen — single source of truth → Rust + Python.

Reads ``constants.yaml`` (project root) and emits:

  - ``src/mbforge/utils/constants.py``                       (overwritten)
  - ``<rust-out>/constants.rs``                              (YAML-derived only;
                                                              consumed by build.rs
                                                              via ``include!``)

The Rust output is YAML-derived ONLY. Rust-only constants and helpers
(Tauri event names, path helpers, project layout) live in
``src-tauri/crates/mbforge-infra/src/config/constants.rs`` by hand.

Usage:
    python scripts/generate_constants.py                 # write Python (default)
    python scripts/generate_constants.py --rust-out DIR  # also write Rust to DIR
    python scripts/generate_constants.py --check         # CI: exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # transitive dep (e.g. via openai). Add to dev deps if missing.
    sys.exit(
        "PyYAML not importable. Run `uv sync` or add `pyyaml` to pyproject.toml."
    )

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
YAML_PATH = REPO_ROOT / "configs" / "constants.yaml"
PY_OUT = REPO_ROOT / "src" / "mbforge" / "utils" / "constants.py"

# Version-sync targets. Each path contains a version string managed by
# `app.version` in constants.yaml. The kind controls sync/check behavior:
#   "toml-section:K"   — required to match; K is the TOML section header
#                        (e.g. "[workspace.package]") where `version` lives.
#                        Drift = hard fail.
#   "toml-section-opt:K" — like above but drift = warn only (Python sidecar
#                        can evolve as an independent crate, controlled by
#                        `app.sync_python_version` in YAML).
#   "json-top"         — required to match; updates top-level "version".
#                        Drift = hard fail.
VERSION_TARGETS: list[tuple[str, Path, str]] = [
    ("Cargo workspace", REPO_ROOT / "src-tauri" / "Cargo.toml", "toml-section:[workspace.package]"),
    ("Tauri config", REPO_ROOT / "src-tauri" / "crates" / "mbforge-app" / "tauri.conf.json", "json-top"),
    ("Frontend package", REPO_ROOT / "frontend" / "package.json", "json-top"),
    ("Python sidecar", REPO_ROOT / "pyproject.toml", "toml-section-opt:[project]"),
]

# ---------------------------------------------------------------------------
# Type registry — YAML key path → (Rust type, Python type)
# Every key in constants.yaml must appear here, or the script aborts.
# ---------------------------------------------------------------------------
TYPE_MAP: dict[str, tuple[str, str]] = {
    "app.name": ("&str", "str"),
    "app.version": ("&str", "str"),
    "app.author": ("&str", "str"),
    "project.format_version": ("u32", "int"),
    "project.meta_dir": ("&str", "str"),
    "directories.memory": ("&str", "str"),
    "directories.trajectory": ("&str", "str"),
    "directories.trajectory_file": ("&str", "str"),
    "directories.summary": ("&str", "str"),
    "directories.mol_db_filename": ("&str", "str"),
    "directories.kb_collection_docs": ("&str", "str"),
    "directories.index_file": ("&str", "str"),
    "directories.settings_file": ("&str", "str"),
    "models.default_embed": ("&str", "str"),
    "models.default_rerank": ("&str", "str"),
    "models.default_hf_endpoint": ("&str", "str"),
    "models.cache_dir": ("&str", "str"),
    "providers.openai_compatible": ("&str", "str"),
    "providers.anthropic": ("&str", "str"),
    "providers.qwen3": ("&str", "str"),
    "providers.sentence_transformers": ("&str", "str"),
    "providers.ollama": ("&str", "str"),
    "providers.api": ("&str", "str"),
    "providers.local": ("&str", "str"),
    "providers.ocr_none": ("&str", "str"),
    "llm.max_tokens": ("u32", "int"),
    "llm.temperature": ("f32", "float"),
    "llm.top_p": ("f32", "float"),
    "pdf.chunk_size": ("usize", "int"),
    "pdf.chunk_overlap": ("usize", "int"),
    "sidecar.default_port": ("u16", "int"),
    "sidecar.default_url": ("&str", "str"),
    "supported_doc_exts": ("&[&str]", "set[str]"),
    "supported_mol_exts": ("&[&str]", "set[str]"),
}

# YAML key → final const identifier. Explicit because identifiers don't
# follow a strict rule from YAML paths (some drop the section prefix, some
# add suffix). Keep in sync with the 50+ call sites in src-tauri/crates/**.
IDENTS: dict[str, str] = {
    "app.name": "APP_NAME",
    "app.version": "APP_VERSION",
    "app.author": "APP_AUTHOR",
    "project.format_version": "PROJECT_FORMAT_VERSION",
    "project.meta_dir": "PROJECT_META_DIR",
    "directories.memory": "MEMORY_DIR",
    "directories.trajectory": "TRAJECTORY_DIR",
    "directories.trajectory_file": "TRAJECTORY_FILE",
    "directories.summary": "SUMMARY_DIR",
    "directories.mol_db_filename": "MOL_DB_FILENAME",
    "directories.kb_collection_docs": "KB_COLLECTION_DOCS",
    "directories.index_file": "INDEX_FILE",
    "directories.settings_file": "SETTINGS_FILE",
    "models.default_embed": "DEFAULT_EMBED_MODEL",
    "models.default_rerank": "DEFAULT_RERANK_MODEL",
    "models.default_hf_endpoint": "DEFAULT_HF_ENDPOINT",
    "models.cache_dir": "MODEL_CACHE_DIR",
    "providers.openai_compatible": "PROVIDER_OPENAI_COMPATIBLE",
    "providers.anthropic": "PROVIDER_ANTHROPIC",
    "providers.qwen3": "PROVIDER_QWEN3",
    "providers.sentence_transformers": "PROVIDER_SENTENCE_TRANSFORMERS",
    "providers.ollama": "PROVIDER_OLLAMA",
    "providers.api": "PROVIDER_API",
    "providers.local": "PROVIDER_LOCAL",
    "providers.ocr_none": "PROVIDER_OCR_NONE",
    "llm.max_tokens": "LLM_MAX_TOKENS",
    "llm.temperature": "LLM_TEMPERATURE",
    "llm.top_p": "LLM_TOP_P",
    "pdf.chunk_size": "PDF_CHUNK_SIZE",
    "pdf.chunk_overlap": "PDF_CHUNK_OVERLAP",
    "sidecar.default_port": "DEFAULT_SIDECAR_PORT",
    "sidecar.default_url": "DEFAULT_SIDECAR_URL",
    "supported_doc_exts": "SUPPORTED_DOC_EXTS",
    "supported_mol_exts": "SUPPORTED_MOL_EXTS",
}


def ident_for(key: str) -> str:
    if key not in IDENTS:
        sys.exit(f"Missing IDENTS entry for YAML key: {key!r}")
    return IDENTS[key]


# ---------------------------------------------------------------------------
# YAML load + validation
# ---------------------------------------------------------------------------
def load_yaml() -> dict[str, Any]:
    if not YAML_PATH.exists():
        sys.exit(f"constants.yaml not found at {YAML_PATH}")
    with YAML_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def flatten(data: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for k, v in data.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.extend(flatten(v, key))
        else:
            out.append((key, v))
    return out


def resolve(key: str) -> tuple[str, str]:
    if key not in TYPE_MAP:
        sys.exit(
            f"Unknown YAML key: {key!r}\n"
            f"Add it to TYPE_MAP and IDENTS in scripts/generate_constants.py."
        )
    return TYPE_MAP[key]


# YAML keys that exist purely as script config (read by main/sync_versions)
# and are not emitted as Rust/Python constants. Listed here so the unknown-key
# check in the emission loop doesn't reject them.
META_KEYS: set[str] = {
    "app.sync_python_version",
}


# ---------------------------------------------------------------------------
# Rust emitter (no inner attributes — apply at the include! site)
# ---------------------------------------------------------------------------
RUST_HEADER = """\
// ============================================================
// AUTO-GENERATED from constants.yaml — DO NOT EDIT MANUALLY
// Generated by: python scripts/generate_constants.py
// Consumed via `include!` in `mbforge-infra/src/config/generated.rs`.
// No inner attributes here — apply them at the include! site.
// ============================================================

use std::path::PathBuf;
"""


def emit_rust_value(rust_type: str, value: Any) -> str:
    if rust_type == "&str":
        return f'"{value}"'
    if rust_type in {"u16", "u32", "usize", "u64", "i32", "i64"}:
        return str(value)
    if rust_type in {"f32", "f64"}:
        suffix = "f64" if rust_type == "f64" else "f32"
        return f"{value}_{suffix}"
    if rust_type == "bool":
        return "true" if value else "false"
    if rust_type == "&[&str]":
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            sys.exit(f"Expected list[str] for &[&str], got: {value!r}")
        return "&[" + ", ".join(f'"{x}"' for x in value) + "]"
    sys.exit(f"Unsupported Rust type: {rust_type}")


def emit_rust_constants(items: list[tuple[str, Any, str]]) -> str:
    lines: list[str] = []
    last_section = None
    for key, value, rust_type in items:
        section = key.split(".", 1)[0]
        if section != last_section:
            if lines:
                lines.append("")
            lines.append(f"// {section}")
            last_section = section
        lines.append(
            f"pub const {ident_for(key)}: {rust_type} = "
            f"{emit_rust_value(rust_type, value)};"
        )
    return "\n".join(lines) + "\n"


def render_rust(items: list[tuple[str, Any, str]]) -> str:
    return RUST_HEADER + "\n" + emit_rust_constants(items)


# ---------------------------------------------------------------------------
# Python emitter
# ---------------------------------------------------------------------------
PY_HEADER = '''\
"""MBForge 全局常量 — 从 constants.yaml 自动生成.

DO NOT EDIT MANUALLY. Run ``python scripts/generate_constants.py`` instead.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from platformdirs import user_config_dir, user_data_dir
except ImportError:
    user_config_dir = user_data_dir = lambda *a, **kw: str(
        Path.home() / ".config" / a[0] if a else ".config"
    )

# Python-only constants (not shared with Rust) live below the generated block.
'''


def emit_py_value(py_type: str, value: Any) -> str:
    if py_type == "str":
        return repr(str(value))
    if py_type in {"int", "float"}:
        return repr(value)
    if py_type == "bool":
        return "True" if value else "False"
    if py_type == "set[str]":
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            sys.exit(f"Expected list[str] for set[str], got: {value!r}")
        # Python uses dotted extensions; YAML has no-dot.
        return "{" + ", ".join(f'".{x}"' for x in value) + "}"
    sys.exit(f"Unsupported Python type: {py_type}")


def emit_py_constants(items: list[tuple[str, Any, str, str]]) -> str:
    # items: (key, value, rust_type, py_type)
    lines: list[str] = []
    last_section = None
    for key, value, _rust, py_type in items:
        section = key.split(".", 1)[0]
        if section != last_section:
            if lines:
                lines.append("")
            lines.append(f"# {section}")
            last_section = section
        ident = ident_for(key)
        literal = emit_py_value(py_type, value)
        if py_type == "set[str]":
            lines.append(f"{ident}: {py_type} = {literal}")
        else:
            lines.append(f"{ident} = {literal}")
    return "\n".join(lines) + "\n"


PY_PRESERVED = '''\
# ===== Python-only constants (not shared with Rust) =====

# Qwen3 Embedding/Reranker 指令前缀
EMBED_INSTRUCTION_RETRIEVAL = "Given a web search query, retrieve relevant passages that answer the query"
EMBED_INSTRUCTION_CLUSTER = "Given a document, retrieve relevant passages that are semantically similar"
RERANK_DEFAULT_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"

# ===== Path helpers =====

GLOBAL_CONFIG_DIR = Path(user_config_dir(APP_NAME, APP_AUTHOR))
GLOBAL_DATA_DIR = Path(user_data_dir(APP_NAME, APP_AUTHOR))


def get_model_cache_dir() -> str:
    """获取模型缓存目录（优先配置文件，其次默认路径）."""
    try:
        from .config import load_global_config
        cfg = load_global_config()
        if cfg.model_cache_dir:
            result = cfg.model_cache_dir
            if result.startswith("~/") or result.startswith("~\\\\"):
                return str(Path.home() / Path(result[2:]))
            elif result == "~":
                return str(Path.home())
            return result
    except Exception:
        pass
    return str(Path.home() / Path(MODEL_CACHE_DIR))


def ensure_hf_mirror() -> None:
    """设置 HuggingFace 镜像环境变量（如果未设置）。"""
    if not os.environ.get("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = DEFAULT_HF_ENDPOINT
'''


def render_py(items: list[tuple[str, Any, str, str]]) -> str:
    return PY_HEADER + "\n" + emit_py_constants(items) + "\n" + PY_PRESERVED


# ---------------------------------------------------------------------------
# Version sync
# ---------------------------------------------------------------------------
def read_toml_section_version(path: Path, section: str) -> str | None:
    """Return the `version = "..."` value inside the given TOML section, or
    None if the section/version is absent. Section may be nested (e.g.
    "workspace.package"); tomllib exposes it as nested dicts, so we walk
    the dotted path."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cur: Any = data
    for part in section.strip("[]").split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    if not isinstance(cur, dict):
        return None
    v = cur.get("version")
    return v if isinstance(v, str) else None


def write_toml_section_version(path: Path, section: str, version: str) -> bool:
    """Update the first `version = "..."` line inside the given TOML section
    in `path` to `version`. Preserves all other content (comments, formatting)
    by line-level replacement. Validates the result via tomllib. Returns True
    if the file changed."""
    text = path.read_text(encoding="utf-8")
    section_header = section.strip()
    lines = text.splitlines(keepends=True)
    in_section = False
    version_re = re.compile(r'^(\s*)version\s*=\s*"([^"]*)"(.*)$')
    target_idx: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == section_header
            continue
        if in_section and version_re.match(line):
            target_idx = i
            break
    if target_idx is None:
        sys.exit(
            f"Could not find `version = ...` in section [{section_header}] of {path}"
        )
    line = lines[target_idx]
    m = version_re.match(line)
    assert m
    if m.group(2) == version:
        return False
    lines[target_idx] = f'{m.group(1)}version = "{version}"{m.group(3)}\n'
    new_text = "".join(lines)
    try:
        tomllib.loads(new_text)
    except tomllib.TOMLDecodeError as e:
        sys.exit(
            f"After updating {path}, file is no longer valid TOML: {e}\n"
            f"This is a bug in the script — please report."
        )
    path.write_text(new_text, encoding="utf-8")
    return True


def read_json_top_version(path: Path) -> str | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    v = data.get("version")
    return v if isinstance(v, str) else None


def write_json_top_version(path: Path, version: str) -> bool:
    """Round-trip JSON, updating only the top-level `version`. Loses comments
    (JSON has no comment syntax) and may reformat keys — acceptable for the
    two targets (tauri.conf.json, package.json) which carry no comments."""
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if "version" not in data:
        sys.exit(f"No top-level 'version' in {path}")
    if data["version"] == version:
        return False
    data["version"] = version
    # Detect indentation: prefer the existing style (json.tool doesn't help).
    indent = 2
    m = re.search(r"\n( +)\"", text)
    if m:
        indent = len(m.group(1))
    # Preserve trailing newline if present.
    trailing = "\n" if text.endswith("\n") else ""
    new_text = json.dumps(data, indent=indent, ensure_ascii=False) + trailing
    path.write_text(new_text, encoding="utf-8")
    return True


def sync_versions(
    yaml_version: str, sync_python: bool, *, write: bool
) -> list[tuple[str, str, str, str]]:
    """Compare each version target against `yaml_version`.

    Returns a list of (label, path_rel, current, status) tuples, where
    status is one of:
      "ok"        — already matches
      "updated"   — file was just updated (only when write=True)
      "drift"     — file differs; hard fail in --check
      "warn"      — optional target differs; warn in --check
      "skipped"   — optional target, sync disabled
      "missing"   — section/version absent
    """
    results: list[tuple[str, str, str, str]] = []
    for label, path, kind in VERSION_TARGETS:
        try:
            rel = str(path.relative_to(REPO_ROOT))
        except ValueError:
            rel = str(path)
        if kind.startswith("toml-section:"):
            section = kind.split(":", 1)[1]
            optional = False
        elif kind.startswith("toml-section-opt:"):
            section = kind.split(":", 1)[1]
            optional = True
        elif kind == "json-top":
            section = ""
            optional = False
        else:
            sys.exit(f"Unknown VERSION_TARGETS kind: {kind!r}")

        if kind == "json-top":
            current = read_json_top_version(path)
        else:
            current = read_toml_section_version(path, section)

        if current is None:
            results.append((label, rel, "—", "missing"))
            continue

        if current == yaml_version:
            results.append((label, rel, current, "ok"))
            continue

        if optional and not sync_python:
            results.append((label, rel, current, "skipped"))
            continue

        if not write:
            status = "warn" if optional else "drift"
            results.append((label, rel, current, status))
            continue

        if kind == "json-top":
            write_json_top_version(path, yaml_version)
        else:
            write_toml_section_version(path, section, yaml_version)
        results.append((label, rel, current, "updated"))
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="Exit 1 on drift")
    ap.add_argument(
        "--rust-out",
        type=Path,
        default=None,
        help="Also write YAML-derived Rust to <DIR>/constants.rs (for build.rs).",
    )
    args = ap.parse_args()

    raw = load_yaml()
    flat = flatten(raw)

    rust_items: list[tuple[str, Any, str]] = []
    py_items: list[tuple[str, Any, str, str]] = []
    for key, value in flat:
        if key in META_KEYS:
            continue
        rust_t, py_t = resolve(key)
        rust_items.append((key, value, rust_t))
        py_items.append((key, value, rust_t, py_t))

    new_py = render_py(py_items)
    new_rust = render_rust(rust_items) if args.rust_out else None
    yaml_version = raw.get("app", {}).get("version", "")
    sync_python = bool(raw.get("app", {}).get("sync_python_version", True))

    if args.check:
        old_py = PY_OUT.read_text(encoding="utf-8") if PY_OUT.exists() else ""
        py_drift = old_py != new_py
        version_results = sync_versions(yaml_version, sync_python, write=False)
        hard_drift = py_drift or any(
            r[3] in {"drift", "missing"} for r in version_results
        )
        if hard_drift:
            for label, rel, current, status in version_results:
                if status == "drift":
                    sys.stderr.write(
                        f"  [drift] {label} ({rel}): "
                        f"{current or '?'} != {yaml_version}\n"
                    )
                elif status == "missing":
                    sys.stderr.write(f"  [missing] {label} ({rel})\n")
            if py_drift:
                sys.stderr.write(
                    f"  [drift] {PY_OUT.relative_to(REPO_ROOT)}\n"
                )
            sys.stderr.write(
                "Constants/version drift detected. "
                "Run: python scripts/generate_constants.py\n"
            )
            return 1
        # Print warnings even on success.
        for label, rel, current, status in version_results:
            if status == "warn":
                sys.stderr.write(
                    f"  [warn] {label} ({rel}): {current} != {yaml_version} "
                    f"(set app.sync_python_version: true in YAML to sync)\n"
                )
        return 0

    PY_OUT.parent.mkdir(parents=True, exist_ok=True)
    PY_OUT.write_text(new_py, encoding="utf-8")
    print(f"wrote {PY_OUT.relative_to(REPO_ROOT)} ({len(new_py)} bytes)")

    if new_rust is not None:
        rust_target = args.rust_out / "constants.rs"
        rust_target.parent.mkdir(parents=True, exist_ok=True)
        rust_target.write_text(new_rust, encoding="utf-8")
        label = (
            str(rust_target.relative_to(REPO_ROOT))
            if rust_target.is_relative_to(REPO_ROOT)
            else str(rust_target)
        )
        print(f"wrote {label} ({len(new_rust)} bytes)")

    # Version sync (Cargo workspace, tauri.conf, frontend, optional pyproject)
    for label, rel, current, status in sync_versions(
        yaml_version, sync_python, write=True
    ):
        if status == "updated":
            print(f"updated version in {label} ({rel}): {current} → {yaml_version}")
        elif status == "skipped":
            print(
                f"skipped {label} ({rel}): {current} != {yaml_version} "
                f"(app.sync_python_version is false in YAML)"
            )
        elif status == "missing":
            sys.stderr.write(f"warning: version field missing in {label} ({rel})\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
