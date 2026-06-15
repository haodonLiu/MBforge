//! Cheminformatics pure-computation Tauri commands.
//!
//! 这些命令**无状态**、**不持锁**、**不依赖 sidecar**，直接转发到 `core::chem/*`。
//! 用于前端做"实时"化学计算（SMILES 校验、规范化、子结构搜索、Markush 解析等），
//! 避免每个调用都走 model_server HTTP。
//!
//! 既有命令在 `commands/molecule.rs`（`chem_validate_smiles` 等）和
//! `commands/molecode.rs`（`esmiles_to_molecode_cmd` / `chem_descriptors_cmd`）
//! 中；本文件补全剩余 14 个高价值纯计算入口。

use chematic_smiles::parse as chematic_parse;
use serde::{Deserialize, Serialize};

use crate::core::chem::chem;
use crate::core::chem::esmiles::{self as esmiles, EsTag};
use crate::core::chem::gesim;
use crate::core::chem::markush;
use crate::core::chem::preprocess;
use crate::parsers::chem::chem_validate;

// ============================================================================
// DTOs (surgical: 不改 core/chem/* 的 Serialize 实现，本地 DTO 转换)
// ============================================================================

/// 前端传入的标签（与 esmiles::EsTag 同形，不修改 EsTag 的 derive）
#[derive(Debug, Clone, Deserialize)]
pub struct EsTagInput {
    /// "atom" | "ring" | "circle"
    pub kind: String,
    pub index: usize,
    pub value: String,
}

impl EsTagInput {
    fn into_estag(self) -> Result<EsTag, String> {
        match self.kind.as_str() {
            "atom" => Ok(EsTag::atom(self.index, self.value)),
            "ring" => Ok(EsTag::ring(self.index, self.value)),
            "circle" => Ok(EsTag::circle(self.index, self.value)),
            other => Err(format!("Unknown EsTag kind: {other}")),
        }
    }
}

/// 前端出参标签
#[derive(Debug, Clone, Serialize)]
pub struct EsTagOutput {
    pub kind: &'static str,
    pub index: usize,
    pub value: String,
}

impl From<&EsTag> for EsTagOutput {
    fn from(t: &EsTag) -> Self {
        match t {
            EsTag::Atom { index, group } => Self {
                kind: "atom",
                index: *index,
                value: group.clone(),
            },
            EsTag::Ring { index, group } => Self {
                kind: "ring",
                index: *index,
                value: group.clone(),
            },
            EsTag::Circle { index, name } => Self {
                kind: "circle",
                index: *index,
                value: name.clone(),
            },
        }
    }
}

/// ValidateResult 的 IPC DTO（chem_validate::ValidateResult 无 Serialize）
#[derive(Debug, Clone, Serialize)]
pub struct ValidateResultDto {
    pub input: String,
    pub valid: bool,
    pub canonical_smiles: Option<String>,
    pub error: Option<String>,
}

/// LayerSplit: 来自 chem_validate::separate_esmiles_layers
#[derive(Debug, Clone, Serialize)]
pub struct LayerSplit {
    pub smiles: String,
    pub esmiles: Option<String>,
    pub tags: Option<serde_json::Value>,
}

/// PreprocessError 的 IPC DTO
#[derive(Debug, Clone, Serialize)]
pub struct PreprocessErrorDto {
    pub kind: String,
    pub message: String,
}

impl From<&preprocess::PreprocessError> for PreprocessErrorDto {
    fn from(e: &preprocess::PreprocessError) -> Self {
        let (kind, message) = match e {
            preprocess::PreprocessError::Empty => ("empty".to_string(), e.to_string()),
            preprocess::PreprocessError::TooLong { len, max } => (
                "too_long".to_string(),
                format!("SMILES too long: {len} > {max}"),
            ),
            preprocess::PreprocessError::ContainsSpaces => {
                ("contains_spaces".to_string(), e.to_string())
            }
        };
        Self { kind, message }
    }
}

