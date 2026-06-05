#!/usr/bin/env python3
"""Convert MBForge native tools to `#[rig_tool]` impls.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Param:
    name: str
    type_str: str
    default_expr: str | None = None
    is_required: bool = True


@dataclass
class Tool:
    fn_name: str
    rig_name: str
    description: str
    params: list[Param]
    body: str
    source_module: str
    param_descriptions: dict[str, str] = field(default_factory=dict)


def find_matching(source: str, open_at: int, open: str, close: str) -> int | None:
    if open_at >= len(source) or source[open_at] != open:
        return None
    depth = 0
    i = open_at
    in_string = False
    string_quote = None
    while i < len(source):
        c = source[i]
        if in_string:
            if c == '\\':
                i += 2
                continue
            if c == string_quote:
                in_string = False
        else:
            if c == '"':
                in_string = True
                string_quote = '"'
            elif c == open:
                depth += 1
            elif c == close:
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return None


def find_matching_paren(source: str, open_at: int) -> int | None:
    return find_matching(source, open_at, '(', ')')


def find_matching_brace(source: str, open_at: int) -> int | None:
    return find_matching(source, open_at, '{', '}')


# --- Stage 1a ---

_EXTRACT_PATS = [
    (re.compile(r'extract\(\s*args\s*,\s*"([a-zA-Z_][a-zA-Z0-9_]*)"\s*\)'),
     Param(name='', type_str='String', is_required=True)),
    (re.compile(r'extract_i64\(\s*args\s*,\s*"([a-zA-Z_][a-zA-Z0-9_]*)"\s*,\s*(-?\d+)\s*\)'),
     Param(name='', type_str='i64', default_expr='0', is_required=False)),
    (re.compile(r'extract_bool\(\s*args\s*,\s*"([a-zA-Z_][a-zA-Z0-9_]*)"\s*\)'),
     Param(name='', type_str='bool', default_expr='false', is_required=False)),
]


def extract_params(body: str) -> list[Param]:
    seen: dict[str, Param] = {}
    order: list[str] = []
    for pat, template in _EXTRACT_PATS:
        for m in pat.finditer(body):
            p = Param(
                name=m.group(1),
                type_str=template.type_str,
                default_expr=template.default_expr,
                is_required=template.is_required,
            )
            if p.name not in seen:
                seen[p.name] = p
                order.append(p.name)
    return [seen[n] for n in order]


_FN_HEADER_RE = re.compile(
    r'pub fn\s+(\w+)\s*\(\s*args:\s*&Value\s*\)\s*->\s*String\s*\{',
    re.MULTILINE,
)


def split_function(source: str, brace_start: int) -> tuple[str, str]:
    end = find_matching_brace(source, brace_start)
    if end is None:
        raise ValueError("unclosed function body")
    return source[brace_start:brace_start+1], source[brace_start+1:end]


def parse_tool_functions(source: str, module: str) -> dict[str, Tool]:
    out: dict[str, Tool] = {}
    for m in _FN_HEADER_RE.finditer(source):
        fn_name = m.group(1)
        brace_start = source.index('{', m.end() - 1)
        _, body = split_function(source, brace_start)
        rig_name = fn_name.removeprefix('tool_')
        params = extract_params(body)
        out[fn_name] = Tool(
            fn_name=fn_name,
            rig_name=rig_name,
            description=f"(migrated from {module}::{fn_name})",
            params=params,
            body=rewrite_body(body),
            source_module=module,
        )
    return out


# --- Body rewriting ---
# Transform the legacy `args: &Value` body into one compatible with
# `Result<String, ToolError>` return type and typed parameters.

_BODY_RULES = [
    # extract_i64(args, "name", default) -> name.parse().unwrap_or(default)
    (re.compile(r'extract_i64\(\s*args\s*,\s*"([a-zA-Z_][a-zA-Z0-9_]*)"\s*,\s*(-?\d+)\s*\)'),
     r'\1.parse().unwrap_or(\2)'),
    # extract_bool(args, "name") -> name.parse().unwrap_or(false)
    (re.compile(r'extract_bool\(\s*args\s*,\s*"([a-zA-Z_][a-zA-Z0-9_]*)"\s*\)'),
     r'\1.parse().unwrap_or(false)'),
    # extract(args, "name") -> name.clone()
    (re.compile(r'extract\(\s*args\s*,\s*"([a-zA-Z_][a-zA-Z0-9_]*)"\s*\)'),
     r'\1.clone()'),
    # Drop `let X = X.clone();` tautology
    (re.compile(r'\n[ \t]*let\s+(\w+)\s*=\s*\1\.clone\(\)\s*;'),
     r''),
    # Wrap early returns: `return args_err("...");` -> `return Ok(args_err("..."));`
    (re.compile(r'(\n[ \t]*)return\s+(args_err\([^;]*?\))(\s*;)'),
     r'\1return Ok(\2)\3'),
    # Wrap trailing match arms in Ok(...). Apply ALL patterns in order.
    (re.compile(r'Ok\(v\) => v\.to_string\(\),'),
     'Ok(v) => Ok(v.to_string()),'),
    (re.compile(r'Err\(e\) => args_err\(&e\),'),
     'Err(e) => Ok(args_err(&e)),'),
    # `Ok(v) => serde_json::json!(...).to_string(),` -> wrap inside Ok()
    (re.compile(r'Ok\(v\) => (serde_json::json!\([^)]*\))\.to_string\(\),'),
     r'Ok(v) => Ok(\1.to_string()),'),
    (re.compile(r'Err\(e\) => serde_json::json!\(\{"error": e\}\)\.to_string\(\),'),
     'Err(e) => Ok(serde_json::json!({"error": e}).to_string()),'),
    (re.compile(r'Err\(e\) => Ok\(args_err\(&e\)\),'),
     'Err(e) => Ok(args_err(&e)),'),
]


def rewrite_body(body: str) -> str:
    for pat, repl in _BODY_RULES:
        body = pat.sub(repl, body)
    return body


# --- Stage 1b ---

_TOOL_NAME_RE = re.compile(
    r'ToolInfo::new\(\s*"([a-zA-Z_][a-zA-Z0-9_]*)"\s*,\s*"((?:[^"\\]|\\.)*)"'
)
_BOX_NEW_RE = re.compile(
    r'Box::new\(\s*([a-zA-Z_][a-zA-Z0-9_]*)::([a-zA-Z_][a-zA-Z0-9_]*)\s*\)'
)
_INSERT_HEADER_RE = re.compile(
    r'\.insert\(\s*"([a-zA-Z_][a-zA-Z0-9_]*)"\.into\(\)\s*,\s*'
    r'serde_json::json!\(\s*\{',
)
_INSERT_TYPE_RE = re.compile(
    r'^\s*"type":\s*"([a-zA-Z_]+)"',
)
_INSERT_DESC_RE = re.compile(
    r',\s*"description":\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$',
)


def _parse_schema_object(obj_text: str) -> tuple[str, str] | None:
    type_m = _INSERT_TYPE_RE.match(obj_text)
    if not type_m:
        return None
    type_str = type_m.group(1)
    desc_m = _INSERT_DESC_RE.search(obj_text)
    desc = desc_m.group(1) if desc_m else ""
    return (type_str, desc)


def _third_arg_bounds(source: str, after_desc: int) -> tuple[int, int] | None:
    i = after_desc
    while i < len(source) and source[i] in ' \t\n,':
        i += 1
    if i >= len(source):
        return None
    if source[i] == '{':
        end = find_matching_brace(source, i)
        return (i, end) if end is not None else None
    if source[i] == '(':
        end = find_matching_paren(source, i)
        return (i, end) if end is not None else None
    return None


def parse_register_block(source: str) -> list[dict]:
    m = re.search(
        r'pub fn register\(\s*registry:\s*&mut ToolRegistry\s*,\s*[^)]*\)\s*\{',
        source,
    )
    if not m:
        return []
    brace_start = source.index('{', m.end() - 1)
    _, body = split_function(source, brace_start)
    out: list[dict] = []
    for tm in _TOOL_NAME_RE.finditer(body):
        name = tm.group(1)
        desc = tm.group(2)
        bounds = _third_arg_bounds(body, tm.end())
        if bounds is None:
            continue
        args_block = body[bounds[0]:bounds[1] + 1]
        schema: dict[str, tuple[str, str]] = {}
        for ins in _INSERT_HEADER_RE.finditer(args_block):
            param_name = ins.group(1)
            close = find_matching_brace(args_block, ins.end() - 1)
            if close is None:
                continue
            inner = args_block[ins.end():close]
            parsed = _parse_schema_object(inner)
            if parsed is None:
                continue
            schema[param_name] = parsed
        after = body[bounds[1] + 1:]
        bm = _BOX_NEW_RE.search(after)
        if not bm:
            continue
        out.append({
            'name': name,
            'description': desc,
            'schema': schema,
            'module': bm.group(1),
            'fn_name': bm.group(2),
        })
    return out


# --- Stage 2 ---

def schema_to_params(schema: dict[str, tuple[str, str]]) -> list[Param]:
    out: list[Param] = []
    for name, (_type_str, _desc) in schema.items():
        out.append(Param(name=name, type_str='String',
                         default_expr=None, is_required=True))
    return out


def to_pascal_case(s: str) -> str:
    parts = re.split(r'[_\-]+', s)
    return ''.join(p.capitalize() for p in parts if p)


def to_param_signature(p: Param) -> str:
    if p.is_required:
        return f"{p.name}: {p.type_str}"
    return f"{p.name}: Option<{p.type_str}>"


def to_params_block(params: list[Param], descriptions: dict[str, str]) -> str:
    lines: list[str] = []
    for p in params:
        desc = descriptions.get(p.name, "(no description)")
        desc_escaped = desc.replace('\\', '\\\\').replace('"', '\\"')
        lines.append(f'        {p.name} = "{desc_escaped}",')
    return "\n".join(lines)


def generate_tool_function(t: Tool) -> str:
    sig_params = ", ".join(to_param_signature(p) for p in t.params)
    params_block = to_params_block(t.params, t.param_descriptions)
    desc_escaped = t.description.replace('\\', '\\\\').replace('"', '\\"')
    return (
        f'#[rig_tool(\n'
        f'    name = "{t.rig_name}",\n'
        f'    description = "{desc_escaped}",\n'
        f'    params(\n{params_block}\n'
        f'    )\n'
        f')]\n'
        f'async fn {t.rig_name}({sig_params}) -> Result<String, rig_core::tool::ToolError> {{\n'
        f'{t.body}\n'
        f'}}'
    )


def generate_register_body(tools: list[Tool]) -> str:
    lines = []
    for t in tools:
        struct_name = to_pascal_case(t.rig_name)
        lines.append(f"    set.add_tool({struct_name});")
    body = "\n".join(lines)
    return (
        '/// Add all migrated tools to a `ToolSet`. Call from your rig agent builder.\n'
        'pub fn register_rig_tools(set: &mut rig_core::tool::ToolSet) {\n'
        f'{body}\n'
        '}'
    )


_DEFAULT_HELPERS = (
    "args_err, param_url, json, text, BASE_ARXIV, BASE_PMC, urlencoding"
)


def generate_rig_module(
    tools: list[Tool],
    target_module_path: str,
    source_basename: str | None = None,
    helpers: str = _DEFAULT_HELPERS,
) -> str:
    if source_basename:
        import_section = (
            f"// Generated by ref/migrate_to_rig.py.\n"
            f"// Helpers come from {source_basename}.rs.\n"
            f'use {target_module_path} as arxiv_src;\n'
            f'use arxiv_src::{{{helpers}}};\n'
        )
    else:
        import_section = ""
    header = (
        '//! Auto-converted from MBForge native tools to `#[rig_tool]` impls.\n'
        '//!\n'
        '//! Generated by ref/migrate_to_rig.py — review manually before committing.\n'
        '\n'
        'use rig_core::tool::Tool;\n'
        'use rig_derive::rig_tool;\n'
        f'{import_section}\n'
    )
    fns = "\n\n".join(generate_tool_function(t) for t in tools)
    register = generate_register_body(tools)
    return header + fns + "\n\n" + register + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tool-sources', nargs='+', type=Path, default=[])
    ap.add_argument('--register-sources', nargs='+', type=Path, default=[])
    ap.add_argument('--target-module', type=str, default='crate::core::agent::arxiv')
    ap.add_argument('--source-basename', type=str, default=None)
    ap.add_argument('--helpers', type=str, default=_DEFAULT_HELPERS)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--print', action='store_true')
    args = ap.parse_args()

    tool_fn_map: dict[str, Tool] = {}
    source_basename = args.source_basename
    for src in args.tool_sources:
        if not src.exists():
            print(f"missing: {src}", file=sys.stderr)
            return 1
        if source_basename is None:
            source_basename = src.stem
        src_text = src.read_text(encoding='utf-8')
        tools = parse_tool_functions(src_text, src.stem)
        tool_fn_map.update(tools)
        print(f"[{src.name}] parsed {len(tools)} tool functions", file=sys.stderr)

    enriched: list[Tool] = []
    for src in args.register_sources:
        if not src.exists():
            print(f"missing: {src}", file=sys.stderr)
            return 1
        src_text = src.read_text(encoding='utf-8')
        regs = parse_register_block(src_text)
        print(f"[{src.name}] parsed {len(regs)} register entries", file=sys.stderr)
        for reg in regs:
            fn_name = reg['fn_name']
            if fn_name not in tool_fn_map:
                print(f"  warn: {fn_name} not in any tool-source", file=sys.stderr)
                continue
            t = tool_fn_map[fn_name]
            t.description = reg['description']
            t.params = schema_to_params(reg['schema'])
            t.param_descriptions = {n: d for n, (_, d) in reg['schema'].items()}
            enriched.append(t)
    seen = {e.fn_name for e in enriched}
    for fn_name, t in tool_fn_map.items():
        if fn_name not in seen:
            enriched.append(t)
            print(f"  note: {fn_name} has no register entry (still emitted)", file=sys.stderr)

    print(f"Total: {len(enriched)} tools to emit", file=sys.stderr)
    for t in enriched:
        sig = ", ".join(to_param_signature(p) for p in t.params)
        print(f"  - {t.rig_name}({sig})", file=sys.stderr)

    output = generate_rig_module(
        enriched,
        target_module_path=args.target_module,
        source_basename=source_basename,
        helpers=args.helpers,
    )
    if args.print:
        print(output)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding='utf-8')
        print(f"wrote {args.out} ({len(output)} chars)", file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
