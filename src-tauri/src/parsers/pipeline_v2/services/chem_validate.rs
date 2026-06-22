//! Chemical structure validation service for the PDF processing pipeline.
//!
//! This service validates the E-SMILES strings stored in [`CompoundEntry`]
//! records using the batch chemical validator. Valid structures are
//! canonicalized and have their confidence promoted when appropriate, while
//! invalid structures are marked as low confidence with a human-readable
//! explanation of the validation issues.

use std::collections::HashSet;

use crate::parsers::chem::chem_validate::validate_smiles_batch;
use crate::parsers::doc_types::CompoundEntry;
use crate::parsers::pipeline_v2::error::PipelineError;

/// Service that validates and canonicalizes E-SMILES in compound entries.
#[derive(Debug, Clone)]
pub struct ChemValidator;

impl ChemValidator {
    /// Creates a new [`ChemValidator`].
    pub fn new() -> Self {
        Self
    }

    /// Validates the E-SMILES of each compound in place.
    ///
    /// Duplicate E-SMILES values are deduplicated before calling the batch
    /// validator to avoid redundant work. For each compound with an E-SMILES:
    ///
    /// - If valid, the E-SMILES is replaced by its canonical form when they
    ///   differ, and confidence is promoted to `"high"` when no issues remain.
    /// - If invalid, confidence is set to `"low"` and `uncertainty_reason` is
    ///   populated with the validation issue messages.
    ///
    /// # Arguments
    /// - `compounds`: Mutable slice of compound entries to validate.
    ///
    /// # Errors
    /// This function currently returns `Ok(())` after mutating `compounds` in
    /// place. The [`Result`] return type is reserved for future fallible
    /// validation steps.
    pub fn validate_compounds(&self, compounds: &mut [CompoundEntry]) -> Result<(), PipelineError> {
        let esmiles_to_validate: Vec<String> = compounds
            .iter()
            .filter_map(|c| c.esmiles.clone())
            .collect::<HashSet<_>>()
            .into_iter()
            .collect();

        if esmiles_to_validate.is_empty() {
            return Ok(());
        }

        let results = validate_smiles_batch(&esmiles_to_validate);

        for compound in compounds.iter_mut() {
            let Some(ref esmiles) = compound.esmiles else {
                continue;
            };
            let Some((_, result)) = results.iter().find(|(s, _)| s == esmiles) else {
                continue;
            };
            if result.valid {
                if let Some(ref canonical) = result.canonical_smiles {
                    if canonical != esmiles {
                        compound.esmiles = Some(canonical.clone());
                    }
                }
                if compound.confidence != "high" && result.issues.is_empty() {
                    compound.confidence = "high".into();
                }
            } else {
                compound.confidence = "low".into();
                let issue_msgs: Vec<String> = result
                    .issues
                    .iter()
                    .map(|i| format!("[{}] {}", i.code, i.message))
                    .collect();
                compound.uncertainty_reason =
                    Some(format!("化学结构验证失败: {}", issue_msgs.join("; ")));
            }
        }

        Ok(())
    }
}
