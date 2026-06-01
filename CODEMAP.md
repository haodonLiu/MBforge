# MBForge 代码逻辑树

> 最后更新: 2026-06-01 (修订版) | 版本: 0.2.0
> 本文档记录项目每个模块的功能、依赖关系、I/O 和实现状态。
> ⚠️ 本次修订基于实际代码审查，补充了一级断链、三级断链、配置不同步和安全风险。

---

## 一、系统架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    React + Vite + TypeScript (port 5173)         │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────────────┐ │
│  │ Welcome  │ │ProjectView│ │   Chat   │ │ MoleculeLibrary     │ │
│  │ (首页)   │ │ (文档)    │ │ (Agent)  │ │ (分子库)             │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───────┬─────────────┘ │
│       │            │            │                │               │
│  ┌────┴────────────┴────────────┴────────────────┴───────────┐  │
│  │              tauri-bridge.ts  (invoke IPC)                 │  │
│  │              client.ts        (HTTP fallback)              │  │
│  └────────────────────────┬───────────────────────────────────┘  │
└───────────────────────────┼──────────────────────────────────────┘
                            │
┌───────────────────────────┼──────────────────────────────────────┐
│  Tauri v2 Shell           │                                      │
│  ┌────────────────────────┴─────────────────────────────────┐   │
│  │  Rust Core Layer (src-tauri/src/)                         │   │
│  │                                                           │   │
│  │  commands/ (10)     core/ (31)        parsers/ (16)       │   │
│  │  ├─ agent           ├─ agent          ├─ pipeline         │   │
│  │  ├─ molecule        ├─ executor       ├─ post_process     │   │
│  │  ├─ mol_store       ├─ llm            ├─ headings         │   │
│  │  ├─ pdf             ├─ context        ├─ sections         │   │
│  │  ├─ classifier      ├─ project        ├─ images           │   │
│  │  ├─ extractor       ├─ knowledge_base ├─ association      │   │
│  │  ├─ file_ops        ├─ molecule_store ├─ vlm_chem         │   │
│  │  ├─ project_ops     ├─ resource_mgr   ├─ intent           │   │
│  │  ├─ text_ops        ├─ memory         └─ ...              │   │
│  │  └─ sidecar         ├─ skills                             │   │
│  │                     └─ ...                                │   │
│  └───────────────────────────────────────────────────────────┘   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  Python Sidecar (port 18792, spawned by Tauri)            │   │
│  │  FastAPI model_server: 16 routers, 5 model singletons     │   │
│  │  LLM / Embed / Rerank / VLM / MolDet / KB / MolScribe    │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 二、数据流：核心管线

### 2.1 PDF 处理管线 (pipeline.rs — Stage 0~7)

```
PDF 文件
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│ Stage 0: 文本提取                                                │
│   pdf_inspector / mineru / llamaparse / liteparse / uniparser   │
│   IN: PDF path                OUT: Markdown + page_texts[]       │
└──────────────────────┬───────────────────────────────────────────┘
                       │
  ┌────────────────────┴───────────────────────────────────┐
  │ Stage 1: 文档分析 (intent.rs → LLM)                     │
  │   IN: raw_text        OUT: DocStructure (类型/sections) │
  └────────────────────┬───────────────────────────────────┘
                       │
  ┌────────────────────┴───────────────────────────────────┐
  │ Stage 2: 分类 + 结构提取                                │
  │   classifier.rs → page classification                   │
  │   headings.rs → heading extraction                      │
  │   sections.rs → section splitting                       │
  │   IN: raw_text      OUT: Vec<SectionChunk>              │
  └────────────────────┬───────────────────────────────────┘
                       │
  ┌────────────────────┴───────────────────────────────────┐
  │ Stage 3: 图像提取                                       │
  │   images.rs (lopdf) → embedded images                   │
  │   vlm_chem.rs → MolScribe image→SMILES                  │
  │   IN: PDF path      OUT: Vec<ExtractedImage>            │
  └────────────────────┬───────────────────────────────────┘
                       │
  ┌────────────────────┴───────────────────────────────────┐
  │ Stage 4: 分子-文本关联                                  │
  │   association.rs → compound/activity extraction         │
  │   extractor.rs → SMILES candidates + spatial assoc      │
  │   IN: sections+images  OUT: Vec<ExtractionResult>       │
  └────────────────────┬───────────────────────────────────┘
                       │
  ┌────────────────────┴───────────────────────────────────┐
  │ Stage 5: 暂存                                           │
  │   pending.rs → save partial results                     │
  │   IN: ExtractionResults  OUT: pending.json              │
  └────────────────────┬───────────────────────────────────┘
                       │
  ┌────────────────────┴───────────────────────────────────┐
  │ Stage 6: 逐 section LLM 处理                            │
  │   post_process.rs → batch prompt → LLM → JSON parse     │
  │   IN: section_text    OUT: StructuredData               │
  └────────────────────┬───────────────────────────────────┘
                       │
  ┌────────────────────┴───────────────────────────────────┐
  │ Stage 7: 合并 + 报告                                    │
  │   report.rs → merge + SAR analysis → DocumentReport     │
  │   molecule_store.rs → SQLite + FTS5 写入                │
  │   knowledge_base.rs → ChromaDB 向量索引                  │
  │   IN: all results     OUT: report + DB                  │
  └────────────────────────────────────────────────────────┘
```

