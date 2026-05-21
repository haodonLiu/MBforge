# MBForge RAG 实施计划

> 基于用户技术选型决策的详细实施路线图。  
> **制定日期**: 2026-05-21  
> **关联文档**: [RAG 技术分析](RAG_TECHNICAL_ANALYSIS.md)

---

## 一、用户技术选型决策（已确认）

| 决策项 | 用户选择 | 理由 |
|--------|---------|------|
| **Embedding 模型** | `Qwen/Qwen3-Embedding-0.6B` | 768-dim, 32K context, 100+ 语言, 支持 MRL + Instruction Aware |
| **Reranker 模型** | `Qwen/Qwen3-Reranker-0.6B` | 同系列配套, 32K context, CausalLM 架构 yes/no 概率评分 |
| **OCR 模型** | `GLM-OCR` (zai-org/GLM-OCR) | 0.9B 参数, 两阶段版面分析, 输出 Markdown/JSON, MIT license |
| **Keyword 检索** | SQLite FTS5（已有依赖） | 零新增外部服务, 纯本地运行 |
| **分子指纹检索** | 方案 C：RDKit 内存检索 | 轻量, 无需额外向量库 |
| **分子图存储** | NetworkX（轻量级） | 规模 <100 篇, NetworkX 足够; SMILES 无法高效子图匹配 |
| **向量数据库** | 保留 ChromaDB | 桌面应用开箱即用, 规模匹配 |

---

## 二、模型技术规格与集成要点

### 2.1 Qwen3-Embedding-0.6B

| 属性 | 规格 |
|------|------|
| HuggingFace | `Qwen/Qwen3-Embedding-0.6B` |
| 参数量 | 0.6B |
| 向量维度 | 768 (支持 MRL: 可输出 768/512/256/128/64) |
| 最大上下文 | 32K tokens |
| 语言支持 | 100+ |
| 特殊能力 | Instruction Aware (不同任务前缀), MRL (Matryoshka) |
| 加载方式 | `sentence-transformers` 原生兼容 (含 `config_sentence_transformers.json`) |
| 模型大小 | ~1.2GB (FP16) |

**Instruction Aware 使用方式**:
```python
# 检索任务前缀（必须添加以获得最佳效果）
INSTRUCTION_RETRIEVAL = "Given a web search query, retrieve relevant passages that answer the query"
# 聚类任务前缀
INSTRUCTION_CLUSTER = "Given a document, retrieve relevant passages that are semantically similar"

# 编码时：为每个文本添加前缀
texts = [f"{INSTRUCTION_RETRIEVAL}\n{t}" for t in texts]
embeddings = model.encode(texts, normalize_embeddings=True)
```

**MRL 使用方式**:
```python
# 输出 256-dim 子向量（节省存储，损失少量精度）
embeddings = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
# 取前 256 维
embeddings_256 = embeddings[:, :256]
```

### 2.2 Qwen3-Reranker-0.6B

| 属性 | 规格 |
|------|------|
| HuggingFace | `Qwen/Qwen3-Reranker-0.6B` |
| 参数量 | 0.6B |
| 架构 | CausalLM (非 CrossEncoder!) |
| 最大上下文 | 32K tokens |
| 推理方式 | 构造 yes/no 判断 prompt, 取 `yes` token 的 logits 概率 |
| 依赖 | `transformers>=4.51.0` |
| 模型大小 | ~1.2GB (FP16) |

**⚠️ 关键差异**: Qwen3-Reranker 是 **CausalLM 生成式重排序器**，与 BGE-Reranker 的 CrossEncoder 完全不同。

**推理流程**:
```python
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-Reranker-0.6B", padding_side='left')
model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-Reranker-0.6B").eval()

# 特殊 token ID
token_false_id = tokenizer.convert_tokens_to_ids("no")
token_true_id = tokenizer.convert_tokens_to_ids("yes")

prefix = "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n"
suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
prefix_tokens = tokenizer.encode(prefix, add_special_tokens=False)
suffix_tokens = tokenizer.encode(suffix, add_special_tokens=False)

def format_instruction(instruction, query, doc):
    if instruction is None:
        instruction = 'Given a web search query, retrieve relevant passages that answer the query'
    return f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"

def rerank(query, passages, instruction=None):
    pairs = [format_instruction(instruction, query, p) for p in passages]
    inputs = tokenizer(pairs, padding=False, truncation='longest_first', 
                       return_attention_mask=False, max_length=8192 - len(prefix_tokens) - len(suffix_tokens))
    for i, ids in enumerate(inputs['input_ids']):
        inputs['input_ids'][i] = prefix_tokens + ids + suffix_tokens
    inputs = tokenizer.pad(inputs, padding=True, return_tensors="pt", max_length=8192)
    
    with torch.no_grad():
        logits = model(**inputs).logits[:, -1, :]
        scores = torch.nn.functional.log_softmax(
            torch.stack([logits[:, token_false_id], logits[:, token_true_id]], dim=1), dim=1
        )[:, 1].exp().tolist()
    
    # 返回 (原始索引, 分数) 按分数降序
    return sorted([(i, s) for i, s in enumerate(scores)], key=lambda x: x[1], reverse=True)
```

