# MBForge 目标架构设计

> 版本: 1.0
> 日期: 2026-06-04
> 基于: 当前代码审计 + 6 份参考文献 + ETCLOVG 七层框架

---

## 一、设计原则

1. **Harness > Model** — 基础设施质量比模型能力更重要（Harness Engineering 论文核心论点）
2. **Rust 优先，Python 必要时** — 高频操作 Rust 原生，ML 推理走 Python sidecar
3. **双轨分子表示** — 存储用 E-SMILES，LLM 推理用 MoleCode（四层表示模型）
4. **追加写入 + 不可变帧** — 文档索引结果不可变，支持崩溃恢复和审计（Memvid 模式）
5. **可观测性是一等公民** — 每个跨边界调用有 trace ID，每个 Agent 决策可审计

---

## 二、骨架拓扑（三层七层）

```
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 7: Governance (治理)                    │
│  预算执行 · 权限模型 · 审计日志 · 成本追踪                        │
├─────────────────────────────────────────────────────────────────┤
│                  Layer 6: Verification (验证)                    │
│  化学有效性校验 · 输出接地检查 · 回归测试 · Agent 行为验证          │
├─────────────────────────────────────────────────────────────────┤
│                Layer 5: Observability (可观测性)                  │
│  结构化 tracing · Token/Cost 统计 · 跨边界关联 ID · 性能指标       │
├─────────────────────────────────────────────────────────────────┤
│              Layer 4: Lifecycle / Orchestration (生命周期)        │
│  Agent ReAct 循环 · 任务分解 · 技能库 · 记忆系统 · 流式事件        │
├─────────────────────────────────────────────────────────────────┤
│               Layer 3: Context Management (上下文)                │
│  短期: 对话窗口 · 长期: MemoryManager · 情景: Episodes            │
│  语义: LanceDB KB · 持久: 文件缓存 · 向量: Embedder               │
├─────────────────────────────────────────────────────────────────┤
│                Layer 2: Tool Interface (工具接口)                  │
│  ToolRegistry (25+ 工具) · 分子工具 · 文档工具 · KB 工具           │
│  文献工具 · 文件工具 · Agent 子代理工具                             │
├─────────────────────────────────────────────────────────────────┤
│             Layer 1: Execution Environment (执行环境)             │
│  Tauri Shell · Python Sidecar (FastAPI:18792) · 进程管理           │
│  SQLite · LanceDB · 文件系统 · HTTP 客户端                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、组件拓扑图

```
                           ┌──────────────────┐
                           │   React Frontend  │
                           │  (TypeScript/Vite)│
                           └────────┬─────────┘
                                    │ Tauri IPC invoke() + listen() events
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        Tauri v2 Shell (Rust)                            │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Command Layer (55+ commands)                    │   │
│  │  agent · kb · molecule · pipeline · notes · file · project · ...  │   │
│  └──────────┬──────────┬──────────┬──────────┬──────────┬───────────┘   │
│             │          │          │          │          │                 │
│  ┌──────────▼──┐ ┌─────▼────┐ ┌───▼────┐ ┌──▼───┐ ┌───▼──────────┐    │
│  │   Agent     │ │  KB      │ │Molecule│ │Parser│ │ResourceMgr   │    │
│  │   Core      │ │  Core    │ │ Core   │ │Core  │ │              │    │
│  │             │ │          │ │        │ │      │ │              │    │
│  │ ┌─────────┐ │ │┌────────┐│ │┌──────┐│ │┌────┐│ │              │    │
│  │ │ReAct    │ │ ││LanceDB ││ ││SQLite││ ││Pipe││ │  模型下载     │    │
│  │ │循环     │ │ ││+ FTS5  ││ ││+FTS5 ││ ││line││ │  路径管理     │    │
│  │ └────┬────┘ │ │└───┬────┘│ │└──┬───┘│ │└─┬──┘│ │  GPU 检测     │    │
│  │ ┌────▼────┐ │ │┌───▼────┐│ │┌──▼───┐│ │┌─▼──┐│ │              │    │
│  │ │Context  │ │ ││Embedder││ ││Chem  ││ ││Stag││ │              │    │
│  │ │Manager  │ │ ││(L1/L2) ││ ││(Rust)││ ││es  ││ │              │    │
│  │ └────┬────┘ │ │└────────┘│ │└──────┘│ │└────┘│ │              │    │
│  │ ┌────▼────┐ │ │          │ │        │ │      │ │              │    │
│  │ │ToolExec │ │ │          │ │        │ │      │ │              │    │
│  │ │(25+tool)│ │ │          │ │        │ │      │ │              │    │
│  │ └────┬────┘ │ │          │ │        │ │      │ │              │    │
│  │ ┌────▼────┐ │ │          │ │        │ │      │ │              │    │
│  │ │Memory   │ │ │          │ │        │ │      │ │              │    │
│  │ │6 class  │ │ │          │ │        │ │      │ │              │    │
│  │ └─────────┘ │ │          │ │        │ │      │ │              │    │
│  └─────────────┘ └──────────┘ └────────┘ └──────┘ └──────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │               Layer 5: Observability (新增)                       │   │
│  │  TraceId · SpanId · TokenCounter · CostTracker · AuditLog         │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │               Layer 6: Verification (增强)                        │   │
│  │  Chematic 校验 · RDKit 校验 · 输出接地检查 · 化学一致性             │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │               Layer 7: Governance (新增)                          │   │
│  │  BudgetEnforcer · PermissionModel · RateLimiter · AuditTrail      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ HTTP (port 18792)
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    Python Sidecar (FastAPI)                              │
│                                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│  │ LLM      │ │ Embed    │ │ Rerank   │ │ VLM      │ │ MolDet   │     │
│  │ /chat    │ │ /embed   │ │ /rerank  │ │ /vlm     │ │ /moldet  │     │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘     │
│                                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│  │ Chem     │ │ SAR      │ │ Download │ │ Popo     │ │ MoleCode │     │
│  │ /chem    │ │ /sar     │ │ /download│ │ /popo    │ │ /molecode│     │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘     │
│                                                          (新增)         │
└──────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    ML Models & External APIs                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│  │ Qwen LLM │ │ Qwen3    │ │ Qwen3    │ │ mimo-v2  │ │ MinerU   │     │
│  │ (GGUF)   │ │ Embed    │ │ Rerank   │ │ VLM      │ │ Popo 4B  │     │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘     │
│                                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                                │
│  │ MolScribe│ │ UniParser│ │ arXiv API│                                │
│  │ (OCSR)   │ │ (cloud)  │ │ (litera) │                                │
│  └──────────┘ └──────────┘ └──────────┘                                │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 四、分子四层表示架构