### 2.2 Agent 对话循环 (agent.rs — ReAct 模式)

```
用户输入
  │
  ▼
┌────────────────────────────────────────────────────────┐
│ Agent::chat() / chat_stream()                          │
│                                                        │
│  context.add_user_message()                            │
│       │                                                │
│       ▼                                                │
│  ┌─── loop (max_iterations) ──────────────────────┐   │
│  │  messages = context.build_messages()            │   │
│  │  response = llm.chat(messages, tool_schemas)    │   │
│  │       │                                         │   │
│  │       ├─ tool_calls 为空 → final_answer → break │   │
│  │       │                                         │   │
│  │       └─ 有 tool_calls →                        │   │
│  │            executor.execute(tc)                  │   │
│  │            context.add_tool_result()             │   │
│  │            trajectory.record_tool()              │   │
│  │            → 继续循环                            │   │
│  └─────────────────────────────────────────────────┘   │
│       │                                                │
│       ▼                                                │
│  clear_tool_results()                                  │
│  spawn_background_tasks()                              │
│    ├─ memory: 每5轮提取一次 → sidecar LLM              │
│    └─ skills: 关键词匹配 → 自动生成 Skill 文件          │
│  save_context() → .mbforge/memory/agent_context.json   │
└────────────────────────────────────────────────────────┘
```

### 2.3 前端路由与后端连接

```
Route          Component           Tauri invoke              HTTP fallback
─────────────────────────────────────────────────────────────────────────
/              Welcome             open_project              —
/project       ProjectView         list_project_documents    —
                                scan_project_files            —
                                index_project_rust            —
/search        Search              kb_search                 —
/chat          Chat                agent_init/create/chat    /api/v1/llm/chat-stream
/molecules     MoleculeLibrary     mol_store_list/search     /api/v1/molecule/*
/workflow      Workflow (Env)      — (HTTP only)             /api/v1/download/*
                                /api/v1/environment/*

SettingsModal  → resources_check (Tauri) + /api/v1/settings (HTTP)
MolDet         → /api/v1/moldet/* (始终 HTTP, GPU 依赖 Python)
```

---

## 三、Rust 模块清单 (src-tauri/src/)

### 3.1 core/ — 核心层 (31 模块, ~9,700 行)

