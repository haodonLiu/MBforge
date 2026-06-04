# Memvid -- Portable AI Memory System

> GitHub: `0xPlaygrounds/memvid` | Stars: ~15.6K | Language: 98.5% Rust
> Repository: https://github.com/0xPlaygrounds/memvid

---

## 1. Overview

Memvid is a portable, single-file AI memory system that packages data, embeddings, search structure, and metadata into one `.mv2` file. It replaces complex RAG pipelines and server-based vector databases with a self-contained, embeddable engine.

Key selling points:

- **Single-file portability** -- entire knowledge base in one `.mv2` file, copyable like a SQLite DB
- **Sub-millisecond queries** -- 0.025ms P50 latency for hybrid search
- **State-of-the-art retrieval** -- +35% over existing systems on the LoCoMo long-context benchmark
- **No infrastructure** -- no external servers, no ChromaDB, no Qdrant, no sidecar files
- **Append-only durability** -- immutable Smart Frames with embedded WAL for crash recovery

---

## 2. Core Architecture

### 2.1 The `.mv2` File Format

A single `.mv2` file contains everything needed for search and retrieval:

```
+--------------------------------------------------+
|  Header (4 KB)                                    |
|  Magic bytes, version, global config, offsets     |
+--------------------------------------------------+
|  Embedded WAL (1--64 MB)                          |
|  Write-ahead log for crash recovery               |
+--------------------------------------------------+
|  Data Segments                                    |
|  Raw content, chunked into Smart Frames           |
+--------------------------------------------------+
|  Lex Index (Tantivy BM25)                         |
|  Full-text inverted index                         |
+--------------------------------------------------+
|  Vec Index (HNSW)                                 |
|  Approximate nearest-neighbor vector index        |
+--------------------------------------------------+
|  Time Index                                       |
|  Temporal ordering and range queries              |
+--------------------------------------------------+
|  TOC (Table of Contents)                          |
|  Master index of all segments and their offsets   |
+--------------------------------------------------+
```

**No sidecar files**: No `.wal`, `.lock`, `.shm`, or temporary files on disk. Everything is inside the single `.mv2` container.

### 2.2 Smart Frames

Smart Frames are the fundamental storage unit -- append-only, immutable, and self-describing:

- **Immutable**: once written, a frame is never modified
- **Timestamped**: each frame carries a creation timestamp for temporal queries
- **Checksummed**: integrity verification on read
- **Metadata-rich**: arbitrary key-value metadata attached to each frame
- **Append-only growth**: new data is always appended; old frames are never mutated

This design provides:
- Crash safety (no partial writes corrupting existing data)
- Efficient incremental backup (only new frames need syncing)
- Natural audit trail (every change is a new frame)

### 2.3 No External Dependencies at Runtime

Memvid embeds all required engines (Tantivy for BM25, HNSW for vector search) directly. The `.mv2` file is the only artifact on disk.

---

## 3. Key Innovations

### 3.1 Video Codec Metaphor

Memvid borrows concepts from video encoding:

- **Frames as immutable units** -- like video frames, each memory unit is self-contained
- **Compression** -- data segments use compression analogous to video codecs
- **Timeline queries** -- temporal indexing allows "rewind" and "fast-forward" through memory history

This metaphor provides a clean mental model: memory is a timeline of immutable snapshots, not a mutable database.

### 3.2 Performance

| Metric | Value |
|--------|-------|
| P50 query latency | 0.025 ms |
| LoCoMo benchmark | +35% over SOTA |
| Startup time | Near-instant (mmap-based) |

### 3.3 Time-Travel Debugging

Memvid supports full temporal operations on memory:

- **Rewind**: revert to any previous memory state
- **Replay**: walk through memory changes step by step
- **Branch**: fork memory at a point in time for experimentation
- **Diff**: compare memory states across time

This is useful for debugging agent behavior -- you can see exactly what the agent "knew" at any point in its history.

### 3.4 Capsule Context

A `.mv2` file is a **Capsule Context** -- a self-contained, shareable unit of memory:

- Copy a `.mv2` file to share a knowledge base
- No server setup, no API keys embedded, no external dependencies
- Portable across machines and environments

---

## 4. Rust Feature Flags

Memvid uses Cargo feature flags to control which capabilities are compiled in:

| Feature | Description |
|---------|-------------|
| `lex` | Tantivy BM25 full-text index |
| `vec` | HNSW approximate nearest-neighbor index |
| `clip` | CLIP model for visual embeddings |
| `whisper` | Whisper model for audio transcription |
| `pdf_extract` | PDF text extraction |
| `api_embed` | Remote embedding API support (OpenAI, etc.) |
| `temporal_track` | Time-indexed queries and time-travel features |
| `encryption` | At-rest encryption of `.mv2` files |
| `parallel_segments` | Parallel read/write of data segments |
| `symspell_cleanup` | Spell correction and text normalization |

Typical minimal build: `lex` + `vec` (BM25 + HNSW hybrid search).

---

## 5. Embedding Models

### Local (ONNX Runtime)

| Model | Dimensions | Notes |
|-------|-----------|-------|
| BGE-small | 384 | Default, fast, good quality |
| BGE-base | 768 | Better quality, slower |
| Nomic | 768 | Strong general-purpose |
| GTE-large | 1024 | Highest quality, largest |

### Cloud

| Provider | Model | Dimensions |
|----------|-------|-----------|
| OpenAI | text-embedding-3-small | 1536 |
| OpenAI | text-embedding-3-large | 3072 |

Local ONNX models run entirely offline with no API key required.

---

## 6. Relevance to MBForge

### 6.1 Patterns Worth Adopting

| Memvid Pattern | MBForge Application |
|----------------|---------------------|
| **Single-file storage** | Simplify `.mbforge/` directory -- instead of separate ChromaDB dirs, molecule DBs, and index files, consider a unified container |
| **Append-only Smart Frames** | Safer document indexing -- PDF extraction results as immutable frames, no risk of corrupting existing data during partial re-index |
| **Embedded WAL** | Crash recovery for knowledge base -- currently ChromaDB has no WAL; a power loss during indexing can lose data |
| **HNSW + BM25 hybrid** | Same approach we use with LanceDB -- validates our architecture choice |
| **Capsule Context** | Shareable knowledge bases between projects -- export a project's knowledge as a single file, import into another |
| **Time-travel debugging** | Agent memory debugging -- rewind to see what the agent knew at step N of a conversation |

### 6.2 What NOT to Adopt

Memvid is a **general-purpose memory engine**, not a chemistry-specific tool. Several design choices are poor fits for MBForge:

| Concern | Detail |
|---------|--------|
| **Video codec metaphor** | Adds conceptual complexity. MBForge's workflow is document-centric (PDF -> molecules -> knowledge), not timeline-centric. The "frame" abstraction maps awkwardly to chemical data. |
| **Single-file concurrency** | A single `.mv2` file makes concurrent access harder than SQLite (which has WAL mode) or LanceDB (which uses Apache Arrow IPC). MBForge's Tauri app has both Rust and Python accessing the same data -- multi-process file locking on a monolithic container is more complex than on separate files. |
| **No chemistry domain support** | Memvid has no molecular fingerprints, substructure search, SMILES handling, or chemical property estimation. We would still need our full `molecule_store.rs` alongside it. |
| **Maturity** | At 15.6K stars but relatively young. LanceDB/ChromaDB have larger ecosystems and more production usage in RAG pipelines. |
| **Feature flag bloat** | CLIP, Whisper, PDF extraction, encryption -- most are irrelevant to MBForge and add binary size. |

### 6.3 Potential Hybrid Approach

If adopting any Memvid ideas, consider:

1. **Smart Frame pattern for PDF extraction results** -- store each extraction as an immutable frame with timestamp and checksum, enabling safe re-extraction and rollback
2. **Embedded WAL for ChromaDB/LanceDB** -- wrap our vector DB writes in a WAL layer for crash recovery
3. **Capsule export** -- implement `.mv2`-like export of project knowledge bases for sharing between MBForge instances

Do NOT replace the entire storage stack with Memvid -- it would add a dependency without solving MBForge's actual problems (molecular search, chemistry validation, multi-parser pipeline).

---

## 7. Summary

Memvid is an impressive engineering achievement: a single-file, sub-millisecond, portable memory engine with hybrid search. Its core ideas (append-only frames, embedded WAL, capsule context) are sound patterns that could improve MBForge's storage layer. However, its video codec metaphor and general-purpose design make it a poor direct replacement for our chemistry-specific toolchain. Borrow the patterns, not the product.
