# 提交记录快照（2026-06-04 已归档）

> 本文件是 2026-06-06 任务管理集中化时记录的 git log 快照。
> 不要手动维护——季度回顾时用 `git log --oneline` 刷新。

---

```
3a08f39 test(python): 新增 Agent + 管线集成测试 (22 个)
b009005 refactor(python): 错误处理统一 — 异常层级 + 全局处理器
d64adf8 refactor(python): 补全 type hints — 27 个文件
7846039 refactor: molecule_db.rs 删除重复的 molecules schema
a4f3801 refactor: 合并 9 项代码重复
5078b9d refactor: 路径解析统一到 Rust 侧，Python 只读不解析
989de48 fix: 统一 Python/Rust 模型路径解析
b0f878d fix: 修正 embedding 配置 + FutureWarning
7e690f4 docs: 更新 CODEMAP 断链状态 — 修正误报
986a734 feat: 接入 semantic_cache + stream_search，移除 Python 双写
d5d6f63 docs: 新增 CODEMAP.md 代码逻辑树
0e63bba fix(agent): 修复 ReAct 循环 6 项问题
3629aa4 fix: 代码审查修复 — 14 项问题 (Rust/Python/TypeScript)
cf907f1 feat(python): 统一资源管理 + 精简下载 + CLI 环境管理
2edc1f6 feat: Rust 侧统一资源管理器 + 前端环境 tab
705a8aa fix(rust): 全代码审查修复 — UTF-8 panic / 路径穿越 / FTS5 损坏 / chat_stream 多步丢失
```