| 模块 | 行数 | 功能 | 依赖 | 状态 |
|------|------|------|------|------|
| `types` | 93 | 共享数据类型 Heading/SectionChunk/TreeNode/ExtractionResult | 无 | ✅ |
| `constants` | 95 | 应用常量: 版本、路径、模型名、Provider 字符串 | config | ✅ |
| `helpers` | 257 | 工具函数: UUID/SHA256/token估算/路径安全 | 无 | ✅ |
| `http` | 59 | HTTP 客户端工厂 (15s/30s/120s/300s LazyLock) | 无 | ✅ |
| `config` | 239 | 配置结构体: LLM/Embed/Rerank/VLM/OCR + load/save | constants, helpers | ✅ |
| `context` | 270 | 分层对话上下文 L0-L3 + token trimming + 文件持久化 | helpers, llm | ✅ |
| `llm` | 416 | LLM 客户端: OpenAI/Anthropic 兼容, chat + streaming | config, context, constants | ✅ |
| `tools` | 134 | 工具注册表 + OpenAI function-calling schema 导出 | 无 | ✅ |
| `executor` | 1007 | **工具执行引擎**: 25+ native 工具 + sidecar 回退 | helpers, markush, tools, kb, doc_tree, summary, mol_store, project, arxiv, http | ✅ |
| `agent` | 413 | **ReAct Agent**: 多步工具循环 + 流式输出 + 记忆 + Skills | config, constants, context, executor, llm, memory, skills, trajectory, http | ✅ |
| `project` | 291 | 项目管理: open/create/scan/CRUD, .mbforge/index.json | constants, helpers, project_migrator | ✅ |
| `project_migrator` | 193 | 版本迁移 v0→v1 + 备份恢复 | constants, helpers | ✅ |
| `knowledge_base` | 192 | FTS5 知识库: 章节索引 + 搜索 + 结构/页面查询 | document_tree, vector_store, parsers::sections | ✅ |
| `vector_store` | 288 | SQLite FTS5 向量存储: upsert/search/delete | 无 | ✅ |
| `document_tree` | 292 | 文档结构树 + 页面级文本缓存 | types | ✅ |
| `embedding` | 207 | Embedding 生成器: sidecar HTTP + 测试用确定性 embedder | config | ⚠️ 仅 sidecar |
| `summary` | 200 | 三层文档摘要 L0/L1/L2 持久化 | constants | ✅ |
| `memory` | 287 | 6 类结构化记忆: profile/preferences/entities/events/cases/patterns | constants, helpers, context, http | ✅ |
| `skills` | 214 | 程序性知识管理: Markdown Skill CRUD + 自动创建 | constants, helpers, http | ✅ |
| `trajectory` | 132 | 检索轨迹追踪: .mbforge/trajectory/ | constants, helpers | ✅ |
| `molecule_db` | 325 | 分子关系数据库: similar/same_as/scaffold/cluster | constants, helpers | ✅ |
| `molecule_store` | 811 | 分子记录数据库: FTS5 + 属性估算(无 RDKit) | constants, molecule_db | ✅ |
| `molecule_cluster` | 134 | 分子聚类: assign/remove/members/list | molecule_db, helpers | ✅ |
| `molecule_dedup` | 150 | 批量去重: exact SMILES match → same_as relation | molecule_db, helpers | ✅ |
| `sar_query` | 270 | SAR 分析: 类似物/骨架谱/活性悬崖 | molecule_db | ✅ |
| `markush` | 1040 | E-SMILES Markush 专利分析: VF2 子结构匹配 + R-group | 无 | ✅ |
| `arxiv` | 287 | arXiv/PMC 论文 API 客户端 (10 个工具函数) | 无 | ✅ |
| `pending` | 156 | 暂存提取结果 → .mbforge/extractions/ | constants, types | ✅ |
| `semantic_cache` | 452 | 三级语义缓存: L1 hash/L2 embedding/L3 prefetch | embedding | ⚠️ 未接入 |
| `stream_search` | 181 | 流式搜索: 分批返回 + 增量更新 | 无 | ⚠️ 未接入 |
| `resource_manager` | 691 | 统一资源管理: 11 资源注册 + 路径检查 + GPU 检测 | 无 | ✅ 新增 |

### 3.2 commands/ — Tauri 命令层 (10 模块, ~1,600 行)

| 模块 | 行数 | Tauri Commands | 依赖 |
|------|------|---------------|------|
| `agent` | 213 | agent_init, agent_create_session, agent_chat, agent_chat_stream, agent_switch_project, agent_clear, agent_destroy_session, agent_get_history | core::agent, config, context |
| `molecule` | 297 | mol_init, mol_add/delete/get_relation, mol_find_by_molecule/similar/same_as, mol_get_stats, mol_assign/remove_cluster, mol_get/list_clusters, mol_find_analogs, mol_scaffold_profile, mol_find_activity_cliffs, mol_dedup_batch | core::molecule_cluster, molecule_db, molecule_dedup, sar_query |
| `mol_store` | 186 | mol_store_init, mol_store_add/list/get/search/delete/stats/search_by_smiles/list_by_doc | core::molecule_store |
| `pdf` | 112 | classify_pdf, extract_text | pdf_inspector crate |
| `text_ops` | 93 | text_chunk | 无 |
| `classifier` | 198 | classify_page, classify_document | core::helpers, parsers::association |
| `extractor` | 272 | extract_esmiles_candidates, extract_activities, extract_associated_molecules | core::helpers, parsers::association |
| `file_ops` | 175 | open_file, read_text_file, upload_files, delete_file | core::project |
| `project_ops` | 230 | open_project, scan_project_files, list_project_documents, get_file_tree | core::project, constants |
| `sidecar` | 33 | sidecar_status, sidecar_restart | sidecar |

