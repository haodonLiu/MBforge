# MBForge 项目全面审计报告

> 审计日期: 2026-06-04
> 审计方法: 三 Agent 并行审计（主审 + 架构分析 + 魔鬼代言人）

---

## 一、当前状态总览

| 指标 | 数值 |
|------|------|
| Rust 代码 | ~24,700 行（22 core + 21 parser + 13 command 模块） |
| Python 代码 | ~13,100 行（17 router + 模型管理 + 解析器） |
| 测试总数 | ~451 个（Rust 267 + Python 111 + Frontend 73） |
| 外部依赖 | Rust: chematic（git）, rusqlite, reqwest 等 |
| 数据库 | SQLite (molecules.db + vectors.db) + semantic_cache.json |
| 核心流程 | PDF → 解析 → LLM 提取 → 分子入库 → 知识库索引 |

---

## 二、三方观点对比

### 主审（Explore Agent）观点
- 代码库结构清晰，无循环依赖
- TODO 中有 1 项已过时（config 重复）
- `chem_validate.rs` 与 `core/chem.rs` 功能重叠
- vector_store.rs 已退化为 15 行类型定义

### 架构分析观点
- ETCLOVG 七层框架映射：E(强) T(强) C(中) L(中) O(弱) V(弱) G(弱)
- 可观测性和治理层是最大短板
- Rust/Python 分裂仍在缩小（chematic 替代 RDKit）
- 多个 std::sync::Mutex 在 async 上下文中使用有死锁风险

### 魔鬼代言人观点 ⚠️
- **chematic 风险大**：1 star，0 forks，单人维护，未发布 crates.io
- **Agent 架构不需要复杂化**：单 Agent ReAct 循环是正确架构
- **参考文献收集不行动**：Memvid 与化学无关，论文是综述非实现
- **TODO 列表虚胖**：P1/P2 多数是"nice to have"伪装
- **27 分钟管线瓶颈被忽视**：这是最大的用户体验问题

---

## 三、魔鬼代言人的关键论点（需要认真对待）

### 论点 1: chematic 是单点故障

> "你用一个 1 star 的仓库替代了有 20 年历史、数千贡献者的 RDKit。"

**评估**: 有道理。chematic 未发布 crates.io，API 可能随时变化。
**决策**: 保留 Python RDKit sidecar 作为权威路径，chematic 仅用于快速路径（指纹/Tanimoto 预筛）。

### 论点 2: 27 分钟管线是真正的问题

> "你在优化分子描述符 Rust 化和 WASM 预览，却忽略了最大的性能瓶颈。"

**评估**: 完全正确。管线瓶颈是 LLM 串行批处理（~32 次 HTTP 调用/文档）。
**决策**: 这应该是 P0，不是 TODO 里没有的。

### 论点 3: TODO 列表需要大幅削减

> "分子描述符 Rust 化、SAR 分析、BRICS 碎片化、3D 坐标 — 这些对药物发现用户不重要。"

**评估**: 大部分正确。用户要的是：① 可靠提取 ② 快速搜索 ③ 准确回答。高级化学功能是锦上添花。
**决策**: 重新优先级排序（见下方）。

---

## 四、重新排序后的优先级

### P0 — 立即做（影响用户体验）

| # | 任务 | 原因 | 工作量 |
|---|------|------|--------|
| 1 | **chematic API 编译验证** | git 依赖，API 可能不匹配 | 小 |
| 2 | **chem_validate.rs 接入 core/chem.rs** | 消除不必要的 Python sidecar 调用 | 中 |
| 3 | **清理过时 TODO 条目** | config 重复已解决 | 小 |
| 4 | **管线并行化评估** | 27 分钟瓶颈，LLM 串行调用是根因 | 大 |

### P1 — 本月做（提升可靠性）

| # | 任务 | 原因 | 工作量 |
|---|------|------|--------|
| 5 | **分子指纹持久化** | 子结构搜索需要预计算指纹 | 中 |
| 6 | **JSON 修复换 llm_json crate** | 提升 LLM 输出解析鲁棒性 | 小 |
| 7 | **Mutex → tokio::sync::Mutex 迁移** | 防止 async 上下文死锁 | 中 |
| 8 | **提取准确率基准测试** | 没有量化指标就无法改进 | 大 |

### P2 — 本季度做（架构改进）

| # | 任务 | 原因 | 工作量 |
|---|------|------|--------|
| 9 | **分子描述符 Rust 化** | 减少 Python sidecar 调用 | 中 |
| 10 | **SAR/MCS Rust 化** | 减少 Python sidecar 调用 | 中 |
| 11 | **Python sidecar 健壮性** | 自动重启 + 连接池 + 优雅降级 | 中 |

### P3 — 暂缓（当前不需要）