**对当前架构的影响**:
- 需新增 `Qwen3Reranker` 类实现 `BaseReranker` 接口
- `transformers>=4.51.0` 成为硬依赖（当前可能未满足）
- 推理延迟略高于 CrossEncoder（因为需要构造完整 prompt + causalLM 前向传播）

### 2.3 GLM-OCR

| 属性 | 规格 |
|------|------|
| GitHub | `zai-org/GLM-OCR` |
| 参数 | 0.9B (0.4B CogViT encoder + 0.5B GLM decoder) |
| 架构 | Encoder-Decoder + MTP (Multi-Token Prediction) |
| 流水线 | 两阶段: PP-DocLayout-V3 版面分析 → 并行区域识别 |
| 输出格式 | Markdown / JSON |
| License | MIT |
| 部署方式 | MaaS API (智谱云) / 本地 (vLLM/SGLang/Ollama) |
| SDK | `pip install glmocr` |

**使用方式（MaaS API - 推荐快速开始）**:
```python
from glmocr import GLMOCR

ocr = GLMOCR(maas_api_key="your-api-key")
result = ocr.recognize("paper.pdf", task="document_parsing")
# result.markdown 为结构化 Markdown
# result.json 为结构化 JSON
```

**使用方式（本地 vLLM）**:
```bash
# 模型下载后启动 vLLM 服务
vllm serve zai-org/GLM-OCR --dtype float16 --max-model-len 8192
```

**对 MBForge 的价值**:
1. **替代/增强 PyMuPDF**: GLM-OCR 的版面分析比 PyMuPDF 纯文本提取更精准，尤其对复杂表格、公式、多栏布局。
2. **化学结构识别**: 虽然 GLM-OCR 是通用 OCR，但对化学结构图有一定识别能力。可在 prompt 中指定 `"识别图中的化学结构，输出 SMILES"`。
3. **表格结构化**: 将 PDF 表格直接转为 Markdown 表格，而非纯文本流，大幅提升后续 chunk 质量。
4. **标题层级提取**: 自动识别 H1/H2/H3，为 Hierarchical RAG 提供文档树。

---

## 三、实施阶段与任务分解

### Phase 0: 基础设施升级（1 周）

#### Task 0.1: 依赖更新

**目标**: 添加新模型所需的 Python 依赖。

**修改文件**: `pyproject.toml`

```toml
# 新增/更新依赖
[project.dependencies]
# 现有依赖保留...
transformers>=4.51.0      # Qwen3-Reranker 需要
glmocr>=0.1.0             # GLM-OCR SDK
accelerate>=0.30.0        # transformers 推理加速

# 可选: 如使用 vLLM 本地部署 GLM-OCR
# vllm>=0.5.0             # 本地高性能推理
```

**验证**:
```bash
uv sync
python -c "import transformers; print(transformers.__version__)"
python -c "from sentence_transformers import SentenceTransformer; m = SentenceTransformer('Qwen/Qwen3-Embedding-0.6B'); print(m.get_sentence_embedding_dimension())"
```

#### Task 0.2: 配置系统扩展

**目标**: 在配置中新增 Qwen3 和 GLM-OCR 的选项。

**修改文件**: `src/mbforge/utils/config.py`, `src/mbforge/utils/constants.py`

```python
# constants.py 新增
PROVIDER_QWEN3 = "qwen3"
PROVIDER_GLM_OCR = "glm_ocr"
DEFAULT_EMBED_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_RERANK_MODEL = "Qwen/Qwen3-Reranker-0.6B"

# config.py 新增 provider 选项
@dataclass
class EmbedConfig:
    provider: str = PROVIDER_SENTENCE_TRANSFORMERS  # 新增 qwen3 选项
    model_name: str = DEFAULT_EMBED_MODEL
    ...

@dataclass
class RerankConfig:
    provider: str = PROVIDER_SENTENCE_TRANSFORMERS  # 新增 qwen3 选项
    model_name: str = DEFAULT_RERANK_MODEL
    ...

@dataclass
class OcrConfig:
    provider: str = PROVIDER_API  # api | glm_ocr_local | glm_ocr_maas
    base_url: str = ""            # 本地 vLLM 地址或智谱 API 地址
    api_key: str = ""
    model_name: str = ""
```

#### Task 0.3: 模型下载与缓存策略

**目标**: 确保模型首次下载后缓存复用。

**策略**:
- Embedding/Reranker 模型通过 `sentence-transformers` / `transformers` 自动下载到 `~/.cache/huggingface/hub`
- GLM-OCR 模型通过 `glmocr` SDK 自动管理
- 在 UI 设置中增加"模型管理"面板，显示已下载模型列表和占用空间，支持手动清理缓存

---

### Phase 1: 核心模型替换（1-2 周）

#### Task 1.1: Qwen3-Embedding 集成

