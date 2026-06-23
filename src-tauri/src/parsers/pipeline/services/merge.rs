//! Structured data merging service for the PDF processing pipeline.
//!
//! This service combines per-section extraction results and VLM chemical
//! structure recognition results into a single consolidated [`StructuredData`]
//! document. It also produces a SAR (structure-activity relationship) analysis
//! text by delegating to the legacy [`run_merge_and_sar`] implementation.

use crate::parsers::chem::vlm_chem::ChemImageResult;
use crate::parsers::doc_types::{DocStructure, StructuredData};
use crate::parsers::pipeline::error::{EnrichError, PipelineError};
use crate::parsers::pipeline::legacy::merge::run_merge_and_sar;

/// Service that merges structured section results and VLM chemistry results.
#[derive(Debug, Clone)]
pub struct StructuredDataMerger;

impl StructuredDataMerger {
    /// Creates a new [`StructuredDataMerger`].
    pub fn new() -> Self {
        Self
    }

    /// Merges `section_results` and `vlm_results` into a single document.
    ///
    /// A default [`DocStructure`] is used because the legacy merger only relies
    /// on it for prompt context. On success, returns the merged
    /// [`StructuredData`] and the generated SAR analysis text.
    ///
    /// # Arguments
    /// - `section_results`: Structured data extracted from each document section.
    /// - `vlm_results`: VLM-recognized chemical structures keyed by image file
    ///   name.
    ///
    /// # Errors
    /// Returns [`PipelineError::Enrich`] with [`EnrichError::MergeFailed`] if the
    /// underlying merge step fails.
    pub async fn merge(
        &self,
        section_results: &[StructuredData],
        vlm_results: &[(String, ChemImageResult)],
    ) -> Result<(StructuredData, Option<String>), PipelineError> {
        let structure = DocStructure {
            doc_type: "unknown".into(),
            page_count: 0,
            has_compound_tables: false,
            has_chemical_structures: false,
            has_activity_data: false,
            estimated_sections: Vec::new(),
            key_terms: Vec::new(),
            recommended_approach: "default".into(),
        };

        let (data, sar) = run_merge_and_sar(section_results, vlm_results, &structure)
            .await
            .map_err(|e| PipelineError::Enrich(EnrichError::MergeFailed { detail: e }))?;

        Ok((data, Some(sar)))
    }
}
