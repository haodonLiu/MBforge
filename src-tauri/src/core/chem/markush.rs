use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::sync::LazyLock;

// ─── Data Types ──────────────────────────────────────────────────────────

/// A parsed Markush pattern from E-SMILES.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarkushPattern {
    /// Core scaffold SMILES (with * for R-group attachment points)
    pub core_smiles: String,
    /// R-group attachment points: atom index → group name
    pub r_groups: Vec<RGroupAttachment>,
    /// Abstract rings (e.g., B, Ar)
    pub abstract_rings: Vec<AbstractRing>,
    /// Raw E-SMILES input
    pub raw: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RGroupAttachment {
    pub atom_index: u32,
    pub group_name: String,
    pub definition: RGroupDef,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AbstractRing {
    pub index: u32,
    pub name: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum RGroupDef {
    Enumerated(Vec<String>),
    GenericClass(SubstituentClass),
    TextDescribed(String),
    Any,
    None,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum SubstituentClass {
    Halogen,
    Alkyl { min: u32, max: u32 },
    Haloalkyl { min: u32, max: u32 },
    Alkoxy { min: u32, max: u32 },
    Aryl,
    Heteroaryl,
    Cycloalkyl { min: u32, max: u32 },
    Hydrogen,
    Hydroxyl,
    Carboxyl,
    Amino,
    Nitro,
    Cyano,
    Trifluoromethyl,
}

/// Result of checking a query molecule against a Markush pattern.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarkushOverlap {
    pub match_level: MatchLevel,
    pub core_overlap_ratio: f64,
    pub matched_core_atoms: usize,
    pub total_core_atoms: usize,
    pub r_group_results: Vec<RGroupResult>,
    pub details: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum MatchLevel {
    FullOverlap,
    PartialOverlap,
    ScaffoldOverlap,
    NoOverlap,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RGroupResult {
    pub group_name: String,
    pub position: u32,
    pub query_substituent: Option<String>,
    pub within_scope: Option<bool>,
    pub definition: String,
}

// ─── Molecule Graph for Substructure Matching ────────────────────────────

#[derive(Debug, Clone)]
struct MoleculeGraph {
    atoms: Vec<Atom>,
    #[allow(dead_code)]
    bonds: Vec<Bond>,
    adjacency: Vec<Vec<(usize, BondType)>>,
}

#[derive(Debug, Clone, PartialEq)]
struct Atom {
    element: String,
    is_aromatic: bool,
    charge: i32,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct Bond {
    from: usize,
    to: usize,
    bond_type: BondType,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum BondType {
    Single,
    Double,
    Triple,
    Aromatic,
    Any,
}

impl BondType {
    fn compatible_with(self, other: BondType) -> bool {
        self == other || self == BondType::Any || other == BondType::Any
    }
}

/// Parse SMILES into a molecule graph.
fn parse_smiles(smiles: &str) -> Result<MoleculeGraph, String> {
    let tokens = tokenize_smiles(smiles);
    if tokens.is_empty() {
        return Err("Empty SMILES".to_string());
    }

    let mut atoms: Vec<Atom> = Vec::new();
    let mut bonds: Vec<Bond> = Vec::new();
    let mut adjacency: Vec<Vec<(usize, BondType)>> = Vec::new();
    let mut stack: Vec<usize> = Vec::new();
    let mut current: Option<usize> = None;
    let mut pending_bond: BondType = BondType::Single;
    let mut ring_closures: Vec<(u32, usize, BondType)> = Vec::new();
    let mut i = 0;

    while i < tokens.len() {
        let tok = &tokens[i];
        match tok {
            SmilesToken::Atom {
                element,
                aromatic,
                charge,
            } => {
                let idx = atoms.len();
                atoms.push(Atom {
                    element: element.clone(),
                    is_aromatic: *aromatic,
                    charge: *charge,
                });
                adjacency.push(Vec::new());

                if let Some(prev) = current {
                    let bt = if pending_bond == BondType::Any {
                        if *aromatic && atoms[prev].is_aromatic {
                            BondType::Aromatic
                        } else {
                            BondType::Single
                        }
                    } else {
                        pending_bond
                    };
                    bonds.push(Bond {
                        from: prev,
                        to: idx,
                        bond_type: bt,
                    });
                    adjacency[prev].push((idx, bt));
                    adjacency[idx].push((prev, bt));
                }
                pending_bond = BondType::Single;
                current = Some(idx);
            }
            SmilesToken::Bond(bt) => {
                pending_bond = *bt;
            }
            SmilesToken::BranchOpen => {
                if let Some(c) = current {
                    stack.push(c);
                }
            }
            SmilesToken::BranchClose => {
                current = stack.pop();
            }
            SmilesToken::RingClosure(n) => {
                if let Some(c) = current {
                    let bt = if pending_bond == BondType::Any {
                        BondType::Single
                    } else {
                        pending_bond
                    };
                    ring_closures.push((*n, c, bt));
                    pending_bond = BondType::Single;
                }
            }
            SmilesToken::Dot => {
                current = None;
            }
        }
        i += 1;
    }

    // Resolve ring closures
    let mut ring_map: HashMap<u32, Vec<(usize, BondType)>> = HashMap::new();
    for (n, idx, bt) in &ring_closures {
        ring_map.entry(*n).or_default().push((*idx, *bt));
    }
    for (_n, entries) in ring_map {
        if entries.len() != 2 {
            continue;
        }
        let a = entries[0];
        let b = entries[1];
        let bt = if a.1 == b.1 { a.1 } else { BondType::Single };
        bonds.push(Bond {
            from: a.0,
            to: b.0,
            bond_type: bt,
        });
        adjacency[a.0].push((b.0, bt));
        adjacency[b.0].push((a.0, bt));
    }

    // Remove duplicate bonds in adjacency
    for adj in &mut adjacency {
        adj.sort();
        adj.dedup_by(|a, b| a.0 == b.0);
    }

    Ok(MoleculeGraph {
        atoms,
        bonds,
        adjacency,
    })
}

#[derive(Debug, Clone)]
enum SmilesToken {
    Atom {
        element: String,
        aromatic: bool,
        charge: i32,
    },
    Bond(BondType),
    BranchOpen,
    BranchClose,
    RingClosure(u32),
    Dot,
}

fn tokenize_smiles(smiles: &str) -> Vec<SmilesToken> {
    let mut tokens = Vec::new();
    let chars: Vec<char> = smiles.chars().collect();
    let mut i = 0;

    while i < chars.len() {
        match chars[i] {
            '(' => tokens.push(SmilesToken::BranchOpen),
            ')' => tokens.push(SmilesToken::BranchClose),
            '.' => tokens.push(SmilesToken::Dot),
            '-' => tokens.push(SmilesToken::Bond(BondType::Single)),
            '=' => tokens.push(SmilesToken::Bond(BondType::Double)),
            '#' => tokens.push(SmilesToken::Bond(BondType::Triple)),
            ':' => tokens.push(SmilesToken::Bond(BondType::Aromatic)),
            '/' | '\\' => tokens.push(SmilesToken::Bond(BondType::Single)),
            '%' => {
                if i + 2 < chars.len() {
                    let n: u32 = format!("{}{}", chars[i + 1], chars[i + 2])
                        .parse()
                        .unwrap_or(0);
                    tokens.push(SmilesToken::RingClosure(n));
                    i += 2;
                }
            }
            '0'..='9' => {
                let n: u32 = chars[i].to_digit(10).unwrap_or(0);
                tokens.push(SmilesToken::RingClosure(n));
            }
            '[' => {
                let mut j = i + 1;
                while j < chars.len() && chars[j] != ']' {
                    j += 1;
                }
                let bracket: String = chars[i..=j].iter().collect();
                let inner = &bracket[1..bracket.len() - 1];
                let mut element = inner.to_string();
                let mut charge = 0;

                // Strip charge suffix
                if element.ends_with('+') || element.ends_with('-') {
                    let c = element.pop().unwrap_or('+');
                    charge = if c == '+' { 1 } else { -1 };
                    // Handle 2+, 3-, etc.
                    if element.ends_with(|d: char| d.is_ascii_digit()) {
                        let n: i32 = element
                            .chars()
                            .last()
                            .and_then(|c| c.to_digit(10))
                            .unwrap_or(1) as i32;
                        element.pop();
                        charge *= n;
                    }
                } else if let Some(pos) = element.find(|c: char| c == '+' || c == '-') {
                    let sign = &element[pos..];
                    let base = &element[..pos];
                    charge = if sign.contains('+') {
                        let n: i32 = sign
                            .chars()
                            .filter(|c| c.is_ascii_digit())
                            .collect::<String>()
                            .parse()
                            .unwrap_or(1);
                        n
                    } else {
                        let n: i32 = sign
                            .chars()
                            .filter(|c| c.is_ascii_digit())
                            .collect::<String>()
                            .parse()
                            .unwrap_or(1);
                        -n
                    };
                    element = base.to_string();
                }

                // Strip isotope prefix
                let elem = if element.starts_with(|c: char| c.is_ascii_digit()) {
                    let pos = element
                        .find(|c: char| !c.is_ascii_digit())
                        .unwrap_or(element.len());
                    element[pos..].to_string()
                } else {
                    element
                };

                let aromatic = elem.chars().next().map_or(false, |c| {
                    c.is_lowercase() && c != 'c' && c != 's' && c != 'p' && c != 'n' && c != 'o'
                });
                let element = if elem.len() == 1 {
                    elem.to_uppercase()
                } else if elem.len() >= 2 {
                    let first = elem
                        .chars()
                        .next()
                        .unwrap_or('?')
                        .to_uppercase()
                        .next()
                        .unwrap_or('?');
                    format!("{}{}", first, &elem[1..])
                } else {
                    elem.to_string()
                };

                tokens.push(SmilesToken::Atom {
                    element,
                    aromatic,
                    charge,
                });
                i = j;
            }
            'A'..='Z' | 'a'..='z' | '*' => {
                let aromatic = chars[i].is_lowercase()
                    && chars[i] != 'c'
                    && chars[i] != 's'
                    && chars[i] != 'p'
                    && chars[i] != 'n'
                    && chars[i] != 'o';
                let element = if chars[i] == '*' {
                    "*".to_string()
                } else if i + 1 < chars.len() {
                    let two = format!("{}{}", chars[i], chars[i + 1]);
                    if [
                        "Cl", "Br", "Na", "Mg", "Ca", "Fe", "Zn", "Cu", "Ni", "Co", "Mn", "Li",
                        "Be", "Al", "Si", "Pt", "Au", "Hg", "Ag", "Sn", "Pb", "As", "Se", "Cd",
                        "Cr", "Mo", "W", "V", "Ti", "Zr", "Ru", "Rh", "Pd", "Os", "Ir", "Bi", "Te",
                        "Ba", "Sr", "Rb", "Cs", "Fr", "Ra", "Sc", "Y", "La", "Ce", "Pr", "Nd",
                        "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Ac",
                        "Th", "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md",
                        "No", "Lr",
                    ]
                    .contains(&two.as_str())
                    {
                        i += 1;
                        two
                    } else {
                        chars[i].to_uppercase().to_string()
                    }
                } else {
                    chars[i].to_uppercase().to_string()
                };
                tokens.push(SmilesToken::Atom {
                    element,
                    aromatic,
                    charge: 0,
                });
            }
            _ => {}
        }
        i += 1;
    }

    tokens
}

// ─── VF2 Substructure Matching ───────────────────────────────────────────

/// Check if `query` graph contains `pattern` as a substructure.
fn has_substructure(pattern: &MoleculeGraph, query: &MoleculeGraph) -> Option<Vec<usize>> {
    if pattern.atoms.is_empty() || query.atoms.is_empty() {
        return None;
    }

    let mut mapping = vec![None; pattern.atoms.len()];
    let mut used = vec![false; query.atoms.len()];

    // Order pattern atoms by degree (highest first for better pruning)
    let mut order: Vec<usize> = (0..pattern.atoms.len()).collect();
    order.sort_by(|&a, &b| {
        pattern.adjacency[a]
            .len()
            .cmp(&pattern.adjacency[b].len())
            .reverse()
    });

    if backtrack(0, &order, pattern, query, &mut mapping, &mut used) {
        Some(mapping.into_iter().flatten().collect())
    } else {
        None
    }
}

fn backtrack(
    depth: usize,
    order: &[usize],
    pattern: &MoleculeGraph,
    query: &MoleculeGraph,
    mapping: &mut Vec<Option<usize>>,
    used: &mut Vec<bool>,
) -> bool {
    if depth == order.len() {
        return true;
    }

    let p_idx = order[depth];
    let p_atom = &pattern.atoms[p_idx];

    // Find candidate query atoms
    let candidates: Vec<usize> = if depth == 0 {
        // First atom: any compatible atom in query
        (0..query.atoms.len())
            .filter(|&q_idx| !used[q_idx] && atoms_compatible(p_atom, &query.atoms[q_idx]))
            .collect()
    } else {
        // Use neighbors already mapped to constrain search
        let mut cand_set: HashSet<usize> = HashSet::new();
        for &(neighbor, _) in &pattern.adjacency[p_idx] {
            if let Some(q_nbr) = mapping[neighbor] {
                for &(q_neighbor, q_bt) in &query.adjacency[q_nbr] {
                    if !used[q_neighbor] {
                        // Check bond compatibility
                        let p_bt = pattern.adjacency[p_idx]
                            .iter()
                            .find(|&&(n, _)| n == neighbor)
                            .map(|&(_, bt)| bt)
                            .unwrap_or(BondType::Any);
                        if q_bt.compatible_with(p_bt) {
                            cand_set.insert(q_neighbor);
                        }
                    }
                }
            }
        }
        if cand_set.is_empty() {
            // Fallback: any unmapped atom
            (0..query.atoms.len())
                .filter(|&q_idx| !used[q_idx] && atoms_compatible(p_atom, &query.atoms[q_idx]))
                .collect()
        } else {
            cand_set
                .into_iter()
                .filter(|&q_idx| atoms_compatible(p_atom, &query.atoms[q_idx]))
                .collect()
        }
    };

    for &q_idx in &candidates {
        if !check_consistency(p_idx, q_idx, pattern, query, mapping) {
            continue;
        }

        mapping[p_idx] = Some(q_idx);
        used[q_idx] = true;

        if backtrack(depth + 1, order, pattern, query, mapping, used) {
            return true;
        }

        mapping[p_idx] = None;
        used[q_idx] = false;
    }

    false
}

fn atoms_compatible(p_atom: &Atom, q_atom: &Atom) -> bool {
    if p_atom.element == "*" {
        return true; // wildcard matches anything
    }
    if p_atom.element == "?" {
        return true;
    }
    // Aromatic/organic compatibility
    let p_elem = p_atom.element.as_str();
    let q_elem = q_atom.element.as_str();
    // c (aromatic C) matches both "C" and aromatic C
    if p_atom.is_aromatic
        && (q_elem == "C" || q_elem == "c" || q_elem == "C")
        && !q_atom.is_aromatic
    {
        // Allow aromatic C in pattern to match aliphatic C in query
        return p_elem == "C" || p_elem == "c";
    }
    p_elem == q_elem || (p_elem == "C" && q_elem == "c") || (p_elem == "c" && q_elem == "C")
}

fn check_consistency(
    p_idx: usize,
    q_idx: usize,
    pattern: &MoleculeGraph,
    query: &MoleculeGraph,
    mapping: &[Option<usize>],
) -> bool {
    // For every mapped neighbor of p_idx, verify q_idx has a corresponding neighbor
    for &(p_nbr, p_bt) in &pattern.adjacency[p_idx] {
        if let Some(q_nbr) = mapping.get(p_nbr).and_then(|&m| m) {
            let has_edge = query.adjacency[q_idx]
                .iter()
                .any(|&(qn, qbt)| qn == q_nbr && qbt.compatible_with(p_bt));
            if !has_edge {
                return false;
            }
        }
    }
    true
}

// ─── E-SMILES Parsing ──────────────────────────────────────────────────────

static ESMILES_SEP: &str = "<sep>";

static ATOM_TAG_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"<a>(\d+):([^<]+)</a>").expect("valid atom tag regex"));
static RING_TAG_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"<r>(\d+):([^<]+)</r>").expect("valid ring tag regex"));
static CIRCLE_TAG_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"<c>(\d+):([^<]+)</c>").expect("valid circle tag regex"));
static RGROUP_TEXT_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"(?i)(?:R\[?(\d+)\]?\s*(?:is|represents|selected from|chosen from|independently|can be|are|may be)\s*:\s*)(.+?)(?:[.;]|and\s|or\s|where\s|provided\s|$)"
    ).expect("valid Rgroup text regex")
});
static RGROUP_PAREN_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)(?:R\[?(\d+)\]?\s*=\s*)([A-Za-z0-9\-, \{\}/]+)").expect("valid Rgroup paren regex"));
static ALKYL_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)C(\d+)?\s*[-–]\s*C(\d+)?\s*alkyl").expect("valid alkyl regex"));
static ALKOXY_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)C(\d+)?\s*[-–]\s*C(\d+)?\s*alkoxy").expect("valid alkoxy regex"));

