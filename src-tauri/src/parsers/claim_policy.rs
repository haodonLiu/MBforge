//! 专利范围政策匹配检测器
//!
//! 将提取的化合物与专利权利要求进行匹配检测，评估化合物是否落在
//! 专利权利要求的保护范围内。

use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::sync::LazyLock;

use super::claim_parser::{ClaimDependencyGraph, PatentClaim};
use super::molecule_extractor::MoleculeTrace;

/// 从 claim 文本中提取可能的 E-SMILES 候选。
///
/// 策略：
/// 1. 优先搜索 E-SMILES 分隔符 `<sep>`
/// 2. 备选：搜索符合 SMILES 字符集特征的连续子串
static SMILES_CANDIDATE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"[A-Z][a-z]?(?:[()=\[\]0-9@#%+\-*/:;<>?!|&^~$`"']*[A-Z][a-z]?)+"#).expect("valid SMILES candidate regex")
});

fn extract_candidate_esmiles(text: &str) -> Option<String> {
    // 策略 1：搜索 E-SMILES 分隔符 <sep>
    if let Some(pos) = text.find("<sep>") {
        let before = &text[..pos];
        let after = &text[pos + 5..];
        let start = before
            .rfind(|c: char| c.is_whitespace() || c == '.' || c == ';' || c == ',')
            .map(|i| i + 1)
            .unwrap_or(0);
        let end = after
            .find(|c: char| c.is_whitespace() || c == '.' || c == ';' || c == ',')
            .map(|i| pos + 5 + i)
            .unwrap_or(text.len());
        let candidate = text[start..end].trim().to_string();
        if candidate.len() > 5 {
            return Some(candidate);
        }
    }

    // 策略 2：搜索符合 SMILES 字符集的连续子串
    for caps in SMILES_CANDIDATE_RE.captures_iter(text) {
        let candidate = caps.get(0).map(|m| m.as_str()).unwrap_or("");
        if candidate.len() >= 5 && !candidate.contains(' ') {
            let pattern = crate::core::markush::parse_esmiles(candidate);
            if !pattern.r_groups.is_empty() || !pattern.abstract_rings.is_empty() {
                return Some(candidate.to_string());
            }
        }
    }

    None
}

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

/// 匹配类型
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum MatchType {
    /// Claim 文本直接提到化合物名称
    DirectMention,
    /// 化合物落在 Markush 通式范围内（复用 markush.rs）
    MarkushOverlap,
    /// 基于关键词集合的语义匹配
    SemanticMatch,
}

/// 单个 claim ↔ 化合物匹配结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClaimPolicyMatch {
    pub claim_number: u32,
    pub compound_name: String,
    pub match_score: f64,
    pub match_type: MatchType,
    pub details: String,
}

/// 风险等级
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum RiskLevel {
    /// 被独立权利要求覆盖
    High,
    /// 仅被从属权利要求覆盖 / Markush 部分重叠
    Medium,
    /// 无直接覆盖，但语义相关
    Low,
    /// 明确不相关
    Clear,
}