### 3.3 parsers/ — PDF 解析管线 (19 模块, ~5,700 行)

| 模块 | 行数 | 功能 | 依赖 |
|------|------|------|------|
| `types` | 270 | 管线类型: PdfParseResult/StructuredData/DocStructure/ExtractionPlan/PhysicochemicalProperty 等 | commands::classifier, extractor, core::types |
| `pipeline` | 1240 | **主管线**: Stage 0~7 编排 + 专利分子提取 + 范围评估 + 项目级批量索引 | 几乎所有 parsers + core |
| `headings` | 122 | 多策略 heading 提取: Markdown #/全大写/冒号/编号 | core::types |
| `sections` | 260 | 章节构建: headings→tree + 长章节分割 | core::types, headings |
| `association` | 331 | 活性提取引擎: 化合物名/IC50/Ki/细胞系/靶点 | core::types |
| `keywords` | 173 | 词频关键词 + 实体标签提取 | 无 |
| `post_process` | 930 | LLM 后处理: 批分割/prompt/JSON 修复/结构化解析 | types, core::config |
| `images` | 354 | PDF 图像提取 (lopdf): JPG/JP2/TIFF/raw | lopdf crate |
| `intent` | 291 | 用户意图路由: LLM 文档结构分析 + ExtractionPlan | post_process, types |
| `report` | 88 | 报告生成: SAR 分析 + 不确定项 | types, post_process |
| `summary` | 80 | LLM 文档摘要生成 (L0+L1) | keywords, post_process |
| `mineru` | 426 | MinerU 云 API 客户端 | 无 |
| `uniparser` | 146 | UniParser 云 API 客户端 | 无 |
| `llama_parse` | 90 | LlamaParse API 客户端 | core::http |
| `liteparse` | 143 | LiteParse 本地解析 (PDFium) | liteparse crate |
| `vlm_chem` | 225 | VLM 化学结构识别: MolScribe image→SMILES | core::constants, http |
| `molecule_extractor` | 630 | **专利命名化合物提取**: 连贯序列检测 + 理化性质关联 + 图像溯源 + VLM 验证 | types, vlm_chem |
| `claim_parser` | 540 | **专利 Claims 结构化解析**: 编号/依赖图/类型分类/规范化文本 | 无 |
| `claim_policy` | 530 | **专利范围政策匹配**: DirectMention/MarkushOverlap/SemanticMatch + 风险评估 | claim_parser, molecule_extractor |

---

## 四、Python 模块清单 (src/mbforge/)

### 4.1 core/ — 核心数据层

| 模块 | 功能 | 依赖 | Rust 对应 |
|------|------|------|-----------|
| `types` | ExtractedContent 中心数据类型 | document_tree | core::types |
| `settings` | 项目级设置 .mbforge/settings.json | constants, helpers | — (Rust 侧独立实现) |
| `project` | 项目管理: open/create/scan/CRUD | settings, constants, helpers | core::project |
| `knowledge_base` | ChromaDB 向量知识库 + 混合搜索 | types, document_tree, summarizer | core::knowledge_base (FTS5) |
| `mol_database` | SQLite 分子数据库 + FTS5 | constants, molecules::schema | core::molecule_store |
| `document_tree` | 文档结构树 + 页面缓存 | constants, helpers | core::document_tree |
| `summarizer` | 三层摘要 L0/L1/L2 + LLM 生成 | types, constants | core::summary |
| `resource_manager` | 统一资源管理: 11 资源 + 下载 + pip | constants | core::resource_manager |

### 4.2 models/ — AI 模型接口

| 模块 | 功能 | 说明 |
|------|------|------|
| `base` | 抽象基类: BaseLLM/BaseEmbedder/BaseReranker/BaseVLM | 所有模型的接口契约 |
| `llm` | OpenAI 兼容 LLM + factory | 支持 stream/tool calling |
| `anthropic_llm` | Anthropic SDK 兼容 LLM | MiniMax 等兼容 Provider |
| `embedding` | SentenceTransformer/Qwen3/API Embedder | MRL 维度截断 + 指令前缀 |
| `rerank` | CrossEncoder/Qwen3 Reranker | yes/no logit 概率评分 |
| `rerank_qwen3` | Qwen3-Reranker 专用实现 | CausalLM 方式 |
| `vlm` | API VLM: OpenAI 兼容视觉模型 | 纯 API 客户端 |

