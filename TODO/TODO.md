# MBForge 工作状态记录

> 更新时间: 2026-06-04

---

## 一、本轮会话完成的工作

### 1. 全代码审查修复 ✅
- UTF-8 切片 panic: 11 处 `floor_char_boundary()` 修复
- 路径穿越漏洞: `assert_within_root()` 校验
- chat_stream 多步工具丢失: 重写为真正流式 + 多步循环
- FTS5 索引损坏: upsert/delete 前清理旧条目
- 异步阻塞: 新增 `call_llm_api_async()`
- KB 重复初始化: 全局缓存统一
- 正则重复编译: `LazyLock` 静态化
- 死代码/死变量/println!/search_sync 错误处理

### 2. 统一资源管理系统 ✅
- Rust `resource_manager.rs`: 11 资源注册 + 路径检查 + GPU 检测 + Tauri commands
- Python `resource_manager.py`: 下载执行 + pip 安装
- 前端环境 tab: SettingsModal → "环境" section
- 路径解析统一到 Rust 侧，Python 通过 `resolved_paths.json` 读取

### 3. 模型下载精简 ✅
- `_is_essential_file()` 过滤器: 只下载 safetensors + config + tokenizer
- `.bin` 回退: 远程无 safetensors 时自动下载 .bin
- MolScribe: 只下载 .pth + config.json

### 4. semantic_cache + stream_search 接入 ✅
- `kb_search`: L1 hash 缓存 → FTS5 → cache store
- `kb_search_stream`: Tauri 事件分批推送
- 前端 Search.tsx: 流式接收 (first/incremental/complete)
- cosine 相似度修复: 点积 → 真正余弦相似度

### 5. Agent ReAct 循环修复 ✅
- chat_stream 最终回复: 假流式 → 真流式 (`llm.chat_stream`)
- max_iterations 耗尽保护
- 记忆提取响应解析 + Skills JSON 路径修正
- 删除 `register_sidecar_tools` 死代码

### 6. 代码重复合并 ✅
- Python 单例: `ModelSingleton` 泛型工厂 (4 文件)
- Rust `clean_path`: 移入 helpers.rs
- Rust `call_llm_api`: 提取 `parse_llm_response` + `build_llm_body`
- Rust `mol_store_add`: 改用 `get_or_init_db()`
- Rust sidecar: 提取 `log_event()` 辅助函数
- `molecule_db.rs`: 删除重复 molecules schema

### 7. Python 工程化 ✅
- Type hints: 27 个文件补全 (factory 函数 / 核心构造 / 路由返回 / helpers)
- 错误处理: 2 个新异常 + 全局处理器 + download.py/kb.py 改用 raise
- Embedding/Reranker 配置修正: config.json + .env

### 8. 集成测试 ✅
- `test_agent.py`: ResourceManager + 异常层级 (13 个)
- `test_pipeline.py`: ExtractionResult / 坐标 / Molecule / 配置 / 项目 (9 个)
- `test_embed_rerank.py`: Embedding + Reranker 全链路 (13 个)
- `test_real_pdfs.py`: 真实 PDF (CN+US 专利) 全链路 (22 个)
- 总计: 55 passed, 4 skipped

### 9. MolDet 路径修复 ✅
- `_resolve_model_path`: 支持扁平布局 (moldetv2-doc.pt 直接在 models/ 下)
- 删除 GeneralDetector 重复的 override

### 10. 文档更新 ✅
- `CODEMAP.md`: 代码逻辑树 (架构/数据流/模块清单/依赖图/断链标注)

---

## 二、已修复的问题

### MolScribe 模型加载失败 ✅
- **现象**: `RuntimeError: Error(s) in loading state_dict for Encoder: size mismatch`
- **根因**: `molscribe_inference/transformer/` 缺少 `swin_transformer.py`，导致 timm 使用内置 Swin 而非 MolScribe 自定义的 `swin_base` (embed_dim=128, depths=[2,2,18,2])
- **修复**: 从原始仓库复制 `swin_transformer.py`，注册自定义模型到 timm
- **验证**: MolDet (0.955) + MolScribe (0.500) 完整管线通过

## 三、发现但未修复的问题

### SQLite 文件锁（Windows）
- **现象**: `PermissionError: [WinError 32]` 在 tempfile 清理时
- **原因**: SQLite 连接未正确关闭时 Windows 文件锁
- **影响**: 某些集成测试在 Windows 上跳过
- **需要**: 确保数据库连接在退出路径中被正确关闭

### 跨语言常量/Config 重复
- `constants.rs` 和 `constants.py` 定义相同常量
- `config.rs` 和 `config.py` 定义相同结构体
- **需要**: codegen 从单一源生成，或保持手动同步

---

## 四、前端 vitest 单测 ✅