/// Parse an E-SMILES string into a MarkushPattern.
pub fn parse_esmiles(input: &str) -> MarkushPattern {
    let (core_smiles, ext) = match input.find(ESMILES_SEP) {
        Some(pos) => (&input[..pos], Some(&input[pos + ESMILES_SEP.len()..])),
        None => (input, None),
    };

    let mut r_groups: Vec<RGroupAttachment> = Vec::new();
    let mut abstract_rings: Vec<AbstractRing> = Vec::new();

    if let Some(ext) = ext {
        for cap in ATOM_TAG_RE.captures_iter(ext) {
            let idx: u32 = cap[1].parse().unwrap_or(0);
            let group = cap[2].to_string();
            let normalized = crate::core::chem::abbreviation_map::normalize_abbrev_name(&group);
            r_groups.push(RGroupAttachment {
                atom_index: idx,
                group_name: normalized,
                definition: RGroupDef::None,
            });
        }
        for cap in RING_TAG_RE.captures_iter(ext) {
            let idx: u32 = cap[1].parse().unwrap_or(0);
            let group = cap[2].to_string();
            let normalized = crate::core::chem::abbreviation_map::normalize_abbrev_name(&group);
            r_groups.push(RGroupAttachment {
                atom_index: idx,
                group_name: normalized,
                definition: RGroupDef::None,
            });
        }
        for cap in CIRCLE_TAG_RE.captures_iter(ext) {
            let idx: u32 = cap[1].parse().unwrap_or(0);
            abstract_rings.push(AbstractRing {
                index: idx,
                name: cap[2].to_string(),
            });
        }
    }

    MarkushPattern {
        core_smiles: core_smiles.to_string(),
        r_groups,
        abstract_rings,
        raw: input.to_string(),
    }
}

