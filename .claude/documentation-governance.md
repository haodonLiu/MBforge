# MBForge 文档治理规范

> 规定描述文件的分工、维护责任与回刷机制。  
> 栈已是 **Python FastAPI + React**（无 Rust/Tauri）。  
> 总索引：[docs/README.md](../docs/README.md)。

---

## 一、描述文件分工

### 1. README.md — 人类入口

**受众**：用户、贡献者、招聘者。

**写**：定位、特性、架构鸟瞰、快速开始、技术栈、文档链接、许可。

**不写**：编码细则、Agent 工具模板、易过时的精确数量（「N 个 router」）、内部模块清单。

### 2. AGENTS.md — AI 短规则

**受众**：所有 AI 编码助手。

**写**：目录约定、命令、风格要点、测试/PR 要求、安全与配置（`library_root`、
`LibraryLayout`、`ArtifactResolver`）。

**不写**：大段 ASCII 架构图、营销特性列表（放 README）、过时栈（Rust/Tauri）规则。

### 3. CLAUDE.md — AI 架构速查

**受众**：Claude Code 等长上下文助手。

**写**：大数据流、7-stage 管线、存储布局、常用命令、指向 AGENTS/specs 的链接。

**不写**：与 AGENTS 重复的命名表长文；以链接代替复制。

### 4. docs/ — 深度文档

| 子树 | 职责 |
|---|---|
| `docs/specs/` | 架构原则、代码风格、分子表示 |
| `docs/architecture/` | 管线、错误日志等实现向参考 |
| `docs/adr/` | 决策记录（不改写历史正文；用 Status/Last note 标注现状） |
| `docs/analysis/`, `docs/reviews/`, `docs/superpowers/` | **历史快照** — 默认只读 |
| `TODO/INDEX.md` | 唯一优先级任务板 |

### 5. CONTRIBUTING / PROJECT_MANAGEMENT / VERSION_CONTROL

流程与治理；不承载瞬时架构数字。

---

## 二、回刷触发（强制）

完成后**立即**回刷相关活文档：

| 操作 | 回刷 |
|---|---|
| 增删改 FastAPI 路由 / 挂载方式 | CLAUDE.md 路由摘要；必要时 README 架构句 |
| 改 pipeline 阶段或 `STAGES` | `docs/architecture/pipeline-stages.md` + CLAUDE 数据流 |
| 改存储布局 / DB 路径 / ArtifactResolver | ADR 状态说明、architecture-conventions、CLAUDE 存储节 |
| 改启动命令、端口、包管理器 | README + CLAUDE + AGENTS 命令节 |
| 改配置入口或 `library_root` 语义 | AGENTS 安全节 + architecture-conventions + settings 相关测试说明 |
| 修 TODO 项完成 | `TODO/INDEX.md` 状态；完成记录可另文件但 INDEX 为真源 |
| 仅单行 bugfix | 可跳过，除非改了用户可见行为或公共契约 |

### 回刷检查清单

```markdown
- [ ] 启动命令可复制执行（uvicorn / python -m mbforge / npm run dev）
- [ ] 无已删除路径（start.py、configs/、src-tauri/、api/tauri/、knowledge_base.db 作为当前唯一库）
- [ ] 管线描述为 7 logical stages，不写已废弃的 6/9 顶层阶段数
- [ ] 字段名 library_root / libraryRoot
- [ ] 未在活文档写死易变精确计数（router 数、测试数）除非脚注「约」且可接受漂移
- [ ] 历史 analysis/reviews 未当现行 API 引用
- [ ] 代码与文档冲突时已改文档，或显式记入 TODO
```

### 自动化辅助

```bash
# 空目录 / 幽灵引用
find src/mbforge -type d -empty 2>/dev/null

# 活文档是否仍提已删路径
rg -n "src-tauri|start\\.py|knowledge_base\\.db|configs/|api/tauri|6-stage|9-stage" \
  README.md AGENTS.md CLAUDE.md docs/specs docs/architecture/pipeline-stages.md \
  docs/architecture/error-logging.md docs/README.md
```

---

## 三、快速决策表

| 内容 | 文件 |
|---|---|
| 项目是什么、怎么装 | README.md |
| AI 编码铁律 | AGENTS.md |
| 系统怎么流转、命令速查 | CLAUDE.md |
| 分层 / 新增模块约束 | docs/specs/architecture-conventions.md |
| 管线阶段 | docs/architecture/pipeline-stages.md |
| 分子表示 | docs/specs/molecular-representation.md 等 |
| 长期决策 | docs/adr/ |
| 优先级任务 | TODO/INDEX.md |

---

## 四、反模式

1. **三份活文档互相粘贴大段** — 一处正文，其余链接。
2. **把 analysis/reviews 当现行规范** — 必须先对代码。
3. **只改代码不改活文档** — PR 视为未完成。
4. **在 README 写 import 排序** — 属 AGENTS / code-style。
5. **复活 project_root / 双 DB 描述为「当前」** — 仅允许出现在 ADR 历史上下文或迁移说明。
6. **硬编码「N 个 router / N% 覆盖率」** 且不维护 — 改写定性描述或链到可测命令。

---

## 五、责任

- **人类**：PR 勾选文档同步；reviewer 抽查活文档。
- **AI**：重构/迁移类任务结束前跑回刷清单；发现漂移就修。
- **ADR**：不删除历史段落；用 Status / Last note 声明「已落地 / 仍开放」。
