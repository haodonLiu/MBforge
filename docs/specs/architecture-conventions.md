# 架构约定

> 版本: 0.3.0 | 日期: 2026-07-10
> 规定模块边界、分层职责和新增代码的约束。
> 适用代码库：Python-only（无 Rust / Tauri）。
> 备注：`src/mbforge/gui/` 是历史 Dear PyGui 桌面壳，零调用方，作为参考保留；
> `backends/moldet.py` 是 2026-07-08 MolDetv2-FT 迁移的兼容 shim，所有移除符号抛
> `AttributeError` 并指向新位置，仅 `default_model_dir()` 仍可用（被
> `legacy_models.py` 调用）。

## 五层架构

```
UI 层          frontend/src/              React 组件、页面路由、状态管理 (React 19)
    │
HTTP 层        frontend/src/api/http/     httpFetch / SSE 流式客户端
    ↓
路由层          src/mbforge/routers/       FastAPI APIRouter（19 个，/api/v1/*）
    ↓
核心层          src/mbforge/core/          数据库、知识库、缓存、库管理、ArtifactResolver
    ↓
业务层          src/mbforge/agent/         LangGraph Agent + 工具
              src/mbforge/pipeline/       9-stage PDF 流水线
    ↓
后端层          src/mbforge/backends/      懒加载 ML 模型（moldet_v2_ft, molscribe, ocr）
              src/mbforge/openkb/         OpenKB + PageIndex 向量检索
              SQLite + filesystem         per-project: {root}/index/*.db + storage/{doc_id}/
```

## 分层约束

| 规则 | 说明 |
|---|---|
| 单向依赖 | UI → HTTP → 路由 → 核心 → 业务 → 后端；后端不可反向调用上层 |
| 路由层薄 | `routers/` 只做参数校验 + 调 core/agent/pipeline，不写业务逻辑 |
| 核心层数据库操作 | `core/database.py` 统一管理 SQLite 连接（molecules.db + knowledge_base.db） |
| 业务层无状态 | `pipeline/` 阶段函数接收 context，无全局状态 |
| 后端懒加载 | `backends/*.py` 模块导入不实例化；首次调用才加载模型（5-30s 代价） |

## 新增代码的约束

### 新增 FastAPI 路由

1. 在 `src/mbforge/routers/` 创建 `APIRouter`。
2. 前缀统一 `/api/v1/{资源名}`。
3. 在 `src/mbforge/app.py:67-86` 通过 `app.include_router()` 注册（保持排序）。
4. 必须有类型注解（`from __future__ import annotations`）+ docstring。
5. 错误用 `MBForgeError` 子类（`utils/helpers.py`），不抛裸 `Exception`。
6. 同步阻塞 IO 用 `await loop.run_in_executor(None, lambda: ...)`。

### 新增 Agent 工具

1. `BaseTool` 子类实现于 `src/mbforge/agent/tools.py`。
2. 注册到文件顶部工具列表。
3. 如需发现提示，更新 `agent/graph.py` 的 system prompt。

### 新增 Pipeline 阶段

1. `src/mbforge/pipeline/{stage}.py` 实现 `run(context) -> StageResult`。
2. 接入 `pipeline/runner.py` 阶段列表。
3. 进度推送：在 `routers/events.py` 添加 `pipelines_{stage}_run` 事件。

### 新增前端组件

1. 页面级放 `frontend/src/components/{feature}/`，PascalCase。
2. Props 用 `interface`，禁用 `any`。
3. API 调用统一放 `frontend/src/api/http/`，用 `httpFetch`/`sse`。
4. 错误用 `AppError.fromResponse()`，`ErrorCode` 来自 `@/utils/errors`。
5. 国际化键同步加入 `i18n/locales/{en,zh-CN}.json`。

## 状态管理约定

| 层级 | 状态类型 | 模式 |
|------|---------|------|
| 前端 | 局部状态 | `useState` |
| 前端 | 跨组件 | Context（`context/AppContext.tsx`） |
| 前端 | 持久 | `localStorage`，键名 `mbforge_` 前缀 |
| 后端 | 进程内 | `app.state` 单例 |
| 后端 | 持久 | SQLite + OpenKB PageIndex |
| 后端 | 用户配置 | `%APPDATA%\MBForge\settings.json` |

## 配置优先级

`MBFORGE_*` 环境变量 > `~/.config/MBForge/config.json` > 代码默认值。

## 迁移历史

- **2026-06-29**：Rust/Tauri → Python-only 迁移完成（commit `4b70ae8`）
- **2026-07-07**：Zvec/ChromaDB → OpenKB + PageIndex 完成（commit `4fbde55`）
- **2026-07-07**：所有 Qwen3 embed/rerank 移除（KB 改 PageIndex 树推理 + dense rerank via LLM）
- **2026-07-08**：MolDetv2 Doc+General → MolDetv2-FT（联合分子 + coref 标识符检测，
  单次推理）。`backends/moldet.py` 保留为兼容 shim。
- **2026-07-10**：新增 first-class `evidence` 表（schema v3 → v4 迁移），统一
  `ArtifactResolver` 路径解析层，`scripts/migrate_artifact_paths.py` 用于老库迁移。