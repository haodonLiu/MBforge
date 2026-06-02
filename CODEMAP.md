# MBForge 代码逻辑树

> 最后更新: 2026-06-01 | 版本: 0.2.0
> 本文档记录项目每个模块的功能、依赖关系、I/O 和实现状态。
> ⚠️ 本次修订基于实际代码审查，补充了断链、配置不同步和安全风险排查。

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
│ Stage 0: 文本提取 (pipeline/extract.rs)                          │
│   pdf_inspector / mineru / llamaparse / liteparse / uniparser   │
│   classify_and_extract() → DocStructure + Markdown              │
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
  │ Stage 5: LLM 逐 section 处理                             │
  │   post_process.rs → batch prompt → LLM → JSON parse     │
  │   IN: section_text    OUT: StructuredData               │
  └────────────────────┬───────────────────────────────────┘
                      │
  ┌────────────────────┴───────────────────────────────────┐
  │ Stage 6: 分子库持久化                                    │
  │   pipeline.rs → CompoundEntry/ActivityEntry →           │
  │   molecule_store.rs → SQLite + FTS5 batch 写入          │
  │   IN: StructuredData  OUT: saved_count + skipped_count  │
  │   依赖: project_root (显式查找 .mbforge/)                │
  │                                                         │
  │ Stage 7: 合并 + 报告                                    │
  │   report.rs → merge + SAR analysis → DocumentReport     │
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

### 3.1 core/ — 核心层 (21 顶层模块 + 4 子目录)

| 模块 | 功能 | 依赖 | 状态 |
|------|------|------|------|
| `types` | 共享数据类型 Heading/SectionChunk/TreeNode/ExtractionResult | 无 | ✅ |
| `constants` | 应用常量: 版本、路径、模型名、Provider 字符串 | config | ✅ |
| `helpers` | 工具函数: UUID/SHA256/token估算/路径安全 | 无 | ✅ |
| `http` | HTTP 客户端工厂 (15s/30s/120s/300s LazyLock) | 无 | ✅ |
| `config` | 配置结构体: LLM/Embed/Rerank/VLM/OCR + load/save | constants, helpers | ✅ |
| `context` | 分层对话上下文 L0-L3 + token trimming + 文件持久化 | helpers, llm | ✅ |
| `llm` | LLM 客户端: OpenAI/Anthropic 兼容, chat + streaming | config, context, constants | ✅ |
| `tools` | 工具注册表 + OpenAI function-calling schema 导出 | 无 | ✅ |
| `executor/mod.rs` | **工具执行引擎协调入口**: 25+ 工具注册 + 分发 | tools, kb, doc_tree, summary, molecule_engine, project, arxiv | ✅ |
| `executor/fs.rs` | 文件系统工具: grep/list/read/save_text | helpers | ✅ |
| `executor/kb.rs` | 知识库工具: search/search_stream/semantic_cache | knowledge_base, document_tree | ✅ |
| `executor/document.rs` | 文档工具: summarize/extract_sections/get_structure | summary, post_process, knowledge_base | ✅ |
| `executor/molecule.rs` | 分子工具: query/analyze/cluster/similarity | molecule_engine | ✅ |
| `executor/literature.rs` | 文献工具: arxiv_search/pmc_search | arxiv, http | ✅ |
| `agent` | **ReAct Agent**: 多步工具循环 + 流式输出 + 记忆 + Skills | config, constants, context, executor, llm, memory, skills, trajectory, http | ✅ |
| `project` | 项目管理: open/create/scan/CRUD, .mbforge/index.json | constants, helpers, project_migrator | ✅ |
| `project_migrator` | 版本迁移 v0→v1 + 备份恢复 | constants, helpers | ✅ |
| `arxiv` | arXiv/PMC 论文 API 客户端 (10 个工具函数) | 无 | ✅ |
| `markush` | E-SMILES Markush 专利分析: VF2 子结构匹配 + R-group | 无 | ✅ |
| `resource_manager` | 统一资源管理: 11 资源注册 + 路径检查 + GPU 检测 | 无 | ✅ |
| `molecule/` | **分子子目录** (5 模块) | | |
| → `molecule_store` | 分子记录数据库: FTS5 + 属性估算(无 RDKit) | constants, molecule_db | ✅ |
| → `molecule_db` | 分子关系数据库: similar/same_as/scaffold/cluster | constants, helpers | ✅ |
| → `molecule_engine` | 统一分子分析引擎: 聚合 store+relation+cluster+SAR+dedup+markush | molecule_store, molecule_db, molecule_cluster, molecule_dedup, sar_query, markush | ✅ |
| → `molecule_cluster` | 分子聚类: assign/remove/members/list | molecule_db, helpers | ✅ |
| → `molecule_dedup` | 批量去重: exact SMILES match → same_as relation | molecule_db, helpers | ✅ |
| `memory/` | **记忆子目录** (4 模块) | | |
| → `memory` | 6 类结构化记忆: profile/preferences/entities/events/cases/patterns | constants, helpers, context, http | ✅ |
| → `trajectory` | 检索轨迹追踪: .mbforge/trajectory/ | constants, helpers | ✅ |
| → `skills` | 程序性知识管理: Markdown Skill CRUD + 自动创建 | constants, helpers, http | ✅ |
| → `pending` | 暂存提取结果 → .mbforge/extractions/ | constants, types | ✅ 已实现但无调用方（仅模块声明） |
| `document/` | **文档子目录** (5 模块) | | |
| → `knowledge_base` | FTS5 知识库: 章节索引 + 搜索 + 结构/页面查询 | document_tree, vector_store, parsers::sections | ✅ |
| → `vector_store` | SQLite FTS5 向量存储: upsert/search/delete | 无 | ✅ |
| → `document_tree` | 文档结构树 + 页面级文本缓存 | types | ✅ |
| → `summary` | 三层文档摘要 L0/L1/L2 持久化 | constants | ✅ |
| → `semantic_cache` | 三级语义缓存: L1 hash/L2 embedding/L3 prefetch | embedding | ✅ 已接入（executor::kb 通过 search_with_cache 调用） |
| → `stream_search` | 流式搜索: 分批返回 + 增量更新 | 无 | ✅ 已接入（knowledge_base::kb_search_stream） |
| `embedding` | Embedding 生成器: sidecar HTTP + 测试用确定性 embedder | config | ✅ 设计如此 |
| `sar_query` | SAR 分析: 类似物/骨架谱/活性悬崖 | molecule_db | ✅ |

