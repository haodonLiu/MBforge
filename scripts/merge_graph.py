#!/usr/bin/env python
"""
graphify-out/graph.json post-processor.

Two passes:
  1. Merge duplicate communities (C31 == C32 etc.) — set the higher-numbered
     community id to the lower one for every node in the duplicate.
  2. Inject hyperedges for cross-language relationships that AST can't see:
       a. Tauri bridge:  frontend invoke("xxx") ↔ Rust command xxx
       b. Sidecar HTTP:  Rust HTTP call ↔ Python FastAPI route

The script preserves all existing nodes/edges; it only rewrites the
`community` field on nodes and appends to `hyperedges`.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

GRAPH = Path("graphify-out/graph.json")
SRC_ROOT = Path("src")
TAURI = Path("src-tauri/src")
FRONTEND = Path("frontend/src")
PY_ROUTERS = Path("src/mbforge/model_server/routers")
SIDE = Path("src-tauri/src/sidecar.rs")

# Community pairs that the user / investigation identified as duplicates.
# Each entry: (keep_id, merge_id) — every node in merge_id gets its
# `community` field reassigned to keep_id.
# The pairs come from exact-label-set community comparison (graph.json
# as of 2026-06-06, commit 606647df). All listed pairs are confirmed
# duplicates of the same source code (file-level diff == identical):
#   - MolScribe: vendored in two locations, MBForge's fork and the
#     setup/ submodule. Excluding setup/MolScribe via .graphifyignore
#     is the long-term fix; the merge here is a one-shot correction
#     for the current graph.json until the next full build.
#
# C64/C68 (arxiv.rs in core/agent/ vs core/executor/) are NOT a dupe:
# the two files differ. They share a filename and many labels but are
# distinct implementations; merging them would hide a real boundary.
DUPLICATE_COMMUNITIES: list[tuple[int, int]] = [
    (31, 32),    # swin_transformer.py
    (43, 44),    # vocab_chars.json
    (92, 93),    # utils.py
    (128, 130),  # model.py (GraphPredictor)
    (133, 134),  # tokenizer.py
    (147, 149),  # beam_search.py
    (148, 150),  # transformer/decoder.py
    (190, 191),  # inference/decode_strategy.py
    (217, 219),  # transformer/decoder.py (init group)
    (218, 220),  # transformer/decoder.py (TransformerDecoder)
]


def collect_tauri_bridge_pairs() -> list[tuple[str, str, str]]:
    """Yield (frontend_file, rust_module, command_name) triples.

    Scans frontend/src for `invoke("foo")` calls and pairs them with
    the Rust module path that defines `#[tauri::command] fn foo`.
    """
    # Map command name -> Rust module path
    rust_commands: dict[str, str] = {}
    for f in TAURI.rglob("*.rs"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(
            r"#\[tauri::command\][^}]*?fn\s+(\w+)", text, flags=re.DOTALL
        ):
            cmd = m.group(1)
            mod = str(f.relative_to(TAURI)).replace("\\", "/")
            rust_commands.setdefault(cmd, mod)
    # Map command name -> frontend file
    frontend_calls: dict[str, list[str]] = defaultdict(list)
    for f in FRONTEND.rglob("*.ts"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'invoke\(\s*[\'"]([^\'"]+)[\'"]', text):
            cmd = m.group(1)
            frontend_calls[cmd].append(
                str(f.relative_to(FRONTEND)).replace("\\", "/")
            )
    # Pair
    pairs = []
    for cmd, files in frontend_calls.items():
        if cmd in rust_commands:
            for ff in files:
                pairs.append((ff, rust_commands[cmd], cmd))
    return pairs


def collect_sidecar_http_pairs() -> list[tuple[str, str, str, str]]:
    """Yield (rust_file, rust_symbol, py_router, py_path) tuples.

    Scans Rust source for `/api/v1/<x>` literal URL strings inside
    format! macros or string literals, and pairs them with the
    Python FastAPI route that handles the same path.
    """
    # Map FastAPI route -> router file
    py_routes: dict[str, str] = {}
    for f in PY_ROUTERS.rglob("*.py"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(
            r'@router\.(get|post|put|delete|patch)\(\s*[\'"]([^\'"]+)[\'"]',
            text,
        ):
            py_routes.setdefault(m.group(2), str(f.relative_to(Path("src"))).replace("\\", "/"))
    # Scan Rust for /api/v1/...
    pairs = []
    for f in TAURI.rglob("*.rs"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'/api/v1/([a-zA-Z][\w/-]*)', text):
            route = m.group(1)
            # The Python routes table uses the post-prefix path (e.g. 'molscribe'),
            # but the Rust URL is the full path (e.g. 'vlm/molscribe'). We compare
            # suffixes.
            matched = None
            for py_path, py_file in py_routes.items():
                if route.endswith("/" + py_path) or route == py_path:
                    matched = py_path
                    break
                # also match 'vlm/molscribe' against 'molscribe' (router file is vlm.py)
                if py_path in route:
                    matched = py_path
                    break
            if matched:
                # Find enclosing function name for context
                start = m.start()
                # search backwards for the most recent `pub async fn` or `pub fn`
                fn_match = None
                for fm in re.finditer(
                    r'pub(?:\s+async)?\s+fn\s+(\w+)', text[:start]
                ):
                    fn_match = fm.group(1)
                fn = fn_match or "anonymous"
                pairs.append(
                    (
                        str(f.relative_to(TAURI)).replace("\\", "/"),
                        fn,
                        py_routes[matched],
                        matched,
                    )
                )
    return pairs


def node_id_for_frontend(frontend_file: str) -> str:
    """Best-effort node id matching graphify's stem_entity naming."""
    stem = Path(frontend_file).stem
    return f"tauri_bridge_{stem}"