// ============================================================================
// 1. chem_canonicalize
// ============================================================================

/// 标准化 SMILES（chematic 稳定化算法）。
#[tauri::command]
pub fn chem_canonicalize(smiles: String) -> Result<String, String> {
    let mol = chematic_parse(&smiles).map_err(|e| format!("SMILES parse failed: {e}"))?;
    Ok(chematic_smiles::canonical_smiles(&mol))
}

// ============================================================================
// 2. chem_substructure_search
// ============================================================================

/// 子结构搜索：Tanimoto 预过滤 + VF2 精确验证（候选列表由前端提供，不读 DB）。
#[tauri::command]
pub fn chem_substructure_search(
    query: String,
    candidates: Vec<(String, String)>,
    threshold: Option<f64>,
) -> Result<Vec<(String, String, f64)>, String> {
    chem::substructure_search_with_filter(&query, &candidates, threshold.unwrap_or(0.3))
}

// ============================================================================
// 3. chem_smiles_to_molecode
// ============================================================================

/// 纯 SMILES → MoleCode (Mermaid graph text)。补齐 esmiles_to_molecode_cmd 的纯 SMILES 路径。
#[tauri::command]
pub fn chem_smiles_to_molecode(smiles: String, name: String) -> Result<String, String> {
    let result = chem::smiles_to_molecode(&smiles, &name)?;
    Ok(result.mermaid)
}

// ============================================================================
// 4. chem_smiles_to_esmiles
// ============================================================================

/// 给 SMILES 添加 E-SMILES 标签。
#[tauri::command]
pub fn chem_smiles_to_esmiles(smiles: String, tags: Vec<EsTagInput>) -> Result<String, String> {
    let tags: Vec<EsTag> = tags
        .into_iter()
        .map(EsTagInput::into_estag)
        .collect::<Result<_, _>>()?;
    Ok(esmiles::smiles_to_esmiles(&smiles, &tags))
}

// ============================================================================
// 5. chem_parse_esmiles_tags
// ============================================================================

/// 从 E-SMILES 字符串中分离 SMILES + 标签列表。
#[tauri::command]
pub fn chem_parse_esmiles_tags(input: String) -> Result<(String, Vec<EsTagOutput>), String> {
    let (smiles, tags) = esmiles::parse_esmiles_tags(&input);
    let out: Vec<EsTagOutput> = tags.iter().map(EsTagOutput::from).collect();
    Ok((smiles, out))
}

// ============================================================================
// 6. chem_sanitize_esmiles
// ============================================================================

/// 清洗 LLM 污染的 E-SMILES（反引号、解释性前缀、空白）。
#[tauri::command]
pub fn chem_sanitize_esmiles(raw: String) -> String {
    chem_validate::sanitize_esmiles(&raw)
}

// ============================================================================
// 7. chem_separate_esmiles_layers
// ============================================================================

/// 三层分离：纯 SMILES + 原始 E-SMILES + 语义标签 JSON。
#[tauri::command]
pub fn chem_separate_esmiles_layers(input: String) -> LayerSplit {
    let (smiles, esmiles, tags) = chem_validate::separate_esmiles_layers(&input);
    LayerSplit {
        smiles,
        esmiles,
        tags,
    }
}

// ============================================================================
// 8. chem_validate_smiles_batch
// ============================================================================

/// 批量 SMILES 验证（单条失败不中断整批）。
#[tauri::command]
pub fn chem_validate_smiles_batch(list: Vec<String>) -> Vec<ValidateResultDto> {
    chem_validate::validate_smiles_batch(&list)
        .into_iter()
        .map(|(input, r)| ValidateResultDto {
            input,
            valid: r.valid,
            canonical_smiles: r.canonical_smiles,
            error: r.issues.first().map(|i| i.message.clone()),
        })
        .collect()
}

// ============================================================================
// 9. chem_preprocess_smiles
// ============================================================================

