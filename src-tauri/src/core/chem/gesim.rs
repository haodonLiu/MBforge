#![allow(dead_code)]
//! GESim: graph-based molecular similarity via von Neumann graph entropy
//!
//! Rust-native implementation using `chematic_core::Molecule` as the graph
//! representation.  Reference: Shiokawa et al., J. Cheminf. 2025.
//!
//! Simplifications over the first draft:
//! - Uses `chematic_core::Molecule::{degree, neighbors, atom, bond}` instead
//!   of manually-built adjacency HashMaps.
//! - `BondOrder::order_int()` replaces the custom `bond_weight` match.
//!
//! # Pipeline (matching original C++ implementation)
//! ```text
//! Molecule1 + Molecule2
//!     → ECFP fingerprint generation (path-based, 1024-bit)
//!     → GRAAL alignment (threshold-decreasing greedy matching)
//!     → Merged-degree SI  (matched nodes: avg degree)
//!     → QJS = SI_merge - (SI_1 + SI_2) / 2
//!     → similarity = 1 - QJS  (optionally logistic-scaled)
//! ```

use chematic_core::implicit_hcount;
use chematic_core::molecule::{AtomIdx, Molecule};

// =============================================================================
//  Constants (matching original)
// =============================================================================

const FP_LEN: usize = 1024;
const MAX_RAD: u8 = 4;
const GRAAL_L: usize = 4; // Minimum # of bits for GRAAL matching

// =============================================================================
//  Public API
// =============================================================================

/// Compute raw GESim similarity between two molecules (no scaler).
///
/// Returns `1 - QJS` in `[0.0, 1.0]` where 1.0 means identical structure.
///
/// # Reference
/// Algorithm from `graph_entropy.hpp::comp_QJS()` in the original GESim.
pub fn similarity_raw(mol1: &Molecule, mol2: &Molecule) -> f64 {
    let si1 = comp_si(mol1);
    let si2 = comp_si(mol2);
    let si_merge = align_graphs(mol1, mol2);
    let qjs = si_merge - (si1 + si2) / 2.0;
    (1.0 - qjs).clamp(0.0, 1.0)
}

/// Compute GESim similarity with logistic scaler (matching original Python default).
///
/// Default parameters: `L=1.0, k=7.0, x0=0.4`.
///
/// The logistic scaler adjusts the range so that values are more evenly
/// distributed across `[0, 1]`.  For exact matching (raw ≈ 1.0) or completely
/// dissimilar (raw ≈ 0.0) the scaler is a no-op.
pub fn similarity(mol1: &Molecule, mol2: &Molecule) -> f64 {
    let raw = similarity_raw(mol1, mol2);
    logistic_scaler(raw, 1.0, 7.0, 0.4)
}

/// Return the atom-level match mapping between two molecules.
///
/// Returns `(mapping1, mapping2)` where:
/// - `mapping1[i] = Some(j)` means atom i in mol1 matches atom j in mol2
/// - `mapping1[i] = None` means atom i in mol1 has no match in mol2
///
/// Reference: `graph_entropy.hpp::align_match()` in the original GESim.
pub fn match_mapping(mol1: &Molecule, mol2: &Molecule) -> (Vec<Option<usize>>, Vec<Option<usize>>) {
    let n1 = mol1.atom_count();
    let n2 = mol2.atom_count();

    // Generate ECFP fingerprints
    let fp1: Vec<BitSet1024> = (0..n1)
        .map(|i| generate_ecfp_nid(mol1, AtomIdx(i as u32), MAX_RAD))
        .collect();
    let fp2: Vec<BitSet1024> = (0..n2)
        .map(|i| generate_ecfp_nid(mol2, AtomIdx(i as u32), MAX_RAD))
        .collect();

    // Cost matrix: intersection count
    let mut costs: Vec<f64> = vec![-1.0; n1 * n2];
    for i in 0..n1 {
        for j in 0..n2 {
            let cnt = fp1[i].intersection_count(&fp2[j]);
            costs[n2 * i + j] = cnt as f64;
        }
    }

    // GRAAL alignment
    let mut align1: Vec<Option<usize>> = vec![None; n1];
    let mut align2: Vec<Option<usize>> = vec![None; n2];

    let max_t = (MAX_RAD as usize) + 1;
    for t in (GRAAL_L..=max_t).rev() {
        for i in 0..n1 {
            if align1[i].is_some() {
                continue;
            }
            for j in 0..n2 {
                if align2[j].is_some() {
                    continue;
                }
                if costs[n2 * i + j] >= t as f64 {
                    align1[i] = Some(j);
                    align2[j] = Some(i);
                    break;
                }
            }
        }
    }

    (align1, align2)
}