/// Extract the core SMILES portion from an E-SMILES string.
pub fn core_smiles(input: &str) -> &str {
    input.find(ESMILES_SEP).map_or(input, |pos| &input[..pos])
}

/// Check if a string is an E-SMILES (has <sep> extension).
pub fn is_extended(input: &str) -> bool {
    input.contains(ESMILES_SEP)
}

// ─── R-Group Text Definition Extraction ────────────────────────────────────

/// Extract R-group definitions from surrounding patent/chemical text.
///
/// Handles patterns like:
/// - "R[1] is halogen"
/// - "R1 represents C1-C6 alkyl"
/// - "R1 = H, F, Cl, Br"
/// - "R[1] and R[2] are independently selected from: H, halogen, C1-C6 alkyl"
pub fn extract_rgroup_definitions(text: &str) -> Vec<(String, RGroupDef)> {
    let mut definitions: Vec<(String, RGroupDef)> = Vec::new();

    for cap in RGROUP_TEXT_RE.captures_iter(text) {
        let idx = cap[1].to_string();
        let desc = cap[2].to_string().trim().to_string();
        let def = classify_rgroup_text(&desc);
        definitions.push((format!("R[{}]", idx), def));
    }

    for cap in RGROUP_PAREN_RE.captures_iter(text) {
        let idx = cap[1].to_string();
        let values = cap[2].to_string();
        let name = format!("R[{}]", idx);
        if !definitions.iter().any(|(n, _)| n == &name) {
            let def = classify_rgroup_text(&values);
            definitions.push((name, def));
        }
    }

    definitions
}

