//! Section enrichment service for the PDF processing pipeline.
//!
//! This module turns a list of segmented [`SectionChunk`]s into structured
//! [`StructuredData`] by invoking the LLM-backed post-processor in parallel.
//! Individual section failures are represented as `None` values and are left
//! to the caller to log or surface.

use crate::parsers::doc_types::StructuredData;
use crate::parsers::pipeline::error::PipelineError;
use crate::parsers::pipeline::models::segmented::SectionChunk;

/// Service that post-processes document sections into structured data.
#[derive(Debug, Clone, Copy)]
pub struct SectionProcessor;

impl SectionProcessor {
    /// Creates a new [`SectionProcessor`].
    pub fn new() -> Self {
        Self
    }

    /// Runs LLM post-processing over the supplied sections in parallel.
    ///
    /// # Arguments
    /// - `sections`: The document sections produced by the segmentation stage.
    /// - `parser`: The parser backend name, forwarded to the post-processor.
    /// - `page_count`: Total number of pages in the source document.
    ///
    /// # Returns
    /// A list of successfully extracted [`StructuredData`] entries. Sections
    /// that fail post-processing are silently skipped.
    pub async fn process_sections(
        &self,
        sections: &[SectionChunk],
        parser: &str,
        page_count: usize,
    ) -> Result<Vec<StructuredData>, PipelineError> {
        let inputs: Vec<(String, String)> = sections
            .iter()
            .map(|s| (s.title.clone(), s.text.clone()))
            .collect();

        let results = crate::parsers::structure::post_process::post_process_sections_parallel(
            inputs, parser, page_count, None,
        )
        .await;

        let mut data = Vec::new();
        for res in results {
            if let Some(d) = res.into_data() {
                data.push(d);
            }
        }
        Ok(data)
    }
}

impl Default for SectionProcessor {
    fn default() -> Self {
        Self::new()
    }
}
