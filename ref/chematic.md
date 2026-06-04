# Chematic — 纯 Rust 化学信息学库

> 来源: https://github.com/kent-tokyo/chematic
> 许可: Apache 2.0 + MIT
> 状态: 已集成到 MBForge（core/chem.rs）

## 概述

chematic 是纯 Rust 化学信息学库，目标是与 RDKit 功能对等，零 C/C++ FFI。736 个测试，ChEMBL 2.9M 分子 100% 通过。

## 模块架构

| Crate | 功能 | MBForge 用途 |
|-------|------|-------------|
| `chematic-core` | Molecule 结构、Kekulization、元素数据 | 分子对象基础 |
| `chematic-smiles` | OpenSMILES 解析/写入、canonical SMILES | SMILES 校验规范化 |
| `chematic-fp` | ECFP4/6、MACCS、AtomPair、Torsion FP、Tanimoto/Dice | 指纹存储+相似度搜索 |
| `chematic-smarts` | SMARTS 解析、VF2 子图同构、MCS | 子结构搜索、SAR 分析 |
| `chematic-chem` | MW/LogP/TPSA/QED/Lipinski/Murcko/BRICS/CIP/VSA/SA | 分子描述符 |
| `chematic-mol` | MOL/SDF V2000+V3000 读写 | 化学文件格式 |
| `chematic-depict` | 2D SVG 渲染（CPK 配色、高亮） | 分子可视化 |
| `chematic-rxn` | 反应 SMILES/SMIRKS 解析 | 反应路线分析 |
| `chematic-3d` | 3D 坐标生成、UFF 能量最小化、PDB/XYZ | 分子构象 |
| `chematic-perception` | SSSR 环检测、Hückel 芳香性 | 环系分析 |
| `chematic-wasm` | WebAssembly 绑定 | 前端分子预览 |

## 与 RDKit 的能力对照

| 能力 | RDKit (Python) | Chematic (Rust) | 状态 |
|------|---------------|-----------------|------|
| SMILES 解析 | ✅ | ✅ | 已替代 |
| 指纹计算 | Morgan FP | ECFP4/6 | 已替代 |
| Tanimoto 相似度 | ✅ | ✅ | 已替代 |
| 子结构搜索 | HasSubstructMatch | VF2 子图同构 | 已替代 |
| 分子描述符 | MW/LogP/TPSA/QED | ✅ | 待接入 |
| MCS | rdFMCS.FindMCS | ✅ | 待接入 |
| MOL/SDF 读写 | ✅ | ✅ | 待接入 |
| 2D 绘图 | matplotlib | SVG | 待接入 |
| 3D 构象 | EmbedMolecule | ✅ | 待接入 |
| 反应 SMILES | ✅ | ✅ | 待接入 |

## 已集成到 MBForge

`src-tauri/src/core/chem.rs` 提供：
- `validate_smiles()` — SMILES 校验 + canonical 化
- `compute_ecfp4()` — 2048-bit ECFP4 指纹
- `tanimoto_similarity()` — 两分子 Tanimoto 相似度
- `tanimoto_batch_filter()` — 批量 Tanimoto 预过滤
- `substructure_search()` — VF2 子结构搜索
- `substructure_search_with_filter()` — 三级漏斗（Tanimoto → VF2）

## 待验证

chematic 通过 git 依赖引入（未发布 crates.io），API 可能随版本变化。需验证编译正确性。