```
Layer 4: 化学语义层 ──── Agent 推理时的功能基团、药理性质、SAR
   ▲                          │
   │  Agent 系统提示           │ LLM 推理输出
   │                          ▼
Layer 3: 显式图层 ────── MoleCode 图（持久 ID + 显式边）
   ▲                          │
   │  mermaid_to_mol()        │ mol_to_molecode()
   │                          ▼
Layer 2: 分子对象层 ──── Chematic Mol / RDKit Mol
   ▲                          │
   │  SmilesParser::parse()   │ mol.to_smiles()
   │                          ▼
Layer 1: 线性字符串层 ── E-SMILES（存储、交换、数据库）

存储路径: Layer 1 (E-SMILES) ──→ molecule_store.rs SQLite
推理路径: Layer 1 → Layer 2 → Layer 3 → Agent → Layer 4
验证路径: Layer 1 → Layer 2 → Chematic/RDKit 校验
```

**关键规则**:
- 存储只用 Layer 1（E-SMILES），兼容所有工具链
- Agent 推理时转 Layer 3（MoleCode），减少 LLM 认知负荷
- 验证用 Layer 2（Chematic/RDKit），确保化学正确性

---

## 五、文档处理管线架构

```
PDF 输入
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 0: 文件缓存检查                                        │
│   FileCache.get(path) → HIT: 跳到 Stage 1                   │
│                        → MISS: 继续 OCR                      │
└─────────────────────┬───────────────────────────────────────┘
                      │ MISS
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 0.1: 页面级 OCR                                       │
│   pdf_inspector / MinerU / LlamaParse / UniParser / LiteParse│
│   输出: raw text + images                                    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 0.5: Popo 文档后处理 (新增)                             │
│   MinerU-Popo 4B 模型                                       │
│   ├── 标题层次分析 → 替代 headings.rs 启发式                   │
│   ├── 图文关联分析 → 替代 association.rs 纯文本                │
│   ├── 表格截断修复 → 跨页 SAR 表格完整性                      │
│   └── 长文档分块 → 动态分块 + 全局一致性                       │
│   输出: StructuredDocTree + ImageTextAssoc[] + TableFix[]     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: LLM 文档结构分析                                    │
│   run_meta_analysis() → DocStructure                         │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: 逐 Section LLM 提取                                 │
│   post_process_section() → StructuredData[]                  │
│   ├── 化合物提取 → E-SMILES + 活性数据                        │
│   ├── 专利 Claim 解析                                         │
│   └── VLM 化学结构识别 (MolScribe)                            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: 合并 + 验证                                         │
│   merge_partial_results() → 最终 StructuredData              │
│   ├── Chematic SMILES 校验 (Rust 原生)                        │
│   ├── RDKit 精确验证 (Python sidecar，权威路径)                │
│   ├── 分子去重 (Tanimoto 预筛 + 精确匹配)                      │
│   └── SAR 分析                                                │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: 持久化                                              │
│   ├── FileCache.put() — 文件缓存（不可变帧）                    │
│   ├── KnowledgeBase.index_document() — LanceDB 知识库         │
│   ├── MoleculeDatabase.add_molecule() — SQLite 分子库          │
│   └── ECFP4 指纹计算 + 持久化                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、存储架构

```
.mbforge/
├── knowledge_base/
│   ├── vectors.db          ← SQLite: file_cache + content_cache
│   └── lancedb/            ← LanceDB: 向量 + BM25 混合搜索
│       ├── chunks table    (chunk_id, doc_id, text, metadata, vector)
│       └── FTS index       (BM25 on text column)
│
├── molecules.db            ← SQLite: 分子记录 + FTS5 + 指纹 BLOB
│   ├── molecules table     (mol_id, esmiles, name, activity, fingerprint BLOB, ...)
│   ├── mol_search FTS5     (name, notes, esmiles)
│   ├── molecule_relations  (mol_a_id, mol_b_id, relation_type, score)
│   └── episodes table      (新增: 情景记忆)
│
├── cache/
│   └── semantic_cache.json ← L1 查询结果缓存
│
├── doc_trees.json          ← 文档结构树
├── pages/{doc_id}/         ← 逐页文本
├── media/{doc-slug}/       ← 提取的图片
├── image-caption-cache.json ← VLM 图片描述缓存
│
├── memory/                 ← Agent 记忆
│   ├── user_profile.json
│   ├── agent_memory.json
│   └── skills.json
│
└── settings.json           ← 项目级配置
```

**存储层分工**:

| 存储 | 用途 | 查询方式 |
|------|------|---------|
| LanceDB (chunks) | 知识库文档搜索 | 向量 ANN + BM25 混合 |
| SQLite (molecules) | 分子记录 + 化学搜索 | FTS5 + 指纹 Tanimoto + VF2 子结构 |
| SQLite (vectors.db) | 文件/内容缓存 | SHA-256 hash + mtime |
| SQLite (episodes) | 情景记忆 | embedding 相似度 + 时间过滤 |
| JSON 文件 | 配置、记忆、语义缓存 | 直接读取 |

---

## 七、通信拓扑

### 7.1 跨层通信协议

```
Frontend ←──Tauri IPC invoke()──→ Rust Commands
Frontend ←──Tauri Events listen()──→ Rust (push)
Rust ←──HTTP REST──→ Python Sidecar (port 18792)
Rust ←──HTTP SSE──→ Python Sidecar (流式)
Rust ←──Child Process──→ Python uvicorn (spawn/kill)
Rust ←──SQLite file I/O──→ 数据库文件
Rust ←──LanceDB file I/O──→ 向量数据库
```

### 7.2 事件总线

| 事件 | 方向 | 用途 |
|------|------|------|
| `doc-progress` | Rust → Frontend | 文档处理进度 |
| `doc-result` | Rust → Frontend | 文档处理结果 |
| `agent-stream-chunk` | Rust → Frontend | Agent 流式回复 |
| `agent-stream-done` | Rust → Frontend | Agent 回复完成 |
| `kb-search-chunk` | Rust → Frontend | KB 搜索结果流 |
| `sidecar://log` | Rust → Frontend | Sidecar 日志 |
| `sidecar://status` | Rust → Frontend | Sidecar 健康状态 |

