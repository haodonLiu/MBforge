# MBForge 开发规范

> 适用于 TODO/ 下所有并行任务

---

## 一、代码规范

### Rust

- **命名**: snake_case 函数/变量，PascalCase 类型，SCREAMING_SNAKE_CASE 常量
- **错误处理**: 所有 public 函数返回 `Result<T, String>`，不使用 `unwrap()` 在非测试代码中
- **文档**: 每个 `pub` 函数/struct 必须有 `///` 文档注释
- **模块**: 每个 `.rs` 文件顶部有 `//!` 模块文档
- **测试**: 每个模块的 `#[cfg(test)] mod tests` 包含至少 2 个单元测试
- **日志**: 使用 `log::info!` / `log::warn!` / `log::error!`，不用 `println!`
- **异步**: async 函数使用 `tokio::runtime::Handle::current().block_on()` 桥接 sync→async
- **Mutex**: async 上下文使用 `tokio::sync::Mutex`，sync 上下文使用 `std::sync::Mutex`

### Python

- **类型注解**: 所有函数签名必须有 type hints
- **错误处理**: 使用自定义异常类，不使用 bare `except:`
- **文档**: 每个 public 函数有 docstring
- **格式化**: `uv run ruff format src/` + `uv run ruff check src/`

### TypeScript

- **类型**: 不使用 `any`，所有 API 响应定义 interface
- **错误处理**: 使用 `invokeWithError` 包装器
- **测试**: vitest 覆盖新增 API 函数

---

## 二、Git 规范

### Commit 格式

```
<type>(<scope>): <description>

[optional body]
```

Type: `feat` / `fix` / `refactor` / `docs` / `test` / `chore`

### Push 策略

攒约 3 个 commit 再 push，不要每次 commit 都推。

### 分支策略

- `main` — 稳定版本
- 并行任务各自在 `main` 上直接开发（当前阶段）
- 大型重构完成后一次性 commit

---

## 三、架构约束

### 存储层

- **SMILES 是唯一事实来源** — 所有化学计算使用纯净 SMILES，不使用 E-SMILES
- **E-SMILES 是可选插件** — `esmiles` 字段 nullable，语义标签存在 `tags` JSON
- **MoleCode 是运行时表示** — 不持久化，Agent 推理时临时生成

### 通信层

- **Rust ↔ Python**: HTTP REST (port 18792)，所有请求携带 `X-Trace-Id`
- **Rust ↔ Frontend**: Tauri IPC invoke + Events
- **跨边界调用**: 必须记录 token 消耗和延迟

### 依赖管理

- **Rust 依赖**: 所有 git 依赖必须锁定到特定 commit rev
- **Python 依赖**: `uv.lock` 锁定，集成测试覆盖
- **新依赖评估**: 引入前检查 crates.io 下载量、维护活跃度、许可兼容性

---

## 四、测试规范

### 单元测试

- 每个新模块至少 3 个测试（正常路径 + 错误路径 + 边界条件）
- 测试命名: `test_<功能>_<场景>` (如 `test_validate_smiles_invalid_input`)
- 测试数据使用 `tempfile::tempdir()`，不写入项目目录

### 集成测试

- 新增 Python sidecar 端点必须有对应的集成测试
- 测试覆盖: 正常响应 + 超时 + 畸形输入

### 回归测试

- `cargo test` 全部通过（~323 个）
- `uv run pytest tests/ -v` 全部通过（~111 个）
- `cd frontend && npm test` 全部通过（~73 个）

---

## 五、文档规范

### 代码内文档

- 每个 `pub struct` / `pub fn` 必须有 `///` 文档
- 复杂算法在实现前写设计注释（`// Design: ...`）
- 跨模块调用标注 `// 参考: ref/xxx.md — 理由`

### 外部文档

- 架构变更必须更新 `ARCHITECTURE.md`
- 新模块必须更新 `CODEMAP.md`
- 完成代码修改后在 `CODEMAP.md §7.6 待审核事项` 记录

---

## 六、并行任务协调

### 文件所有权

- 每个任务文件声明其修改范围
- 任务间不修改对方声明的文件（避免冲突）
- 共享文件（如 `mod.rs`）由最后完成的任务合并

### 接口契约

- 任务间通过 trait 或函数签名定义接口
- 接口变更必须通知依赖方任务
- 可以先定义 trait 再实现（接口先行）

### 完成标准

- [ ] 所有新增代码通过 `cargo check`
- [ ] 所有新增测试通过
- [ ] 不破坏现有测试（回归）
- [ ] 文档更新完成
- [ ] 任务文件中标记 ✅
