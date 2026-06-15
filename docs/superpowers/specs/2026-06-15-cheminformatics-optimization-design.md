# Cheminformatics Module Optimization — Design Spec

**Date**: 2026-06-15
**Status**: Approved
**Scope**: 封装既有 chem 纯计算 + MoleculeEngine CRUD 为 Tauri 命令，暴露前端调用接口

## 1. 目标

`chem/*` 与 `molecule/*` 子模块已实现 30+ 高频函数（chematic-backed），但仅 8 个暴露为 Tauri 命令，前端只能间接走 sidecar HTTP。本设计封装剩余 26 个函数为 IPC 命令，前端可直接 `invoke()` 调用。

**不实现**：新 chem 算法、新 UI、新前端调用方。仅补全命令层 surface。

## 2. 文件布局

```
src-tauri/src/commands/
├── chem_ops.rs          [NEW]  14 个纯计算命令，无 state
└── molecule_admin.rs    [NEW]  12 个 engine CRUD 命令

frontend/src/api/tauri/
├── chem.ts              [NEW]  14 个 chemXxx 函数 + 类型
└── moleculeAdmin.ts     [NEW]  12 个 molAdminXxx 函数
```

**不变更**：`chem.rs` / `markush.rs` / `molecule_engine.rs` 函数体；`molecule.ts` 既有 API；`molecule.rs` 既有 17 个 `mol_*` 命令。

## 3. `chem_ops.rs` — 14 命令

| 命令 | 签名 | 包装目标 |
|------|------|----------|
| `chem_canonicalize` | `(smiles: String) -> Result<String, String>` | `chem::canonical_smiles` |
| `chem_substructure_search` | `(query: String, candidates: Vec<(String,String)>, threshold: Option<f64>) -> Result<Vec<(String,String,f64)>, String>` | `chem::substructure_search_with_filter` |
| `chem_smiles_to_molecode` | `(smiles: String, name: String) -> Result<String, String>` | `chem::smiles_to_molecode` |
| `chem_smiles_to_esmiles` | `(smiles: String, tags: Vec<EsTag>) -> Result<String, String>` | `esmiles::smiles_to_esmiles` |
| `chem_parse_esmiles_tags` | `(input: String) -> Result<(String, Vec<EsTag>), String>` | `esmiles::parse_esmiles_tags` |
| `chem_sanitize_esmiles` | `(raw: String) -> Result<String, String>` | `chem_validate::sanitize_esmiles` |
| `chem_separate_esmiles_layers` | `(input: String) -> Result<LayerSplit, String>` | `chem_validate::separate_esmiles_layers` |
| `chem_validate_smiles_batch` | `(list: Vec<String>) -> Result<Vec<ValidateResult>, String>` | `chem_validate::validate_smiles_batch` |
| `chem_preprocess_smiles` | `(smiles: String) -> Result<String, String>` | `preprocess::preprocess_smiles` |
| `chem_preprocess_rgroup_name` | `(name: String) -> Result<String, String>` | `preprocess::preprocess_rgroup_name` |
| `chem_markush_parse` | `(input: String) -> Result<MarkushPattern, String>` | `markush::parse_esmiles` |
| `chem_markush_check` | `(esmiles: String, query: String, ctx: Option<String>) -> Result<MarkushOverlap, String>` | `markush::analyze_markush_coverage` |
| `chem_core_smiles` | `(input: String) -> Result<String, String>` | `markush::core_smiles` |
| `chem_gesim_atom_mapping` | `(a: String, b: String) -> Result<Vec<(usize, usize)>, String>` | `gesim::match_mapping` |

**特征**：无 `tauri::State`，无 `MutexGuard`，无 `project_root`。纯函数包装。

## 4. `molecule_admin.rs` — 12 命令

**统一签名**：`async fn mol_admin_xxx(state, project_root: String, ...) -> Result<T, String>`

| 命令 | engine 方法 | 写？ |
|------|------------|------|
| `mol_admin_get` | `get_molecule` | 读 |
| `mol_admin_search_by_smiles` | `search_by_smiles` | 读 |
| `mol_admin_search_text` | `search_text` | 读 |
| `mol_admin_list` | `list_all` | 读 |
| `mol_admin_store_stats` | `get_store_stats` | 读 |
| `mol_admin_add` | `add_molecule` | 写 |
| `mol_admin_update` | `update_molecule` | 写 |
| `mol_admin_update_status` | `update_status` | 写 |
| `mol_admin_delete` | `delete_molecule` | 写 |
| `mol_admin_add_similarity` | `add_similarity_relation` | 写 |
| `mol_admin_check_markush` | `check_markush` | 读 |
| `mol_admin_parse_esmiles` | `parse_esmiles` | 读 |