### 3.2 commands/ — Tauri 命令层 (12 模块，由 `mod.rs` 聚合)

| 模块 | Tauri Commands | 依赖 |
|------|---------------|------|
| `mod.rs` | `handler()` 聚合函数: `generate_handler![...]` 注册全部 40+ 命令 | — |
| `agent` | agent_init, agent_create_session, agent_chat, agent_chat_stream, agent_switch_project, agent_clear, agent_destroy_session, agent_get_history | core::agent, config, context |
| `mol_engine` | mol_engine_init, mol_engine_destroy, mol_engine_status | core::molecule_engine |
| `mol_store` | 统一通过 `MoleculeEngineState` 调度: store CRUD + relation + cluster + SAR + dedup (26 个命令) | core::molecule_engine |
| `molecule` | 分子分析命令 (extract/smiles/query) | core::molecule_engine |
| `pdf` | classify_pdf, extract_text | pdf_inspector crate |
| `text_ops` | text_chunk | 无 |
| `classifier` | classify_page, classify_document | core::helpers, parsers::association |
| `extractor` | extract_esmiles_candidates, extract_activities, extract_associated_molecules | core::helpers, parsers::association |
| `file_ops` | open_file, read_text_file, upload_files, delete_file | core::project |
| `project_ops` | open_project, scan_project_files, list_project_documents, get_file_tree | core::project, constants |
| `sidecar` | sidecar_status, sidecar_restart | sidecar |

### 3.3 parsers/ — PDF 解析管线 (19 模块)

