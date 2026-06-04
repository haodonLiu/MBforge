//! 纯 Rust 化学信息学 — 基于 chematic，替代 Python RDKit sidecar
//!
//! 提供：
//! - SMILES 解析和校验
//! - Morgan/ECFP 指纹计算
//! - Tanimoto 相似度
//! - VF2 子结构搜索
//!
//! 注意：chematic 的实际 API 与初始假设不同，当前使用占位实现。
//! 待 Task B 时适配实际 API：parse_smiles(), canonical_smiles(), ecfp4(), tanimoto_ecfp4()

/// SMILES 校验结果
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SmilesValidation {
    pub valid: bool,
    pub canonical_smiles: Option<String>,
    pub error: Option<String>,
}

/// 校验并规范化 SMILES（占位实现，待适配 chematic API）
pub fn validate_smiles(smiles: &str) -> SmilesValidation {
    // TODO: 使用 chematic_smiles::parse(smiles) + canonical_smiles()
    if smiles.is_empty() || smiles.len() > 10000 {
        return SmilesValidation {
            valid: false,
            canonical_smiles: None,
            error: Some("Invalid SMILES: empty or too long".into()),
        };
    }
    // 基本格式检查：SMILES 不应包含空格
    if smiles.contains(' ') {
        return SmilesValidation {
            valid: false,
            canonical_smiles: None,
            error: Some("Invalid SMILES: contains spaces".into()),
        };
    }
    SmilesValidation {
        valid: true,
        canonical_smiles: Some(smiles.to_string()),
        error: None,
    }
}

/// 计算 ECFP4 指纹（占位实现，待适配 chematic_fp::ecfp4()）
pub fn compute_ecfp4(_smiles: &str) -> Result<Vec<u8>, String> {
    // TODO: 使用 chematic_fp::ecfp4(mol) -> BitVec2048 -> Vec<u8>
    Err("ECFP4 not yet implemented (chematic API adaptation pending)".into())
}

/// 计算两个 SMILES 之间的 Tanimoto 相似度
pub fn tanimoto_similarity(smiles1: &str, smiles2: &str) -> Result<f64, String> {
    let fp1 = compute_ecfp4(smiles1)?;
    let fp2 = compute_ecfp4(smiles2)?;
    Ok(tanimoto_bytes(&fp1, &fp2))
}

/// 批量 Tanimoto 预过滤
pub fn tanimoto_batch_filter(
    query_smiles: &str,
    candidates: &[(String, String)],
    threshold: f64,
) -> Result<Vec<(String, String, f64)>, String> {
    let query_fp = compute_ecfp4(query_smiles)?;

    let mut results = Vec::new();
    for (mol_id, smiles) in candidates {
        let fp = match compute_ecfp4(smiles) {
            Ok(fp) => fp,
            Err(_) => continue,
        };
        let score = tanimoto_bytes(&query_fp, &fp);
        if score >= threshold {
            results.push((mol_id.clone(), smiles.clone(), score));
        }
    }

    results.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal));
    Ok(results)
}

/// 子结构搜索（占位实现，待适配 chematic_smarts::find_matches()）
pub fn substructure_search(
    _query_smiles: &str,
    _candidates: &[(String, String)],
) -> Result<Vec<(String, String)>, String> {
    // TODO: 使用 chematic_smarts::parse_smarts() + find_matches()
    Err("Substructure search not yet implemented (chematic API adaptation pending)".into())
}

/// 三级漏斗：Tanimoto 预过滤 + VF2 子结构搜索
pub fn substructure_search_with_filter(
    query_smiles: &str,
    candidates: &[(String, String)],
    tanimoto_threshold: f64,
) -> Result<Vec<(String, String, f64)>, String> {
    let filtered = tanimoto_batch_filter(query_smiles, candidates, tanimoto_threshold)?;

    let filtered_pairs: Vec<(String, String)> = filtered
        .iter()
        .map(|(id, smiles, _)| (id.clone(), smiles.clone()))
        .collect();

    let matches = substructure_search(query_smiles, &filtered_pairs)?;

    let match_set: std::collections::HashSet<String> =
        matches.iter().map(|(id, _)| id.clone()).collect();

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
        assert_eq!(result.canonical_smiles.unwrap(), "CCO");
    }

    #[test]
    fn test_validate_smiles_empty() {
        let result = validate_smiles("");
        assert!(!result.valid);
    }

    #[test]
    fn test_validate_smiles_with_spaces() {
        let result = validate_smiles("CC O");
        assert!(!result.valid);
    }

    #[test]
    fn test_tanimoto_bytes() {
        let a = vec![0xFF, 0x00];
        let b = vec![0xFF, 0x00];
        assert!((tanimoto_bytes(&a, &b) - 1.0).abs() < 0.01);

        let c = vec![0x00, 0xFF];
        assert!(tanimoto_bytes(&a, &c) < 0.01);
    }
}
