# MBForge PDF 提取流程 (Extraction Workflow)

> 固定版本 — 记录完整的 PDF 提取管线，每个阶段的输入/输出/函数/文件。

---

## 总览

```
PDF 文件
  │
  ├─ Stage 0: 项目扫描 (Project Scan)
  │    输入: 项目根目录路径
  │    输出: DocumentEntry[] (doc_id, path, doc_type, title, indexed)
  │    函数: Project::scan_files()
  │    文件: src-tauri/src/core/project.rs
  │
  ├─ Stage 1: PDF 分类 (PDF Classification)
  │    输入: PDF 文件路径
  │    输出: PdfClassification { pdf_type, confidence, page_count, pages_needing_ocr, ... }
  │    函数: classify_pdf() → pdf_inspector::detect_pdf()
  │    文件: src-tauri/src/commands/pdf.rs
  │    耗时: ~10-50ms (仅检测，不提取文本)
  │
  ├─ Stage 2: 文本提取 (Text Extraction)  ← 根据 Stage 1 结果路由
  │    输入: PDF 文件路径 + parser 选择
  │    输出: (content: String, page_count: usize)
  │    路由逻辑:
  │      - TextBased PDF → pdf_inspector (默认)
  │      - Scanned/ImageBased PDF + MinerU 配置 → MinerU Precise API
  │      - 其他 → 按 parser 参数选择
  │    文件: src-tauri/src/parsers/pipeline.rs
  │
  ├─ Stage 3: 文档分类 (Document Classification)
  │    输入: content 按 "\n\n" 分割的 pages
  │    输出: DocumentClassification { text_density, is_scanned, has_molecular_patterns, pages[] }
  │    函数: classify_document()
  │    文件: src-tauri/src/commands/classifier.rs
  │
  ├─ Stage 4: 文本分块 (Text Chunking)
  │    输入: content (String), chunk_size (默认 512), overlap (默认 128)
  │    输出: TextChunkResult { chunks: Vec<String>, total_chunks }
  │    函数: text_chunk()
  │    文件: src-tauri/src/commands/text_ops.rs
  │
  ├─ Stage 5: 分子提取 (Molecule Extraction)
  │    输入: content (String)
  │    输出: smiles: Vec<String>, activities: Vec<ActivityData>
  │    函数: extract_smiles_candidates() + extract_activities()
  │    文件: src-tauri/src/commands/extractor.rs
  │
  └─ Stage 6: 结果组装 (Result Assembly)
       输出: PdfParseResult { content, classification, chunks, smiles, activities, parser, page_count }
       文件: src-tauri/src/parsers/pipeline.rs
```

---

## 各阶段详细说明

### Stage 0: 项目扫描

**目的**: 扫描项目目录，识别所有支持的文件，生成文档清单。

| 项目 | 值 |
|------|-----|
| 输入 | 项目根目录 `PathBuf` |
| 输出 | `Vec<DocumentEntry>` |
| 函数 | `Project::scan_files()` |
| 文件 | `src-tauri/src/core/project.rs:68` |

**流程**:
1. `walkdir` 遍历项目目录，跳过 `.mbforge/` 元数据目录和隐藏文件
2. 按扩展名匹配 `SUPPORTED_DOC_EXTS` + `SUPPORTED_MOL_EXTS`
3. 新文件: 生成 `doc_id` (UUID)，计算 SHA-256 hash，检测文件类型
4. 已有文件: 检查 hash 是否变化，变化则标记 `indexed = false`
5. 删除不存在的文件条目
6. 保存索引到 `.mbforge/index.json`

**文件类型检测** (`detect_type`):
```
.pdf → "pdf"       .md → "markdown"
.sdf/.mol/.mol2/.pdb/.smi → "molecule"
.csv/.xlsx/.json → "data"      其他 → "text"
```

---

### Stage 1: PDF 分类 (快速检测)

**目的**: 在不提取文本的情况下，快速判断 PDF 是文字型还是扫描型。

| 项目 | 值 |
|------|-----|
| 输入 | PDF 文件路径 `String` |
| 输出 | `PdfClassification` |
| 函数 | `classify_pdf()` → `pdf_inspector::detect_pdf()` |
| 文件 | `src-tauri/src/commands/pdf.rs:38` |
| 耗时 | ~10-50ms |

**输出字段**:
```rust
pub struct PdfClassification {
    pub pdf_type: String,           // "TextBased" | "Scanned" | "Mixed" | "ImageBased"
    pub confidence: f64,            // 0.0-1.0
    pub page_count: usize,
    pub pages_needing_ocr: Vec<usize>,  // 1-indexed 页码
    pub text_density_avg: f64,      // detect-only 模式下为 0.0
    pub has_complex_layout: bool,
    pub has_encoding_issues: bool,
    pub title: Option<String>,
}
```

