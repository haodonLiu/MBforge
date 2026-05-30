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
fn extract_activities_with_positions(text: &str) -> Vec<(ActivityData, usize)> {
    let mut results = Vec::new();

    for caps in ACTIVITY_RE.captures_iter(text) {
        let activity_type = caps.get(1).unwrap().as_str().to_uppercase();
        let value: f64 = caps.get(2).unwrap().as_str().parse().unwrap_or(0.0);
        let units = caps.get(3).unwrap().as_str().replace("uM", "µM");
        let context = extract_context(
            text,
            caps.get(0).unwrap().start(),
            caps.get(0).unwrap().end(),
        );
        let pos = caps.get(0).unwrap().start();

        results.push((
            ActivityData {
                activity_type,
                value,
                units,
                context,
            },
            pos,
        ));
    }

    results
}

/// Extract esmiles from text and associate them with nearby activity data
/// based on spatial proximity (200-character window).
#[tauri::command]
pub fn extract_associated_molecules(
    text: String,
    source_doc: String,
) -> Vec<AssociatedMolecule> {
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
