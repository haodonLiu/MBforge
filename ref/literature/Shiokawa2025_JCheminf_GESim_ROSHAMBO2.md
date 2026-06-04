# Shiokawa et al. (J. Cheminf., 2025) + Atwi et al. (JCIM, 2025) — 综合分析报告

> **文献 1**: *GESim: ultrafast graph-based molecular similarity calculation via von Neumann graph entropy*  
> **作者**: Hiroaki Shiokawa, Shoichi Ishida, Kei Terayama  
> **期刊**: Journal of Cheminformatics, **2025**, 17:57  
> **DOI**: [10.1186/s13321-025-01003-6](https://doi.org/10.1186/s13321-025-01003-6)  
> **Code**: https://github.com/LazyShion/GESim

> **文献 2**: *ROSHAMBO2: Accelerating Molecular Alignment for Large Chemical Libraries with GPU Optimization and Algorithmic Advances*  
> **作者**: Rasha Atwi, Stephen Farr, Ye Wang, Adam Antoszewski, Simone Sciabola  
> **期刊**: Journal of Chemical Information and Modeling, **2025**, 65, 19  
> **DOI**: [10.1021/acs.jcim.5c01322](https://doi.org/10.1021/acs.jcim.5c01322)  
> **Code**: https://github.com/molecularinformatics/roshambo2  
> **前身**: https://github.com/molecularinformatics/roshambo

---

## 1. 概述：互补的两种分子相似性范式

这两篇论文恰好代表了**分子相似性计算的两个互补维度**：

| 维度 | GESim | ROSHAMBO2 |
|------|-------|-----------|
| **表示层** | 2D 拓扑图（原子=节点，键=边） | 3D 形状（Gaussian volume overlap） |
| **核心数学** | von Neumann Graph Entropy + QJS Divergence | Gaussian 函数重叠优化 |
| **计算特性** | CPU，O(n) 近似，与 fingerprint 速度相当 | GPU 加速，200x 于原版 |
| **相似性类型** | 结构/拓扑相似性 | 形状/空间相似性 |
| **最佳场景** | 骨架相似性搜索、去重、 analog 发现 | 虚拟筛选、骨架跃迁、药效团匹配 |
| **RDKit 兼容** | ✅ 原生支持 Mol 对象 | ✅ 支持 SDF/SMILES |

MBForge 作为分子知识库平台，在分子提取后的分析阶段可以**同时利用这两种相似性度量**，构建多维度的分子关联网络。

---

## 2. GESim 深度解析

### 2.1 核心思想

传统 fingerprint（ECFP/MACCS 等）将分子编码为固定长度向量，速度快但会丢失全局拓扑信息。Graph Edit Distance (GED) 能保留完整图结构，但为 NP-hard / O(n³)，无法规模化。

GESim 的解决方案：**用 von Neumann Graph Entropy (vNGE) 替代 fingerprint，用 1D Structural Information (SI) 近似 vNGE，实现与 fingerprint 相当的速度 + 图论级别的区分能力。**

### 2.2 算法流程（三模块）

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────────┐
│ Graph Aligner   │ ──▶ │ Projection      │ ──▶ │ Similarity Calculator│
│ 原子指纹匹配    │     │ 构建合并图+投影图│     │ QJS Divergence 计算  │
│ 找最大公共子图  │     │ Ĝ₁,₂, Ĝ₁, Ĝ₂   │     │ similarity = 1 - QJS │
└─────────────────┘     └─────────────────┘     └─────────────────────┘
```

**关键创新**：
1. **1D Structural Information (SI)**：用归一化度序列的 Shannon entropy 近似 Laplacian 谱熵，从 O(n³) → O(n)
2. **Merged Graph + Projection**：QJS divergence 需要三个输入图（合并图 + 两个投影图），GESim 通过原子指纹匹配构建这些图
3. **Atom Fingerprint (r=4)**：1024-bit 的路径哈希指纹，用于快速节点匹配，避免 MCS 的 NP-hard 问题

### 2.3 性能基准

论文在 **structural similarity benchmark**（近 analog 排序）和 **functional similarity benchmark**（虚拟筛选，DUD/MUV/ChEMBL）上与五种 fingerprint 比较：

| 方法 | 类型 | 速度 | 特点 |
|------|------|------|------|
| ECFP | Circular fingerprint | 基准 | 最常用，但可能丢失全局结构信息 |
| FCFP | Feature-based | 基准 | 考虑原子属性而非拓扑 |
| APFP | Atom-pair | 基准 | 路径编码 |
| TTFP | Topological torsion | 基准 | 四原子扭转角 |
| MACCS | Dictionary | 基准 | 166 keys，速度快但粗糙 |
| **GESim** | **Graph entropy** | **≈ ECFP** | **区分高度相似分子的能力强** |
| GED | Graph edit distance | 极慢 (O(n³)) | 精确但不可扩展 |

**关键发现**：
- GESim 在区分**高度相似分子**（如只差一个键或一个环）时表现优于 fingerprint 方法
- 在 functional similarity（虚拟筛选）任务上与 ECFP+Tanimoto 相当
- 计算速度与 ECFP 同数量级，比 GED 快数个数量级

---

## 3. ROSHAMBO2 深度解析

### 3.1 核心思想

ROSHAMBO (v1) 是基于 **Gaussian volume overlap** 的 3D 分子对齐工具，概念上类似 OpenEye ROCS。它用原子为中心的 Gaussian 函数近似分子体积，通过优化重叠体积来计算 3D 相似性。

ROSHAMBO2 在此基础上实现了 **200 倍以上的性能提升**，使其能够处理超大型化学库（ultralarge chemical libraries）的虚拟筛选。

### 3.2 技术改进

| 方面 | ROSHAMBO (v1) | ROSHAMBO2 |
|------|--------------|-----------|
| **GPU 支持** | 有但有限 | 深度优化，核心计算 offload 到 GPU |
| **算法** | 基础 overlap 优化 | 算法创新 + 内存优化 |
| **内存** | 常规 | 优化内存处理，支持更大库 |
| **性能** | 基准 | **>200x 加速** |
| **API** | Python + CLI | 保持模块化，兼容原有工作流 |
| **License** | GPL | MIT |

**关键指标**：
- 支持 **Tanimoto** 和 **Tversky** 相似性度量
- Tversky (α=0.95, query-biased) 在 query 与 database 分子大小差异大时表现优于 Tanimoto
- 可处理 **~10¹⁵ 级别**的虚拟化学空间筛选

### 3.3 应用案例

从相关文献（如 `RoshamboLearningJourney`）可以看到 ROSHAMBO2 的典型应用场景：
- **Shape-based virtual screening**：基于 query 分子的 3D 形状从 ChEMBL 等大型库中检索相似物
- **Query conformation 的影响**：bioactive conformation vs non-bioactive conformation 作为 query，前者能显著提升已知活性分子的排序（如 ROS1 抑制剂 CHEMBL1997924 从 rank 50 提升到 rank 11）
- **骨架跃迁 (scaffold hopping)**：发现与 query 拓扑不同但形状相似的活性分子

---

## 4. 对 MBForge 的启示与落地建议

### 4.1 分子去重与聚类：引入 GESim

MBForge 目前已有基于 RDKit fingerprint 的分子去重（`dedup.rs` / `dedup.py`）。GESim 提供了一种**不依赖 fingerprint 哈希碰撞**的替代方案：

- **优势**：GESim 考虑全局图结构，能区分 ECFP 可能混淆的高度相似分子（如位置异构体、环化变体）
- **接口**：GESim 提供 RDKit-compatible Python API (`gesim.graph_entropy_similarity(m1, m2)`)，集成成本低
- **可视化**：`gesim.get_matched_mapping_numbers()` 可展示原子级匹配，对用户对齐和审核非常有价值

**落地路径**：
```python
# 在分子数据库去重/聚类阶段，增加 GESim 作为可选相似性后端
from mbforge.molecules.similarity import compute_similarity

# 默认：ECFP + Tanimoto
# 可选：GESim (graph entropy)
sim = compute_similarity(mol1, mol2, method="gesim")
```

### 4.2 虚拟筛选与分子库探索：引入 ROSHAMBO2

MBForge 的 Agent 系统在用户查询时可以做**基于形状的分子检索**。ROSHAMBO2 是理想的 3D 相似性后端：

- **GPU 加速**：MBForge 的 Python sidecar 已有 CUDA 环境（PyTorch），ROSHAMBO2 可直接复用
- **大规模筛选**：支持对项目分子库做形状相似性搜索，而不仅是子结构/拓扑搜索
- **query 准备**：可结合 RDKit / CDPKit 的 conformer generation 为 ROSHAMBO2 准备 query 构象

**落地路径**：
```python
# Agent 工具：shape_search
from mbforge.models.shape_search import Roshambo2Screening

results = Roshambo2Screening.search(
    query_sdf="query_conf.sdf",
    library_sdf="project_library.sdf",
    metric="RefTverskyCombo",  # query-biased
    top_k=100,
)
```

### 4.3 多维度相似性融合

GESim（2D 拓扑）和 ROSHAMBO2（3D 形状）可以**联合使用**，构建更 robust 的分子相似性评估：

| 应用场景 | GESim | ROSHAMBO2 | 融合策略 |
|---------|-------|-----------|---------|
| 分子去重 | ✅ 主 | ❌ | 阈值过滤 |
| 骨架跃迁发现 | ❌ | ✅ 主 | 3D 筛选 → 人工审核 |
| 专利规避 | ✅ | ✅ | 两者都低 = 安全区域 |
| SAR 分析 | ✅ | ✅ | 2D 聚类 + 3D 形状验证 |
| 虚拟筛选 | 预过滤 | ✅ 主 | GESim 粗筛 → ROSHAMBO2 精筛 |

**具体融合策略**：
1. **Cascade 筛选**：先用 GESim（或 ECFP）做粗筛（百万→万级），再用 ROSHAMBO2 做精筛
2. **Score 融合**：`combined_score = α * gesim_score + β * roshambo_score`，通过机器学习训练权重
3. **Conformer-aware GESim**：在 GESim 的 Graph Aligner 阶段，将 3D 距离信息融入节点匹配

### 4.4 与现有架构的整合点

| MBForge 模块 | 整合方式 |
|-------------|---------|
| `molecule/`（分子数据库） | 新增 `similarity_gesim`、`similarity_roshambo` 字段 |
| `document/`（知识库） | 文档关联的分子增加 3D 构象和形状指纹索引 |
| `agent.rs` / `executor/` | 新增 `shape_search`、`scaffold_hop` Agent 工具 |
| `model_server/` | 新增 `/api/v1/shape_search` FastAPI 路由，调用 ROSHAMBO2 |
| `frontend/` | 分子库页面增加 "Shape Similarity Search" 和 "GESim Cluster" 功能 |

---

## 5. Actionable TODOs

| 优先级 | 任务 | 模块 | 备注 |
|--------|------|------|------|
| P1 | 集成 GESim 作为分子去重的可选后端 | `core/molecule/dedup.rs` / Python fallback | GESim 有 RDKit-compatible API，集成简单 |
| P1 | 集成 ROSHAMBO2 作为 3D 形状搜索后端 | `model_server/routers/` | 需确认 CUDA 兼容性，复用现有 GPU 环境 |
| P2 | 为项目分子库生成 3D 构象 + 形状指纹 | `parsers/molecule/` | 使用 RDKit / CDPKit `confgen` |
| P2 | 新增 Agent 工具：`shape_search` | `core/executor/mod.rs` | 接收 query SMILES/SDF，返回相似分子列表 |
| P2 | 新增 Agent 工具：`scaffold_hop` | `core/executor/mod.rs` | 结合 GESim + ROSHAMBO2 发现骨架跃迁 |
| P3 | 多维度相似性评分融合 | `core/molecule/similarity_fusion.py` | 训练 α/β 权重，或让用户手动调节 |
| P3 | 前端：分子库 shape search UI | `frontend/src/components/project/` | 上传 query SDF，选择 metric，展示 3D overlay |

---

## 6. 相关引用

- Shiokawa, H.; Ishida, S.; Terayama, K. *J. Cheminf.*, **2025**, 17, 57. DOI: [10.1186/s13321-025-01003-6](https://doi.org/10.1186/s13321-025-01003-6)
- GESim GitHub: https://github.com/LazyShion/GESim
- Atwi, R.; et al. *J. Chem. Inf. Model.*, **2025**, 65, 19. DOI: [10.1021/acs.jcim.5c01322](https://doi.org/10.1021/acs.jcim.5c01322)
- ROSHAMBO2 GitHub: https://github.com/molecularinformatics/roshambo2
- ROSHAMBO (v1) GitHub: https://github.com/molecularinformatics/roshambo
- ROSHAMBO (v1) ChemRxiv: https://doi.org/10.26434/chemrxiv-2024-6wk09