### 4.3 model_server/ — FastAPI 服务 (16 路由)

| 路由 | 前缀 | 端点 | 用途 |
|------|------|------|------|
| `llm` | /api/v1/llm | POST /chat, /chat-stream | LLM 推理 |
| `embed` | /api/v1 | POST /embed | 文本嵌入 |
| `rerank` | /api/v1 | POST /rerank | 结果重排 |
| `vlm` | /api/v1/vlm | POST /describe, /molscribe | VLM + MolScribe |
| `moldet` | /api/v1/moldet | POST /detect-page, /extract-page, /extract-region | 分子检测 |
| `kb` | /api/v1/kb | POST /search, /index-sections | 知识库 |
| `molecule` | /api/v1/molecule | GET /list, /stats, /search | 分子数据库 |
| `project` | /api/v1/project | GET /list, /file-tree | 项目管理 |
| `file` | /api/v1/file | GET /content, /pdf, POST /upload | 文件操作 |
| `settings` | /api/v1/settings | GET /, POST / | 全局配置 |
| `download` | /api/v1/download | GET /models, POST /download/{id} | 模型下载 |
| `chem` | /api/v1/chem | POST /tanimoto, /tanimoto/batch | 化学计算 |
| `environment` | /api/v1/environment | GET /check | 环境检测 |
| `resources` | /api/v1/resources | GET /check, POST /ensure/{id} | 资源管理 |
| `health` | /api/v1 | GET /health | 健康检查 |
| `uniparser` | /api/v1/uniparser | POST /parse, /result | PDF 解析代理 |

### 4.4 parsers/ — Python 解析器

| 模块 | 功能 | Rust 对应 |
|------|------|-----------|
| `molecule/mol_image_pipeline` | MolDetv2+MolScribe 图像分子提取 | parsers::vlm_chem (部分) |
| `molecule/molscribe` | MolScribe 门面模块 | — |
| `molecule/molscribe_inference` | MolScribe 推理引擎 (encoder-decoder) | — |
| `molecule/coords` | PDF↔图像坐标转换 | parsers::images (部分) |
| `molecule/extraction_result` | 分子提取结果数据契约 | core::types::ExtractionResult |

---

## 五、依赖关系图

### 5.1 Rust 内部依赖 (→ 表示 "依赖于")

```
main.rs ─→ commands::{agent, molecule, mol_store}, sidecar
sidecar ─→ (standalone, 管理 Python 进程)

core/agent ─→ core/{config, constants, context, executor, llm, memory, skills, trajectory, http, helpers}
core/executor ─→ core/{helpers, markush, tools, knowledge_base, document_tree, summary, molecule_store, project, arxiv, http}
core/llm ─→ core/{config, context, constants}
core/context ─→ core/{helpers, llm}
core/knowledge_base ─→ core/{document_tree, vector_store}, parsers::sections
core/molecule_store ─→ core/{constants, molecule_db}
core/resource_manager ─→ (standalone, 无内部依赖)

parsers/pipeline ─→ commands/{classifier, extractor, text_ops}
                   ─→ parsers/{types, headings, sections, post_process, intent, vlm_chem, images, report, uniparser, mineru, llama_parse, liteparse, molecule_extractor, claim_parser, claim_policy}
                   ─→ core/{knowledge_base, http, constants}
parsers/molecule_extractor ─→ parsers/{types, vlm_chem}
parsers/claim_parser ─→ (standalone, 无内部 Rust 依赖)
parsers/claim_policy ─→ parsers/{claim_parser, molecule_extractor}
```

### 5.2 Rust ↔ Python 连接

```
Rust sidecar.rs ──spawn──→ Python uvicorn (port 18792)
                ──health──→ GET /api/v1/health

Rust agent.rs ──LLM──→ POST /api/v1/llm/chat
              ──memory──→ POST /api/v1/llm/chat (记忆提取)
              ──skills──→ POST /api/v1/llm/chat (Skill 创建)

Rust pipeline.rs ──index──→ POST /api/v1/kb/index-sections
Rust vlm_chem.rs ──SMILES──→ POST /api/v1/vlm/molscribe
Rust executor.rs ──fallback──→ POST /api/v1/tools/call (sidecar 回退)
Rust resource_manager.rs ──python pkg──→ subprocess "python -c import X"
```

