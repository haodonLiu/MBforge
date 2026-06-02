# MBForge 工作状态记录

> 更新时间: 2026-06-02

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

## 五、下一步计划

| 优先级 | 任务 | 说明 |
|--------|------|------|
| **P2** | 跨语言 codegen | constants.yaml → constants.rs + constants.py |
| **P2** | PDF 管线 Rust 集成测试 | 需要 Tauri 环境 |

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
