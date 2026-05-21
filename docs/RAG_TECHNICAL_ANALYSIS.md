# MBForge RAG 技术选型分析报告

> 基于《RAG 技术选型深度指南：17 种方案详解与工程实践补充》对 MBForge 现有 RAG 架构进行差距分析，提出改进路径与技术选型建议。
>
> **分析日期**: 2026-05-21  
> **参考文档**: `C:\Users\10954\Downloads\rag_technical_selection_guide.md`  
> **项目版本**: MBForge v0.2.0 (src/mbforge/)

---

## 一、项目 RAG 现状总览

### 1.1 已有能力矩阵

MBForge 并非"需要从零构建 RAG"的项目——它已经拥有一个**功能完整、架构清晰**的 RAG 流水线，覆盖从文档解析到 Agent 对话的全链路：

| 组件 | 当前实现 | 成熟度 |
|------|---------|--------|
| **文档解析** | PyMuPDF (fitz) 提取文本+图像；可选 VLM 图像描述；UniParser API 备选 | ⭐⭐⭐⭐ |
| **文本分块** | `split_text_chunks()` — 字符数限制(512)+边界感知(换行/句号/空格)，重叠 128 | ⭐⭐⭐ |
| **Embedding** | `BAAI/bge-small-zh-v1.5` (512-dim, local) + OpenAI-compatible API embedder | ⭐⭐⭐⭐ |
| **向量数据库** | ChromaDB `PersistentClient`, cosine 距离, metadata 过滤 | ⭐⭐⭐⭐ |
| **语义检索** | `KnowledgeBase.search()` — ANN 近似最近邻 | ⭐⭐⭐⭐ |
| **重排序** | `KnowledgeBase.hybrid_search()` — 先召回 top_k×3，再用 `BAAI/bge-reranker-base` CrossEncoder 精排 | ⭐⭐⭐⭐ |
| **LLM 生成** | OpenAI-compatible / Anthropic Claude / local vLLM，支持 stream | ⭐⭐⭐⭐ |
| **Agent** | ReAct 循环，最多 5 轮，10 个工具 (KB 搜索/分子搜索/文档读取/性质计算等) | ⭐⭐⭐⭐ |
| **分层上下文** | `LayeredContext` — System → Project → Memory → Tool Results → History | ⭐⭐⭐⭐⭐ |
| **记忆系统** | 6 类记忆 (User profile / Agent exp / Project summary / Recent context / Entity knowledge / Session summary)，参考 TencentDB-Agent-Memory | ⭐⭐⭐⭐ |
| **文档摘要** | L0 Abstract (~100 tokens) / L1 Overview (~2000 tokens) / L2 Detail (chunks)，参考 OpenViking | ⭐⭐⭐⭐ |
| **分子提取** | 正则提取 SMILES + 活性数据 (IC50/EC50/Ki)，LLM 辅助化学名→SMILES | ⭐⭐⭐ |
| **分子数据库** | SQLite + FTS5 全文搜索 + RDKit 性质计算 | ⭐⭐⭐⭐ |
| **多格式支持** | PDF, Markdown, TXT, SDF, MOL, MOL2, PDB, SMI, CSV, XLSX, JSON | ⭐⭐⭐⭐⭐ |

### 1.2 架构亮点

1. **Vault 设计**: 每个项目独立目录，`.mbforge/` 下自包含 ChromaDB + SQLite + summaries + memories，天然隔离，便于迁移和备份。
2. **策略模式**: `FileProcessStrategy` 统一处理 11 种文件类型，`extract → index → store` 流程一致。
3. **模型抽象层**: `BaseLLM` / `BaseEmbedder` / `BaseReranker` / `BaseVLM` 接口清晰，切换 provider 成本极低。
4. **离线优先**: sentence-transformers + ChromaDB 纯本地运行，无需外部服务即可使用核心功能。

---

## 二、参考项目技术特点（RAG 技术选型指南 17 种方案）

以下是对指南中 17 种 RAG 方案的核心技术特点提炼，以及**在化学/药物发现场景中的适用性评估**：

