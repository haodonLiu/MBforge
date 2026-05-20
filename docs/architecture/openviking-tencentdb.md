# OpenViking & TencentDB-Agent-Memory 架构参考

本文档记录 MBForge 中参考 [OpenViking](https://github.com/volcengine/OpenViking) 和 [TencentDB-Agent-Memory](https://github.com/Tencent/TencentDB-Agent-Memory) 实现的核心机制。

## 1. 六类记忆系统

**实现文件：** `src/mbforge/agent/memory_manager.py`

参考 OpenViking 的记忆分类，将 Agent 的长期记忆分为 6 类：

| 类别 | 用途 | 示例 |
|------|------|------|
| `profile` | 用户基本信息 | 用户名、研究方向、专业背景 |
| `preferences` | 用户偏好（按主题） | 偏好的 LLM 模型、回答风格、语言 |
| `entities` | 实体记忆 | 关注的分子、蛋白、项目名 |
| `events` | 事件记录 | 决策记录、里程碑、重要对话 |
| `cases` | Agent 学习案例 | 成功的检索策略、有效的提问方式 |
| `patterns` | Agent 学习模式 | 用户常问的问题类型、常用工具组合 |

### 数据模型

```python
@dataclass
class MemoryEntry:
    category: str       # 类别名
    key: str            # 记忆键（如 "user_name", "preferred_model"）
    content: str        # 记忆内容
    confidence: float   # 置信度 0-1
    source: str         # 来源（如 "conversation:msg_id"）
    created_at: str     # 创建时间
    updated_at: str     # 更新时间
    access_count: int   # 被检索次数
```

### 存储

- 路径：`.mbforge/memory/<category>.json`
- 每个类别一个 JSON 文件，数组存储
- 内存缓存 + 写时持久化

### 记忆自迭代（TencentDB 机制）

`extract_from_conversation()` 方法在对话结束后自动从历史中提取记忆：

1. 取最近 10 条消息
2. 构造 prompt 让 LLM 分析对话，输出 JSON 格式的记忆条目
3. 解析 JSON，按类别写入记忆存储

这一机制参考了 TencentDB-Agent-Memory 的"记忆自迭代"理念：Agent 在每次对话后自动学习和积累经验，而非依赖手动配置。

## 2. 检索轨迹系统

**实现文件：** `src/mbforge/agent/trajectory.py`

参考 OpenViking 的轨迹可视化，记录 Agent 的每一步检索行为，形成可追溯的 `viking://` 路径。

### 轨迹步骤

```python
@dataclass
class TrajectoryStep:
    step_type: str      # search | navigate | read | abstract | overview | tool
    uri: str            # viking:// 风格路径
    query: str          # 原始查询
    result_count: int   # 返回结果数
    top_results: list   # 结果摘要
    duration_ms: float  # 耗时
    timestamp: str      # 时间戳
    metadata: dict      # 附加信息
```

### URI 方案

| 步骤类型 | URI 格式 | 示例 |
|----------|----------|------|
| search | `viking://kb/search?q=<query>` | `viking://kb/search?q=aspirin` |
| navigate | `viking://project/<path>` | `viking://project/raw/paper.pdf` |
| read | `viking://docs/<doc_id>?level=<level>` | `viking://docs/abc123?level=abstract` |
| tool | `viking://tools/<tool_name>` | `viking://tools/list_documents` |

### 用途

- **结果可解释性**：用户可追溯 Agent 的检索路径
- **检索策略优化**：分析哪些检索路径有效
- **Agent 模式学习**：记录成功的工具调用模式

### 存储

- 路径：`.mbforge/memory/trajectory.json`
- 保留最近 500 步，自动裁剪

## 3. 三层文档摘要

**实现文件：** `src/mbforge/core/summarizer.py`

参考 OpenViking 的分层摘要机制，为每篇文档生成三个层次的摘要：

| 层次 | 长度 | 用途 | 存储 |
|------|------|------|------|
| L0 Abstract | ~100 tokens | 一句话核心摘要，用于快速过滤 | 摘要 JSON |
| L1 Overview | ~2000 tokens | 结构化概览，用于 Rerank 精排 | 摘要 JSON |
| L2 Detail | 完整内容 | 按需加载，不预生成 | 原始文本引用 |

### L1 结构化概览格式

LLM 生成的 L1 摘要包含：
1. 研究背景与目的
2. 主要方法与实验设计
3. 关键结果与发现
4. 涉及的分子/化合物列表
5. 生物活性数据摘要

### 存储

- 路径：`.mbforge/summaries/<doc_id>.json`
- 包含 keywords（高频词提取）和 entity_tags（分子名等）

## 4. 目录级语义检索

**实现文件：** `src/mbforge/core/knowledge_base.py` — `search_by_directory()`

参考 OpenViking 的递归目录检索：

1. 先执行全库语义搜索（扩大候选集 3x）
2. 按路径前缀过滤，保留目标目录下的结果
3. 返回 top-k 结果

```python
def search_by_directory(self, query, directory_prefix="", top_k=5):
    results = self.search(query, top_k=top_k * 3)
    if directory_prefix:
        results = [r for r in results if prefix_match(r, directory_prefix)]
    return results[:top_k]
```

## 5. 与 Agent 的集成

### 注入时机

Agent 初始化时（`ProjectAgent.__init__`）：

1. `MemoryManager.get_user_profile_text()` → 注入用户画像到项目上下文
2. `MemoryManager.get_agent_memory_text()` → 注入 Agent 学习经验
3. `TrajectoryTracker` → 记录每步工具调用

### 对话结束后

`extract_memory()` 方法自动从对话历史提取新记忆。

### Agent 可用工具

工具注册在 `src/mbforge/agent/tools.py`，通过 `ToolExecutor` 暴露给 LLM：

- `search_knowledge_base` — 语义搜索知识库
- `find_documents` — 按类型查找文档
- `read_document_abstract` — 读取 L0 摘要
- `read_document_overview` — 读取 L1 概览
- `read_document_detail` — 读取完整内容
- `list_molecules` — 列出分子数据库
- `search_molecule_by_smiles` — 按 SMILES 搜索分子
- `list_documents` — 列出所有文档
- `get_document_summary` — 获取文档摘要
- `get_project_info` — 获取项目信息

## 6. 依赖关系

```
Agent (agent.py)
├── MemoryManager (memory_manager.py)  ← OpenViking 6 类记忆
├── TrajectoryTracker (trajectory.py)  ← OpenViking 轨迹
├── LayeredContext (context.py)         ← 对话上下文管理
└── ToolExecutor (executor.py)         ← 工具注册与执行

KnowledgeBase (knowledge_base.py)
├── SummaryManager (summarizer.py)     ← OpenViking 三层摘要
└── ChromaDB 向量存储

PDFParserPipeline (pdf_parser.py)
├── DocumentProcessor (document.py)    ← PyMuPDF 文本/图片提取
├── MoleculeExtractor (molecule_extractor.py)
├── DocumentSummarizer (summarizer.py) ← LLM 摘要生成
├── KnowledgeBase → ChromaDB
└── MoleculeDatabase → SQLite
```
