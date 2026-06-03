# MBForge 工作状态记录

> 更新时间: 2026-06-03

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

### ChromaDB Windows 文件锁
- **现象**: `PermissionError: [WinError 32]` 在 tempfile 清理时
- **原因**: ChromaDB SQLite 连接未正确关闭时 Windows 文件锁
- **影响**: KB 集成测试在 Windows 上跳过
- **需要**: 确保 `KnowledgeBase.close()` 在所有退出路径被调用

### 跨语言常量/Config 重复
- `constants.rs` 和 `constants.py` 定义相同常量
- `config.rs` 和 `config.py` 定义相同结构体
- **需要**: codegen 从单一源生成，或保持手动同步

---

## 四、已完成

### 前端 vitest 单测 ✅
- vitest + @testing-library/react + jsdom
- 73 个测试: API (kb/agent/environment/download) + 组件 (Button) + hook (useToast)

## 五、已完成

### 跨语言 codegen ✅
- constants.yaml: 25 个共享常量单一源
- scripts/generate_constants.py: 生成 Rust + Python
- `python scripts/generate_constants.py` 一键同步

## 六、下一步计划

| 优先级 | 任务 | 说明 |
|--------|------|------|
| **P0** | lancedb → sqlite-vec 迁移 | 解决 lancedb 0.30.0 编译阻塞；统一 FTS5+向量到单一 SQLite 文件 | 
| **P1** | JSON 修复换 llm_json crate | `post_process.rs` 自研修复 → `llm_json::repair_json()`，提升 LLM 输出鲁棒性 |
| **P2** | chem_validate 换 rdkit-rs | 消除化学验证的 HTTP 往返；本地 RDKit 验证 + 属性计算 |
| **P2** | semantic_cache 换 moka | 消除 Mutex Send 问题；高性能无锁缓存 |
| **P3** | llm.rs 评估 rig/async-openai | 减少多 provider 维护负担；非紧急 |
| **P3** | PDF 管线 Rust 集成测试 | 需要 Tauri 环境 |

---

## 七、开源替代方案分析记录（2026-06-03）

> 本次分析基于对代码库的全面审查 + Rust/Python/TS 生态调研，找出可直接用现成开源库替代的自研模块。

### 高优先级（ROI 极高）

| # | 自研模块 | 开源替代 | 收益 | 风险 |
|---|---------|---------|------|------|
| 1 | `post_process.rs:605-699` JSON 修复 | `llm_json` crate (oramasearch/llm_json) — Python json_repair 的 Rust 移植 | 处理 trailing commas/unquoted keys/single quotes 等更常见错误 | 极低，API 简单 |
| 2 | `chem_validate.rs` + Python `/chem/validate` | `rdkit-rs` (rdkit-rs.github.io) — RDKit C++ 的 Rust 绑定；或 `chematic` (纯 Rust) | 消除 HTTP 往返、离线可用、可算 MW/LogP/TPSA/指纹 | `rdkit-rs` 需 C++ 编译链；`chematic` 功能尚不完整 |

### 中优先级（ROI 中等）

| # | 自研模块 | 开源替代 | 收益 | 风险 |
|---|---------|---------|------|------|
| 3 | `vector_store.rs` + `lance_store.rs` (LanceDB) | `sqlite-vec` + 自建 RRF；或 `cairn_search` crate | 解决 lancedb 0.30.0 编译阻塞；单一 SQLite 文件更稳定 | 需迁移数据 |
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
  └─ ② sqlite-vec 替换 lancedb（解决当前编译阻塞）

Phase 2（本月）:
  ├─ ③ rdkit-rs 替换 chem 验证 HTTP 层（评估 C++ 编译链）
  └─ ④ moka 替换 semantic_cache（测试缓存命中率）

Phase 3（后续）:
  └─ ⑤ 评估 rig/async-openai 替换 llm.rs（非紧急）
```

---

## 四、Git 提交记录

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