### 5.3 前端 ↔ 后端连接

```
Frontend ──Tauri invoke──→ Rust commands (主路径)
         ──HTTP fetch────→ Python sidecar (回退 + MolDet/下载/设置)
         ──SSE stream────→ Python sidecar (LLM 流式 + 模型下载进度)

连接模式:
  Desktop 模式: isTauriAvailable() → invoke()
  浏览器模式:  !isTauriAvailable() → fetch()
  MolDet:      始终 HTTP (GPU 依赖 Python)
  下载:        始终 HTTP (ModelScope SDK 依赖 Python)
  设置:        始终 HTTP (配置文件由 Python 管理)
```

---

## 六、I/O 规格

### 6.1 核心数据类型流转

```
PDF path
  │
  ▼
PdfParseResult ──────────────────────────────────────────────┐
  ├─ raw_text: String                                        │
  ├─ classification: DocumentClassification                  │
  ├─ page_texts: Vec<String>                                 │
  ├─ headings: Vec<Heading>                                  │
  ├─ sections: Vec<SectionChunk>                             │
  ├─ images: Vec<ExtractedImage>                             │
  ├─ esmiles: Vec<String>                                    │
  └─ parser_used: String                                     │
       │                                                     │
       ▼                                                     │
StructuredData ← post_process.rs (LLM)                      │
  ├─ metadata: DocumentMetadata                              │
  ├─ summary: String                                         │
  ├─ compounds: Vec<CompoundEntry>                           │
  │   ├─ name / esmiles / category / description             │
  │   ├─ physicochemical_props (新增): IC50/mp/logP/...      │
  │   ├─ related_images (新增): Vec<String> 关联图像文件名   │
  │   ├─ vlm_verified_esmiles (新增): VLM 交叉验证结构       │
  │   └─ page_location (新增): Option<usize> 页码            │
  ├─ activities: Vec<ActivityEntry>                          │
  ├─ key_findings: Vec<FindingEntry>                         │
  └─ uncertain_items: Vec<UncertainItem>                     │
       │                                                     │
       ▼                                                     │
DocumentReport ← report.rs (merge)                           │
  ├─ data: StructuredData                                    │
  ├─ sar_analysis: String                                    │
  └─ report_markdown: String                                 │
       │                                                     │
       ├─→ MoleculeRecord[] → molecule_store.rs (SQLite)     │
       ├─→ VectorItem[] → knowledge_base.rs (ChromaDB)       │
       └─→ DocumentSummary → summary.rs (L0/L1/L2)           │
                                                             │
ExtractionResult ← association.rs (图像分子)                  │
  ├─ esmiles: String                                         │
  ├─ source: "image" | "text"                                │
  ├─ moldet_conf / scribe_conf                               │
  ├─ bbox_pdf: (f64,f64,f64,f64)                             │
  └─ page_idx: usize                                         │
       │                                                     │
       └─→ pending.rs → .mbforge/extractions/ ←──────────────┘
```

### 6.2 文件系统 I/O

```
写入:
  .mbforge/index.json          ← project.rs (文档索引)
  .mbforge/settings.json       ← settings.py (项目设置)
  .mbforge/memory/             ← memory.rs (6 类记忆 JSON)
  .mbforge/skills/*.md         ← skills.rs (Markdown 技能)
  .mbforge/trajectory/         ← trajectory.rs (检索轨迹)
  .mbforge/summaries/          ← summary.rs (L0/L1/L2 摘要)
  .mbforge/extractions/        ← pending.rs (暂存提取)
  .mbforge/pages/{doc_id}/     ← document_tree.rs (页面文本)
  .mbforge/doc_trees.json      ← document_tree.rs (结构树)
  .mbforge/kb/sections.db      ← vector_store.rs (FTS5 索引)
  .mbforge/molecules.db        ← molecule_store.rs (分子数据库)
  .mbforge/memory/agent_context.json ← agent.rs (对话上下文)

读取:
  ~/.config/MBForge/config.json ← config.py / config.rs (全局配置)
  ~/.cache/mbforge/models/      ← resource_manager (模型缓存)
  PDF/MD/TXT 文件               ← parsers + commands
```

---

## 七、断链功能 (承诺但未连贯)

