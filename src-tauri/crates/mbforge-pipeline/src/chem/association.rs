use regex::Regex;
use serde::{Deserialize, Serialize};
use std::sync::LazyLock;

pub use mbforge_infra::types::ExtractionResult;

// ---------------------------------------------------------------------------
// Regex patterns (port of `association_engine.py`)
// ---------------------------------------------------------------------------

static COMPOUND_NAME_PATTERNS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    vec![
        Regex::new(r"(?i)Compound\s+(\d+[a-zA-Z]?)").expect("valid compound pattern regex"),
        Regex::new(r"(?i)Fig(?:ure)?\.?\s*(\d+[a-zA-Z]?)").expect("valid fig pattern regex"),
        Regex::new(r"(?i)Scheme\s+(\d+[a-zA-Z]?)").expect("valid scheme pattern regex"),
        Regex::new(r"(?i)Table\s+(\d+[a-zA-Z]?)").expect("valid table pattern regex"),
    ]
});

static ACTIVITY_PATTERNS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    vec![
        // IC50 = 5.2 nM
        Regex::new(
            r"(?i)(IC50|EC50|EC90|Ki|Kd|IC90)\s*[=:]\s*([<>]?\d+\.?\d*)\s*(nM|µM|uM|μM|mM|pM)",
        )
        .expect("valid activity IC50 regex"),
        // Ki of 3.4 nM
        Regex::new(
            r"(?i)(IC50|EC50|EC90|Ki|Kd|IC90)\s+of\s+([<>]?\d+\.?\d*)\s*(nM|µM|uM|μM|mM|pM)",
        )
        .expect("valid activity of regex"),
        // 5.2 nM (IC50)
        Regex::new(
            r"(?i)([<>]?\d+\.?\d*)\s*(nM|µM|uM|μM|mM|pM)\s*\(?\s*(IC50|EC50|EC90|Ki|Kd|IC90)\s*\)?",
        )
        .expect("valid activity paren regex"),
    ]
});

static CELL_LINE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(\b[A-Z][a-zA-Z0-9\-]+\s+(cell|cells|line)\b)").expect("valid cell line regex")
});

static TARGET_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(\b[A-Z][a-z]+\s+(receptor|kinase|protease|enzyme|channel|transporter)\b)")
        .expect("valid target regex")
});

// ---------------------------------------------------------------------------
// Static helpers
// ---------------------------------------------------------------------------

/// Check whether a string looks like an activity type (IC50, EC50, etc.).
fn looks_like_type(s: &str) -> bool {
    matches!(
        s.to_uppercase().as_str(),
        "IC50" | "EC50" | "EC90" | "KI" | "KD" | "IC90"
    )
}

/// Normalize concentration units to the standard form.
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

/// Parse a value string with optional `<`/`>` prefix, returning the float.
fn parse_activity_value(val_str: &str) -> Option<f64> {
    let cleaned = val_str
        .trim_start_matches(|c: char| c == '<' || c == '>')
        .trim();
    cleaned.parse::<f64>().ok()
}

// ---------------------------------------------------------------------------
// Public API — port of `AssociationEngine` from
// `src/mbforge/parsers/molecule/association_engine.py`.
// ---------------------------------------------------------------------------

/// Extract compound name/number from context text.
///
/// Priority: Compound > Fig > Scheme > Table
pub fn extract_compound_name(text: &str) -> Option<String> {
    for pattern in COMPOUND_NAME_PATTERNS.iter() {
        if let Some(m) = pattern.find(text) {
            return Some(m.as_str().to_string());
        }
    }
    None
}

/// A single activity entry with type, value, and unit.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityEntry {
    pub activity_type: String,
    pub value: f64,
    pub unit: String,
}

/// Extract activity data from text using all three pattern variants.
///
/// Returns deduplicated entries (by type+value+unit).
pub fn extract_activities(text: &str) -> Vec<ActivityEntry> {
    let mut activities = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for pattern in ACTIVITY_PATTERNS.iter() {
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

            let value = match parse_activity_value(val_str) {
                Some(v) => v,
                None => continue,
            };
            let unit = normalize_unit(unit);
            let key = format!("{}|{}|{}", act_type.to_uppercase(), value, unit);

            if seen.insert(key) {
                activities.push(ActivityEntry {
                    activity_type: act_type.to_uppercase(),
                    value,
                    unit,
                });
            }
        }
    }

    activities
}

/// Extract cell line mentions from text.
pub fn extract_cell_lines(text: &str) -> Vec<String> {
    CELL_LINE_RE
        .captures_iter(text)
        .filter_map(|c| c.get(1).map(|m| m.as_str().to_string()))
        .collect()
}

/// Extract target/receptor mentions from text.
pub fn extract_targets(text: &str) -> Vec<String> {
    TARGET_RE
        .captures_iter(text)
        .filter_map(|c| c.get(1).map(|m| m.as_str().to_string()))
        .collect()
}