| 模块 | 功能 | 依赖 |
|------|------|------|
| `doc_types` | 管线类型: PdfParseResult/StructuredData/DocStructure/ExtractionPlan/PhysicochemicalProperty 等 | commands::classifier, extractor, core::types |
| `pipeline` | **主管线入口**: Stage 0~7 编排 + 专利分子提取 + 范围评估 + 项目级批量索引 (内部拆分到 `pipeline/extract.rs`, `helpers.rs`, `merge.rs`) | 几乎所有 parsers + core |
| `headings` | 多策略 heading 提取: Markdown #/全大写/冒号/编号 | core::types |
| `sections` | 章节构建: headings→tree + 长章节分割 | core::types, headings |
| `association` | 活性提取引擎: 化合物名/IC50/Ki/细胞系/靶点 | core::types |
| `keywords` | 词频关键词 + 实体标签提取 | 无 |
| `post_process` | LLM 后处理: 批分割/prompt/JSON 修复/结构化解析 | types, core::config |
| `images` | PDF 图像提取 (lopdf): JPG/JP2/TIFF/raw | lopdf crate |
| `intent` | 用户意图路由: LLM 文档结构分析 + ExtractionPlan | post_process, types |
| `report` | 报告生成: SAR 分析 + 不确定项 | types, post_process |
| `summary` | LLM 文档摘要生成 (L0+L1) | keywords, post_process |
| `mineru` | MinerU 云 API 客户端 | 无 |
| `uniparser` | UniParser 云 API 客户端 | 无 |
| `llama_parse` | LlamaParse API 客户端 | core::http |
| `liteparse` | LiteParse 本地解析 (PDFium) | liteparse crate |
| `vlm_chem` | VLM 化学结构识别: MolScribe image→SMILES | core::constants, http |
| `molecule_extractor` | **专利命名化合物提取**: 连贯序列检测 + 理化性质关联 + 图像溯源 + VLM 验证 | types, vlm_chem |
| `claim_parser` | **专利 Claims 结构化解析**: 编号/依赖图/类型分类/规范化文本 | 无 |
| `claim_policy` | **专利范围政策匹配**: DirectMention/MarkushOverlap/SemanticMatch + 风险评估 | claim_parser, molecule_extractor |

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
core/executor ─→ core/{helpers, markush, tools, knowledge_base, document_tree, summary, molecule_engine, project, arxiv, http}
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
       ├─→ MoleculeRecord[] → molecule_engine.rs (SQLite)   │
       │    统一入口: MoleculeEngine 聚合 store + relation_db   │
       │    自动持久化: process_document Stage 4.5              │
       │    batch insert, 确定性 mol_id (sha256(name|esmiles)) │
        ├─→ VectorItem[] → knowledge_base.rs (FTS5)           │
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
  .mbforge/molecules.db        ← molecule_engine.rs (统一分子数据库: store + relations)
  .mbforge/memory/agent_context.json ← agent.rs (对话上下文)

读取:
  ~/.config/MBForge/config.json ← config.py / config.rs (全局配置)
  ~/.cache/mbforge/models/      ← resource_manager (模型缓存)
  PDF/MD/TXT 文件               ← parsers + commands
