# 代码风格规范

> 版本: 0.1.0 | 日期: 2026-06-04
> 高层原则。具体实现细节（缩进、引号、命名规则）见 AGENTS.md §代码风格规范。

## 总则

1. **显式优于隐式**：类型、错误、返回值必须明确。禁止隐式转换和全局魔术状态。
2. **DRY**：重复超过两次的逻辑必须抽取为函数/宏/工具类。
3. **KISS**：优先使用标准库和已引入依赖的内置能力。
4. **最小变更**：修复或添加功能时，改动范围尽可能小。
5. **常量同步**：Rust 与 Python 的同名常量必须保持值一致。

## 错误处理原则

| 场景 | 要求 |
|---|---|
| 函数签名 | 返回 `Result<T, String>` 或自定义 Error，禁止裸 `unwrap`/`expect`（测试除外） |
| 错误信息 | 必须包含上下文，如 `"Project migration failed: {e}"` |
| 用户可见错误 | Tauri 命令返回 `Result<T, String>`，String 为可读信息 |
| 日志 | 错误必须记录 `log::error!` / `logger.error`，禁止 `print` |

## 模块边界原则

| 规则 | 说明 |
|---|---|
| 一个文件一个主要职责 | 超过 300 行的组件/模块必须拆分 |
| 禁止跨层直接调用 | `commands/` → `core/` → `parsers/` 单向依赖 |
| 状态管理 | Tauri 状态使用 `Arc<RwLock<T>>`；写操作用 `.write().await` |
| 路径安全 | 必须使用 `assert_within_root()` 或 `safe_join()`，禁止裸 `Path::join()` |

## 命名一致性（跨语言）

| 概念 | Rust | Python | TypeScript |
|------|------|--------|------------|
| 文件/模块 | `snake_case.rs` | `snake_case.py` | `PascalCase.tsx` / `camelCase.ts` |
| 类型/类 | `PascalCase` | `PascalCase` | `PascalCase` |
| 函数/方法 | `snake_case` | `snake_case` | `camelCase` |
| 变量/属性 | `snake_case` | `snake_case` | `camelCase` |
| 常量 | `SCREAMING_SNAKE_CASE` | `SCREAMING_SNAKE_CASE` | `SCREAMING_SNAKE_CASE` |

## 文档注释要求

- 所有 `pub` Rust 函数/结构体必须有 `///` 文档注释。
- 所有公共 Python 函数/类必须有 Google-style docstring。
- 所有导出 TypeScript 类型/函数必须有 JSDoc。
- 跨语言边界的数据结构（Tauri IPC 传参）必须注释字段含义。

## 导入排序（通用）

所有语言遵循**三组分离**，组内按字母顺序：

1. 标准库
2. 第三方依赖
3. 项目内部

组间以空行分隔。
