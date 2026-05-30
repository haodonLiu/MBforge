# MBForge Agent 工作规范

## 编译与测试

### 快速开发循环

本项目 Rust 侧测试数量较多（~145 个），全量运行耗时较长。开发时应优先运行**目标模块测试**，而非全量测试。

#### 只跑改动的模块

```bash
# 核心数据层
cargo test --lib embedding::
cargo test --lib vector_store::
cargo test --lib knowledge_base::
cargo test --lib document_tree::

# 解析层
cargo test --lib headings::
cargo test --lib sections::
cargo test --lib pipeline::

# Agent 层
cargo test --lib executor::
```

#### 一键脚本

```powershell
cd src-tauri
.\test-quick.ps1
```

输出示例：
```
Total: 30 targeted tests passed
```

#### 全量测试（仅 CI / 发布前）

```bash
cargo test --lib
```

### 编译配置

`src-tauri/.cargo/config.toml` 已配置 dev 环境 suppress warnings：

```toml
[build]
rustflags = ["-A", "warnings"]
```

`cargo check` 默认只看 errors。如需恢复 warnings，临时注释掉该配置即可。

### 前端类型检查

```bash
cd frontend
npx tsc --noEmit
```

## 代码风格

- Rust：遵循现有代码风格，不引入新 lint 规则
- Python：保留现有代码，迁移期不强制修改
- 前端：TypeScript 严格模式已启用

## 模块边界

| 层级 | 职责 | 关键文件 |
|------|------|----------|
| `core/` | 数据层：embedding、向量存储、知识库、文档树 | `embedding.rs`, `vector_store.rs`, `knowledge_base.rs`, `document_tree.rs` |
| `parsers/` | 解析层：PDF 提取、heading/section 分块 | `headings.rs`, `sections.rs`, `pipeline.rs` |
| `commands/` | Tauri IPC 命令注册 | `main.rs` 中的 `invoke_handler` |
| `frontend/` | UI 层：桥接调用、组件 | `tauri-bridge.ts`, `*.tsx` |

## 迁移期规则

- Rust 新代码优先，Python 代码冻结（除 bugfix 外不改）
- 新增功能必须在 Rust 侧实现
- Python sidecar 仅保留：模型推理（Embedding/VLM/LLM）、MolDetv2/MolScribe
- 前端调用逐步从 HTTP API 迁移到 Tauri `invoke()`