### 2.1 基础分块与语义优化

| # | 方案 | 核心技术特点 | 化学场景适用性 |
|---|------|-------------|--------------|
| 1 | **Simple RAG** | 固定长度切块，无语义理解 | 基础能力，化学文献中易切断 SAR 讨论和合成路线描述 |
| 2 | **Semantic Chunking** | 基于 spaCy/HanLP 句法分析，在语义边界切分；需领域术语词典 | ⭐⭐⭐⭐⭐ **高价值** — 保持化合物系列、SAR 表格、机制描述的完整性 |
| 3 | **Chunk Overlap** | 相邻 chunk 重叠 15%-30%，降低跨块信息断裂 | ⭐⭐⭐⭐ 技术文档推荐 15-20% 重叠；当前 128/512=25% 略偏高，可能引入冗余 |
| 4 | **Contextual Chunking** | 每个 chunk 注入元信息（文档标题、章节路径、实体标签、关键词） | ⭐⭐⭐⭐⭐ **高价值** — 注入"靶点蛋白、assay 类型、化合物类别"可大幅提升检索精度 |

### 2.2 检索策略优化

| # | 方案 | 核心技术特点 | 化学场景适用性 |
|---|------|-------------|--------------|
| 5 | **Hybrid RAG** | Keyword (BM25/ES) + Vector (ANN) + Graph (图谱遍历) 三路融合 | ⭐⭐⭐⭐⭐ **极高价值** — 化学名精确匹配 + 语义相似 + 化合物-靶点关系图，三重互补 |
| 6 | **Multi-Query RAG** | LLM 改写生成同义 query，扩展检索面 | ⭐⭐⭐⭐ "imatinib" ↔ "STI-571" ↔ "Gleevec" 多命名覆盖；但增加 LLM 调用成本 |
| 7 | **Rerank RAG** | CrossEncoder 精排，N=50 时延迟 100-300ms；推荐粗排+精排两级 | ⭐⭐⭐⭐ 当前已实现但 candidate 规模小 (top_k×3=15)；粗排阶段缺失 |
| 8 | **Filtered RAG** | Pre-filter 在检索前过滤（权限、时效、属性范围） | ⭐⭐⭐⭐⭐ **高价值** — 按 assay 类型、活性范围、分子量范围预过滤 |

### 2.3 进阶增强方案

| # | 方案 | 核心技术特点 | 化学场景适用性 |
|---|------|-------------|--------------|
| 9 | **Hierarchical RAG** | 文档→章节→段落 分层导航，长文档 (>100 页) 准确率提升 13% | ⭐⭐⭐⭐ 专利、综述论文常有 100+ 页；MinerU 可自动提取标题层级 |
| 10 | **Fused RAG** | 多来源/多模态分数融合，需 Z-score/Min-Max 归一化 | ⭐⭐⭐⭐⭐ **极高价值** — 文本嵌入 + 分子指纹 (Morgan/Tanimoto) + 活性向量 三路融合 |
| 11 | **Self-RAG** | LLM 自我评估"是否需要检索""结果是否相关""答案是否准确" | ⭐⭐⭐ 成本高昂；仅对高价值决策（如候选化合物选择）启用 |
| 12 | **Knowledge-Enhanced RAG (GraphRAG)** | Neo4j 存储实体关系；共现边策略简化关系抽取；双存储 Neo4j+Milvus | ⭐⭐⭐⭐⭐ **极高价值** — 化合物→靶点→疾病→骨架→ADMET 知识图谱是多跳推理基础 |

### 2.4 前沿探索方案