### 7.3 跨边界 Trace 传播（新增）

```
Frontend: trace_id = generate_uuid()
  → invoke("process_document", {trace_id, ...})
    → Rust: trace_id 贯穿所有 Stage
      → HTTP header: X-Trace-Id: {trace_id}
        → Python sidecar: 记录 trace_id
```

每个跨 Rust↔Python 的 HTTP 调用携带 `X-Trace-Id` header，用于：
- 端到端延迟追踪
- 错误关联
- 成本归因（哪个 trace 触发了多少 LLM 调用）

---

## 八、Agent 架构（当前 + 目标）

### 8.1 当前：单 Agent ReAct 循环

```
用户输入 → Agent.chat()
  │
  ├─ LLM 推理（系统提示 + 上下文 + 工具列表）
  │   └─ 输出: 工具调用 or 最终回复
  │
  ├─ 工具执行（ToolExecutor）
  │   ├─ 原生 Rust 工具（fs, kb, document, molecule, literature）
  │   └─ Sidecar 工具（LLM, embed, VLM）
  │
  ├─ 结果注入上下文
  │   └─ 循环（最多 5 次迭代）
  │
  └─ 最终回复（流式输出）
```

### 8.2 目标：增强单 Agent（不引入多 Agent）

> 魔鬼代言人建议：保持单 Agent，不做多 Agent 编排。理由：药物发现用户需要可信赖的输出，单 Agent 更可预测、可调试。