**目标**: 替换 `SentenceTransformerEmbedder` 的默认模型，支持 Instruction Aware。

**修改文件**: `src/mbforge/models/embedding.py`

```python
class Qwen3Embedder(BaseEmbedder):
    """基于 Qwen3-Embedding 的本地 Embedding.
    
    支持 Instruction Aware 和 MRL (Matryoshka Representation Learning).
    """
    
    # 任务指令前缀
    INSTRUCTION_RETRIEVAL = "Given a web search query, retrieve relevant passages that answer the query"
    INSTRUCTION_CLUSTER = "Given a document, retrieve relevant passages that are semantically similar"
    
    def __init__(self, model_name: str = "Qwen/Qwen3-Embedding-0.6B", 
                 device: str = "cpu", mrl_dim: Optional[int] = None,
                 instruction: Optional[str] = None):
        self.model_name = model_name
        self.device = device
        self.mrl_dim = mrl_dim  # MRL 输出维度, e.g., 256
        self.instruction = instruction or self.INSTRUCTION_RETRIEVAL
        self._model = None
        self._dim = None
    
    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=self.device, 
                                               trust_remote_code=True)
            self._dim = self._model.get_sentence_embedding_dimension()
            if self.mrl_dim and self.mrl_dim < self._dim:
                self._dim = self.mrl_dim
        return self._model
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        model = self._load_model()
        # 为每个文本添加 instruction 前缀
        prefixed = [f"{self.instruction}\n{t}" for t in texts]
        embeddings = model.encode(prefixed, normalize_embeddings=True, 
                                   show_progress_bar=False, convert_to_numpy=True)
        if self.mrl_dim and self.mrl_dim < embeddings.shape[1]:
            embeddings = embeddings[:, :self.mrl_dim]
        return embeddings.tolist()
```

**配置更新**: `create_embedder_from_config` 中增加 `qwen3` provider 分支。

#### Task 1.2: Qwen3-Reranker 集成

**目标**: 实现全新的 CausalLM 重排序器。

**新建文件**: `src/mbforge/models/rerank_qwen3.py`

```python
"""Qwen3-Reranker 实现.

基于 CausalLM 的生成式重排序器，通过 yes/no 概率判断相关性。
与 BGE CrossEncoder 架构完全不同。
"""

from __future__ import annotations

import torch
from typing import List, Optional
from transformers import AutoTokenizer, AutoModelForCausalLM

from .base import BaseReranker


class Qwen3Reranker(BaseReranker):
    """Qwen3-Reranker-0.6B 重排序器."""
    
    DEFAULT_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"
    
    def __init__(self, model_name: str = "Qwen/Qwen3-Reranker-0.6B",
                 device: str = "cpu", max_length: int = 8192):
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self._tokenizer = None
        self._model = None
        self._prefix_tokens = None
        self._suffix_tokens = None
        self._token_true_id = None
        self._token_false_id = None
    
    def _load(self):
        if self._model is None:
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, padding_side='left', trust_remote_code=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name, trust_remote_code=True
            ).eval().to(self.device)
            
            self._token_true_id = self._tokenizer.convert_tokens_to_ids("yes")
            self._token_false_id = self._tokenizer.convert_tokens_to_ids("no")
            
            prefix = "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n"
            suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
            self._prefix_tokens = self._tokenizer.encode(prefix, add_special_tokens=False)
            self._suffix_tokens = self._tokenizer.encode(suffix, add_special_tokens=False)
    
    def _format_pair(self, instruction: str, query: str, doc: str) -> str:
        return f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"
    
    def rerank(self, query: str, passages: List[str]) -> List[tuple[int, float]]:
        self._load()
        instruction = self.DEFAULT_INSTRUCTION
        pairs = [self._format_pair(instruction, query, p) for p in passages]
        
        # Tokenize
        inputs = self._tokenizer(
            pairs, padding=False, truncation='longest_first',
            return_attention_mask=False,
            max_length=self.max_length - len(self._prefix_tokens) - len(self._suffix_tokens)
        )
        
        # Wrap with prefix/suffix
        for i, ids in enumerate(inputs['input_ids']):
            inputs['input_ids'][i] = self._prefix_tokens + ids + self._suffix_tokens
        
        # Pad and convert to tensor
        inputs = self._tokenizer.pad(inputs, padding=True, return_tensors="pt", 
                                      max_length=self.max_length)
        for key in inputs:
            inputs[key] = inputs[key].to(self.device)
        
        # Forward
        with torch.no_grad():
            logits = self._model(**inputs).logits[:, -1, :]
            false_vec = logits[:, self._token_false_id]
            true_vec = logits[:, self._token_true_id]
            batch_scores = torch.stack([false_vec, true_vec], dim=1)
            batch_scores = torch.nn.functional.log_softmax(batch_scores, dim=1)
            scores = batch_scores[:, 1].exp().tolist()
        
        indexed = [(i, float(scores[i])) for i in range(len(passages))]
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed
```