| # | 任务 | 暂缓原因 |
|---|------|---------|
| 12 | MOL/SDF 文件格式 | 药物发现用户主要用 PDF |
| 13 | 反应 SMILES | 合成化学规划，非文献提取 |
| 14 | 3D 坐标生成 | 计算化学，不同产品方向 |
| 15 | PDB/XYZ 格式 | 结构生物学，超出范围 |
| 16 | 2D SVG 渲染 | 用户可在 PDF 中看结构 |
| 17 | WASM 分子预览 | 演示价值 > 实用价值 |
| 18 | SMARTS 编辑器 | 专家级功能，目标用户不用 |
| 19 | 多 Agent 编排 | 当前单 Agent 足够 |
| 20 | 情景记忆 | 学术概念，无用户需求 |
| 21 | 自适应上下文预算 | 过度工程 |

---

## 五、架构问题清单

### 已确认的问题

| # | 问题 | 严重性 | 状态 |
|---|------|--------|------|
| 1 | chem_validate.rs 与 core/chem.rs 功能重叠 | 中 | 待合并 |
| 2 | vector_store.rs 退化为 15 行类型定义 | 低 | 待清理 |
| 3 | 多个 std::sync::Mutex 在 async 上下文中 | 高 | 待迁移 |
| 4 | TODO 第三节有 2 条过时条目 | 低 | 待清理 |
| 5 | （已删除 LanceDB — 改用 SQLite FTS5 + semantic_cache） | — | — |

### 需要讨论的架构决策

| # | 决策 | 选项 A | 选项 B | 魔鬼代言人建议 |
|---|------|--------|--------|---------------|
| 1 | 知识库存储 | SQLite FTS5 + semantic_cache | — | — |
| 2 | 化学后端 | 纯 chematic | chematic 快速路径 + RDKit 权威 | 双路径（降低风险） |
| 3 | Agent 复杂度 | 保持单 Agent | 引入多 Agent | 保持单 Agent（够用） |
| 4 | SQLite 统一 | 保持分离 | 合并为单一 DB | 保持分离（简单清晰） |

---

## 六、参考文献行动计划

| 参考 | 行动 | 理由 |
|------|------|------|
| Memvid | **归档到 ref/archive/** | 通用记忆引擎，与化学无关 |
| Harness Engineering 综述 | **保留但不行动** | 框架参考，无直接实现价值 |
| Harness Systems 论文 | **保留但不行动** | 理论指导，当前单 Agent 足够 |
| Chematic | **保留，已集成** | 核心化学依赖，需验证 API |
| Wiki 应用笔记 | **已采纳** | 文件缓存、语义分块等已实现 |

---

## 七、隐藏风险清单

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| chematic 仓库删除/停止维护 | 中 | 高 | 保留 RDKit sidecar 作为后备 |
| Python sidecar 崩溃 | 中 | 高 | 添加自动重启 + 健康检查 |
| Tauri v3 破坏性变更 | 确定 | 中 | 不急于升级，等稳定后迁移 |
| Python 依赖腐烂 | 中 | 中 | uv.lock 锁定，集成测试覆盖 |
| 27 分钟管线瓶颈 | 已知 | 高 | **P0: 并行化 LLM 调用** |

---

## 八、最终建议

### 一句话总结
**停止扩展功能，聚焦提取质量和管线性能。**

### 具体行动

1. **本周**: 验证 chematic API + 清理过时 TODO + 合并 chem_validate 到 chem.rs
2. **本月**: 管线并行化（27 分钟 → 5 分钟）+ 提取准确率基准 + MinerU-Popo 图文关联集成
3. **本季度**: 分子描述符 Rust 化 + SAR Rust 化 + sidecar 健壮性 + MoleCode OCSR fallback + 标题层次 Popo 替换
4. **暂缓**: 所有 P3 功能（格式扩展、可视化、高级 Agent 特性）

### 新增参考: MoleCode 显式图表示

MoleCode 论文提供了关键的表示理论洞察：
- **双轨制**: 存储用 E-SMILES（紧凑），推理/编辑用 MoleCode（显式图）
- **OCSR fallback**: MolScribe 失败时 → VLM + MoleCode prompt → 显式图 → SMILES
- **Markush 创新**: 显式 R-group 节点，准确率 38% → 84%
- **跨文档分子追踪**: 利用持久原子 ID 建立分子精确对应
- **分子版本控制**: MoleCode 的 git diff 有意义（局部图操作 vs SMILES 整行变化）

### 新增参考: MinerU-Popo 文档后处理

MinerU-Popo 是 MBForge 文档解析层缺失的关键一块：
- **图文关联**: 填补 association.rs 的致命空白（分子图像 ↔ 化合物编号 ↔ 活性数据精确绑定）
- **标题层次**: TEDS 53.7→90.6，替代 sections.rs 的启发式规则
- **表格修复**: 跨页 SAR 表格不再碎片化
- **集成成本**: Python sidecar 新增路由 + 格式转换器，可选增强层默认关闭

### 不做的事

- ❌ 不引入多 Agent 编排
- ❌ 不添加情景记忆/自适应上下文
- ❌ 不支持 MOL/SDF/PDB/XYZ 格式
- ❌ 不做 WASM 分子预览
- ❌ 不移除 Python RDKit sidecar（保留为权威路径）
