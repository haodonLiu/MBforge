//! Enrichment stage for the PDF processing pipeline.
//!
//! This stage turns an [`ExtractedDocument`] and a [`SegmentedDocument`] into an
//! [`EnrichedDocument`] by:
//!
//! 1. Post-processing each document section into structured chemical data.
//! 2. Detecting and recognizing molecules embedded in the PDF pages.
//! 3. Generating VLM captions for non-chemical images.
//! 4. Merging section and VLM results into a single [`StructuredData`] document.
//! 5. Validating and canonicalizing the E-SMILES of all extracted compounds.

use std::collections::HashMap;
use std::path::Path;

use async_trait::async_trait;

use crate::parsers::chem::vlm_chem::ChemImageResult;
use crate::parsers::doc_types::{DocumentMetadata, StructuredData};
use crate::parsers::pipeline::context::{PipelineContext, PipelineEvent};
use crate::parsers::pipeline::error::PipelineError;
use crate::parsers::pipeline::models::enriched::{DetectedMoleculeResult, EnrichedDocument};
use crate::parsers::pipeline::models::extracted::ExtractedDocument;
use crate::parsers::pipeline::models::segmented::SegmentedDocument;
use crate::parsers::pipeline::runner::{Stage, StageOutcome};
use crate::parsers::pipeline::services::captions::ImageCaptionService;
use crate::parsers::pipeline::services::chem_validate::ChemValidator;
use crate::parsers::pipeline::services::merge::StructuredDataMerger;
use crate::parsers::pipeline::services::molecules::MoleculeService;
use crate::parsers::pipeline::services::section_processor::SectionProcessor;

/// Pipeline stage that enriches extracted and segmented documents with
/// structured chemical data, molecule detections and image captions.
pub struct EnrichStage {
    /// LLM-backed section post-processor.
    pub section_processor: SectionProcessor,

    /// Molecule detection and recognition service.
    pub molecule_service: MoleculeService,

    /// VLM image captioning service.
    pub caption_service: ImageCaptionService,

    /// Structured-data merger and SAR analyzer.
    pub merger: StructuredDataMerger,

    /// Chemical structure validator.
    pub validator: ChemValidator,
}

impl EnrichStage {
    /// Creates a new enrichment stage.
    ///
    /// Sidecar-backed services (`MoleculeService`, `ImageCaptionService`) use the
    /// provided `sidecar_url`; other services do not require network access.
    ///
    /// # Arguments
    /// - `sidecar_url`: Base URL of the Python sidecar (e.g. `http://127.0.0.1:18792`).
    pub fn new(sidecar_url: impl Into<String>) -> Self {
        let sidecar_url = sidecar_url.into();
        Self {
            section_processor: SectionProcessor::new(),
            molecule_service: MoleculeService::new(sidecar_url.clone()),
            caption_service: ImageCaptionService::new(sidecar_url),
            merger: StructuredDataMerger::new(),
            validator: ChemValidator::new(),
        }
    }
}

/// Returns an empty [`StructuredData`] document used as a fallback when no
/// enrichment results were produced.
fn empty_structured_data() -> StructuredData {
    StructuredData {
        metadata: DocumentMetadata {
            title: None,
            authors: Vec::new(),
            document_type: "unknown".into(),
            key_targets: Vec::new(),
            source_file: None,
        },
        summary: String::new(),
        compounds: Vec::new(),
        activities: Vec::new(),
        key_findings: Vec::new(),
        uncertain_items: Vec::new(),
    }
}