**修改文件**: `src/mbforge/models/rerank.py`

在 `create_reranker_from_config` 中增加 `qwen3` provider 分支。

#### Task 1.3: GLM-OCR 集成

**目标**: 将 GLM-OCR 作为可选文档解析后端。

**新建文件**: `src/mbforge/parsers/glm_ocr_parser.py`

```python
"""GLM-OCR 文档解析后端.

两阶段流水线:
1. PP-DocLayout-V3 版面分析
2. 并行区域级识别

输出结构化 Markdown/JSON，替代 PyMuPDF 纯文本提取。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)


class GlmOcrParser:
    """GLM-OCR 解析器封装."""
    
    def __init__(self, api_key: str = "", base_url: str = "", 
                 use_local: bool = False, local_model_path: str = ""):
        self.api_key = api_key
        self.base_url = base_url
        self.use_local = use_local
        self.local_model_path = local_model_path
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                from glmocr import GLMOCR
                if self.use_local and self.local_model_path:
                    self._client = GLMOCR(model_path=self.local_model_path)
                elif self.api_key:
                    self._client = GLMOCR(maas_api_key=self.api_key)
                else:
                    # 尝试从环境变量读取
                    self._client = GLMOCR()
            except ImportError:
                logger.error("glmocr not installed. Run: uv add glmocr")
                raise
        return self._client
    
    def parse_pdf(self, pdf_path: Path, **kwargs) -> Dict[str, Any]:
        """解析 PDF，返回结构化结果.
        
        Returns:
            {
                "markdown": str,      # 结构化 Markdown
                "text": str,          # 纯文本（用于兼容现有流程）
                "json": dict,         # 结构化 JSON
                "tables": List[dict], # 表格列表
                "images": List[dict], # 图像描述列表
                "layout": List[dict], # 版面分析结果
            }
        """
        client = self._get_client()
        result = client.recognize(str(pdf_path), task="document_parsing")
        
        return {
            "markdown": getattr(result, "markdown", ""),
            "text": getattr(result, "text", ""),
            "json": getattr(result, "json", {}),
            "tables": getattr(result, "tables", []),
            "images": getattr(result, "images", []),
            "layout": getattr(result, "layout", []),
        }
    
    def extract_smiles_from_images(self, pdf_path: Path) -> List[str]:
        """从 PDF 图像中提取化学结构 SMILES.
        
        使用专用 prompt 引导 GLM-OCR 识别化学结构。
        """
        client = self._get_client()
        prompt = (
            "识别文档中的所有化学结构（分子结构图），"
            "为每个结构输出其 SMILES 字符串。"
            "如果无法确定精确 SMILES，请描述结构特征。"
        )
        result = client.recognize(str(pdf_path), task="key_information_extraction", 
                                   prompt=prompt)
        # 从结果中提取 SMILES
        smiles_list = []
        # TODO: 解析 result.json 中的化学结构字段
        return smiles_list
```

**修改文件**: `src/mbforge/parsers/pdf_parser.py`

在 `PDFParserPipeline` 中增加 `use_glm_ocr` 选项，优先使用 GLM-OCR，fallback 到 PyMuPDF。

---

### Phase 2: Hybrid RAG 实现（1 周）

#### Task 2.1: SQLite FTS5 全文检索

**目标**: 利用现有 SQLite 做 keyword 检索。

**修改文件**: `src/mbforge/core/knowledge_base.py`

```python
# 在 KnowledgeBase 中新增 keyword_search 方法

class KnowledgeBase:
    # ... existing code ...
    
    def _init_fts(self):
        """初始化全文检索虚拟表."""
        # ChromaDB 的 metadata 已存储 source 和 doc_id
        # 我们在 SQLite 中创建一个独立的 FTS5 表来索引 chunk 文本
        # 注意: 这里需要在项目初始化时创建
        pass
    
    def keyword_search(
        self, query: str, top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """基于 SQLite FTS5 的关键词检索.
        
        用于精确匹配化学名、CAS 号、专利号等。
        """
        # 实现方案:
        # 1. 在 index_document 时，同时将 chunk 文本写入 SQLite FTS5 表
        # 2. 使用 MATCH 语法做全文检索
        # 3. 返回与 vector search 兼容的格式
        pass
```

**更优方案**: 由于 ChromaDB 本身支持 `query_texts`（让 ChromaDB 自己做 embedding），但 keyword 检索需要不同的机制。

**推荐实现**:
1. 在 `KnowledgeBase.__init__` 中创建独立的 SQLite 连接（或复用 `MoleculeDatabase` 的 SQLite）。
2. 创建 FTS5 虚拟表：
   ```sql
   CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
       chunk_text, doc_id, chunk_index, source
   );
   ```
3. `index_document` 时双写：ChromaDB + FTS5。
4. `keyword_search` 用 `MATCH` 查询 FTS5。

#### Task 2.2: Hybrid Search 融合

**修改文件**: `src/mbforge/core/knowledge_base.py`

