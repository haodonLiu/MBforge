# MBForge API Reference

> 本文档详细描述 MBForge 所有公共 API 接口、类、函数及其用法。

**Related Documentation:** [Architecture](ARCHITECTURE.md) · [Development Guide](DEVELOPMENT.md) · [Tech Stack](TECH_STACK.md) · [References](../REFERENCES.md)

---

## Table of Contents

- [core](#core)
  - [Project](#project)
  - [DocumentEntry](#documententry)
  - [KnowledgeBase](#knowledgebase)
  - [MoleculeDatabase](#moleculedatabase)
  - [MoleculeRecord](#moleculerecord)
  - [DocumentProcessor](#documentprocessor)
  - [DocumentSummarizer](#documentsummarizer)
- [models](#models)
  - [Message](#message)
  - [StreamChunk](#streamchunk)
  - [BaseLLM](#basellm)
  - [OpenAILLM](#openllm)
  - [AnthropicLLM](#anthropicllm)
  - [create_llm_from_config](#create_llm_from_config)
  - [BaseEmbedder](#baseembedder)
  - [SentenceTransformerEmbedder](#sentencetransformerembedder)
  - [BaseReranker](#baseranker)
  - [BaseVLM](#basevlm)
- [parsers](#parsers)
  - [PDFParserPipeline](#pdfparserpipeline)
  - [MoleculeExtractor](#moleculeextractor)
- [agent](#agent)
  - [ProjectAgent](#projectagent)
  - [LayeredContext](#layeredcontext)
  - [ToolExecutor](#tool_executor)
  - [MemoryManager](#memorymanager)
  - [TrajectoryTracker](#trajectorytracker)
- [parser_io](#parser_io)
  - [ParserClient](#parserclient)
  - [ParseResult](#parseresult)
  - [ParserConfig](#parserconfig)
- [utils](#utils)
  - [AppConfig](#appconfig)
  - [ModelConfig](#modelconfig)
  - [EmbedConfig](#embedconfig)
  - [RerankConfig](#rerankconfig)
  - [load_global_config](#load_global_config)
  - [save_global_config](#save_global_config)

---

## core

### Project

```python
from mbforge.core.project import Project
```

Vault 机制项目管理器。每个文件夹即一个项目（Vault），`.mbforge/` 隐藏目录存储索引、配置、数据库。

#### `Project(root: Path)`

构造函数，打开已有项目或创建新实例。

```python
project = Project(Path("./my-project"))
```

#### `Project.create(root: Path, name: str = "") -> Project` *(classmethod)*

创建新项目。自动创建 `.mbforge/` 元数据目录和初始配置。

```python
project = Project.create(Path("./new-project"), name="MyProject")
```

#### `Project.open(root: Path) -> Optional[Project]` *(classmethod)*

打开已有项目。若目录不存在 `.mbforge/` 返回 `None`。

```python
project = Project.open(Path("./existing-project"))
```

#### `Project.is_valid_project(root: Path) -> bool` *(classmethod)*

检查目录是否为有效 MBForge 项目。

```python
if Project.is_valid_project(Path("./some-dir")):
    project = Project.open(Path("./some-dir"))
```

#### `project.name: str` *(property)*

项目名称。

#### `project.scan_files() -> List[DocumentEntry]`

扫描项目目录，更新文件索引。返回所有文档条目列表。

```python
entries = project.scan_files()
for entry in entries:
    print(entry.path, entry.doc_type, entry.indexed)
```

#### `project.add_file(path: Path) -> DocumentEntry`

手动添加文件到索引。

```python
entry = project.add_file(Path("./data/molecule.sdf"))
```

#### `project.remove_document(doc_id: str) -> None`

从索引移除文档（不删除实际文件）。

#### `project.list_documents(doc_type: Optional[str] = None) -> List[DocumentEntry]`

列出所有文档，或按类型过滤（`pdf`/`markdown`/`molecule`/`data`）。

```python
pdfs = project.list_documents(doc_type="pdf")
```

#### `project.get_document(doc_id: str) -> Optional[DocumentEntry]`

根据 ID 获取文档条目。

#### `project.get_document_by_path(path: Path) -> Optional[DocumentEntry]`

根据路径获取文档条目。

---

### DocumentEntry

```python
from mbforge.core.project import DocumentEntry
```

文件索引条目。包含路径、类型、标题、索引状态等信息。

#### `DocumentEntry.to_dict() -> Dict`

序列化为字典。

#### `DocumentEntry.from_dict(data: Dict, project_root: Path) -> DocumentEntry` *(classmethod)*

从字典反序列化。

---

### KnowledgeBase

```python
from mbforge.core.knowledge_base import KnowledgeBase
```

基于 ChromaDB 的向量知识库。

#### `KnowledgeBase(project_root: Path, embedder: Optional[BaseEmbedder] = None)`

构造函数。

```python
kb = KnowledgeBase(project.root, embedder=embedder)
```

#### `kb.index_document(doc_id: str, content: ExtractedContent, metadata: Optional[Dict] = None) -> None`

将文档内容索引到知识库。自动分块、生成向量（如 embedder 可用）。

```python
kb.index_document(doc_id, content, metadata={"source": str(pdf_path)})
```

#### `kb.search(query: str, top_k: int = 5, filter_dict: Optional[Dict] = None) -> List[Dict[str, Any]]`

语义搜索。返回列表，每项包含 `id`、`text`、`metadata`、`distance`。

```python
results = kb.search("分子对接", top_k=10)
for r in results:
    print(r["text"], r["distance"])
```

#### `kb.hybrid_search(query: str, top_k: int = 5, reranker: Optional[BaseReranker] = None) -> List[Dict[str, Any]]`

语义搜索 + Rerank 重排序。先检索 3×top_k 再重排。

```python
results = kb.hybrid_search("蛋白酶抑制剂", top_k=5, reranker=reranker)
```

#### `kb.remove_document(doc_id: str) -> None`

移除文档的所有索引。

#### `kb.get_stats() -> Dict[str, Any]`

获取知识库统计信息（总 chunk 数、数据库路径）。

---

### MoleculeDatabase

```python
from mbforge.core.mol_database import MoleculeDatabase
```

SQLite + RDKit 分子数据库。

#### `MoleculeDatabase(project_root: Path)`

构造函数。

```python
mol_db = MoleculeDatabase(project.root)
```

#### `mol_db.add_molecule(record: MoleculeRecord) -> None`

添加或更新分子记录。自动计算分子性质（MW、LogP、TPSA 等）。

```python
mol_db.add_molecule(record)
```

#### `mol_db.get_molecule(mol_id: str) -> Optional[MoleculeRecord]`

根据 ID 获取分子记录。

#### `mol_db.search_by_smiles(smiles: str) -> Optional[MoleculeRecord]`

根据 SMILES 精确搜索。

#### `mol_db.search_by_source(doc_id: str) -> List[MoleculeRecord]`

搜索来自指定文档的所有分子。

#### `mol_db.search_by_activity_range(min_val: float, max_val: float, activity_type: str = "") -> List[MoleculeRecord]`

按活性值范围搜索（如 IC50 < 100 nM）。

```python
potent = mol_db.search_by_activity_range(0, 100, activity_type="IC50")
```

#### `mol_db.list_all(limit: int = 1000) -> List[MoleculeRecord]`

列出所有分子记录。

#### `mol_db.delete_molecule(mol_id: str) -> None`

删除分子记录。

#### `mol_db.get_stats() -> Dict[str, Any]`

获取统计信息（总数、带活性数据的分子数）。

---

### MoleculeRecord

```python
from mbforge.core.mol_database import MoleculeRecord
```

分子记录数据类。

#### 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `mol_id` | `str` | 唯一标识符 |
| `smiles` | `str` | SMILES 结构 |
| `name` | `str` | 分子名称 |
| `source_doc` | `str` | 来源文档 ID |
| `activity` | `Optional[float]` | 活性值 |
| `activity_type` | `str` | 活性类型（IC50/EC50/Ki） |
| `units` | `str` | 单位（默认 nM） |
| `properties` | `Dict[str, Any]` | RDKit 计算的性质 |
| `tags` | `List[str]` | 标签 |
| `notes` | `str` | 备注 |

#### `record.compute_properties() -> Dict[str, float]`

使用 RDKit 计算分子性质：MW、LogP、HBD、HBA、TPSA、RotatableBonds。

#### `record.mol` *(property)*

返回 RDKit Mol 对象。

---

### DocumentProcessor

```python
from mbforge.core.document import DocumentProcessor, ExtractedContent
```

文档内容提取器，支持 PDF、Markdown、文本文件。

#### `DocumentProcessor.process(file_path: Path) -> ExtractedContent`

处理单个文件，返回 `ExtractedContent`。

#### `DocumentProcessor.extract_pdf_images(pdf_path: Path, output_dir: Path) -> List[Path]`

从 PDF 提取所有图片到指定目录。返回图片路径列表。

---

### DocumentSummarizer

```python
from mbforge.core.summarizer import DocumentSummarizer, SummaryManager
```

LLM 驱动的文档摘要生成器，支持 L0/L1/L2 三层摘要。

#### `DocumentSummarizer(llm: Optional[BaseLLM] = None)`

构造函数。

#### `summarizer.summarize(content: ExtractedContent, doc_id: str) -> Summary`

生成三层摘要。

---

## models

### Message

```python
from mbforge.models.base import Message
```

对话消息数据结构。

```python
msg = Message(
    role="user",
    content="查找 IC50 < 100nM 的分子",
    attachments=["path/to/image.png"],  # 可选，用于 VLM
)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `role` | `str` | `system`/`user`/`assistant`/`tool` |
| `content` | `str` | 消息内容 |
| `attachments` | `Optional[List[str]]` | 附件路径（VLM 用） |
| `tool_call_id` | `Optional[str]` | 工具调用 ID |
| `name` | `Optional[str]` | 工具名（tool 消息） |
| `tool_calls` | `Optional[List]` | 工具调用列表（assistant 消息） |

### StreamChunk

```python
from mbforge.models.base import StreamChunk
```

流式输出块。

| 字段 | 类型 | 说明 |
|------|------|------|
| `delta` | `str` | 本次增量文本 |
| `finish_reason` | `Optional[str]` | 结束原因（stop/tool_calls） |

---

### BaseLLM

```python
from mbforge.models.base import BaseLLM
```

LLM 抽象基类。所有 LLM 实现必须继承此类。

#### Abstract Methods

```python
def chat(self, messages: List[Message], **kwargs) -> str
def chat_stream(self, messages: List[Message], **kwargs) -> Iterator[StreamChunk]
async def achat(self, messages: List[Message], **kwargs) -> str
async def achat_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[StreamChunk, None]
```

---

### OpenAILLM

```python
from mbforge.models.llm import OpenAILLM
```

OpenAI 兼容 API 的 LLM 实现（支持 vLLM、Ollama、硅基流动等）。

#### `OpenAILLM(base_url: str = "http://localhost:8000/v1", api_key: str = "", model_name: str = "default", max_tokens: int = 4096, temperature: float = 0.7, top_p: float = 0.9)`

构造函数。

```python
llm = OpenAILLM(
    base_url="http://localhost:8000/v1",
    api_key="dummy",
    model_name="Qwen2.5-7B-Instruct",
    temperature=0.7,
)
response = llm.chat([Message(role="user", content="Hello")])
```

#### `llm.chat(messages: List[Message], **kwargs) -> str`

同步对话，返回完整回复。

#### `llm.chat_stream(messages: List[Message], **kwargs) -> Iterator[StreamChunk]`

同步流式对话。

```python
for chunk in llm.chat_stream(messages):
    print(chunk.delta, end="", flush=True)
```

---

### AnthropicLLM

```python
from mbforge.models.anthropic_llm import AnthropicLLM
```

Anthropic Claude 系列 LLM 实现。

#### `AnthropicLLM(base_url: str = "", api_key: str = "", model_name: str = "claude-sonnet-4-20250514", max_tokens: int = 4096, temperature: float = 0.7, top_p: float = 0.9)`

构造函数。

#### `llm.call_with_tools(messages: List[Message], tools: List[Dict], **kwargs) -> Any`

带工具调用的对话（Anthropic tool use 协议）。

---

### create_llm_from_config

```python
from mbforge.models import create_llm_from_config
```

工厂函数，根据配置创建 LLM 实例。

```python
from mbforge.utils.config import load_global_config
config = load_global_config()
llm = create_llm_from_config(config.llm)
```

---

### BaseEmbedder

```python
from mbforge.models.base import BaseEmbedder
```

Embedding 模型抽象基类。

#### Abstract Methods

```python
def embed(self, texts: List[str]) -> List[List[float]]
async def aembed(self, texts: List[str]) -> List[List[float]]
```

---

### SentenceTransformerEmbedder

```python
from mbforge.models.embedding import SentenceTransformerEmbedder
```

基于 sentence-transformers 的本地 Embedding 实现。

#### `SentenceTransformerEmbedder(model_name: str = "BAAI/bge-small-zh-v1.5", device: str = "cpu")`

构造函数。默认使用中文 BGE 小模型。

```python
embedder = SentenceTransformerEmbedder(
    model_name="BAAI/bge-small-zh-v1.5",
    device="cpu",
)
vectors = embedder.embed(["分子对接", "蛋白酶抑制剂"])
```

---

### BaseReranker

```python
from mbforge.models.base import BaseReranker
```

Rerank 模型抽象基类。

#### Abstract Method

```python
def rerank(self, query: str, passages: List[str]) -> List[tuple[int, float]]
```

返回 `(原始索引, 分数)` 列表，按分数降序排列。

---

### BaseVLM

```python
from mbforge.models.base import BaseVLM
```

视觉语言模型抽象基类。

#### Abstract Methods

```python
def describe_image(self, image_path: str, prompt: str = "") -> str
def describe_pdf_page(self, image_path: str, context: str = "") -> str
```

---

## parsers

### PDFParserPipeline

```python
from mbforge.parsers.pdf_parser import PDFParserPipeline
```

PDF 解析与处理流水线。

#### `PDFParserPipeline(llm: Optional[BaseLLM] = None, embedder: Optional[BaseEmbedder] = None, vlm: Optional[BaseVLM] = None, knowledge_base: Optional[KnowledgeBase] = None, mol_db: Optional[MoleculeDatabase] = None)`

构造函数，所有组件可选。

```python
pipeline = PDFParserPipeline(
    llm=llm,
    embedder=embedder,
    knowledge_base=kb,
    mol_db=mol_db,
)
```

#### `pipeline.parse(pdf_path: Path, doc_id: str = "", extract_molecules: bool = True, summarize: bool = True, index_kb: bool = True) -> ExtractedContent`

解析单个 PDF 文件。完整流程：提取文本/图片 → VLM 分析 → LLM 摘要 → 分子提取 → 知识库索引。

```python
content = pipeline.parse(Path("./paper.pdf"), doc_id="paper-001")
print(content.summary)
print(content.molecules)
```

---

### MoleculeExtractor

```python
from mbforge.parsers.molecule_extractor import MoleculeExtractor
```

从文本中提取分子结构（SMILES）和活性数据。

#### `MoleculeExtractor(llm: Optional[BaseLLM] = None)`

构造函数。LLM 用于复杂化学命名到 SMILES 的转换。

#### `extractor.extract_from_text(text: str, doc_id: str = "") -> List[MoleculeRecord]`

从文本提取分子记录列表。

---

## agent

### ProjectAgent

```python
from mbforge.agent.agent import ProjectAgent
```

项目级 AI Agent，基于 ReAct 循环。

#### `ProjectAgent(llm: Optional[BaseLLM] = None, tool_executor: Optional[ToolExecutor] = None, system_prompt: str = "", max_iterations: int = 5, project_root: Optional[Path] = None)`

构造函数。

```python
agent = ProjectAgent(
    llm=llm,
    tool_executor=executor,
    project_root=project.root,
)
```

#### `agent.chat(user_input: str) -> str`

同步对话（ReAct 循环，最多 `max_iterations` 次工具调用）。

```python
response = agent.chat("查找项目中 IC50 小于 100nM 的分子")
print(response)
```

#### `agent.chat_stream(user_input: str)`

流式对话生成器。先判断是否需要工具，执行后再流式输出最终答案。

```python
for delta in agent.chat_stream("查找活性分子"):
    print(delta, end="", flush=True)
```

#### `agent.extract_memory() -> None`

从当前对话历史自动提取记忆（需 `memory_manager` 初始化）。

#### `agent.clear() -> None`

清空对话历史。

---

### LayeredContext

```python
from mbforge.agent.context import LayeredContext
```

分层上下文管理器。组织结构：system → project → memory → history。

#### `LayeredContext(system_prompt: str = "", max_history_rounds: int = 20)`

构造函数。

#### `context.add_user_message(content: str) -> None`

添加用户消息。

#### `context.add_assistant_message(content: str, tool_calls: Optional[List] = None) -> None`

添加助手消息。

#### `context.add_tool_result(name: str, result: str, tool_call_id: str = "") -> None`

添加工具执行结果。

#### `context.inject_memory(text: str) -> None`

注入用户记忆到 memory 层。

#### `context.inject_agent_memory(text: str) -> None`

注入 Agent 经验到 memory 层。

#### `context.build_messages(include_tools: bool = True) -> List[Message]`

构建完整的消息列表，供 LLM 调用。

---

### ToolExecutor

```python
from mbforge.agent.executor import ToolExecutor
```

工具执行器。包含工具注册表和执行逻辑。

#### `executor.registry.list_tools() -> List[Tool]`

列出所有已注册工具。

#### `executor.registry.to_openai_schemas() -> List[Dict]`

导出为 OpenAI function calling schema。

#### `executor.registry.call(name: str, args: Dict) -> str`

执行指定名称的工具调用。

---

### MemoryManager

```python
from mbforge.agent.memory_manager import MemoryManager
```

Agent 记忆管理器。基于 6 类记忆模板。

#### `MemoryManager(project_root: Path)`

构造函数。

#### `mm.get_user_profile_text() -> str`

获取用户画像文本（注入 system prompt）。

#### `mm.get_agent_memory_text() -> str`

获取 Agent 经验文本。

#### `mm.extract_from_conversation(messages: List[Message], llm: BaseLLM) -> None`

从对话历史自动提取和更新记忆。

---

### TrajectoryTracker

```python
from mbforge.agent.trajectory import TrajectoryTracker
```

检索轨迹跟踪器，记录 Agent 的工具调用历史。

#### `TrajectoryTracker(project_root: Path)`

构造函数。

#### `tt.record_tool(name: str, arguments: Dict, result_preview: str) -> None`

记录单次工具调用。

---

## parser_io

### UniParser 服务信息

| 项目 | 地址/说明 |
|------|-----------|
| **API 基础地址** | `https://uniparser.dp.tech` |
| **API 文档页面** | `https://uniparser.dp.tech/api` |
| **Python SDK** | `UniParser-Tools/`（本地子模块） |
| **认证方式** | 请求头 `X-API-Key` |

> 在 `.env` 中配置 `UNIPARSER_HOST` 和 `UNIPARSER_API_KEY` 后，`load_config()` 会自动读取。

### ParserClient

```python
from mbforge.parser_io.client import ParserClient
```

UniParser API 客户端封装。基于 `UniParser-Tools` 的 `UniParserClient` 进行高层封装，支持同步/异步解析、轮询等待和格式化结果获取。

#### `ParserClient(config: ParserConfig)`

构造函数。

```python
from mbforge.parser_io.config import load_config
config = load_config()
client = ParserClient(config)
```

#### `client.parse_pdf(pdf_path: Union[str, Path], *, sync: bool = True, textual: int = 2, table: int = 2, equation: int = 2, chart: int = -1, figure: int = -1, expression: int = -1, molecule: int = 1, **kwargs) -> ParseResult`

触发 PDF 解析请求。默认配置为科学文献推荐：高质 OCR + 快速分子识别。

```python
result = client.parse_pdf("./paper.pdf", sync=True)
print(result.token)
```

#### `client.get_result(token: str, *, content: bool = True, objects: bool = False, molecule_source: bool = False) -> Dict[str, Any]`

获取解析结果（轮询模式）。

#### `client.get_formatted(token: str, *, content: bool = True, textual: int = 4, table: int = 4, equation: int = 4) -> Dict[str, Any]`

获取格式化结果（Markdown）。

#### `client.parse_and_wait(pdf_path: Union[str, Path], *, timeout: int = 300, poll_interval: int = 2, **kwargs) -> ParseResult`

异步解析并等待完成。

```python
result = client.parse_and_wait("./paper.pdf", timeout=300)
```

#### `client.health() -> Dict[str, Any]`

检查服务健康状态。

---

### ParseResult

```python
from mbforge.parser_io.models import ParseResult
```

解析结果数据类。

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | `str` | 状态（pending/completed/failed） |
| `token` | `str` | 解析任务 token |
| `raw_data` | `Dict[str, Any]` | 原始响应数据 |

---

## utils

### AppConfig

```python
from mbforge.utils.config import AppConfig
```

全局应用配置数据类。

| 字段 | 类型 | 说明 |
|------|------|------|
| `llm` | `ModelConfig` | LLM 配置 |
| `embed` | `EmbedConfig` | Embedding 配置 |
| `rerank` | `RerankConfig` | Rerank 配置 |
| `vlm` | `VLMConfig` | VLM 配置 |
| `recent_projects` | `list[str]` | 最近项目路径列表 |
| `theme` | `str` | 主题（dark/light） |
| `language` | `str` | 语言（zh/en） |

---

### ModelConfig

```python
from mbforge.utils.config import ModelConfig
```

LLM 模型配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `provider` | `str` | `openai_compatible` | 提供商 |
| `base_url` | `str` | `http://localhost:8000/v1` | API 地址 |
| `api_key` | `str` | `""` | API 密钥 |
| `model_name` | `str` | `"default"` | 模型名 |
| `max_tokens` | `int` | `4096` | 最大 token 数 |
| `temperature` | `float` | `0.7` | 温度参数 |
| `top_p` | `float` | `0.9` | top_p 参数 |

---

### EmbedConfig

```python
from mbforge.utils.config import EmbedConfig
```

Embedding 模型配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `provider` | `str` | `sentence_transformers` | 提供商 |
| `model_name` | `str` | `BAAI/bge-small-zh-v1.5` | 模型名 |
| `base_url` | `str` | `""` | API 地址（OpenAI/自定义） |
| `api_key` | `str` | `""` | API 密钥 |
| `device` | `str` | `"cpu"` | 设备（cpu/cuda） |

---

### RerankConfig

```python
from mbforge.utils.config import RerankConfig
```

Rerank 模型配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `provider` | `str` | `sentence_transformers` | 提供商 |
| `model_name` | `str` | `BAAI/bge-reranker-base` | 模型名 |
| `device` | `str` | `"cpu"` | 设备（cpu/cuda） |

---

### load_global_config

```python
from mbforge.utils.config import load_global_config
```

加载全局配置。优先级：内存缓存 → 配置文件 → 环境变量 → 默认值。

```python
config = load_global_config()
print(config.llm.model_name)
```

---

### save_global_config

```python
from mbforge.utils.config import save_global_config
```

保存全局配置到 `~/.config/MBForge/config.json`。

```python
save_global_config(config)
```