| # | 方案 | 核心技术特点 | 化学场景适用性 |
|---|------|-------------|--------------|
| 13 | **Adaptive RAG** | 查询复杂度分级：简单→Simple RAG；中等→Hybrid；复杂→Agent+Graph | ⭐⭐⭐⭐⭐ **高价值** — "clogP 是多少"走快路径，"骨架 A vs B 的选择性差异"走复杂路径 |
| 14 | **Streaming RAG** | 增量解析入库，边解析边检索；流式 LLM 输出中断-续写机制 | ⭐⭐⭐ 对新文献实时监控有价值，但桌面应用场景需求不高 |
| 15 | **Cross-Modal RAG** | VLM 描述图像→嵌入；双图构建（跨模态 KG + 文本 KG）；视觉内容恢复 | ⭐⭐⭐⭐⭐ **极高价值** — 专利/论文中大量化学结构以图像形式存在，SMILES 不一定在文本中 |
| 16 | **Agent-RAG** | ReAct Agent 多跳推理；工具粒度设计（search/neighbors/filter/describe） | ⭐⭐⭐⭐⭐ **极高价值** — 当前已有基础，可扩展为更复杂的多跳 SAR 分析 |
| 17 | **Personalized RAG** | 用户画像与图谱结合；角色导向检索优先级 | ⭐⭐⭐ 合成化学家 vs 药物化学家 vs 计算化学家的检索偏好不同 |

---

## 三、差距分析：当前实现 vs 前沿方案

### 3.1 分块层（Chunking）— 中等差距

**当前状态**: `split_text_chunks()` 是**基于字符数+简单边界**的 Simple RAG，默认 512 字符、128 重叠。

**问题**:
1. **化学文献特殊结构未处理**: SMILES 字符串、化学方程式、IC50 表格容易被从中间切断。
2. **无上下文元信息注入**: chunk 只包含 `doc_id`, `source`, `chunk_index`, `chunk_hash`，缺少"所属章节""文档类型""涉及的分子列表"等。
3. **重叠比例偏高**: 128/512 = 25%，对于技术密集型的化学文献，指南建议 15-20%。

**改进方向**:
- 引入 **Semantic Chunking**: 先识别化学实体（SMILES、IUPAC 名、靶点名），再在实体边界处切分。
- 引入 **Contextual Chunking**: 每个 chunk 头部注入 `"[Document: {title}] [Section: {heading}] [Molecules: {entity_tags}]"`。
- 为 PDF 引入 **Hierarchical Chunking**: 利用 PyMuPDF 提取的标题层级（Heading 1/2/3），构建文档树后再切分。

### 3.2 检索层（Retrieval）— 较大差距

**当前状态**: 仅有 **Vector Search** + **Rerank** 两阶段。无关键词检索、无图谱检索。

**问题**:
1. **无 Keyword 检索**: ChromaDB 的 metadata 过滤只能做精确匹配，不能做模糊关键词搜索。化学名、CAS 号、专利号的精确匹配需求强。
2. **无 Graph 检索**: 化合物与靶点、疾病、骨架之间的关系无法通过向量相似度表达。例如"找到所有对 EGFR 有活性且没有肝毒性的骨架"是纯向量检索无法回答的。
3. **无分子指纹检索**: RDKit 的 Morgan 指纹/Tanimoto 相似性检索与文本向量检索是两条独立 pipeline，未融合。
4. **无 Multi-Query**: 用户查询 "imatinib" 时，系统不会自动扩展搜索 "STI-571" 或 "Gleevec"。

**改进方向**:
- **Hybrid RAG**: 在 ChromaDB 基础上增加 SQLite FTS5 全文检索（或轻量级 Elasticsearch），实现 Keyword + Vector 混合。
- **Graph RAG**: 引入 Neo4j 或 NetworkX（内存图）构建化合物-靶点-疾病知识图谱，作为第三路检索。
- **分子相似性融合**: 将 RDKit 指纹相似度分数与文本向量相似度做归一化融合（Fused RAG）。

### 3.3 分子处理层 — 核心差距

**当前状态**: `MoleculeExtractor` 用正则提取 SMILES，用距离匹配活性数据；`MoleculeDatabase` 用 SQLite + FTS5 存储。