/// Compute the Structural Information (SI) for a single molecule.
///
/// SI = -Σ (deg_i / vol) * ln(deg_i / vol)
///
/// Uses **natural logarithm** (matching original C++ `log(x)`).
pub fn comp_si(mol: &Molecule) -> f64 {
    let deg = degree_sequence(mol);
    let vol: f64 = deg.iter().sum();
    if vol <= 0.0 {
        return 0.0;
    }
    let mut si = 0.0;
    for d in deg {
        if d > 0.0 {
            let p = d / vol;
            si += p * p.ln();
        }
    }
    -si
}

/// Compute the degree sequence of a molecule.
///
/// Uses `chematic_core::Molecule::degree()` for O(1) per-atom lookup.
pub fn degree_sequence(mol: &Molecule) -> Vec<f64> {
    (0..mol.atom_count())
        .map(|i| mol.degree(AtomIdx(i as u32)) as f64)
        .collect()
}

/// Logistic function scaler matching `gesim.py::logistic_function_scaler()`.
///
/// ```text
/// f(x) = L / (1 + exp(-k * (x - x0)))
/// ```
///
/// For `x <= 0` or `x >= 1` the function is a no-op (returns clamped x).
pub fn logistic_scaler(x: f64, l: f64, k: f64, x0: f64) -> f64 {
    if x <= 0.0 || x >= 1.0 {
        x.clamp(0.0, 1.0)
    } else {
        l / (1.0 + (-k * (x - x0)).exp())
    }
}

// =============================================================================
//  Graph Aligner  —  GRAAL + ECFP fingerprints
// =============================================================================

/// `align_graphs` from original: returns the SI of the merged graph.
///
/// For matched node pairs, merged degree = 0.5 * deg1 + 0.5 * deg2.
/// Unmatched nodes keep their original degree.
fn align_graphs(mol1: &Molecule, mol2: &Molecule) -> f64 {
    let n1 = mol1.atom_count();
    let n2 = mol2.atom_count();

    // Generate ECFP fingerprints for every atom
    let fp1: Vec<BitSet1024> = (0..n1)
        .map(|i| generate_ecfp_nid(mol1, AtomIdx(i as u32), MAX_RAD))
        .collect();
    let fp2: Vec<BitSet1024> = (0..n2)
        .map(|i| generate_ecfp_nid(mol2, AtomIdx(i as u32), MAX_RAD))
        .collect();

    // Cost matrix: intersection count
    let mut costs: Vec<f64> = vec![-1.0; n1 * n2];
    for i in 0..n1 {
        for j in 0..n2 {
            let cnt = fp1[i].intersection_count(&fp2[j]);
            costs[n2 * i + j] = cnt as f64;
        }
    }

    // GRAAL alignment
    let mut align1: Vec<Option<usize>> = vec![None; n1];
    let mut align2: Vec<Option<usize>> = vec![None; n2];

    let max_t = (MAX_RAD as usize) + 1;
    for t in (GRAAL_L..=max_t).rev() {
        for i in 0..n1 {
            if align1[i].is_some() {
                continue;
            }
            for j in 0..n2 {
                if align2[j].is_some() {
                    continue;
                }
                if costs[n2 * i + j] >= t as f64 {
                    align1[i] = Some(j);
                    align2[j] = Some(i);
                    break;
                }
            }
        }
    }

    // Build merged-degree sequence
    let deg1 = degree_sequence(mol1);
    let deg2 = degree_sequence(mol2);

    let mut merged_deg: Vec<f64> = Vec::new();

    for i in 0..n1 {
        let d = if let Some(j) = align1[i] {
            0.5 * deg1[i] + 0.5 * deg2[j]
        } else {
            deg1[i]
        };
        merged_deg.push(d);
    }

    for j in 0..n2 {
        if align2[j].is_none() {
            merged_deg.push(deg2[j]);
        }
    }

    // Compute SI of merged graph
    let vol: f64 = merged_deg.iter().sum();
    if vol <= 0.0 {
        return 0.0;
    }
    let mut si = 0.0;
    for d in merged_deg {
        if d > 0.0 {
            let p = d / vol;
            si += p * p.ln();
        }
    }
    -si
}

// =============================================================================
//  ECFP Fingerprint (path-based, 1024-bit)
// =============================================================================

/// 1024-bit bitset with linear-probing hash table behaviour.
#[derive(Clone, Debug)]
struct BitSet1024 {
    bits: [u64; 16], // 16 * 64 = 1024
}