### 7.1 一级断链核实

| # | 功能 | 位置 | 状态 | 详情 |
|---|------|------|------|------|
| L1-1 | **csar CLI 入口** | `pyproject.toml` | ✅ 无此问题 | pyproject.toml 中无 csar 入口条目（grep 0 匹配），csar/ 仅为空占位模块 |
| L1-2 | **agent_manager 导入** | `model_server/main.py` | ✅ 无此问题 | 实际代码无此导入（grep 0 匹配），探索报告误报 |
| L1-3 | **chem 路由** | `routers/chem.py` | ✅ 已实现 | 两个端点有完整 RDKit Morgan 指纹 + Tanimoto 实现；`_RDKIT_AVAILABLE` 拼写正确；RDKit 未安装时优雅降级 |
| L1-4 | **pdf_parser.py** | `src/mbforge/parsers/` | ✅ 设计如此 | PDF 解析全在 Rust 侧（parsers/pipeline.rs），Python 侧不需要 pdf_parser.py |

### 7.2 二级断链：CODEMAP 已知的断链（状态核实）

| # | 功能 | 承诺位置 | 当前状态 | 断链原因 |
|---|------|---------|---------|---------|
| 1 | **semantic_cache** | core/semantic_cache.rs (452 行) | ✅ 已接入 | L1 hash 缓存接入 kb_search，重复查询直接返回；cosine 已修复为真正余弦相似度 |
| 2 | **stream_search** | core/stream_search.rs (181 行) | ✅ 已接入 | kb_search_stream 通过 Tauri 事件分批推送；前端 Search.tsx 已改为流式接收 |
| 3 | **embedding native** | core/embedding.rs | ⚠️ 仅 sidecar 模式 | `SidecarEmbedder` 通过 HTTP 调 Python，无本地 Rust embedding |
| 4 | **Python MoleculeDatabase** | core/mol_database.py | ⚠️ 双份实现 | Rust `molecule_store.rs` 已完全替代，Python 版仅作 browser fallback |
| 5 | **Python KnowledgeBase** | core/knowledge_base.py | ⚠️ 仅 fallback | 搜索已完全迁移到 Rust FTS5 + semantic_cache；Python ChromaDB 仅作浏览器 dev 模式 fallback |
| 6 | **MolScribe 路径** | molscribe_inference/download.py | ⚠️ 已修复但脆弱 | ResourceManager 路径 → env var → 默认路径三级回退，依赖 ModelScope 缓存布局 |
| 7 | **LLM 多 Provider** | models/anthropic_llm.py | ✅ 已实现 | Anthropic SDK 兼容，但 Rust 侧 llm.rs 也独立实现了 Anthropic 协议 |
| 8 | **arXiv 工具** | core/arxiv.rs (10 个工具) | ✅ 已实现 | 已注册到 executor，通过 data.rag.ac.cn API |
| 9 | **Markush 分析** | core/markush.rs (1040 行) | ✅ 已实现 | check_markush_overlap 工具已注册 |
| 10 | **分子聚类/SAR** | core/molecule_cluster.rs, sar_query.rs | ✅ 已实现 | 17 个 Tauri 命令已注册 |
| 11 | **PDFium** | parsers/liteparse.rs, setup.ps1 | ⚠️ 需手动安装 | `cargo check` 通过但运行时需要 vendor/pdfium/release/ |
| 12 | **MolDet GPU 门控** | model_server/models/moldet.py | ⚠️ 条件可用 | 无 GPU 时返回 None，前端 MolDet 功能不可用 |

### 7.3 三级断链：文档声称 ≠ 实际状态

| # | 声称 | 来源 | 实际状态 |
|---|------|------|---------|
| T1 | "16 路由" | CODEMAP §4.3 / AGENTS.md | 实际注册 16 个 `APIRouter`，chem 的 2 个端点均已有完整实现（探索报告误判为桩） |
| T2 | "~25 组件, ~6,500 行前端" | CODEMAP §九 | 实际 58 个 `.tsx/.ts` 文件，9,065 行（CODEMAP 统计偏保守） |
| T3 | "csar/ SAR 分析工具箱" | CODEMAP §4.4, pyproject.toml | 已清理为空占位模块（`__init__.py` 仅注明计划），pyproject.toml 入口已移除 |
| T4 | "ui/ 目录" | `src/mbforge/` 目录存在 | 已删除（空目录，无任何文件） |
| T5 | "parsers/pdf_parser.py" | AGENTS.md 项目结构 | 文件不存在，CODEMAP §4.4 已诚实省略（PDF 解析全在 Rust 侧） |