def node_id_for_rust_module(rust_file: str) -> str:
    stem = Path(rust_file).stem
    parent = Path(rust_file).parent.name
    return f"{parent}_{stem}"


def node_id_for_py_route(py_file: str, route: str) -> str:
    stem = Path(py_file).stem
    return f"routers_{stem}_{re.sub(r'[^a-z0-9_]', '_', route.lower())}"


def main() -> None:
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    nodes = graph["nodes"]
    edges = graph["links"]
    hyperedges = graph.setdefault("hyperedges", [])

    # ------------------------------------------------------------------
    # 1. Merge duplicate communities
    # ------------------------------------------------------------------
    merge_map: dict[int, int] = {}
    for keep, drop in DUPLICATE_COMMUNITIES:
        merge_map[drop] = keep
    affected = 0
    for n in nodes:
        cid = n.get("community")
        if cid in merge_map:
            n["community"] = merge_map[cid]
            affected += 1
    print(f"community merge: {affected} nodes reassigned across {len(DUPLICATE_COMMUNITIES)} pairs")

    # ------------------------------------------------------------------
    # 2. Inject hyperedges for Tauri bridge (frontend ↔ Rust)
    # ------------------------------------------------------------------
    tauri_pairs = collect_tauri_bridge_pairs()
    print(f"tauri bridge pairs: {len(tauri_pairs)}")
    seen_hyper: set[str] = set()
    for ff, rf, cmd in tauri_pairs:
        h_id = f"tauri_bridge_{cmd}"
        if h_id in seen_hyper:
            continue
        seen_hyper.add(h_id)
        fe_id = node_id_for_frontend(ff)
        rs_id = node_id_for_rust_module(rf)
        hyperedges.append({
            "id": h_id,
            "label": f"Tauri bridge: {cmd}",
            "nodes": [fe_id, rs_id],
            "relation": "form",
            "confidence": "EXTRACTED",
            "confidence_score": 0.95,
            "source_file": f"frontend/src/api/tauri/{Path(ff).name}",
            "source_location": ff,
            "weight": 1.0,
        })

    # ------------------------------------------------------------------
    # 3. Inject hyperedges for Sidecar HTTP (Rust ↔ Python)
    # ------------------------------------------------------------------
    sidecar_pairs = collect_sidecar_http_pairs()
    print(f"sidecar http pairs: {len(sidecar_pairs)}")
    for rf, fn, pf, route in sidecar_pairs:
        h_id = f"sidecar_http_{fn}_{re.sub(r'[^a-z0-9_]', '_', route.lower())}"
        if h_id in seen_hyper:
            continue
        seen_hyper.add(h_id)
        rs_id = f"src_tauri_src_{Path(rf).stem}_{fn}" if Path(rf).stem != fn else node_id_for_rust_module(rf)
        py_id = node_id_for_py_route(pf, route)
        hyperedges.append({
            "id": h_id,
            "label": f"Sidecar HTTP: {fn} → POST /api/v1/{route}",
            "nodes": [rs_id, py_id],
            "relation": "form",
            "confidence": "EXTRACTED",
            "confidence_score": 0.90,
            "source_file": rf,
            "source_location": f"{rf}::{fn}",
            "weight": 1.0,
        })

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------
    graph["hyperedges"] = hyperedges
    GRAPH.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {GRAPH}")
    print(f"  total nodes: {len(nodes)}")
    print(f"  total edges: {len(edges)}")
    print(f"  total hyperedges: {len(hyperedges)}")
    print(f"  unique community ids: {len(set(n.get('community') for n in nodes))}")


if __name__ == "__main__":
    main()