```python
def hybrid_search(
    self,
    query: str,
    top_k: int = 5,
    reranker=None,
    keyword_weight: float = 0.3,
    vector_weight: float = 0.7,
) -> List[Dict[str, Any]]:
    """Hybrid RAG: Keyword + Vector + Rerank.
    
    Args:
        keyword_weight: keyword 检索结果的权重
        vector_weight: 向量检索结果的权重
    """
    # 1. 两路并行召回
    keyword_results = self.keyword_search(query, top_k=top_k * 2)
    vector_results = self.search(query, top_k=top_k * 2)
    
    # 2. 归一化分数（Min-Max）
    # keyword: BM25 分数 → [0, 1]
    # vector: cosine distance → similarity → [0, 1]
    
    # 3. 融合去重
    merged = {}
    for r in keyword_results:
        key = r["id"]
        merged[key] = {"item": r, "kw_score": r["score"], "vec_score": 0}
    for r in vector_results:
        key = r["id"]
        if key in merged:
            merged[key]["vec_score"] = 1 - r["distance"]  # distance → similarity
        else:
            merged[key] = {"item": r, "kw_score": 0, "vec_score": 1 - r["distance"]}
    
    # 4. 加权融合
    for key, data in merged.items():
        data["fused_score"] = (
            keyword_weight * data["kw_score"] + 
            vector_weight * data["vec_score"]
        )
    
    # 5. 排序取 top_k * 3
    candidates = sorted(merged.values(), key=lambda x: x["fused_score"], reverse=True)
    candidates = candidates[:top_k * 3]
    
    # 6. Rerank
    if reranker is None:
        return [c["item"] for c in candidates[:top_k]]
    
    passages = [c["item"]["text"] for c in candidates]
    ranked = reranker.rerank(query, passages)
    result = []
    for idx, score in ranked[:top_k]:
        item = candidates[idx]["item"].copy()
        item["rerank_score"] = score
        result.append(item)
    return result
```

---

### Phase 3: 分子图与指纹检索（1-2 周）

#### Task 3.1: NetworkX 分子图存储

**目标**: 用图结构存储分子，支持高效子图匹配。

**新建文件**: `src/mbforge/core/mol_graph.py`

```python
"""分子图存储 - NetworkX 内存图.

将 RDKit Mol 对象转为 NetworkX 图，支持子图同构匹配。
SMILES 无法直接高效子图匹配，图结构是必要格式。
"""

from __future__ import annotations

import json
import networkx as nx
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors
except ImportError:
    Chem = None  # type: ignore

from ..utils.logger import get_logger

logger = get_logger(__name__)


class MoleculeGraph:
    """分子图管理器.
    
    每个分子存储为 NetworkX 图:
    - 节点: 原子 (atomic_num, formal_charge, hybridization, aromatic)
    - 边: 化学键 (bond_type, is_conjugated, in_ring)
    
    支持:
    - 子图同构匹配 (GraphMatcher)
    - 图编辑距离 (GED)
    - 拓扑特征提取
    """
    
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.graph_path = self.project_root / ".mbforge" / "mol_graphs.json"
        self._graphs: Dict[str, nx.Graph] = {}  # mol_id -> graph
        self._smiles_map: Dict[str, str] = {}    # mol_id -> smiles
        self._load()
    
    def _mol_to_graph(self, mol) -> nx.Graph:
        """将 RDKit Mol 转为 NetworkX Graph."""
        g = nx.Graph()
        for atom in mol.GetAtoms():
            g.add_node(
                atom.GetIdx(),
                atomic_num=atom.GetAtomicNum(),
                formal_charge=atom.GetFormalCharge(),
                hybridization=str(atom.GetHybridization()),
                aromatic=atom.GetIsAromatic(),
                degree=atom.GetDegree(),
            )
        for bond in mol.GetBonds():
            g.add_edge(
                bond.GetBeginAtomIdx(),
                bond.GetEndAtomIdx(),
                bond_type=str(bond.GetBondType()),
                is_conjugated=bond.GetIsConjugated(),
                in_ring=bond.IsInRing(),
            )
        return g
    
    def add_molecule(self, mol_id: str, smiles: str) -> bool:
        """添加分子到图存储."""
        if Chem is None:
            return False
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False
        self._graphs[mol_id] = self._mol_to_graph(mol)
        self._smiles_map[mol_id] = smiles
        return True
    
    def subgraph_search(self, query_smiles: str) -> List[str]:
        """子图匹配搜索.
        
        返回所有包含 query 作为子图的分子 ID。
        使用 NetworkX GraphMatcher 做子图同构。
        """
        if Chem is None or not self._graphs:
            return []
        
        query_mol = Chem.MolFromSmiles(query_smiles)
        if query_mol is None:
            return []
        query_g = self._mol_to_graph(query_mol)
        
        results = []
        for mol_id, graph in self._graphs.items():
            from networkx.algorithms import isomorphism
            # 节点匹配器：原子序数相同
            node_match = isomorphism.categorical_node_match(
                ["atomic_num"], [0]
            )
            # 边匹配器：键类型相同
            edge_match = isomorphism.categorical_edge_match(
                ["bond_type"], [""]
            )
            GM = isomorphism.GraphMatcher(
                graph, query_g, node_match=node_match, edge_match=edge_match
            )
            if GM.subgraph_is_isomorphic():
                results.append(mol_id)
        return results
    
    def save(self) -> None:
        """持久化图数据（以边列表形式）."""
        data = {}
        for mol_id, g in self._graphs.items():
            data[mol_id] = {
                "smiles": self._smiles_map.get(mol_id, ""),
                "nodes": [
                    {"id": n, **g.nodes[n]} for n in g.nodes()
                ],
                "edges": [
                    {"u": u, "v": v, **g.edges[u, v]} for u, v in g.edges()
                ],
            }
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.graph_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _load(self) -> None:
        if not self.graph_path.exists():
            return
        try:
            with open(self.graph_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for mol_id, item in data.items():
                g = nx.Graph()
                for node in item.get("nodes", []):
                    nid = node.pop("id")
                    g.add_node(nid, **node)
                for edge in item.get("edges", []):
                    u = edge.pop("u")
                    v = edge.pop("v")
                    g.add_edge(u, v, **edge)
                self._graphs[mol_id] = g
                self._smiles_map[mol_id] = item.get("smiles", "")
        except Exception as e:
            logger.warning(f"Failed to load molecule graphs: {e}")
```