impl BitSet1024 {
    fn new() -> Self {
        Self { bits: [0; 16] }
    }

    fn set(&mut self, pos: usize) {
        let word = pos / 64;
        let bit = pos % 64;
        self.bits[word] |= 1u64 << bit;
    }

    fn get(&self, pos: usize) -> bool {
        let word = pos / 64;
        let bit = pos % 64;
        (self.bits[word] >> bit) & 1 != 0
    }

    /// Count of set bits (intersection count with another bitset).
    fn intersection_count(&self, other: &Self) -> usize {
        self.bits
            .iter()
            .zip(other.bits.iter())
            .map(|(a, b)| (a & b).count_ones() as usize)
            .sum()
    }
}

/// Generate ECFP fingerprint for a single atom.
///
/// Reference: `graph_entropy.hpp::generate_ecfp_nid()`
///
/// Enumerates all paths up to `max_rad` rooted at `nid`, hashes each path
/// string into one of 1024 bits with linear probing on collision.
fn generate_ecfp_nid(mol: &Molecule, nid: AtomIdx, max_rad: u8) -> BitSet1024 {
    let mut fp = BitSet1024::new();
    for dir in 0..=max_rad {
        let code = generate_path_fp(mol, nid, dir);
        let mut pos = string_hash(&code) % FP_LEN;
        // Linear probing on collision
        loop {
            if !fp.get(pos) {
                fp.set(pos);
                break;
            }
            pos = (pos + 1) % FP_LEN;
        }
    }
    fp
}

/// Generate path-based fingerprint string for atom `nid` with radius `rad`.
///
/// Reference: `graph_entropy.hpp::generate_PATH_FP()`
///
/// Path encoding (BFS, matching original C++):
/// - Layer 0: `"#[label:degree]-(weight)-"`
/// - Layer 1..r: `"[label:degree]-(weight)-"` or `"[label:degree]"` (leaf/max-rad)
///
/// Uses `chematic_core::Molecule::neighbors()` and `mol.bond()` instead of a
/// manually-built adjacency HashMap.
fn generate_path_fp(mol: &Molecule, nid: AtomIdx, max_rad: u8) -> String {
    let mut paths: Vec<String> = Vec::new();
    let mut q: Vec<(AtomIdx, i32)> = vec![(nid, -1)];
    let mut path_prefix = "#";

    for r in 0..=max_rad {
        let size = q.len();
        for _ in 0..size {
            let (node, parent) = q.remove(0);
            let node_degree = mol.degree(node);
            let node_label = node_label_int(mol, node);
            let extended = format!("{}[{}:{}]", path_prefix, node_label, node_degree);

            if r != 0 && node_degree == 1 {
                paths.push(extended);
                continue;
            }

            for (nbr, bid) in mol.neighbors(node) {
                if nbr.0 as i32 == parent {
                    continue;
                }
                let weight = mol.bond(bid).order.order_int();
                let sub = format!("{}-({})-", extended, weight);
                if r == max_rad {
                    paths.push(extended.clone());
                } else {
                    q.push((nbr, node.0 as i32));
                    paths.push(sub);
                }
            }
        }
        path_prefix = "";
    }

    paths.sort();
    paths.concat()
}

/// Simple string hash matching `std::hash<std::string>` behaviour (FNV-1a).
fn string_hash(s: &str) -> usize {
    let mut h: usize = 0xcbf29ce484222325;
    for b in s.bytes() {
        h ^= b as usize;
        h = h.wrapping_mul(0x0100_0000_0000_001b3);
    }
    h
}

// =============================================================================
//  Helpers
// =============================================================================

/// Get a numeric label for an atom (element atomic number + charge encoding).
///
/// The original C++ uses `gdb->node_label(gid, node)` which returns an unsigned int.
/// We approximate this with a hash of (element, charge, h_count).
///
/// Uses `chematic_core::Molecule::atom()` for O(1) lookup.
fn node_label_int(mol: &Molecule, idx: AtomIdx) -> u64 {
    let atom = mol.atom(idx);
    let symbol = atom.element.symbol();
    let charge = atom.charge as i32;
    let h = implicit_hcount(mol, idx);
    // Simple encoding: element hash + charge * 1000 + h
    let mut h_val: u64 = 0;
    for b in symbol.bytes() {
        h_val = h_val.wrapping_mul(31).wrapping_add(b as u64);
    }
    h_val = h_val.wrapping_mul(10000);
    h_val = h_val.wrapping_add((charge + 10) as u64 * 100);
    h_val = h_val.wrapping_add(h as u64);
    h_val
}

