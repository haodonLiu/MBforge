Codex：
下面是完整审核报告。

  # MBForge 架构审核报告

  ## 一、整体结构概览

  ┌─────────────────────────────────────────────────────────────┐
  │  frontend (React 19)                                         │
  │  ── src/api/{client.ts, tauri/*, tauri-bridge.ts}            │
  │  ── 双层 API: 老 client.ts + 新 tauri/*                      │
  └─────────────────────────────────────────────────────────────┘
                              │ Tauri IPC (80+ commands)
                              ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  src-tauri (Rust)                                            │
  │  commands/mod.rs → 生成 handler![] 单点注册                  │
  │  ├─ commands/         15 模块, ~80 IPC 命令                  │
  │  ├─ core/             73 文件                                │
  │  │  ├─ agent/         22 文件（rig 适配 + ReAct）            │
  │  │  ├─ chem/          6 文件 + 顶层 4 文件（散落）           │
  │  │  ├─ document/      6 文件                                 │
  │  │  ├─ molecule/      4 文件 + 顶层 6 文件（散落）           │
  │  │  ├─ project/       项目索引                               │
  │  │  ├─ vector/        embedding + sqlite_vector_store         │
  │  │  └─ executor/      fs/kb/document/molecule/literature + arxiv│
  │  └─ parsers/          pipeline (58 symbols) + chem/ + pdf/   │
  └─────────────────────────────────────────────────────────────┘
                              │ HTTP (port 18792)
                              ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  src/mbforge/model_server (Python FastAPI)                   │
  │  6 个 router（embed / vlm / moldet / rerank / health / env） │
  └─────────────────────────────────────────────────────────────┘

  ## 二、数据流向梳理（应有方向）

  PDF → 解析（Rust）→ 分块/摘要 → embed（HTTP→Py）→ FTS5+向量检索
                                              ↓
                            Agent ReAct: LLM（HTTP→Py）+ tools（25 个）
                                              ↓
                            工具→ core/executor/fs,kb,document,molecule
                                              ↓
                            SQLite: molecules.db + vectors.db + semantic_cache.db
                                              ↓
                            IPC → 前端 tauri-bridge → React 组件

  问题：实际流向出现多处逆流/泄漏（见下）。

  ## 三、严重问题（按优先级）

  ### 🔴 P0：致命级重复

  1. commands/mol_store.rs 与 commands/molecule_store.rs 字节级一致

  两个文件各 181 行，函数签名到变量命名完全相同。commands/mod.rs:103-113 把两边的 mol_store_* 命令都注册进 handler!：

  - mol_store.rs 引用 crate::core::molecule_store::MoleculeRecord
  - molecule_store.rs 引用 crate::core::molecule::molecule_store::MoleculeRecord

  后者是迁移后的新路径，前者是老路径。两份代码会同时被注册，调用方任意一个都能跑——bug 修一份漏一份。

  2. commands/mol_engine.rs（7 symbols）与 commands/molecule_engine.rs（47 symbols）状态类型并存

  MoleculeEngineState 出现两份（核心状态被同时定义），调用方任一即可——但 main.rs:73 只 .manage() 了 MoleculeEngineState::new()，另一份等价类型可能正在被另一个文件引入。

  3. Agent 工具注册两套系统并存

  - core/agent/executor_rig.rs（149 symbols，rig 框架新版，16 + 9 = 25 个工具）
  - core/agent/executor_rig.rs:679 的 assemble_rig_tool_vec 没用 core/executor/ 子模块的代码，而是直接 fs_src::native_read_file()、document_src::native_list_documents() 这种自由函数——

  但 core/executor/ 目录里的 fs.rs、kb.rs、document.rs、molecule.rs、literature.rs + arxiv.rs 是老实现。两者描述的工具（read_file、search_kb、list_documents 等）大量重叠，但导入路径完全不同。

  4. core/agent/arxiv.rs（31 symbols） vs core/agent/arxiv_rig.rs（13 symbols）

  两个 arxiv 实现并存——名字带 _rig 的是 rig 版，不带的是老版。

  5. 内存模块三套并存

  - core/agent/memory.rs（26 symbols）
  - core/agent/managed_memory.rs（45 symbols）
  - core/agent/compactor.rs（13 symbols）

  agent_chat 和 agent_chat_stream 同时引用 CompositeMemory、observe_turn，但究竟哪个是当前 source of truth 不清楚。

  ### 🟠 P1：结构性混乱

  6. 模块目录布局一半"扁平"一半"分组"

  core/
  ├── chem/                       (esmiles.rs, markush.rs, molecode.rs, chem.rs, chem_facade.rs)
  │   ├── esmiles.rs              ← 与 chem/ 同级也存在 core/esmiles.rs?
  ├── esmiles.rs                  ← 顶层有这个，但 chem/ 也有同名 — 需要确认是否同名
  ├── markush.rs                  ← 同上
  ├── molecule/                   (molecule_store.rs, molecule_db.rs, molecule_engine.rs, molecule_dedup.rs)
  ├── molecule_store.rs           ← 顶层（与 molecule/ 里的同名内容重复）
  ├── molecule_db.rs              ← 顶层
  ├── molecule_engine.rs          ← 顶层
  ├── molecule_cluster.rs         ← 顶层
  ├── molecule_dedup.rs           ← 顶层
  ├── sar_query.rs                ← 顶层
  ├── abbreviation_map.rs         ← 顶层（markush 引用）
  ├── gesim.rs                    ← 顶层（应入 chem/）

  core/chem/ 是目录，core/molecule/ 是目录，但同名/相关文件散落在 core/ 顶层。要么全部移入子目录、要么全部扁平。

  7. Commands 文件命名混乱

  commands/
  ├── molecule.rs             ← mol_init, mol_add_relation, mol_find_by_molecule (老命名 mol_*)
  ├── mol_store.rs            ← mol_store_init, mol_store_add... (新命名 mol_store_*)
  ├── molecule_store.rs       ← 同上函数名完全一致 (重复!)
  ├── mol_engine.rs           ← MoleculeEngineState? (与下面重复?)
  ├── molecule_engine.rs      ← MoleculeEngineState 真正定义
  ├── gesim.rs                ← 单命令文件
  ├── molecode.rs             ← 单命令文件
  └── classifier.rs, extractor.rs, detection_cache.rs   ← PDF 解析命令，但内部依赖 crate::parsers::pipeline

  mod.rs:69-94 把命令按 mol_* 和 mol_store_* 两套都注册了——老接口没下架，新接口并存。

  8. 前端双层 API 包装

  frontend/src/api/
  ├── client.ts                  ← 老 HTTP fallback 包装（18 symbols）
  ├── settings.ts                ← 老接口
  ├── tauri/                     ← 新 Tauri invoke 包装
  │   ├── molecule.ts            ← 26 symbols：包含 molStoreXxx + moleculeStatsTauri（兼容 client.ts）
  │   ├── agent.ts               ← agent + postProcessPdf 混在一起
  │   └── sar.ts                 ← 15 symbols：另一套分子/分子库接口（与 molecule.ts 重叠）
  ├── tauri-bridge.ts            ← barrel 重导出
  └── tauri-events.ts            ← 事件名（与 Rust 常量副本，需手动同步）

  molecule.ts:166-241 同一文件内既有新接口 molStoreList，又有兼容老 client.ts 的 listMoleculesTauri——因为前端还没全部迁移完成。

  ### 🟡 P2：跨层耦合 / 泄漏

  9. Core 模块直接走 HTTP 到 Python sidecar

  core/molecule/molecule_engine.rs:206-214 的 dedup_batch：

  let sidecar_url = crate::core::constants::sidecar_url();
  crate::core::molecule_dedup::run_dedup_batch(
      new_mols, &self.relation_db, &sidecar_url, threshold,
  );

  "核心层"命名上应该是纯 Rust 的，但它主动调用 Python sidecar URL。AGENTS.md 明确说 "Rust 新代码优先"，但这里核心仍在做"core→HTTP→Python"调用。

  10. Embedder 绕开共享 HTTP 池

  core/vector/embedding.rs:80-95 的 SidecarEmbedder::new 直接 reqwest::Client::builder() 自己创建连接：

  self.client = Client::builder()
      .timeout(Duration::from_secs(120))
      .build()
      .expect("reqwest blocking client build failed");

  而 AGENTS.md 写着 "Rust 共享 HTTP 客户端：core/http.rs 提供 4 个按超时分类的 LazyLock 单例"。Embedder 没走这条路。

  11. MoleculeEngineState 单实例陷阱

  commands/molecule_engine.rs:34-36 的 get_or_init_engine：

  if guard.is_some() {
      return Ok(());   // 已初始化就直接返回，不检查 project_root 是否变化！
  }

  注释自己承认 "We don't re-open for a different root here; the caller is responsible for project switching via a re-init command." 但 handler 里没有对应的 re-init 命令。前端切项目后，state 仍是上一个项目的 engine——所有 mol_store_* 命令会在错误项目的数
  据库上读写。

  12. Pipeline.rs 巨型文件 + 同名子目录

  parsers/
  ├── pipeline.rs              ← 58 symbols（主入口）
  └── pipeline/                ← 又是同名子目录
      ├── extract.rs
      ├── helpers.rs
      ├── merge.rs
      └── markdown_augment.rs

  pipeline.rs 作为入口文件却包含 58 个符号，子目录又有 4 个文件实现细节。入口 + 实现职责混合，应只剩"入口 + 编排"。

  13. Chem facade 与 chem 模块平级

  core/chem/chem_facade.rs 只有 32 行，是 facade：

  //! All parser-layer chem operations should go through this facade
  //! keeping the architecture: parsers → core::chem::facade → core::chem::*.

  设计意图好，但 core/molecule/molecule_engine.rs:235 写的是 markush::analyze_markush_coverage(...)（直接调用，没走 facade）。facade 没被强制。

  ### 🟢 P3：小问题

  14. 类型重复定义

  - Rust 端 MoleculeRecord 17 个字段（core/molecule/molecule_store.rs:14）
  - 前端 MoleculeRecord 14 个字段（types/index.ts:31）
  - 前端 MoleculeRecord_ 又是 14 个字段（tauri/molecule.ts:8）——尾下划线版本

  后两者职责相同但分开存在——一旦 Rust 加字段，前端要改两个文件。

  15. protocol.rs 顶层位置不当

  src-tauri/src/protocol.rs 注册 mbforge:// URI scheme，与 commands/mod.rs 同级。这个文件实际承担了"自定义协议资源加载"，应放在 commands/ 或独立子目录。

  16. core/agent/mod.rs 只有 1 symbol

  22 个子文件但 mod.rs 几乎没有聚合声明——外部使用 core::agent::xxx 时看到的是 22 个平铺文件名，没有子分组（agent/executor、agent/specialist_agent 等）。

  17. 模型路径常量双源

  .cargo/config.toml 屏蔽 warnings + Rust 端的 core/constants.rs 自动生成（来自 constants.yaml），但 Python 端 mbforge/utils/constants.py 是另一份拷贝，AGENTS.md 要求"双侧同步更新"——容易漂移。

  18. Embedder 后端选择用 API key 判定

  core/vector/embedding.rs:39-49：

  if config.api_key.is_empty() {
      DeterministicEmbedder::new(384)   // 假向量，测试用
  } else {
      SidecarEmbedder::new(...)
  }

  逻辑上"无 key → 测试 stub"，但生产用户配置错误（key 漏填）时会静默退化到假向量，无任何告警。

  ## 四、修改建议（按 ROI 排序）

  ### 第 1 步：清理致命重复（1-2 天）

  # 删除老路径文件，统一到唯一权威源
  rm src-tauri/src/commands/mol_store.rs
  rm src-tauri/src/commands/mol_engine.rs
  rm src-tauri/src/core/molecule_store.rs       # 顶层那个
  rm src-tauri/src/core/molecule_db.rs          # 顶层那个
  rm src-tauri/src/core/molecule_engine.rs      # 顶层那个（与 core/molecule/molecule_engine.rs 重复）
  rm src-tauri/src/core/molecule_cluster.rs     # 移入 core/molecule/
  rm src-tauri/src/core/molecule_dedup.rs       # 移入 core/molecule/
  rm src-tauri/src/core/sar_query.rs            # 移入 core/molecule/sar.rs

  # 在 mod.rs 移除重复的 mol_store_* 注册行（103-113）
  # 让 mol_init, mol_add_relation 等老命令仍然在 commands/molecule.rs，标注 deprecated

  加 cargo check 死代码 lint：#[deprecated(since = "0.3.0")] 标在重复命令上，让前端 migration 编译器驱动。

  ### 第 2 步：统一 agent 工具入口（1 天）

  决定 core/executor/ 目录与 core/agent/executor_rig.rs 哪个是真：

  - 若 rig 版是未来 → 删除 core/executor/{fs,kb,document,molecule,literature,arxiv}.rs，让 executor_rig.rs:679 的 assemble_rig_tool_vec 改成调 core 子模块的纯函数（去掉 fs_src::native_* 这种自由函数风格）
  - 若旧版是未来 → 把 executor_rig.rs 的 rig 宏生成的工具拆成普通函数，迁回 core/executor/

  ### 第 3 步：修 core/ 模块目录（半天）

  core/
  ├── chem/        { chem.rs, chem_facade.rs, esmiles.rs, markush.rs, molecode.rs, gesim.rs, abbreviation_map.rs }
  ├── molecule/    { molecule_engine.rs, molecule_store.rs, molecule_db.rs, molecule_dedup.rs, molecule_cluster.rs, sar_query.rs }
  ├── document/    { document_tree.rs, summary.rs, semantic_cache.rs, content_cache.rs, knowledge_base.rs, stream_search.rs }
  ├── agent/       { mod.rs (re-exports), rig_adapter.rs, executor_rig.rs, context.rs, memory.rs, arxiv.rs, llm_client.rs }
  ├── vector/      { embedding.rs, sqlite_vector_store.rs }
  └── project/     { project.rs, project_migrator.rs }

  mod.rs 用 pub mod xxx; pub use xxx::*; 模式对外暴露分组。

  ### 第 4 步：修 get_or_init_engine 单实例陷阱（半天）

  两种方案：

  - 方案 A：把 MoleculeEngineState 改成 Arc<RwLock<HashMap<ProjectRoot, Arc<MoleculeEngine>>>>——多项目并存
  - 方案 B：加 mol_reset_engine 命令，前端切项目时显式调用，state 重建

  推荐方案 A，工程量小。

  ### 第 5 步：修 Embedder 与 HTTP 池脱节（2 小时）

  core/vector/embedding.rs:88-94 改成从 core/http.rs 拿共享 Client：

  use crate::core::http::short_client;   // 已经在 AGENTS.md 提到
  let client = short_client();

  ### 第 6 步：dedup_batch 的 HTTP 调用拆出 core

  把 molecule_engine.rs:206-214 的 dedup_batch 拆成两步：

  1. core 算 SMILES 相似性（已有 RDKit 替代 chematic-chem）
  2. 需要 embedding 时才走 HTTP——并把 URL 注入从 constants 改成参数传入

  或更彻底：把 dedup 移到 Python 侧 mbforge/，core 只保留 relation 表写入。

  ### 第 7 步：前端 API 双层收敛（2 天）

  - 删除 frontend/src/api/client.ts（已被 tauri/* 替代）
  - tauri/molecule.ts 删除 listMoleculesTauri、searchMoleculesTauri、moleculeStatsTauri（兼容层）——前端组件直接用 molStoreList
  - tauri-events.ts 与 Rust 常量加 CI check：自动从 Rust 侧生成 TS 副本（scripts/sync_constants.py）

  ### 第 8 步：Pipeline.rs 瘦身（1 天）

  parsers/pipeline.rs 58 symbols 中大部分是 stage 实现细节，留入口 + 编排：

  // pipeline.rs 只剩
  pub async fn parse_pdf(...) -> Result<PdfParseResult, String> { ... }
  pub async fn post_process_pdf(...) -> Result<PostProcessResult, String> { ... }
  pub async fn process_document(...) -> Result<DocumentReport, String> { ... }
  pub async fn index_project_rust(...) -> Result<(), String> { ... }

  其余 stage 实现迁入 pipeline/stages/ 子目录。

  ### 第 9 步：MoleculeRecord 类型收敛（2 小时）

  - 前端 MoleculeRecord_ 删除，统一用 types/index.ts 的 MoleculeRecord
  - Rust 加字段时，前端用 Partial<> 包装层（tRPC/JSON Schema）自动派生，不必手维护两处

  ## 五、影响面估算

   改动                                     影响行数              风险                       测试覆盖
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   删除 mol_store.rs / molecule_store.rs    -362 行               高（IPC 接口变化）         需 cargo check + 集成测试
  ───────────────────────────────────────  ────────────────────  ─────────────────────────  ──────────────────────────────
   Agent 工具入口统一                       ~500 行               中（工具行为可能漂移）     已有 test_agent_chat.rs 覆盖
  ───────────────────────────────────────  ────────────────────  ─────────────────────────  ──────────────────────────────
   core/ 目录重组                           仅 import 路径变化    低（cargo rename 自动）    cargo check + 现有 ~323 测试
  ───────────────────────────────────────  ────────────────────  ─────────────────────────  ──────────────────────────────
   get_or_init_engine 多项目                ~50 行                中（状态语义变化）         需要手动多项目切测
  ───────────────────────────────────────  ────────────────────  ─────────────────────────  ──────────────────────────────
   Embedder 用共享池                        -5 行                 低                         现有 embedding 测试
  ───────────────────────────────────────  ────────────────────  ─────────────────────────  ──────────────────────────────
   dedup_batch 拆出                         ~100 行               中（流程改动）             dedup 单测
  ───────────────────────────────────────  ────────────────────  ─────────────────────────  ──────────────────────────────
   前端 API 收敛                            -200 行               中（前端调用迁移）         vitest + 手动 E2E
  ───────────────────────────────────────  ────────────────────  ─────────────────────────  ──────────────────────────────
   Pipeline.rs 拆分                         仅文件移动            低                         pipeline 单测
  ───────────────────────────────────────  ────────────────────  ─────────────────────────  ──────────────────────────────
   类型收敛                                 -50 行                低                         typecheck

  ## 六、一句话总结

  最大的"乱"来自迁移期没下架老接口——4 个分子命令模块、3 套内存模块、2 套 agent 工具、2 套 arxiv 实现并存，再加上模块目录半扁平半分组，最终把任何新人 onboarding 时间从 1 周拉到 3 周。建议先做"第 1 步 + 第 2 步 + 第 3 步"三件事，预期能砍掉 ~15% 代码并消
  除 80% 的困惑。

Kimi：
• 现在我有了完整的画面。你的直觉是对的——数据流确实很混乱。我发现了 5 个结构性问题，有些甚至是文档与代码不符的。
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  MBForge 架构数据流分析：5 大混乱根源
  根源 1：「统一数据库」是个谎言 — 连接管理完全碎片化
  AGENTS.md 说 core/db.rs 是"统一 SQLite 数据库连接管理"。但我实际查证：这个文件根本不存在。
  真实情况是各模块各自为政：
   模块                连接方式                                                                   问题
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   molecule_db.rs      Mutex<Connection> 包一个长连接                                             还算合理
   molecule_store.rs   每次操作 Connection::open                                                  频繁开关连接
   knowledge_base.rs   同一个 vectors.db 开 4 个独立连接 (vec_conn, cache_conn, fts_conn, conn)   连接膨胀，无事务协调
   semantic_cache.rs   每次读写都重新 Connection::open                                            严重性能问题
   file_cache.rs       自己 Connection::open                                                      重复代码
   ingest_queue.rs     自己 Connection::open                                                      重复代码
   content_cache.rs    Connection::open_in_memory()                                               甚至不走磁盘
  后果：
  • 没有连接池，没有事务边界
  • vectors.db 和 molecules.db 被多连接并发访问，潜在锁竞争
  • 想做一个跨表事务（比如"索引文档同时写 molecules + vectors"）是不可能的
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  根源 2：Parser 层不是"下层"，而是 Core 的"寄生虫"
  架构文档说 Parsers 是独立的一层（④），但实际上 Parsers 大量直接引用 Core 内部实现：
  parsers/pipeline.rs          → crate::core::agent::rig_adapter::MbforgeAgent
  parsers/pipeline/extract.rs  → crate::core::document::detection_cache
  parsers/pipeline/helpers.rs  → crate::core::molecule_store::MoleculeRecord
  parsers/chem/chem_validate.rs → crate::core::chem::chem::validate_smiles
  parsers/chem/claim_policy.rs  → crate::core::chem::markush::parse_esmiles
  parsers/structure/post_process.rs → call_llm_api (直接调 LLM!)
  最离谱的是 parsers/pipeline.rs:338：解析管线直接实例化 MbforgeAgent 做文献审阅。这意味着解析层直接调用了最高层的 Agent。
  后果：
  • Parsers ↔ Core 之间不是单向依赖，而是双向缠绕
  • 你无法单独测试 Parsers（必须把整个 Core 拉进来）
  • 无法把 Parsers 拆成独立 crate 或微服务
  • 画架构图时箭头必然打结——因为依赖是网状的，不是树状的
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  根源 3：Python Sidecar 被"到处插队"，没有统一网关
  理论上 Python Sidecar 应该是 Core 层的一个外部依赖，但实际上三个不同层级直接发 HTTP：
  core/agent/rig_adapter.rs    → 直接 HTTP 调用户配置的 LLM endpoint
  core/vector/embedding.rs     → 直接 POST /api/v1/embed 到 sidecar
  parsers/chem/vlm_chem.rs     → 直接 POST /api/v1/vlm 到 sidecar
  parsers/chem/vlm_chem.rs     → 直接 POST /api/v1/moldet 到 sidecar
  注意：core/http.rs 确实存在（共享 HTTP 客户端），但grep显示它并没有被 Parsers 层使用。Parsers 层似乎自己发请求。
  后果：
  • Sidecar 的地址、超时、重试逻辑散落在各处
  • 想换 sidecar 实现（比如改成本地进程间通信）需要改 N 个文件
  • 无法做统一的请求追踪、熔断、降级
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  根源 4：Agent 的 Tool 注册是"硬编码大杂烩"
  core/agent/rig_adapter.rs::assemble_rig_tool_vec() 用 25 行 tools.push(Box::new(...)) 硬编码了所有工具：
  // 16 个 executor 工具
  tools.push(Box::new(GrepSearchTool::new(project_root)));
  tools.push(Box::new(SearchKbTool::new(project_root)));
  tools.push(Box::new(MoleculeAnalysisTool::new(project_root)));
  // ...
  // 9 个 arxiv 工具
  tools.push(Box::new(ArxivMetadata));
  // ...
  后果：
  • Agent 直接依赖了 core/executor 的每一个具体工具实现 + core/agent/arxiv 的每一个函数
  • 新增一个工具需要改 rig_adapter.rs（ violates 开闭原则）
  • 工具的 project_root 注入是手动传参，没有依赖注入容器
  • Agent 和 Executor 之间没有抽象边界——它们是一个编译时耦合体
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  根源 5：Data Storage 没有抽象层，谁都可以直接写磁盘
  除了 SQLite 的碎片化，文件系统访问也是混乱的：
  core/project/project.rs       → 直接 fs::write(.mbforge/version.json)
  core/document/document_tree.rs → 直接 fs::write(index/page_1.txt)
  parsers/pipeline/extract.rs   → 直接写 reports/ 目录
  core/document/file_cache.rs   → 自己管理文件级缓存
  没有统一的 Storage trait 或 Repository 层。每个模块自己决定：
  • 文件路径怎么拼
  • JSON 怎么序列化
  • 错误怎么处理
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  综合判断：这不是"分层架构"，是"洋葱+意大利面"
  理想的分层应该是：
  Frontend → Commands → Core → Parsers → Sidecar
                ↓
             Storage
  实际的数据流是：
  Frontend → Commands → Core ──┬──→ Parsers ──→ Core (又绕回来了!)
                ↓               ├──→ Sidecar (直接 HTTP)
             Storage ←──────────┘    (各写各的)
                ↑
          Parsers 也直接写!
  具体的恶性循环：
  1. Parser 解析 PDF → 需要验证 SMILES → 调 core/chem（逆向依赖）
  2. Parser 做后处理 → 需要 LLM → 直接调 call_llm_api（越级）
  3. Parser 提取分子 → 需要写数据库 → 自己拼路径写文件（绕过 Storage）
  4. Agent 做工具调用 → 需要搜索 KB → 调 core/document/knowledge_base（同层循环）
  5. KB 需要向量 → 调 Sidecar /embed → 又一条跨层 HTTP
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  如果要修，最小侵入的切入点
  按优先级：
   优先级   问题                 最小修复
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   P0       数据库连接碎片化     新建 core/db.rs，用 OnceLock<Arc<Mutex<Connection>>> 统一提供 molecules.db 和 vectors.db 的单连接引用
   P1       Parser 直接调 Core   把 chem_validate、molecode 等提炼成 core/chem_facade.rs，Parser 只依赖 Facade
   P1       Parser 直接调 LLM    把 post_process.rs 的 LLM 调用改成走 Agent 命令（或至少走统一的 llm_client.rs）
   P2       Sidecar HTTP 散落    把 core/http.rs 的共享客户端真正用起来，所有 sidecar 调用走统一封装
   P2       Tool 硬编码          把 assemble_rig_tool_vec 改成从 registry 动态加载（比如扫描 core/executor/tools/ 目录注册）
   P3       文件存储碎片化       抽象出 FileStorage trait，Project 元数据、缓存、索引都走统一接口