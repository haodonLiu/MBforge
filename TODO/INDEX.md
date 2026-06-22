# MBForge 任务看板

## P0 — 正在进行 / 阻塞

- [ ] **抽取质量基线（P0-1: gold set + F1 harness）**
      来源：`TODO/2026-06-22-llm-extraction-paper-research.md`（Chem. Soc. Rev. 2025, 54, 1125）
      规范：`docs/specs/llm-chemical-extraction-reference.md` §6。
      **必须先做**：不建立评估基线则后续所有改动盲改。
      验收：(a) ≥50 gold PDF + 标注 JSON（**其中 ≥10 篇专利**含 claim/example/R-group 标注）；
      (b) Rust 端 precision/recall/F1；(c) Hungarian assignment；(d) Levenshtein fuzzy；
      (e) `cargo run --bin eval` 跑通给 baseline 数字；**(f) 专利子指标：claim-example mapping F1**。
      工作量：2-3 周。

- [ ] **P0-2 — temperature=0 强制（抽取路径）**
      论文 §3.1, §3.3.1。`llm_gateway.rs:178` 当前 0.7 → 改为 0.0。
      工作量：半天。

- [ ] **P0-3 — constrained decoding 接 E-SMILES（含 Markush）**
      论文 §3.3.1。选 `outlines` 或自实现 grammar；Python 侧 LLM 接 **E-SMILES + Markush 标签** 文法；
      **专利 R-group 抽取保留率 ≥95%**。
      工作量：1-2 周。

- [ ] **P0-4 — chain-of-verification + LLM-as-judge**
      论文 §3.2.5 + CoVe glossary + §3.3.2 LLM-as-judge。
      (a) ReAct 主 agent 在"写入知识库"前插入 verifier 步骤；
      **(b) 专利路径额外加 LLM-as-judge（第二 LLM 检查 factual inconsistency）**。
      工作量：3-5 天。

## P1 — 近期计划

- [ ] **P1-1 — document cleaning**（剥 references/ack/headers）
      论文 §3.1.2。期望向量库大小下降 ≥ -30%。
      工作量：3 天。

- [ ] **P1-2 — semantic chunking + 分类预过滤**
      论文 §3.1.3, Fig. 5。当前仅 `text-splitter` fixed-size。
      工作量：1-2 周。

- [ ] **P1-3 — ontology grounding**（ChEBI / PubChem CID）
      论文 §3.3.1 SPIRES 范式。
      工作量：1 周。

- [ ] **P1-4 — multi-agent (creator + critic)**
      论文 §3.2.5 multi-agent。`rig_adapter.rs` 加 verifier agent。
      工作量：1-2 周。

- [ ] **P1-5 — YAML schema 替换 JSON**
      论文 §3.2.1 Patiny & Godin。
      工作量：2 天。

- [ ] **P1-6 — DSPy 引入可行性评估**
      论文 §3.2.1。评估报告 `docs/dspy-eval.md`。
      工作量：1 周。

- [ ] **P1-7 — claim-example-reaction 三层 join**（专利域核心）
      论文 §4.2 + §5.4 瓶颈 #1。
      (a) DB schema 加 `claim_id` / `example_id` / `reaction_scheme_id` 三列；
      (b) 抽取阶段产出三层 ID 映射；(c) 评测 claim-example F1（独立于单分子 F1）。
      工作量：1-2 周。

- [ ] **P1-8 — 同族专利 family traversal**（专利域，论文 §4.2 前沿提前）
      (a) 新增 `agent 工具：patent_family(doc_id)` 抓 US/EP/JP/CN 同族；
      (b) 同族 join 入知识库；(c) 跨语种 link。
      工作量：2-3 周。

- [ ] **P1-9 — Claim 语言学解析**（专利域）
      论文 §5.4 瓶颈 #4。
      (a) 新增 `parse_claim_language(text)`：识别 "comprising" / "consisting of" / "wherein"；
      (b) 输出 claim scope 类型（open/closed/limited）；(c) 律师 review 校验。
      工作量：1 周。

- [ ] **P1-10 — CPC 分类 link**（专利域）
      论文 §3.3.1 SPIRES + §5.4 瓶颈 #5。
      (a) 抽到的分子映射 CPC code；(b) 知识库加 `cpc_code` 列；(c) 支持按 CPC 子领域检索。
      工作量：1 周。

- [x] **处理队列 UX 优化 + 当前 PDF 流程图**（2026-06-12）
      见 `TODO/2026-06-12-processing-queue-ux.md`。
      Phase 1+2：A PdfPipelineFlow · B 列表打磨 · C 吞吐洞察 · G 跨页 toast。

## P2 — 中期计划

- [ ] **P2-1 — citation traversal 工具**（论文 §4.2）
- [ ] **P2-2 — VLM 替代 A/B 实验**（论文 §3.2.4）
- [ ] **P2-3 — Human-in-the-loop 标注 UI**（论文 §3.2.2 Dagdelen）
- [ ] **P2-4 — 化学抽取 LoRA 微调**（论文 §3.2.2）
- [ ] **P2-5 — 负结果 / 失败案例库**（论文 §4.3）
- [ ] **P2-6 — query-to-model 探索**（论文 §4.5）
- [x] **P2-7 — pdf-inspector 深度优化**（2026-06-22）
      见 `TODO/2026-06-22-pdf-inspector-investigation.md`。
      P-S4 锁版本 · P-S2 单次加载复用 · P-S1 heading 解析简化 · P-S3 per-page OCR routing。