- vitest + @testing-library/react + jsdom
- 73 个测试: API (kb/agent/environment/download) + 组件 (Button) + hook (useToast)

## 五、跨语言 codegen ✅

- constants.yaml: 25 个共享常量单一源
- scripts/generate_constants.py: 生成 Rust + Python
- `python scripts/generate_constants.py` 一键同步

## 六、下一步计划

| 优先级 | 任务 | 说明 | 状态 |
|--------|------|------|------|
| **P0** | chematic API 编译验证 | core/chem.rs 中的 API 调用需验证与实际 crate 版本一致 | ✅ 已完成 |
| **P0** | mol_search_substructure 接入 chem.rs | 子结构搜索命令改用纯 Rust | ✅ 已完成 |
| **P0** | **分子三层表示迁移** | SMILES(事实来源) + E-SMILES(语义插件) + MoleCode(推理层) | 🟧 代码完成，DB 迁移待定 |
| **P0** | **index_project_rust 并行化** | 用 `buffer_unordered(4)` 并行提取 PDF | ✅ 已完成 |
| **P0** | **extract_pdf_workflow** | 独立工作流函数 + CLI + Tauri 命令 | ✅ 已完成 |
| **P1** | 分子指纹持久化 | add_molecule 时自动计算 ECFP4 并存入 fingerprint BLOB | ✅ 已完成 |
| **P1** | **Markush MoleCode 增强** | 缩写展开 + 名称归一化 + Kekule 等价 → `TODO/E-markush-molecode.md` | ✅ 已完成 |
| **P1** | **Markush 可视化** | mermaid.js + Tauri 命令 + MoleculeDisplay 集成 → `TODO/F-markush-visualization.md` | ✅ 已完成 |
| **P1** | **分子交互式编辑** | Ketcher 编辑器 + MoleculeDetailPanel + 理化性质 | ✅ 已完成 |
| **P1** | **分子描述符 Rust 化** | schematic-chem 替代 Python RDKit 的 MW/LogP/TPSA | ✅ 已完成 |
| **P1** | SAR 分析 Rust 化 | schematic-smarts MCS 替代 Python rdFMCS | ⬜ |
| **P1** | **置信度阈值过滤** | 用户可调整最低置信度显示阈值滑块 | ⬜ |
| **P1** | **低置信度项目级提醒** | 检测完成后弹出全局警告（低于阈值的分子数量） | ⬜ |
| **P1** | **SMILES 验证兜底** | 检测后自动调用 chem_validate，无效 SMILES 标红 + 提示编辑 | ⬜ |
| **P1** | **分子状态标记** | overlay 中已确认/已拒绝的分子有视觉区分（绿色/灰色边框） | ⬜ |
| **P1** | **区域重新检测** | overlay 右键菜单"重新检测此区域"调用 extractRegion API | ⬜ |
| **P2** | MOL/SDF 文件解析 | schematic-mol 支持 V2000+V3000 | ⬜ |
| **P2** | JSON 修复换 llm_json crate | 提升 LLM 输出鲁棒性 | ⬜ |
| **P3** | 2D 分子 SVG 渲染 | schematic-depict 生成分子结构图 | ⬜ |
| **P3** | WASM 分子预览 | schematic-wasm 前端实时预览 | ⬜ |

### 分子三层表示迁移详情

> 详见 ARCHITECTURE.md §四

**迁移步骤**（按风险从低到高）：

| # | 步骤 | 工作量 | 风险 | 状态 |
|---|------|--------|------|------|
| 1 | 数据库 schema：加 `smiles` 列，`esmiles` 改 nullable | 小 | 需数据迁移脚本 | ⬜ |
| 2 | 迁移脚本：现有 `esmiles` → 分离为 `smiles` + `esmiles`(nullable) + `tags`(JSON) | 小 | 一次性 | ⬜ |
| 3 | FTS5 重建：从索引 `esmiles` 改为索引 `smiles` | 小 | 重建期间搜索不可用 | ⬜ |
| 4 | Chematic/RDKit 调用点：去掉 `sanitize_esmiles()`，直接用 `smiles` | 中 | 20+ 处需检查 | ⬜ |
| 5 | Agent 工具：新增 `smiles_to_molecode` 转换 | 中 | 依赖 Python sidecar 路由 | ✅ `core/molecode.rs` |
| 6 | 前端：分子详情页增加 MoleCode 图渲染 | 中 | 需 Mermaid 组件 | ⬜ |

**总工作量**：约 2-3 天

---

## 七、开源替代方案分析记录（2026-06-03）

> 本次分析基于对代码库的全面审查 + Rust/Python/TS 生态调研，找出可直接用现成开源库替代的自研模块。

### 高优先级（ROI 极高）

