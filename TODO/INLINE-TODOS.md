# MBForge 代码内未实现注释（inline TODOs）

> 本文件汇集**项目自研代码**中以注释形式标记的"待办 / 占位 / 临时"信号。
> 第三方 vendored 代码（`src/mbforge/parsers/molecule/molscribe_inference/`、`setup/MolScribe/`、`ref/`）按 AGENTS.md "迁移期 Python 冻结" 规则不在范围内。
> 核验方式：ripgrep 搜索 `\b(TODO|FIXME|HACK|XXX)\b` + 中文"占位/临时/暂不/后续/等[到M]?\d+ 再[换改做]" + Rust 宏 `todo!()/unimplemented!()`

---

## 未实现 / 占位（2 处）

### I-02. Embedding HTTP sidecar 待替换 ONNX
- **文件**：`src-tauri/src/core/vector/embedding.rs:4`
- **注释原文**：
  > 当前通过 HTTP 调用 Python sidecar 的 /embed 端点，后续可替换为本地 ONNX Runtime (`ort` crate)。
- **关联上下文**：模块顶部 `//!` 文档注释
- **对应 OPEN.md**：[O-06](#)

### I-04. Anthropic thinking 内容暂不输出
- **文件**：`src/mbforge/models/anthropic_llm.py:150`
- **代码**：`pass`（chunk.type == "thinking_delta" 分支）
- **判断**：⚠️ **设计取舍**，非 bug。若用户要求保留 thinking 链可加开关
- **对应 OPEN.md**：无（设计性，不算待办）

---

## Deprecated 但未删除（清理建议）

### I-05. `img_to_pdf_rect`
- **文件**：`src/mbforge/parsers/molecule/coords.py:85-113`
- **标记**：`.. deprecated::` — 新代码请用 `image_to_pdf_bbox()`
- **状态**：未删除

### I-06. `pdf_to_img_rect`
- **文件**：`src/mbforge/parsers/molecule/coords.py:115-141`
- **标记**：`.. deprecated::` — 新代码请用 `pdf_to_image_bbox()`
- **状态**：未删除
- **对应 OPEN.md**：[O-23](#)

---

## 排除范围（不视为项目待办）

| 路径 | 原因 |
|------|------|
| `src/mbforge/parsers/molecule/molscribe_inference/` | vendored MolScribe 副本（与 setup/MolScribe 同源） |
| `setup/MolScribe/` | 第三方安装包 |
| `ref/` | 参考资料 / 旧实现 |
| `graphify-out/` | 构建产物缓存 |
| `docs/` | 已发布文档（含历史 TODO 描述） |
| `frontend/src/i18n/locales/*.json` | 翻译词条里 "todo" 是 UI 标签，不是待办 |
| `frontend/src/**/__tests__/` 中的 `stub:` | 单测占位 mock，不是生产代码待办 |

---

## 核验命令（可重跑）

```bash
# Rust 代码内 TODO（含中文暗示）
rg -n --no-heading -t rust -i \
  -e "\bTODO\b" -e "\bFIXME\b" -e "\bHACK\b" -e "\bXXX\b" \
  -e "todo!\(\)" -e "unimplemented!\(\)" \
  -e "待办|待实现|未实现|占位|先这样|暂不|权宜|后续" \
  -e "等[到M]?\d+" \
  src-tauri/src

# Python（排除 molscribe_inference）
rg -n --no-heading -t py -i -g '!molscribe_inference/**' \
  -e "\bTODO\b" -e "\bFIXME\b" -e "\bHACK\b" -e "\bXXX\b" \
  -e "待办|占位|后续" -e "deprecated" \
  src/mbforge

# 前端
rg -n --no-heading -t ts --type-add 'tsx:*.tsx' -t tsx -t js \
  -g '!i18n/locales/**' -g '!**/__tests__/**' \
  -e "占位|待办|TODO|FIXME" \
  frontend/src
```

> **维护规则**：
> 1. 任何完成/废弃的占位接口删除时，连同本文件对应条目一起删除
> 2. 新增 `TODO`/`FIXME`/`HACK` 注释时，**当周**在本文件登记（避免散落）
> 3. 超过 1 季度未动的 `I-NN` 条目升级到 `OPEN.md`（带优先级）
