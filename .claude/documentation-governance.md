# MBForge 文档治理规范

> 本文档规定项目描述文件的分工、维护责任与回刷机制。
> 所有 AI 编码助手在执行重构、模块迁移、目录调整后，必须按本规范回刷描述文件。

---

## 一、描述文件工作范畴（严格区分）

### 1. README.md — 人类入口

**受众**：首次访问仓库的人类开发者、用户、招聘者。

**职责范围**：
- 项目一句话定位与核心特性列表
- 架构鸟瞰图（不展开内部模块细节）
- 快速开始（一键启动 / 手动启动）
- 项目结构树（一级目录 + 关键子目录，不罗列每个文件）
- 技术栈表格（技术名称，**禁止行数/文件数/测试数**）
- 文档索引（链接到 AGENTS.md / CLAUDE.md / docs/）

**禁止写入**：
- 代码风格规范（引号、缩进、import 排序）
- 详细的 Tauri 命令注册步骤
- Agent 工具添加模板
- 模块边界与架构约定
- 精确数量（"18 个命令"、"~70 个组件"）

---

### 2. AGENTS.md — AI 编码助手操作手册

**受众**：所有 AI 编码助手（Kimi / Claude / Copilot 等）。

**职责范围**：
- 项目概览与技术栈版本
- **代码风格规范**（Rust / Python / TypeScript 三端）
- **模块边界与架构约定**（五层架构、目录组织规则）
- **新增代码的约定**（如何加命令、加工具、加路由、加组件）
- **命名约定**（跨语言一致性、特殊前缀规则）
- **错误处理模式**（三端分别怎么做）
- **配置系统**（两级配置 + 环境变量）
- **Git 提交规范**（type/scope/subject 格式）
- **测试规范**（命名、组织、Mock 策略）
- **迁移期规则**（Python → Rust 冻结期铁律）
- **设计原则**（Harness > Model、Rust 优先等）
- **技术债务与风险清单**（需定期审计）

**禁止写入**：
- 详细的架构图 ASCII 艺术（维护成本高，放 CLAUDE.md）
- 具体的数据流步骤（放 CLAUDE.md）
- 一键启动脚本（放 README.md）

---

### 3. CLAUDE.md — Claude 上下文补充

**受众**：Claude 助手实例（当前对话上下文）。

**职责范围**：
- **架构图**（ASCII 系统架构 + 数据流）
- **核心数据流**（PDF → Pipeline → KB 的完整链路）
- **操作模板**（添加 Rust Agent 工具、添加 API 端点、添加 PDF 解析后端）
- **常见调试策略**（"遇到报错时停下来描述..."）
- **Build / Test / Lint 命令速查**（精确命令，不解释为什么）
- **内置文档索引**（快速跳转）

**禁止写入**：
- 代码风格细节（放 AGENTS.md）
- 命名约定表格（放 AGENTS.md）
- 错误处理模式详解（放 AGENTS.md）
- Git 提交规范（放 AGENTS.md）
- 项目营销式特性列表（放 README.md）

---

## 二、文档回刷机制（强制）

### 触发条件

以下操作**完成后必须立即回刷**对应描述文件：

| 操作类型 | 必须回刷的文件 | 检查要点 |
|----------|---------------|---------|
| 新增 / 删除 / 重命名 Rust Tauri 命令 | AGENTS.md + CLAUDE.md | commands/ 模块列表、handler() 注册说明 |
| 新增 / 删除 / 重命名 Rust Agent 工具 | AGENTS.md + CLAUDE.md | executor_rig.rs / rig_adapter.rs 模板 |
| 调整 `core/` 子目录结构 | AGENTS.md + CLAUDE.md + README.md | 五层架构表、项目结构树 |
| 调整 `parsers/` 子目录结构 | AGENTS.md + CLAUDE.md + README.md | 解析管线数据流、项目结构树 |
| 新增 / 删除 PDF 解析后端 | CLAUDE.md + AGENTS.md | pipeline.rs 分支、客户端列表 |
| Python 侧模块增减（backends/ 等） | AGENTS.md + README.md | 模型服务层描述、启动命令 |
| 前端 `api/tauri/` 新增模块 | AGENTS.md + README.md | Tauri invoke 子模块列表 |
| 前端 components/ 重大结构调整 | README.md + AGENTS.md | 组件分组描述 |
| 修改启动命令、端口、构建流程 | CLAUDE.md + README.md | 命令速查、快速开始 |
| 技术债务修复或新增 | AGENTS.md | 债务清单状态更新 |
| 修改 `.env` 模板或配置系统 | AGENTS.md | 环境变量列表、配置优先级 |

### 回刷检查清单（Checklist）

执行重构后，在提交前按此清单检查：

```markdown
- [ ] **结构一致性**：codegraph / tree 输出与 AGENTS.md 项目结构树匹配
- [ ] **命令准确性**：CLAUDE.md 中的 Build/Test/Lint 命令在本地可执行
- [ ] **启动命令**：README.md / CLAUDE.md / AGENTS.md 中的启动命令指向正确的入口文件
- [ ] **模块存在性**：README.md 项目结构树中列出的每个文件/目录真实存在
- [ ] **无空壳目录**：README.md 不再列出已空置的目录（如 model_server/routers/）
- [ ] **无精确数量**：三份文档中均无 "~X 行"、"Y 个"、"Z 个命令" 等会快速过时的量化描述
- [ ] **技术债务**：若本次修复了债务清单中的某条，在 AGENTS.md 中标记为 `[已修复]` 或移除
- [ ] **迁移期规则**：若本次修改了 Python 侧，确认是否符合 "Python 代码冻结" 原则
```

### 自动化辅助检查

使用 codegraph 快速验证文档是否过时：

```bash
# 1. 生成当前实际的文件树
codegraph_files --format tree --path src-tauri/src > /tmp/actual-rust.tree

# 2. 与 AGENTS.md 中的项目结构树对比
# 手动检查：AGENTS.md 列出的模块是否在 actual-rust.tree 中存在

# 3. 检查空壳目录
find src/mbforge -type d -empty 2>/dev/null
# 若输出非空，检查 README.md / AGENTS.md 是否仍引用这些目录
```

### 责任归属

- **人类开发者**：在 PR 描述中勾选 "文档已同步更新"， reviewer 必须检查
- **AI 助手**：在执行重构类任务的最后一步，**必须**执行回刷检查清单；若发现文档与代码不一致，在结束对话前完成更新
- **例外**：纯 bugfix（单行修改、变量名修正、类型补全）不影响文档时，可跳过回刷

---

## 三、快速决策表

> "我应该更新哪个文件？"

| 你要写什么内容 | 目标文件 |
|---------------|---------|
| 项目做什么、有什么特性、怎么安装 | README.md |
| 代码该怎么写、怎么命名、怎么加模块 | AGENTS.md |
| 系统怎么流转、怎么加工具/端点、命令速查 | CLAUDE.md |
| 技术选型理由、依赖版本说明 | docs/TECH_STACK.md |
| 分子表示规范（E-SMILES / MoleCode） | docs/specs/ |

---

## 四、反模式（禁止）

1. **三份文档互相复制粘贴**：发现重复内容时，只保留在正确的文件中，其他文件用链接引用
2. **"大概差不多"**：结构树中多一个或少一个模块都会误导后续开发者，必须精确
3. **只改代码不改文档**：提交前检查清单未勾选即视为未完成
4. **在 README.md 中写编码规范**：人类用户不关心 import 排序规则
5. **在 AGENTS.md 中写启动脚本**：AI 助手不需要知道 `start-dev.bat` 的内容