/// Run all association steps on a single `ExtractionResult`.
///
/// Fills in `name` and `properties` (activity_type, activity_value,
/// activity_unit, activities, cell_lines, targets).
pub fn associate_single(result: &mut ExtractionResult) {
    let text = &result.context_text;
    if text.is_empty() {
        return;
    }

    // 1. Compound name
    if let Some(name) = extract_compound_name(text) {
        if result.name.is_empty() {
            result.name = name;
        }
    }

    // Ensure `result.properties` is a JSON object. We use a fresh map
    // local variable to avoid the unsafe `as_object_mut().unwrap()` that
    // would otherwise be required after re-assigning properties.
    let mut map_owned: serde_json::Map<String, serde_json::Value> =
        match result.properties.as_object_mut() {
            Some(m) => std::mem::take(m),
            None => {
                log::warn!("associate_single: properties is not a JSON object, resetting");
                serde_json::Map::new()
            }
        };

    // 2. Activities
    let activities = extract_activities(text);
    if !activities.is_empty() {
        let first = &activities[0];
        map_owned
            .entry("activity_type".to_string())
            .or_insert(serde_json::json!(first.activity_type));
        map_owned
            .entry("activity_value".to_string())
            .or_insert(serde_json::json!(first.value));
        map_owned
            .entry("activity_unit".to_string())
            .or_insert(serde_json::json!(first.unit));

        let activities_json: Vec<serde_json::Value> = activities
            .iter()
            .map(|a| {
                serde_json::json!({
                    "type": a.activity_type,
                    "value": a.value,
                    "unit": a.unit,
                })
            })
            .collect();
        map_owned
            .entry("activities".to_string())
            .or_insert(serde_json::json!(activities_json));
    }

    // 3. Cell lines
    let cell_lines = extract_cell_lines(text);
    if !cell_lines.is_empty() {
        map_owned
            .entry("cell_lines".to_string())
            .or_insert(serde_json::json!(cell_lines));
    }

    // 4. Targets
    let targets = extract_targets(text);
    if !targets.is_empty() {
        map_owned
            .entry("targets".to_string())
            .or_insert(serde_json::json!(targets));
    }

    // Write back the populated map.
    result.properties = serde_json::Value::Object(map_owned);
}

/// Batch association: run `associate_single` on every result.
pub fn associate_all(results: &mut [ExtractionResult]) {
    for result in results.iter_mut() {
        associate_single(result);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_compound_name_compound() {
        assert_eq!(
            extract_compound_name("Compound 1 showed activity").as_deref(),
            Some("Compound 1")
        );
    }

    #[test]
    fn test_extract_compound_name_figure() {
        assert_eq!(
            extract_compound_name("As shown in Fig. 2A").as_deref(),
            Some("Fig. 2A")
        );
    }

    #[test]
    fn test_extract_compound_name_scheme() {
        assert_eq!(
            extract_compound_name("See Scheme 3").as_deref(),
            Some("Scheme 3")
        );
    }

    #[test]
    fn test_extract_compound_name_table() {
        assert_eq!(
            extract_compound_name("Table 1 summarizes").as_deref(),
            Some("Table 1")
        );
    }

    #[test]
    fn test_extract_compound_name_priority() {
        assert_eq!(
            extract_compound_name("Compound 5 in Fig. 3").as_deref(),
            Some("Compound 5")
        );
    }

    #[test]
    fn test_extract_activities_ic50_eq() {
        let acts = extract_activities("IC50 = 5.2 nM");
        assert_eq!(acts.len(), 1);
        assert_eq!(acts[0].activity_type, "IC50");
        assert!((acts[0].value - 5.2).abs() < 1e-9);
        assert_eq!(acts[0].unit, "nM");
    }

    #[test]
    fn test_extract_activities_ki_of() {
        let acts = extract_activities("Ki of 3.4 nM");
        assert_eq!(acts.len(), 1);
        assert_eq!(acts[0].activity_type, "KI");
        assert_eq!(acts[0].unit, "nM");
    }

    #[test]
    fn test_extract_activities_value_paren() {
        let acts = extract_activities("5.2 nM (IC50)");
        assert_eq!(acts.len(), 1);
        assert_eq!(acts[0].activity_type, "IC50");
    }

    #[test]
    fn test_extract_activities_dedup() {
        let acts = extract_activities("IC50 = 5.2 nM and IC50=5.2 nM");
        assert_eq!(acts.len(), 1);
    }

    #[test]
    fn test_extract_activities_unit_normalization() {
        let acts = extract_activities("EC50: 0.1 uM");
        assert_eq!(acts[0].unit, "µM");
    }

    #[test]
    fn test_extract_cell_lines() {
        let lines = extract_cell_lines("HEK293 cells were used");
        assert!(!lines.is_empty());
        assert!(lines[0].contains("cells"));
    }

    #[test]
    fn test_extract_targets() {
        let targets = extract_targets("EGFR receptor was inhibited");
        assert!(!targets.is_empty());
        assert!(targets[0].contains("receptor"));
    }

    #[test]
    fn test_associate_single_basic() {
        let mut result = ExtractionResult::new("Compound 1: IC50 = 5.2 nM in HEK293 cells");
        associate_single(&mut result);
        assert_eq!(result.name, "Compound 1");
        assert_eq!(result.properties["activity_type"], "IC50");
        assert_eq!(result.properties["cell_lines"][0], "HEK293 cells");
    }
}
