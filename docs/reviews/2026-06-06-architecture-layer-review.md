# MBForge 代码层次关系审查报告

> 审查日期：2026-06-06
> 审查范围：src-tauri/src/ 目录下的模块依赖与层次边界
> 方法：CodeGraph 静态分析 + 手动代码审查

---

## 一、执行摘要

本次审查基于五层架构约定（UI → Commands → Core → Parsers → Model Server），重点检查了模块间的调用方向和边界合规性。共发现 **3 个严重问题、4 个中等问题、3 个轻微问题**，其中最突出的是 **存在完全不被编译的死代码目录**，以及 **命令层直接穿透调用解析层**。

---

## 二、严重问题（🔴）

### 2.1 `core/executor/` 是完全不被编译的死代码目录

**证据**：
- `core/mod.rs` 中没有 `pub mod executor;`，整个目录 7 个文件不被 Rust 编译器处理
- `core/executor/mod.rs` 引用了不存在的 `crate::core::agent::tools` 模块（因不被编译而不报错）
- 目录内容：
  ```
  core/executor/
  ├── mod.rs          # ToolExecutor 协调器
  ├── arxiv.rs        # arXiv 工具
  ├── document.rs     # 文档工具注册
  ├── fs.rs           # 文件系统工具注册
  ├── kb.rs           # 知识库工具注册
  ├── literature.rs   # 文献工具注册
  └── molecule.rs     # 分子工具注册
  ```

**问题**：
- 与 `core/agent/` 下的 `fs.rs`, `kb.rs`, `molecule.rs`, `document.rs`, `arxiv.rs` **功能完全重复**
- `core/agent/executor_rig.rs`（150 符号）已替代旧 `ToolExecutor`，但旧目录未删除
- 造成命名混淆：`core/agent/executor_rig.rs` vs `core/executor/mod.rs`

**修复建议**：
```bash
# 删除死代码目录
rm -rf src-tauri/src/core/executor/
```
- 确认 `core/agent/executor_rig.rs` 已完整覆盖旧功能后删除
- 如部分旧逻辑未迁移，先合并到 `core/agent/` 对应模块再删除

---

### 2.2 命令层直接调用解析层：`commands/` → `parsers/`

**证据**：

`commands/mod.rs` 第 57-61 行直接注册解析层函数为 Tauri 命令：
```rust
crate::parsers::pipeline::parse_pdf,
crate::parsers::pipeline::post_process_pdf,
crate::parsers::pipeline::process_document,
crate::parsers::pipeline::index_project_rust,
```

`commands/pdf.rs` 深入调用解析层内部函数：
```rust
use crate::parsers::doc_types::OcrBlock;
use crate::parsers::chem::chem_validate::separate_esmiles_layers;
use crate::parsers::chem::vlm_chem::DetectedMolecule;
let result = crate::parsers::pipeline::extract_pdf_workflow(...).await?;
let classified = crate::parsers::pipeline::classify_and_extract(&path).await?;
```

`commands/extractor.rs`：
```rust
use crate::parsers::chem::association::{self, ActivityEntry};
```

**问题**：
- 违反 AGENTS.md 五层架构约定："命令层（commands/）桥接前端与核心层，禁止跨层直接调用"
- 命令层应只调用 `core/` 暴露的 facade，由核心层内部调度解析层
- 这导致解析层的内部实现细节泄漏到命令层，增加重构成本

**修复建议**：
1. 在 `core/` 中建立 PDF 解析的 facade 模块（如 `core::document::ingest_queue` 或新建 `core::pdf`）
2. 将 `commands/mod.rs` 中的 4 个 `parsers::pipeline::*` 命令替换为 `core::*` facade 调用
3. `commands/pdf.rs` 中对 `parsers::pipeline::*` 的调用应下沉到 `core/document/` 或 `core/project/` 中

---

### 2.3 解析层直接驱动核心层的 Agent：`parsers/` → `core::agent`

**证据**：

`parsers/pipeline.rs` 第 338 行：
```rust
use crate::core::agent::rig_adapter::{
    MbforgeAgent, MbforgeAgentSpec, MbforgeProviderConfig
};
```

**问题**：
- 解析层（parsers/）直接实例化和配置 Agent 适配器
- 方向错误：解析层应产出结构化数据（`StructuredData`, `DocumentReport`），核心层消费数据并驱动 Agent
- 这导致解析层与 Agent 架构强耦合，无法独立测试和替换

**修复建议**：
- 将 `pipeline.rs` 中对 `rig_adapter` 的调用上提到核心层
- 解析层只返回数据，由 `core::agent/` 或 `core::document::ingest_queue` 决定何时/如何触发 Agent

---

