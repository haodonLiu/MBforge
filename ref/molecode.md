# MoleCode — 显式图分子表示 + VLM OCSR

> 来源: ref/MoleCode（本地仓库）
> 论文: MoleCode — Subgraph–Node–Edge 语法表示分子结构
> 状态: 待评估集成

## 核心论文贡献

MoleCode 不是新工具，而是**表示理论**：科学对象的 LLM 接口应将结构本身作为语言，而非从文本解码结构。

### 关键发现

> "It changes how inference is allocated, replacing long reasoning traces devoted to implicit structural reconstruction with shorter, more chemically directed reasoning over explicit atoms and bonds."

表示格式的改变改变认知负荷分配——从"语法解析"转向"化学推理"。

### 实证数据

| 场景 | SMILES 准确率 | MoleCode 准确率 | 提升来源 |
|------|--------------|----------------|---------|
| 熟悉分子 | ~42% | ~76-80% | 减少结构重建错误 |
| 陌生分子 | ~20% | ~76-80% | 泛化而非记忆 |
| 复杂+陌生 | ~16% | ~72% | 推理成本亚线性增长 |
| Markush | 38.1% | 84.0% | 显式 R-group 节点 |
| 聚合物 | →0% | 稳定 | 显式重复单元+×n |
| 总 token 成本 | ~10,370 | ~2,005 | 长输入/短 CoT |

**核心洞察**: 输入更长（~38.4·C tokens vs SMILES ~2.0·C），但推理链更短（~C^0.52 vs ~C^1.65），总成本降低 5 倍。

## MoleCode 语法结构

```mermaid
subgraph Aspirin
    Aspirin_C_1[C]      ← 持久 ID
    Aspirin_C_2[C]
    Aspirin_O_3[OH]
    Aspirin_C_1 --- Aspirin_C_2   ← 显式边
    Aspirin_C_2 === Aspirin_O_3   ← 键级显式
end
```

关键特性：
- **持久原子标识符**（Aspirin_C_1 vs SMILES 的 c1 临时符号）
- **显式边声明**（---, ===, ~~~）
- **子图模块化**（subgraph 组织）
- **R-group 显式节点**（{R1} 而非标签）

## vs E-SMILES: 互补而非替代

| 维度 | E-SMILES | MoleCode |
|------|----------|----------|
| 表示层级 | 字符串（线性） | 图（显式节点+边） |
| 原子身份 | 临时符号 | 持久标识符 |
| 拓扑信息 | 隐式（位置+数字） | 显式（边声明） |
| 可组合性 | 低（字符串拼接易错） | 高（子图可独立定义后连接） |
| LLM 认知负荷 | 高（需重建图） | 低（直接读图） |
| 空间效率 | ✅ 紧凑 | ❌ 冗长 |
| 版本控制 | ⚠️ 整行变化 | ✅ git diff 有意义 |
| 传统工具兼容 | ✅ RDKit 原生 | ❌ 需转换 |

**结论**: 存储用 E-SMILES，推理/编辑时用 MoleCode（双轨制）。

## MoleCode OCSR 方法

```
分子图像 (PNG)
    → 通用 VLM (GPT-4o/Gemini/Claude Vision) + MARKUSH_SYSTEM_PROMPT
    → MoleCode Mermaid 图 (文本)
    → mermaid_to_mol() → RDKit Mol → SMILES
```

vs MBForge 的 MolScribe 管线：

| 维度 | MoleCode OCSR | MBForge MolScribe |
|------|--------------|-------------------|
| 模型类型 | 通用 VLM（零训练） | 专用模型（需训练数据） |
| 输出格式 | 显式图（可审计） | 隐式字符串（SMILES） |
| 错误恢复 | 可解析性检查 + VLM 重试 | 一旦出错需人工纠正 |
| 可扩展性 | 新结构类型 = 更新 prompt | 新结构类型 = 重新训练 |
| Markush 支持 | 原生 | 不支持 |
| 速度 | 慢（VLM API） | 快（本地 GPU） |

