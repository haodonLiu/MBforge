# LiteParse Getting Started

> Source: https://developers.llamaindex.ai/liteparse/getting_started/
> Generated: 2026-05-30

Install LiteParse and parse your first document in under a minute.

## Installation

### Rust (CLI binary)
```sh
cargo install liteparse
```

### Node.js / TypeScript
```sh
npm i -g @llamaindex/liteparse
```

### Python
```sh
pip install liteparse
```

### Browser (WASM)
```sh
npm i @llamaindex/liteparse-wasm
```

## Quick Start (CLI)

```sh
# Parse a PDF and print text to stdout
lit parse document.pdf

# Save output to a file
lit parse document.pdf -o output.txt

# Get structured JSON with bounding boxes
lit parse document.pdf --format json -o output.json

# Parse only specific pages
lit parse document.pdf --target-pages "1-5,10,15-20"
```

### Batch Parsing

```sh
lit batch-parse ./pdfs ./outputs
```

### Screenshots

```sh
lit screenshot document.pdf -o ./screenshots
```

## Rust Library Usage (Quick)

Add to `Cargo.toml`:
```toml
[dependencies]
liteparse = "2"
tokio = { version = "1", features = ["rt-multi-thread", "macros"] }
```

Parse a document:
```rust
use liteparse::{LiteParse, LiteParseConfig};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let parser = LiteParse::new(LiteParseConfig::default());
    let result = parser.parse("document.pdf").await?;
    println!("{}", result.text);
    Ok(())
}
```

Screenshots:
```rust
let screenshots = parser.screenshot("document.pdf", None).await?;
for shot in &screenshots {
    println!("Page {}: {}x{}", shot.page_num, shot.width, shot.height);
}
```
