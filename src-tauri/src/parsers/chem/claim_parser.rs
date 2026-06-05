//! 专利权利要求（Claims）结构化解析器
//!
//! 将专利的 claims section 文本解析为结构化的权利要求依赖图，
//! 支持独立/从属权利要求识别、依赖关系构建、规范化文本生成。

use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::sync::LazyLock;

// ---------------------------------------------------------------------------
// Regex patterns
// ---------------------------------------------------------------------------

/// Claim 编号行 — 支持 "1. ", "1) ", "Claim 1. ", "Claim 1: " 等格式
static CLAIM_NUMBER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^(?:Claim\s*)?(\d+)[\.:\)\-]\s*(.+)$").expect("valid claim number regex"));

/// 备用编号格式（仅数字+点号，更宽松）
static CLAIM_NUMBER_LOOSE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\s*(\d+)[\.\)\-]\s+(.+)$").expect("valid claim loose regex"));

/// 从属引用检测 — "claim 1", "claims 1 and 2", "claim 1 or 2", "claims 1-3"
static DEPENDENCY_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)claim(?:s?)\s+(\d+)(?:\s*(?:and|or|,)\s*(\d+))?(?:\s*(?:and|or|,)\s*(\d+))?")
        .expect("valid dependency regex")
});

/// 范围引用 — "claims 1 to 5", "claims 1-5"
static DEPENDENCY_RANGE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)claims?\s+(\d+)\s*(?:to|-)\s*(\d+)").expect("valid dependency range regex"));

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

/// 权利要求类型
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum ClaimType {
    /// 独立权利要求（无引用其他 claim）
    Independent,
    /// 从属权利要求（引用其他 claim）
    Dependent,
    /// 方法权利要求（含 method, process, use 等关键词）
    Method,
    /// 组合物/化合物权利要求（含 composition, compound, salt, formulation）
    Composition,
}

/// 单个专利权利要求
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatentClaim {
    /// 权利要求编号
    pub claim_number: u32,
    /// 权利要求类型
    pub claim_type: ClaimType,
    /// 引用的父权利要求编号（从属时使用）
    pub parent_claims: Vec<u32>,
    /// 原始文本
    pub raw_text: String,
    /// 规范化后的完整文本（已展开依赖）
    pub normalized_text: String,
    /// 拆分后的技术特征列表
    pub limitations: Vec<String>,
    /// 文中提到的化合物名称
    pub compounds_mentioned: Vec<String>,
}

