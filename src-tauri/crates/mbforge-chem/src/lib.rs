//! mbforge-chem: 纯 Rust 化学信息学工具库
//!
//! 提供 SMILES 校验/规范化、ECFP4 指纹、Tanimoto 相似度、子结构搜索、
//! E-SMILES 标签、MoleCode 生成、Markush 模式解析以及 SAR 分析等化学
//! 信息学基础能力。
//!
//! 该 crate 基于 [`chematic`](https://github.com/kent-tokyo/chematic) 实现，
//! 替代原有的 Python RDKit sidecar，用于 MBForge 桌面端。

mod abbreviation_map;
pub mod esmiles;
pub mod gesim;
pub mod markush;
pub mod molecode;
pub mod preprocess;
pub mod sar;
pub mod smiles;

/// 向后兼容别名：旧代码中的 `core::chem::chem` 对应新的 `smiles` 模块。
pub use smiles as chem;

pub use abbreviation_map::{find_abbrev, normalize_abbrev_name, AbbrevDef};
pub use esmiles::{parse_esmiles_tags, smiles_to_esmiles, smiles_with_rgroups_to_esmiles, EsTag};
pub use markush::{check_overlap, MarkushOverlap, MarkushPattern};
pub use molecode::{esmiles_to_molecode, smiles_to_molecode, MoleCodeResult};
pub use sar::{
    build_activity_heatmap, build_rgroup_matrix, decompose_compound, find_common_scaffold,
    CompoundInput, RGroupDecomposition, RGroupMatrix, ScaffoldResult,
};
pub use smiles::{
    compute_descriptors, compute_ecfp4, compute_ecfp4_as_bytes, substructure_search,
    tanimoto_similarity, validate_smiles, ChemDescriptors, SmilesValidation,
};
