# Tier 1 Rust Conversion — SMILES 提取、PDF 分类、文本分块

## Context

MBForge 的 Rust 侧（`src-tauri/`）目前只是个 Tauri 进程启动器（74 行 main.rs），零业务逻辑。前端通过 HTTP 与 Python 后端通信。

三个高频 Python 函数（正则密集型）适合首批转 Rust 作为 Tauri Command，前端通过 `invoke()` 直接调用，跳过 HTTP。Python 侧实现保持不动，作为服务端 pipeline 和浏览器 dev 模式的 fallback。

## 架构

```
Frontend (React)
  ├─ Tauri 环境? ──→ invoke('text_chunk', ...) ──→ Rust (零延迟)
  └─ 浏览器环境? ──→ fetch('/api/v1/...')      ──→ Python (HTTP)
```

- **Path A（新）**：Tauri webview 内，前端直接调 Rust command，零 HTTP 开销
- **Path B（不变）**：服务端 pipeline（`/api/v1/project/index-stream`）继续走 Python
- **Fallback**：前端检测 `window.__TAURI_INTERNALS__` 判断是否可用 Rust

## 改动文件清单

### Rust 侧

| 文件 | 操作 | 说明 |
|------|------|------|
| `src-tauri/Cargo.toml` | 修改 | 添加 `regex = "1"` |
| `src-tauri/src/main.rs` | 修改 | 添加 `mod commands` + `.invoke_handler(...)` |
| `src-tauri/src/commands/mod.rs` | 新建 | re-export 三个子模块 |
| `src-tauri/src/commands/text_ops.rs` | 新建 | `text_chunk` command |
| `src-tauri/src/commands/classifier.rs` | 新建 | `classify_page` + `classify_document` |
| `src-tauri/src/commands/extractor.rs` | 新建 | `extract_smiles_candidates` + `extract_activities` |
| `src-tauri/capabilities/default.json` | 修改 | 添加新 command 权限 |

### Frontend 侧

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/package.json` | 修改 | 添加 `@tauri-apps/api: "^2"` |
| `frontend/src/api/tauri-bridge.ts` | 新建 | Tauri invoke 封装 + 类型定义 |
| `frontend/src/api/client.ts` | 修改 | 底部追加 `*Rust` 导出函数 |

## Tauri Command 签名

### text_ops.rs
```rust
#[tauri::command]
fn text_chunk(text: String, chunk_size: usize, overlap: usize) -> Vec<String>
```
- 来源：`src/mbforge/utils/helpers.py:split_text_chunks`
- 算法：滑动窗口，`\n` → `。` → ` ` 三级边界检测，UTF-8 byte offset

### classifier.rs
```rust
#[tauri::command]
fn classify_page(page_text: String, page_idx: usize) -> PageClassification

#[tauri::command]
fn classify_document(pages: Vec<String>, metadata: Option<serde_json::Value>) -> DocumentClassification
```
- 来源：`src/mbforge/parsers/pdf_classifier.py:PDFClassifier`
- SMILES 正则 lookahead 拆成两步（Rust regex 不支持 lookahead）
- 化学名用 `HashSet` 静态查表

### extractor.rs
```rust
#[tauri::command]
fn extract_smiles_candidates(text: String) -> Vec<String>

#[tauri::command]
fn extract_activities(text: String) -> Vec<ActivityData>
```
- 来源：`src/mbforge/parsers/molecule/molecule_extractor.py:MoleculeExtractor`
- SMILES 验证用 Python fallback 逻辑（`len>3` 且含有机子集字符）
- Activity 正则含 Unicode µ/μ，Rust regex 默认支持

## Frontend Bridge 模式

```typescript
// tauri-bridge.ts
import { invoke } from '@tauri-apps/api/core'

export function isTauriAvailable(): boolean {
  return '__TAURI_INTERNALS__' in window
}

export async function textChunk(text: string, chunkSize = 512, overlap = 128): Promise<string[]> {
  return invoke('text_chunk', { text, chunk_size: chunkSize, overlap })
}
```

```typescript
// client.ts 底部追加
export async function textChunkRust(text: string, chunkSize = 512, overlap = 128) {
  if (!isTauriAvailable()) throw new Error('Not in Tauri')
  return textChunk(text, chunkSize, overlap)
}
```

## 实施顺序

1. Cargo.toml + main.rs + commands/mod.rs → `cargo check`
2. text_ops.rs + 单测 → `cargo test`
3. classifier.rs + 单测 → `cargo test`
4. extractor.rs + 单测 → `cargo test`
5. Frontend: @tauri-apps/api + tauri-bridge.ts + client.ts + capabilities
6. `cargo tauri dev` 集成验证

## 不动的部分

- Python 侧三个函数保持原样
- 服务端 pipeline 继续走 Python
- `rust/` 目录（PyO3 Tanimoto）不受影响

## 验证

- `cargo test` — Rust 单测覆盖所有 command
- `cargo tauri dev` — Tauri webview 中 `invoke('text_chunk', ...)` 验证
- `npm run dev` — 浏览器中 `isTauriAvailable()` 返回 false，fallback 正常
