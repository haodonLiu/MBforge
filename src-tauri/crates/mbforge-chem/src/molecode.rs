//! MoleCode 生成：E-SMILES → MoleCode (Mermaid graph text)
//!
//! 将 SMILES/E-SMILES 分子表示转换为 MoleCode 格式——一种以 Mermaid 图语法
//! 序列化的显式图分子表示。每个原子是一个命名节点，每个键是一条显式边。
//!
//! # 格式
//!
//! ```text
//! graph TB
//!     subgraph Name["Name"]
//!         Name_C_1[C]
//!         Name_C_2[CH]
//!         Name_O_1[OH]
//!
//!         Name_C_1 === Name_C_2
//!         Name_C_2 --- Name_O_1
//!     end
//! ```
//!
//! # E-SMILES 兼容
//!
//! E-SMILES 中的 `<a>N:GROUP</a>` 标签映射为 MoleCode 的缩写节点 `{GROUP}`。
//! `<r>` 和 `<c>` 标签作为语义元数据保留，不影响图结构。
//!
//! # 转换流程
//!
//! ```text
//! E-SMILES → parse_esmiles_tags() → (SMILES, tags)
//!   → schematic_smiles::parse(SMILES) → Molecule
//!   → kekulize() → assign_cip()
//!   → 遍历 atoms → node declarations
//!   → 遍历 bonds → edge declarations
//!   → 拼接 Mermaid 文本
//! ```

use std::collections::HashMap;

use chematic_chem::cip::assign_cip;
use chematic_core::atom::CipCode;
use chematic_core::bond::BondOrder;
use chematic_core::{implicit_hcount, kekulize};
use chematic_smiles::parse;

use crate::esmiles::{normalize_wildcards, parse_esmiles_tags, EsTag};

// ─── Bond type mapping ────────────────────────────────────────────

/// chematic BondOrder → Mermaid operator
fn bond_operator(order: &BondOrder) -> &'static str {
    match order {
        BondOrder::Single | BondOrder::Up | BondOrder::Down => "---",
        BondOrder::Double => "===",
        BondOrder::Triple => "-.-",
        BondOrder::Aromatic => "<-->", // fallback, should not appear after kekulize
        _ => "---",
    }
}

// ─── Atom ID / Label generation ───────────────────────────────────

/// Per-element counter for generating unique atom IDs.
struct AtomIdGenerator {
    counters: HashMap<String, usize>,
    prefix: String,
}

impl AtomIdGenerator {
    fn new(prefix: &str) -> Self {
        Self {
            counters: HashMap::new(),
            prefix: sanitize_identifier(prefix),
        }
    }

    /// Generate atom ID: `{prefix}_{Element}_{N}[_R|_S]`
    fn next_id(&mut self, symbol: &str, cip: Option<CipCode>) -> String {
        let count = self.counters.entry(symbol.to_string()).or_insert(0);
        *count += 1;
        let base = format!("{}_{}_{}", self.prefix, symbol, count);

        match cip {
            Some(CipCode::R) => format!("{}_R", base),
            Some(CipCode::S) => format!("{}_S", base),
            _ => base,
        }
    }
}

/// Clean a string to be a valid Mermaid identifier.
fn sanitize_identifier(name: &str) -> String {
    crate::preprocess::sanitize_identifier(name)
}

/// Generate atom display label: `Element[Hcount][(charge)]`
///
/// Examples: `C`, `CH3`, `OH`, `NH2`, `N(+)`, `O(-)`, `NH3(+)`
fn atom_display_label(symbol: &str, h: u8, charge: i8) -> String {
    let mut label = symbol.to_string();

    if h > 0 {
        if h == 1 {
            label.push('H');
        } else {
            label.push_str(&format!("H{}", h));
        }
    }

    if charge != 0 {
        match charge {
            1 => label.push_str("(+)"),
            -1 => label.push_str("(-)"),
            c if c > 0 => label.push_str(&format!("({}+)", c)),
            c => label.push_str(&format!("({}-)", -c)),
        }
    }

    label
}

// ─── Core converter ───────────────────────────────────────────────

/// MoleCode 转换结果
pub struct MoleCodeResult {
    /// Mermaid 图文本
    pub mermaid: String,
    /// 节点数量
    pub atom_count: usize,
    /// 边数量
    pub bond_count: usize,
}

