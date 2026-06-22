# 2026-06-22 — LLM 化学抽取论文研究 + 改进路线

> 主参考论文: Schilling-Wilhelmi et al., *Chem. Soc. Rev.* 2025, **54**, 1125–1150
> DOI: [10.1039/d4cs00913d](https://doi.org/10.1039/d4cs00913d)
> 配套规范: `docs/specs/llm-chemical-extraction-reference.md` v1.0
> 状态: ✅ 研究完成 · 🟧 P0-1 进行中

---

## 1. 研究背景

Jablonka 组 (FAIRmat / Jena) 在 *Chem. Soc. Rev.* 发表的 tutorial review，是当前
**LLM 用于化学数据抽取** 最系统的综述。论文核心论点：评估 > 抽取，
化学领域有独特校验资源（chematic 类工具），constrained decoding 是低垂果实。

完整论文分析、现状盘点、可做/不可做边界 → 见 `docs/specs/llm-chemical-extraction-reference.md`。

---

## 2. 关键发现（现状盘点）

经代码核查（2026-06-22），MBForge 与论文框架对照：

### 缺口（按严重性）
1. **无 F1 / precision / recall 评估体系** — `src-tauri/src/` grep 0 命中
2. **无 constrained decoding** — agent 输出自由字符串，E-SMILES 文法未利用
3. **temperature=0.7** — `llm_gateway.rs:178` 硬编码，论文强推抽取任务 t=0
4. **无 self-reflection / critic** — agent/ 下 0 命中 verifier
5. **chunking 只有 text-splitter (fixed)** — 无 semantic / 分类预过滤
6. **无文档清洗** — refs/ack/headers 未剥离
7. **无 ontology grounding** — ChEBI/PubChem CID 未链接
8. **无 cross-document linking** — RAG 仅单文档内
9. **无 multi-agent** — single ReAct
10. **无 prompt 自动优化** — DSPy 类未评估

### 已对齐
- 多 backend OCR + VDU
- RAG (Qwen3 384d + SQLite + FTS5)
- MolDet + MolScribe + cross-page coref
- ReAct agent (16 工具 + 9 文献)
- chematic 校验 (SMILES / ECFP4 / Tanimoto / VF2)
- E-SMILES / MoleCode 三层表示（最天然 constrained decoding 目标）

---

## 3. 改进路线（来自规范 §6）

### P0 — 必须做（建立质量基线）

- [ ] **P0-1 — gold set + F1 harness**
      论文 §3.3.2。验收：(a) ≥50 gold PDF + 标注 JSON；(b) Rust 端实现
      precision/recall/F1；(c) Hungarian assignment；(d) Levenshtein fuzzy；
      (e) `cargo run --bin eval` 跑通给 baseline 数字。
      工作量：2-3 周。

- [ ] **P0-2 — temperature=0 强制（抽取路径）**
      论文 §3.1, §3.3.1。验收：`llm_gateway.rs` 所有抽取调用 t=0；单元测试覆盖。
      工作量：半天。

- [ ] **P0-3 — constrained decoding 接 E-SMILES**
      论文 §3.3.1。验收：(a) 选 `outlines` 或自实现 grammar；
      (b) Python 侧 LLM 调用接 E-SMILES 文法；(c) 与 P0-1 对照无效率下降。
      工作量：1-2 周。

- [ ] **P0-4 — chain-of-verification 自检步骤**
      论文 §3.2.5 + CoVe glossary。验收：ReAct 主 agent 在"写入知识库"前插入
      verifier 步骤；成本/收益在 P0-1 上量化。
      工作量：3-5 天。

### P1 — 应该做（论文强推）

- [ ] **P1-1 — document cleaning** (剥 refs/ack/headers)
      论文 §3.1.2。验收：`text.md` 阶段加 cleaning step；
      前后向量库大小对比 ≥ -30%。工作量：3 天。

- [ ] **P1-2 — semantic chunking + 分类预过滤**
      论文 §3.1.3 Fig. 5。验收：(a) 引入 semantic chunker；
      (b) 启发式分类器预过滤；(c) 与 P0-1 对比 F1。工作量：1-2 周。

- [ ] **P1-3 — ontology grounding** (ChEBI / PubChem CID)
      论文 §3.3.1 SPIRES。验收：(a) 入库时 PubChem REST 查询；
      (b) 新增 `ontology_id` 列；(c) 与外部可 join。工作量：1 周。

- [ ] **P1-4 — multi-agent (creator + critic)**
      论文 §3.2.5。验收：`rig_adapter.rs` 加 verifier agent；
      双 agent 投票；冲突时人工 review。工作量：1-2 周。

- [ ] **P1-5 — YAML schema 替换 JSON**
      论文 §3.2.1 Patiny & Godin。验收：system prompt 改 YAML；
      token 减少 ≥20%。工作量：2 天。

- [ ] **P1-6 — DSPy 引入可行性评估**
      论文 §3.2.1。验收：评估报告 `docs/dspy-eval.md`；
      决定接 / 不接 + 理由。工作量：1 周。

### P2 — 前沿（论文 §4 开放问题）

- [ ] **P2-1 — citation traversal 工具**
      论文 §4.2。验收：新增 `cite_traverse(paper_id)` 工具；
      references 入 RAG。工作量：2-3 周。

- [ ] **P2-2 — VLM 替代 A/B 实验**
      论文 §3.2.4。验收：选定 VLM API；
      与 OCR+Moldet 管线 A/B；写评估报告。工作量：2-3 周。

- [ ] **P2-3 — Human-in-the-loop 标注 UI**
      论文 §3.2.2 Dagdelen。验收：Argilla 风格前端；
      标注数据驱动 P2-4。工作量：3-4 周。

- [ ] **P2-4 — 化学抽取 LoRA 微调**
      论文 §3.2.2。验收：≥200 gold 样本（依赖 P2-3）；
      LoRA 微调基础 LLM；与 P0-1 对比。工作量：2-3 周。

- [ ] **P2-5 — 负结果 / 失败案例库**
      论文 §4.3。验收：schema + 收集机制；对抗 scientific bias。
      工作量：1-2 周。

- [ ] **P2-6 — query-to-model 探索**
      论文 §4.5。验收：与 PaperQA 对齐 PoC。research。

---

## 4. 关键决策（立即生效）

| 决策点 | 旧值 | 新值 | 触发条件 |
|--------|------|------|---------|
| 抽取路径 temperature | 0.7 | **0.0** | P0-2 落地后 |
| system prompt 格式 | JSON | **YAML**（视场景） | P1-5 落地后 |
| LLM 输出约束 | 自由字符串 | **constrained decoding** | P0-3 落地后 |

---

## 5. 收益 vs 成本估算

**最低限度落地 P0-1 + P0-2 + P0-3 + P1-1** 的预估收益（保守）：
- 抽取无效率（错误 SMILES / 错误反应）下降 ≥ 50%
- 向量库存储下降 ≥ 30%（document cleaning）
- 评估可重复（temperature=0 + gold set + F1）
- 后续所有改动有量化基线

**预估工作量**：6-8 周（一人专注）

**不做 P0-1 的代价**：所有 P1/P2 改动无法量化收益，回退到"凭感觉调参"。

---

## 6. 同步更新

- [x] 写入 `docs/specs/llm-chemical-extraction-reference.md` v1.0
- [x] 写入 `TODO/INDEX.md` P0/P1 区块（下次看板整理时同步）
- [ ] AGENTS.md §技术债务新增一行：本研究主导 P0-1

---

## 7. 引用

> 主参考论文: Schilling-Wilhelmi M., Rios-Garcia M., Shabih S., Gil M.V., Miret S.,
> Koch C.T., Marquez J.A., Jablonka K.M. *From text to insight: large language
> models for chemical data extraction*. Chem. Soc. Rev. 2025, 54, 1125-1150.
> DOI: 10.1039/d4cs00913d

> Companion: https://matextract.pub ·
> https://github.com/lamalab-org/matextract-book

---

## 8. 自我反思

直白说，本次研究最大的冲击是认识到 MBForge 长期缺乏评估体系。
我们花了大量精力做"管道"（PDF→md→molecule→vector），但论文 §3.3
整套质量保证（constrained decoding + domain validation + F1 evaluation）
几乎空白。这不是"细节优化"，而是"方向问题"。

P0-1 必须在其他一切改动之前完成。