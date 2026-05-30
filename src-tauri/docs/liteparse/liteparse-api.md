# LiteParse API Reference

> Source: https://developers.llamaindex.ai/liteparse/api/
> Generated: 2026-05-30

LiteParse — open-source PDF parsing with spatial text extraction, OCR, and bounding boxes.

This crate is the core Rust library. Language bindings for Node.js, Python, and WebAssembly re-export the same types with language-idiomatic wrappers.

## Struct `LiteParseConfig`

Configuration for LiteParse document parsing.

```rust
pub struct LiteParseConfig {
    pub ocr_language: String,
    pub ocr_enabled: bool,
    pub ocr_server_url: Option<String>,
    pub tessdata_path: Option<String>,
    pub max_pages: usize,
    pub target_pages: Option<String>,
    pub dpi: f32,
    pub output_format: OutputFormat,
    pub preserve_very_small_text: bool,
    pub password: Option<String>,
    pub quiet: bool,
    pub num_workers: usize,
}
```

### Fields

| Name | Type | Description |
|------|------|-------------|
| `ocr_language` | `String` | OCR language code (Tesseract format: "eng", "fra", "deu", etc.) |
| `ocr_enabled` | `bool` | Whether OCR is enabled. When true, runs on text-sparse pages and embedded images. |
| `ocr_server_url` | `Option<String>` | HTTP OCR server URL (uses Tesseract if not provided) |
| `tessdata_path` | `Option<String>` | Path to tessdata directory. Falls back to `TESSDATA_PREFIX` env var if not set. |
| `max_pages` | `usize` | Maximum number of pages to parse. |
| `target_pages` | `Option<String>` | Specific pages to parse (e.g., "1-5,10,15-20"). None means all pages. |
| `dpi` | `f32` | DPI for rendering pages (used for OCR and screenshots). |
| `output_format` | `OutputFormat` | Output format (`Json` or `Text`). |
| `preserve_very_small_text` | `bool` | Keep very small text that would normally be filtered out. |
| `password` | `Option<String>` | Password for encrypted/protected documents. |
| `quiet` | `bool` | Suppress progress output. |
| `num_workers` | `usize` | Number of concurrent OCR workers. Defaults to (number of CPU cores - 1), minimum 1. |

## Enum `OutputFormat`

```rust
pub enum OutputFormat {
    Json,
    Text,
}
```

### Variants

- `Json` — Structured JSON output with bounding boxes
- `Text` — Plain text output

## Enum `LiteParseError`

```rust
pub enum LiteParseError {
    Pdf(pdfium::PdfiumError),
    Io(std::io::Error),
    Json(serde_json::Error),
    Image(image::ImageError),
    Ocr(String),
    Conversion(String),
    Config(String),
    Other(String),
}
```

### Variants

| Variant | Description |
|---------|-------------|
| `Pdf(PdfiumError)` | PDFium-level parsing error |
| `Io(io::Error)` | Filesystem I/O error |
| `Json(serde_json::Error)` | JSON serialization error |
| `Image(ImageError)` | Image processing error |
| `Ocr(String)` | OCR engine error |
| `Conversion(String)` | Document format conversion error |
| `Config(String)` | Configuration validation error |
| `Other(String)` | Catch-all error |

## Struct `ParseResult`

Result of parsing a document.

```rust
pub struct ParseResult {
    pub pages: Vec<crate::types::ParsedPage>,
    pub text: String,
}
```

### Fields

| Name | Type | Description |
|------|------|-------------|
| `pages` | `Vec<ParsedPage>` | Parsed pages with projected text layout. |
| `text` | `String` | Full document text, concatenated from all pages. |

## Struct `ScreenshotResult`

Result of rendering a single page screenshot.

```rust
pub struct ScreenshotResult {
    pub page_num: u32,
    pub width: u32,
    pub height: u32,
    pub image_bytes: Vec<u8>,
}
```

### Fields

| Name | Type | Description |
|------|------|-------------|
| `page_num` | `u32` | Page number |
| `width` | `u32` | Image width in pixels |
| `height` | `u32` | Image height in pixels |
| `image_bytes` | `Vec<u8>` | Raw PNG image bytes |

## Struct `LiteParse`

Main LiteParse orchestrator.

```rust
pub struct LiteParse { /* fields omitted */ }
```

### Methods

```rust
pub fn new(config: LiteParseConfig) -> Self
```

Create a new LiteParse instance with the given configuration.

```rust
pub fn with_ocr_engine(self: Self, engine: std::sync::Arc<dyn OcrEngine>) -> Self
```

Override the OCR engine. When set, the engine is used regardless of configuration.

```rust
pub async fn parse(self: &Self, input: &str) -> Result<ParseResult, LiteParseError>
```