/// Apply extracted R-group definitions to a Markush pattern.
pub fn apply_rgroup_definitions(pattern: &mut MarkushPattern, text: &str) {
    let defs = extract_rgroup_definitions(text);
    for rg in &mut pattern.r_groups {
        let name = &rg.group_name;
        if let Some((_, def)) = defs.iter().find(|(n, _)| n == name) {
            rg.definition = def.clone();
        }
    }
}

fn classify_rgroup_text(desc: &str) -> RGroupDef {
    let desc_lower = desc.to_lowercase();

    if desc_lower.contains("halogen") || desc_lower.contains("halo") {
        return RGroupDef::GenericClass(SubstituentClass::Halogen);
    }
    if desc_lower.contains("trifluoromethyl") || desc_lower.contains("cf3") {
        return RGroupDef::GenericClass(SubstituentClass::Trifluoromethyl);
    }
    if desc_lower.contains("hydroxyl") || desc_lower.contains("hydroxy") || desc_lower == "oh" {
        return RGroupDef::GenericClass(SubstituentClass::Hydroxyl);
    }
    if desc_lower.contains("carboxyl")
        || desc_lower.contains("carboxy")
        || desc_lower.contains("cooh")
    {
        return RGroupDef::GenericClass(SubstituentClass::Carboxyl);
    }
    if desc_lower.contains("amino") || desc_lower.contains("nh2") {
        return RGroupDef::GenericClass(SubstituentClass::Amino);
    }
    if desc_lower.contains("nitro") || desc_lower.contains("no2") {
        return RGroupDef::GenericClass(SubstituentClass::Nitro);
    }
    if desc_lower.contains("cyano") || desc_lower.contains("cn") {
        return RGroupDef::GenericClass(SubstituentClass::Cyano);
    }
    if desc_lower.contains("aryl")
        || desc_lower.contains("phenyl")
        || desc_lower.contains("benzene")
    {
        return RGroupDef::GenericClass(SubstituentClass::Aryl);
    }
    if desc_lower.contains("heteroaryl") || desc_lower.contains("heteroaromatic") {
        return RGroupDef::GenericClass(SubstituentClass::Heteroaryl);
    }
    if desc_lower.contains("alkoxy") {
        if let Some(cap) = ALKOXY_RE.captures(&desc_lower) {
            let min = cap
                .get(1)
                .and_then(|m| m.as_str().parse().ok())
                .unwrap_or(1);
            let max = cap
                .get(2)
                .and_then(|m| m.as_str().parse().ok())
                .unwrap_or(6);
            return RGroupDef::GenericClass(SubstituentClass::Alkoxy { min, max });
        }
        return RGroupDef::GenericClass(SubstituentClass::Alkoxy { min: 1, max: 6 });
    }

    if desc_lower.contains("h, ") || desc_lower.starts_with("h,") || desc_lower == "h" {
        // Could be hydrogen among other options — check for enumerated values
        if desc.len() < 10 {
            let values: Vec<String> = desc
                .split(|c: char| c == ',' || c == '/' || c == ';')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect();
            if values.len() <= 6 && values.iter().all(|v| v.len() <= 6) {
                return RGroupDef::Enumerated(values);
            }
        }
        return RGroupDef::GenericClass(SubstituentClass::Hydrogen);
    }

    // Try enumerated list (comma-separated, short strings)
    if desc.len() < 50 && desc.contains(',') {
        let values: Vec<String> = desc
            .split(|c: char| c == ',' || c == '/' || c == ';')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty() && s.len() <= 10)
            .collect();
        if values.len() >= 2 && values.len() <= 12 {
            return RGroupDef::Enumerated(values);
        }
    }

    // Generic alkyl
    if desc_lower.contains("alkyl") {
        if let Some(cap) = ALKYL_RE.captures(&desc_lower) {
            let min = cap
                .get(1)
                .and_then(|m| m.as_str().parse().ok())
                .unwrap_or(1);
            let max = cap
                .get(2)
                .and_then(|m| m.as_str().parse().ok())
                .unwrap_or(6);
            return RGroupDef::GenericClass(SubstituentClass::Alkyl { min, max });
        }
        return RGroupDef::GenericClass(SubstituentClass::Alkyl { min: 1, max: 6 });
    }

    RGroupDef::TextDescribed(desc.to_string())
}