/// 将 E-SMILES 转换为 MoleCode (Mermaid graph text)。
///
/// # 参数
/// - `esmiles`: E-SMILES 字符串（含或不含 `<sep>` 标签）
/// - `name`: 分子名称，用作 subgraph 标题（传空字符串则用 "Molecule"）
///
/// # 返回
/// `MoleCodeResult` 包含 Mermaid 文本和统计信息
///
/// # 示例
///
/// ```ignore
/// let result = esmiles_to_molecode("CCO", "Ethanol");
/// // result.mermaid == "graph TB\n    subgraph Ethanol..."
///
/// let result = esmiles_to_molecode("*c1ccccc1<sep><a>0:R[1]</a>", "Scaffold");
/// // R[1] 节点用 {R[1]} 而非 [C]
/// ```
pub fn esmiles_to_molecode(esmiles: &str, name: &str) -> Result<MoleCodeResult, String> {
    // 1. 分离 SMILES 和标签
    let (smiles_str, tags) = parse_esmiles_tags(esmiles);

    // 2. 解析 SMILES → Molecule（bare * → [*]）
    let normalized = normalize_wildcards(&smiles_str);
    let mol = parse(&normalized).map_err(|e| format!("SMILES parse failed: {:?}", e))?;

    // 3. Kekulize（芳香键 → 单/双键交替）
    let kekule = kekulize(&mol).map_err(|e| format!("Kekulize failed: {}", e))?;

    // 4. CIP 立体化学分配
    let cip = assign_cip(&mol);

    // 5. 构建 atom_idx → EsTag 映射（只有 <a> 标签影响图节点）
    let abbrev_map: HashMap<usize, &str> = tags
        .iter()
        .filter_map(|t| match t {
            EsTag::Atom { index, group } => Some((*index, group.as_str())),
            _ => None,
        })
        .collect();

    // 6. 生成节点和边
    let mol_name = if name.is_empty() { "Molecule" } else { name };
    let mut id_gen = AtomIdGenerator::new(mol_name);

    // atom_idx (usize) → node_id (String)
    let mut node_ids: HashMap<usize, String> = HashMap::new();
    let mut nodes: Vec<(String, String, bool)> = Vec::new(); // (id, label, is_abbrev)

    for (idx, atom) in mol.atoms() {
        let idx_usize = idx.0 as usize;

        if atom.wildcard {
            // Wildcard atom (*): check if it has an abbreviation tag
            if let Some(group) = abbrev_map.get(&idx_usize) {
                let node_id = id_gen.next_id("X", None);
                node_ids.insert(idx_usize, node_id.clone());
                nodes.push((node_id, group.to_string(), true));
            } else {
                // Unnamed wildcard → use "R" as default
                let node_id = id_gen.next_id("X", None);
                node_ids.insert(idx_usize, node_id.clone());
                nodes.push((node_id, "R".to_string(), true));
            }
        } else {
            // Regular atom
            let symbol = atom.element.symbol();
            let cip_code = cip.get(idx);
            let node_id = id_gen.next_id(symbol, cip_code);
            node_ids.insert(idx_usize, node_id.clone());

            let h = implicit_hcount(&mol, idx);
            let label = atom_display_label(symbol, h, atom.charge);
            nodes.push((node_id, label, false));
        }
    }

    // 7. 生成边
    let mut edges: Vec<(String, String, String)> = Vec::new(); // (id1, id2, operator)

    for (bidx, bond) in mol.bonds() {
        let id1 = match node_ids.get(&(bond.atom1.0 as usize)) {
            Some(id) => id.clone(),
            None => continue,
        };
        let id2 = match node_ids.get(&(bond.atom2.0 as usize)) {
            Some(id) => id.clone(),
            None => continue,
        };

        // 从 KekuleResult 获取 kekulized 键序
        let order = match kekule.get(&bidx) {
            Some(o) => *o,
            None => bond.order,
        };

        let base_op = bond_operator(&order);

        // E/Z stereo on double bonds
        let op = if order == BondOrder::Double {
            // Check CIP assignments on the bond's atoms for E/Z
            // In chematic, E/Z is stored as a CipCode on one of the double-bond atoms
            let cip1 = cip.get(bond.atom1);
            let cip2 = cip.get(bond.atom2);
            match (cip1, cip2) {
                (Some(CipCode::E), _) | (_, Some(CipCode::E)) => "===|E|",
                (Some(CipCode::Z), _) | (_, Some(CipCode::Z)) => "===|Z|",
                _ => base_op,
            }
        } else {
            base_op
        };

        edges.push((id1, id2, op.to_string()));
    }

    // 8. 拼接 Mermaid 文本
    let mermaid = build_mermaid(mol_name, &nodes, &edges);

    Ok(MoleCodeResult {
        mermaid,
        atom_count: mol.atom_count(),
        bond_count: edges.len(),
    })
}

/// 便捷函数：纯 SMILES → MoleCode
pub fn smiles_to_molecode(smiles: &str, name: &str) -> Result<MoleCodeResult, String> {
    esmiles_to_molecode(smiles, name)
}

