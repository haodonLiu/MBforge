# 2026-06-03 — 化学信息学 Rust 化重构（已归档）

> 本文件归档 2026-06-03 完成的"chematic 集成" + "开源替代分析" 中已实施项。
> **核验基线**：chematic 5 个 crate 锁到 `rev = "2702636"`、cargo check 通过。
> **保留目的**：chematic 能力清单供后续能力扩展参考（见 OPEN.md O-13~O-22）。

---

## 一、chematic 集成（已完成）

| 项目 | 说明 |
|------|------|
| **chematic 集成** | 纯 Rust 化学信息学库（736 测试，ChEMBL 2.9M 100% 通过） |
| **core/chem.rs** | SMILES 校验、ECFP4 指纹、Tanimoto 相似度、VF2 子结构搜索 |
| **三级漏斗全 Rust 化** | Tanimoto 预过滤 → VF2 子图同构 → 零 Python sidecar 调用 |
| **SQLite FTS5 + vectors.db** | 单一 SQLite 存储向量 + BM25，Rust 侧 `document/knowledge_base.rs` 统一管理 |
| **semantic_cache** | SHA-256 查询缓存 + TTL 1小时，取代旧 JSON 方案 |
| **文件内容缓存** | SHA-256 + mtime 两级检查，避免重复 PDF 解析 |
| **代码瘦身** | 净删 ~710 行死代码（SqliteVectorStore、pending.rs 等） |

---

## 二、chematic 可用能力清单（已集成 vs 未集成）

| 模块 | 能力 | 状态 | 关联待办 |
|------|------|------|----------|
| `chematic-core` | Molecule 结构、Kekulization、元素数据 | ✅ | — |
| `chematic-smiles` | OpenSMILES 解析/写入、canonical SMILES | ✅ | — |
| `chematic-fp` | ECFP4/6、MACCS、AtomPair、Torsion FP、Tanimoto/Dice | ✅ | — |
| `chematic-smarts` | SMARTS 解析、VF2 子图同构、MCS | ✅ | — |
| `chematic-chem` | MW/LogP/TPSA/QED/Lipinski/Murcko/BRICS/CIP/VSA/SA | ✅ 部分 | O-15/O-16 |
| `chematic-mol` | MOL/SDF V2000+V3000 读写 | ❌ 未集成 | O-13 |
| `chematic-depict` | 2D SVG 渲染（CPK 配色、高亮） | ❌ 未集成 | O-20 |
| `chematic-rxn` | 反应 SMILES/SMIRKS 解析 | ❌ 未集成 | O-17 |
| `chematic-3d` | 3D 坐标生成、UFF 能量最小化、PDB/XYZ | ❌ 未集成 | O-18/O-19 |
| `chematic-perception` | SSSR 环检测、Hückel 芳香性 | ✅ | — |
| `chematic-wasm` | WebAssembly 绑定 | ❌ 未集成 | O-21 |

---

## 三、开源替代方案（已完成 vs 待办）

### 已完成
| # | 自研模块 | 开源替代 | 备注 |
|---|---------|---------|------|
| 1 | LanceDB | SQLite FTS5 + semantic_cache | 已移除 LanceDB |
| 2 | `chem_validate.rs` + Python `/chem/validate` | `chematic` | 已集成 |

### 待办
| # | 自研模块 | 开源替代 | 关联 |
|---|---------|---------|------|
| 3 | `post_process.rs:605-699` JSON 修复 | `llm_json` crate | O-14 |
| 4 | `semantic_cache.rs` (~493 行) | `moka` crate | 待评估 |
| 5 | `llm.rs` (~516 行) | `async-openai` / `rig` | 待评估 |

### 不建议替代（自研合理）
- `agent.rs` ReAct 循环 — 深度领域定制
- `memory/` 记忆系统 — 6 分类结构化记忆
- `association.rs` 分子-文本关联 — 领域特定
- `parsers/pipeline.rs` PDF 解析编排 — 合理编排层

### 推荐实施顺序（原始建议）
```
Phase 1（本周）:
  ├─ ① llm_json 替换 JSON 修复（cargo add，一行替换）  ⬜ O-14
  └─ ② （LanceDB 已移除）  ✅
Phase 2（本月）:
  ├─ ③ rdkit-rs 替换 chem 验证 HTTP 层（评估 C++ 编译链）
  └─ ④ moka 替换 semantic_cache（测试缓存命中率）  ⬜
Phase 3（后续）:
  └─ ⑤ 评估 rig/async-openai 替换 llm.rs（非紧急）  ⬜
```
