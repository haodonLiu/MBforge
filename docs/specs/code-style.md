# 代码风格规范

> 版本: 0.2.0 | 日期: 2026-07-14  
> 高层原则。命令与仓库级约定见 [AGENTS.md](../../AGENTS.md)、[CLAUDE.md](../../CLAUDE.md)。  
> 工具配置以 `pyproject.toml`（ruff）与 `frontend/` ESLint/TSConfig 为准。

## 总则

1. **显式优于隐式**：类型、错误、返回值必须明确。禁止隐式全局魔术状态。
2. **DRY**：重复超过两次的逻辑抽取为函数/模块。
3. **KISS**：优先标准库与已引入依赖。
4. **最小变更**：只改验收所需范围，不顺手重构无关代码。
5. **常量**：跨模块常量放 `src/mbforge/utils/`（如 `paths.py` / `config` 默认值）；
   业务可调项走 `AppConfig` + `settings.json`，不要再引入已删除的 `configs/` 运行时目录。

## 错误处理

| 场景 | 要求 |
|---|---|
| API / 业务错误 | `MBForgeError` 子类（`status_code` + `error_code`），由 `app.py` 统一序列化 |
| 响应体 | `{success: false, error, error_code, severity, category, …}` |
| 错误信息 | 带上下文，禁止空消息与静默吞异常 |
| 日志 | `logger = get_logger(__name__)`；禁止 `print` 与 bare `except` |

前端：`httpFetch` 提取后端 `error_code`；UI 用 `AppError` / `ErrorBoundary`。

## 模块边界

| 规则 | 说明 |
|---|---|
| 单文件主职责 | 过大组件/模块应拆分 |
| 单向依赖 | `routers/` → `core/` + `pipeline/` + `agent/` + `backends/` |
| 路径安全 | `LibraryLayout` / `ArtifactResolver` / 既有 path helpers；禁止未校验的 `Path /` 拼到用户输入 |
| 配置写入 | 只经 `update_settings` / `save_global_config`，路由层不直接写盘 |

## 命名一致性（跨语言）

| 概念 | Python | TypeScript |
|---|---|---|
| 库根目录 | `library_root` | `libraryRoot` |
| 文件/模块 | `snake_case.py` | `PascalCase.tsx` / `camelCase.ts` |
| 类型/类 | `PascalCase` | `PascalCase` |
| 函数/方法 | `snake_case` | `camelCase` |
| 布尔 | `is_` / `has_` / `can_` | 同语义 camelCase |
| 常量 | `SCREAMING_SNAKE_CASE` | `SCREAMING_SNAKE_CASE` |

## 文档注释

- 公共 Python 函数/类：Google-style docstring。
- 导出的 TypeScript 类型/函数：必要时 JSDoc。
- 跨语言契约（Pydantic ↔ TS）字段语义要可对上，改名时同步前后端与文档。

## 导入排序

三组、组间空行：标准库 → 第三方 → 项目内部。Python 由 ruff `I` 强制；TS 跨目录用 `@/`。

## 格式化

- Python：ruff format，行宽 88，target py312。
- TS：项目 ESLint + `tsc --noEmit`；`strict` 打开。