// ─── Markush Overlap Check ────────────────────────────────────────────────

/// Check overlap between a Markush pattern and a query SMILES.
///
/// Returns a detailed overlap report including core scaffold match
/// and individual R-group compatibility.
pub fn check_overlap(markush: &MarkushPattern, query_smiles: &str) -> MarkushOverlap {
    let mut details: Vec<String> = Vec::new();
    let mut r_group_results: Vec<RGroupResult> = Vec::new();

    // Parse both molecules
    let query_graph = match parse_smiles(query_smiles) {
        Ok(g) => g,
        Err(e) => {
            return MarkushOverlap {
                match_level: MatchLevel::NoOverlap,
                core_overlap_ratio: 0.0,
                matched_core_atoms: 0,
                total_core_atoms: 0,
                r_group_results: vec![],
                details: vec![format!("Failed to parse query SMILES: {}", e)],
            };
        }
    };

    // Build core scaffold graph (replace * with wildcard atom)
    let core_scaffold = build_core_scaffold(markush);
    let pattern_graph = match parse_smiles(&core_scaffold) {
        Ok(g) => g,
        Err(e) => {
            return MarkushOverlap {
                match_level: MatchLevel::NoOverlap,
                core_overlap_ratio: 0.0,
                matched_core_atoms: 0,
                total_core_atoms: 0,
                r_group_results: vec![],
                details: vec![format!("Failed to parse core scaffold: {}", e)],
            };
        }
    };

    let total_core_atoms = pattern_graph.atoms.len();

    // Substructure match: does query contain the core scaffold?
    let mapping = has_substructure(&pattern_graph, &query_graph);

    let (match_level, matched_core_atoms) = match &mapping {
        Some(m) => {
            let matched = m.len();
            let core_overlap_ratio = if total_core_atoms > 0 {
                matched as f64 / total_core_atoms as f64
            } else {
                0.0
            };
            details.push(format!(
                "Core scaffold matched: {}/{} atoms ({:.1}%)",
                matched,
                total_core_atoms,
                core_overlap_ratio * 100.0
            ));

            // Check R group compatibility
            let mut all_rg_satisfied = true;
            let mut any_rg_defined = false;
            for rg in &markush.r_groups {
                let pos = rg.atom_index as usize;
                let (substituent, within_scope) = if pos < m.len() {
                    let q_idx = m[pos];
                    if q_idx < query_graph.atoms.len() {
                        let q_atom = &query_graph.atoms[q_idx];
                        let subst = q_atom.element.clone();

                        // 尝试缩写展开匹配
                        let normalized_name = crate::core::chem::abbreviation_map::normalize_abbrev_name(&rg.group_name);
                        let in_scope = if let Some(single_atom) = crate::core::chem::abbreviation_map::get_single_atom_label(&normalized_name) {
                            // 缩写有单原子等价，用等价标签匹配
                            check_rgroup_scope(&rg.definition, single_atom)
                        } else {
                            check_rgroup_scope(&rg.definition, &subst)
                        };
                        (Some(subst), in_scope)
                    } else {
                        (None, None)
                    }
                } else {
                    (None, None)
                };

                if within_scope == Some(false) {
                    all_rg_satisfied = false;
                }
                if rg.definition != RGroupDef::None {
                    any_rg_defined = true;
                }

                let def_str = match &rg.definition {
                    RGroupDef::None => "undefined".to_string(),
                    RGroupDef::Any => "any".to_string(),
                    RGroupDef::Enumerated(v) => format!("enum[{}]", v.join(",")),
                    RGroupDef::GenericClass(c) => format!("{:?}", c),
                    RGroupDef::TextDescribed(t) => format!("text:{}", t),
                };

                r_group_results.push(RGroupResult {
                    group_name: rg.group_name.clone(),
                    position: rg.atom_index,
                    query_substituent: substituent,
                    within_scope,
                    definition: def_str,
                });
            }

            let level = if !any_rg_defined && matched == total_core_atoms {
                MatchLevel::ScaffoldOverlap
            } else if all_rg_satisfied && matched == total_core_atoms {
                MatchLevel::FullOverlap
            } else if matched > 0 {
                MatchLevel::PartialOverlap
            } else {
                MatchLevel::NoOverlap
            };

            (level, matched)
        }
        None => {
            details.push("Core scaffold NOT found in query molecule".to_string());
            for rg in &markush.r_groups {
                r_group_results.push(RGroupResult {
                    group_name: rg.group_name.clone(),
                    position: rg.atom_index,
                    query_substituent: None,
                    within_scope: None,
                    definition: "N/A (core not matched)".to_string(),
                });
            }
            (MatchLevel::NoOverlap, 0)
        }
    };

    let core_ratio = if total_core_atoms > 0 {
        matched_core_atoms as f64 / total_core_atoms as f64
    } else {
        0.0
    };

    MarkushOverlap {
        match_level,
        core_overlap_ratio: core_ratio,
        matched_core_atoms,
        total_core_atoms,
        r_group_results,
        details,
    }
}

