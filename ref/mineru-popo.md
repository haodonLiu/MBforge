# MinerU-Popo — 文档级语义后处理模型

> 来源: MinerU 项目（4B 参数通用后处理模型）
> 定位: 不替换 OCR 引擎，而是将页面级 OCR 输出提升为文档级语义结构
> 状态: 待集成评估

## 核心定位

> "A 4B-parameter general post-processing model that upgrades any page-level OCR output into document-level semantic structure."

```
页面级 OCR (MinerU/MonkeyOCR/Dolphin/PaddleOCR/GLM-OCR)
    │
    ▼
MinerU-Popo 后处理层
    ├── 表格截断分析 (Table Truncation)
    ├── 文本截断分析 (Text Truncation)
    ├── 标题层次分析 (Title Hierarchy)
    └── 图文关联分析 (Image-Text Association)
    │
    ▼
结构化文档树 + 语义摘要 + 长章节拆分
```

## 关键性能

| 指标 | 数值 |
|------|------|
| TEDS 分数（标题层次） | MinerU 53.7 → 90.6（近乎翻倍） |
| 处理速度 | 0.37 doc/s（比 Qwen3-VL-32B 快 9×，比 Qwen3-VL-4B 快 1.8×） |
| 下游 RAG（Pharma 领域） | Popo 71.6% vs Visual RAG 67.6% vs Raw RAG 64.4% |
| 模型大小 | 4B 参数，~8GB VRAM (fp16) 或 ~4GB (int8) |

## MBForge 当前的差距

| 功能 | MBForge 当前实现 | MinerU-Popo 对应 | 差距 |
|------|-----------------|-----------------|------|
| OCR 调用 | mineru.rs — HTTP 调 MinerU API，返回 markdown | 输入源 | — |
| 标题层次 | sections.rs + headings.rs — 启发式规则 | Title Hierarchy Analysis | **高误报率** |
| 文档树 | document_tree.rs — 从 SectionChunk 构建树 | Document Tree Building | 启发式 vs 学习型 |
| 图文关联 | association.rs — 纯文本正则匹配，无图像关联 | Image-Text Association | **最致命差距** |
| 表格处理 | ❌ 无专门处理，表格作为 markdown 文本 | Table Truncation Analysis | 跨页表格碎片化 |
| 跨页连续性 | ❌ 无，每页独立处理 | Text Truncation Analysis | 数据丢失 |
| 长文档处理 | pipeline.rs 分 Stage，无动态分块 | Dynamic Chunking | 全局一致性缺失 |

## 差距深度分析

### 差距 1: 图文关联（最致命）

association.rs 的 `associate_single()` 只能做文本内关联：
- 从文本中提取 "Compound 1"、"IC50 = 5.2 nM"、"HEK293 cells"、"EGFR receptor"
- **无法将分子图像与文本描述关联**

在化学/药物专利中，分子图通常在 Figure/Scheme 中，而活性数据在表格或正文中。当前关联是启发式猜测（靠页码 proximity），不是结构化关联。

**MinerU-Popo 的 Image-Text Association 可以**：
- 将 Figure 1 中的分子图像与正文 "As shown in Figure 1, Compound 1..." 精确关联
- 将 Scheme 2 中的合成路线与 "Scheme 2 illustrates the synthesis..." 关联
- 将 Table 1 中的数据行与对应的分子图像关联

### 差距 2: 标题层次（高误报率）

sections.rs 的 `is_semantic_boundary()` 检测 30+ 边界关键词，但：
- 假阳性高："Results and Discussion" 可能被拆成两个 section
- 无法处理跨页 heading
- 多级标题嵌套依赖 path 字符串的 " > " 计数

**MinerU-Popo 的 Title Hierarchy Analysis**：
- 4B 模型训练了大量文档的标题层次模式
- 可以识别 "1.1.3 Synthesis of Compound 1" 是三级标题
- 可以处理跨页标题
- TEDS 从 ~53.7% 提升到 ~90.6%