**问题**:
1. **SMILES 提取准确率有限**: 正则 `r'[A-Za-z0-9@\.\+\-\=\#\$\(\)\[\]\\\/\%]{4,}'` 会产生大量假阳性（普通英文单词也匹配），依赖 RDKit `MolFromSmiles` 二次过滤，但仍有遗漏。
2. **无化学结构图像识别**: PDF 中的化学结构图（占了专利和论文中分子信息的很大比例）完全未被处理。当前 VLM 仅用于"描述页面图像"，未专门识别化学结构。
3. **无分子嵌入**: 分子没有自己的向量表示。无法做"找到与这个分子结构相似的文献"这类查询。
4. **活性数据未向量化**: 活性数值没有参与检索，无法回答"找 IC50 < 10 nM 的化合物相关段落"。
5. **无子结构搜索**: `search_by_substructure` 工具是 placeholder，未实现。

**改进方向**:
- **Cross-Modal RAG**: 用 VLM 或专门的化学结构识别模型（如 DECIMER、MolScribe）将 PDF 中的化学结构图像转为 SMILES，再嵌入。
- **分子指纹嵌入**: 将 Morgan 指纹或分子描述符（MW, LogP, TPSA 等）作为附加向量字段存入 ChromaDB metadata，或单独建立分子相似性索引。
- **子结构搜索**: 实现 RDKit 子结构匹配工具，与向量检索形成互补。

### 3.4 Agent 层 — 中等差距

**当前状态**: ReAct 循环，5 轮迭代，10 个工具，支持 OpenAI function calling 和 Anthropic tool use。

**问题**:
1. **无查询复杂度分级**: 所有查询走同样的 ReAct 循环，简单问题（如"文档里提到了哪些化合物？"）本可以一次检索回答，却也要走完整的 agent loop。
2. **无 Multi-Query 扩展**: Agent 没有自动改写查询来扩展检索面的能力。
3. **无 Self-RAG 评估**: Agent 不会自我检查"检索到的内容是否足够回答用户问题"。
4. **工具粒度**: 当前 10 个工具较粗（`search_knowledge` 一个工具包揽所有 KB 查询），缺少细粒度的过滤和邻居扩展工具。

**改进方向**:
- **Adaptive RAG**: 添加轻量级 query 分类器，简单查询直接走 KB search，复杂查询才启用 Agent。
- **Multi-Query 工具**: Agent 增加 `expand_query` 工具，用 LLM 生成同义/改写查询。
- **Self-Eval 工具**: Agent 增加 `evaluate_sufficiency` 工具，判断检索结果是否充分。

### 3.5 评估与监控层 — 完全缺失

**当前状态**: 无任何 RAG 评估指标。

**问题**: 无法量化回答"我们的 RAG 效果好不好"，改进是盲目的。

**改进方向**:
- 建立离线评测集：包含事实型（"化合物 X 的 IC50 是多少"）、推理型（"为什么骨架 A 比 B 活性高"）、多跳型（"与化合物 Y 同骨架的所有化合物中活性最好的是"）问题。
- 监控指标：Recall@K, Precision@K, MRR, Faithfulness, E2E Latency。

---

## 四、技术选型建议与优先级

### 4.1 优先级矩阵

采用 **效果 × 成本 × 复杂度** 三维评估，推荐按以下优先级迭代：