#[async_trait]
impl Stage<(ExtractedDocument, SegmentedDocument), EnrichedDocument> for EnrichStage {
    /// Executes the enrichment stage on an extracted and segmented document.
    async fn run(
        &self,
        input: (ExtractedDocument, SegmentedDocument),
        ctx: &PipelineContext,
    ) -> Result<StageOutcome<EnrichedDocument>, PipelineError> {
        let (mut extracted, segmented) = input;
        let mut warnings: Vec<String> = Vec::new();

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "enrich".into(),
            message: "processing sections".into(),
        });

        let section_results = self
            .section_processor
            .process_sections(&segmented.sections, &extracted.parser, extracted.page_count)
            .await?;

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "enrich".into(),
            message: format!("extracted {} section results", section_results.len()),
        });

        let mut molecule_results: Vec<DetectedMoleculeResult> = Vec::new();
        let mut image_captions: HashMap<String, String> = HashMap::new();

        if let Some(ref project_root) = ctx.project_root {
            let source_path = ctx.source_path.to_string_lossy().to_string();

            ctx.reporter.report(PipelineEvent::StageProgress {
                stage: "enrich".into(),
                message: "extracting molecules".into(),
            });

            match self
                .molecule_service
                .extract(&source_path, &extracted, project_root)
                .await
            {
                Ok(results) => {
                    molecule_results = results;
                    ctx.reporter.report(PipelineEvent::StageProgress {
                        stage: "enrich".into(),
                        message: format!("detected {} molecules", molecule_results.len()),
                    });
                }
                Err(e) => {
                    warnings.push(format!("molecule extraction failed: {e}"));
                }
            }

            ctx.reporter.report(PipelineEvent::StageProgress {
                stage: "enrich".into(),
                message: "captioning images".into(),
            });

            match self
                .caption_service
                .caption_images(&mut extracted.images, project_root)
                .await
            {
                Ok(captions) => {
                    image_captions = captions;
                    ctx.reporter.report(PipelineEvent::StageProgress {
                        stage: "enrich".into(),
                        message: format!("captioned {} images", image_captions.len()),
                    });
                }
                Err(e) => {
                    warnings.push(format!("image captioning failed: {e}"));
                }
            }
        } else {
            warnings.push(
                "project root not available; skipping molecule extraction and image captioning"
                    .into(),
            );
        }

        let vlm_results: Vec<(String, ChemImageResult)> = molecule_results
            .iter()
            .map(|m| {
                let filename = Path::new(&m.crop_path)
                    .file_stem()
                    .map(|s| s.to_string_lossy().to_string())
                    .unwrap_or_else(|| format!("molecule_p{}_{:.4}", m.page, m.confidence));
                (
                    filename,
                    ChemImageResult {
                        esmiles: m.esmiles.clone(),
                        confidence: m.confidence,
                    },
                )
            })
            .collect();

        let (mut structured_data, sar_analysis) =
            if section_results.is_empty() && vlm_results.is_empty() {
                (empty_structured_data(), None)
            } else {
                self.merger.merge(&section_results, &vlm_results).await?
            };

        self.validator
            .validate_compounds(&mut structured_data.compounds)?;

        let mut outcome = StageOutcome::new(EnrichedDocument {
            structured_data,
            sar_analysis,
            molecule_results,
            image_captions,
            sections: segmented.sections,
        });

        for warning in warnings {
            outcome = outcome.with_warning(warning);
        }

        Ok(outcome)
    }
}

#[cfg(test)]
mod tests {
    use std::path::Path;

    use super::*;
    use crate::parsers::pipeline::context::PipelineContext;
    use crate::parsers::pipeline::models::extracted::{ExtractedDocument, ExtractedMetadata};
    use crate::parsers::pipeline::models::segmented::SegmentedDocument;

    #[tokio::test]
    async fn test_enrich_stage_empty_sections() {
        let extracted = ExtractedDocument {
            raw_text: "".into(),
            page_count: 0,
            parser: "test".into(),
            images: Vec::new(),
            ocr_blocks: Vec::new(),
            metadata: ExtractedMetadata::default(),
        };
        let segmented = SegmentedDocument {
            sections: Vec::new(),
            document_tree: Vec::new(),
            headings: Vec::new(),
        };

        let ctx = PipelineContext::new(Path::new("dummy.pdf"), "");
        let stage = EnrichStage::new("http://127.0.0.1:18792");
        let outcome = stage.run((extracted, segmented), &ctx).await.unwrap();

        assert!(outcome.output.structured_data.compounds.is_empty());
        assert!(outcome.output.structured_data.activities.is_empty());
        assert!(outcome.output.sar_analysis.is_none());
    }
}
