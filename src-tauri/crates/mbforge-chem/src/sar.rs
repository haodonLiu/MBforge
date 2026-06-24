//! SAR (Structure-Activity Relationship) 分析 — 纯 Rust 实现
//!
//! 替代 Python `csar/sar.py`，使用 chematic 的 MCS ring-awareness constraints。
//! 功能：
//! - 共同骨架提取（MCS，支持 ringMatchesRingOnly + completeRingsOnly）
//! - R-group 分解

use std::sync::LazyLock;

use regex::Regex;
use serde::{Deserialize, Serialize};

// ─── 数据类型 ────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RGroupEntry {
    pub position: usize,
    pub label: String,
    pub substituent_smiles: String,
    pub substituent_atoms: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RGroupDecomposition {
    pub compound_id: String,
    pub compound_name: String,
    pub smiles: String,
    pub core_matches: bool,
    pub r_groups: Vec<RGroupEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompoundInput {
    pub id: String,
    pub name: String,
    pub smiles: String,
    #[serde(default)]
    pub activity: Option<f64>,
    #[serde(default)]
    pub activity_type: String,
    #[serde(default)]
    pub units: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScaffoldResult {
    pub scaffold_smarts: String,
    pub atom_count: usize,
    pub bond_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RGroupMatrix {
    pub core_smiles: String,
    pub r_labels: Vec<String>,
    pub rows: Vec<Vec<String>>,
    pub compounds: Vec<serde_json::Value>,
    pub unmatched_count: usize,
}

// ─── 工具函数 ────────────────────────────────────────────────────

static ESMILES_TAG_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"</?[a-zA-Z]>").expect("valid E-SMILES tag regex"));

/// 剥离 E-SMILES 语义标签（<a>, <r>, <c>），保留标签内的内容
fn strip_esmiles_tags(smiles: &str) -> String {
    ESMILES_TAG_RE.replace_all(smiles, "").to_string()
}

/// 解析 SMILES 为 Molecule
fn parse_mol(smiles: &str) -> Option<chematic_core::Molecule> {
    let cleaned = strip_esmiles_tags(smiles);
    chematic_smiles::parse(&cleaned).ok()
}

// ─── 共同骨架提取 ────────────────────────────────────────────────

/// 从一组 SMILES 中找最大公共子结构（MCS）作为共同骨架
pub fn find_common_scaffold(
    smiles_list: &[String],
    timeout_ms: Option<u64>,
    min_atoms: usize,
) -> Option<ScaffoldResult> {
    let mols: Vec<chematic_core::Molecule> =
        smiles_list.iter().filter_map(|s| parse_mol(s)).collect();

    if mols.len() < 2 {
        return None;
    }

    let mol_refs: Vec<&chematic_core::Molecule> = mols.iter().collect();

    let config = chematic_smarts::McsConfig {
        match_bonds: true,
        min_atoms,
        timeout_ms,
        ring_matches_ring_only: true,
        complete_rings_only: true,
    };

    let result = chematic_smarts::find_mcs_with_config(&mol_refs, &config);

    let atom_count = result.atom_count();
    let bond_count = result.bonds.len();

    if atom_count < min_atoms {
        return None;
    }

    // QueryMolecule → SMARTS 字符串
    let smarts = query_to_smarts(&result);

    Some(ScaffoldResult {
        scaffold_smarts: smarts,
        atom_count,
        bond_count,
    })
}

/// QueryMolecule → SMARTS 字符串
fn query_to_smarts(qmol: &chematic_smarts::QueryMolecule) -> String {
    let mut parts = Vec::new();

    for (i, qa) in qmol.atoms.iter().enumerate() {
        let label = match &qa.query {
            chematic_smarts::AtomQuery::Primitive(p) => {
                format!("[{}]", format!("{:?}", p).to_lowercase())
            }
            _ => "[*]".to_string(),
        };
        parts.push(format!("{}:{}", i, label));
    }

    for qb in &qmol.bonds {
        let bond_char = match qb.query {
            chematic_smarts::BondQuery::Primitive(chematic_smarts::BondPrimitive::Single) => "-",
            chematic_smarts::BondQuery::Primitive(chematic_smarts::BondPrimitive::Double) => "=",
            chematic_smarts::BondQuery::Primitive(chematic_smarts::BondPrimitive::Triple) => "#",
            _ => "~",
        };
        parts.push(format!("{}{}{}", qb.atom1, bond_char, qb.atom2));
    }

    parts.join(";")
}

// ─── R-group 分解 ────────────────────────────────────────────────

/// 将单个化合物分解为骨架 + R-group 取代基
pub fn decompose_compound(
    smiles: &str,
    core_smiles: &str,
    compound_id: &str,
    compound_name: &str,
) -> RGroupDecomposition {
    let mut result = RGroupDecomposition {
        compound_id: compound_id.to_string(),
        compound_name: compound_name.to_string(),
        smiles: smiles.to_string(),
        core_matches: false,
        r_groups: Vec::new(),
    };

    let mol = match parse_mol(smiles) {
        Some(m) => m,
        None => return result,
    };

    // 将 core_smiles 解析为 SMARTS 用于匹配
    let core_smi = strip_esmiles_tags(core_smiles);
    let core_qmol = match chematic_smarts::parse_smarts(&core_smi) {
        Ok(q) => q,
        Err(_) => {
            // 如果 SMARTS 解析失败，尝试作为 SMILES 解析后转 QueryMolecule
            match parse_mol(&core_smi) {
                Some(core_mol) => molecule_to_query(&core_mol),
                None => return result,
            }
        }
    };

    // 使用 chematic 的子结构匹配
    let matches = chematic_smarts::find_matches(&core_qmol, &mol);

    if matches.is_empty() {
        return result;
    }

    result.core_matches = true;

    // 获取第一个匹配：HashMap<usize (query atom), AtomIdx (mol atom)>
    let match_map = &matches[0];
    let core_atom_set: std::collections::HashSet<u32> = match_map.values().map(|ai| ai.0).collect();

    // 遍历骨架原子，识别每个位置上的外接基团
    let mut position_substituents: std::collections::HashMap<usize, Vec<u32>> =
        std::collections::HashMap::new();

    for (&query_idx, mol_ai) in match_map.iter() {
        let mol_idx = mol_ai.0;
        let mut external_atoms = Vec::new();
        for (neighbor, _bond) in mol.neighbors(chematic_core::AtomIdx(mol_idx)) {
            let n_idx = neighbor.0;
            if !core_atom_set.contains(&n_idx) {
                external_atoms.push(n_idx);
            }
        }
        if !external_atoms.is_empty() {
            position_substituents.insert(query_idx, external_atoms);
        }
    }

    let mut sorted_positions: Vec<usize> = position_substituents.keys().copied().collect();
    sorted_positions.sort();

    for (r_idx, &core_idx) in sorted_positions.iter().enumerate() {
        if let Some(external_atoms) = position_substituents.get(&core_idx) {
            let atom_count = external_atoms.len();
            let label = format!("R{}", r_idx + 1);
            let substituent_smiles = format!("[R{}]", r_idx + 1);

            result.r_groups.push(RGroupEntry {
                position: core_idx,
                label,
                substituent_smiles,
                substituent_atoms: atom_count,
            });
        }
    }

    result
}

/// Molecule → QueryMolecule（简化转换）
fn molecule_to_query(mol: &chematic_core::Molecule) -> chematic_smarts::QueryMolecule {
    let mut qmol = chematic_smarts::QueryMolecule::new();

    // 原子 → QueryAtom（使用 AtomicNum 匹配）
    for (_ai, atom) in mol.atoms() {
        let atomic_num = atom.element.atomic_number();
        let query = chematic_smarts::AtomQuery::Primitive(
            chematic_smarts::AtomPrimitive::AtomicNum(atomic_num),
        );
        qmol.add_atom(query);
    }

    // 键 → QueryBond
    for (_bi, bond) in mol.bonds() {
        let query = chematic_smarts::BondQuery::Primitive(match bond.order {
            chematic_core::BondOrder::Single => chematic_smarts::BondPrimitive::Single,
            chematic_core::BondOrder::Double => chematic_smarts::BondPrimitive::Double,
            chematic_core::BondOrder::Triple => chematic_smarts::BondPrimitive::Triple,
            _ => chematic_smarts::BondPrimitive::Single,
        });
        qmol.add_bond(bond.atom1.0 as usize, bond.atom2.0 as usize, query);
    }

    qmol
}

// ─── R-group 矩阵 ────────────────────────────────────────────────

/// 构建 R-group 矩阵
pub fn build_rgroup_matrix(
    compounds: &[CompoundInput],
    core_smiles: Option<&str>,
    auto_extract_scaffold: bool,
    timeout_ms: Option<u64>,
) -> RGroupMatrix {
    let smiles_list: Vec<String> = compounds.iter().map(|c| c.smiles.clone()).collect();

    let scaffold = if let Some(cs) = core_smiles {
        Some(cs.to_string())
    } else if auto_extract_scaffold {
        find_common_scaffold(&smiles_list, timeout_ms, 3).map(|s| s.scaffold_smarts)
    } else {
        None
    };

    let core_smiles = match scaffold {
        Some(cs) => cs,
        None => {
            return RGroupMatrix {
                core_smiles: String::new(),
                r_labels: Vec::new(),
                rows: Vec::new(),
                compounds: compounds
                    .iter()
                    .map(|c| serde_json::to_value(c).unwrap_or_default())
                    .collect(),
                unmatched_count: compounds.len(),
            };
        }
    };

    let decompositions: Vec<RGroupDecomposition> = compounds
        .iter()
        .map(|c| decompose_compound(&c.smiles, &core_smiles, &c.id, &c.name))
        .collect();

    let mut all_labels: std::collections::HashSet<String> = std::collections::HashSet::new();
    for d in &decompositions {
        for r in &d.r_groups {
            all_labels.insert(r.label.clone());
        }
    }
    let mut r_labels: Vec<String> = all_labels.into_iter().collect();
    r_labels.sort_by_key(|x| x[1..].parse::<usize>().unwrap_or(0));

    let mut rows = Vec::new();
    let mut matched_meta = Vec::new();
    let mut unmatched_count = 0;

    for (d, c) in decompositions.iter().zip(compounds.iter()) {
        if !d.core_matches {
            rows.push(vec!["—".to_string(); r_labels.len()]);
            let mut meta = serde_json::to_value(c).unwrap_or_default();
            if let Some(obj) = meta.as_object_mut() {
                obj.insert("matches".to_string(), serde_json::json!(false));
            }
            matched_meta.push(meta);
            unmatched_count += 1;
            continue;
        }

        let rmap: std::collections::HashMap<&str, &str> = d
            .r_groups
            .iter()
            .map(|r| (r.label.as_str(), r.substituent_smiles.as_str()))
            .collect();

        let row: Vec<String> = r_labels
            .iter()
            .map(|label| rmap.get(label.as_str()).unwrap_or(&"—").to_string())
            .collect();

        rows.push(row);
        let mut meta = serde_json::to_value(c).unwrap_or_default();
        if let Some(obj) = meta.as_object_mut() {
            obj.insert("matches".to_string(), serde_json::json!(true));
        }
        matched_meta.push(meta);
    }

    RGroupMatrix {
        core_smiles,
        r_labels,
        rows,
        compounds: matched_meta,
        unmatched_count,
    }
}

// ─── 公共 API 包装 ────────────────────────────────────────────────

/// 提取共同骨架（MCS，带 ring constraints）
pub fn sar_find_scaffold(smiles_list: Vec<String>) -> Option<ScaffoldResult> {
    find_common_scaffold(&smiles_list, Some(5000), 3)
}

/// 分解单个化合物为骨架 + R-group
pub fn sar_decompose(smiles: String, core_smiles: String) -> RGroupDecomposition {
    decompose_compound(&smiles, &core_smiles, "", "")
}

/// 构建 R-group 矩阵
pub fn sar_build_matrix(
    compounds: Vec<CompoundInput>,
    core_smiles: Option<String>,
) -> RGroupMatrix {
    build_rgroup_matrix(&compounds, core_smiles.as_deref(), true, Some(5000))
}

// ─── 活性热力图 ──────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeatmapCell {
    pub substituent_smiles: String,
    pub avg_activity: f64,
    pub count: usize,
    pub min: f64,
    pub max: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityHeatmap {
    pub r_label: String,
    pub cells: Vec<HeatmapCell>,
}

/// 基于 R-group 矩阵 + 活性数据构建热力图
pub fn build_activity_heatmap(
    matrix: &RGroupMatrix,
    lower_is_better: bool,
) -> Vec<ActivityHeatmap> {
    let mut heatmaps = Vec::new();

    for (col_idx, r_label) in matrix.r_labels.iter().enumerate() {
        let mut bucket: std::collections::HashMap<String, Vec<f64>> =
            std::collections::HashMap::new();

        for (row_idx, row) in matrix.rows.iter().enumerate() {
            if col_idx >= row.len() {
                continue;
            }
            let sub = &row[col_idx];
            if sub == "—" || sub.is_empty() {
                continue;
            }
            if let Some(compound) = matrix.compounds.get(row_idx) {
                if let Some(activity) = compound.get("activity").and_then(|v| v.as_f64()) {
                    bucket.entry(sub.clone()).or_default().push(activity);
                }
            }
        }

        let mut cells: Vec<HeatmapCell> = bucket
            .into_iter()
            .map(|(sub_smiles, values)| {
                let count = values.len();
                let sum: f64 = values.iter().sum();
                HeatmapCell {
                    substituent_smiles: sub_smiles,
                    avg_activity: sum / count as f64,
                    count,
                    min: values.iter().cloned().fold(f64::INFINITY, f64::min),
                    max: values.iter().cloned().fold(f64::NEG_INFINITY, f64::max),
                }
            })
            .collect();

        cells.sort_by(|a, b| {
            if lower_is_better {
                a.avg_activity
                    .partial_cmp(&b.avg_activity)
                    .unwrap_or(std::cmp::Ordering::Equal)
            } else {
                b.avg_activity
                    .partial_cmp(&a.avg_activity)
                    .unwrap_or(std::cmp::Ordering::Equal)
            }
        });

        heatmaps.push(ActivityHeatmap {
            r_label: r_label.clone(),
            cells,
        });
    }

    heatmaps
}

/// 构建热力图
pub fn sar_heatmap(matrix: RGroupMatrix, lower_is_better: bool) -> Vec<ActivityHeatmap> {
    build_activity_heatmap(&matrix, lower_is_better)
}

// ─── 测试 ────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_find_common_scaffold() {
        let smiles = vec![
            "c1ccc(CC(=O)O)cc1".to_string(),
            "c1ccc(CC(=O)N)cc1".to_string(),
        ];
        let result = find_common_scaffold(&smiles, Some(5000), 3);
        assert!(result.is_some(), "Should find a common scaffold");
        let scaffold = result.unwrap();
        assert!(
            scaffold.atom_count >= 3,
            "Scaffold should have at least 3 atoms"
        );
    }

    #[test]
    fn test_strip_esmiles_tags() {
        assert_eq!(
            strip_esmiles_tags("c1ccc(<c>1:R1</c>)cc1"),
            "c1ccc(1:R1)cc1"
        );
        assert_eq!(strip_esmiles_tags("CCO"), "CCO");
    }

    #[test]
    fn test_decompose_compound() {
        let result =
            decompose_compound("c1ccc(CC(=O)O)cc1", "c1ccccc1", "mol1", "Phenylacetic acid");
        assert!(result.core_matches, "Should match the benzene core");
    }
}
