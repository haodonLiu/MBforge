# Leong et al., Chem. Sci., 2024 — MERMES 分析报告

> **原文**: *Automated electrosynthesis reaction mining with multimodal large language models (MLLMs)*  
> **作者**: Shi Xuan Leong, Sergio Pablo-García, Zijian Zhang, Alán Aspuru-Guzik  
> **期刊**: Chemical Science, 2024, 15, 17881–17891  
> **DOI**: [10.1039/D4SC04630G](https://doi.org/10.1039/D4SC04630G)  
> **Code**: https://github.com/aspuru-guzik-group/MERMES

---

## 1. 论文核心贡献

MERMES (Multimodal Reaction Mining pipeline for ElectroSynthesis) 是一个基于 **多模态大语言模型 (MLLM)** 的自动化电合成反应挖掘工具包。其核心价值在于：

- 超越单模态（纯文本或纯图像）限制，同时处理 **文本、图片、表格** 中的化学信息
- 解决 **跨模态数据依赖 (cross-modality interdependency)** 问题，例如 figure 中的上标字母与 caption 中脚注定义的关联
- 端到端自动化：文献检索 → 图文提取 → 多模态分析

---

## 2. 系统架构（三阶段流水线）

```
┌─────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
│ 1. Article Retrieval │ ──▶ │ 2. Information Extraction│ ──▶ │ 3. Multimodal Analysis  │
│    从出版社下载 HTML │     │    提取 image-caption 对  │     │    MLLM + NL Prompt     │
│    及高清图片        │     │    MLLM 筛选相关 figure   │     │    提取化学信息         │
└─────────────────────┘     └─────────────────────────┘     └─────────────────────────┘
```

**MBForge 映射**：我们的管线设计与此逻辑高度一致，但直接处理更难的 **PDF** 格式（MERMES 目前仅支持 HTML，作者明确将 PDF 列为未来扩展方向）。

---

## 3. 关键技术发现与 MBForge 启示

### 3.1 图像裁剪预处理 — 验证 MolDet → Crop → MolScribe 策略

MERMES 最重要的技术发现：**将 figure 自动裁剪为 subfigure 后再送入 MLLM**，footnote cross-reference 的 recall 从 **73% → 96%**。

| 策略 | Recall |
|------|--------|
| 整图直接输入 MLLM | 73% |
| 自动裁剪为 subfigures 后输入 | **96%** |

**启示**：MBForge 的 **MolDet (YOLOv8) 检测分子区域 → 裁剪 → MolScribe 识别** 流水线与此发现完全吻合。可进一步扩展：
- 对 **表格 (table)** 和 **反应式示意图 (scheme)** 也做类似的检测+裁剪
- 分别送入不同后端（表格→结构化提取，scheme→反应条件解析）

---

### 3.2 Single-Shot Visual Prompting — VLM 层 Prompt 工程新思路

GPT-4V 零样本识别电合成反应图的电极材料准确率仅 **70-83%**，但引入 single-shot visual prompting（每种呈现风格给一张示例图）后：

| 呈现风格 | 零样本 | + Visual Prompt |
|---------|--------|-----------------|
| Style 1 (明确极性标注) | 100% | 100% |
| Style 3 (需化学常识推断) | 70% | **89%** |
| Style 4 (电路符号示意) | 75% | **100%** |
| **整体电极 Hard Match** | 85% | **99%** |

**启示**：
- `vlm_chem.rs` 目前主要是 zero-shot。可考虑在调用 VLM 时附带**同类型示例分子图像**作为 in-context visual prompt
- 例如识别复杂 Markush 结构时，先附一张已正确解析的类似结构图，说明期望输出格式 (E-SMILES)
- 需在 `ImageCaptionCache` 或知识库中维护**高质量示例图库**

---

### 3.3 Cross-Modality Association — 验证 `association.rs` 方向

MERMES 核心任务二：**resolving cross-modality interdependencies**
- 图上上标字母 ↔ Caption 脚注定义
- Substrate-specific 产率/条件 ↔ 结构变体索引

最终指标：**Precision ≈ 96%, Recall ≈ 96%, F1 ≈ 96%**

**启示**：
- MBForge `parsers/association.rs`（分子-文本关联引擎）方向正确
- 可引入 LLM 做关联推理：将检测到的分子框 + 周围文本片段 + caption 一起送入 LLM，做 "哪个分子对应哪个产率/条件" 的推理
- 比纯规则匹配（正则、位置启发）更鲁棒，尤其适用于排版不标准的文献

---

### 3.4 Hard Match vs Soft Match — 引入更严格的评估框架

论文提出两级评估：
- **Hard match**：参数识别正确 + **角色分配正确**（如准确区分 anode vs cathode）
- **Soft match**：参数识别正确即可（角色分配错误也算对）

**启示**：
- MBForge 的分子提取评估可借鉴此框架：
  - **Hard match**: 检测框位置准 + SMILES 完全正确 + 上下文关联正确
  - **Soft match**: SMILES canonical 后相同即可
- 对 `parser_io` 测试集的自动评分很有价值

---

### 3.5 Specialist vs Generalist — 验证混合架构

| 工具类型 | 代表 | 电合成数据集表现 |
|---------|------|-----------------|
| Specialist DL toolkit | ReactionDataExtractor 2.0 | 23–36% (soft match) |
| Specialist DL toolkit | RxnScribe | 50–59% (soft match) |
| General MLLM (GPT-4V) | MERMES | **96%** (hard match) |

**关键洞察**：专用工具因训练数据局限，在域外数据上严重退化；通用 MLLM 配合 in-context learning 更具适应性。

**启示**：
- MBForge **MolScribe (specialist) + 通用 LLM (generalist)** 的混合架构合理
- 分子图像识别需要 specialist（化学键、立体化学）
- 文本理解和跨模态关联需要 generalist（适应不同化学子领域）
- **但**：遇到全新分子表示风格时，MolScribe 也可能失效。应设计 **LLM-based fallback**（如 GPT-4V 直接读图）作为降级策略

---

## 4. MBForge 差异化优势

MERMES 明确承认的局限（也是我们的机会）：

> *"Our future work will include extending the pipeline to efficiently mine other document formats, such as PDF, which remains challenging for machines to parse and sort the data."*

MBForge 的核心壁垒：
1. **Rust 侧原生 PDF 解析**（lopdf）+ 图像提取
2. **MinerU Precise API 深度集成**（layout.json + OCR blocks）
3. **MolDet + MolScribe 端到端分子检测识别管线**
4. **正在建设的跨模态关联引擎** (`association.rs`)

---

## 5. Actionable TODOs

| 优先级 | 改进项 | 涉及模块 |
|--------|--------|---------|
| P1 | 为 VLM 化学识别引入 in-context visual prompting | `vlm_chem.rs` |
| P1 | 在 association 阶段引入 LLM 推理做跨模态匹配 | `association.rs` |
| P2 | 扩展 MolDet 检测类别：table、scheme、chart | `moldet_client.rs` |
| P2 | 建立 Hard/Soft match 评估框架 | `parser_io/` 测试集 |
| P3 | 为 MolScribe 设计 LLM fallback 机制 | `molecule_extractor.rs` |
| P3 | 维护高质量示例图库用于 visual prompting | 项目级配置 / cache |

---

## 6. 相关引用

- Leong, S. X.; et al. *Chem. Sci.*, **2024**, 15, 17881–17891.
- GitHub: https://github.com/aspuru-guzik-group/MERMES
- Zenodo (code): https://doi.org/10.5281/zenodo.12713560
- Zenodo (raw data & prompts): https://doi.org/10.5281/zenodo.12701834
