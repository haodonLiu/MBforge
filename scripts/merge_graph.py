#!/usr/bin/env python
"""
graphify-out/graph.json post-processor.

Two passes:
  1. Merge duplicate communities (C31 == C32 etc.) — set the higher-numbered
     community id to the lower one for every node in the duplicate.
  2. Inject hyperedges for cross-language relationships that AST cannot see:
       a. Tauri bridge:  frontend invoke("xxx") ↔ Rust command xxx
       b. Sidecar HTTP:  Rust HTTP call ↔ Python FastAPI route

Hyperedge node IDs are computed from graphify's actual naming
convention: `{parent_dir_stem}_{filename_stem}` (file-level) and
`{parent_dir_stem}_{filename_stem}_{entity}` (function-level). For
nested paths, only the **immediate** parent dir is used.

Reference: graphify/skills/*/references/extraction-spec.md
  "Node ID format: ... `{stem}_{entity}` where stem is `{parent_dir}_{filename_without_ext}`"
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

GRAPH = Path("graphify-out/graph.json")
TAURI = Path("src-tauri/src")
FRONTEND_API = Path("frontend/src/api/tauri")
PY_ROUTERS = Path("src/mbforge/model_server/routers")

# Community pairs that the user / investigation identified as duplicates.
# Each entry: (keep_id, merge_id) — every node in merge_id gets its
# `community` field reassigned to keep_id.
# All listed pairs are confirmed duplicates of the same source code
# (file-level diff == identical):
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


def graphify_id(file_rel: str, entity: str | None = None) -> str:
    """Compute a graphify node id from a relative file path and entity.

    graphify uses {parent_dir}_{filename_stem} for the file-level node
    and {parent_dir}_{filename_stem}_{entity} for sub-entities. Only
    the **immediate** parent dir is used. Path is relative to project
    root (e.g. 'src-tauri/src/commands/agent.rs').
    """
    parts = file_rel.replace("\\", "/").split("/")
    if len(parts) < 2:
        # top-level file (e.g. setup.py) — stem is just the filename
        stem = Path(file_rel).stem.lower()
        stem = re.sub(r"[^a-z0-9_]", "_", stem)
    else:
        parent = parts[-2].lower()
        parent = re.sub(r"[^a-z0-9_]", "_", parent)
        fname = Path(parts[-1]).stem.lower()
        fname = re.sub(r"[^a-z0-9_]", "_", fname)
        stem = f"{parent}_{fname}"
    if entity:
        ent = re.sub(r"[^a-z0-9_]", "_", entity.lower())
        return f"{stem}_{ent}"
    return stem


def collect_tauri_bridge_pairs() -> list[tuple[str, str, str]]:
    """Map `invoke("foo")` calls in frontend/src/api/tauri/ to Rust command modules."""
    rust_commands: dict[str, str] = {}
    for f in TAURI.rglob("*.rs"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(
            r"#\[tauri::command\][^}]*?fn\s+(\w+)", text, flags=re.DOTALL
        ):
            cmd = m.group(1)
            mod = str(f.relative_to(TAURI.parent)).replace("\\", "/")  # src-tauri/src/...
            rust_commands.setdefault(cmd, mod)
    pairs: list[tuple[str, str, str]] = []
    for f in sorted(FRONTEND_API.glob("*.ts")):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'invoke\(\s*[\'"]([^\'"]+)[\'"]', text):
            cmd = m.group(1)
            if cmd in rust_commands:
                fe = str(f.relative_to(Path("frontend"))).replace("\\", "/")
                rs = rust_commands[cmd]
                pairs.append((fe, rs, cmd))
    return pairs


def collect_sidecar_http_pairs() -> list[tuple[str, str, str, str]]:
    """Map Rust `/api/v1/<x>` calls to Python FastAPI route handler files."""
    py_routes: dict[str, str] = {}
    for f in PY_ROUTERS.rglob("*.py"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(
            r'@router\.(get|post|put|delete|patch)\(\s*[\'"]([^\'"]+)[\'"]',
            text,
        ):
            py_routes.setdefault(
                m.group(2),
                str(f.relative_to(Path("src"))).replace("\\", "/"),
            )
    pairs: list[tuple[str, str, str, str]] = []
    for f in TAURI.rglob("*.rs"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'/api/v1/([a-zA-Z][\w/-]*)', text):
            route = m.group(1)
            matched = None
            for py_path, py_file in py_routes.items():
                if route == py_path or route.endswith("/" + py_path) or py_path in route:
                    matched = py_path
                    break
            if matched:
                start = m.start()
                fn = "anonymous"
                for fm in re.finditer(r'pub(?:\s+async)?\s+fn\s+(\w+)', text[:start]):
                    fn = fm.group(1)
                rf = str(f.relative_to(TAURI.parent)).replace("\\", "/")
                pairs.append((rf, fn, py_routes[matched], matched))
    return pairs


def main() -> None:
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    nodes = graph["nodes"]
    edges = graph["links"]

    # 0. Clear any hyperedges from a previous run (idempotent re-build)
    if "hyperedges" in graph:
        del graph["hyperedges"]
    graph["hyperedges"] = []
    hyperedges = graph["hyperedges"]

    # ------------------------------------------------------------------
    # 1. Merge duplicate communities (idempotent — only fires if not
    #    already merged)
    # ------------------------------------------------------------------
    merge_map: dict[int, int] = {drop: keep for keep, drop in DUPLICATE_COMMUNITIES}
    affected = 0
    for n in nodes:
        cid = n.get("community")
        if cid in merge_map:
            n["community"] = merge_map[cid]
            affected += 1
    print(f"community merge: {affected} nodes reassigned across {len(DUPLICATE_COMMUNITIES)} pairs")

    # ------------------------------------------------------------------
    # 2. Build node-id set for verification
    # ------------------------------------------------------------------
    node_ids = {n["id"] for n in nodes}

    # ------------------------------------------------------------------
    # 3. Tauri bridge hyperedges
    # ------------------------------------------------------------------
    tauri_pairs = collect_tauri_bridge_pairs()
    print(f"tauri bridge pairs discovered: {len(tauri_pairs)}")
    seen: set[str] = set()
    unresolved: list[tuple[str, str]] = []
    for fe, rs, cmd in tauri_pairs:
        h_id = f"tauri_bridge_{cmd}"
        if h_id in seen:
            continue
        fe_id = graphify_id(fe.replace("src/api/tauri/", "api/tauri/"))
        # Frontend: graphify places it under frontend/src/api/tauri/<file>
        # so the parent is 'tauri' and stem is the file stem. Try that first.
        alt_fe = graphify_id("tauri/" + Path(fe).name)
        if fe_id in node_ids:
            pass
        elif alt_fe in node_ids:
            fe_id = alt_fe
        else:
            unresolved.append((h_id, f"frontend: tried {fe_id} and {alt_fe}"))
            continue
        rs_id = graphify_id(rs)
        if rs_id not in node_ids:
            unresolved.append((h_id, f"rust: {rs_id}"))
            continue
        seen.add(h_id)
        hyperedges.append({
            "id": h_id,
            "label": f"Tauri bridge: {cmd}",
            "nodes": [fe_id, rs_id],
            "relation": "form",
            "confidence": "EXTRACTED",
            "confidence_score": 0.95,
            "source_file": fe,
            "source_location": f"{rs}::{cmd}",
            "weight": 1.0,
        })

    # ------------------------------------------------------------------
    # 4. Sidecar HTTP hyperedges
    # ------------------------------------------------------------------
    sidecar_pairs = collect_sidecar_http_pairs()
    print(f"sidecar http pairs discovered: {len(sidecar_pairs)}")
    for rf, fn, pf, route in sidecar_pairs:
        slug = re.sub(r"[^a-z0-9_]", "_", f"{fn}_{route}".lower())
        h_id = f"sidecar_http_{slug}"
        if h_id in seen:
            continue
        # Try Rust function node first, then fall back to file-level
        rs_id_fn = graphify_id(rf, fn)
        rs_id_file = graphify_id(rf)
        if rs_id_fn in node_ids:
            rs_id = rs_id_fn
        elif rs_id_file in node_ids:
            rs_id = rs_id_file
        else:
            unresolved.append((h_id, f"rust: tried {rs_id_fn} and {rs_id_file}"))
            continue
        # Python route - graphify's naming for routers/vlm.py is `routers_vlm`
        py_id_file = graphify_id(pf)
        # Some routers have an `func` node too
        py_id_route = graphify_id(pf, route.lstrip("/"))
        if py_id_route in node_ids:
            py_id = py_id_route
        elif py_id_file in node_ids:
            py_id = py_id_file
        else:
            unresolved.append((h_id, f"python: tried {py_id_route} and {py_id_file}"))
            continue
        seen.add(h_id)
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

    if unresolved:
        print(f"\nunresolved hyperedge node ids ({len(unresolved)} skipped):")
        for h_id, why in unresolved[:10]:
            print(f"  {h_id}: {why}")
        if len(unresolved) > 10:
            print(f"  ... and {len(unresolved) - 10} more")

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------
    graph["hyperedges"] = hyperedges
    GRAPH.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {GRAPH}")
    print(f"  total nodes: {len(nodes)}")
    print(f"  total edges: {len(edges)}")
    print(f"  total hyperedges: {len(hyperedges)}")
    print(f"  unique community ids: {len(set(n.get('community') for n in nodes))}")

    # Verify
    bad = []
    for h in hyperedges:
        for nid in h["nodes"]:
            if nid not in node_ids:
                bad.append((h["id"], nid))
    if bad:
        print(f"\n!! {len(bad)} hyperedge references do not resolve to graph nodes:")
        for h_id, nid in bad[:10]:
            print(f"  {h_id}: {nid}")
        sys.exit(1)
    else:
        print(f"  all {sum(len(h['nodes']) for h in hyperedges)} hyperedge node references resolve")


if __name__ == "__main__":
    main()