/// 专利范围保护状态评估
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScopeAssessment {
    pub compound_name: String,
    pub esmiles: Option<String>,
    pub covered_claims: Vec<u32>,
    pub independent_claims_covered: Vec<u32>,
    pub risk_level: RiskLevel,
    pub assessment_summary: String,
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// 检查单个化合物与所有权利要求的匹配情况。
///
/// 依次执行三种匹配策略：
/// 1. DirectMention — 化合物名称是否直接出现在 claim 文本中
/// 2. MarkushOverlap — 若化合物有 E-SMILES 且 claim 含 Markush 描述，调用 markush.rs
/// 3. SemanticMatch — 基于技术特征关键词的 Jaccard 相似度
pub fn check_compound_against_claims(
    compound: &MoleculeTrace,
    claims: &ClaimDependencyGraph,
) -> Vec<ClaimPolicyMatch> {
    let mut matches = Vec::new();

    for claim in &claims.claims {
        // 1. Direct Mention
        if let Some(m) = check_direct_mention(compound, claim) {
            matches.push(m);
            continue;
        }

        // 2. Markush Overlap（若化合物有 E-SMILES）
        if compound.vlm_verified_esmiles.is_some() || !compound.molecule.context_text.is_empty() {
            if let Some(m) = check_markush_mention(compound, claim) {
                matches.push(m);
                continue;
            }
        }

        // 3. Semantic Match
        if let Some(m) = check_semantic_match(compound, claim) {
            matches.push(m);
        }
    }

    matches
}

/// 评估化合物在专利中的整体保护范围风险。
///
/// 基于 `check_compound_against_claims` 的结果，综合判断：
/// - 若被任意独立权利要求覆盖 → High
/// - 若仅被从属权利要求覆盖 → Medium
/// - 若只有语义匹配 → Low
/// - 若无任何匹配 → Clear
pub fn assess_patent_scope(
    compound: &MoleculeTrace,
    claims: &ClaimDependencyGraph,
) -> ScopeAssessment {
    let matches = check_compound_against_claims(compound, claims);

    let covered_claims: Vec<u32> = matches.iter().map(|m| m.claim_number).collect();

    let independent_claims_covered: Vec<u32> = matches
        .iter()
        .filter(|m| claims.independent_claims.contains(&m.claim_number))
        .map(|m| m.claim_number)
        .collect();

    let risk_level = if !independent_claims_covered.is_empty() {
        RiskLevel::High
    } else if !covered_claims.is_empty() {
        RiskLevel::Medium
    } else if matches
        .iter()
        .any(|m| m.match_type == MatchType::SemanticMatch)
    {
        RiskLevel::Low
    } else {
        RiskLevel::Clear
    };

    let assessment_summary = build_assessment_summary(compound, claims, &matches, &risk_level);

    ScopeAssessment {
        compound_name: compound.molecule.name.clone(),
        esmiles: compound.vlm_verified_esmiles.clone(),
        covered_claims,
        independent_claims_covered,
        risk_level,
        assessment_summary,
    }
}

/// 批量评估所有化合物。
pub fn assess_all_compounds(
    compounds: &[MoleculeTrace],
    claims: &ClaimDependencyGraph,
) -> Vec<ScopeAssessment> {
    compounds
        .iter()
        .map(|c| assess_patent_scope(c, claims))
        .collect()
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

fn check_direct_mention(compound: &MoleculeTrace, claim: &PatentClaim) -> Option<ClaimPolicyMatch> {
    let name_lower = compound.molecule.name.to_lowercase();
    let claim_lower = claim.raw_text.to_lowercase();

    // 精确匹配化合物名称
    if claim_lower.contains(&name_lower) {
        return Some(ClaimPolicyMatch {
            claim_number: claim.claim_number,
            compound_name: compound.molecule.name.clone(),
            match_score: 1.0,
            match_type: MatchType::DirectMention,
            details: format!(
                "Claim {} 文本直接提到 '{}'",
                claim.claim_number, compound.molecule.name
            ),
        });
    }

    // 匹配编号部分（如 "Compound 1" 可以匹配 "compound 1" 或仅 "1" 在特定上下文中）
    let _num_str = compound.molecule.sequence_num.to_string();
    if claim
        .compounds_mentioned
        .iter()
        .any(|m| m.to_lowercase() == name_lower)
    {
        return Some(ClaimPolicyMatch {
            claim_number: claim.claim_number,
            compound_name: compound.molecule.name.clone(),
            match_score: 0.95,
            match_type: MatchType::DirectMention,
            details: format!(
                "Claim {} 的化合物引用列表中包含 '{}'",
                claim.claim_number, compound.molecule.name
            ),
        });
    }

    None
}

fn check_markush_mention(
    compound: &MoleculeTrace,
    claim: &PatentClaim,
) -> Option<ClaimPolicyMatch> {
    let esmiles = compound.vlm_verified_esmiles.as_ref()?;
    if esmiles.is_empty() {
        return None;
    }

    // 1. 启发式：检测 claim 是否含 Markush 关键词
    let claim_lower = claim.raw_text.to_lowercase();
    let has_markush_keywords = claim_lower.contains("formula")
        || claim_lower.contains("r1")
        || claim_lower.contains("r2")
        || claim_lower.contains("wherein")
        || claim_lower.contains("substituent")
        || claim_lower.contains("selected from");

    if !has_markush_keywords {
        return None;
    }

    // 2. 尝试从 claim 文本中提取可解析的 E-SMILES
    let candidate = match extract_candidate_esmiles(&claim.raw_text) {
        Some(c) => c,
        None => {
            // 无有效 E-SMILES 核心，返回启发式标记
            return Some(ClaimPolicyMatch {
                claim_number: claim.claim_number,
                compound_name: compound.molecule.name.clone(),
                match_score: 0.4,
                match_type: MatchType::MarkushOverlap,
                details: format!(
                    "Claim {} 含 Markush 通式描述但无有效 E-SMILES 核心，化合物 '{}' 无法精确匹配",
                    claim.claim_number, compound.molecule.name
                ),
            });
        }
    };

    // 3. 调用真正的 Markush 子结构匹配
    let overlap =
        crate::core::markush::analyze_markush_coverage(&candidate, esmiles, Some(&claim.raw_text));

    let (score, details) = match overlap.match_level {
        crate::core::markush::MatchLevel::FullOverlap => (
            1.0,
            format!(
                "Claim {} 的 Markush 通式完全覆盖化合物 '{}' (core_overlap: {:.2})",
                claim.claim_number, compound.molecule.name, overlap.core_overlap_ratio
            ),
        ),
        crate::core::markush::MatchLevel::PartialOverlap => (
            0.7,
            format!(
                "Claim {} 的 Markush 通式部分覆盖化合物 '{}' (core_overlap: {:.2})",
                claim.claim_number, compound.molecule.name, overlap.core_overlap_ratio
            ),
        ),
        crate::core::markush::MatchLevel::ScaffoldOverlap => (
            0.5,
            format!(
                "Claim {} 的 Markush 骨架与化合物 '{}' 匹配 (core_overlap: {:.2})",
                claim.claim_number, compound.molecule.name, overlap.core_overlap_ratio
            ),
        ),
        crate::core::markush::MatchLevel::NoOverlap => {
            return Some(ClaimPolicyMatch {
                claim_number: claim.claim_number,
                compound_name: compound.molecule.name.clone(),
                match_score: 0.0,
                match_type: MatchType::MarkushOverlap,
                details: format!(
                    "Claim {} 的 Markush 通式与化合物 '{}' 无子结构重叠",
                    claim.claim_number, compound.molecule.name
                ),
            });
        }
    };

    Some(ClaimPolicyMatch {
        claim_number: claim.claim_number,
        compound_name: compound.molecule.name.clone(),
        match_score: score,
        match_type: MatchType::MarkushOverlap,
        details,
    })
}

fn check_semantic_match(compound: &MoleculeTrace, claim: &PatentClaim) -> Option<ClaimPolicyMatch> {
    let compound_keywords = extract_tech_keywords(&compound.molecule.context_text);
    let claim_keywords = extract_tech_keywords(&claim.raw_text);

    if compound_keywords.is_empty() || claim_keywords.is_empty() {
        return None;
    }

    let score = jaccard_similarity(&compound_keywords, &claim_keywords);

    if score >= 0.15 {
        Some(ClaimPolicyMatch {
            claim_number: claim.claim_number,
            compound_name: compound.molecule.name.clone(),
            match_score: score,
            match_type: MatchType::SemanticMatch,
            details: format!(
                "Claim {} 与化合物 '{}' 的技术特征关键词 Jaccard 相似度为 {:.2}",
                claim.claim_number, compound.molecule.name, score
            ),
        })
    } else {
        None
    }
}

/// 提取技术特征关键词集合。
fn extract_tech_keywords(text: &str) -> HashSet<String> {
    let lower = text.to_lowercase();
    let mut keywords = HashSet::new();

    // 药物化学常见技术关键词
    let tech_terms = [
        "inhibitor",
        "antagonist",
        "agonist",
        "receptor",
        "kinase",
        "enzyme",
        "therapeutic",
        "pharmaceutical",
        "composition",
        "administering",
        "treating",
        "disease",
        "cancer",
        "inflammation",
        "pain",
        "diabetes",
        "halogen",
        "alkyl",
        "aryl",
        "heteroaryl",
        "cycloalkyl",
        "alkoxy",
        "hydroxy",
        "amino",
        "carboxy",
        "nitro",
        "cyano",
        "fluoro",
        "chloro",
        "bromo",
        "methyl",
        "ethyl",
        "propyl",
        "phenyl",
        "pyridyl",
        "thienyl",
        "formula",
        "salt",
        "solvate",
        "prodrug",
        "isomer",
        "stereoisomer",
    ];

    for term in tech_terms {
        if lower.contains(term) {
            keywords.insert(term.to_string());
        }
    }

    keywords
}

fn jaccard_similarity(a: &HashSet<String>, b: &HashSet<String>) -> f64 {
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    let intersection: HashSet<_> = a.intersection(b).collect();
    let union: HashSet<_> = a.union(b).collect();
    intersection.len() as f64 / union.len() as f64
}

fn build_assessment_summary(
    compound: &MoleculeTrace,
    claims: &ClaimDependencyGraph,
    matches: &[ClaimPolicyMatch],
    risk: &RiskLevel,
) -> String {
    let name = &compound.molecule.name;
    match risk {
        RiskLevel::High => {
            let ind_claims: Vec<String> = matches
                .iter()
                .filter(|m| claims.independent_claims.contains(&m.claim_number))
                .map(|m| format!("Claim {} ({:?})", m.claim_number, m.match_type))
                .collect();
            format!(
                "化合物 '{}' 被以下独立权利要求覆盖：{}。风险等级：高。建议进行 FTO 分析。",
                name,
                ind_claims.join(", ")
            )
        }
        RiskLevel::Medium => {
            let dep_claims: Vec<String> = matches
                .iter()
                .filter(|m| !claims.independent_claims.contains(&m.claim_number))
                .map(|m| format!("Claim {}", m.claim_number))
                .collect();
            format!(
                "化合物 '{}' 被以下从属权利要求覆盖：{}。风险等级：中。需确认独立权利要求范围。",
                name,
                dep_claims.join(", ")
            )
        }
        RiskLevel::Low => {
            format!(
                "化合物 '{}' 与专利权利要求有部分语义关联，但无直接覆盖。风险等级：低。",
                name
            )
        }
        RiskLevel::Clear => {
            format!(
                "化合物 '{}' 与当前专利权利要求无明显关联。风险等级：清洁。",
                name
            )
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::super::claim_parser::{ClaimType, PatentClaim};
    use super::super::molecule_extractor::{NameType, NamedMolecule};
    use super::*;

    fn make_molecule(name: &str, seq: u32, context: &str) -> MoleculeTrace {
        MoleculeTrace {
            molecule: NamedMolecule {
                name: name.into(),
                name_type: NameType::Compound,
                sequence_num: seq,
                context_text: context.into(),
                section: "".into(),
                page_hint: None,
                line_start: 0,
                line_end: 0,
                char_pos: 0,
            },
            properties: vec![],
            related_images: vec![],
            vlm_verified_esmiles: None,
            vlm_confidence: 0.0,
        }
    }

    fn make_claim(num: u32, text: &str, claim_type: ClaimType, parents: Vec<u32>) -> PatentClaim {
        PatentClaim {
            claim_number: num,
            claim_type,
            parent_claims: parents,
            raw_text: text.into(),
            normalized_text: text.into(),
            limitations: vec![],
            compounds_mentioned: vec![],
        }
    }

    #[test]
    fn test_direct_mention_found() {
        let mol = make_molecule("Compound 1", 1, "Compound 1 is active.");
        let claim = make_claim(
            1,
            "A pharmaceutical composition comprising Compound 1 and a carrier.",
            ClaimType::Independent,
            vec![],
        );
        let graph = ClaimDependencyGraph {
            claims: vec![claim.clone()],
            independent_claims: vec![1],
            dependents_map: Default::default(),
        };
        let matches = check_compound_against_claims(&mol, &graph);
        assert_eq!(matches.len(), 1);
        assert_eq!(matches[0].match_type, MatchType::DirectMention);
        assert!((matches[0].match_score - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_direct_mention_not_found() {
        let mol = make_molecule("Compound 99", 99, "Compound 99 is active.");
        let claim = make_claim(
            1,
            "A pharmaceutical composition comprising Compound 1 and a carrier.",
            ClaimType::Independent,
            vec![],
        );
        let graph = ClaimDependencyGraph {
            claims: vec![claim],
            independent_claims: vec![1],
            dependents_map: Default::default(),
        };
        let matches = check_compound_against_claims(&mol, &graph);
        assert!(matches.is_empty());
    }

    #[test]
    fn test_semantic_match() {
        let mol = make_molecule(
            "Compound 5",
            5,
            "Compound 5 is a kinase inhibitor for treating cancer.",
        );
        let claim = make_claim(
            1,
            "A method of treating cancer comprising administering a kinase inhibitor.",
            ClaimType::Method,
            vec![],
        );
        let graph = ClaimDependencyGraph {
            claims: vec![claim],
            independent_claims: vec![1],
            dependents_map: Default::default(),
        };
        let matches = check_compound_against_claims(&mol, &graph);
        assert!(!matches.is_empty());
        let semantic = matches
            .iter()
            .find(|m| m.match_type == MatchType::SemanticMatch);
        assert!(semantic.is_some());
        assert!(semantic.unwrap().match_score > 0.15);
    }

    #[test]
    fn test_markush_overlap_heuristic() {
        let mut mol = make_molecule("Compound 1", 1, "Compound 1 has formula I.");
        mol.vlm_verified_esmiles = Some("C1CCCCC1".into());
        let claim = make_claim(
            1,
            "A compound of formula I wherein R1 is selected from halogen and alkyl.",
            ClaimType::Independent,
            vec![],
        );
        let graph = ClaimDependencyGraph {
            claims: vec![claim],
            independent_claims: vec![1],
            dependents_map: Default::default(),
        };
        let matches = check_compound_against_claims(&mol, &graph);
        let markush = matches
            .iter()
            .find(|m| m.match_type == MatchType::MarkushOverlap);
        assert!(markush.is_some());
    }

    #[test]
    fn test_markush_no_esmiles() {
        let mol = make_molecule("Compound 1", 1, "Compound 1 has formula I.");
        // vlm_verified_esmiles is None
        let claim = make_claim(
            1,
            "A compound of formula I wherein R1 is selected from halogen.",
            ClaimType::Independent,
            vec![],
        );
        let graph = ClaimDependencyGraph {
            claims: vec![claim],
            independent_claims: vec![1],
            dependents_map: Default::default(),
        };
        let matches = check_compound_against_claims(&mol, &graph);
        let markush = matches
            .iter()
            .find(|m| m.match_type == MatchType::MarkushOverlap);
        assert!(markush.is_none());
    }

    #[test]
    fn test_assess_patent_scope_high() {
        let mol = make_molecule("Compound 1", 1, "Compound 1 is active.");
        let claim = make_claim(
            1,
            "A composition comprising Compound 1.",
            ClaimType::Independent,
            vec![],
        );
        let graph = ClaimDependencyGraph {
            claims: vec![claim],
            independent_claims: vec![1],
            dependents_map: Default::default(),
        };
        let assessment = assess_patent_scope(&mol, &graph);
        assert_eq!(assessment.risk_level, RiskLevel::High);
        assert_eq!(assessment.covered_claims, vec![1]);
        assert_eq!(assessment.independent_claims_covered, vec![1]);
        assert!(assessment.assessment_summary.contains("高"));
    }

    #[test]
    fn test_assess_patent_scope_clear() {
        let mol = make_molecule("Compound 99", 99, "Compound 99 is unrelated.");
        let claim = make_claim(
            1,
            "A composition comprising Compound 1.",
            ClaimType::Independent,
            vec![],
        );
        let graph = ClaimDependencyGraph {
            claims: vec![claim],
            independent_claims: vec![1],
            dependents_map: Default::default(),
        };
        let assessment = assess_patent_scope(&mol, &graph);
        assert_eq!(assessment.risk_level, RiskLevel::Clear);
        assert!(assessment.covered_claims.is_empty());
    }

    #[test]
    fn test_assess_patent_scope_medium() {
        let mol = make_molecule("Compound 2", 2, "Compound 2 is active.");
        let claim1 = make_claim(
            1,
            "A compound of formula I.",
            ClaimType::Independent,
            vec![],
        );
        let claim2 = make_claim(
            2,
            "The compound of claim 1 wherein R1 is methyl and Compound 2 is included.",
            ClaimType::Dependent,
            vec![1],
        );
        let graph = ClaimDependencyGraph {
            claims: vec![claim1, claim2],
            independent_claims: vec![1],
            dependents_map: {
                let mut m = std::collections::HashMap::new();
                m.insert(1, vec![2]);
                m
            },
        };
        let assessment = assess_patent_scope(&mol, &graph);
        assert_eq!(assessment.risk_level, RiskLevel::Medium);
        assert_eq!(assessment.covered_claims, vec![2]);
    }

    #[test]
    fn test_jaccard_similarity() {
        let a: HashSet<String> = ["a".into(), "b".into(), "c".into()].into();
        let b: HashSet<String> = ["b".into(), "c".into(), "d".into()].into();
        let score = jaccard_similarity(&a, &b);
        assert!((score - 0.5).abs() < 1e-9);
    }

    #[test]
    fn test_jaccard_empty() {
        let a: HashSet<String> = HashSet::new();
        let b: HashSet<String> = ["x".into()].into();
        assert_eq!(jaccard_similarity(&a, &b), 0.0);
    }

    #[test]
    fn test_tech_keywords_extraction() {
        let text = "This kinase inhibitor is useful for treating cancer and inflammation.";
        let kw = extract_tech_keywords(text);
        assert!(kw.contains("inhibitor"));
        assert!(kw.contains("kinase"));
        assert!(kw.contains("treating"));
        assert!(kw.contains("cancer"));
        assert!(kw.contains("inflammation"));
    }

    #[test]
    fn test_assess_all_compounds() {
        let mol1 = make_molecule("Compound 1", 1, "Compound 1 is in claim.");
        let mol2 = make_molecule("Compound 2", 2, "Compound 2 is unrelated.");
        let claim = make_claim(
            1,
            "A composition comprising Compound 1.",
            ClaimType::Independent,
            vec![],
        );
        let graph = ClaimDependencyGraph {
            claims: vec![claim],
            independent_claims: vec![1],
            dependents_map: Default::default(),
        };
        let assessments = assess_all_compounds(&[mol1, mol2], &graph);
        assert_eq!(assessments.len(), 2);
        assert_eq!(assessments[0].risk_level, RiskLevel::High);
        assert_eq!(assessments[1].risk_level, RiskLevel::Clear);
    }
}