/// SMILES 文本级预处理（验证 + wildcard 归一化）。
#[tauri::command]
pub fn chem_preprocess_smiles(smiles: String) -> Result<String, PreprocessErrorDto> {
    preprocess::preprocess_smiles(&smiles).map_err(|e| PreprocessErrorDto::from(&e))
}

// ============================================================================
// 10. chem_preprocess_rgroup_name
// ============================================================================

/// R-group 名称预处理（验证 + 缩写归一化）。
#[tauri::command]
pub fn chem_preprocess_rgroup_name(name: String) -> Result<String, PreprocessErrorDto> {
    preprocess::preprocess_rgroup_name(&name).map_err(|e| PreprocessErrorDto::from(&e))
}

// ============================================================================
// 11. chem_markush_parse
// ============================================================================

/// E-SMILES → MarkushPattern（MarkushPattern 已有 Serialize/Deserialize）。
#[tauri::command]
pub fn chem_markush_parse(input: String) -> markush::MarkushPattern {
    markush::parse_esmiles(&input)
}

// ============================================================================
// 12. chem_markush_check
// ============================================================================

/// Markush 覆盖度检查（纯计算路径，不走 engine）。
#[tauri::command]
pub fn chem_markush_check(
    esmiles: String,
    query: String,
    ctx: Option<String>,
) -> markush::MarkushOverlap {
    markush::analyze_markush_coverage(&esmiles, &query, ctx.as_deref())
}

// ============================================================================
// 13. chem_core_smiles
// ============================================================================

/// 提取 E-SMILES 中的 core SMILES 部分（<sep> 之前）。
#[tauri::command]
pub fn chem_core_smiles(input: String) -> String {
    markush::core_smiles(&input).to_string()
}

// ============================================================================
// 14. chem_gesim_atom_mapping
// ============================================================================

/// GESim 原子级对齐：返回 (a→b, b→a) 的双向索引序列（None 表示无匹配）。
#[tauri::command]
pub fn chem_gesim_atom_mapping(a: String, b: String) -> Result<[Vec<Option<usize>>; 2], String> {
    let mol_a = chematic_parse(&a).map_err(|e| format!("SMILES a parse error: {e}"))?;
    let mol_b = chematic_parse(&b).map_err(|e| format!("SMILES b parse error: {e}"))?;
    let (m1, m2) = gesim::match_mapping(&mol_a, &mol_b);
    Ok([m1, m2])
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// `pub(crate)` 包装，避开 `#[tauri::command]` 宏签名不可直调的约束。
    /// 仅供本测试模块使用。
    fn chem_sanitize_esmiles_for_test(raw: &str) -> String {
        chem_validate::sanitize_esmiles(raw)
    }

    fn chem_parse_esmiles_tags_for_test(input: &str) -> (String, Vec<EsTagOutput>) {
        let (smiles, tags) = esmiles::parse_esmiles_tags(input);
        (smiles, tags.iter().map(EsTagOutput::from).collect())
    }

    #[test]
    fn test_chem_sanitize_strips_markdown() {
        // LLM 经常输出反引号包裹的 SMILES
        let out = chem_sanitize_esmiles_for_test("`CCO`");
        assert_eq!(out, "CCO");

        // 解释性前缀也应被去除
        let out2 = chem_sanitize_esmiles_for_test("SMILES: CCO");
        assert_eq!(out2, "CCO");

        // 前后空白
        let out3 = chem_sanitize_esmiles_for_test("  CCO  ");
        assert_eq!(out3, "CCO");
    }

    #[test]
    fn test_chem_parse_esmiles_tags_roundtrip() {
        let (smiles, tags) = chem_parse_esmiles_tags_for_test("CCO<sep><a>0:R1</a>");
        assert_eq!(smiles, "CCO");
        assert_eq!(tags.len(), 1);
        assert_eq!(tags[0].kind, "atom");
        assert_eq!(tags[0].index, 0);
        assert_eq!(tags[0].value, "R1");
    }
}
