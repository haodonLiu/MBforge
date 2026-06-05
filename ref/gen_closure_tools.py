#!/usr/bin/env python3
"""Generate hand-rolled `impl Tool` blocks for closure-based tools.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClosureTool:
    name: str
    description: str
    schema_args: list
    captures: list
    body_calls: list
    body: str
    source_file: str


_TOOL_NAME_RE = re.compile(
    r'ToolInfo::new\(\s*"([a-zA-Z_][a-zA-Z0-9_]*)"\s*,\s*"((?:[^"\\]|\\.)*)"'
)
_INSERT_HEADER_RE = re.compile(
    r'\.insert\(\s*"([a-zA-Z_][a-zA-Z0-9_]*)"\.into\(\)\s*,\s*'
    r'serde_json::json!\(\s*\{',
)
_INSERT_TYPE_RE = re.compile(r'^\s*"type":\s*"([a-zA-Z_]+)"')
_INSERT_DESC_RE = re.compile(r',\s*"description":\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$')
_BOX_NEW_MOVE_RE = re.compile(
    r'Box::new\(\s*move\s*\|\s*args\s*\|\s*\{',
    re.MULTILINE,
)
_LET_R_RE = re.compile(r'\s*let\s+(\w+)\s*=\s*root\.clone\(\);')
_NATIVE_CALL_RE = re.compile(r'\b(native_[a-zA-Z_]+)\(')


def find_matching_brace(source, open_at):
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
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return None


def find_matching_paren(source, open_at):
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
            elif c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return None


def _third_arg_bounds(source, after_desc):
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


def parse_register_block(source, source_file):
    m = re.search(
        r'pub fn register\(\s*registry:\s*&mut ToolRegistry\s*,\s*([^)]*)\)\s*\{',
        source,
    )
    if not m:
        return []
    brace_start = source.index('{', m.end() - 1)
    end = find_matching_brace(source, brace_start)
    if end is None:
        return []
    body = source[brace_start + 1:end]
    out = []
    for tm in _TOOL_NAME_RE.finditer(body):
        name = tm.group(1)
        desc = tm.group(2)
        # Captures from preceding 1000 chars
        captures = []
        prefix = body[max(0, tm.start() - 1000):tm.start()]
        for lm in _LET_R_RE.finditer(prefix):
            captures.append(lm.group(1))
        for lm in re.finditer(r'let\s+(\w+)\s*=\s*_?project_root\.to_string\(\)', prefix):
            captures.append(lm.group(1))
        # Dedupe
        seen = set()
        dedup = []
        for c in captures:
            if c not in seen:
                seen.add(c)
                dedup.append(c)
        captures = dedup
        # Schema
        schema = []
        bounds = _third_arg_bounds(body, tm.end())
        if bounds is not None:
            args_block = body[bounds[0]:bounds[1] + 1]
            for ins in _INSERT_HEADER_RE.finditer(args_block):
                param_name = ins.group(1)
                close = find_matching_brace(args_block, ins.end() - 1)
                if close is None:
                    continue
                inner = args_block[ins.end():close]
                tm2 = _INSERT_TYPE_RE.match(inner)
                if not tm2:
                    continue
                dm = _INSERT_DESC_RE.search(inner)
                desc_d = dm.group(1) if dm else ""
                schema.append((param_name, tm2.group(1), desc_d))
        # Closure body + native calls
        after_tm = body[tm.end():]
        cm_after = _BOX_NEW_MOVE_RE.search(after_tm)
        body_calls = []
        body_text = ""
        if cm_after:
            closure_end = find_matching_brace(after_tm, cm_after.end() - 1)
            if closure_end:
                closure_body = after_tm[cm_after.end():closure_end]
                body_calls = list(set(_NATIVE_CALL_RE.findall(closure_body)))
                body_text = after_tm[cm_after.start():closure_end + 1]
        out.append(ClosureTool(
            name=name,
            description=desc,
            schema_args=schema,
            captures=captures,
            body_calls=body_calls,
            body=body_text,
            source_file=source_file,
        ))
    return out


_TYPE_MAP = {
    "string": "String",
    "integer": "i64",
    "number": "f64",
    "boolean": "bool",
    "object": "serde_json::Value",
    "array": "Vec<serde_json::Value>",
}


def to_pascal_case(s):
    parts = re.split(r'[_\-]+', s)
    return ''.join(p.capitalize() for p in parts if p)


def generate_tool_impl(t):
    struct_name = to_pascal_case(t.name)
    caps = list(t.captures) if t.captures else ['project_root']
    field_lines = "\n".join(f"    {c}: String," for c in caps)

    args_fields = []
    args_init = []
    for name, json_type, _desc in t.schema_args:
        rust_type = _TYPE_MAP.get(json_type, "String")
        args_fields.append(f"    pub {name}: Option<{rust_type}>,")
        if rust_type == "i64":
            args_init.append(f"            {name}.unwrap_or(0)")
        elif rust_type == "f64":
            args_init.append(f"            {name}.unwrap_or(0.0)")
        elif rust_type == "bool":
            args_init.append(f"            {name}.unwrap_or(false)")
        else:
            args_init.append(f'            {name}.clone().unwrap_or_default()')
    if not args_fields:
        args_fields = ["    // no args"]
    if not args_init:
        args_init = ["            ()"]

    params_block_lines = []
    for name, _, desc in t.schema_args:
        desc_escaped = desc.replace('\\', '\\\\').replace('"', '\\"')
        params_block_lines.append(f'        {name} = "{desc_escaped}",')
    params_block = "\n".join(params_block_lines)
    if not params_block:
        params_block = "        // (no params)"

    desc_escaped = t.description.replace('\\', '\\\\').replace('"', '\\"')
    new_sig = ", ".join(f"{c}: impl Into<String>" for c in caps)
    new_init = ", ".join(f"{c}: {c}.into()" for c in caps)
    arg_names = [n for n, _, _ in t.schema_args] or ['(none)']

    return f"""// ----- {t.name} -----