| 优先级 | 方案 | 预期效果 | 开发成本 | 运维成本 | 建议迭代 |
|--------|------|---------|---------|---------|---------|
| 🔴 P0 | **Contextual Chunking** | ⭐⭐⭐⭐⭐ | 低 | 低 | 立即 — 只需修改 `split_text_chunks` 和 `index_document` |
| 🔴 P0 | **Hybrid RAG (Keyword+Vector)** | ⭐⭐⭐⭐⭐ | 低 | 低 | 立即 — SQLite FTS5 已存在，只需在 `KnowledgeBase` 增加 keyword search |
| 🔴 P0 | **分子指纹融合检索** | ⭐⭐⭐⭐⭐ | 中 | 低 | 1-2 周 — RDKit + ChromaDB metadata 结合 |
| 🟡 P1 | **Semantic Chunking (化学感知)** | ⭐⭐⭐⭐ | 中 | 低 | 2-3 周 — 需要化学实体识别前置 |
| 🟡 P1 | **Cross-Modal RAG (化学结构图)** | ⭐⭐⭐⭐⭐ | 高 | 中 | 3-4 周 — VLM/DECIMER 集成 |
| 🟡 P1 | **子结构搜索工具** | ⭐⭐⭐⭐ | 低 | 低 | 1 周 — 补齐 placeholder |
| 🟢 P2 | **GraphRAG (化合物-靶点-疾病)** | ⭐⭐⭐⭐⭐ | 高 | 高 | 2-3 月 — Neo4j 引入 + 实体抽取 |
| 🟢 P2 | **Adaptive RAG (查询分级)** | ⭐⭐⭐⭐ | 中 | 低 | 2-3 周 — 分类器 + 路由逻辑 |
| 🟢 P2 | **Multi-Query RAG** | ⭐⭐⭐ | 中 | 中 | 2-3 周 — LLM 改写 + 缓存 |
| ⚪ P3 | **Self-RAG** | ⭐⭐⭐⭐ | 高 | 高 | 后期 — 成本高，优先保证基础链路 |
| ⚪ P3 | **Personalized RAG** | ⭐⭐⭐ | 中 | 低 | 后期 — 用户画像系统 |
| ⚪ P3 | **Streaming RAG** | ⭐⭐ | 中 | 中 | 后期 — 桌面应用场景需求有限 |

### 4.2 具体技术选型依据

#### 4.2.1 向量数据库：保留 ChromaDB，未来扩展 Milvus

**选型**: 当前 ChromaDB → 未来可选 Milvus

**依据**:
- **ChromaDB 优势**: 纯 Python、无外部依赖、PersistentClient 直接读写文件、与 sentence-transformers 生态无缝。对于桌面应用，这是决定性的——用户不需要安装 Docker 或启动服务。
- **ChromaDB 局限**: 单节点、无分布式能力、大规模 (>100万 chunk) 时性能下降。但 MBForge 是项目级桌面应用，单个项目的文档量通常在数千页级别，ChromaDB 完全够用。
- **Milvus 升级点**: 如果未来需要云端部署或跨项目联邦检索，Milvus 的多模态 embedding 支持和 ANN 性能更优。但当前阶段**不需要**。

#### 4.2.2 Embedding 模型：升级 bge-m3，保留本地优先

**选型**: `BAAI/bge-small-zh-v1.5` → `BAAI/bge-m3`

**依据**:
- **当前模型局限**: `bge-small-zh-v1.5` 是 512-dim 的轻量模型，对中英混合的化学文献（大量英文术语+中文描述）表现一般，且不支持跨模态。
- **bge-m3 优势**: 1024-dim，支持多语言、长文本（8192 tokens）、稀疏向量（lexical weighting），一个模型同时提供 dense + sparse 向量，天然支持 Hybrid RAG 的 keyword 成分。
- **成本**: bge-m3 比 small 大 (~2GB vs ~100MB)，对内存有要求，但现代桌面电脑完全可承受。
- **备选**: 如果资源极度受限，可保留 small 做默认，m3 做可选升级。

#### 4.2.3 Reranker：升级 bge-reranker-v2-m3

**选型**: `BAAI/bge-reranker-base` → `BAAI/bge-reranker-v2-m3`

**依据**:
- **v2-m3 优势**: 跨模态重排能力，对图文混合候选集（化学结构图+文本描述）的排序更精准。与 bge-m3 embedding 形成同一技术栈，减少维护成本。
- **性能**: 指南中提到 N=50 时延迟 100-300ms，当前 candidate 只有 15，延迟可忽略。

#### 4.2.4 分块策略：化学感知 Semantic + Contextual Chunking

**选型**: 保留 `split_text_chunks` 作为 fallback，新增 `ChemistryAwareChunker`

**依据**:
- **化学文献的特殊性**: 化学论文中有大量"短行"内容——SMILES 字符串、化学方程式、IC50 表格行。固定字符切分极易切断这些内容。
- **实现思路**:
  1. 预扫描文本，标记化学实体区域（SMILES 行、表格区域、化学名段落）。
  2. 化学实体区域作为**不可切分原子单元**。
  3. 非化学区域使用语义边界切分。
  4. 每个 chunk 注入元信息：`"[Source: {doc_id}] [Section: {heading}] [Molecules: {smiles_list}] [Activities: {activity_list}]"`。

