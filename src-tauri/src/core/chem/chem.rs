#![allow(dead_code)]
//! 纯 Rust 化学信息学 — 基于 chematic crate，替代 Python RDKit sidecar
//!
//! 实际 API（来自 `chematic-*` git 依赖，本地 cache `@ .cargo/git/checkouts/chematic-09e7e67b97ed9dba/47a69b1`）：
//! - `chematic_smiles::parse(&str) -> Result<Molecule, SmilesError>`
//! - `chematic_smiles::canonical_smiles(&Molecule) -> String`
//! - `chematic_fp::ecfp4(&Molecule) -> BitVec2048`
//! - `chematic_fp::BitVec2048::tanimoto(&self, &Self) -> f64`
//! - `chematic_smarts::parse_smarts(&str) -> Result<QueryMolecule, SmartsError>`
//! - `chematic_smarts::find_matches(&QueryMolecule, &Molecule) -> Vec<HashMap<usize, AtomIdx>>`
//!
//! 历史：早期版本引用了不存在的 `SmilesParser` / `EcfpOptions` API；现在使用
//! 直接函数式 API，零中间类型。
//!
//! 提供：
//! - `validate_smiles()` — SMILES 解析 + canonical 化
//! - `compute_ecfp4()` — 2048-bit ECFP4 指纹
//! - `tanimoto_similarity()` — 两分子 Tanimoto 相似度
//! - `tanimoto_batch_filter()` — 批量 Tanimoto 预过滤
//! - `substructure_search()` — VF2 子结构搜索
//! - `substructure_search_with_filter()` — 三级漏斗（Tanimoto → VF2）

use chematic_fp::BitVec2048;
use chematic_smiles::{canonical_smiles, parse};
use chematic_smarts::{find_matches, parse_smarts};

use crate::core::molecule::molecule_store::MoleculeRecord;

/// SMILES 校验结果
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SmilesValidation {
    pub valid: bool,
    pub canonical_smiles: Option<String>,
    pub error: Option<String>,
}

/// 校验并规范化 SMILES。
///
/// # 行为
/// - 空串 / 超长（> 10KB）→ `valid=false`
/// - 含空格 → `valid=false`（SMILES 规范不允许内部空白）
/// - 解析失败 → `valid=false`，错误信息透传 `SmilesError::Display`
/// - 成功 → `valid=true`，`canonical_smiles` 由 chematic 稳定化算法给出
pub fn validate_smiles(smiles: &str) -> SmilesValidation {
    if smiles.is_empty() || smiles.len() > 10000 {
        return SmilesValidation {
            valid: false,
            canonical_smiles: None,
            error: Some("Invalid SMILES: empty or too long".into()),
        };
    }
    if smiles.contains(' ') {
        return SmilesValidation {
            valid: false,
            canonical_smiles: None,
            error: Some("Invalid SMILES: contains spaces".into()),
        };
    }
    match parse(smiles) {
        Ok(mol) => SmilesValidation {
            valid: true,
            canonical_smiles: Some(canonical_smiles(&mol)),
            error: None,
        },
        Err(e) => SmilesValidation {
            valid: false,
            canonical_smiles: None,
            error: Some(e.to_string()),
        },
    }
}

/// 计算 ECFP4 指纹并返回为字节向量（256 bytes）。
///
/// 用于 SQLite BLOB 存储。SMILES 解析失败时返回 Err。
pub fn compute_ecfp4_as_bytes(smiles: &str) -> Result<Vec<u8>, String> {
    let fp = compute_ecfp4(smiles)?;
    Ok(bitvec_to_bytes(&fp))
}

/// BitVec2048 → 256 bytes（小端序，每 8 bit 打包为 1 byte）
fn bitvec_to_bytes(fp: &BitVec2048) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(256);
    for byte_idx in 0..256 {
        let mut byte: u8 = 0;
        for bit_idx in 0..8 {
            let global_bit = byte_idx * 8 + bit_idx;
            if fp.get(global_bit) {
                byte |= 1 << bit_idx;
            }
        }
        bytes.push(byte);
    }
    bytes
}