**pdf_type 含义**:
- `TextBased`: 大部分页面有可提取文本 → 用 `pdf_inspector` 提取即可
- `Scanned`: 几乎全是图片 → 需要 OCR (MinerU)
- `Mixed`: 部分文字部分图片 → 需要 OCR 处理图片页
- `ImageBased`: 纯图片 PDF → 必须 OCR

---

### Stage 2: 文本提取 (4 种 Parser)

**目的**: 从 PDF 中提取结构化 Markdown 文本。

| 项目 | 值 |
|------|-----|
| 输入 | PDF 路径 + parser 选择 |
| 输出 | `(content: String, page_count: usize)` |
| 函数 | `parse_pdf()` 中的 match 分支 |
| 文件 | `src-tauri/src/parsers/pipeline.rs:29` |

#### Parser 1: pdf_inspector (默认)

| 项目 | 值 |
|------|-----|
| 函数 | `pdf_inspector::process_pdf(&path)` |
| 依赖 | `pdf-inspector` crate (Rust 原生) |
| 适用 | TextBased PDF |
| 特点 | 本地执行，无需网络，输出 Markdown |

#### Parser 2: MinerU

| 项目 | 值 |
|------|-----|
| 函数 | `MineruClient::parse_file(&path)` |
| 文件 | `src-tauri/src/parsers/mineru.rs` |
| 适用 | Scanned / ImageBased PDF |
| 依赖 | 环境变量 `MINERU_HOST`, `MINERU_API_KEY` |

**MinerU 双模式**:
- **Agent API** (无 Token): `api_key` 为空时自动使用，≤20 页，IP 限频
  - 流程: 获取上传 URL → PUT 文件到 OSS → 轮询任务状态 → 下载 Markdown
  - 端点: `/api/v1/agent/parse/file`, `/api/v1/agent/parse/{task_id}`
- **Precise API** (JWT Token): `api_key` 非空时使用，支持大文件，VLM OCR
  - 流程: 批量获取上传 URL → PUT 文件 → 轮询 batch → 下载 zip → 解压 Markdown
  - 端点: `/api/v4/file-urls/batch`, `/api/v4/extract-results/batch/{batch_id}`

#### Parser 3: UniParser

| 项目 | 值 |
|------|-----|
| 函数 | `UniParserClient::parse_pdf(&path)` |
| 文件 | `src-tauri/src/parsers/uniparser.rs` |
| 依赖 | 环境变量 `UNIPARSER_HOST`, `UNIPARSER_API_KEY` |

#### Parser 4: LlamaParse

| 项目 | 值 |
|------|-----|
| 函数 | `parse_with_llamaparse_sync()` |
| 文件 | `src-tauri/src/parsers/llama_parse.rs` |
| 依赖 | Python sidecar (`http://127.0.0.1:18792`) |

---

### Stage 3: 文档分类

**目的**: 分析提取出的文本，检测扫描密度和分子模式。

| 项目 | 值 |
|------|-----|
| 输入 | `pages: Vec<String>` (content 按 `\n\n` 分割) |
| 输出 | `DocumentClassification` |
| 函数 | `classify_document()` |
| 文件 | `src-tauri/src/commands/classifier.rs:162` |

**流程**:
1. 按 `\n\n` 分割 content 为 pages
2. 对每页调用 `classify_page()`: 计算 text_density，判断 is_scanned (density < 20)
3. 检测分子模式: SMILES 字母模式 (`is_smiles_like`) + 常见化学名 (aspirin, ibuprofen, ...)
4. 汇总: 平均 text_density，整体 is_scanned (avg < 50)，是否有分子模式

**输出字段**:
```rust
pub struct DocumentClassification {
    pub text_density: f64,           // 平均每页字符数
    pub is_scanned: bool,           // avg_density < 50
    pub has_molecular_patterns: bool,
    pub metadata_hints: Option<serde_json::Value>,
    pub pages: Vec<PageClassification>,
    pub needs_confirmation: bool,   // 混合内容或含分子模式时为 true
}
```

---

### Stage 4: 文本分块

**目的**: 将长文本切分为固定大小的 chunks，优先在自然边界处断开。

| 项目 | 值 |
|------|-----|
| 输入 | `text: String`, `chunk_size: usize` (默认 512), `overlap: usize` (默认 128) |
| 输出 | `TextChunkResult { chunks: Vec<String>, total_chunks }` |
| 函数 | `text_chunk()` |
| 文件 | `src-tauri/src/commands/text_ops.rs:13` |