### 7.4 四级断链：配置/常量不同步

| # | 问题 | Rust 侧值 | Python 侧值 | `.env.template` 值 |
|---|------|-----------|-------------|-------------------|
| C1 | **LLM 默认模型** | `Qwen/Qwen2.5-7B-Instruct-GGUF` (`constants.rs`) | `Qwen2.5-7B-Instruct-GGUF` (`constants.py:28`) | `Qwen/Qwen2.5-7B-Instruct` (非 GGUF, `:31`) |
| C2 | **VLM 默认模型** | — (Rust 侧未定义默认值) | `internlm/internlm-xcomposer2-vl-7b` (`constants.py:29`) | `Qwen/Qwen2.5-VL-7B-Instruct` (`:36`) |
| C3 | **Embed/Rerank 默认模型** | `DEFAULT_EMBED_MODEL` / `DEFAULT_RERANK_MODEL` (`constants.rs:13-14`) | 缺失 (`constants.py` 中无对应定义) | — |
| C4 | **AGENTS.md 模块数** | core 声称 26，实际 31；commands 声称 6，实际 10；API routes 声称 15，实际 16（CODEMAP 已反映实际数） | — | — |

### 7.5 安全风险

| # | 位置 | 问题 | 风险等级 |
|---|------|------|---------|
| S1 | `routers/environment.py:46-50` | `check_command` 对用户传入的命令执行 `subprocess.run`，存在命令注入风险 | 🟡 中（已缓解） |
| S2 | `.env` | API key 明文存储于项目根目录，已被 `.gitignore` 排除但本地仍暴露 | 🟡 中 |

---

## 八、当前进度标记

### 已完成的核心链路 ✅

```
PDF → Rust parsers/pipeline → Stage 0~7 → DocumentReport
                                              ├→ SQLite molecule_store
                                              └→ FTS5 knowledge_base

Agent → Rust agent.rs → ReAct 循环 → 25+ native 工具
                                       ├→ KB 搜索
                                       ├→ 分子查询
                                       ├→ arXiv/PMC
                                       └→ 文件操作

前端 → Tauri invoke → Rust commands → 所有 CRUD 操作
前端 → HTTP → Python sidecar → LLM/Embed/Rerank/VLM/MolDet

资源管理 → Rust resource_manager → 11 资源检查
         → Python resource_manager → ModelScope 下载 + pip 安装
```

### 需要打通的链路 ⚠️

```
semantic_cache → 需接入 executor 的 KB 搜索路径
stream_search → 需接入前端 Search 组件的增量渲染
embedding native → 需实现 Rust 本地 embedding (或确认 sidecar 模式足够)
PDFium → 需自动化 setup.ps1 或集成到 resource_manager
```

### 修复中的链路 🚧

```
专利分子提取 (pipeline.rs Stage 2a) → 2026-06-01 新增，已接入专利文档处理管线
专利 Claims 解析 (claim_parser.rs) → 2026-06-01 新增，已接入专利文档处理管线
专利范围检测 (claim_policy.rs) → 2026-06-01 新增，已接入专利文档处理管线
```

---

## 九、模块行数统计

```
Rust (src-tauri/src/):
  core/       31 模块   ~9,700 行
  commands/   10 模块   ~1,600 行
  parsers/    19 模块   ~5,700 行
  main.rs + sidecar.rs + lib.rs  ~400 行
  ─────────────────────────────────
  总计:        62 模块  ~17,400 行

Python (src/mbforge/):
  core/       8 模块    ~3,200 行
  models/     7 模块    ~2,100 行
  model_server/ 16 路由 + 5 models  ~3,500 行
  parsers/    5 模块    ~2,800 行
  molecules/  1 模块    ~400 行
  utils/      6 模块    ~880 行
  ─────────────────────────────────
  总计:        48 模块  ~12,900 行

Frontend (frontend/src/):
  components/  ~58 组件  ~7,500 行
  api/         5 文件    ~900 行
  hooks/       4 文件    ~335 行
  types/       1 文件    ~84 行
  utils/       1 文件    ~65 行
  ─────────────────────────────────
  总计:        58 文件  ~9,065 行

全项目: ~165 模块/文件, ~39,365 行代码
```
