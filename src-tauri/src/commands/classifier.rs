use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::sync::LazyLock;

use crate::core::helpers::SMILES_RE;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PageClassification {
    pub page_idx: usize,
    pub text_density: f64,
    pub is_scanned: bool,
    pub has_molecular_patterns: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentClassification {
    pub text_density: f64,
    pub is_scanned: bool,
    pub has_molecular_patterns: bool,
    pub metadata_hints: Option<serde_json::Value>,
    pub pages: Vec<PageClassification>,
    pub needs_confirmation: bool,
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SCAN_THRESHOLD: f64 = 20.0;
const DOCUMENT_SCAN_THRESHOLD: f64 = 50.0;

/// Common chemical names.
static CHEMICAL_NAMES: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    let names = [
        "aspirin",
        "ibuprofen",
        "caffeine",
        "metformin",
        "paracetamol",
        "acetaminophen",
        "penicillin",
        "morphine",
        "codeine",
        "insulin",
        "glucose",
        "ethanol",
        "methanol",
        "acetone",
        "benzene",
        "toluene",
        "phenol",
        "aniline",
        "pyridine",
        "quinoline",
    ];
    names.iter().copied().collect()
});

/// Molecular keywords for metadata analysis.
static MOLECULAR_KEYWORDS: &[&str] = &["mol", "drug", "compound", "chemical", "pharma"];

// ---------------------------------------------------------------------------
// SMILES detection (split from Python lookahead regex)
// ---------------------------------------------------------------------------

/// Check if a string match looks like a SMILES pattern.
/// The Python regex uses a lookahead that Rust doesn't support,
/// so we check structural features directly.
fn is_smiles_like(s: &str) -> bool {
    // Must contain at least one of: =, #, @, [+, [-, or lowercase-letter+digit
    let bytes = s.as_bytes();
    let mut has_bond = false;
    let mut has_ring = false;
    let mut has_chirality = false;
    let mut has_charge = false;
    let mut prev_lower = false;

    for &b in bytes {
        match b {
            b'=' | b'#' => has_bond = true,
            b'@' => has_chirality = true,
            b'[' => has_charge = true, // simplified: any bracket
            _ => {}
        }
        if prev_lower && b.is_ascii_digit() {
            has_ring = true;
        }
        prev_lower = b.is_ascii_lowercase();
    }

    has_bond || has_ring || has_chirality || has_charge
}

// ---------------------------------------------------------------------------
// Core functions
// ---------------------------------------------------------------------------

/// Detect SMILES or chemical names in text.
fn detect_molecular_patterns(text: &str) -> bool {
    // Check SMILES-like patterns
    for m in SMILES_RE.find_iter(text).map(|m| m.as_str()) {
        if is_smiles_like(m) {
            return true;
        }
    }
    // Check chemical names
    let lower = text.to_lowercase();
    for name in CHEMICAL_NAMES.iter() {
        if lower.contains(name) {
            return true;
        }
    }
    false
}

/// Analyze PDF metadata for molecular hints.
fn analyze_metadata(metadata: &serde_json::Value) -> serde_json::Value {
    let mut hints = serde_json::Map::new();

    if let Some(filename) = metadata.get("filename").and_then(|v| v.as_str()) {
        let lower = filename.to_lowercase();
        if MOLECULAR_KEYWORDS.iter().any(|kw| lower.contains(kw)) {
            hints.insert("filename_hint".into(), true.into());
        }
    }

    if let Some(title) = metadata.get("title").and_then(|v| v.as_str()) {
        let lower = title.to_lowercase();
        if MOLECULAR_KEYWORDS.iter().any(|kw| lower.contains(kw)) {
            hints.insert("title_hint".into(), true.into());
        }
    }

    serde_json::Value::Object(hints)
}

/// Determine if user confirmation is needed.
fn needs_confirmation(pages: &[PageClassification]) -> bool {
    let scanned = pages.iter().filter(|p| p.is_scanned).count();
    let text = pages.len() - scanned;
    // Mixed content
    if scanned > 0 && text > 0 {
        return true;
    }
    // Any molecular patterns
    if pages.iter().any(|p| p.has_molecular_patterns) {
        return true;
    }
    false
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn classify_page(page_text: String, page_idx: usize) -> PageClassification {
    let text_density = page_text.trim().len() as f64;
    let is_scanned = text_density < PAGE_SCAN_THRESHOLD;
    let has_molecular_patterns = detect_molecular_patterns(&page_text);

    PageClassification {
        page_idx,
        text_density,
        is_scanned,
        has_molecular_patterns,
    }
}

#[tauri::command]
pub fn classify_document(
    pages: Vec<String>,
    metadata: Option<serde_json::Value>,
) -> DocumentClassification {
    if pages.is_empty() {
        return DocumentClassification {
            text_density: 0.0,
            is_scanned: true,
            has_molecular_patterns: false,
            metadata_hints: None,
            pages: vec![],
            needs_confirmation: false,
        };
    }

    let total_chars: usize = pages.iter().map(|p| p.trim().len()).sum();
    let avg_density = total_chars as f64 / pages.len() as f64;

    let page_classifications: Vec<PageClassification> = pages
        .iter()
        .enumerate()
        .map(|(idx, text)| classify_page(text.clone(), idx))
        .collect();

    let has_molecules = page_classifications
        .iter()
        .any(|p| p.has_molecular_patterns);

    let metadata_hints = metadata.map(|m| analyze_metadata(&m));

    let confirm = needs_confirmation(&page_classifications);

    DocumentClassification {
        text_density: avg_density,
        is_scanned: avg_density < DOCUMENT_SCAN_THRESHOLD,
        has_molecular_patterns: has_molecules,
        metadata_hints,
        pages: page_classifications,
        needs_confirmation: confirm,
    }
}