| # | 自研模块 | 开源替代 | 收益 | 风险 |
|---|---------|---------|------|------|
| 1 | `post_process.rs:605-699` JSON 修复 | `llm_json` crate (oramasearch/llm_json) — Python json_repair 的 Rust 移植 | 处理 trailing commas/unquoted keys/single quotes 等更常见错误 | 极低，API 简单 |
| 2 | `chem_validate.rs` + Python `/chem/validate` | **`chematic`** (纯 Rust，已集成) — core/chem.rs 已实现 SMILES 校验/指纹/Tanimoto/子结构搜索 | 消除 HTTP 往返、离线可用、可算 MW/LogP/TPSA/指纹 | API 需验证（git 依赖，未发布 crates.io） |

### 中优先级（ROI 中等）

| # | 自研模块 | 开源替代 | 收益 | 风险 |
|---|---------|---------|------|------|
| 3 | （已删除 LanceDB，改用 SQLite FTS5 + semantic_cache） | — | — |
| 4 | `semantic_cache.rs` (~493 行) | `moka` crate — 高性能并发缓存 | 消除 Mutex Send 问题；无锁；减少 ~400 行自研 | 需适配 disk_persist |
| 5 | `llm.rs` (~516 行) | `async-openai` / `rig` 通用 LLM 框架 | 减少 provider API 变更维护 | 可能引入不需要的抽象 |

### 不建议替代（自研合理）

- `agent.rs` ReAct 循环 — 深度领域定制（分子科学系统提示、25+ 工具、记忆系统）
- `memory/` 记忆系统 — 6 分类结构化记忆是领域设计
- `association.rs` 分子-文本关联 — 领域特定正则引擎，无通用替代品
- `parsers/pipeline.rs` PDF 解析编排 — 已基于多个开源后端，自研的是合理编排层

### 推荐实施顺序

```
Phase 1（本周）:
  ├─ ① llm_json 替换 JSON 修复（cargo add，一行替换）
  └─ ② （LanceDB 已移除，SQLite FTS5 + semantic_cache 已到位）

Phase 2（本月）:
  ├─ ③ rdkit-rs 替换 chem 验证 HTTP 层（评估 C++ 编译链）
  └─ ④ moka 替换 semantic_cache（测试缓存命中率）

Phase 3（后续）:
  └─ ⑤ 评估 rig/async-openai 替换 llm.rs（非紧急）
```

---

## 七、Git 提交记录

```
3a08f39 test(python): 新增 Agent + 管线集成测试 (22 个)
b009005 refactor(python): 错误处理统一 — 异常层级 + 全局处理器
d64adf8 refactor(python): 补全 type hints — 27 个文件
7846039 refactor: molecule_db.rs 删除重复的 molecules schema
a4f3801 refactor: 合并 9 项代码重复
5078b9d refactor: 路径解析统一到 Rust 侧，Python 只读不解析
989de48 fix: 统一 Python/Rust 模型路径解析
b0f878d fix: 修正 embedding 配置 + FutureWarning
7e690f4 docs: 更新 CODEMAP 断链状态 — 修正误报
986a734 feat: 接入 semantic_cache + stream_search，移除 Python 双写
d5d6f63 docs: 新增 CODEMAP.md 代码逻辑树
0e63bba fix(agent): 修复 ReAct 循环 6 项问题
3629aa4 fix: 代码审查修复 — 14 项问题 (Rust/Python/TypeScript)
cf907f1 feat(python): 统一资源管理 + 精简下载 + CLI 环境管理
2edc1f6 feat: Rust 侧统一资源管理器 + 前端环境 tab
705a8aa fix(rust): 全代码审查修复 — UTF-8 panic / 路径穿越 / FTS5 损坏 / chat_stream 多步丢失
```

---

## 八、架构重构 — 化学信息学 Rust 化（2026-06-03）

### 已完成 ✅

| 项目 | 说明 |
|------|------|
| **chematic 集成** | 纯 Rust 化学信息学库（736 测试，ChEMBL 2.9M 100% 通过） |
| **core/chem.rs** | SMILES 校验、ECFP4 指纹、Tanimoto 相似度、VF2 子结构搜索 |
| **三级漏斗全 Rust 化** | Tanimoto 预过滤 → VF2 子图同构 → 零 Python sidecar 调用 |
| **SQLite FTS5 + vectors.db** | 单一 SQLite 存储向量 + BM25，Rust 侧 `document/knowledge_base.rs` 统一管理 |
| **semantic_cache** | SHA-256 查询缓存 + TTL 1小时，取代旧 JSON 方案 |
| **文件内容缓存** | SHA-256 + mtime 两级检查，避免重复 PDF 解析 |
| **代码瘦身** | 净删 ~710 行死代码（SqliteVectorStore、pending.rs 等） |

### chematic 可用能力清单

