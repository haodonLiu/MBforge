# 架构约定

> 版本: 0.4.0 | 日期: 2026-07-14  
> 规定模块边界、分层职责和新增代码的约束。  
> 适用代码库：Python-only 后端 + React 前端（无 Rust / Tauri / Dear PyGui）。  
> 唯一官方 UI：`frontend/`（React 19 + Vite 8）。入口：`python -m mbforge` 或
> `uvicorn mbforge.app:app`。  
> 布局决策见 [ADR 0001](../adr/0001-canonical-library-layout.md)。  
> 管线细节见 [pipeline-stages.md](../architecture/pipeline-stages.md)。  
> 若与代码冲突，**以代码为准**。

## 五层架构

```
UI 层          frontend/src/              React 组件、路由、AppContext
    │
HTTP 层        frontend/src/api/http/     httpFetch
               frontend/src/api/query/    React Query hooks + SSE 入缓存
    ↓
路由层          src/mbforge/routers/       FastAPI APIRouter（/api/v1/*）
    ↓
核心层          src/mbforge/core/          library、database、artifact、layout、KB
               src/mbforge/openkb/        OpenKB + PageIndex
    ↓
业务层          src/mbforge/agent/         LangGraph agent + tools
               src/mbforge/pipeline/      7-stage PDF 流水线
    ↓
后端层          src/mbforge/backends/      懒加载 ML（moldet_v2_ft、molscribe、ocr）
               SQLite + filesystem        {root}/.mbforge/library.db + storage/{doc_id}/
```

## 分层约束

| 规则 | 说明 |
|---|---|
| 单向依赖 | UI → HTTP → 路由 → 核心/业务 → 后端；后端不可反向调用上层 |
| 路由层薄 | `routers/` 只做校验 + 调 core/agent/pipeline，不堆业务 |
| 数据库 | `core/database.py` + 统一 `{root}/.mbforge/library.db` |
| 路径 | 库级 `LibraryLayout`；文档级 `ArtifactResolver`；禁止裸拼接 `storage/` |
| 管线无全局状态 | 状态在 `PipelineContext`；阶段实现 `StageExecutor` |
| 后端懒加载 | `backends/*` 导入不实例化；首次调用再加载模型（约 5–30 s） |
| 配置入口 | 仅 `mbforge.utils.config` 的 load/save/update/reset |

**字段名**：Python `library_root`，TS `libraryRoot`。禁止新增 `project_root` /
`projectRoot` 调用点。

**MolDet**：新代码只用 `backends/moldet_v2_ft.py`。`backends/moldet.py` 是兼容
shim（已移除符号抛 `AttributeError`）。

## 新增代码约束

### 新增 FastAPI 路由

1. `src/mbforge/routers/` 新建 `APIRouter`。
2. 前缀 `/api/v1/{资源}`（少数模块自带完整路径时前缀为 `/api/v1`）。
3. 在 `app.py` 用 `include_router` 注册。
4. 边界用 Pydantic；错误用 `MBForgeError` 子类。
5. 阻塞 IO：`await loop.run_in_executor(...)` 或 `asyncio.to_thread`。
6. 前端配套：`frontend/src/api/http/{name}.ts`，服务端状态优先 React Query hooks。

### 新增 Agent 工具

1. 在 `agent/tools.py` 增加工具并加入 `get_all_tools()`。
2. 如需发现提示，更新 `agent/graph.py` system prompt。

### 新增 / 调整 Pipeline 阶段

1. 实现 `StageExecutor`（`pipeline/stages/`）。
2. 注册到 `pipeline/runner.py` 的 `STAGES` 列表。
3. 进度键同步 `STAGE_PCT`；通过既有 progress / events 通道上报。
4. 更新 `docs/architecture/pipeline-stages.md`。

### 新增前端组件

1. 页面级：`frontend/src/components/{feature}/`，PascalCase。
2. 跨目录 import 用 `@/`；HTTP 走 `api/http`，服务端状态走 `api/query`。
3. 错误：`AppError` / `ErrorCode`（`@/utils/errors`）。
4. 动画复用 `hooks/useAnimations`；样式优先 CSS 变量。

## 状态管理

| 层级 | 类型 | 模式 |
|---|---|---|
| 前端 | 局部 | `useState` |
| 前端 | 跨组件 UI | `context/AppContext.tsx` |
| 前端 | 服务端 | React Query（`api/query/`） |
| 前端 | 持久 UI 偏好 | `localStorage`，键前缀 `mbforge_` |
| 后端 | 进程内 | app lifespan / 单例 cache |
| 后端 | 持久 | SQLite + OpenKB + `storage/` |
| 后端 | 业务配置 | `~/MBForge/settings.json` |

## 配置优先级

业务配置：`~/MBForge/settings.json` > 代码默认值。

`MBFORGE_HOST`、`MBFORGE_LOG_LEVEL`、`MBFORGE_FORCE_CPU`、Docker/browser 开关以及
`HF_HOME` / `MODELSCOPE_CACHE` / `TORCH_HOME` / `HF_ENDPOINT` 是基础设施环境变量，
**不覆盖** `AppConfig` 业务字段。

## 存储布局（摘要）

```
{library_root}/                 # 默认 ~/MBForge
├── .mbforge/library.db
├── .mbforge/openkb/
├── storage/{doc_id}/…
└── notes/
```

全局 `settings.json` 与 `logs/` 固定在 `~/MBForge`（即使 `library_root` 被改到别处）。

## 迁移历史（只记里程碑）

- **2026-06-29**：Rust/Tauri → Python-only
- **2026-07-07**：OpenKB + PageIndex 替换旧向量栈
- **2026-07-08**：MolDetv2-FT 替换 Doc+General 双模型
- **2026-07-10**：`evidence` 表 + `ArtifactResolver`；Dear PyGui 移除
- **2026-07**：统一 `library.db` + `library_root` 术语（见 ADR 0001）