#### 4.2.5 图数据库：NetworkX 内存图 → Neo4j（渐进式）

**选型**: 第一阶段用 NetworkX（已依赖）构建内存知识图；第二阶段引入 Neo4j

**依据**:
- **NetworkX 优势**: 已在依赖列表中，无需额外安装，适合小规模图谱（<10万节点）。
- **Neo4j 优势**: 持久化、Cypher 查询、多跳推理性能、与 LangChain 集成成熟。
- **渐进策略**: 先在 `MoleculeDatabase` 中维护化合物-靶点-疾病关系（SQLite JSON 列），定期导出到 NetworkX 做内存分析。当图谱规模增长或需要持久化查询时再引入 Neo4j。

#### 4.2.6 文档解析：PyMuPDF → MinerU（可选升级）

**选型**: 保留 PyMuPDF 为主，UniParser 为辅；未来评估 MinerU

**依据**:
- **PyMuPDF 当前够用**: 文本提取速度快、图像提取稳定，是化学文献解析的可靠基线。
- **MinerU 优势**: 版面分析（Layout Analysis）、表格结构提取、公式识别、标题层级提取——这些对 Hierarchical RAG 和表格数据提取至关重要。
- **成本**: MinerU 依赖较重（需要 OCR 引擎、版面分析模型），对桌面应用打包（PyInstaller）不友好。
- **策略**: 保留 PyMuPDF 为默认，将 MinerU 作为可选高级解析插件（类似当前 UniParser 的集成方式）。

#### 4.2.7 跨模态：VLM 化学结构识别

**选型**: 分两步——先用现有 VLM 描述图像；再引入 DECIMER/MolScribe 专门模型

**依据**:
- **现有 VLM 局限**: `APIVLM` 调用的是通用多模态模型（如 GPT-4o），对化学结构图的识别是"通用描述"级别，不会输出精确 SMILES。
- **DECIMER/MolScribe**: 专门为化学结构图像→SMILES 训练的模型，准确率远高于通用 VLM。
- **策略**: 
  1. 短期：在 VLM prompt 中加入"如果图像包含化学结构，请尽可能描述其 SMILES 字符串"的指令。
  2. 中期：集成 DECIMER（开源、可本地运行）作为 PDF 图像的后处理管道。
  3. 长期：构建跨模态双图（文本知识图 + 化学结构图知识图）。

---

## 五、推荐改进路线图

### Phase 1: 基础增强（2-3 周）

目标：**在不引入新依赖的前提下，最大化现有架构的检索质量。**

1. **Contextual Chunking**
   - 修改 `KnowledgeBase.index_document()`，为每个 chunk 注入 `title`, `section`, `molecules`, `keywords` 到 metadata。
   - 修改 `split_text_chunks()` 的 prompt：为 chunk 头部注入 `"[Context: {section_title}]"`。

2. **Hybrid RAG（Keyword + Vector）**
   - `KnowledgeBase` 新增 `keyword_search()` 方法，利用 SQLite FTS5（已存在）对 `content.text` 做全文检索。
   - `hybrid_search()` 改为：FTS5 召回 + Vector 召回 → 去重合并 → Rerank。
   - 权重：化学名/CAS 查询时提升 keyword 权重；概念性问题提升 vector 权重。

3. **子结构搜索工具**
   - 实现 `search_by_substructure` placeholder：RDKit `MolFromSmarts` + `HasSubstructMatch`。
   - 在 Agent tools 中注册，与 `search_molecules` 互补。

4. **分子指纹相似性**
   - 在 `MoleculeDatabase` 中预计算 Morgan 指纹（1024-bit），存储为 BLOB。
   - 新增 `search_by_similarity(smiles, threshold=0.7)` 方法，使用 RDKit `TanimotoSimilarity`。

### Phase 2: 化学感知增强（3-4 周）