| 模块 | 能力 | MBForge 用途 |
|------|------|-------------|
| `chematic-core` | Molecule 结构、Kekulization、元素数据 | 分子对象基础 |
| `chematic-smiles` | OpenSMILES 解析/写入、canonical SMILES | SMILES 校验规范化 |
| `chematic-fp` | ECFP4/6、MACCS、AtomPair、Torsion FP、Tanimoto/Dice | 指纹存储+相似度搜索 |
| `chematic-smarts` | SMARTS 解析、VF2 子图同构、MCS | 子结构搜索、SAR 分析 |
| `chematic-chem` | MW/LogP/TPSA/QED/Lipinski/Murcko/BRICS/CIP/VSA/SA | 分子描述符、药物相似性 |
| `chematic-mol` | MOL/SDF V2000+V3000 读写 | 化学文件格式支持 |
| `chematic-depict` | 2D SVG 渲染（CPK 配色、高亮） | 分子结构可视化 |
| `chematic-rxn` | 反应 SMILES/SMIRKS 解析 | 反应路线分析 |
| `chematic-3d` | 3D 坐标生成、UFF 能量最小化、PDB/XYZ | 分子构象 |
| `chematic-perception` | SSSR 环检测、Hückel 芳香性 | 环系分析 |
| `chematic-wasm` | WebAssembly 绑定 | 前端分子预览 |

### 待做 TODO

#### P0 — 当前阻塞
- [ ] **chematic API 编译验证** — core/chem.rs 中的 API 调用需验证与实际 crate 版本一致
- [x] **mol_search_substructure 接入 chem.rs** — molecule.rs 子结构搜索命令改用纯 Rust（✅ 已完成）

#### P2 — 测试修复
- [ ] **file_cache 测试失败** — `test_file_cache_roundtrip` 和 `test_file_cache_mtime_change` 断言失败（既有 bug，非重构引起）
- [ ] **ingest_queue 测试挂起** — `test_queue_enqueue_dequeue` 和 `test_queue_retry` 超时 60s+（疑似异步运行时死锁）
- [ ] **liteparse 测试 ignored** — `test_screenshot_cn_patent` 需要外部服务
- [ ] **pipeline 集成测试 ignored** — `test_extract_images_from_both_patents`、`test_supervised_pipeline_cn_patent`、`test_supervised_pipeline_us_patent` 需要 sidecar 运行

#### P1 — 核心功能 Rust 化
- [ ] **分子指纹持久化** — add_molecule 时自动计算 ECFP4 并存入 fingerprint BLOB
- [ ] **分子描述符 Rust 化** — schematic-chem 替代 Python RDKit 的 MW/LogP/TPSA/QED/Lipinski
- [ ] **SAR 分析 Rust 化** — schematic-smarts MCS 替代 Python rdFMCS.FindMCS
- [ ] **BRICS 分子碎片化** — schematic-chem BRICS 用于分子库多样性分析
- [ ] **Murcko 骨架提取** — 用于 scaffold-based 聚类

#### P2 — 格式支持扩展
- [ ] **MOL/SDF 文件解析** — schematic-mol 支持 V2000+V3000
- [ ] **反应 SMILES 支持** — schematic-rxn 解析反应 SMILES/SMIRKS
- [ ] **3D 坐标生成** — schematic-3d 用于分子构象搜索
- [ ] **PDB/XYZ 格式** — 蛋白质-配体对接准备

#### P3 — 可视化与前端
- [ ] **2D 分子 SVG 渲染** — schematic-depict 生成分子结构图（替代 Python matplotlib）
- [ ] **WASM 分子预览** — schematic-wasm 在前端实时预览分子结构
- [ ] **SMARTS 模式编辑器** — 前端 SMARTS 输入 + 实时匹配反馈

#### Rust 化学库生态参考

> 来源: [Rust 化学计算库指南](https://jishuzhan.net/article/1832075668892946433)

| 库 | 功能 | 与 MBForge 相关性 |
|---|---|---|
| `chemistry-rs` | 化学方程式解析 | 低（不需要方程式） |
| `rust-chem` | 分子结构模拟、反应动力学 | 中（可补充 3D 模拟能力） |
| `periodic-rs` | 元素周期表数据 | 低（chematic-core 已包含） |
| `chemfiles-rs` | PDB/XYZ/MOL2 文件读写 | 高（可替代 schematic-mol 部分功能） |
| `rust-bio-chem` | 生物分子建模、相似性分析 | 中（蛋白质-配体场景） |
| `quantum-rs` | 量子化学计算 | 低（超出 MBForge 范围） |

**结论**: chematic 已覆盖 MBForge 80%+ 的化学信息学需求。`chemfiles-rs` 可作为补充（更丰富的文件格式支持）。其他库暂不需要。