## 三、中等问题（🟡）

### 3.1 `core/mod.rs` 的向后兼容 re-export 过于宽泛

**证据**：

`core/mod.rs` 中有大量 `pub use` 重导出，使得深层模块可直接通过 `crate::core::*` 访问：
```rust
pub use document::knowledge_base::{get_or_init_kb, kb_search, kb_search_stream, ...};
pub use document::semantic_cache::{SemanticCache, SemanticCacheConfig};
pub use molecule::molecule_engine::{MoleculeEngine, ...};
pub use project::resource_manager;
pub use chem::markush;
```

这导致 `commands/mod.rs` 中直接引用：
```rust
crate::core::knowledge_base::kb_search,       // 实际在 core::document::knowledge_base
crate::core::resource_manager::resources_check, // 实际在 core::project::resource_manager
crate::core::chem::sar::sar_find_scaffold,    // 实际在 core::chem::sar
```

**问题**：
- 模糊了子目录边界，外部调用者不必知道正确的模块路径
- 重构时影响范围不可预测（重导出增加了隐式依赖面）
- 助长了命令层直接引用核心层深层模块的习惯

**修复建议**：
- 逐步移除 `core/mod.rs` 的 `pub use` 重导出
- 外部代码应使用正确路径：`crate::core::document::knowledge_base::kb_search`
- 给每个子目录提供清晰的 `pub mod` 声明，但不跨越 re-export

---

### 3.2 `core/agent/` 内部新旧架构并存，职责不清

**证据**：

`core/agent/mod.rs` 同时导出两套模块：
```rust
// 旧 ReAct Agent 模块
pub mod context;
pub mod document;
pub mod fs;
pub mod kb;
pub mod memory;
pub mod molecule;
pub mod skills;
pub mod trajectory;

// 新 Rig 框架模块
pub mod rig_adapter;
pub mod rig_hooks;
pub mod rig_memory;
pub mod executor_rig;
pub mod arxiv_rig;
pub mod observability;
```

- `arxiv.rs`（旧）与 `arxiv_rig.rs`（新，由 `ref/migrate_to_rig.py` 自动生成）并存
- `fs.rs`, `kb.rs`, `molecule.rs`, `document.rs` 仅被 `executor_rig.rs` 使用，对外无独立调用方

**问题**：
- 迁移期未完成的中间状态长期停留
- 旧模块与新模块职责边界不清（都提供"工具"）
- `executor_rig.rs` 命名与废弃的 `core/executor/` 产生混淆

**修复建议**：
1. 完成 Rig 迁移后删除旧模块：`context.rs`（如已被 `rig_adapter` 替代）、`arxiv.rs`
2. 将 `fs.rs`, `kb.rs`, `molecule.rs`, `document.rs` 的公共函数合并到 `executor_rig.rs` 中，或重命名为 `tools_fs.rs` 等以明确其附属角色
3. 统一工具注册入口：只保留 `executor_rig.rs` 作为工具集 facade

---

### 3.3 `commands/` 命名与核心层不一致

**证据**：

| 命令层 | 核心层 |
|--------|--------|
| `commands/mol_engine.rs` | `core/molecule/` |
| `commands/mol_store.rs` | `core/molecule/molecule_store.rs` |
| `commands/molecode.rs` | `core/chem/molecode.rs` |
| `commands/gesim.rs` | `core/chem/gesim.rs` |

**问题**：
- `mol_` 缩写与 `molecule` 完整名混用
- `gesim.rs` 在命令层是顶层模块，但在核心层属于 `chem/` 子目录

**修复建议**：
- 统一命名为 `molecule_engine.rs`, `molecule_store.rs`
- 或考虑将 `gesim.rs` 命令合并到 `molecule.rs` 中

---

### 3.4 `parsers/` 对 `core/` 业务模块的较深耦合

**证据**：

```rust
// parsers/chem/chem_validate.rs
crate::core::chem::chem::validate_smiles(&cleaned)

// parsers/chem/claim_policy.rs
crate::core::chem::markush::parse_esmiles(candidate);
crate::core::chem::markush::analyze_markush_coverage(...);

// parsers/pipeline/helpers.rs
crate::core::molecode::esmiles_to_molecode(smiles_input, name)

// parsers/pipeline.rs
crate::core::molecule_store::{MoleculeDatabase, MoleculeImage, MoleculeRecord};
crate::core::document::knowledge_base::KnowledgeBase::new(...);
```

**问题**：
- 解析层直接操作分子数据库、知识库和化学验证逻辑
- 虽然业务上合理，但耦合度较高：解析层既负责"解析"又负责"持久化"