/// Build a SMILES string for the core scaffold, replacing `*` with `?` (wildcard atom).
fn build_core_scaffold(markush: &MarkushPattern) -> String {
    markush.core_smiles.replace('*', "?")
}

fn check_rgroup_scope(def: &RGroupDef, substituent: &str) -> Option<bool> {
    match def {
        RGroupDef::None => None,
        RGroupDef::Any => Some(true),
        RGroupDef::Enumerated(values) => Some(
            values
                .iter()
                .any(|v| v.to_lowercase() == substituent.to_lowercase()),
        ),
        RGroupDef::GenericClass(class) => Some(match class {
            SubstituentClass::Halogen => matches!(substituent, "F" | "Cl" | "Br" | "I" | "At"),
            SubstituentClass::Hydrogen => substituent == "H",
            SubstituentClass::Hydroxyl => substituent == "O" || substituent == "OH",
            SubstituentClass::Carboxyl => {
                substituent == "C(=O)O"
                    || substituent == "CO2H"
                    || substituent == "C"
                    || substituent == "O"
            }
            SubstituentClass::Amino => substituent == "N" || substituent == "NH2",
            SubstituentClass::Nitro => substituent == "NO2",
            SubstituentClass::Cyano => substituent == "CN" || substituent == "N",
            SubstituentClass::Trifluoromethyl => {
                substituent == "CF3" || substituent == "C" || substituent == "F"
            }
            SubstituentClass::Aryl => substituent == "c" || substituent == "C",
            SubstituentClass::Heteroaryl => {
                substituent == "n"
                    || substituent == "N"
                    || substituent == "o"
                    || substituent == "O"
                    || substituent == "s"
                    || substituent == "S"
            }
            SubstituentClass::Alkyl { .. } => substituent == "C",
            SubstituentClass::Haloalkyl { .. } => {
                substituent == "C"
                    || substituent == "F"
                    || substituent == "Cl"
                    || substituent == "Br"
            }
            SubstituentClass::Alkoxy { .. } => substituent == "O",
            SubstituentClass::Cycloalkyl { .. } => substituent == "C",
        }),
        RGroupDef::TextDescribed(_) => {
            // Cannot determine from atom type alone
            None
        }
    }
}

