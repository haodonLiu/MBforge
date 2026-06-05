//! 专利命名化合物序列提取器
//!
//! 核心能力：
//! 1. 从专利文本中优先提取有具体名称且序列连贯的分子（Compound 1, 2, 3…）
//! 2. 为每个分子在邻近窗口中关联活性数据与理化性质
//! 3. 记录分子在文中的精确位置，并关联对应页面图像
//! 4. 调用 VLM 图像识别进行交叉验证，提高分子可溯源性

use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::sync::LazyLock;

use crate::parsers::doc_types::ImageRef;

// ---------------------------------------------------------------------------
// Regex patterns
// ---------------------------------------------------------------------------

static NAMED_MOLECULE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(Compound|Example|Intermediate|Reference)\s+(\d+[a-zA-Z]?)").expect("valid named molecule regex")
});

static ACTIVITY_RE: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    vec![
        // IC50 = 5.2 nM
        Regex::new(r"(?i)(IC50|EC50|EC90|Ki|Kd|IC90)\s*[=:]\s*([<>]?\d+\.?\d*)\s*(nM|µM|uM|μM|mM|pM|%)")
            .expect("valid activity IC50 regex"),
        // Ki of 3.4 nM
        Regex::new(r"(?i)(IC50|EC50|EC90|Ki|Kd|IC90)\s+of\s+([<>]?\d+\.?\d*)\s*(nM|µM|uM|μM|mM|pM|%)")
            .expect("valid activity of regex"),
        // 5.2 nM (IC50)
        Regex::new(r"(?i)([<>]?\d+\.?\d*)\s*(nM|µM|uM|μM|mM|pM|%)\s*\(?\s*(IC50|EC50|EC90|Ki|Kd|IC90)\s*\)?")
            .expect("valid activity paren regex"),
    ]
});

static PHYSICOCHEMICAL_RE: LazyLock<Vec<(String, Regex)>> = LazyLock::new(|| {
    vec![
        (
            "mp".to_string(),
            Regex::new(r"(?i)m\.?p\.?\s*[=:]\s*(\d+\.?\d*)\s*°?\s*C").expect("valid mp regex"),
        ),
        (
            "logP".to_string(),
            Regex::new(r"(?i)log\s*P\s*[=:]\s*([\-]?\d+\.?\d*)").expect("valid logP regex"),
        ),
        (
            "solubility".to_string(),
            Regex::new(r"(?i)solubility\s*[=:]\s*([<>]?\d+\.?\d*)\s*(mg/mL|μg/mL|ug/mL|g/L|mg/L)")
                .expect("valid solubility regex"),
        ),
        (
            "MW".to_string(),
            Regex::new(r"(?i)M\.?W\.?\s*[=:]\s*(\d+\.?\d*)\s*(Da|g/mol)?").expect("valid MW regex"),
        ),
    ]
});

static PAGE_HINT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)\[?page\s*(\d+)\]?|\[?p\.?\s*(\d+)\]?").expect("valid page hint regex"));

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

/// 命名化合物类型
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum NameType {
    Compound,
    Example,
    Intermediate,
    Reference,
}

impl NameType {
    fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "example" => NameType::Example,
            "intermediate" => NameType::Intermediate,
            "reference" => NameType::Reference,
            _ => NameType::Compound,
        }
    }
}

/// 从专利文本中提取的命名化合物
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NamedMolecule {
    pub name: String,
    pub name_type: NameType,
    pub sequence_num: u32,
    pub context_text: String,
    pub section: String,
    pub page_hint: Option<usize>,
    pub line_start: usize,
    pub line_end: usize,
    pub char_pos: usize,
}

/// 理化性质条目
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PhysicochemicalProperty {
    pub property_type: String,
    pub value: f64,
    pub unit: String,
    pub source_quote: String,
    pub confidence: String,
}

