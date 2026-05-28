# MBForge Rust 迁移路线图

## Context

MBForge 是 Python+React+Tauri 桌面应用，目标是将核心计算逐步迁移到 Rust，同时整合 LlamaIndex。当前 Rust 层仅有 Tauri 进程管理 + pdf-inspector + 7 个 Tauri commands。

**核心约束：**
- 渐进迁移，每个阶段都产出可运行的软件
- Python ML 生态（RDKit、PyTorch、sentence-transformers）短期保留
- LlamaIndex 是 Python-only，作为编排层保留
- Rust 处理计算密集型任务，Python 处理模型推理

## 架构演进

```
当前:  Frontend → Python HTTP → Python Pipeline
       Frontend → Tauri invoke → Rust (pdf-inspector)

目标:  Frontend → Tauri invoke → Rust Core (计算+数据+HTTP)
                                  ↕ PyO3/IPC
                                  Python (ML推理+LlamaIndex)
```

## 阻塞项与解决方案

| Python 库 | 用途 | Rust 替代方案 |
|-----------|------|--------------|
| RDKit | SMILES 解析、分子描述符 | 纯 Rust SMILES 解析器 + 描述符计算 |
| ChromaDB | 向量存储 | `tantivy` + HNSW 或 `scylla` |
| sentence-transformers | 本地 embedding/rerank | ONNX Runtime (`ort`) 或保留 Python |
| PyTorch | GPU 推理 | ONNX Runtime (`ort`) 或保留 Python |
| pandas | DataFrame | `polars`（Rust 原生） |
| openai SDK | LLM HTTP 调用 | `reqwest` + `serde_json` |

## 五阶段迁移计划

### Phase 1: 基础层 Rust 化（无外部依赖）

**目标：** 将纯计算模块迁移到 Rust，建立 Rust 工程结构。

**迁移模块（EASY）：**
- `utils/constants.py` → Rust constants 模块
- `utils/config.py` → Rust config（serde + directories crate）
- `utils/helpers.py` → Rust helpers（sha2, uuid, text_chunk）
- `agent/context.py` → Rust LayeredContext
- `agent/trajectory.py` → Rust TrajectoryTracker
- `agent/memory_manager.py` → Rust MemoryManager
- `agent/tools.py` → Rust ToolRegistry
- `core/project.py` → Rust Project（walkdir + sha2 + serde_json）

**Rust 工程结构：**
```
src-tauri/src/
  lib.rs           — 公共 API
  commands/        — Tauri commands（已有）
  core/            — 核心数据结构
    config.rs      — 配置管理
    project.rs     — 项目扫描
    context.rs     — 对话上下文
    memory.rs      — 记忆管理
    trajectory.rs  — 轨迹记录
    tools.rs       — 工具注册表
  parsers/         — 解析器（已有 pdf.rs）
  models/          — 模型接口（trait 定义）
```

**集成方式：** PyO3 绑定，Python 通过 `import mbforge_core` 调用。

### Phase 2: LLM 客户端 + Agent 核心 Rust 化

**目标：** LLM HTTP 调用和 ReAct 循环迁移到 Rust。

**迁移模块（MEDIUM）：**
- `models/llm.py` → Rust LLM client（reqwest + serde_json）
- `models/base.py` → Rust trait 定义
- `agent/agent.py` → Rust ReAct 循环
- `agent/executor.py` → Rust ToolExecutor（调用 Python KB/mol_db 通过 IPC）
- `core/summarizer.py` → Rust SummaryManager + LLM 调用

**关键决策：**
- LLM 客户端：Rust 原生 HTTP 调用 OpenAI/Anthropic API
- Agent 循环：Rust 实现 ReAct loop，调用 Rust LLM client
- 工具执行：Rust 调用 Python 进程执行 KB/mol_db 操作（过渡期）

### Phase 3: PDF Pipeline Rust 化 + LlamaParse 集成

**目标：** PDF 解析全链路 Rust 化，同时接入 LlamaParse 作为可选后端。

