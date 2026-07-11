# MBForge 版本控制与发布规范

> 版本：1.0 | 生效日期：2026-07-11

## 1. 分支模型

采用以 `main` 为中心的短分支开发模型。`main` 必须始终可构建、可测试，并代表下一次
可发布状态。除仓库管理员处理紧急恢复外，所有变更均通过 PR 合并，禁止直接推送和
强制推送 `main`。

分支格式为 `<type>/<issue-id>-<short-description>`：

```text
feat/123-activity-filter
fix/248-library-transaction
docs/301-contribution-rules
release/0.4.0
hotfix/0.3.1-startup-crash
```

允许类型：`feat`、`fix`、`refactor`、`perf`、`test`、`docs`、`chore`、`release`、
`hotfix`。描述使用小写 kebab-case。无 Issue 的小型维护任务可省略 ID，但 P0/P1、功能、
迁移和发布任务不得省略。普通分支应在数日内合并；超过 7 天需同步 `main` 并复核范围。

## 2. 提交规则

提交信息采用 Conventional Commits：

```text
<type>(<scope>): <subject>

<why and what changed>

Refs: #123
```

常用类型为 `feat`、`fix`、`refactor`、`perf`、`test`、`docs`、`build`、`ci`、
`chore`、`revert`；scope 使用稳定模块名，如 `frontend`、`api`、`pipeline`、`core`、
`agent`、`ocr`、`docs`、`deps`。subject 使用祈使语气、不加句号、建议不超过 72 字符。

破坏性变更使用 `!` 并在 footer 写 `BREAKING CHANGE:`、迁移路径和兼容窗口。提交必须
可构建、只表达一个逻辑意图；不要按文件拆提交，也不要混入无关格式化。开发中可使用
`fixup!`，合并前整理历史。

## 3. PR 与合并

- 一个 PR 对应一个逻辑主题和一个主要工作项。
- 默认使用 **Squash merge**，最终提交沿用合规的 PR 标题。
- PR 必须与最新 `main` 无冲突；优先 rebase，禁止对共享分支无通知改写历史。
- 至少一名非作者批准，所有要求检查通过后方可合并。
- 未配置为 CI 的必需检查由作者本地执行并在 PR 记录结果，直至 CI 覆盖。
- 合并后删除远端和本地功能分支；禁止长期保留已合并 worktree。

不得合并已知会损坏数据、泄露秘密或让 `main` 无法启动的变更。紧急修复可缩短审查，
但不能省略回归测试、变更记录和事后复盘。

## 4. 版本号

使用 Semantic Versioning：`MAJOR.MINOR.PATCH`，Git 标签为 `vMAJOR.MINOR.PATCH`。
在 `1.0.0` 前：

- `MINOR`：新增能力或发生需要迁移的破坏性变更；破坏性变更必须明确标注。
- `PATCH`：向后兼容的缺陷、安全、性能和文档修复。
- 预发布版本：`0.4.0-alpha.1`、`0.4.0-beta.1`、`0.4.0-rc.1`。

从 `1.0.0` 起严格遵循 SemVer：破坏性变更升 MAJOR，兼容功能升 MINOR，兼容修复升
PATCH。版本号不得用日期、分支名或构建次数替代。

`pyproject.toml` 的 `[project].version` 是发布版本的单一来源。发布 PR 必须同步所有
消费者，包括 `frontend/package.json`、`src/mbforge/utils/paths.py`、FastAPI/health
元数据及锁文件；新增代码不得再写死版本号。CI 应增加版本一致性检查。

## 5. 变更日志

`CHANGELOG.md` 采用 Keep a Changelog 结构。日常 PR 将用户可见变化写入
`Unreleased`，按 `Added`、`Changed`、`Deprecated`、`Removed`、`Fixed`、`Security`
分类；纯内部重构可省略。发布时把 `Unreleased` 内容移动到带日期的版本段并创建新的
空 `Unreleased`。

日志说明用户影响，不复制提交列表。破坏性变更必须给出迁移步骤；安全项在修复公开前
避免披露可利用细节。

## 6. 发布流程

1. 从 `main` 创建 `release/X.Y.Z`，冻结无关功能。
2. 确定版本增量，更新全部版本消费者、`CHANGELOG.md` 和必要迁移文档。
3. 执行完整 Python 测试、lint/format、前端 lint/typecheck/test/build，以及适用的迁移
   和关键流程验收。
4. 合并发布 PR，确认 `main` 的 CI 通过。
5. 在发布提交创建 annotated tag：`git tag -a vX.Y.Z -m "MBForge X.Y.Z"`；能够签名
   时使用 `git tag -s`。
6. 推送标签并创建 GitHub Release，正文来自对应 changelog，附安装、迁移、已知问题
   和回滚说明。
7. 发布后执行健康检查；失败时优先修复前滚。仅在工件和数据完全兼容时回滚发布。

标签一经发布不得移动或复用；发现问题应发布新 PATCH。制品必须可追溯到标签提交。

## 7. Hotfix 与回退

生产阻断问题从受影响的最新标签创建 `hotfix/X.Y.Z-...`。修复保持最小化，补回归测试，
同时合并回 `main`，并发布新的 PATCH。回退代码使用 `git revert` 产生可审计提交；禁止
删除公共历史或强推已共享分支。涉及数据库迁移时，按迁移文档决定前滚或恢复备份，
不得仅回退应用代码。