增强方向（不改变单 Agent 架构）：

```
Agent.chat()
  │
  ├─ 上下文组装（增强）
  │   ├─ 短期: 对话窗口（现有）
  │   ├─ 长期: MemoryManager 6 类记忆（现有）
  │   ├─ 情景: 相似任务的历史 episodes（新增）
  │   └─ 技能: 匹配的 skill 模板（增强）
  │
  ├─ 工具执行（增强）
  │   ├─ 原子工具: 25+ 现有工具
  │   ├─ 分子表示转换: E-SMILES ↔ MoleCode（新增）
  │   └─ 化学验证: Chematic (快速) + RDKit (权威)（新增）
  │
  ├─ 结果验证（新增）
  │   ├─ 化学有效性: Chematic 校验
  │   └─ 接地检查: 结果是否被知识库支持
  │
  └─ 情景记录（新增）
      └─ 记录: (任务, 工具序列, 结果, 耗时, token 消耗)
```

---

## 九、可观测性架构（Layer 5，新增）

### 9.1 结构化 Tracing

```rust
// 新增: core/observability.rs

pub struct TraceContext {
    pub trace_id: String,      // 端到端追踪 ID
    pub span_id: String,       // 当前操作 ID
    pub parent_span_id: Option<String>,
    pub started_at: Instant,
    pub token_count: TokenCounter,
    pub cost_estimate: f64,
}

pub struct TokenCounter {
    pub prompt_tokens: u64,
    pub completion_tokens: u64,
    pub embedding_calls: u64,
    pub llm_calls: u64,
}
```

### 9.2 成本追踪

每次 LLM/Embedding 调用记录：
- 输入 token 数
- 输出 token 数
- 模型名称
- 调用来源（哪个 Stage、哪个工具）

汇总到 `TraceContext`，最终持久化到 `.mbforge/traces/` 目录。

