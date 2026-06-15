use serde::{Deserialize, Serialize};

use crate::core::helpers::SMILES_RE;

use crate::parsers::chem::association::{self, ActivityEntry};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/// Activity data with context window — used by extract_associated_molecules.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityData {
    pub activity_type: String,
    pub value: f64,
    pub units: String,
    pub context: String,
}

impl From<&ActivityEntry> for ActivityData {
    fn from(entry: &ActivityEntry) -> Self {
        Self {
            activity_type: entry.activity_type.clone(),
            value: entry.value,
            units: entry.unit.clone(),
            context: String::new(),
        }
    }
}

/// Organic subset for basic SMILES validation (fallback when RDKit unavailable).
const ORGANIC_CHARS: &[u8] = b"CcNnOoSsPp";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Basic SMILES validation: length > 3 and contains at least one organic atom.
fn is_valid_smiles_candidate(s: &str) -> bool {
    if s.len() <= 3 {
        return false;
    }
    s.as_bytes().iter().any(|b| ORGANIC_CHARS.contains(b))
}

/// Extract a context window around a match position.
fn extract_context(text: &str, start: usize, end: usize) -> String {
    let ctx_start = start.saturating_sub(50);
    let ctx_end = std::cmp::min(end + 50, text.len());
    text[ctx_start..ctx_end].to_string()
}

// ---------------------------------------------------------------------------
// Phase 1.1: SMILES-activity position association
// Port of `MoleculeExtractor.extract_from_text()` from
// `src/mbforge/parsers/molecule/molecule_extractor.py`.
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EsmilesWithPosition {
    pub esmiles: String,
    pub position: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssociatedMolecule {
    pub esmiles: String,
    pub activity: Option<ActivityData>,
    pub position: usize,
    pub confidence: String,
    pub source_doc: String,
}

/// Extract esmiles candidates with their text positions.
fn extract_esmiles_with_positions(text: &str) -> Vec<EsmilesWithPosition> {
    let mut seen = std::collections::HashSet::new();
    let mut results = Vec::new();

    for m in SMILES_RE.find_iter(text) {
        let candidate = m.as_str();
        if seen.contains(candidate) {
            continue;
        }
        if is_valid_smiles_candidate(candidate) {
            seen.insert(candidate.to_string());
            results.push(EsmilesWithPosition {
                esmiles: candidate.to_string(),
                position: m.start(),
            });
        }
    }

    results
}

/// Extract activity data with their text positions.
/// Uses association.rs patterns (IC50=, Ki of, value (IC50)) for broader coverage.
fn extract_activities_with_positions(text: &str) -> Vec<(ActivityData, usize)> {
    use regex::Regex;
    use std::sync::LazyLock;

    // All three activity patterns from association.rs
    static PATTERNS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
        vec![
            Regex::new(
                r"(?i)(IC50|EC50|EC90|Ki|Kd|IC90)\s*[=:]\s*([<>]?\d+\.?\d*)\s*(nM|µM|uM|μM|mM|pM)",
            ).expect("valid activity IC50 regex"),
            Regex::new(
                r"(?i)(IC50|EC50|EC90|Ki|Kd|IC90)\s+of\s+([<>]?\d+\.?\d*)\s*(nM|µM|uM|μM|mM|pM)",
            ).expect("valid activity of regex"),
            Regex::new(
                r"(?i)([<>]?\d+\.?\d*)\s*(nM|µM|uM|μM|mM|pM)\s*\(?\s*(IC50|EC50|EC90|Ki|Kd|IC90)\s*\)?",
            ).expect("valid activity paren regex"),
        ]
    });

    fn looks_like_type(s: &str) -> bool {
        matches!(
            s.to_uppercase().as_str(),
            "IC50" | "EC50" | "EC90" | "KI" | "KD" | "IC90"
        )
    }

    fn normalize_unit(unit: &str) -> String {
        match unit.to_lowercase().as_str() {
            "um" | "μm" => "µM",
            "nm" => "nM",
            "mm" => "mM",
            "pm" => "pM",
            _ => unit,
        }
        .to_string()
    }

    let mut results = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for pattern in PATTERNS.iter() {
        for caps in pattern.captures_iter(text) {
            let g0 = caps.get(1).map(|m| m.as_str()).unwrap_or("");
            let g1 = caps.get(2).map(|m| m.as_str()).unwrap_or("");
            let g2 = caps.get(3).map(|m| m.as_str()).unwrap_or("");

            let (act_type, val_str, unit) = if looks_like_type(g0) {
                (g0, g1, g2)
            } else if looks_like_type(g2) {
                (g2, g0, g1)
            } else {
                continue;
            };

            let value = match val_str
                .trim_start_matches(|c: char| c == '<' || c == '>')
                .trim()
                .parse::<f64>()
            {
                Ok(v) => v,
                Err(_) => continue,
            };
            let unit = normalize_unit(unit);
            let key = format!("{}|{}|{}", act_type.to_uppercase(), value, unit);

            if seen.insert(key.clone()) {
                let pos = caps.get(0).expect("matched regex has group 0").start();
                let context = extract_context(
                    text,
                    caps.get(0).expect("matched regex has group 0").start(),
                    caps.get(0).expect("matched regex has group 0").end(),
                );
                results.push((
                    ActivityData {
                        activity_type: act_type.to_uppercase(),
                        value,
                        units: unit,
                        context,
                    },
                    pos,
                ));
            }
        }
    }

    results
}