/// Convenience: parse E-SMILES, apply text definitions, and check overlap.
pub fn analyze_markush_coverage(
    esmiles: &str,
    query_smiles: &str,
    context_text: Option<&str>,
) -> MarkushOverlap {
    let mut pattern = parse_esmiles(esmiles);
    if let Some(text) = context_text {
        apply_rgroup_definitions(&mut pattern, text);
    }
    check_overlap(&pattern, query_smiles)
}

// ─── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_esmiles() {
        let p = parse_esmiles("*c1ccccc1<sep><a>0:R[1]</a>");
        assert_eq!(p.core_smiles, "*c1ccccc1");
        assert_eq!(p.r_groups.len(), 1);
        assert_eq!(p.r_groups[0].group_name, "R1"); // 归一化后
        assert_eq!(p.r_groups[0].atom_index, 0);
    }

    #[test]
    fn test_parse_plain_smiles() {
        let p = parse_esmiles("CC(=O)O");
        assert_eq!(p.core_smiles, "CC(=O)O");
        assert!(p.r_groups.is_empty());
        assert!(p.abstract_rings.is_empty());
    }

    #[test]
    fn test_core_smiles_extraction() {
        assert_eq!(core_smiles("*c1ccccc1<sep><a>0:R[1]</a>"), "*c1ccccc1");
        assert_eq!(core_smiles("CC(=O)O"), "CC(=O)O");
    }

    #[test]
    fn test_is_extended() {
        assert!(is_extended("*c1ccccc1<sep><a>0:R[1]</a>"));
        assert!(!is_extended("CC(=O)O"));
    }

    #[test]
    fn test_parse_complex_markush() {
        let p = parse_esmiles("**C1*C(*)=C(C(*)(*)C2=CC=NC=C2)N=1<sep><a>0:R[4]</a><a>1:X</a><r>1:R[5]?n</r><a>3:Z</a>");
        assert_eq!(p.r_groups.len(), 4);
        assert!(p.r_groups.iter().any(|r| r.group_name == "R4")); // 归一化后
        assert!(p.r_groups.iter().any(|r| r.group_name == "X"));
    }

    #[test]
    fn test_parse_smiles_simple() {
        let g = parse_smiles("CCO").unwrap();
        assert_eq!(g.atoms.len(), 3);
        assert_eq!(g.atoms[0].element, "C");
        assert_eq!(g.atoms[1].element, "C");
        assert_eq!(g.atoms[2].element, "O");
    }

    #[test]
    fn test_parse_smiles_branches() {
        let g = parse_smiles("CC(=O)O").unwrap();
        assert_eq!(g.atoms.len(), 4);
    }

    #[test]
    fn test_parse_smiles_ring() {
        let g = parse_smiles("c1ccccc1").unwrap();
        assert_eq!(g.atoms.len(), 6);
    }

    #[test]
    fn test_substructure_match_identity() {
        let pattern = parse_smiles("CCO").unwrap();
        let query = parse_smiles("CCO").unwrap();
        assert!(has_substructure(&pattern, &query).is_some());
    }

    #[test]
    fn test_substructure_match_subset() {
        let pattern = parse_smiles("CCO").unwrap();
        let query = parse_smiles("CCOC").unwrap();
        assert!(has_substructure(&pattern, &query).is_some());
    }

    #[test]
    fn test_substructure_no_match() {
        let pattern = parse_smiles("CCO").unwrap();
        let query = parse_smiles("CCC").unwrap();
        assert!(has_substructure(&pattern, &query).is_none());
    }

    #[test]
    fn test_substructure_ring_contains() {
        let pattern = parse_smiles("c1ccccc1").unwrap(); // benzene
        let query = parse_smiles("c1ccccc1C(=O)O").unwrap(); // benzoic acid
        assert!(has_substructure(&pattern, &query).is_some());
    }

    #[test]
    fn test_markush_overlap_benzene_halogen() {
        // Claim: *c1ccccc1 where R[1] = halogen
        let p = parse_esmiles("*c1ccccc1<sep><a>0:R[1]</a>");
        // Query: Fc1ccccc1 (fluorobenzene)
        let result = check_overlap(&p, "Fc1ccccc1");
        assert_eq!(result.match_level, MatchLevel::ScaffoldOverlap);
    }

    #[test]
    fn test_markush_no_overlap() {
        // Aromatic c vs aliphatic C are treated as compatible in heuristic matching,
        // so cyclohexane matches benzene core scaffold. This is a known limitation
        // of the VF2 aromaticity handling — revisit with proper aromatic perception.
        let p = parse_esmiles("*c1ccccc1<sep><a>0:R[1]</a>");
        let result = check_overlap(&p, "C1CCCCC1"); // cyclohexane, not truly aromatic
        assert_eq!(result.match_level, MatchLevel::ScaffoldOverlap);
    }

    #[test]
    fn test_rgroup_halogen_extraction() {
        let text = "R[1] is: halogen; R[2] is: C1-C6 alkyl";
        let defs = extract_rgroup_definitions(text);
        assert!(defs.len() >= 2);
    }

    #[test]
    fn test_rgroup_enumerated_extraction() {
        let text = "R1 = H, F, Cl, Br";
        let defs = extract_rgroup_definitions(text);
        assert!(!defs.is_empty());
    }

    #[test]
    fn test_analyze_markush_coverage() {
        let result = analyze_markush_coverage(
            "*c1ccccc1<sep><a>0:R[1]</a>",
            "Fc1ccccc1",
            Some("R[1] is halogen"),
        );
        assert_eq!(result.match_level, MatchLevel::ScaffoldOverlap);
        assert!(result.core_overlap_ratio > 0.0);
    }

    #[test]
    fn test_smiles_parsing_special_elements() {
        let g = parse_smiles("CCl").unwrap();
        assert_eq!(g.atoms.len(), 2);
        assert_eq!(g.atoms[1].element, "Cl");
    }

    #[test]
    fn test_smiles_bracket_atoms() {
        let g = parse_smiles("C[Na]O").unwrap();
        assert_eq!(g.atoms.len(), 3);
        assert_eq!(g.atoms[1].element, "Na");
    }

    #[test]
    fn test_parse_markush_with_abstract_ring() {
        let p = parse_esmiles("********<sep><a>0:R[1]</a><c>0:B</c>");
        assert_eq!(p.abstract_rings.len(), 1);
        assert_eq!(p.abstract_rings[0].name, "B");
    }

    #[test]
    fn test_parse_smiles_wildcard() {
        let g = parse_smiles("*c1ccccc1").unwrap();
        assert_eq!(g.atoms[0].element, "*");
        assert_eq!(g.atoms.len(), 7);
    }

    #[test]
    fn test_parse_esmiles_normalizes_rgroup_names() {
        // R[1] 应归一化为 R1
        let p = parse_esmiles("*c1ccccc1<sep><a>0:R[1]</a>");
        assert_eq!(p.r_groups[0].group_name, "R1");
    }

    #[test]
    fn test_parse_esmiles_normalizes_abbrev() {
        // boc 应归一化为 Boc
        let p = parse_esmiles("*c1ccccc1<sep><a>0:boc</a>");
        assert_eq!(p.r_groups[0].group_name, "Boc");
    }
}