**迁移模块：**
- `parsers/pdf_parser.py` → Rust PDFPipeline（已有 pdf-inspector）
- `parsers/pdf_classifier.py` → Rust classifier（已有）
- `parsers/molecule_extractor.py` → Rust extractor（已有）
- `core/document.py` → Rust DocumentProcessor
- 新增：LlamaParse 适配器（Python 调用 LlamaParse API，结果传给 Rust）

**Pipeline 演进：**
```
当前: PyMuPDF → PDFClassifier → split_text → MoleculeExtractor → Summarizer → KB
目标: pdf-inspector/LlamaParse → Rust Classifier → Rust Chunker → Rust Extractor → Python Summarizer → Rust KB
```

### Phase 4: 知识库 Rust 化 + KnowledgeGraphIndex

**目标：** 向量存储从 ChromaDB 迁移到 Rust 原生实现。

**迁移模块（HARD）：**
- `core/knowledge_base.py` → Rust KnowledgeBase（tantivy + HNSW）
- 新增：KnowledgeGraphIndex（LlamaIndex Python 层）

**向量存储方案：**
- `tantivy` — 全文搜索（替代 ChromaDB 的文本匹配）
- `hnswlib-rs` — HNSW 向量索引（替代 ChromaDB 的向量搜索）
- 或 `scylla` — 高性能向量数据库

### Phase 5: ML 推理 Rust 化（ONNX Runtime）

**目标：** 本地 embedding/rerank 模型迁移到 Rust ONNX Runtime。

**迁移模块（HARD）：**
- `models/embedding.py` → Rust Embedder（ort crate + ONNX 模型）
- `models/rerank.py` → Rust Reranker（ort crate + ONNX 模型）
- `core/mol_database.py` → Rust MoleculeDatabase（rusqlite + 纯 Rust SMILES 解析）

**前置条件：**
- 将 sentence-transformers 模型导出为 ONNX 格式
- 实现或集成 Rust SMILES 解析器
- 实现分子描述符计算（MW, LogP, TPSA, HBD, HBA, RotatableBonds）

## 依赖关系图

```
Phase 1 (基础层)
  ↓
Phase 2 (LLM + Agent) ←── 依赖 Phase 1 的 trait 定义
  ↓
Phase 3 (PDF + LlamaParse) ←── 依赖 Phase 2 的 LLM client
  ↓
Phase 4 (KB + KG) ←── 依赖 Phase 1 的 project, Phase 2 的 agent
  ↓
Phase 5 (ML 推理) ←── 依赖 Phase 4 的 KB 接口
```

## PyO3 集成策略

```rust
// src-tauri/src/lib.rs
pub mod core;
pub mod parsers;
pub mod models;

// PyO3 绑定（供 Python 调用）
#[cfg(feature = "python")]
pub mod python {
    use pyo3::prelude::*;

    #[pymodule]
    pub fn mbforge_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_function(wrap_pyfunction!(super::core::config::load_config, m)?)?;
        m.add_function(wrap_pyfunction!(super::core::project::scan_project, m)?)?;
        m.add_function(wrap_pyfunction!(super::parsers::text_ops::text_chunk, m)?)?;
        Ok(())
    }
}
```

Python 侧：
```python
# Python 代码中
try:
    from mbforge_core import text_chunk, scan_project  # Rust 实现
except ImportError:
    from mbforge.utils.helpers import split_text_chunks as text_chunk  # Python fallback
```

## 验证策略

每个 Phase 完成后：
1. `cargo test` — Rust 单元测试
2. `cargo tauri dev` — Tauri 集成测试
3. `uv run pytest tests/` — Python 测试（确保 fallback 正常）
4. `uv run mbforge dev` — 端到端功能测试
5. 性能基准：对比 Rust vs Python 实现的延迟

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| RDKit 无 Rust 等价物 | Phase 5 延期 | 先实现基础 SMILES 解析，复杂功能保留 Python |
| ChromaDB 迁移复杂 | Phase 4 延期 | 先用 tantivy 全文搜索，向量搜索后补 |
| ONNX 模型格式不兼容 | Phase 5 失败 | 保留 Python 推理路径作为 fallback |
| PyO3 跨平台编译问题 | 构建失败 | CI 中测试所有目标平台 |
| Python/Rust 接口不稳定 | 集成 bug | 接口层用 JSON 序列化，解耦实现 |
