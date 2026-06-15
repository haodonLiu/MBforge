# 架构约定

> 版本: 0.1.0 | 日期: 2026-06-04
> 规定模块边界、分层职责和新增代码的约束。

## 五层架构

```
UI 层          frontend/src/              React 组件、页面路由、状态管理
    │
命令层          src-tauri/src/commands/    Tauri IPC 命令注册，桥接前端与 Rust 核心
    │
核心层          src-tauri/src/core/        Agent、数据持久化、向量存储、分子数据库
    │
解析层          src-tauri/src/parsers/     PDF 解析管线、图像提取、关联引擎
    │
模型服务        src/mbforge/model_server/  FastAPI REST API、模型单例管理
```

## 分层约束

| 规则 | 说明 |
|---|---|
| 单向依赖 | UI → 命令 → 核心 → 解析；模型服务可被核心调用，但不可反向调用 |
| 命令层无业务逻辑 | `commands/` 只做参数校验和调用转发，不实现业务逻辑 |
| 核心层数据库操作 | `core/` 直接操作 SQLite 数据库（molecules.db + vectors.db），通过 `core/db.rs` 统一管理连接 |
| 解析层无状态 | `parsers/` 模块为纯函数或轻量客户端，不持有全局状态 |

## 新增代码的约束

### 新增 Rust Tauri 命令

1. 在 `commands/` 的适当模块中定义 `#[tauri::command]`。
2. 命名：`{模块}_{动作}`，如 `agent_init`、`mol_store_search`。
3. 在 `commands/mod.rs` 的 `handler()` 中通过 `generate_handler!` 注册。

### 新增 Rust Agent 工具（rig-core 模式）

1. 在 `core/agent/executor_rig.rs` 中声明 `struct <Name>Tool` + `#[derive(Deserialize, JsonSchema)]` Args。
2. 实现 `impl Tool for <Name>Tool`，`call()` 中调用 `core/agent/{fs,kb,document,molecule}.rs` 中的 `native_*` 自由函数。
3. 在 `core/agent/rig_adapter.rs::assemble_rig_tool_vec()` 中添加 `tools.push(Box::new(<Name>Tool::new(...)))` 一行注册。
4. 工具名用 `snake_case`，描述必须清晰说明输入输出格式。

### 新增 FastAPI 路由

1. 在 `model_server/routers/` 创建 `APIRouter`。
2. 前缀统一使用 `/api/v1/{资源名}`。
3. 在 `main.py` 通过 `app.include_router()` 注册。
4. 必须有类型注解和 docstring。

### 新增 PDF 解析后端

1. 在 `parsers/` 创建客户端模块。
2. 实现异步接口：`async fn parse(&self, input: &str) -> Result<ParsedOutput, String>`。
3. 在 `pipeline.rs` 的解析器选择逻辑中添加分支。

### 新增前端页面/组件

1. 页面级组件放入 `frontend/src/components/`，命名 `PascalCase.tsx`。
2. Props 用 `interface` 定义，不允许 `any`。
3. 新增 API 调用统一放入 `frontend/src/api/`，优先使用 Tauri `invoke()`。

## 状态管理约定

| 层级 | 状态类型 | 模式 |
|------|---------|------|
| 前端 | 局部状态 | `useState` |
| 前端 | 跨组件状态 | Props 传递，复杂场景用 Context |
| 前端 | 持久状态 | `localStorage`，键名以 `mbforge_` 前缀 |
| Rust | Tauri 应用状态 | `Arc<RwLock<T>>` |
| Rust | 读多写少 | `RwLock`，读用 `.read().await`，写用 `.write().await` |

## 迁移完成声明

**Python → Rust 迁移已完成。** Python sidecar 仅保留以下职责：

- **Embedding**（Qwen3）— 文本向量化
- **Rerank**（Qwen3）— 检索结果重排序
- **MolDet**（YOLO）— PDF 图像中的分子检测
- **MolScribe**（Swin Transformer）— 分子图像 → SMILES 识别

所有代码（含 Python 侧）均须遵守本规范，不再有"旧代码豁免"。