**算法**:
1. 滑动窗口，窗口大小 = chunk_size
2. 在后半窗口中寻找自然边界: `\n` > `。` (中文句号) > 空格
3. 如果找到边界且在后半段，则在边界处断开
4. 下一个窗口起始 = 当前 end - overlap
5. **关键**: 当 `end == len` 时立即 break，防止无限循环 (已修复的 bug)

---

### Stage 5: 分子提取

**目的**: 从文本中提取 SMILES 候选和活性数据。

| 项目 | 值 |
|------|-----|
| 输入 | `text: String` |
| 输出 | `smiles: Vec<String>`, `activities: Vec<ActivityData>` |
| 函数 | `extract_smiles_candidates()` + `extract_activities()` |
| 文件 | `src-tauri/src/commands/extractor.rs` |

**SMILES 提取** (`extract_smiles_candidates`):
- 正则: `[A-Za-z0-9@.+\-=#$()\[\]\\/%]{4,}`
- 过滤: 长度 > 3，包含有机原子 (C/c/N/n/O/o/S/s/P/p)
- 验证: 需要含键 (=, #)、环 (小写+数字)、手性 (@) 或电荷 ([) 之一
- 注意: Rust 无 RDKit，仅做启发式过滤，不做化学合法性验证

**活性数据提取** (`extract_activities`):
- 正则: `(IC50|EC50|Ki|Kd|pIC50|pEC50)\s*[=:~]\s*([0-9.]+)\s*(nM|µM|uM|μM|mM|M|pM)`
- 输出: 每个匹配包含 activity_type, value, units, context (前后 50 字符)

---

### Stage 6: 结果组装

**目的**: 将所有阶段的结果打包为统一的 `PdfParseResult`。

```rust
pub struct PdfParseResult {
    pub content: String,              // Stage 2: 提取的 Markdown
    pub classification: DocumentClassification,  // Stage 3: 文档分类
    pub chunks: Vec<String>,          // Stage 4: 分块结果
    pub smiles: Vec<String>,          // Stage 5: SMILES 候选
    pub activities: Vec<ActivityData>, // Stage 5: 活性数据
    pub parser: String,               // 使用的 parser 名称
    pub page_count: usize,            // PDF 页数
}
```

---

### Stage 7: LLM 后处理 (Post-Processing)

**目的**: 使用 LLM 对提取结果进行语义级别的整理 — 生成摘要、验证 SMILES、提取结构化信息。

| 项目 | 值 |
|------|-----|
| 输入 | `PdfParseResult` (Stage 0-6 的完整输出) |
| 输出 | `PostProcessResult` |
| 函数 | `post_process_pdf()` → `post_process::post_process()` |
| 文件 | `src-tauri/src/parsers/post_process.rs` |
| 依赖 | LLM API (MiniMax, OpenAI-compatible) |

**流程**:
1. 从环境变量加载 LLM 配置 (`MBFORGE_LLM_BASE_URL`, `MBFORGE_LLM_API_KEY`, `MBFORGE_LLM_MODEL`)
2. 构建 prompt: 将 content (截取前 8000 字符) + SMILES 候选 + 活性数据 打包
3. 调用 `{base_url}/chat/completions` (OpenAI 格式, temperature=0.3)
4. 解析 LLM 返回的 JSON 为 `PostProcessResult`
5. 容错: 处理 markdown 代码块包裹、缺失字段填充默认值

**输出字段**:
```rust
pub struct PostProcessResult {
    pub summary: String,                    // 200字中文摘要
    pub structured_content: String,         // 按主题整理的内容
    pub validated_smiles: Vec<String>,      // 验证后的 SMILES (去假阳性)
    pub activity_records: Vec<ActivityRecord>,  // 结构化活性数据
    pub key_findings: Vec<String>,          // 关键发现
    pub metadata: DocumentMetadata,         // 文档元信息
    pub model: String,                      // 使用的模型
    pub tokens_used: Option<u32>,           // token 使用量
}
```

**ActivityRecord 结构**:
```rust
pub struct ActivityRecord {
    pub compound: String,       // 化合物名称或 SMILES
    pub activity_type: String,  // IC50/EC50/Ki/Kd
    pub value: f64,            // 数值
    pub units: String,          // nM/uM/mM
    pub target: Option<String>, // 靶点名称
    pub context: String,        // 来源上下文
}
```

**DocumentMetadata 结构**:
```rust
pub struct DocumentMetadata {
    pub title: Option<String>,
    pub authors: Vec<String>,
    pub document_type: String,  // patent/paper/review/report
    pub key_compounds: Vec<String>,
    pub key_targets: Vec<String>,
}
```

---

## 前端调用链

```
用户点击 "索引文件"
  │
  ├─ scanProject(root)  →  Python FastAPI /api/v1/project/scan
  │    返回 DocumentEntry[]
  │
  └─ indexProjectStream(root, callback)  →  Python FastAPI /api/v1/project/index-stream
       │
       ├─ 对每个 PDF 调用 parse_pdf (Tauri 命令)
       │    返回 PdfParseResult
       │
        ├─ 存入 SQLite vectors.db 向量库 + FTS5 (via Rust knowledge_base::index_document)
       │
       └─ SSE 流式返回进度
            ├─ { status: "indexing", file, current, total }
            ├─ { status: "file_done", file, molecules }
            ├─ { status: "file_error", file, error }
            └─ { status: "completed", indexed, molecules, total }
```

**前端文件**:
- UI: `frontend/src/components/ProjectView.tsx`
- API Client: `frontend/src/api/client.ts` (HTTP) + `frontend/src/api/tauri-bridge.ts` (Tauri IPC)

---

## Tauri 命令注册

在 `src-tauri/src/main.rs` 的 `generate_handler![]` 中:

```
commands::pdf::classify_pdf          → Stage 1: PDF 分类
commands::pdf::extract_text          → Stage 2: pdf_inspector 提取
commands::text_ops::text_chunk       → Stage 4: 文本分块
commands::classifier::classify_page  → Stage 3: 单页分类
commands::classifier::classify_document → Stage 3: 文档分类
commands::extractor::extract_smiles_candidates → Stage 5: SMILES 提取
commands::extractor::extract_activities → Stage 5: 活性提取
parsers::pipeline::parse_pdf        → 完整管线 (Stage 2-6)
parsers::pipeline::post_process_pdf → LLM 后处理 (Stage 7)
```

---

## 已修复的 Bug

1. **`detect_type` 扩展名匹配** (`project.rs:24`): `path.extension()` 返回 `"pdf"` 而非 `".pdf"`，原代码用 `Some(".pdf")` 匹配导致所有文件被归类为 `"text"`。已移除前导点。

2. **`text_chunk` 无限循环** (`text_ops.rs:52-63`): 当 `end == len` (最后一个 chunk) 时，`start` 被设为 `len - overlap`，导致下一轮 `end` 仍为 `len`，循环永不终止。已添加 `if end == len { break; }`。

---

## 环境变量

```bash
# MinerU OCR (Stage 2, Parser 2)
MINERU_HOST=https://mineru.net        # MinerU API 地址
MINERU_API_KEY=                       # JWT Token (空=Agent模式, 非空=Precise模式)

# UniParser (Stage 2, Parser 3)
UNIPARSER_HOST=https://uniparser.dp.tech/
UNIPARSER_API_KEY=

# LLM 后处理 (Stage 7)
MBFORGE_LLM_BASE_URL=https://api.minimaxi.com/v1   # OpenAI-compatible endpoint
MBFORGE_LLM_API_KEY=                                # LLM API key
MBFORGE_LLM_MODEL=MiniMax-M2.7-highspeed            # 模型名称

# Python Sidecar (Stage 2, Parser 4 + 前端 API)
# 由 Tauri 自动启动，端口 18792
```

---

## 文件清单

| 文件 | 职责 | Stage |
|------|------|-------|
| `src-tauri/src/core/project.rs` | 项目扫描、文件类型检测、索引管理 | 0 |
| `src-tauri/src/commands/pdf.rs` | PDF 分类 (classify_pdf)、文本提取 (extract_text) | 1, 2 |
| `src-tauri/src/parsers/pipeline.rs` | 完整管线 parse_pdf + post_process_pdf | 2-7 |
| `src-tauri/src/parsers/post_process.rs` | LLM 后处理器 (调用 OpenAI-compatible API) | 7 |
| `src-tauri/src/parsers/mineru.rs` | MinerU HTTP 客户端 (Agent + Precise) | 2 |
| `src-tauri/src/parsers/uniparser.rs` | UniParser HTTP 客户端 | 2 |
| `src-tauri/src/parsers/llama_parse.rs` | LlamaParse Python sidecar 客户端 | 2 |
| `src-tauri/src/commands/classifier.rs` | 页面/文档分类，分子模式检测 | 3 |
| `src-tauri/src/commands/text_ops.rs` | 文本分块 (滑动窗口 + 自然边界) | 4 |
| `src-tauri/src/commands/extractor.rs` | SMILES 候选提取、活性数据提取 | 5 |
| `frontend/src/components/ProjectView.tsx` | 索引 UI，文件列表，进度显示 | 前端 |
| `frontend/src/api/client.ts` | HTTP API 客户端 + Rust 包装 (postProcessPdfRust) | 前端 |
| `frontend/src/api/tauri-bridge.ts` | Tauri IPC 桥接 (classify, extract, parse, postProcess) | 前端 |
| `src-tauri/src/main.rs` | Tauri 命令注册 + .env 加载 + Python sidecar 启动 | 入口 |
