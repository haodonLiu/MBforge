# LiteParse Library Usage

> Source: https://developers.llamaindex.ai/liteparse/guides/library-usage/
> Generated: 2026-05-30

## Rust Usage

Add `liteparse` to your `Cargo.toml`:

```toml
[dependencies]
liteparse = "2"
tokio = { version = "1", features = ["rt-multi-thread", "macros"] }
```

### Parsing a Document

```rust
use liteparse::{LiteParse, LiteParseConfig};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let parser = LiteParse::new(LiteParseConfig::default());
    let result = parser.parse("document.pdf").await?;

    // Full document text
    println!("{}", result.text);

    // Per-page data
    for page in &result.pages {
        println!("Page {}: {} text items", page.page_number, page.text_items.len());
    }
    Ok(())
}
```

### Parsing from Bytes

Use `PdfInput::Bytes` when you have the PDF in memory:

```rust
use liteparse::{LiteParse, LiteParseConfig};
use liteparse::types::PdfInput;

let parser = LiteParse::new(LiteParseConfig::default());
let pdf_bytes = std::fs::read("document.pdf")?;
let result = parser.parse_input(PdfInput::Bytes(pdf_bytes)).await?;
```

### Configuration

Override only the fields you need:

```rust
use liteparse::{LiteParse, LiteParseConfig, OutputFormat};

let config = LiteParseConfig {
    ocr_enabled: true,
    ocr_language: "fra".to_string(),
    dpi: 300.0,
    target_pages: Some("1-10".to_string()),
    output_format: OutputFormat::Json,
    password: Some("secret".to_string()),
    ..Default::default()
};
let parser = LiteParse::new(config);
```

### Screenshots

Generate page images as PNG bytes:

```rust
let parser = LiteParse::new(LiteParseConfig::default());
let screenshots = parser.screenshot("document.pdf", None).await?;

for shot in &screenshots {
    println!("Page {}: {}x{}", shot.page_num, shot.width, shot.height);
    // shot.image_bytes contains the raw PNG data
}

// Screenshot specific pages
let shots = parser.screenshot("document.pdf", Some(vec![1, 2, 3])).await?;
```

### Parsing from Bytes (screenshots)

```rust
use liteparse::types::PdfInput;

let pdf_bytes = std::fs::read("document.pdf")?;
let screenshots = parser.screenshot_input(PdfInput::Bytes(pdf_bytes), None).await?;
```

### Custom OCR Engine

Implement the `OcrEngine` trait to plug in your own OCR backend:

```rust
use liteparse::LiteParse;
use liteparse::ocr::OcrEngine;
use std::sync::Arc;

let parser = LiteParse::new(Default::default())
    .with_ocr_engine(Arc::new(my_engine));
```

### Features

| Feature | Default | Description |
|---------|---------|-------------|
| `tesseract` | Yes | Built-in Tesseract OCR via `tesseract-rs`. Disable with `default-features = false` if you only use HTTP OCR or no OCR. |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `TESSDATA_PREFIX` | Path to Tesseract `.traineddata` directory. Also available as `tessdata_path` config option. |

## TypeScript / Node.js Usage

```ts
import { LiteParse } from "@llamaindex/liteparse";
const parser = new LiteParse({ ocrEnabled: true });
const result = await parser.parse("document.pdf");
console.log(result.text);
```

## Python Usage

```python
from liteparse import LiteParse
parser = LiteParse()
result = parser.parse("document.pdf")
print(result.text)
```