// =============================================================================
//  Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use chematic_smiles::parse;

    fn mol_from_smiles(smiles: &str) -> Molecule {
        parse(smiles).expect("valid SMILES")
    }

    #[test]
    fn test_degree_sequence_ethanol() {
        let mol = mol_from_smiles("CCO");
        let deg = degree_sequence(&mol);
        // C(0)-C(1)-O(2)
        assert_eq!(deg, vec![1.0, 2.0, 1.0]);
    }

    #[test]
    fn test_structural_information() {
        // Complete graph K4: 4 nodes, each degree = 3
        // vol = 12, p = 0.25, SI = -4 * 0.25 * ln(0.25) = ln(4) ≈ 1.386
        let deg = vec![3.0, 3.0, 3.0, 3.0];
        let si = comp_si_from_degrees(&deg);
        assert!(
            (si - 1.386294).abs() < 1e-4,
            "SI of K4 should be ~1.386, got {}",
            si
        );
    }

    #[test]
    fn test_similarity_identical() {
        let mol = mol_from_smiles("CCO");
        let sim = similarity(&mol, &mol);
        assert!(
            (sim - 1.0).abs() < 1e-6,
            "identical molecules should have similarity ~1.0, got {}",
            sim
        );
    }

    #[test]
    fn test_similarity_ethanol_vs_methanol() {
        let ethanol = mol_from_smiles("CCO");
        let methanol = mol_from_smiles("CO");
        let sim = similarity(&ethanol, &methanol);
        assert!(sim > 0.0 && sim < 1.0, "expected 0 < sim < 1, got {}", sim);
    }

    #[test]
    fn test_similarity_benzene_vs_cyclohexane() {
        let benzene = mol_from_smiles("c1ccccc1");
        let cyclohexane = mol_from_smiles("C1CCCCC1");
        let sim = similarity(&benzene, &cyclohexane);
        assert!(sim > 0.0 && sim < 1.0, "expected 0 < sim < 1, got {}", sim);
    }

    #[test]
    fn test_fingerprint_generation() {
        let mol = mol_from_smiles("CCO");
        let fp = generate_ecfp_nid(&mol, AtomIdx(0), MAX_RAD);
        // Just verify it doesn't panic and produces something
        assert_eq!(fp.intersection_count(&fp), 5); // r=0..4 → 5 bits set
    }

    #[test]
    fn test_logistic_scaler() {
        // Edge cases: no-op for 0 and 1
        assert!((logistic_scaler(0.0, 1.0, 7.0, 0.4) - 0.0).abs() < 1e-10);
        assert!((logistic_scaler(1.0, 1.0, 7.0, 0.4) - 1.0).abs() < 1e-10);
        // Mid-point check (x = x0 → f(x) = L/2)
        assert!((logistic_scaler(0.4, 1.0, 7.0, 0.4) - 0.5).abs() < 1e-10);
        // Slightly above x0
        let s = logistic_scaler(0.5, 1.0, 7.0, 0.4);
        assert!(s > 0.5 && s < 1.0, "expected 0.5 < s < 1, got {}", s);
    }

    #[test]
    fn test_match_mapping_identical() {
        let mol = mol_from_smiles("CCO");
        let (m1, m2) = match_mapping(&mol, &mol);
        // All 3 atoms should match themselves
        assert_eq!(m1, vec![Some(0), Some(1), Some(2)]);
        assert_eq!(m2, vec![Some(0), Some(1), Some(2)]);
    }

    #[test]
    fn test_match_mapping_benzene_ring() {
        // Two benzene rings — symmetric environment guarantees all radii match.
        let b1 = mol_from_smiles("c1ccccc1");
        let b2 = mol_from_smiles("c1ccccc1");
        let (m1, m2) = match_mapping(&b1, &b2);
        // Every atom should find a match (benzene is perfectly symmetric)
        assert_eq!(m1.iter().filter(|o| o.is_some()).count(), 6);
        assert_eq!(m2.iter().filter(|o| o.is_some()).count(), 6);
        // Consistency: m1[i] = j  ⇒  m2[j] = i
        for (i, mj) in m1.iter().enumerate() {
            if let Some(j) = mj {
                assert_eq!(m2[*j], Some(i));
            }
        }
    }

    fn comp_si_from_degrees(degrees: &[f64]) -> f64 {
        let vol: f64 = degrees.iter().sum();
        if vol <= 0.0 {
            return 0.0;
        }
        degrees
            .iter()
            .map(|d| {
                if *d <= 0.0 {
                    0.0
                } else {
                    let p = d / vol;
                    -p * p.ln()
                }
            })
            .sum()
    }
}
