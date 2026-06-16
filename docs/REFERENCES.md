# References & Acknowledgments

MBForge 的构建依赖于众多优秀的开源项目和服务。感谢以下项目和团队的贡献。

## 核心框架

| 项目 | 许可证 | 用途 |
|------|--------|------|
| [Tauri v2](https://tauri.app/) | MIT/Apache-2.0 | 跨平台桌面应用框架 |
| [React](https://react.dev/) | MIT | 前端 UI 框架 |
| [FastAPI](https://fastapi.tiangolo.com/) | MIT | Python 模型服务器 |
| [Vite](https://vitejs.dev/) | MIT | 前端构建工具 |

## PDF 解析

| 项目 | 许可证 | 用途 |
|------|--------|------|
| [pdf-inspector](https://github.com/firecrawl/pdf-inspector) | — | PDF 文本提取与分类（Rust） |
| [lopdf](https://github.com/J-F-Liu/lopdf) | MIT | PDF 嵌入式图像提取（Rust） |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | AGPL-3.0 / 商业 | PDF 页面渲染（Python sidecar） |
| [MinerU](https://mineru.net/) | 商业服务 | PDF OCR 解析 API |
| [UniParser](https://uniparser.dp.tech/) | 商业服务 | PDF 解析 API |
| [LlamaIndex LlamaParse](https://llamaindex.ai/) | 商业服务 | PDF 解析服务 |

## 化学信息学

| 项目 | 许可证 | 用途 |
|------|--------|------|
| [RDKit](https://rdkit.org/) | BSD-3-Clause | 分子指纹、描述符、SMILES 解析 |
| [MolScribe](https://github.com/thomas0809/MolScribe) | MIT | 分子图像 → SMILES 识别 |
| [OpenBabel](https://openbabel.org/) | GPL-2.0 | 分子格式转换 |
| [E-SMILES](https://github.com/thomas0809/MolScribe) | — | 扩展 SMILES 分子格式规范 |
| [E-SMILES](https://github.com/thomas0809/MolScribe) | — | 扩展 SMILES 分子格式规范 |
## LLM 抽取方法论
| 项目 | 许可证 | 用途 |
| [Dagdelen et al. 2024 (Nature Comm. 15:1418)](https://doi.org/10.1038/s41467-024-45563-x) | — | LLM-NERRE：联合 NER + 关系抽取。我们的 post-process prompt 借鉴其 JSON schema 设计与"规范化即抽取"原则 |
### MolScribe 子依赖
MolScribe 内部使用了以下组件（均已包含在 `setup/MolScribe/` 中）：

| 组件 | 许可证 | 来源 |
|------|--------|------|
| Swin Transformer | MIT | [Microsoft Swin Transformer](https://github.com/microsoft/Swin-Transformer) |
| OpenNMT-py Decoder | MIT | [OpenNMT](https://opennmt.net/) |

## AI 模型

| 模型 | 许可证 | 来源 |
|------|--------|------|
| Qwen3-Embedding-0.6B | Apache-2.0 | [Qwen (Alibaba)](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) |
| Qwen3-Reranker-0.6B | Apache-2.0 | [Qwen (Alibaba)](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) |
| MolDetv2 | Apache-2.0 | [yujieq/MolDetect](https://huggingface.co/yujieq/MolDetect) |
| MolScribe | MIT | [yujieq/MolScribe](https://huggingface.co/yujieq/MolScribe) |

## 数据存储与检索

| 项目 | 许可证 | 用途 |
|------|--------|------|
| [ChromaDB](https://www.trychroma.com/) | Apache-2.0 | 向量数据库 |
| [rusqlite](https://github.com/rusqlite/rusqlite) | MIT | SQLite 绑定（Rust） |
| [sentence-transformers](https://www.sbert.net/) | Apache-2.0 | 文本 Embedding 框架 |
| [HuggingFace Transformers](https://huggingface.co/docs/transformers) | Apache-2.0 | Transformer 模型加载 |

## ML 推理

| 项目 | 许可证 | 用途 |
|------|--------|------|
| [PyTorch](https://pytorch.org/) | BSD-3-Clause | ML 推理后端 |
| [Ultralytics (YOLO)](https://ultralytics.com/) | AGPL-3.0 | 分子检测（MolDetv2） |

## 设计参考

以下项目的设计理念对 MBForge 产生了影响：

| 项目 | 链接 | 参考内容 |
|------|------|----------|
| OpenViking | https://github.com/volcengine/OpenViking | 知识库架构设计 |
| TencentDB-Agent-Memory | https://github.com/Tencent/TencentDB-Agent-Memory | Agent 记忆系统设计 |
| RxnScribe | https://github.com/thomas0809/RxnScribe | 反应图解析（MolScribe 相关工作） |
| OpenChemIE | https://github.com/CrystalEye42/OpenChemIE | 化学信息抽取 |

## 学术论文

| 论文 | 用途 |
|------|------|
| Vaswani et al., "Attention Is All You Need" (2017) | MolScribe 位置编码实现 |
| Sennrich et al., "Linguistic Input Features Improve Neural Machine Translation" (2016) | MolScribe 特征嵌入 |
| Liu et al., "Swin Transformer: Hierarchical Vision Transformer using Shifted Windows" (2021) | MolScribe 编码器架构 |
| Qian et al., "MolScribe: Robust Molecular Structure Recognition with Image-to-Graph Generation" (JCIM 2023) | 分子图像识别核心模型 |
| "MolParser: End-to-end Visual Recognition of Molecule Structures in the Wild" (arXiv: 2411.11098) | E-SMILES 格式规范来源 |

## API 服务

| 服务 | 用途 |
|------|------|
| [ModelScope](https://modelscope.cn/) (Alibaba) | 模型下载 |
| [HuggingFace Hub](https://huggingface.co/) | 模型下载（中国镜像 hf-mirror.com） |
| [Ollama](https://ollama.ai/) | 本地 LLM 推理 |
| [MiniMax](https://www.minimaxi.com/) | LLM API 服务 |

---

*本文档最后更新: 2026-05-31*