目标：**让 RAG 真正"理解"化学结构和数据。**

1. **Semantic Chunking（化学感知）**
   - 在 `split_text_chunks()` 前增加化学实体识别层：正则标记 SMILES、IUPAC 名、活性数据区域。
   - 这些区域作为不可切分单元。

2. **分子嵌入**
   - 为每个 `MoleculeRecord` 生成文本描述（"SMILES: ... MW: ... LogP: ... Activity: ..."），用 embedder 编码为向量。
   - 在 ChromaDB 中创建独立的 `molecules` collection，支持"找与这个分子相似的文献"查询。

3. **Cross-Modal 化学结构识别**
   - 集成 DECIMER 或类似模型，处理 PDF 中的化学结构图像。
   - 将识别出的 SMILES 与文本提取的 SMILES 合并去重。

4. **Filtered RAG 增强**
   - 在 `KnowledgeBase.search()` 中扩展 metadata filter：支持 `activity_min`, `activity_max`, `molecule_present`, `assay_type` 等过滤条件。

### Phase 3: 图谱与智能体（2-3 月）

目标：**支持复杂多跳推理，如 SAR 对比分析、化合物-靶点关系查询。**

1. **知识图谱构建**
   - 从文献中提取实体：化合物、靶点蛋白、疾病、骨架、ADMET 属性。
   - 关系：化合物-抑制-靶点、化合物-属于-骨架、化合物-具有-ADMET属性。
   - 存储：NetworkX（内存）或 Neo4j（持久化）。

2. **GraphRAG 检索**
   - Agent 新增图遍历工具：`get_neighbors(entity, hops=2)`, `search_entities(name)`, `get_entities_by_type(type)`。
   - 向量检索与图检索结果融合（Fused RAG）。

3. **Adaptive RAG**
   - 添加 query 分类器（轻量 BERT 或规则引擎）。
   - 路由策略：事实型→直接 KB 搜索；对比型→Agent + Graph；列表型→Multi-Query + KB。

4. **Multi-Query RAG**
   - Agent 增加查询改写步骤：用 LLM 将用户 query 扩展为 3-5 个同义/补全 query。
   - 缓存高频查询改写结果（Redis 或 SQLite）。

### Phase 4: 评估体系（持续）

1. 构建化学领域评测集（50-100 个问题）。
2. 自动化评估 pipeline：Recall@5, MRR, Faithfulness。
3. A/B 测试框架：对比不同 chunk 策略、embedding 模型、检索策略的效果。

---

## 六、关键决策记录

### 决策 1: 为什么保留 ChromaDB 而不是升级到 Milvus？

- **桌面应用约束**: MBForge 是 PyQt6 桌面应用，用户期望开箱即用。Milvus 需要 Docker 或独立服务，部署复杂度与产品定位不符。
- **规模匹配**: 单个项目的文档量通常在 10-1000 篇，ChromaDB 的 PersistentClient 完全胜任。
- **未来兼容性**: 当前 `KnowledgeBase` 是 ChromaDB 的包装类，如果需要切换到 Milvus，只需重写这一个类即可，对其他模块无侵入。

### 决策 2: 为什么 Embedding 模型优先本地而不是 API？

- **离线优先设计目标**: MBForge 明确将"offline-first with optional cloud services"作为设计目标。sentence-transformers 保证无网络时也能使用核心功能。
- **成本**: API embedding 按 token 收费，对大量文档索引成本高昂。
- **延迟**: 本地 embedding 批量处理 PDF 时延迟可控；API 有网络延迟和速率限制。

### 决策 3: 为什么 GraphRAG 不是 P0？

- **构建成本**: 知识图谱需要从文献中抽取实体和关系，依赖 LLM 调用，成本高且不稳定。
- **维护成本**: 图谱需要持续更新和校验，对桌面应用维护负担大。
- **ROI 曲线**: 在文档量 <1000 篇时，纯向量检索+重排序的效果通常足够好。GraphRAG 的优势在长文档、多跳推理场景，需要一定规模才能体现。
- **渐进路径**: 先通过 SQLite JSON 列和 NetworkX 做轻量关系管理，验证效果后再决定是否引入 Neo4j。

