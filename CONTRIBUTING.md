# MBForge 贡献指南

感谢参与 MBForge。本文件是开发流程的入口；架构和代码细则分别以
[`AGENTS.md`](AGENTS.md) 与 [`docs/specs/`](docs/specs/README.md) 为准，任务治理和
版本发布分别以 [`docs/PROJECT_MANAGEMENT.md`](docs/PROJECT_MANAGEMENT.md) 与
[`docs/VERSION_CONTROL.md`](docs/VERSION_CONTROL.md) 为准。

## 1. 开始之前

1. 在 `TODO/INDEX.md` 或 GitHub Issue 中确认任务，避免重复工作。
2. P0/P1、跨模块改造、数据库迁移和公开 API 变更必须先有 Issue 或设计文档。
3. 一个分支和一个 PR 只处理一个逻辑主题；发现无关问题时另建任务。
4. 不提交论文、模型权重、真实项目库、API Key、日志或其他敏感数据。

## 2. 开发环境

要求 Python 3.12、`uv`、Node.js 20.19+ 和 `npm`。GPU 仅在运行
MolDet/MolScribe 等模型时需要。

```bash
uv sync --dev
npm --prefix frontend install
```

本地启动：

```bash
uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792
cd frontend && npm run dev
```

复制 `.env.template` 配置本地环境；`.env` 和运行数据不得提交。

## 3. 标准开发流程

1. 从最新 `main` 创建短生命周期分支，命名见版本控制规范。
2. 先明确验收条件；修复缺陷时优先补充可复现失败的测试。
3. 采用最小、完整的改动，遵守 `ArtifactResolver`、配置入口、HTTP 边界等仓库约束。
4. 按影响范围增加或更新测试和文档。
5. 执行适用的质量检查并在 PR 中记录结果。
6. 发起 PR，关联任务，说明风险、迁移、验证和回滚方式。
7. 处理审查意见；合并后删除分支，更新任务状态。

不要在功能 PR 中顺带格式化无关文件、升级无关依赖或修复无关问题。

## 4. 代码与测试要求

代码必须遵守 [`docs/specs/code-style.md`](docs/specs/code-style.md) 和
[`docs/specs/architecture-conventions.md`](docs/specs/architecture-conventions.md)。
下列检查按改动范围执行：

```bash
# Python
uv run ruff check src/ tests/
uv run ruff format src/ tests/ --check
uv run pytest tests/ -q

# Frontend
cd frontend
npm run lint
npx tsc --noEmit
npm run test
npm run build
```

最低测试策略：

| 改动 | 必需验证 |
|---|---|
| Python 业务逻辑 | 相关单元测试；共享核心路径补回归测试 |
| 路由或跨层契约 | 后端路由测试；同步 TS 类型/HTTP 封装 |
| 数据库或文件布局 | 临时目录中的真实 SQLite 测试；迁移与回滚说明 |
| React 交互 | Vitest/Testing Library；类型检查和构建 |
| Pipeline、OCR、模型 | 无模型单测加至少一个可复现的集成/夹具验证 |
| 仅文档 | 链接、命令、术语和当前实现人工核对 |

禁止通过删除断言、扩大异常捕获或永久跳过测试来“修复”失败。确因环境无法执行的
检查，必须在 PR 中写明原因、替代证据和剩余风险。

## 5. Pull Request 要求

PR 应保持可独立审查和回滚，并满足：

- 标题符合 Conventional Commits：`<type>(<scope>): <subject>`。
- 描述包含背景、改动、验证、风险、迁移和回滚。
- 关联 Issue 或 `TODO/INDEX.md` 项；用户可见变更更新 `CHANGELOG.md`。
- API、配置、存储或行为变化同步更新对应文档。
- 新代码没有无关格式化、生成物、秘密、模型或本地数据。
- 所有适用检查通过，至少一名非作者审查者批准后合并。

作者不能批准自己的 PR。审查按正确性、数据安全、兼容性、测试充分性、可维护性和
文档准确性排序；风格问题尽量交给自动化工具。

## 6. 完成定义

任务只有在以下条件全部满足时才算完成：验收条件达成；测试和质量门禁通过；文档、
变更日志与迁移说明已同步；审查意见已解决；已合并到 `main`；任务板或 Issue 已更新；
不存在未记录的后续工作。

安全漏洞请勿公开提交包含利用细节或真实数据的 Issue，应通过维护者的私密渠道报告。