**修复建议**：
- 将数据库写入操作（`molecule_store`, `knowledge_base`）上提到 `core::document::ingest_queue` 或 pipeline 的更高层
- 解析层只返回纯数据结构，由核心层决定持久化策略

---

## 四、轻微问题（🟢）

### 4.1 `core/document/` 子目录职责混杂

**问题**：
- `content_cache.rs`, `file_cache.rs`, `ingest_queue.rs` 是通用基础设施
- 与 `knowledge_base.rs`, `document_tree.rs`, `summary.rs` 等业务模块混在一起

**修复建议**：
- 考虑将缓存/队列模块提取到 `core/cache/` 或 `core/queue/` 子目录

---

### 4.2 前端 `tauri-events.ts` 与 Rust 常量的手动同步风险

**证据**：
```typescript
/** Tauri IPC event names — must match `src-tauri/src/core/constants.rs`.
 * Single source of truth for both Rust emitters and TS listeners.
 * Drift between the two silently breaks event delivery with no compile error,
 * so keep this file in sync with the Rust constants module.
 */
```

**修复建议**：
- 使用 Tauri 的 `ts-rs` 或构建时代码生成，将 Rust 常量自动导出到 TypeScript
- 或至少添加 CI 检查，确保两个文件的字符串值一致

---

### 4.3 `commands/mod.rs` handler 列表过长（131 行）

**问题**：
- `handler()` 函数聚合了 70+ 个命令注册
- 虽然按注释分组，但随着命令增加，维护成本上升
- 大量命令直接引用 `crate::core::*` 和 `crate::parsers::*`，而不是通过 `commands/` 子模块包装

**修复建议**：
- 每个 commands/ 子模块自行注册其命令，handler 只做聚合
- 禁止在 handler 中直接引用 `crate::parsers::*` 和 `crate::core::*` 深层路径

---

## 五、依赖关系图（现状 vs 理想）

### 现状（违规调用以 🔴 标出）

```
frontend/ ──invoke──► commands/ ──🔴──► parsers/
                          │
                          ├──► core/agent/ ──► core/chem/
                          │       │
                          │       ├──► core/document/
                          │       ├──► core/molecule/
                          │       └── executor_rig.rs  (调用 fs/kb/molecule/document)
                          │
                          ├──► core/project/
                          └──► core/vector/

parsers/ ──🔴──► core::agent::rig_adapter   (反向驱动)
parsers/ ─────► core::chem::markush         (较深耦合)
parsers/ ─────► core::molecule_store        (数据库操作)

core/mod.rs 大量 pub use ──► 模糊子目录边界
core/executor/ 完全不编译 ──► 死代码
```

### 理想状态

```
frontend/ ──invoke──► commands/ ─────► core/
                          │              │
                          │              ├── agent/ (rig 驱动)
                          │              ├── chem/
                          │              ├── document/ (含 ingest_queue facade)
                          │              ├── molecule/
                          │              ├── project/
                          │              └── vector/
                          │
                          └── 禁止直接调用 parsers/

core/document/ingest_queue ──► parsers/ (核心层调度解析)
core/agent/ ──► core::executor/ (工具 facade，统一注册)

parsers/ ─────► core::types     (仅共享类型)
parsers/ ─────► core::helpers   (仅工具函数)
parsers/ ─────► core::constants (仅常量)
parsers/ ─────► core::http      (仅 HTTP 客户端)

删除：core/executor/ (死代码)
删除：core/mod.rs 的宽泛 pub use
```

---

## 六、修复优先级

| 优先级 | 问题 | 影响 | 工作量 |
|--------|------|------|--------|
| P0 | 删除 `core/executor/` 死代码 | 减少混淆、降低维护成本 | 1 小时 |
| P0 | 隔离 `commands/` → `parsers/` 调用 | 架构合规、降低耦合 | 1-2 天 |
| P1 | 移除 `core/mod.rs` 宽泛 re-export | 清晰边界、重构安全 | 半天 |
| P1 | 清理 `core/agent/` 旧模块 | 明确职责、减少重复 | 1 天 |
| P2 | 解耦 `parsers/` → `core/` 业务模块 | 独立测试、可替换性 | 2-3 天 |
| P2 | 统一 commands/ 命名 | 可读性 | 2 小时 |
| P3 | 前端事件常量自动化同步 | 防止运行时静默错误 | 半天 |

---

## 七、附录：审查数据

- **索引文件数**：371（Rust 117 + TypeScript/TSX 163 + Python 89）
- **总节点数**：5,324
- **总边数**：11,727
- **核心层死代码**：`core/executor/`（7 文件，~400 行）
- **跨层违规调用**：commands/ → parsers/（4 处直接注册 + 多处代码引用）
- **反向调用**：parsers/ → core::agent（1 处）