/// 拼接 Mermaid graph 文本
fn build_mermaid(
    name: &str,
    nodes: &[(String, String, bool)],
    edges: &[(String, String, String)],
) -> String {
    let mut lines: Vec<String> = Vec::new();

    let safe_name = sanitize_identifier(name);

    lines.push("graph TB".to_string());
    lines.push(format!("    %% Original molecule name: {}", name));
    lines.push(format!("    subgraph {}[\"{}\"]", safe_name, name));

    // Nodes
    for (id, label, is_abbrev) in nodes {
        if *is_abbrev {
            lines.push(format!("        {}{{{}}}", id, label));
        } else {
            lines.push(format!("        {}[{}]", id, label));
        }
    }

    // Blank separator
    lines.push(String::new());

    // Edges
    for (id1, id2, op) in edges {
        lines.push(format!("        {} {} {}", id1, op, id2));
    }

    lines.push("    end".to_string());

    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ethanol_smiles() {
        let result = esmiles_to_molecode("CCO", "Ethanol").unwrap();
        assert!(result.mermaid.contains("graph TB"));
        assert!(result.mermaid.contains("subgraph Ethanol"));
        // Ethanol: CH3-CH2-OH
        assert!(result.mermaid.contains("[CH3]"));
        assert!(result.mermaid.contains("[CH2]"));
        assert!(result.mermaid.contains("[OH]"));
        assert!(result.atom_count == 3);
        assert!(result.bond_count == 2);
    }

    #[test]
    fn test_benzene_kekulized() {
        let result = esmiles_to_molecode("c1ccccc1", "Benzene").unwrap();
        // Kekulized benzene: alternating === and ---
        assert!(result.mermaid.contains("==="));
        assert!(result.mermaid.contains("---"));
        assert!(result.atom_count == 6);
        assert!(result.bond_count == 6);
    }

    #[test]
    fn test_aspirin() {
        let result = esmiles_to_molecode("CC(=O)Oc1ccccc1C(=O)O", "Aspirin").unwrap();
        assert!(result.atom_count > 10);
        assert!(result.bond_count > 10);
        assert!(result.mermaid.contains("[O]"));
    }

    #[test]
    fn test_acetylene_triple() {
        let result = esmiles_to_molecode("C#C", "Acetylene").unwrap();
        assert!(result.mermaid.contains("-.-"));
        assert!(result.atom_count == 2);
        assert!(result.bond_count == 1);
    }

    #[test]
    fn test_charged_atoms() {
        // Nitromethane: [N+](=O)[O-]
        let result = esmiles_to_molecode("[N+](=O)[O-]", "Nitro").unwrap();
        assert!(result.mermaid.contains("N(+)"));
        assert!(result.mermaid.contains("O(-)"));
    }

    #[test]
    fn test_esmiles_with_abbrev_tag() {
        // *c1ccccc1<sep><a>0:R[1]</a> — wildcard atom becomes {R[1]}
        let result = esmiles_to_molecode("*c1ccccc1<sep><a>0:R[1]</a>", "Scaffold").unwrap();
        assert!(result.mermaid.contains("{R[1]}"));
        // The other 6 atoms should be regular [C]/[CH]
        assert!(result.mermaid.contains("[C]") || result.mermaid.contains("[CH]"));
    }

    #[test]
    fn test_esmiles_multiple_abbrevs() {
        let result =
            esmiles_to_molecode("*c1ccc(*)cc1<sep><a>0:R[1]</a><a>5:R[2]</a>", "Benzene_R")
                .unwrap();
        assert!(result.mermaid.contains("{R[1]}"));
        assert!(result.mermaid.contains("{R[2]}"));
    }

    #[test]
    fn test_plain_smiles_no_tags() {
        let result = esmiles_to_molecode("CCO", "").unwrap();
        // Empty name → "Molecule"
        assert!(result.mermaid.contains("subgraph Molecule"));
    }

    #[test]
    fn test_display_label_formats() {
        assert_eq!(atom_display_label("C", 0, 0), "C");
        assert_eq!(atom_display_label("C", 3, 0), "CH3");
        assert_eq!(atom_display_label("O", 1, 0), "OH");
        assert_eq!(atom_display_label("N", 2, 0), "NH2");
        assert_eq!(atom_display_label("N", 0, 1), "N(+)");
        assert_eq!(atom_display_label("O", 0, -1), "O(-)");
        assert_eq!(atom_display_label("N", 3, 1), "NH3(+)");
        assert_eq!(atom_display_label("O", 0, -2), "O(2-)");
    }

    #[test]
    fn test_sanitize_identifier() {
        assert_eq!(sanitize_identifier("Aspirin"), "Aspirin");
        assert_eq!(sanitize_identifier("(E)-2-Butene"), "E2Butene");
        assert_eq!(sanitize_identifier("123"), "M123");
        assert_eq!(sanitize_identifier(""), "Molecule");
    }
}