#### Task 3.2: RDKit 分子指纹内存检索

**修改文件**: `src/mbforge/core/mol_database.py`

```python
class MoleculeDatabase:
    # ... existing schema ...
    
    SCHEMA = """
    -- 现有表保留 ...
    
    -- 新增指纹表
    CREATE TABLE IF NOT EXISTS mol_fingerprints (
        mol_id TEXT PRIMARY KEY,
        morgan_fp BLOB,      -- 2048-bit Morgan fingerprint 二进制
        morgan_ecfp4 BLOB,   -- ECFP4 variant
        smiles TEXT,
        FOREIGN KEY (mol_id) REFERENCES molecules(mol_id)
    );
    """
    
    def _compute_fingerprint(self, smiles: str) -> Optional[bytes]:
        """计算 Morgan 指纹并序列化为 bytes."""
        if Chem is None or AllChem is None:
            return None
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        # 转为 numpy array 再序列化
        import numpy as np
        arr = np.zeros((1,), dtype=np.uint8)
        Chem.DataStructs.ConvertToNumpyArray(fp, arr)
        return arr.tobytes()
    
    def add_molecule(self, record: MoleculeRecord) -> None:
        """添加分子时同时计算指纹."""
        # ... existing code ...
        
        # 计算并存储指纹
        fp_blob = self._compute_fingerprint(record.smiles)
        if fp_blob is not None:
            self._conn.execute(
                "INSERT OR REPLACE INTO mol_fingerprints (mol_id, morgan_fp, smiles) VALUES (?, ?, ?)",
                (record.mol_id, fp_blob, record.smiles)
            )
        self._conn.commit()
    
    def search_by_similarity(self, smiles: str, threshold: float = 0.7, 
                            top_k: int = 20) -> List[Tuple[MoleculeRecord, float]]:
        """基于 Tanimoto 相似度的分子检索.
        
        使用 RDKit 内存计算，适合小规模（<10万）分子库。
        """
        if Chem is None or AllChem is None:
            return []
        
        query_mol = Chem.MolFromSmiles(smiles)
        if query_mol is None:
            return []
        query_fp = AllChem.GetMorganFingerprintAsBitVect(query_mol, 2, nBits=2048)
        
        rows = self._conn.execute(
            "SELECT mol_id, morgan_fp, smiles FROM mol_fingerprints WHERE morgan_fp IS NOT NULL"
        ).fetchall()
        
        results = []
        for mol_id, fp_blob, db_smiles in rows:
            if fp_blob is None:
                continue
            import numpy as np
            arr = np.frombuffer(fp_blob, dtype=np.uint8)
            db_fp = Chem.DataStructs.CreateFromBinaryText(arr.tobytes())
            similarity = Chem.DataStructs.TanimotoSimilarity(query_fp, db_fp)
            if similarity >= threshold:
                record = self.get_molecule(mol_id)
                if record:
                    results.append((record, similarity))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
```

#### Task 3.3: 子结构搜索工具实现

**修改文件**: `src/mbforge/agent/tools.py`

补齐 `search_by_substructure` placeholder：

```python
@tool("子结构搜索", {"smarts": {"type": "string", "description": "SMARTS 子结构模式"}})
def search_by_substructure(smarts: str) -> str:
    """在分子数据库中搜索包含指定子结构的分子."""
    from ..core.mol_database import MoleculeDatabase
    # 需要传入 mol_db 实例，这里简化为伪代码
    pass
```

实际实现需要在 `ToolExecutor` 初始化时注入 `mol_db` 实例。

---