/// 权利要求依赖图
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClaimDependencyGraph {
    /// 所有权利要求
    pub claims: Vec<PatentClaim>,
    /// 独立权利要求编号列表
    pub independent_claims: Vec<u32>,
    /// 父 → 子 映射
    pub dependents_map: HashMap<u32, Vec<u32>>,
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// 解析专利 claims section 文本，生成结构化的权利要求依赖图。
///
/// # 输入
/// claims section 的纯文本，例如：
/// ```text
/// 1. A compound of formula I ...
/// 2. The compound of claim 1, wherein ...
/// 3. A method of treating ... comprising administering ...
/// ```
///
/// # 输出
/// `ClaimDependencyGraph`，包含每个 claim 的编号、类型、依赖关系、
/// 规范化文本（已递归展开 parent claim 内容）以及技术特征拆分。
pub fn parse_claims_section(claims_text: &str) -> ClaimDependencyGraph {
    let raw_claims = split_raw_claims(claims_text);
    let mut claims: Vec<PatentClaim> = Vec::new();
    let mut dependents_map: HashMap<u32, Vec<u32>> = HashMap::new();

    for (num, text) in raw_claims {
        let parents = extract_parent_claims(&text);
        let claim_type = classify_claim_type(&text, &parents);
        let limitations = split_limitations(&text);
        let compounds = extract_compound_mentions(&text);

        let claim = PatentClaim {
            claim_number: num,
            claim_type,
            parent_claims: parents.clone(),
            raw_text: text.clone(),
            normalized_text: String::new(), // 稍后填充
            limitations,
            compounds_mentioned: compounds,
        };

        claims.push(claim);

        // 构建 parent -> children 映射
        for parent in parents {
            dependents_map.entry(parent).or_default().push(num);
        }
    }

    // 按 claim_number 排序
    claims.sort_by_key(|c| c.claim_number);

    // 生成规范化文本（递归展开依赖）
    let claims_snapshot = claims.clone();
    let mut memo = HashMap::new();
    for claim in claims.iter_mut() {
        let mut visiting = HashSet::new();
        claim.normalized_text =
            build_normalized_text(claim, &claims_snapshot, &mut memo, &mut visiting);
    }

    let independent_claims: Vec<u32> = claims
        .iter()
        .filter(|c| c.claim_type == ClaimType::Independent || c.parent_claims.is_empty())
        .map(|c| c.claim_number)
        .collect();

    ClaimDependencyGraph {
        claims,
        independent_claims,
        dependents_map,
    }
}

/// 生成规范化后的 claims 文本（用于后续专利范围检测）。
///
/// 输出格式：
/// ```text
/// Claim 1 (Independent): [完整文本]
/// Claim 2 (Dependent → 1): [完整文本，已展开 parent]
/// ...
/// ```
pub fn generate_normalized_claims_text(graph: &ClaimDependencyGraph) -> String {
    let mut lines = Vec::new();
    for claim in &graph.claims {
        let type_label = match claim.claim_type {
            ClaimType::Independent => "Independent".to_string(),
            ClaimType::Dependent => format!(
                "Dependent → {}",
                claim
                    .parent_claims
                    .iter()
                    .map(|n| n.to_string())
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            ClaimType::Method => "Method".to_string(),
            ClaimType::Composition => "Composition".to_string(),
        };
        lines.push(format!(
            "Claim {} ({}): {}",
            claim.claim_number, type_label, claim.normalized_text
        ));
    }
    lines.join("\n")
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// 将 claims 文本按编号拆分为 (claim_number, raw_text) 列表。
fn split_raw_claims(text: &str) -> Vec<(u32, String)> {
    let mut result = Vec::new();
    let lines: Vec<&str> = text.lines().collect();
    let mut current_num: Option<u32> = None;
    let mut current_text = String::new();

    for line in lines {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        // 尝试匹配严格格式
        if let Some(caps) = CLAIM_NUMBER_RE.captures(trimmed) {
            // 保存上一个
            if let Some(num) = current_num {
                result.push((num, current_text.trim().to_string()));
            }
            current_num = caps.get(1).and_then(|m| m.as_str().parse::<u32>().ok());
            current_text = caps
                .get(2)
                .map(|m| m.as_str().to_string())
                .unwrap_or_default();
        } else if let Some(caps) = CLAIM_NUMBER_LOOSE_RE.captures(trimmed) {
            // 宽松格式（仅在严格匹配失败时使用，且要求数字递增）
            let num = caps.get(1).and_then(|m| m.as_str().parse::<u32>().ok());
            if let Some(n) = num {
                let expected_next = current_num.map(|c| c + 1).unwrap_or(n);
                if n == expected_next || current_num.is_none() {
                    if let Some(prev) = current_num {
                        result.push((prev, current_text.trim().to_string()));
                    }
                    current_num = Some(n);
                    current_text = caps
                        .get(2)
                        .map(|m| m.as_str().to_string())
                        .unwrap_or_default();
                    continue;
                }
            }
            // 不匹配编号格式，追加到当前文本
            if !current_text.is_empty() {
                current_text.push(' ');
            }
            current_text.push_str(trimmed);
        } else {
            // 不匹配编号格式，追加到当前文本
            if !current_text.is_empty() {
                current_text.push(' ');
            }
            current_text.push_str(trimmed);
        }
    }

    // 保存最后一个
    if let Some(num) = current_num {
        result.push((num, current_text.trim().to_string()));
    }

    result
}

/// 从 claim 文本中提取引用的父 claim 编号。
fn extract_parent_claims(text: &str) -> Vec<u32> {
    let _parents: Vec<u32> = Vec::new();
    let mut seen = HashMap::new();

    // 先尝试范围匹配
    for caps in DEPENDENCY_RANGE_RE.captures_iter(text) {
        let start = caps.get(1).and_then(|m| m.as_str().parse::<u32>().ok()).unwrap_or(0);
        let end = caps.get(2).and_then(|m| m.as_str().parse::<u32>().ok()).unwrap_or(0);
        for n in start..=end {
            seen.entry(n).or_insert(true);
        }
    }

    // 再尝试单个匹配
    for caps in DEPENDENCY_RE.captures_iter(text) {
        for i in 1..=3 {
            if let Some(m) = caps.get(i) {
                if let Ok(n) = m.as_str().parse::<u32>() {
                    seen.entry(n).or_insert(true);
                }
            }
        }
    }

    let mut nums: Vec<u32> = seen.keys().copied().collect();
    nums.sort_unstable();
    nums
}

/// 基于关键词启发式分类权利要求类型。
fn classify_claim_type(text: &str, parents: &[u32]) -> ClaimType {
    let lower = text.to_lowercase();

    // 如果有 parent，统一为 Dependent（从属权利要求）
    // 方法从属可额外检测，但当前枚举不支持组合值
    if !parents.is_empty() {
        if lower.contains("method")
            || lower.contains("process")
            || lower.contains("use")
            || lower.contains("treating")
        {
            return ClaimType::Method;
        }
        return ClaimType::Dependent;
    }

    // 独立权利要求的细分
    if lower.contains("method")
        || lower.contains("process")
        || lower.contains("use")
        || lower.contains("treating")
    {
        return ClaimType::Method;
    }
    if lower.contains("composition")
        || lower.contains("compound")
        || lower.contains("salt")
        || lower.contains("formulation")
    {
        return ClaimType::Composition;
    }

    ClaimType::Independent
}

/// 将 claim 文本拆分为技术特征列表（按逗号、分号、"wherein" 拆分）。
fn split_limitations(text: &str) -> Vec<String> {
    let mut limitations = Vec::new();

    // 先按 "wherein" 拆分
    let parts: Vec<&str> = text.split("wherein").collect();
    if !parts.is_empty() {
        // 第一部分按逗号/分号拆分
        for sub in parts[0].split(|c| c == ',' || c == ';') {
            let trimmed = sub.trim();
            if !trimmed.is_empty() && trimmed.len() > 5 {
                limitations.push(trimmed.to_string());
            }
        }
        // 后续的 wherein 子句
        for &part in parts.iter().skip(1) {
            let trimmed = part.trim().trim_end_matches(|c| c == '.' || c == ';');
            if !trimmed.is_empty() && trimmed.len() > 5 {
                limitations.push(format!("wherein {}", trimmed));
            }
        }
    }

    limitations
}

/// 提取 claim 文本中提到的化合物名称。
fn extract_compound_mentions(text: &str) -> Vec<String> {
    let mut mentions = Vec::new();
    let re = Regex::new(r"(?i)(Compound|Example|Intermediate)\s+(\d+[a-zA-Z]?)").expect("valid compound mention regex");
    for caps in re.captures_iter(text) {
        let full = caps
            .get(0)
            .map(|m| m.as_str().to_string())
            .unwrap_or_default();
        if !mentions.contains(&full) {
            mentions.push(full);
        }
    }
    mentions
}

/// 递归构建规范化文本：将 dependent claim 与 parent claim 文本合并。
///
/// 对于独立权利要求，返回自身文本；对于从属权利要求，
/// 递归拼接所有 parent claim 的规范化文本 + 自身的限定条件。
/// `visiting` 用于检测循环依赖（如 claim 引用自身）。
fn build_normalized_text(
    claim: &PatentClaim,
    all_claims: &[PatentClaim],
    memo: &mut HashMap<u32, String>,
    visiting: &mut HashSet<u32>,
) -> String {
    if let Some(cached) = memo.get(&claim.claim_number) {
        return cached.clone();
    }

    // 检测循环依赖（如 claim 引用自身或形成环）
    if !visiting.insert(claim.claim_number) {
        return claim.raw_text.clone();
    }

    let own_text = claim.raw_text.clone();

    // 独立权利要求：直接返回自身文本
    if claim.parent_claims.is_empty() {
        visiting.remove(&claim.claim_number);
        memo.insert(claim.claim_number, own_text.clone());
        return own_text;
    }

    // 从属权利要求：递归获取 parent claims 的规范化文本
    let mut parent_texts = Vec::new();
    for &parent_num in &claim.parent_claims {
        if parent_num == claim.claim_number {
            continue; // 跳过自引用
        }
        if let Some(parent) = all_claims.iter().find(|c| c.claim_number == parent_num) {
            let parent_norm = build_normalized_text(parent, all_claims, memo, visiting);
            if !parent_norm.is_empty() && !parent_texts.contains(&parent_norm) {
                parent_texts.push(parent_norm);
            }
        }
    }

    visiting.remove(&claim.claim_number);

    let normalized = if parent_texts.is_empty() {
        own_text
    } else {
        format!("{} [附加限定: {}]", parent_texts.join(" + "), own_text)
    };

    memo.insert(claim.claim_number, normalized.clone());
    normalized
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_claims_basic() {
        let text = "1. A compound of formula I.\n2. The compound of claim 1, wherein R1 is methyl.\n3. A method of treating cancer.";
        let graph = parse_claims_section(text);
        assert_eq!(graph.claims.len(), 3);
        assert_eq!(graph.claims[0].claim_number, 1);
        assert_eq!(graph.claims[0].claim_type, ClaimType::Composition);
        assert_eq!(graph.claims[1].claim_number, 2);
        assert_eq!(graph.claims[1].claim_type, ClaimType::Dependent);
        assert_eq!(graph.claims[1].parent_claims, vec![1]);
    }

    #[test]
    fn test_parse_claims_multiline() {
        let text = "1. A compound of formula I\n   wherein R1 is halogen.\n2. The compound of claim 1,\n   wherein R1 is chlorine.";
        let graph = parse_claims_section(text);
        assert_eq!(graph.claims.len(), 2);
        assert!(graph.claims[0].raw_text.contains("wherein R1 is halogen"));
        assert!(graph.claims[1].raw_text.contains("wherein R1 is chlorine"));
    }

    #[test]
    fn test_parse_claims_method() {
        let text = "1. A compound of formula I.\n2. A method of treating a disease, comprising administering the compound of claim 1.";
        let graph = parse_claims_section(text);
        assert_eq!(graph.claims[1].claim_type, ClaimType::Method);
    }

    #[test]
    fn test_parse_claims_composition() {
        let text = "1. A pharmaceutical composition comprising the compound of claim 1 and a pharmaceutically acceptable carrier.";
        let graph = parse_claims_section(text);
        assert_eq!(graph.claims[0].claim_type, ClaimType::Dependent);
        assert_eq!(graph.claims[0].parent_claims, vec![1]);
    }

    #[test]
    fn test_parse_claims_multiple_parents() {
        let text = "1. A compound.\n2. The compound of claim 1.\n3. The compound of claims 1 and 2, wherein X is O.";
        let graph = parse_claims_section(text);
        let claim3 = graph.claims.iter().find(|c| c.claim_number == 3).unwrap();
        assert!(claim3.parent_claims.contains(&1));
        assert!(claim3.parent_claims.contains(&2));
    }

    #[test]
    fn test_parse_claims_dependency_range() {
        let text = "1. A compound.\n2. The compound of claim 1.\n3. The compound of claims 1 to 3.\n4. Another claim.";
        let graph = parse_claims_section(text);
        // claim 3 引用了 1-3（包含自己，这在实际专利中不常见，但测试解析能力）
        let claim3 = graph.claims.iter().find(|c| c.claim_number == 3).unwrap();
        assert!(claim3.parent_claims.contains(&1));
        assert!(claim3.parent_claims.contains(&2));
    }

    #[test]
    fn test_independent_claims_identified() {
        let text =
            "1. A compound.\n2. The compound of claim 1.\n3. A method.\n4. The method of claim 3.";
        let graph = parse_claims_section(text);
        assert_eq!(graph.independent_claims, vec![1, 3]);
    }

    #[test]
    fn test_dependents_map() {
        let text = "1. A compound.\n2. The compound of claim 1.\n3. The compound of claim 1.\n4. The compound of claim 2.";
        let graph = parse_claims_section(text);
        assert_eq!(graph.dependents_map.get(&1).unwrap().len(), 2);
        assert!(graph.dependents_map.get(&1).unwrap().contains(&2));
        assert!(graph.dependents_map.get(&1).unwrap().contains(&3));
        assert_eq!(graph.dependents_map.get(&2).unwrap(), &vec![4]);
    }

    #[test]
    fn test_limitations_split() {
        let text = "1. A compound of formula I, wherein R1 is methyl, and R2 is ethyl.";
        let graph = parse_claims_section(text);
        let claim1 = &graph.claims[0];
        assert!(!claim1.limitations.is_empty());
        let lim_texts: Vec<String> = claim1
            .limitations
            .iter()
            .map(|l| l.to_lowercase())
            .collect();
        assert!(lim_texts.iter().any(|l| l.contains("r1 is methyl")));
        assert!(lim_texts.iter().any(|l| l.contains("r2 is ethyl")));
    }

    #[test]
    fn test_compound_mentions_in_claims() {
        let text = "1. A compound of formula I.\n2. The compound of claim 1, wherein Compound 5 is excluded.";
        let graph = parse_claims_section(text);
        let claim2 = graph.claims.iter().find(|c| c.claim_number == 2).unwrap();
        assert!(claim2
            .compounds_mentioned
            .contains(&"Compound 5".to_string()));
    }

    #[test]
    fn test_generate_normalized_text() {
        let text = "1. A compound.\n2. The compound of claim 1, wherein X=O.";
        let graph = parse_claims_section(text);
        let normalized = generate_normalized_claims_text(&graph);
        assert!(normalized.contains("Claim 1"));
        assert!(normalized.contains("Claim 2"));
        assert!(normalized.contains("Dependent → 1"));
    }

    #[test]
    fn test_claim_number_formats() {
        let text = "Claim 1: A compound.\nClaim 2: The compound of Claim 1.";
        let graph = parse_claims_section(text);
        assert_eq!(graph.claims.len(), 2);
        assert_eq!(graph.claims[0].claim_number, 1);
    }

    #[test]
    fn test_claim_number_parenthesis() {
        let text = "1) A compound.\n2) The compound of 1).";
        let graph = parse_claims_section(text);
        assert_eq!(graph.claims.len(), 2);
    }

    #[test]
    fn test_empty_claims() {
        let text = "";
        let graph = parse_claims_section(text);
        assert!(graph.claims.is_empty());
        assert!(graph.independent_claims.is_empty());
    }

    #[test]
    fn test_claims_with_extra_whitespace() {
        let text = "  1.  A compound.\n\n  2.  The compound of claim 1.\n";
        let graph = parse_claims_section(text);
        assert_eq!(graph.claims.len(), 2);
        assert_eq!(graph.claims[0].raw_text, "A compound.");
    }
}
