//! Chem facade — blocks parsers/ from directly calling core chem modules.
//!
//! All parser-layer chem operations should go through this facade,
//! keeping the architecture: parsers → core::chem::facade → core::chem::*.

pub use crate::core::chem::chem::SmilesValidation;
pub use crate::core::chem::markush::{MarkushOverlap, MarkushPattern, MatchLevel};
pub use crate::core::chem::molecode::MoleCodeResult;

/// Validate a SMILES string.
pub fn validate_smiles(smiles: &str) -> SmilesValidation {
    crate::core::chem::chem::validate_smiles(smiles)
}

/// Parse an E-SMILES string into a Markush pattern.
pub fn parse_esmiles(input: &str) -> MarkushPattern {
    crate::core::chem::markush::parse_esmiles(input)
}

/// Analyze Markush coverage between a candidate and query SMILES.
pub fn analyze_markush_coverage(
    esmiles: &str,
    query_smiles: &str,
    context_text: Option<&str>,
) -> MarkushOverlap {
    crate::core::chem::markush::analyze_markush_coverage(esmiles, query_smiles, context_text)
}

/// Convert E-SMILES to MoleCode Mermaid diagram.
pub fn esmiles_to_molecode(esmiles: &str, name: &str) -> Result<MoleCodeResult, String> {
    crate::core::chem::molecode::esmiles_to_molecode(esmiles, name)
}