### Phase 4: 配置与 UI 更新（3-5 天）

#### Task 4.1: 设置面板扩展

**修改文件**: `src/mbforge/ui/dialogs.py`

新增"AI 模型"设置标签页：
- Embedding 模型选择: `Qwen3-Embedding-0.6B` (默认) / `BAAI/bge-small-zh-v1.5` (fallback)
- Reranker 模型选择: `Qwen3-Reranker-0.6B` (默认) / `BAAI/bge-reranker-base` (fallback)
- OCR 后端选择: `GLM-OCR (MaaS)` / `GLM-OCR (Local)` / `PyMuPDF` (fallback)
- GLM-OCR API Key 输入框
- 模型缓存管理: 显示已下载模型大小，提供"清理缓存"按钮

#### Task 4.2: 环境变量支持

**修改文件**: `src/mbforge/utils/config.py`

```python
# 新增环境变量
MBFORGE_EMBED_MODEL = "Qwen/Qwen3-Embedding-0.6B"
MBFORGE_RERANK_MODEL = "Qwen/Qwen3-Reranker-0.6B"
MBFORGE_OCR_PROVIDER = "glm_ocr_maas"  # glm_ocr_maas | glm_ocr_local | pymupdf
MBFORGE_GLM_OCR_API_KEY = ""
```

---

## 四、测试计划

### 4.1 单元测试

| 测试项 | 验证内容 |
|--------|---------|
| Qwen3Embedder.embed | 输出维度=768，归一化验证，Instruction prefix 生效 |
| Qwen3Reranker.rerank | 返回排序列表，分数在 [0,1] 区间，query-doc 相关性正例分数 > 反例 |
| GlmOcrParser.parse_pdf | 返回包含 markdown/text/json 的 dict，表格非空时格式正确 |
| KnowledgeBase.keyword_search | FTS5 匹配结果包含 query 关键词 |
| KnowledgeBase.hybrid_search | 融合结果包含 vector 和 keyword 两路来源 |
| MoleculeGraph.subgraph_search | 已知子结构的 query 能正确匹配包含分子 |
| MoleculeDatabase.search_by_similarity | Tanimoto 分数计算正确，阈值过滤生效 |

### 4.2 集成测试

| 测试项 | 验证内容 |
|--------|---------|
| 完整索引流程 | PDF → GLM-OCR 解析 → 分块 → Embedding → ChromaDB + FTS5 |
| 完整检索流程 | 用户 query → Hybrid Search → Qwen3-Reranker → Agent 回答 |
| 分子检索流程 | SMILES 输入 → 子结构搜索 + 相似度搜索 → 结果融合 |
| 配置持久化 | 修改设置 → 重启应用 → 配置恢复正确 |

### 4.3 性能基准

| 指标 | 当前 (BGE-small) | 目标 (Qwen3-0.6B) | 测试方法 |
|------|-----------------|-------------------|---------|
| Embedding 速度 | ~100 docs/sec (CPU) | ~50 docs/sec (CPU) | 批量编码 1000 个 chunk |
| Rerank 延迟 (N=15) | ~200ms | ~500ms | 单次重排序 |
| 端到端检索 | ~1s | ~2s | 完整 query → result |
| 模型内存占用 | ~200MB | ~2.5GB | nvidia-smi / htop |

---

## 五、风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| Qwen3 模型下载失败（网络问题） | 中 | 高 | 提供 ModelScope 镜像下载选项；首次启动时引导用户下载 |
| transformers>=4.51.0 与现有代码冲突 | 低 | 高 | 在隔离环境测试；使用 uv 虚拟环境隔离 |
| GLM-OCR SDK 不稳定 | 中 | 中 | 保留 PyMuPDF 作为 fallback；异常时自动切换 |
| Qwen3-Reranker 推理速度过慢 | 中 | 中 | 限制 max_length=4096；candidate 数量控制在 20 以内；支持 CUDA 加速 |
| 模型内存占用过大（2.5GB+） | 中 | 高 | 支持 INT8 量化加载；提供模型选择 UI（小模型 / 大模型切换） |
| NetworkX 子图匹配过慢（>10万分子时） | 低 | 中 | 规模 <100 篇时无问题；未来规模增长时引入 vf2++ 优化或切换 Neo4j |

---

## 六、交付物清单