## 与 MBForge 的结合方案

### 方案 A: 最小侵入 — Agent 分子工具的备选表示

在 Agent 推理场景中，将分子转换为 MoleCode 图再输入 LLM：
- 成本：Python sidecar 新增 `/molecode/convert` 端点，~50 行
- 收益：论文验证的推理准确率提升

### 方案 B: OCSR 增强 — VLM + MoleCode 作为 MolScribe 的 fallback

```
图像 → MolScribe
    ├── 成功（confidence > 0.8）→ E-SMILES
    └── 失败/低置信度
            → VLM + MARKUSH_SYSTEM_PROMPT → MoleCode 图
            → mermaid_to_mol → SMILES → E-SMILES
```

创新点：VLM 输出 MoleCode 图时可在前端渲染为交互式图，让用户点击验证。

### 方案 C: 专利 Markush 结构化存储（最大创新点）

```json
{
    "scaffold": "MoleCode 图字符串",
    "r_groups": {
        "R1": ["SMILES_1", "SMILES_2"],
        "R2": ["SMILES_3"]
    },
    "constraints": "R1 != H if R2 = Cl"
}
```

Agent 可直接操作：
- "将 R1 从甲基改为乙基" = 局部替换一个节点
- "枚举所有 R1×R2 组合" = 笛卡尔积生成
- "检查是否侵犯专利 X" = 子图匹配

### 方案 D: 跨文档分子身份追踪（最有前景）

利用 MoleCode 持久原子 ID，在不同文档间建立分子精确对应：

```
Document A (专利)          Document B (论文)           Document C (审查意见)
    ├── 化合物 I (MoleCode)    ├── 相同结构 (不同编号)      ├── 引用化合物 I
    └── "R1 = Me"              └── "IC50 = 5.2 nM"          └── "缺乏创造性"
                                    ↓
                          统一分子身份: Molecule_X
                          (基于 MoleCode 图的 canonical hash)
```

解决"同一分子在不同文档中编号不同"的问题。

## 四层分子表示模型

```
Layer 4: 化学语义层 — 功能基团、药理性质、反应位点（LLM 推理）
Layer 3: 图结构层   — MoleCode 显式图（持久 ID + 显式边）← MBForge 缺失
Layer 2: 分子对象层 — RDKit Mol（标准化学信息学）
Layer 1: 线性字符串 — E-SMILES / InChI（存储、交换）
```

MBForge 当前缺少 Layer 3，导致：
1. Agent 分子编辑时每次修改都是"重新生成 E-SMILES"，无法局部图操作
2. Markush 依赖标签解析而非显式 R-group 节点
3. 分子-文本关联无法精确定位"哪个原子在哪个位置"

## 想法: 分子版本控制

Git 对 SMILES 的 diff 无意义（整行变化），对 MoleCode 的 diff 有意义：

```diff
-     Aspirin_C_1[CH3]
+     Aspirin_C_1[CH2]           ← 失去一个 H
+     Aspirin_C_4[CH3]           ← 新加的甲基
+     Aspirin_C_1 --- Aspirin_C_4  ← 新键
```

分子版本控制系统：追踪编辑历史，每个 commit 是一个局部图操作。

## 优先级评估

| 方案 | 优先级 | 工作量 | 收益 |
|------|--------|--------|------|
| A: Agent 备选表示 | P2 | 小（~50 行） | 推理准确率提升 |
| B: OCSR fallback | P1 | 中 | Markush/复杂结构识别 |
| C: Markush 结构化存储 | P2 | 中 | 专利分析创新 |
| D: 跨文档分子追踪 | P3 | 大 | 长期价值最高 |
| 分子版本控制 | P3 | 大 | 创新性最高 |

**魔鬼代言人评论**: MoleCode 论文是理论性的，实际代码库只有转换器和文件 I/O，没有生产级实现。集成前需评估 mermaid_to_mol 的可靠性和覆盖率。
