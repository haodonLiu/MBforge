# pdf-inspector 集成设计

## Context

MBForge 的 PDF 处理流水线当前使用 PyMuPDF 做文本提取、自写 PDFClassifier 做分类。pdf-inspector（Firecrawl 团队开源的 Rust PDF 库）提供更准确的分类（基于 PDF 操作符而非文本密度）和结构化 Markdown 提取。项目正逐步向 Rust 迁移，pdf-inspector 作为 Tauri command 集成。

## 架构

```
Frontend (React)
  └─ invoke('classify_pdf', { path })   ← 索引前预览分类
  └─ invoke('extract_text', { path })   ← 获取结构化 Markdown

src-tauri/src/commands/pdf.rs
  └─ pdf-inspector Rust 原生调用
  └─ classify_pdf() → PdfClassification
  └─ extract_text() → PdfExtraction

Python Pipeline (pdf_parser.py)
  Stage 1:   extract_text() → Markdown（替代 page.get_text()）
  Stage 1.5: classify_pdf() → 分类结果（替代 PDFClassifier）
  Stage 2:   PyMuPDF 图片提取（保留，pdf-inspector 不提供）
  Stage 3-6: LLM/分子/KB（不变）
```

## Rust Command 接口

### classify_pdf

```rust
#[tauri::command]
fn classify_pdf(path: String) -> PdfClassification

struct PdfClassification {
    pdf_type: String,              // "TextBased" | "Scanned" | "Mixed" | "ImageBased"
    confidence: f64,               // 0.0 - 1.0
    page_count: usize,
    pages_needing_ocr: Vec<usize>, // 需要 OCR 的页码（0-indexed）
    text_density_avg: f64,
}
```

替换 `PDFClassifier` 的文本密度阈值判断。pdf-inspector 用 PDF 操作符（Tj/TJ/Do）判断，10-50ms 完成 300+ 页分类。

### extract_text

```rust
#[tauri::command]
fn extract_text(path: String) -> PdfExtraction

struct PdfExtraction {
    markdown: String,          // 结构化 Markdown（含标题、表格、列表）
    page_texts: Vec<String>,   // 每页纯文本（用于分类）
    page_count: usize,
}
```

替换 `page.get_text()` 的纯文本提取。Markdown 格式更适合 LLM 摘要。

## Python Pipeline 集成

### 改动前（Stage 1 + 1.5）

```python
with fitz.open(str(pdf_path)) as doc:
    text_parts = [page.get_text() for page in doc]
    content.text = "\n\n".join(text_parts)
    classifier = PDFClassifier()
    doc_classification = classifier.classify_document_from_pages(text_parts, ...)
```

### 改动后

```python
# 通过 Tauri command 获取 Markdown + 分类
pdf_data = call_tauri_command("extract_text", path=str(pdf_path))
classification = call_tauri_command("classify_pdf", path=str(pdf_path))

if pdf_data and classification:
    # pdf-inspector 路径
    content.text = pdf_data["markdown"]
    content.metadata["classification"] = {
        "is_scanned": classification["pdf_type"] in ("Scanned", "ImageBased"),
        "has_molecules": ...,  # 保留我们的 SMILES 正则检测
        "text_density": classification["text_density_avg"],
        "pages_needing_ocr": classification["pages_needing_ocr"],
    }
else:
    # 降级：PyMuPDF + PDFClassifier（旧路径）
    with fitz.open(str(pdf_path)) as doc:
        text_parts = [page.get_text() for page in doc]
        content.text = "\n\n".join(text_parts)
        classifier = PDFClassifier()
        doc_classification = classifier.classify_document_from_pages(text_parts, ...)
```

### 保留的部分

- **PyMuPDF**：仍用于 Stage 2（图片提取 `page.get_images()`）和 Stage 4（页面渲染 `page.get_pixmap()`）
- **SMILES/化学名检测**：pdf-inspector 不懂分子领域，保留我们的正则检测
- **PDFClassifier**：保留作为 fallback，标记 deprecated

## Fallback 策略

```python
def call_tauri_command(command: str, **kwargs):
    """调用 Tauri command，失败时返回 None."""
    try:
        # 过渡期通过 HTTP 调 Tauri command
        resp = requests.post(f"http://127.0.0.1:{tauri_port}/api/{command}", ...)
        return resp.json()
    except Exception:
        return None  # 降级到旧路径
```

- 浏览器 dev 模式：Tauri 不可用，自动降级
- `OcrConfig.use_pdf_inspector = False`：强制走旧路径

## 配置

`src/mbforge/utils/config.py` — `OcrConfig` 扩展：

```python
@dataclass
class OcrConfig:
    # ... 现有字段 ...
    use_pdf_inspector: bool = True  # 新增：是否使用 pdf-inspector
```

## 文件改动清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src-tauri/src/commands/pdf.rs` | 新建 | pdf-inspector Tauri commands |
| `src-tauri/src/commands/mod.rs` | 修改 | 添加 `pub mod pdf` |
| `src-tauri/src/main.rs` | 修改 | 注册 `commands::pdf` |
| `src-tauri/Cargo.toml` | 修改 | 添加 `pdf-inspector` 依赖 |
| `src-tauri/capabilities/default.json` | 修改 | 添加新 command 权限 |
| `src/mbforge/parsers/pdf_parser.py` | 修改 | Stage 1 + 1.5 改用 Tauri command |
| `src/mbforge/parsers/pdf_classifier.py` | 保留 | 标记 deprecated，fallback 用 |
| `src/mbforge/utils/config.py` | 修改 | OcrConfig 加 `use_pdf_inspector` |
| `frontend/src/api/tauri-bridge.ts` | 修改 | 添加 `classifyPdf()`, `extractText()` |

## 验证

1. `cargo build` — Rust 编译通过
2. `cargo tauri dev` — Tauri 启动，`invoke('classify_pdf', ...)` 返回正确分类
3. `uv run mbforge dev` — Python pipeline 通过 Tauri command 获取 Markdown + 分类
4. 浏览器 dev 模式 — 自动降级到 PyMuPDF + PDFClassifier
5. `OcrConfig.use_pdf_inspector = False` — 强制走旧路径