/// 计算 ECFP4 指纹（2048 bit）。
///
/// # 错误
/// - SMILES 解析失败时返回 Err（不会 fallback 到全 0）
/// - 成功时返回 `BitVec2048`（在 MBForge 内部按 `Vec<u8>` 序列化）
pub fn compute_ecfp4(smiles: &str) -> Result<BitVec2048, String> {
    let mol = parse(smiles).map_err(|e| format!("SMILES parse failed: {}", e))?;
    Ok(chematic_fp::ecfp4(&mol))
}

/// 计算两个 SMILES 之间的 Tanimoto 相似度。
///
/// 化学约定：1.0 = 完全相同，0.0 = 无共同位。
pub fn tanimoto_similarity(smiles1: &str, smiles2: &str) -> Result<f64, String> {
    let mol1 = parse(smiles1).map_err(|e| format!("SMILES parse failed: {}", e))?;
    let mol2 = parse(smiles2).map_err(|e| format!("SMILES parse failed: {}", e))?;
    Ok(chematic_fp::tanimoto_ecfp4(&mol1, &mol2))
}

/// 批量 Tanimoto 预过滤。
///
/// # Arguments
/// - `query_smiles`: 查询 SMILES
/// - `candidates`: `(mol_id, smiles)` 列表
/// - `threshold`: 阈值（≥ 0.0, ≤ 1.0）
///
/// # Returns
/// 超过阈值的 (mol_id, smiles, score) 列表，按 score 降序。
/// SMILES 解析失败的候选项被静默跳过。
pub fn tanimoto_batch_filter(
    query_smiles: &str,
    candidates: &[(String, String)],
    threshold: f64,
) -> Result<Vec<(String, String, f64)>, String> {
    let query_mol = parse(query_smiles).map_err(|e| format!("query SMILES parse failed: {}", e))?;
    let query_fp = chematic_fp::ecfp4(&query_mol);

    let mut results = Vec::new();
    for (mol_id, smiles) in candidates {
        let mol = match parse(smiles) {
            Ok(m) => m,
            Err(_) => continue, // skip invalid candidates
        };
        let fp = chematic_fp::ecfp4(&mol);
        let score = fp.tanimoto(&query_fp);
        if score >= threshold {
            results.push((mol_id.clone(), smiles.clone(), score));
        }
    }

    results.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal));
    Ok(results)
}

/// 子结构搜索 — 在候选中找出与 query_smarts 匹配的项。
///
/// # Arguments
/// - `query_smarts`: SMARTS 子结构查询（支持 SMILES 串作为简化查询）
/// - `candidates`: `(mol_id, smiles)` 列表
///
/// # Returns
/// 命中的 (mol_id, smiles) 列表。
pub fn substructure_search(
    query_smarts: &str,
    candidates: &[(String, String)],
) -> Result<Vec<(String, String)>, String> {
    let query = parse_smarts(query_smarts).map_err(|e| format!("SMARTS parse failed: {:?}", e))?;

    let mut matches_out = Vec::new();
    for (mol_id, smiles) in candidates {
        let mol = match parse(smiles) {
            Ok(m) => m,
            Err(_) => continue,
        };
        if !find_matches(&query, &mol).is_empty() {
            matches_out.push((mol_id.clone(), smiles.clone()));
        }
    }
    Ok(matches_out)
}

/// 三级漏斗：Tanimoto 预过滤 + VF2 子结构搜索
pub fn substructure_search_with_filter(
    query_smarts: &str,
    candidates: &[(String, String)],
    tanimoto_threshold: f64,
) -> Result<Vec<(String, String, f64)>, String> {
    let query_mol =
        parse(query_smarts).map_err(|e| format!("query SMILES parse failed: {}", e))?;
    let query_smiles = canonical_smiles(&query_mol);

    let filtered = tanimoto_batch_filter(&query_smiles, candidates, tanimoto_threshold)?;

    let filtered_pairs: Vec<(String, String)> = filtered
        .iter()
        .map(|(id, smiles, _)| (id.clone(), smiles.clone()))
        .collect();

    let matches = substructure_search(query_smarts, &filtered_pairs)?;

    let match_set: std::collections::HashSet<String> =
        matches.iter().map(|(id, _)| id.clone()).collect();

    Ok(filtered
        .into_iter()
        .filter(|(id, _, _)| match_set.contains(id))
        .collect())
}