/// Extract esmiles from text and associate them with nearby activity data
/// based on spatial proximity (200-character window).
#[tauri::command]
pub fn extract_associated_molecules(text: String, source_doc: String) -> Vec<AssociatedMolecule> {
    let esmiles_list = extract_esmiles_with_positions(&text);
    let activities = extract_activities_with_positions(&text);
    let proximity_window: usize = 200;

    let mut used = vec![false; activities.len()];
    let mut results = Vec::new();

    for s in &esmiles_list {
        let mut best_idx = None;
        let mut best_dist = usize::MAX;

        for (i, (_, act_pos)) in activities.iter().enumerate() {
            if used[i] {
                continue;
            }
            let dist = if s.position > *act_pos {
                s.position - act_pos
            } else {
                act_pos - s.position
            };
            if dist < best_dist {
                best_dist = dist;
                best_idx = Some(i);
            }
        }

        let activity = best_idx.and_then(|idx| {
            if best_dist < proximity_window {
                used[idx] = true;
                Some(activities[idx].0.clone())
            } else {
                None
            }
        });

        let confidence = if activity.is_some() { "high" } else { "low" }.to_string();
        results.push(AssociatedMolecule {
            esmiles: s.esmiles.clone(),
            activity,
            position: s.position,
            confidence,
            source_doc: source_doc.clone(),
        });
    }

    results
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

/// Extract esmiles candidates from text using regex + basic validation.
///
/// Port of `MoleculeExtractor.extract_smiles_candidates()` from
/// `src/mbforge/parsers/molecule/molecule_extractor.py`.
/// Note: RDKit validation is not available in Rust — this uses basic
/// heuristic filtering instead.
#[tauri::command]
pub fn extract_esmiles_candidates(text: String) -> Vec<String> {
    let mut seen = std::collections::HashSet::new();
    let mut candidates = Vec::new();

    for m in SMILES_RE.find_iter(&text).map(|m| m.as_str()) {
        let candidate = m;
        if seen.contains(candidate) {
            continue;
        }
        if is_valid_smiles_candidate(candidate) {
            seen.insert(candidate.to_string());
            candidates.push(candidate.to_string());
        }
    }

    candidates
}

/// Extract activity data (IC50, EC50, Ki, Kd, etc.) from text.
///
/// Delegates to `association::extract_activities` which supports 3 pattern
/// variants (IC50=, Ki of, value (IC50)) with dedup and unit normalization.
#[tauri::command]
pub fn extract_activities(text: String) -> Vec<ActivityData> {
    association::extract_activities(&text)
        .iter()
        .map(ActivityData::from)
        .collect()
}

/// 一步式提取 + 关联：从文本中找出 esmiles 候选，构造 `ExtractionResult`，
/// 然后跑 `association::associate_all` 填 compound name / cell line / target。
/// 把分散的 regex + LLM-style 关联逻辑集中到一个 Tauri 命令里供前端调用，
/// 避免在 JS 端再走一遍字符串解析。
#[tauri::command]
pub fn extract_with_associations(
    text: String,
    context_window: Option<usize>,
) -> Vec<crate::core::types::ExtractionResult> {
    use crate::commands::extractor::extract_esmiles_with_positions;
    use crate::core::types::ExtractionResult;

    let window = context_window.unwrap_or(200);
    let esmiles_with_pos = extract_esmiles_with_positions(&text);

    let mut results: Vec<ExtractionResult> = esmiles_with_pos
        .into_iter()
        .map(|s| {
            let lo = s.position.saturating_sub(window);
            let hi = (s.position + window).min(text.len());
            let ctx = text.get(lo..hi).unwrap_or("").to_string();
            let mut r = ExtractionResult::new(&ctx);
            r.esmiles = s.esmiles.clone();
            r
        })
        .collect();

    association::associate_all(&mut results);
    results
}