### 差距 3: 表格截断（专利常见问题）

专利中实验数据表格经常被分页截断。当前 MBForge 将每页独立处理，导致：
- 表格被拆成多个不完整的 markdown 表格
- 列对齐丢失
- 分子图像在表格中的位置信息丢失

**MinerU-Popo 的 Table Truncation Analysis**：
- 检测表格是否在当前页被截断
- 将跨页表格碎片合并为完整表格
- 保持列对齐和行连续性

## 集成方案

### Phase 1: Sidecar 集成（最小侵入）

MinerU-Popo 是 Python 项目，MBForge 已有 Python FastAPI sidecar (port 18792)：

```python
# src/mbforge/model_server/routers/popo.py (新增)

class PopoEnhanceRequest(BaseModel):
    ocr_output: dict   # 页面级 OCR 的 JSON 输出
    ocr_source: str    # "mineru" | "llamaparse" | "uniparser" | "lopdf"

class PopoEnhanceResponse(BaseModel):
    document_tree: dict           # 结构化文档树
    image_text_assoc: list        # 图文关联列表
    table_reconstructions: list   # 修复后的表格
    success: bool
    error: str | None
```

Rust 侧调用点（pipeline.rs）：
```rust
// Stage 0.5: Popo 后处理增强（新增）
let enhanced = popo_enhance(&ocr_output, parser_type, sidecar_url).await?;
// enhanced.document_tree, enhanced.image_text_assoc, enhanced.table_reconstructions
```

### Phase 2: association.rs 重写

利用 Popo 的图文关联输出：
```rust
pub struct PopoImageTextAssoc {
    pub image_id: String,            // 图像 ID
    pub image_type: String,          // "figure" | "scheme" | "table"
    pub caption_text: String,        // 图注文本
    pub referenced_in: Vec<String>,  // 正文中引用此图的位置
    pub nearby_compounds: Vec<String>, // 附近提及的化合物名
}
```

### Phase 3: 表格修复集成

利用 Popo 的表格截断修复输出，增强分子数据提取。

## 技术风险

| 风险 | 评估 | 缓解 |
|------|------|------|
| 模型大小 | 4B 参数，~8GB VRAM | 支持 CPU 推理（慢但可用）；或 int4 量化 |
| 推理速度 | 0.37 doc/s ≈ 2.7s/页 | 5000 页 ≈ 3.7 小时，需后台异步 |
| 依赖冲突 | 依赖特定 transformers/torch 版本 | 隔离环境运行，FastAPI 封装 |
| 输入格式转换 | 需统一多种 OCR 输出为 Popo schema | 一次性开发转换器 |
| 化学专利准确率 | 未经专门验证 | 先用测试集评估 |

## 优先级

| 优先级 | 功能 | 价值 | 工作量 |
|--------|------|------|--------|
| **P0** | 图文关联分析 | 极高（分子图像-文本精确绑定） | 中 |
| **P1** | 标题层次分析 | 高（替代启发式规则） | 中 |
| **P2** | 表格截断修复 | 高（SAR 表格完整性） | 中 |
| **P3** | 长文档动态分块 | 中（5000+ 页 scalability） | 高 |

## 核心结论

> MinerU-Popo 不是"可选优化"，而是 MBForge 文档解析层缺失的关键一块。

当前架构的核心瓶颈：MBForge 从"文本"重建"结构"，而 Popo 让 MBForge 可以直接从 OCR 输出获取原生结构——跳过 headings.rs 的启发式猜测、sections.rs 的 fallback chunking、以及 association.rs 的纯文本扫描。

**魔鬼代言人评论**: MinerU-Popo 是 4B 模型，推理需要 GPU。对于只需处理几十篇 PDF 的小型项目，2.7s/页的开销可能不值得。但对于 5000+ 页的专利项目，这是唯一能保证结构准确性的方案。建议作为可选增强层，默认关闭，用户手动启用。