详见 `TODO/2026-06-22-llm-extraction-paper-research.md` 完整定义。

## 技术债务

> 与 `AGENTS.md`「技术债务」同步维护。修复后两边同时更新。

| # | 债务 | 严重性 | 状态 | 修复方案 | 优先级 |
|---|------|--------|------|---------|--------|
| 1 | chem_validate.rs 与 core/chem.rs 边界模糊（委派层而非重复） | 中 | 🟥 待修复 | 合并到 chem.rs | P2 |
| 2 | 多个 std::sync::Mutex 在 async 上下文 | 高 | 🟧 进行中 | 迁移到 tokio::sync::Mutex | P1 |
| 3 | chematic git 依赖缺 tag | 中 | 🟥 待修复 | 锁定到特定 commit | P2 |
| 4 | Python sidecar 单进程无连接池 | 中 | 🟥 待修复 | 添加连接池 + 优雅降级 | P2 |
| 5 | tracing 覆盖不全 | 中 | 🟧 部分完成 | 扩展 observability.rs 到所有跨边界调用 | P2 |
| 6 | 无成本护栏 | 中 | 🟥 待修复 | 新增 BudgetEnforcer | P3 |
| 7 | 27 分钟管线瓶颈 | 高 | 🟧 部分完成 | LLM 调用并行化 | P1 |
| 8 | constants.rs 生成机制失效 | 中 | 🟧 部分完成 | 脚本已修复，Rust 侧改为参考文件 + 人工合并 | P2 |

---

## P3 — 远期 / 想法

## 已完成（本次会话）

- [x] 前端 API 彻底统一到单层（`api/tauri/*`）
- [x] Environment 页面添加"刷新模型环境"按钮（调用 `refresh_resolved_paths` + 自动重载模型列表）
- [x] 删除遗留顶层 API 文件（`http.ts`、`download.ts`、`moldet.ts`、`settings.ts`）
- [x] Rust/Python 模型路径扫描统一为 ENV 优先级顺序（MBFORGE → HF_HOME → MODELSCOPE → TORCH_HOME）
- [x] Python 侧改为优先读 Rust 写入的 `resolved_paths.json`（单一真相源）
- [x] Rust 添加 `refresh_resolved_paths` Tauri 命令供前端刷新调用
- [x] `resolved_paths.json` 缓存改为 mtime 感知，Rust 刷新后 Python 自动重读
- [x] **化学信息学模块封装为 26 个 Tauri 命令**（2026-06-15）
      14 纯计算 (`chem_ops.rs`) + 12 engine CRUD (`molecule_admin.rs`) + 2 个 frontend API 文件。
      Commit `8b998a8`。surgical 修复：orphan `preprocess` 模块注册 + `lazy_static` → `LazyLock`。
      Spec 在 `docs/superpowers/specs/2026-06-15-cheminformatics-optimization-design.md`。

## 未完成（cheminformatics 后续 follow-up）

> 26 命令已暴露但**未被前端消费**。待 UI 集成 + 业务接入。

- [ ] **前端消费层**：用 `chem.ts` / `molecule_admin.ts` 实现的 UI 组件（无明确 owner）
      - `chemCanonicalize` → dedup 提交前规范化（替换 `molecule_extractor` 内的 ad-hoc 标准化）
      - `chemSeparateEsmilesLayers` → 取代 `chem_validate::separate_esmiles_layers` 的 pipeline 调用点
      - `chemMarkushCheck` → 集成到 `claim_policy.rs` 的 `check_compound_against_claims`
      - `molAdminList` + `molAdminStoreStats` → "库管理" 面板（搜索/分页/统计）
      - `molAdminAdd` / `Update` / `Delete` → 手动编辑/删除分子 UI
      - `chemGesimAtomMapping` → 分子对齐高亮可视化
- [ ] **`mol_search_substructure` 重构**：当前用 `db.get_all_smiles()` 全表扫描 O(N)，N 大时性能劣化
      - 加 SQLite FTS5 加速候选筛选，或
      - 用 `chemSubstructureSearch` 替代让前端传候选
- [ ] **`chemValidateSmiles` vs `chemSeparateEsmilesLayers` 统一入口**：
      前端两路径并存易混淆。统一为单一"输入 e-smiles" → 校验 + 分离 + 标签解析三合一函数
- [x] **orphan `preprocess` 模块补测试**：已加 12 个测试用例覆盖 preprocess_rgroup_name + preprocess() 管线
      `preprocess_smiles` / `preprocess_rgroup_name` / `normalize_abbrev_name` / `sanitize_identifier` 全覆盖
- [x] **`chem_canonicalize` 作为 dedup 主键**：canonicalize_esmiles 已升级为 chematic 化学规范化
      当前 `MoleculeRecord::smiles` 字段无 canonical 形式，重复分子（不同写法）可能插入多次
      需在 `molecule_dedup::run_dedup_batch` 入口用 `chemCanonicalize` 归一化候选 SMILES

## 待评估（pageindex 调研）

- [ ] **PageIndex 替换向量检索可行性评估**
      调研报告 `docs/pageindex-research.md`（2026-06-14）结论：PageIndex **不建议完全替换**。
      详见下方 pageindex 评估章节。
