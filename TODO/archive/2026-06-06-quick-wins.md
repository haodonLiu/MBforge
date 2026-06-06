# 2026-06-06 — 快速胜利包：vector_store.rs 合并 + llm_json 迁移

> 本文件归档 2026-06-06 完成的两项低风险高 ROI 修复。
> 净效果：删 13 行冗余文件 + 删 50 行自研 JSON 修复 + 加 1 个 crate 依赖 + 加 6 个单测。

---

## 1. 删除旧 `vector_store.rs`（O-23，5 分钟）

**起因**：[TECH-DEBT #2](TECH-DEBT.md) — 旧 13 行 `core/vector/vector_store.rs` 被 `sqlite_vector_store.rs` 取代但未删除。

**变更**：
- 把 `SearchResult` struct 移到 `sqlite_vector_store.rs:14-25`（带历史注释）
- `knowledge_base.rs:22` import 合并为 `use crate::core::vector::sqlite_vector_store::{SqliteVectorStore, SearchResult, reciprocal_rank_fusion};`
- 删除 `core/vector/vector_store.rs`
- `core/vector/mod.rs` 移除 `pub mod vector_store;`

**验证**：`cargo check --lib` exit 0；`rg vector_store:: src-tauri/src` 0 命中旧模块路径（仅 `sqlite_vector_store::SearchResult` 新引用）。

---

## 2. 用 `llm_json` 替换自研 `extract_json` 修复（O-14，1.5 小时）

**起因**：[OPEN.md O-14](OPEN.md) — `post_process.rs:501-598` 自研 `extract_json` + `repair_truncated_json` 共 97 行。

**变更**：
- `Cargo.toml` 加 `llm_json = "1.0.3"`
- `post_process.rs::extract_json` 简化为 ~30 行：先 `serde_json::from_str` 快速路径，失败 fallback 到 `llm_json::loads`
- `repair_truncated_json` 函数**整段删除**（llm_json 内置截断修复）
- 新增 `mod extract_json_tests` 6 个单测：合法对象 / trailing comma / markdown fence / think block / 截断 / 拒绝 scalar

**行为差异**：
- ✅ 全部 6 个原有用例 + 3 个旧 `tests::*` 单测继续通过
- ✅ 强制 `is_object() || is_array()`——llm_json 把"not json at all"误判为 `Ok(String)` 的情况被 reject 掉
- ⚠️ 错误信息格式略变（增加"LLM response is not a JSON object/array"分支）

**验证**：`cargo test --lib extract_json` 9 passed / 0 failed。

---

## 3. 顺带记录：预存的 lib 测试失败

`cargo check --tests` 报错 31 个 `failed to resolve: could not find \`xxx\` in \`parsers\`/\`core\``：
- `tests/test_e2e_real_pdf.rs` 引用 `parsers::headings` / `parsers::association` / `parsers::post_process`
- `tests/test_pipeline_integration.rs` 引用 `parsers::headings` / `core::knowledge_base` / `core::resource_manager`

这些模块在各自 `mod.rs` 没 `pub` 出来。**与本次重构无关**——属于历史预存问题，建议下个迭代统一处理（TECH-DEBT 候选）。

---

## 4. 净统计

| 项 | 改动 |
|----|------|
| 删除文件 | 1（vector_store.rs，13 行）|
| 删除函数 | 1（repair_truncated_json，50 行）|
| 新增函数 | 1（extract_json 重写 + 6 测试，约 +60 行）|
| Cargo.toml | +1 依赖（llm_json 1.0.3）|
| `cargo check --lib` | exit 0 ✅ |
| `cargo test --lib extract_json` | 9/9 passed ✅ |