#[derive(serde::Deserialize, rig_core::schemars::JsonSchema)]
pub struct {struct_name}Args {{
{chr(10).join(args_fields)}
}}

#[derive(Clone)]
pub struct {struct_name} {{
{field_lines}
}}

impl {struct_name} {{
    /// Construct a new instance.
    pub fn new({new_sig}) -> Self {{
        Self {{ {new_init} }}
    }}
}}

impl rig_core::tool::Tool for {struct_name} {{
    const NAME: &'static str = "{t.name}";

    type Error = rig_core::tool::ToolError;
    type Args = {struct_name}Args;
    type Output = String;

    async fn definition(&self, _prompt: String) -> rig_core::completion::ToolDefinition {{
        let schema = serde_json::to_value(
            rig_core::schemars::schema_for!({struct_name}Args)
        ).expect("schema serialization");
        rig_core::completion::ToolDefinition {{
            name: Self::NAME.to_string(),
            description: "{desc_escaped}".to_string(),
            parameters: schema,
        }}
    }}

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {{
        // TODO(manual): wire the call to the existing native_xxx function.
        //   Captured:   {', '.join(caps)}
        //   Args:       {', '.join(arg_names)}
        //   Native fns: {', '.join(t.body_calls) or '(none detected)'}
        // See executor_rig.rs for worked examples.
        let _ = (self, args);
        Ok(String::new())
    }}
}}
"""


def generate_for_module(source_path):
    src = source_path.read_text(encoding='utf-8')
    tools = parse_register_block(src, source_path.name)
    if not tools:
        return ""
    out = []
    for t in tools:
        out.append(generate_tool_impl(t))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--module-path', type=str, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if not args.source.exists():
        print(f"missing: {args.source}", file=sys.stderr)
        return 1
    body = generate_for_module(args.source)
    if not body:
        print(f"no closure-based tools found in {args.source}", file=sys.stderr)
        return 0
    header = (
        f"//! Auto-generated `impl Tool` for closure-based tools in {args.source.name}.\n"
        f"//!\n"
        f"//! Generated by ref/gen_closure_tools.py — review and fill in the `call()`\n"
        f"//! bodies manually (the script identifies schema + captures + native_xxx\n"
        f"//! calls but does not wire the call body automatically).\n"
        f"\n"
        f"use rig_core::completion::ToolDefinition;\n"
        f"use rig_core::schemars::JsonSchema;\n"
        f"use rig_core::tool::{{Tool, ToolError}};\n"
        f"use serde::Deserialize;\n"
    )
    out = header + "\n" + body
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(out, encoding='utf-8')
    print(f"wrote {args.out} ({len(out)} chars)", file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