/// 带完整溯源信息的分子
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MoleculeTrace {
    pub molecule: NamedMolecule,
    pub properties: Vec<PhysicochemicalProperty>,
    pub related_images: Vec<ImageRef>,
    pub vlm_verified_esmiles: Option<String>,
    pub vlm_confidence: f64,
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// 从文本中提取命名化合物序列，按序列连贯性排序。
///
/// 优先返回有具体名称且编号连贯的分子组（如 Compound 1, 2, 3）。
/// 提取时会记录每个分子在原文中的段落上下文和行号范围。
pub fn extract_named_molecule_series(text: &str) -> Vec<NamedMolecule> {
    let lines: Vec<&str> = text.lines().collect();
    let mut molecules: Vec<NamedMolecule> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();

    for (line_idx, line) in lines.iter().enumerate() {
        for cap in NAMED_MOLECULE_RE.captures_iter(line) {
            let type_str = cap.get(1).map(|m| m.as_str()).unwrap_or("Compound");
            let num_str = cap.get(2).map(|m| m.as_str()).unwrap_or("0");
            let full_name = format!("{} {}", type_str, num_str);

            if seen.contains(&full_name) {
                continue;
            }
            seen.insert(full_name.clone());

            let seq_num = parse_sequence_num(num_str);
            let name_type = NameType::from_str(type_str);

            // 提取上下文：当前行 ±2 行
            let ctx_start = line_idx.saturating_sub(2);
            let ctx_end = (line_idx + 3).min(lines.len());
            let context_text = lines[ctx_start..ctx_end].join("\n");

            // 页码推测：在上下文中搜索 page N 或 p.N
            let page_hint = extract_page_hint(&context_text);

            // 字符位置（基于全文）
            let char_pos = lines[..line_idx].iter().map(|l| l.len() + 1).sum::<usize>();

            molecules.push(NamedMolecule {
                name: full_name,
                name_type,
                sequence_num: seq_num,
                context_text,
                section: String::new(),
                page_hint,
                line_start: line_idx,
                line_end: line_idx,
                char_pos,
            });
        }
    }

    // 按序列连贯性排序：连贯的序列排在前面
    // 预先计算分数避免闭包内同时借用可变和不可变引用
    let scores: std::collections::HashMap<String, usize> = molecules
        .iter()
        .map(|m| (m.name.clone(), sequence_coherence_score(&molecules, m)))
        .collect();

    molecules.sort_by(|a, b| {
        let a_score = scores.get(&a.name).copied().unwrap_or(0);
        let b_score = scores.get(&b.name).copied().unwrap_or(0);
        b_score
            .cmp(&a_score)
            .then_with(|| a.sequence_num.cmp(&b.sequence_num))
    });

    molecules
}

/// 为单个命名化合物在邻近文本窗口中提取理化性质与活性数据。
///
/// `window_size` 为从化合物名称位置向两侧扩展的字符数。
pub fn extract_properties_for_molecule(
    mol: &NamedMolecule,
    full_text: &str,
    window_size: usize,
) -> Vec<PhysicochemicalProperty> {
    let mut props = Vec::new();
    let mut seen = HashSet::new();

    // 截取窗口文本
    let center = mol.char_pos.min(full_text.len());
    let win_start = center.saturating_sub(window_size);
    let win_end = (center + window_size).min(full_text.len());
    let window_text = &full_text[win_start..win_end];

    // 1. 活性数据（复用类似 association.rs 的模式）
    for pattern in ACTIVITY_RE.iter() {
        for caps in pattern.captures_iter(window_text) {
            let g0 = caps.get(1).map(|m| m.as_str()).unwrap_or("");
            let g1 = caps.get(2).map(|m| m.as_str()).unwrap_or("");
            let g2 = caps.get(3).map(|m| m.as_str()).unwrap_or("");

            let (prop_type, val_str, unit) = if looks_like_activity_type(g0) {
                (g0, g1, g2)
            } else if looks_like_activity_type(g2) {
                (g2, g0, g1)
            } else {
                continue;
            };

            let value = match parse_prop_value(val_str) {
                Some(v) => v,
                None => continue,
            };
            let unit = normalize_unit(unit);
            let key = format!("{}|{}|{}", prop_type.to_uppercase(), value, unit);
            if !seen.insert(key) {
                continue;
            }

            let source_quote = caps
                .get(0)
                .map(|m| m.as_str().to_string())
                .unwrap_or_default();
            props.push(PhysicochemicalProperty {
                property_type: prop_type.to_uppercase(),
                value,
                unit,
                source_quote,
                confidence: "high".into(),
            });
        }
    }

    // 2. 理化性质
    for (prop_type, pattern) in PHYSICOCHEMICAL_RE.iter() {
        for caps in pattern.captures_iter(window_text) {
            let val_str = caps.get(1).map(|m| m.as_str()).unwrap_or("");
            let unit = caps.get(2).map(|m| m.as_str()).unwrap_or("");
            let value = match parse_prop_value(val_str) {
                Some(v) => v,
                None => continue,
            };
            let key = format!("{}|{}|{}", prop_type, value, unit);
            if !seen.insert(key) {
                continue;
            }
            let source_quote = caps
                .get(0)
                .map(|m| m.as_str().to_string())
                .unwrap_or_default();
            props.push(PhysicochemicalProperty {
                property_type: prop_type.clone(),
                value,
                unit: unit.to_string(),
                source_quote,
                confidence: "high".into(),
            });
        }
    }

    props
}

/// 将命名化合物与页面图像关联，生成带完整溯源的 MoleculeTrace。
///
/// 关联规则：
/// - 若分子有 `page_hint`，匹配同页图像
/// - 若无页码，匹配图像文件名中包含分子名称或编号的图像
/// - 对关联的图像调用 VLM 识别（异步，但本函数为同步组装，VLM 调用由调用方执行）
pub fn link_molecules_to_images(
    molecules: &[NamedMolecule],
    images: &[ImageRef],
    _page_text_mapping: &[(usize, String)],
) -> Vec<MoleculeTrace> {
    molecules
        .iter()
        .map(|mol| {
            let related_images = find_related_images(mol, images);
            MoleculeTrace {
                molecule: mol.clone(),
                properties: Vec::new(),
                related_images,
                vlm_verified_esmiles: None,
                vlm_confidence: 0.0,
            }
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

fn parse_sequence_num(s: &str) -> u32 {
    s.chars()
        .take_while(|c| c.is_ascii_digit())
        .collect::<String>()
        .parse::<u32>()
        .unwrap_or(0)
}

fn extract_page_hint(text: &str) -> Option<usize> {
    for caps in PAGE_HINT_RE.captures_iter(text) {
        let num = caps
            .get(1)
            .or_else(|| caps.get(2))
            .map(|m| m.as_str().parse::<usize>().ok())
            .flatten();
        if num.is_some() {
            return num;
        }
    }
    None
}

/// 计算一个分子在其同类序列中的连贯性分数。
/// 同类（如都是 Compound）且编号连续的分子获得更高分数。
fn sequence_coherence_score(all: &[NamedMolecule], target: &NamedMolecule) -> usize {
    let same_type: Vec<u32> = all
        .iter()
        .filter(|m| m.name_type == target.name_type)
        .map(|m| m.sequence_num)
        .collect();

    if same_type.is_empty() {
        return 0;
    }

    let min_num = *same_type.iter().min().unwrap_or(&0);
    let max_num = *same_type.iter().max().unwrap_or(&0);
    let span = max_num.saturating_sub(min_num) + 1;
    let unique_count = same_type.iter().collect::<HashSet<_>>().len();

    // 连贯性 = 唯一编号数 / 跨度，越接近 1 越连贯
    if span == 0 {
        return 0;
    }
    let coherence = (unique_count * 100) / span as usize;

    coherence
}

fn looks_like_activity_type(s: &str) -> bool {
    matches!(
        s.to_uppercase().as_str(),
        "IC50" | "EC50" | "EC90" | "KI" | "KD" | "IC90"
    )
}

fn parse_prop_value(s: &str) -> Option<f64> {
    let cleaned = s.trim_start_matches(|c: char| c == '<' || c == '>').trim();
    cleaned.parse::<f64>().ok()
}

fn normalize_unit(unit: &str) -> String {
    match unit.to_lowercase().as_str() {
        "um" | "μm" => "µM",
        "nm" => "nM",
        "mm" => "mM",
        "pm" => "pM",
        "%" => "%",
        _ => unit,
    }
    .to_string()
}

fn find_related_images(mol: &NamedMolecule, images: &[ImageRef]) -> Vec<ImageRef> {
    let mut related = Vec::new();
    let lowercase_name = mol.name.to_lowercase();
    let num_only = mol.sequence_num.to_string();

    for img in images {
        // 规则 1：页码匹配
        if let Some(page) = mol.page_hint {
            if img.page == page {
                related.push(img.clone());
                continue;
            }
        }

        // 规则 2：文件名包含化合物名称或特定前缀+编号
        let filename_lower = img.filename.to_lowercase();
        if filename_lower.contains(&lowercase_name)
            || filename_lower.contains(&format!("compound_{}", num_only))
            || filename_lower.contains(&format!("example_{}", num_only))
            || filename_lower.contains(&format!("intermediate_{}", num_only))
            || filename_lower.contains(&format!("reference_{}", num_only))
            || filename_lower.contains(&format!("struct_{}", num_only))
        {
            related.push(img.clone());
        }
    }

    related
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_named_molecule_series_basic() {
        let text =
            "Compound 1 was synthesized. Compound 2 showed activity. Compound 3 was inactive.";
        let mols = extract_named_molecule_series(text);
        assert_eq!(mols.len(), 3);
        assert_eq!(mols[0].name, "Compound 1");
        assert_eq!(mols[0].sequence_num, 1);
        assert_eq!(mols[1].name, "Compound 2");
        assert_eq!(mols[2].name, "Compound 3");
    }

    #[test]
    fn test_extract_named_molecule_series_example() {
        let text = "Example 1: mp 150° C. Example 2: mp 160 C.";
        let mols = extract_named_molecule_series(text);
        assert_eq!(mols.len(), 2);
        assert_eq!(mols[0].name_type, NameType::Example);
    }

    #[test]
    fn test_extract_named_molecule_series_mixed() {
        let text = "Compound 1 and Intermediate 3 were used. Reference 10 was cited.";
        let mols = extract_named_molecule_series(text);
        assert_eq!(mols.len(), 3);
        let types: Vec<_> = mols.iter().map(|m| m.name_type.clone()).collect();
        assert!(types.contains(&NameType::Compound));
        assert!(types.contains(&NameType::Intermediate));
        assert!(types.contains(&NameType::Reference));
    }

    #[test]
    fn test_extract_named_molecule_series_dedup() {
        let text = "Compound 1 is good. Compound 1 is also active.";
        let mols = extract_named_molecule_series(text);
        assert_eq!(mols.len(), 1);
    }

    #[test]
    fn test_extract_named_molecule_series_context() {
        let text = "Line A\nLine B\nCompound 5 was tested.\nLine D\nLine E";
        let mols = extract_named_molecule_series(text);
        assert_eq!(mols.len(), 1);
        assert!(mols[0].context_text.contains("Line B"));
        assert!(mols[0].context_text.contains("Line D"));
    }

    #[test]
    fn test_sequence_coherence_priority() {
        let text = "Compound 1.\nCompound 2.\nCompound 3.\nIsolated 9.";
        let mols = extract_named_molecule_series(text);
        // Compound 1/2/3 是连贯序列，应排在前面
        assert!(mols[0].sequence_num <= 3);
        assert!(mols[1].sequence_num <= 3);
        assert!(mols[2].sequence_num <= 3);
    }

    #[test]
    fn test_extract_properties_activity() {
        let text = "Compound 1: IC50 = 5.2 nM. logP = 3.5. mp = 150 C.";
        let mols = extract_named_molecule_series(text);
        assert_eq!(mols.len(), 1);
        let props = extract_properties_for_molecule(&mols[0], text, 500);
        let types: Vec<_> = props.iter().map(|p| p.property_type.as_str()).collect();
        assert!(types.contains(&"IC50"));
        assert!(types.contains(&"logP"));
        assert!(types.contains(&"mp"));
    }

    #[test]
    fn test_extract_properties_activity_reverse() {
        let text = "5.2 nM (IC50) was measured for Compound 1.";
        let mols = extract_named_molecule_series(text);
        let props = extract_properties_for_molecule(&mols[0], text, 500);
        assert!(!props.is_empty());
        assert_eq!(props[0].property_type, "IC50");
    }

    #[test]
    fn test_extract_properties_solubility() {
        let text = "Compound 2 has solubility: 10.5 mg/mL in water.";
        let mols = extract_named_molecule_series(text);
        let props = extract_properties_for_molecule(&mols[0], text, 500);
        let sol = props.iter().find(|p| p.property_type == "solubility");
        assert!(sol.is_some());
        assert!((sol.unwrap().value - 10.5).abs() < 1e-9);
        assert_eq!(sol.unwrap().unit, "mg/mL");
    }

    #[test]
    fn test_extract_properties_window_excludes_distant() {
        let text =
            "Compound 1: IC50 = 5.2 nM.\n...very long separator...\nCompound 2: IC50 = 100 nM.";
        let mols = extract_named_molecule_series(text);
        assert_eq!(mols.len(), 2);
        // 对 Compound 1 用小窗口，不应包含 Compound 2 的数据
        let small_window = mols[0].name.len() + 20;
        let props = extract_properties_for_molecule(&mols[0], text, small_window);
        let ic50_vals: Vec<f64> = props
            .iter()
            .filter(|p| p.property_type == "IC50")
            .map(|p| p.value)
            .collect();
        assert_eq!(ic50_vals.len(), 1);
        assert!((ic50_vals[0] - 5.2).abs() < 1e-9);
    }

    #[test]
    fn test_link_molecules_to_images_by_page() {
        let mol = NamedMolecule {
            name: "Compound 1".into(),
            name_type: NameType::Compound,
            sequence_num: 1,
            context_text: "".into(),
            section: "".into(),
            page_hint: Some(3),
            line_start: 0,
            line_end: 0,
            char_pos: 0,
        };
        let images = vec![
            ImageRef {
                filename: "page_2_img_1.png".into(),
                page: 2,
                region: None,
                description: None,
                esmiles: None,
                rel_path: None,
            },
            ImageRef {
                filename: "page_3_img_1.png".into(),
                page: 3,
                region: None,
                description: None,
                esmiles: None,
                rel_path: None,
            },
        ];
        let traces = link_molecules_to_images(&[mol], &images, &[]);
        assert_eq!(traces[0].related_images.len(), 1);
        assert_eq!(traces[0].related_images[0].page, 3);
    }

    #[test]
    fn test_link_molecules_to_images_by_filename() {
        let mol = NamedMolecule {
            name: "Compound 5".into(),
            name_type: NameType::Compound,
            sequence_num: 5,
            context_text: "".into(),
            section: "".into(),
            page_hint: None,
            line_start: 0,
            line_end: 0,
            char_pos: 0,
        };
        let images = vec![ImageRef {
            filename: "compound_5_structure.png".into(),
            page: 1,
            region: None,
            description: None,
            esmiles: None,
            rel_path: None,
        }];
        let traces = link_molecules_to_images(&[mol], &images, &[]);
        assert_eq!(traces[0].related_images.len(), 1);
    }

    #[test]
    fn test_parse_sequence_num_with_letter() {
        assert_eq!(parse_sequence_num("1A"), 1);
        assert_eq!(parse_sequence_num("12b"), 12);
        assert_eq!(parse_sequence_num("0"), 0);
    }

    #[test]
    fn test_normalize_unit() {
        assert_eq!(normalize_unit("uM"), "µM");
        assert_eq!(normalize_unit("nm"), "nM");
        assert_eq!(normalize_unit("%"), "%");
    }
}