### 代码变更

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `pyproject.toml` | 修改 | 新增 transformers, glmocr 依赖 |
| `src/mbforge/utils/constants.py` | 修改 | 更新默认模型名，新增 provider 常量 |
| `src/mbforge/utils/config.py` | 修改 | 新增 OcrConfig，扩展 EmbedConfig/RerankConfig |
| `src/mbforge/models/embedding.py` | 修改 | 新增 Qwen3Embedder，支持 Instruction + MRL |
| `src/mbforge/models/rerank.py` | 修改 | 新增 Qwen3Reranker 分支 |
| `src/mbforge/models/rerank_qwen3.py` | 新增 | Qwen3-Reranker CausalLM 实现 |
| `src/mbforge/models/vlm.py` | 修改 | 新增 GlmOcrVLM / GlmOcrConfig |
| `src/mbforge/parsers/glm_ocr_parser.py` | 新增 | GLM-OCR 解析器封装 |
| `src/mbforge/parsers/pdf_parser.py` | 修改 | 增加 use_glm_ocr 选项 |
| `src/mbforge/core/knowledge_base.py` | 修改 | 新增 keyword_search, hybrid_search 融合逻辑 |
| `src/mbforge/core/mol_graph.py` | 新增 | NetworkX 分子图存储 + 子图匹配 |
| `src/mbforge/core/mol_database.py` | 修改 | 新增指纹表，similarity_search 方法 |
| `src/mbforge/agent/tools.py` | 修改 | 补齐子结构搜索工具 |
| `src/mbforge/ui/dialogs.py` | 修改 | 新增模型选择设置面板 |

### 文档

| 文件 | 说明 |
|------|------|
| `docs/RAG_TECHNICAL_ANALYSIS.md` | 技术分析报告（已完成） |
| `docs/RAG_IMPLEMENTATION_PLAN.md` | 本实施计划 |
| `docs/MODEL_INTEGRATION.md` | 模型集成指南（含 Qwen3/GLM-OCR 使用示例） |

---

## 七、时间线

```
Week 1 (Phase 0-1):
  Day 1-2: 依赖更新 + 配置扩展 + 模型下载验证
  Day 3-4: Qwen3-Embedding 集成 + 单元测试
  Day 5:   Qwen3-Reranker 集成 + 单元测试

Week 2 (Phase 1-2):
  Day 1-2: GLM-OCR 集成 + PDF 解析流程改造
  Day 3-4: Hybrid RAG (FTS5 + Vector 融合)
  Day 5:   集成测试 + 性能基准

Week 3 (Phase 3):
  Day 1-2: NetworkX 分子图存储
  Day 3-4: RDKit 指纹检索 + 子结构搜索
  Day 5:   UI 设置面板 + 端到端测试

Week 4 (收尾):
  Day 1-3: Bugfix + 性能优化
  Day 4:   文档完善
  Day 5:   Code Review + 合并
```

---

## 八、关键决策记录（补充）

### 决策 5: 为什么 Embedding 选 Qwen3-Embedding-0.6B 而不是 bge-m3？

- **用户指定**: 用户明确选择 Qwen3 系列，与 Reranker 形成配套。
- **模型配套优势**: Embedding 和 Reranker 同系列训练，语义空间对齐更好，融合效果优于跨系列组合。
- **尺寸适中**: 0.6B 比 bge-m3 (~2GB) 更小，比 bge-small (~100MB) 更大，是桌面应用的甜点。
- **32K 上下文**: 对长文档 chunk 更友好，减少截断损失。

### 决策 6: 为什么 Reranker 选 Qwen3-Reranker-0.6B（CausalLM）而不是 CrossEncoder？

- **用户指定**: 用户明确选择 Qwen3 系列配套。
- **架构差异**: CausalLM 重排序通过 yes/no 概率判断，与 CrossEncoder 的回归分数本质不同。对化学领域的"是/否"类判断（如"这段是否讨论了这个化合物"）可能更自然。
- **上下文长度**: 32K vs BGE-Reranker 的 512，长文档 chunk 不需要截断。
- **代价**: 推理速度较慢（CausalLM 前向传播 vs CrossEncoder），需要控制 candidate 数量。

### 决策 7: 为什么 OCR 选 GLM-OCR 而不是 MinerU？

- **用户指定**: 用户明确选择 GLM-OCR。
- **GLM-OCR 优势**: 
  - 0.9B 参数，比 MinerU 轻量
  - 两阶段版面分析（PP-DocLayout-V3）
  - 支持 MaaS API（无需本地 GPU）
  - MIT license，商用友好
  - 输出 Markdown/JSON 结构化结果
- **MinerU 劣势**: 依赖重（需 OCR 引擎、版面分析模型），对 PyInstaller 打包不友好。

### 决策 8: 为什么分子图存储选 NetworkX 而不是 Neo4j？

- **用户规模确认**: 用户明确项目规模 <100 篇文献，NetworkX 内存图完全胜任。
- **SMILES 局限**: 用户明确指出"SMILES 不能实现高效的子图匹配与搜索"，图结构是必要的。
- **NetworkX 优势**: 已在依赖列表中，零新增依赖，纯 Python，适合桌面应用。
- **Neo4j 延后**: 当规模增长至 >1000 篇或需要持久化图查询时再引入。

### 决策 9: 为什么分子指纹检索选内存方案（RDKit）？

- **轻量**: 不需要额外向量库，直接在 SQLite BLOB 中存储二进制指纹。
- **规模匹配**: <100 篇文献对应的分子数通常在数百到数千，RDKit 内存 Tanimoto 计算毫秒级。
- **未来扩展**: 规模增大时可迁移到 ChromaDB 多列向量或专门化学指纹库（如 chemfp）。