### 9.3 跨边界关联

```
Rust pipeline Stage 2 → HTTP POST /api/v1/llm/chat
  Header: X-Trace-Id: abc123
  Header: X-Span-Id: stage2-section3
  Header: X-Parent-Span-Id: stage2

Python sidecar 收到请求
  → 记录: trace=abc123, span=stage2-section3, model=qwen, tokens=1500
  → 返回结果

Rust 收到响应
  → TraceContext.token_count += 1500
  → TraceContext.cost_estimate += estimate_cost(1500, "qwen")
```

---

## 十、治理架构（Layer 7，新增）

### 10.1 预算执行器

```rust
pub struct BudgetEnforcer {
    pub max_tokens_per_session: u64,     // 默认 100K
    pub max_cost_per_session: f64,        // 默认 $1.00
    pub max_llm_calls_per_document: usize, // 默认 50
    pub current_usage: TokenCounter,
}

impl BudgetEnforcer {
    pub fn check_budget(&self, estimated_tokens: u64) -> Result<(), BudgetExceeded>;
    pub fn record_usage(&mut self, actual_tokens: u64, cost: f64);
}
```

### 10.2 权限模型

| 操作 | 权限级别 | 审计 |
|------|---------|------|
| 读取文件 | 基础 | 否 |
| 写入文件 | 受限（assert_within_root） | 是 |
| 执行 LLM 调用 | 计量 | 是 |
| 访问外部 API | 受限 | 是 |
| 删除数据 | 确认 | 是 |

---

## 十一、记忆架构（增强）

### 11.1 四层记忆模型

```
短期记忆: LayeredContext（对话窗口，token 预算内）
  └─ 最近 N 轮对话 + 工具结果

长期记忆: MemoryManager（6 类，SQLite 持久化）
  └─ 用户画像、Agent 记忆、文档摘要、项目笔记、...

情景记忆: Episodes（新增）
  └─ (任务描述, 工具序列, 结果摘要, 耗时, token消耗, 时间戳)
  └─ 检索: embedding 相似度 + 时间衰减 + 任务类型过滤

语义记忆: 从 episodes 淘炼（远期）
  └─ "处理专利文献时，SAR 表格通常在 Results Section 的 Table 2-5"
```

### 11.2 情景记忆表

```sql
CREATE TABLE episodes (
    episode_id TEXT PRIMARY KEY,
    task_description TEXT NOT NULL,
    tools_used TEXT,          -- JSON: ["search_knowledge_base", "analyze_molecule"]
    result_summary TEXT,
    success BOOLEAN,
    duration_ms INTEGER,
    tokens_used INTEGER,
    cost_estimate REAL,
    trace_id TEXT,
    created_at REAL,
    embedding BLOB            -- 用于相似任务检索
);
```

---

## 十二、验证架构（Layer 6，增强）

### 12.1 化学验证双路径

```
SMILES 输入
  │
  ├── 快速路径: Chematic (Rust 原生, <1ms)
  │   ├── validate_smiles() → 语法校验
  │   ├── compute_ecfp4() → 指纹
  │   └── tanimoto_similarity() → 相似度
  │
  └── 权威路径: RDKit (Python sidecar, 2-5ms)
      ├── /api/v1/chem/validate → 完整校验
      ├── /api/v1/chem/tanimoto → Morgan 指纹
      └── /api/v1/chem/substructure_search → HasSubstructMatch
```

**规则**: Chematic 结果用于快速过滤和预筛，RDKit 结果用于最终确认。两者冲突时以 RDKit 为准。

### 12.2 Agent 输出接地检查（新增）

```rust
pub fn check_groundedness(
    agent_response: &str,
    knowledge_base: &KnowledgeBase,
) -> GroundednessReport {
    // 1. 从 agent_response 提取关键声明
    // 2. 在知识库中搜索支持证据
    // 3. 计算接地分数
    GroundednessReport {
        score: f64,           // 0.0-1.0
        supported_claims: Vec<(String, Vec<SearchResult>)>,
        unsupported_claims: Vec<String>,
    }
}
```