```

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
| 1 | **semantic_cache** | core/semantic_cache.rs (452 行) | ✅ 已接入全部调用方 | `kb_search`/`kb_search_stream` 走 `search_with_cache()`；`executor::native_search_knowledge_base()` 原绕过缓存，已修复为调用 `search_with_cache()` |
| 2 | **stream_search** | core/stream_search.rs (181 行) | ✅ 已接入 Rust + 前端 | `search_with_cache()` 输出流式 chunks；`kb_search_stream` Tauri 命令通过事件推送；前端 `Search.tsx` + `tauri-bridge:kbSearchStream` 流式接收 |
| 3 | **embedding native** | core/embedding.rs | ✅ 设计如此 | Rust 侧通过 HTTP 调 Python sidecar，无需本地 embedding 实现 |
| 4 | **Python MoleculeDatabase** | core/mol_database.py | ⚠️ 双份实现 | Rust `molecule_store.rs` 已完全替代，Python 版仅作 browser fallback |
| 5 | **Python KnowledgeBase** | core/knowledge_base.py | ⚠️ 仅 fallback | 搜索已完全迁移到 Rust FTS5 + semantic_cache；Python ChromaDB 仅作浏览器 dev 模式 fallback |
| 6 | **MolScribe 路径** | molscribe_inference/download.py | ⚠️ 已修复但脆弱 | ResourceManager 路径 → env var → 默认路径三级回退，依赖 ModelScope 缓存布局 |
| 7 | **LLM 多 Provider** | models/anthropic_llm.py | ✅ 已实现 | Anthropic SDK 兼容，但 Rust 侧 llm.rs 也独立实现了 Anthropic 协议 |
| 8 | **arXiv 工具** | core/arxiv.rs (10 个工具) | ✅ 已实现 | 已注册到 executor，通过 data.rag.ac.cn API |
| 9 | **Markush 分析** | core/markush.rs (1040 行) | ✅ 已实现 | check_markush_overlap 工具已注册 |
| 10 | **分子聚类/SAR** | core/molecule_cluster.rs, sar_query.rs | ✅ 已实现 | 17 个 Tauri 命令已注册；2026-06-01 收拢至 `molecule_engine.rs` 统一入口 |
| 11 | **PDFium** | parsers/liteparse.rs, setup.ps1 | ✅ 有安装提示 | `setup/` 验证阶段检测 `vendor/pdfium/` 并给出下载指引；功能可选，不影响主体管线 |
| 12 | **MolDet GPU 门控** | model_server/models/moldet.py | ✅ 有安装提示 | `setup/` 验证阶段检测 GPU 并提示；无 GPU 时前端 MolDet 不可用，其余功能正常 |

### 7.3 三级断链：文档声称 ≠ 实际状态

| # | 声称 | 来源 | 实际状态 |
|---|------|------|---------|
| T1 | "16 路由" | CODEMAP §4.3 / AGENTS.md | 实际注册 16 个 `APIRouter`，chem 的 2 个端点均已有完整实现（探索报告误判为桩） |
| T2 | "~25 组件, ~6,500 行前端" | AGENTS.md | 实际 53 个 `.tsx/.ts` 文件（早期预估偏保守） |
| T3 | "csar/ SAR 分析工具箱" | CODEMAP §4.4, pyproject.toml | 已清理为空占位模块（`__init__.py` 仅注明计划），pyproject.toml 入口已移除 |
| T4 | "ui/ 目录" | `src/mbforge/` 目录存在 | 已删除（空目录，无任何文件） |
| T5 | "parsers/pdf_parser.py" | AGENTS.md 项目结构 | 文件不存在，CODEMAP §4.4 已诚实省略（PDF 解析全在 Rust 侧） |

### 7.4 四级断链：配置/常量不同步

| # | 问题 | Rust 侧值 | Python 侧值 | `.env.template` 值 | 状态 |
|---|------|-----------|-------------|-------------------|------|
| C1 | **LLM 默认模型** | `Qwen/Qwen2.5-7B-Instruct-GGUF` (`constants.rs:15`) | `Qwen/Qwen2.5-7B-Instruct-GGUF` (`constants.py:28`) | `Qwen/Qwen2.5-7B-Instruct-GGUF` (`:31`) | ✅ 三侧一致 |
| C2 | **VLM 默认模型** | — (Rust 侧未使用 VLM) | `mimo-v2.5` (`constants.py:29`) | `mimo-v2.5` (`:55`，已注释) | ✅ Python/Rust 无冲突 |
| C3 | **Embed/Rerank 默认模型** | `DEFAULT_EMBED_MODEL` / `DEFAULT_RERANK_MODEL` (`constants.rs:13-14`) | `Qwen/Qwen3-Embedding-0.6B` / `Qwen/Qwen3-Reranker-0.6B` (`constants.py:26-27`) | `Qwen/Qwen3-Embedding-0.6B` / `Qwen/Qwen3-Reranker-0.6B` (`:40,48`) | ✅ 三侧一致 |
| C4 | **AGENTS.md 模块数** | core 声称 26，实际 31；commands 声称 6，实际 10；API routes 声称 15，实际 16 | — | — | ✅ 已同步 |
| C5 | **PROVIDER_API / PROVIDER_LOCAL** | 缺失（原仅 Python `constants.py:79,81` 有） | 已于 Rust `constants.rs` 补加 `PROVIDER_API` / `PROVIDER_LOCAL` | ✅ 已同步 | ✅ |
| C6 | **OCR_PROVIDER_PYMUPDF** | Python `constants.py:84` 标记已废弃 | 已删除（PyMuPDF 已从项目移除） | ✅ 已清理 | ✅ |
| C7 | **DEFAULT_SIDECAR_PORT** | 仅 Rust `constants.rs:56` 有定义 | 已补加 Python `constants.py`，`cli.py` 中 8 处硬编码改为引用常量 | ✅ 已同步 | ✅ |

### 7.5 安全风险

| # | 位置 | 问题 | 风险等级 |
|---|------|------|---------|
| S1 | `routers/environment.py:44-72` | `check_command` 对用户传入的命令执行 `subprocess.run`，通过 `_ALLOWED_COMMANDS` 白名单限制仅允许 `vina`/`nvidia-smi` | 🟢 低（白名单缓解 + 硬编码调用） |
| S2 | `.env` | API key 明文存储于项目根目录，已被 `.gitignore` 排除但本地仍暴露 | 🟡 中（建议改用系统密钥链或环境变量注入） |

---

### 7.6 待审核事项

> 每次完成代码修改后，在此记录待人工审核项，由人工确认后标记为 ✅ 或移除。

| # | 日期 | 修改人 | 文件 | 问题描述 | 状态 |
|---|------|--------|------|---------|------|
| 1 | 2026-06-01 | AI | AGENTS.md §项目结构 | 移除不存在的 `pdf_parser.py`；标注 `csar/` 为占位模块；更正 AGENTS.md 模块统计（core 26→31, commands 6→10, routes 15→16） | ✅ 已确认 |
| 2 | 2026-06-01 | AI | AGENTS.md, CLAUDE.md, CODEMAP.md | 同步三文件至当前代码库：CLAUDE.md 模块计数更新（commands 11/core 32/parsers 19/routers 16）、待审核移入 CODEMAP；AGENTS.md 项目结构移除不存在的 agent/ 目录、补充 frontend/ 文件清单、修正 typo；CODEMAP.md 表头补齐"状态"列 | ⚠️ 待审核 |
| 3 | 2026-06-01 | AI | CODEMAP.md §2.1, §3.1, §7.2 | 修复内部矛盾：① §2.1 管线图 Stage 5（pending.rs 虚设）重编为 Stage 5 LLM 处理 + Stage 6 分子库持久化；② §3.1 semantic_cache/stream_search 状态从 ⚠️ 更新为 ✅ 并注明接入方式；③ §7.2 #1 semantic_cache 状态同步更新。pending.rs 确认为死代码（仅 mod.rs 声明，无调用方） | ⚠️ 待审核 |

---

## 八、当前进度标记

### 已完成的核心链路 ✅

```
PDF → Rust parsers/pipeline → Stage 0~7 → DocumentReport
                                              ├→ SQLite molecule_store
                                              └→ FTS5 knowledge_base

Agent → Rust agent.rs → ReAct 循环 → 24+ native 工具
                                       ├→ KB 搜索
                                       ├→ 分子查询
                                       ├→ arXiv/PMC
                                       └→ 文件操作

前端 → Tauri invoke → Rust commands → 所有 CRUD 操作
前端 → HTTP → Python sidecar → LLM/Embed/Rerank/VLM/MolDet

资源管理 → Rust resource_manager → 11 资源检查
         → Python resource_manager → ModelScope 下载 + pip 安装
```

### 已有安装提示 🛈

```
embedding native → setup/ 验证阶段显示提示（sidecar HTTP 模式，功能正常）
PDFium         → setup/ 验证阶段检测 vendor/pdfium/ 并给出下载指引
MolDet GPU     → setup/ 验证阶段检测 GPU 并提示；无 GPU 时功能不可用
```

### 修复中的链路 🚧

```
专利分子提取 (pipeline.rs Stage 2a) → 2026-06-01 新增，已接入专利文档处理管线
专利 Claims 解析 (claim_parser.rs) → 2026-06-01 新增，已接入专利文档处理管线
专利范围检测 (claim_policy.rs) → 2026-06-01 新增，已接入专利文档处理管线
```
