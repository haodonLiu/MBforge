# 参考 Wiki 应用 — 提取管线设计笔记

> 来源: 用户提供的 Tauri v2 桌面 Wiki 应用（本地文件读取和索引实现）
> 状态: 已部分采纳到 MBForge

## 核心架构

### 文件提取层（Rust 后端）

| 类型 | 处理方式 |
|------|---------|
| 纯文本 (.md, .txt, .json) | std::fs::read_to_string |
| PDF | pdfium FFI 提取文本 + 图片 |
| DOCX | docx-rs 结构化解析 |
| DOC | office_oxide |
| PPTX/ODF | ZIP + XML |
| XLS/XLSX/ODS | calamine |
| 图片/媒体 | 返回元信息 |

关键设计：
- 所有阻塞 IO 通过 `spawn_blocking` 移到 tokio blocking pool
- PDF 有 `PDFIUM_LOCK` 序列化，防止多线程崩溃
- PDF/Office 有 `.cache/` 缓存（mtime 比对）

### 向量索引层

```
文本 → chunkMarkdown() → fetchEmbedding() → vector_upsert_chunks() → LanceDB
```

- Markdown 感知递归分块：标题 → 段落 → 行 → 句 → 空格 → 硬切
- 不拆分代码块和表格
- 每个 chunk 带 headingPath 面包屑
- chunk 间 overlap（默认 200 字符）
- upsert 语义：先 DELETE 该 page 的所有旧 chunk，再 ADD 新 chunk

### 文件变更监听

- notify crate 监听项目根目录
- file-snapshot.json（MD5 + size + mtime）
- file-change-queue.json 持久化待处理任务
- 应用写入忽略：mark_app_write_path() 防止 watcher 循环

## 已采纳到 MBForge 的设计

| 设计 | MBForge 实现 | 状态 |
|------|-------------|------|
| 文件缓存（mtime+hash） | file_cache.rs | ✅ 已实现 |
| 提取队列+重试 | ingest_queue.rs | ✅ 已创建，待接入 |
| 语义分块 | sections.rs is_semantic_boundary | ✅ 已实现 |
| 图片 VLM 描述 | vlm_chem.rs describe_image_cached | ✅ 已实现 |
| LLM 内容去重 | content_cache.rs | ✅ 已创建，待接入 |

## 未采纳的设计

| 设计 | 原因 |
|------|------|
| 多格式文件提取 | MBForge 聚焦 PDF（药物发现文献主要是 PDF） |
| notify 文件监听 | P1 范围，用户场景不同（手动导入 vs 自动监听） |
| AnyTXT 集成 | 外部依赖重，Agent 工具链已覆盖搜索需求 |
