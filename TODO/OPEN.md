# MBForge 未完成项明细

> 本文件汇集代码与文档中所有"未实现" / "待办" / "占位"信号，按优先级排序。
> 入口与摘要见 [INDEX.md](INDEX.md)。每条都标注**来源**（核验方式）+ **定位**（文件:行号或看板 ID）。
> 已完成/已归档项不在此出现——见 [archive/](archive/)。

---

## 🔴 P0 — 阻塞性 / 用户明显感知

### O-04. moldet 区域重检设计分离
- **核验（2026-06-06）**：
  - 前端 `api/moldet.ts:49` `extractRegion()` 走 **Python sidecar HTTP** `/api/v1/moldet/extract-region` ✅
  - 后端 `vlm_chem.rs:153-174` 在 Rust 端同样调 sidecar（不是 Tauri 命令）
  - Tauri 端**确实无** `extractRegion` / `extract_region` 命令（grep 0 命中）
- **OPEN.md 失实修正**：原描述"违反迁移期规则，前端调用逐步迁 Tauri invoke"**不准确** — 当前是**有意识的设计分离**（moldet 走 Python，Rust 调度，Vite proxy 在 dev 模式下桥接）
- **真实问题**（如果有）：Tauri 生产构建下前端直连 sidecar URL 的配置（与 sidecar 启动模式耦合）— 这不是 O-04 描述的"迁移"
- **结论**：**不修**，不视为待办

### O-06. 代码内占位 #2 — Embedding 替换为 ONNX Runtime
- **位置**：`src-tauri/src/core/vector/embedding.rs:4`
- **原文**：当前 HTTP 调 sidecar `/embed`，后续可换 ONNX Runtime
- **真实情况**：
  - `SidecarEmbedder`（L80-173）调 sidecar HTTP
  - `DeterministicEmbedder`（L177-225）测试 fallback（无 key 时用文本哈希伪向量）
  - 功能上**完整**（有 fallback），ONNX 改造是性能优化
- **建议工作量**：1-2 天（性价比低，留为 P3 性能优化）

---

## 🟧 P1 — 结构性 / 看板明示

### O-08. 任务 A：数据库抽象层
- **看板**：TODO/INDEX.md Task A ⬜
- **核验**：grep `trait Table|Table\s+trait` → **0 命中**
- **依赖**：阻塞 Task B 收尾
- **建议工作量**：3-4 天

### O-09. 任务 C：可观测性层
- **看板**：TODO/INDEX.md Task C ⬜
- **核验**：`tracing::|BudgetEnforcer` → 仅 1 行在 `observability.rs` 注释（"已显式移出"）
- **建议工作量**：2-3 天

### O-10. Task B 收尾 — sanitize_esmiles 冗余清理
- **看板**：TODO/INDEX.md Task B 🟧
- **核验（2026-06-06）**：
  - schema + `migrate_v0_to_v1` ✅
  - FTS5 独立表 + 显式同步（`knowledge_base.rs:87-90`）✅ — **不需改造**（OPEN.md 旧描述"仍索引 text"失实）
  - `sanitize_esmiles` 调度点：
    - `chem_validate.rs:27/90` 公共 API 入口净化 ✅ 保留（外部命令依赖）
    - `post_process.rs:669` 早期净化 ✅ 保留（让 `c.esmiles` 日志输出一致）
    - `pipeline.rs:893` 冗余净化 loop ✅ **已删除**（紧跟 `validate_smiles_batch`，后者入口会净化）
- **改造动机**：Stage 3.5 的净化 loop 与 `validate_smiles_batch` 入口净化重复，去重提升可读性。
- **建议工作量**：30 分钟（仅修改一处）
- **状态**：✅ 完成

---

## 🟡 P2 — 化学能力扩展

### O-13. MOL/SDF 文件解析
- **核验**：`SUPPORTED_MOL_EXTS` 含 sdf/mol/mol2/pdb/smi ✅（声明支持）
- **核验**：`core/chem/sar.rs::parse_mol` 实际**只是 SMILES 解析器**，`chematic-mol` 未引用 ❌
- **建议工作量**：1 天

### O-15. BRICS 分子碎片化
- **核验**：`brics|BRICS` → **0 命中**
- **建议工作量**：1 天

### O-16. Murcko 骨架提取
- **核验**：`murcko|Murcko` → **0 命中**
- **建议工作量**：1 天

### O-17. 反应 SMILES / SMIRKS 支持
- **核验**：`schematic_rxn|smirks|SMIRKS` → **0 命中**
- **建议工作量**：1 天

### O-18. 3D 坐标生成
- **核验**：`schematic_3d|uff_minimize` → **0 命中**
- **建议工作量**：1-2 天

### O-19. PDB/XYZ 格式解析
- **核验**：`chemfiles` 未在 Cargo.toml 引用
- **建议工作量**：1-2 天

---

## 🟢 P3 — 可视化与前端增强

### O-20. 2D 分子 SVG 渲染
- **核验**：`schematic_depict|depict` → **0 命中**
- **现状**：靠 mermaid MoleCode
- **建议工作量**：2 天

### O-21. WASM 分子预览
- **核验**：`schematic_wasm|wasm_bindgen` → **0 命中**
- **建议工作量**：2-3 天

### O-22. SMARTS 模式编辑器
- **核验**：`sar.ts:8` 有 `scaffold_smarts` 字段；前端无 UI 编辑器
- **建议工作量**：1-2 天

---

## 🛠 代码内遗留清理

### I-NN 索引见 [INLINE-TODOS.md](INLINE-TODOS.md)
- **I-02**（O-06 同源）：Embedding HTTP sidecar 待替换 ONNX
- **I-04**：Anthropic thinking 内容暂不输出（设计取舍）

---

## ID 编号说明

- O-NN = 本文件（OPEN.md）未完成项
- I-NN = 代码内注释（见 [INLINE-TODOS.md](INLINE-TODOS.md)）

> **维护规则**：
> 1. 完成任务 → 删除对应条目（不是标 ✅——避免"已完成"占用主清单空间）
> 2. 完成的修复包整体移入 [archive/](archive/)
> 3. 新增待办 → 加在本文件，分配下一个 O-NN
> 4. **核验日** — 2026-06-06 复核 O-04/O-05/O-07 描述，发现 O-04/O-07 与代码失实，已改写；O-05 已在 commit 中实现。