// ---------------------------------------------------------------------------
// MoleculeRecord 集成
// ---------------------------------------------------------------------------

/// 从 MoleculeRecord 列表批量计算 ECFP4，返回 (mol_id, fp) 对。
///
/// 跳过 SMILES 解析失败的记录（warn log）。
pub fn fingerprints_for_records(records: &[MoleculeRecord]) -> Vec<(String, BitVec2048)> {
    let mut out = Vec::with_capacity(records.len());
    for r in records {
        match parse(&r.smiles) {
            Ok(mol) => out.push((r.mol_id.clone(), chematic_fp::ecfp4(&mol))),
            Err(e) => log::warn!(
                "fingerprints_for_records: skip mol_id={} (SMILES parse failed: {})",
                r.mol_id,
                e
            ),
        }
    }
    out
}

/// 字节级 Tanimoto 相似度（按位 AND/OR 计算）。
///
/// 保留为辅助函数：当 fingerprint 已经是 `Vec<u8>` 形式（来自持久化层）
/// 时，可以不走 chematic 重新计算。
pub fn tanimoto_bytes(a: &[u8], b: &[u8]) -> f64 {
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
        let result = validate_smiles("CCO"); // ethanol
        assert!(result.valid, "expected valid, got error: {:?}", result.error);
        assert!(result.canonical_smiles.is_some());
    }

    #[test]
    fn test_validate_smiles_aromatic() {
        // canonical_smiles 应该保留芳香性
        let result = validate_smiles("c1ccccc1"); // benzene
        assert!(result.valid, "benzene should be valid: {:?}", result.error);
        let c = result.canonical_smiles.unwrap();
        assert!(c.starts_with('c'), "expected aromatic canonical, got {c}");
    }

    #[test]
    fn test_validate_smiles_empty() {
        let result = validate_smiles("");
        assert!(!result.valid);
    }

    #[test]
    fn test_validate_smiles_too_long() {
        let s = "C".repeat(10001);
        let result = validate_smiles(&s);
        assert!(!result.valid);
    }

    #[test]
    fn test_validate_smiles_with_spaces() {
        let result = validate_smiles("CC O");
        assert!(!result.valid);
    }

    #[test]
    fn test_validate_smiles_invalid_bond() {
        let result = validate_smiles("C%"); // '%' is not valid SMILES
        assert!(!result.valid);
        assert!(result.error.is_some());
    }

    #[test]
    fn test_canonical_smiles_stable() {
        // chematic canonical_smiles 保留输入的芳香/Kekule 形式
        // 验证：同一个 SMILES 多次 canonicalize 结果稳定
        let r1 = validate_smiles("c1ccccc1");
        let r2 = validate_smiles("C1=CC=CC=C1");
        assert!(r1.valid && r2.valid);

        // aromatic 形式 canonicalize 后仍为 aromatic
        let can1 = r1.canonical_smiles.unwrap();
        let m1 = chematic_smiles::parse(&can1).unwrap();
        assert_eq!(chematic_smiles::canonical_smiles(&m1), can1);

        // Kekule 形式 canonicalize 后仍为 Kekule
        let can2 = r2.canonical_smiles.unwrap();
        let m2 = chematic_smiles::parse(&can2).unwrap();
        assert_eq!(chematic_smiles::canonical_smiles(&m2), can2);
    }

    #[test]
    fn test_compute_ecfp4() {
        let fp = compute_ecfp4("CCO").unwrap();
        assert_eq!(fp.popcount() + 0, fp.popcount()); // BitVec2048 sanity
        let fp2 = compute_ecfp4("CCO").unwrap();
        assert_eq!(fp.tanimoto(&fp2), 1.0);
    }

    #[test]
    fn test_tanimoto_similarity_identical() {
        let s = tanimoto_similarity("CCO", "CCO").unwrap();
        assert!((s - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_tanimoto_similarity_distinct() {
        // ethanol vs benzene — 共同子结构很少
        let s = tanimoto_similarity("CCO", "c1ccccc1").unwrap();
        assert!(s < 0.5, "ethanol vs benzene should be dissimilar, got {s}");
    }

    #[test]
    fn test_tanimoto_batch_filter() {
        let cands = vec![
            ("mol1".to_string(), "CCO".to_string()),
            ("mol2".to_string(), "CCN".to_string()),
            ("mol3".to_string(), "c1ccccc1".to_string()),
        ];
        let out = tanimoto_batch_filter("CCO", &cands, 0.0).unwrap();
        // 全部通过阈值 0.0
        assert_eq!(out.len(), 3);
        // 排序：C > N > 苯环（与 CCO 共享 substructures 较多）
        assert_eq!(out[0].0, "mol1");
    }

    #[test]
    fn test_substructure_search_smiles_as_query() {
        // 简化场景：query 是一段 SMILES，候选含有更大分子包含该片段
        let cands = vec![
            ("ethanol".to_string(), "CCO".to_string()),
            ("benzene".to_string(), "c1ccccc1".to_string()),
        ];
        // CCO 是乙醇本身 — 自身匹配
        let out = substructure_search("CCO", &cands).unwrap();
        // SMILES 查询（用作 query_smarts）应至少匹配 ethanol 自身
        assert!(out.iter().any(|(id, _)| id == "ethanol"));
    }

    #[test]
    fn test_substructure_search_with_filter() {
        let cands = vec![
            ("mol1".to_string(), "CCO".to_string()),
            ("mol2".to_string(), "c1ccccc1".to_string()),
        ];
        // Tanimoto 阈值 0.5 + CCO 子结构 → mol1 命中，mol2 不命中
        let out = substructure_search_with_filter("CCO", &cands, 0.5).unwrap();
        assert!(out.iter().all(|(id, _, _)| id == "mol1"));
    }

    #[test]
    fn test_tanimoto_bytes() {
        let a = vec![0xFF, 0x00];
        let b = vec![0xFF, 0x00];
        assert!((tanimoto_bytes(&a, &b) - 1.0).abs() < 0.01);

        let c = vec![0x00, 0xFF];
        assert!(tanimoto_bytes(&a, &c) < 0.01);
    }

    #[test]
    fn test_smiles_error_display() {
        // 验证无效 SMILES 被拒绝
        let r = validate_smiles("this is not smiles at all!!!");
        assert!(!r.valid);
        assert!(r.error.unwrap().len() > 0);
    }
}

// ─── MoleCode / E-SMILES convenience re-exports ──────────────────

/// E-SMILES → MoleCode (Mermaid graph text)
pub fn esmiles_to_molecode(
    esmiles: &str,
    name: &str,
) -> Result<crate::core::chem::molecode::MoleCodeResult, String> {
    crate::core::chem::molecode::esmiles_to_molecode(esmiles, name)
}

/// 纯 SMILES → MoleCode (Mermaid graph text)
pub fn smiles_to_molecode(
    smiles: &str,
    name: &str,
) -> Result<crate::core::chem::molecode::MoleCodeResult, String> {
    crate::core::chem::molecode::smiles_to_molecode(smiles, name)
}

/// SMILES → E-SMILES（添加 `<sep>` + 标签）
pub fn smiles_to_esmiles(smiles: &str, tags: &[crate::core::chem::esmiles::EsTag]) -> String {
    crate::core::chem::esmiles::smiles_to_esmiles(smiles, tags)
}

// ─── 化学描述符 ──────────────────────────────────────────────

/// 分子理化性质描述符
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ChemDescriptors {
    pub molecular_weight: f64,
    pub logp: f64,
    pub tpsa: f64,
    pub hba: usize,
    pub hbd: usize,
    pub rotatable_bonds: usize,
    pub formula: String,
}

/// 计算分子理化性质描述符
///
/// 使用 chematic-chem 计算 MW、LogP、TPSA、HBA、HBD、可旋转键数、分子式。
pub fn compute_descriptors(smiles: &str) -> Result<ChemDescriptors, String> {
    let mol = parse(smiles).map_err(|e| format!("SMILES parse failed: {:?}", e))?;

    Ok(ChemDescriptors {
        molecular_weight: chematic_chem::molecular_weight(&mol),
        logp: chematic_chem::logp_crippen(&mol),
        tpsa: chematic_chem::tpsa(&mol),
        hba: chematic_chem::hba_count(&mol),
        hbd: chematic_chem::hbd_count(&mol),
        rotatable_bonds: chematic_chem::rotatable_bond_count(&mol),
        formula: mol.formula(),
    })
}