**统一模板**：
```rust
#[tauri::command]
pub async fn mol_admin_xxx(
    state: tauri::State<'_, MoleculeEngineState>,
    project_root: String,
    ...
) -> Result<T, String> {
    get_or_init_engine(&state, &project_root).await?;
    let guard = state.inner.lock().await;
    let engine = guard.as_ref().map(|(_, e)| e)
        .ok_or_else(|| "MoleculeEngine not initialized".to_string())?;
    engine.xxx(...).await.map_err(|e| { log::error!(...); e.to_string() })
}
```

## 5. 前端 API

### `frontend/src/api/tauri/chem.ts`

- 5 个本地类型：`EsTag` / `LayerSplit` / `ValidateResult` / `MarkushPattern` / `MarkushOverlap`
- 14 个 `chemXxx` 异步函数，统一通过 `invokeWithError(..., ErrorCode.ApiError)` 包装
- Tauri `invoke` 参数命名遵循 camelCase 转换（Rust 侧 `#[tauri::command]` 自动 serde 转换）

### `frontend/src/api/tauri/moleculeAdmin.ts`

- 复用 `MoleculeRecord_` 类型：`export type { MoleculeRecord_ as MoleculeRecord }`
- 12 个 `molAdminXxx` 异步函数，同 `chemXxx` 错误处理风格

**既有 `molecule.ts` 不变**。`CliffsTab` / `AnalogSearchPanel` 等现有调用方 0 影响。

## 6. 错误处理

| 失败 | Rust | IPC | 前端 |
|------|------|-----|------|
| SMILES 解析失败 | `Err("SMILES parse failed: ...")` | Promise reject | `ApiError` 抛出 |
| engine 未初始化 | `Err("MoleculeEngine not initialized")` | reject | `ApiError` 抛出 |
| 写操作 DB 失败 | `Err("...")` | reject | `ApiError` 抛出 |
| `chem_validate_smiles` 单条失败 | 返回 `SmilesValidation { valid: false, ... }` | **resolve** | 业务层判 `valid` |

不引入新错误码。`ErrorCode.ApiError` 现有枚举足够。

## 7. 测试

**不新增** `chem_ops` / `molecule_admin` 集成测试（包装层无新分支）。

**新增** 2 个轻量单元测试（`chem_ops.rs` 末尾 `#[cfg(test)] mod tests`）：
- `test_chem_sanitize_strips_markdown` — sanitize 去除反引号
- `test_chem_parse_esmiles_tags_roundtrip` — 解析 + 标签计数

为测试暴露 2 个 `pub(crate) fn` 包装，避开 `#[tauri::command]` 宏。

依赖既有覆盖：
- `chem.rs` / `esmiles.rs` / `markush.rs` / `preprocess.rs` / `gesim.rs` 各自 `#[cfg(test)] mod tests`（含 ECFP4 / Tanimoto / Markush 解析 / 预处理 / Gesim 全覆盖）
- `molecule_engine.rs` / `molecule_store.rs` 自身测试

## 8. Pre-flight 必需变更

2 行 `pub` 标记（surgical，零函数体改动）：
- `src-tauri/src/core/chem/chem.rs::canonical_smiles` → `pub fn`
- `src-tauri/src/core/chem/markush.rs::core_smiles` → `pub fn`

## 9. 实施顺序

1. `pub` 标记 2 处
2. 新建 `chem_ops.rs`（14 命令 + 2 测试）
3. 新建 `molecule_admin.rs`（12 命令）
4. `commands/mod.rs` + `lib.rs` 注册 26 个命令
5. 新建 `chem.ts`（14 函数 + 5 类型）
6. 新建 `moleculeAdmin.ts`（12 函数）

## 10. 完成标准

```bash
cd src-tauri && cargo check      # exit 0
cd src-tauri && cargo test       # all pass（含 2 新测试）
cd frontend && npm run build     # exit 0
```

`git diff --stat` 预期 8 文件变更：
- 1 行改（chem.rs pub）
- 1 行改（markush.rs pub）
- 250 行新（chem_ops.rs）
- 280 行新（molecule_admin.rs）
- 2 行新（commands/mod.rs）
- 30 行新（lib.rs invoke_handler）
- 200 行新（chem.ts）
- 120 行新（moleculeAdmin.ts）

## 11. 风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| 命令名拼错 | 低 | `cargo check` 单次捕获 |
| `MoleculeRecord` 字段前端拼错 | 中 | 复用 `MoleculeRecord_` 类型 |
| 写操作并发 | 中 | `Mutex<MoleculeDatabase>` 已保证串行，与现有 model 一致 |
| `pub` 暴露引入新下游 | 低 | 加 `pub` 仅增外部使用方，不破坏既有 ABI |

## 12. 不做

- 不改 `chem.rs` / `markush.rs` / `molecule_engine.rs` 函数体
- 不改 `frontend/src/api/tauri/molecule.ts`
- 不写前端调用方
- 不写 E2E 测试
- 不写性能基准