---

## 十三、组件依赖矩阵

| 组件 | 依赖 | 被依赖 | 通信方式 |
|------|------|--------|---------|
| **Tauri Shell** | OS, WebView | Commands | IPC |
| **Commands** | Core, Parsers | Frontend | invoke() |
| **Agent** | LlmClient, ToolExecutor, Context, Memory | Commands | 直接调用 |
| **LlmClient** | HTTP | Python sidecar | HTTP/SSE |
| **ToolExecutor** | ToolRegistry, 各工具模块 | Agent | 直接调用 |
| **KnowledgeBase** | LanceDB, FileCache, Embedder | Commands, Agent | 直接调用 |
| **MoleculeEngine** | MoleculeStore, RelationDb, Chematic | Commands, Agent | 直接调用 |
| **Pipeline** | OCR, Popo, LLM, Chematic, KB | Commands | 直接调用 |
| **Embedder** | HTTP | Python sidecar | HTTP |
| **MemoryManager** | JSON 文件 | Agent | 直接调用 |
| **Chematic** | Rust crate | Pipeline, MoleculeEngine | 直接调用 |
| **Python Sidecar** | FastAPI, torch, RDKit | Rust | HTTP |
| **Popo** | Python, 4B 模型 | Pipeline (via sidecar) | HTTP |
| **Frontend** | React, TypeScript | 用户 | 渲染 |

---

## 十四、技术债务清单

| # | 债务 | 严重性 | 修复方案 |
|---|------|--------|---------|
| 1 | chem_validate.rs 与 core/chem.rs 重叠 | 中 | 合并到 chem.rs |
| 2 | vector_store.rs 退化为 15 行 | 低 | 内联到 lance_store.rs |
| 3 | 多个 std::sync::Mutex 在 async 上下文 | 高 | 迁移到 tokio::sync::Mutex |
| 4 | TODO 有 2 条过时条目 | 低 | 清理 |
| 5 | LanceDB protoc 构建依赖重 | 中 | 锁定版本，准备 FTS5 回退 |
| 6 | chematic git 依赖无 tag | 中 | 锁定到特定 commit |
| 7 | Python sidecar 单进程无连接池 | 中 | 添加连接池 + 优雅降级 |
| 8 | 无结构化 tracing | 高 | 新增 observability.rs |
| 9 | 无成本追踪 | 中 | 新增 BudgetEnforcer |
| 10 | 27 分钟管线瓶颈 | 高 | LLM 调用并行化 |

---

## 十五、实施路线图

### Phase 1: 骨架加固（本周）
- [ ] chematic API 编译验证 + 锁定 commit
- [ ] chem_validate.rs 合并到 chem.rs
- [ ] 清理过时 TODO
- [ ] Mutex → tokio::sync::Mutex 迁移

### Phase 2: 管线优化（本月）
- [ ] LLM 调用并行化（27min → 5min）
- [ ] 提取准确率基准测试
- [ ] 分子指纹持久化（ECFP4 BLOB）
- [ ] MinerU-Popo 图文关联集成

### Phase 3: 可观测性（本季度）
- [ ] observability.rs — 结构化 tracing
- [ ] BudgetEnforcer — 成本追踪
- [ ] Episodes 情景记忆
- [ ] Agent 输出接地检查

### Phase 4: 分子表示增强（下季度）
- [ ] MoleCode 双轨表示
- [ ] 分子描述符 Rust 化（schematic-chem）
- [ ] SAR/MCS Rust 化（schematic-smarts）
- [ ] 标题层次 Popo 替换

---

## 十六、架构评审检查清单

- [ ] 每个跨层调用有 trace_id 传播？
- [ ] 每个 LLM 调用有 token/cost 记录？
- [ ] 每个文件写入在 assert_within_root 内？
- [ ] 每个化学验证有 Chematic + RDKit 双路径？
- [ ] 每个 Agent 决策有审计日志？
- [ ] 每个存储操作有崩溃恢复机制？
- [ ] 每个外部依赖有版本锁定和回退方案？