Parse a document from a file path, returning structured results.

```rust
pub async fn parse_input(self: &Self, input: PdfInput) -> Result<ParseResult, LiteParseError>
```

Parse a document from either a file path or raw bytes.

```rust
pub async fn screenshot(
    self: &Self,
    input: &str,
    page_numbers: Option<Vec<u32>>
) -> Result<Vec<ScreenshotResult>, LiteParseError>
```

Generate screenshots of document pages as PNG bytes (file path input).

```rust
pub async fn screenshot_input(
    self: &Self,
    input: PdfInput,
    page_numbers: Option<Vec<u32>>
) -> Result<Vec<ScreenshotResult>, LiteParseError>
```

Generate screenshots from a file path or raw bytes.

```rust
pub fn config(self: &Self) -> &LiteParseConfig
```

Get the current configuration.

## Struct `SearchOptions`

Options for searching text items.

```rust
pub struct SearchOptions {
    pub phrase: String,
    pub case_sensitive: bool,
}
```

### Fields

| Name | Type | Description |
|------|------|-------------|
| `phrase` | `String` | Search phrase |
| `case_sensitive` | `bool` | Whether the search is case-sensitive |

## Function `search_items`

Search text items for phrase matches, returning synthetic merged items.

Consecutive text items are concatenated and searched. When a phrase spans multiple items, the result is a single merged item with a combined bounding box and the matched text. Font metadata is taken from the first matched item.

```rust
pub fn search_items(
    items: &[crate::types::TextItem],
    options: &SearchOptions
) -> Vec<crate::types::TextItem>
```

## Struct `TextItem`

Represents a single text item extracted from a PDF page, including its content, position, size, rotation, and font metadata.

```rust
pub struct TextItem {
    pub text: String,
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
    pub rotation: f32,
    pub font_name: Option<String>,
    pub font_size: Option<f32>,
    pub font_height: Option<f32>,
    pub font_ascent: Option<f32>,
    pub font_descent: Option<f32>,
    pub font_weight: Option<i32>,
    pub font_flags: Option<i32>,
    pub text_width: Option<f32>,
    pub font_is_buggy: bool,
    pub mcid: Option<i32>,
    pub fill_color: Option<String>,
    pub stroke_color: Option<String>,
    pub confidence: Option<f32>,
}
```

### Fields

| Name | Type | Description |
|------|------|-------------|
| `text` | `String` | The extracted text content |
| `x` | `f32` | Viewport-space X coordinate (top-left origin, 72 DPI) |
| `y` | `f32` | Viewport-space Y coordinate (top-left origin, 72 DPI) |
| `width` | `f32` | Width of the text item bounding box |
| `height` | `f32` | Height of the text item bounding box |
| `rotation` | `f32` | Rotation in degrees (counter-clockwise, adjusted for page rotation) |
| `font_name` | `Option<String>` | Font name |
| `font_size` | `Option<f32>` | Font size |
| `font_height` | `Option<f32>` | Font size * scale_y from the text matrix — accounts for CTM scaling |
| `font_ascent` | `Option<f32>` | Font ascent |
| `font_descent` | `Option<f32>` | Font descent |
| `font_weight` | `Option<i32>` | Font weight |
| `font_flags` | `Option<i32>` | Font flags |
| `text_width` | `Option<f32>` | Sum of glyph widths (using charcode-based lookup when possible) |
| `font_is_buggy` | `bool` | Whether the font has buggy encoding (private-use codepoints, TT subset, etc.) |
| `mcid` | `Option<i32>` | Marked content ID from the PDF structure tree |
| `fill_color` | `Option<String>` | Fill color as ARGB hex string (e.g. "ff000000") |
| `stroke_color` | `Option<String>` | Stroke color as ARGB hex string |
| `confidence` | `Option<f32>` | OCR confidence score (0.0–1.0). None for native PDF text. |

## Struct `ParsedPage`

Represents a fully parsed page with projected text layout.

```rust
pub struct ParsedPage {
    pub page_number: usize,
    pub page_width: f32,
    pub page_height: f32,
    pub text: String,
    pub text_items: Vec<TextItem>,
}
```

### Fields

| Name | Type | Description |
|------|------|-------------|
| `page_number` | `usize` | Page number (1-indexed) |
| `page_width` | `f32` | Page width in PDF points |
| `page_height` | `f32` | Page height in PDF points |
| `text` | `String` | Full page text |
| `text_items` | `Vec<TextItem>` | Text items with bounding boxes and font metadata |

## `PdfInput` Enum (from `liteparse::types`)

```rust
pub enum PdfInput {
    Path(String),
    Bytes(Vec<u8>),
}
```

### Variants

- `Path(String)` — Parse from a file path
- `Bytes(Vec<u8>)` — Parse from raw bytes