### 决策 4: 为什么 Cross-Modal RAG 是 P1 而不是 P0？

- **技术成熟度**: 化学结构图像→SMILES 的专用模型（DECIMER、MolScribe）虽然开源，但集成到桌面应用有模型加载和打包挑战。
- **数据占比**: 对于以文本为主的文献（如 ACS 文章），SMILES 通常已在文本中。结构图识别对专利（图像密集）更重要。
- **备选方案**: 通用 VLM 已能在一定程度上描述化学结构，可作为短期 fallback。

---

## 七、参考项目与开源资源清单

| 项目/资源 | 类型 | 用途 | 集成方式 |
|----------|------|------|---------|
| [OpenViking](https://github.com/volcengine/OpenViking) | 架构参考 | 分层摘要 (L0/L1/L2)、目录检索 | 已参考，架构已融合 |
| [TencentDB-Agent-Memory](https://github.com/Tencent/TencentDB-Agent-Memory) | 架构参考 | 6 类记忆系统、记忆自迭代 | 已参考，已集成 |
| [LangChain](https://github.com/langchain-ai/langchain) | 框架 | ReAct Agent、工具调用、图谱集成 | 当前自建实现，未来可选集成 |
| [ChromaDB](https://github.com/chroma-core/chroma) | 向量数据库 | 语义检索、metadata 过滤 | 已集成 |
| [sentence-transformers](https://github.com/UKPLab/sentence-transformers) | 模型库 | Embedding + Rerank | 已集成 |
| [BGE 系列](https://github.com/FlagOpen/FlagEmbedding) | 模型 | bge-small-zh, bge-reranker-base | 已集成 |
| **BGE-M3** | 模型 | 多语言 dense+sparse 统一嵌入 | **推荐集成** |
| **BGE-Reranker-v2-m3** | 模型 | 跨模态重排序 | **推荐集成** |
| [MinerU](https://github.com/opendatalab/MinerU) | 文档解析 | 版面分析、表格/公式提取 | **未来可选** |
| [Neo4j](https://neo4j.com/) | 图数据库 | 知识图谱持久化、Cypher 查询 | **未来可选** |
| [DECIMER](https://github.com/Kohulan/DECIMER-Image_Transformer) | 化学 OCR | 化学结构图像→SMILES | **未来可选** |
| [MolScribe](https://github.com/thomas0809/MolScribe) | 化学 OCR | 化学结构图像→SMILES | **未来可选** |
| [NetworkX](https://networkx.org/) | 图算法 | 内存知识图、拓扑分析 | 已在依赖中，待充分利用 |
| [RDKit](https://www.rdkit.org/) | 化学信息学 | 分子解析、指纹、性质计算、子结构搜索 | 已集成 |

---

## 八、总结

MBForge 的 RAG 架构已经完成了 **70% 的基础建设**——文档解析、向量化、检索、重排序、Agent 对话、记忆系统均已具备。与 RAG 技术选型指南中的 17 种方案对比：

- **已对齐**: Simple RAG、Chunk Overlap、Rerank RAG、Agent-RAG（基础版）、Filtered RAG（部分）、Hierarchical RAG（L0/L1/L2 摘要）。
- **显著差距**: Semantic Chunking（化学感知）、Contextual Chunking、Hybrid RAG（缺少 Keyword 路）、Cross-Modal RAG（化学结构图）、GraphRAG（化合物关系图谱）、Adaptive RAG（查询分级）、评估体系。
- **最大机会**: **分子数据处理**是 MBForge 区别于通用 RAG 系统的核心差异化能力。将分子指纹、子结构搜索、活性数据过滤与文本 RAG 深度融合，是打造"化学领域专用 RAG"的关键。

**下一步建议**: 立即启动 **Phase 1**（Contextual Chunking + Hybrid RAG + 子结构搜索），这三项改动对现有架构侵入性最小、ROI 最高，可在 2-3 周内显著提升检索质量。
