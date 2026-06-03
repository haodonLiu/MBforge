//! 纯 Rust 化学信息学 — 基于 chematic，替代 Python RDKit sidecar
//!
//! 提供：
//! - SMILES 解析和校验
//! - Morgan/ECFP 指纹计算
//! - Tanimoto 相似度
//! - VF2 子结构搜索
//! - 分子描述符（MW, LogP, TPSA 等）

use schematic_core::Molecule;
use schematic_smiles::SmilesParser;
use schematic_fp::{EcfpOptions, Fingerprint};
use schematic_smarts::SmartsPattern;

/// SMILES 校验结果
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SmilesValidation {
    pub valid: bool,
    pub canonical_smiles: Option<String>,
    pub error: Option<String>,
}

/// 校验并规范化 SMILES
pub fn validate_smiles(smiles: &str) -> SmilesValidation {
    match SmilesParser::parse(smiles) {
        Ok(mol) => {
            let canonical = mol.to_smiles();
            SmilesValidation {
                valid: true,
                canonical_smiles: Some(canonical),
                error: None,
            }
        }
        Err(e) => SmilesValidation {
            valid: false,
            canonical_smiles: None,
            error: Some(format!("Parse failed: {}", e)),
        },
    }
}

/// 计算 ECFP4 指纹（2048 bit Morgan 指纹）
///
/// 返回 256 bytes 的位向量（与 RDKit Morgan 指纹格式兼容）
pub fn compute_ecfp4(smiles: &str) -> Result<Vec<u8>, String> {
    let mol = SmilesParser::parse(smiles)
        .map_err(|e| format!("SMILES parse failed: {}", e))?;

    let opts = EcfpOptions {
        radius: 2,
        num_bits: 2048,
        ..Default::default()
    };

    let fp = mol.ecfp(opts)
        .map_err(|e| format!("ECFP computation failed: {}", e))?;

    Ok(fp.to_bytes())
}

/// 计算两个 SMILES 之间的 Tanimoto 相似度
pub fn tanimoto_similarity(smiles1: &str, smiles2: &str) -> Result<f64, String> {
    let fp1 = compute_ecfp4(smiles1)?;
    let fp2 = compute_ecfp4(smiles2)?;
    Ok(tanimoto_bytes(&fp1, &fp2))
}

/// 批量 Tanimoto 预过滤
///
/// 返回 (smiles, score) 对，只包含 score >= threshold 的
pub fn tanimoto_batch_filter(
    query_smiles: &str,
    candidates: &[(String, String)],  // (mol_id, smiles)
    threshold: f64,
) -> Result<Vec<(String, String, f64)>, String> {
    let query_fp = compute_ecfp4(query_smiles)?;

    let mut results = Vec::new();
    for (mol_id, smiles) in candidates {
        let fp = match compute_ecfp4(smiles) {
            Ok(fp) => fp,
            Err(_) => continue, // 跳过无法解析的分子
        };
        let score = tanimoto_bytes(&query_fp, &fp);
        if score >= threshold {
            results.push((mol_id.clone(), smiles.clone(), score));
        }
    }

    // 按相似度降序排列
    results.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal));
    Ok(results)
}

/// 子结构搜索（VF2 子图同构）
///
/// 返回匹配的 SMILES 列表
pub fn substructure_search(
    query_smiles: &str,
    candidates: &[(String, String)],  // (mol_id, smiles)
) -> Result<Vec<(String, String)>, String> {
    let query_mol = SmilesParser::parse(query_smiles)
        .map_err(|e| format!("Query SMILES parse failed: {}", e))?;

    let pattern = SmartsPattern::from_molecule(&query_mol)
        .map_err(|e| format!("SMARTS pattern creation failed: {}", e))?;

    let mut matches = Vec::new();
    for (mol_id, smiles) in candidates {
        let mol = match SmilesParser::parse(smiles) {
            Ok(m) => m,
            Err(_) => continue,
        };

        if pattern.matches(&mol) {
            matches.push((mol_id.clone(), smiles.clone()));
        }
    }

    Ok(matches)
}

/// 三级漏斗：Tanimoto 预过滤 + VF2 子结构搜索（全 Rust，零 sidecar 调用）
pub fn substructure_search_with_filter(
    query_smiles: &str,
    candidates: &[(String, String)],  // (mol_id, smiles)
    tanimoto_threshold: f64,
) -> Result<Vec<(String, String, f64)>, String> {
    // 第一级：Tanimoto 指纹预过滤
    let filtered = tanimoto_batch_filter(query_smiles, candidates, tanimoto_threshold)?;

    // 第二级：VF2 子结构精确匹配
    let filtered_pairs: Vec<(String, String)> = filtered
        .iter()
        .map(|(id, smiles, _)| (id.clone(), smiles.clone()))
        .collect();

    let matches = substructure_search(query_smiles, &filtered_pairs)?;

    let match_set: std::collections::HashSet<String> =
        matches.iter().map(|(id, _)| id.clone()).collect();

    // 返回匹配的分子（保留 Tanimoto 分数）
    Ok(filtered
        .into_iter()
        .filter(|(id, _, _)| match_set.contains(id))
        .collect())
}

/// 字节级 Tanimoto 相似度计算
fn tanimoto_bytes(a: &[u8], b: &[u8]) -> f64 {
    if a.len() != b.len() || a.is_empty() {
        return 0.0;
    }

    let (mut intersection, mut union) = (0u32, 0u32);
    for (x, y) in a.iter().zip(b.iter()) {
        intersection += (x & y).count_ones();
        union += (x | y).count_ones();
    }

    if union == 0 {
        0.0
    } else {
        intersection as f64 / union as f64
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_smiles_valid() {
        let result = validate_smiles("CCO");
        assert!(result.valid);
        assert!(result.canonical_smiles.is_some());
    }

    #[test]
    fn test_validate_smiles_invalid() {
        let result = validate_smiles("this is not a smiles");
        assert!(!result.valid);
        assert!(result.error.is_some());
    }

    #[test]
    fn test_tanimoto_identical() {
        let score = tanimoto_similarity("CCO", "CCO").unwrap();
        assert!((score - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_tanimoto_different() {
        let score = tanimoto_similarity("CCO", "c1ccccc1").unwrap();
        assert!(score < 1.0);
    }

    #[test]
    fn test_ecfp4_length() {
        let fp = compute_ecfp4("CCO").unwrap();
        assert_eq!(fp.len(), 256); // 2048 bits / 8 = 256 bytes
    }

    #[test]
    fn test_substructure_search() {
        let candidates = vec![
            ("1".to_string(), "CCO".to_string()),
            ("2".to_string(), "c1ccccc1O".to_string()), // 苯酚，含苯环
            ("3".to_string(), "CC(=O)O".to_string()),    // 乙酸
        ];
        // 搜索含苯环的分子
        let matches = substructure_search("c1ccccc1", &candidates).unwrap();
        assert_eq!(matches.len(), 1);
        assert_eq!(matches[0].0, "2");
    }
}
