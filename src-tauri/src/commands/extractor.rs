use regex::Regex;
use serde::{Deserialize, Serialize};
use std::sync::LazyLock;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityData {
    pub activity_type: String,
    pub value: f64,
    pub units: String,
    pub context: String,
}

// ---------------------------------------------------------------------------
// Regex patterns
// ---------------------------------------------------------------------------

/// SMILES candidate pattern (simplified — no RDKit validation in Rust).
static SMILES_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"[A-Za-z0-9@.+\-=#$()\[\]\\/%]{4,}").unwrap());

/// Activity data pattern: IC50 = 5.2 nM, EC50: 10 µM, etc.
static ACTIVITY_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"(?i)(IC50|EC50|Ki|Kd|pIC50|pEC50)\s*[=:~]\s*([0-9.]+)\s*(nM|µM|uM|μM|mM|M|pM)",
    )
    .unwrap()
});

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
// Tauri commands
// ---------------------------------------------------------------------------

/// Extract SMILES candidates from text using regex + basic validation.
///
/// Port of `MoleculeExtractor.extract_smiles_candidates()` from
/// `src/mbforge/parsers/molecule/molecule_extractor.py`.
/// Note: RDKit validation is not available in Rust — this uses basic
/// heuristic filtering instead.
#[tauri::command]
pub fn extract_smiles_candidates(text: String) -> Vec<String> {
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
/// Port of `MoleculeExtractor.extract_activities()` from
/// `src/mbforge/parsers/molecule/molecule_extractor.py`.
#[tauri::command]
pub fn extract_activities(text: String) -> Vec<ActivityData> {
    let mut results = Vec::new();

    for caps in ACTIVITY_RE.captures_iter(&text) {
        let activity_type = caps.get(1).unwrap().as_str().to_uppercase();
        let value: f64 = caps.get(2).unwrap().as_str().parse().unwrap_or(0.0);
        let units = caps.get(3).unwrap().as_str().replace("uM", "µM");
        let context = extract_context(&text, caps.get(0).unwrap().start(), caps.get(0).unwrap().end());

        results.push(ActivityData {
            activity_type,
            value,
            units,
            context,
        });
    }

    results
}
