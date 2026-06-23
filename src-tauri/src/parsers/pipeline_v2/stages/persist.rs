//! Persistence stage for the PDF processing pipeline.
//!
//! This stage turns an [`ExtractedDocument`] and an [`EnrichedDocument`] into a
//! [`PersistedDocument`] by:
//!
//! 1. Resolving the MBForge `doc_id` for the source path.
//! 2. Writing the augmented extraction output to `text.md`.
//! 3. Writing the structured agent report to `report.md`.
//! 4. Persisting extracted compounds and activities to the molecule store.
//! 5. Counting images that still require verification.

use std::path::Path;

use async_trait::async_trait;

use crate::core::project::project::Project;
use crate::parsers::pipeline_v2::context::{PipelineContext, PipelineEvent};
use crate::parsers::pipeline_v2::error::{PersistError, PipelineError};
use crate::parsers::pipeline_v2::models::enriched::EnrichedDocument;
use crate::parsers::pipeline_v2::models::extracted::ExtractedDocument;
use crate::parsers::pipeline_v2::models::persisted::PersistedDocument;
use crate::parsers::pipeline_v2::runner::{Stage, StageOutcome};
use crate::parsers::pipeline_v2::services::molecule_store::MoleculeStoreWriter;
use crate::parsers::pipeline_v2::writer::report_md::write_agent_report;
use crate::parsers::pipeline_v2::writer::text_md::write_text_markdown;

/// Pipeline stage that persists extracted and enriched pipeline outputs to disk.
pub struct PersistStage {
    /// Writer for compound and activity records.
    pub molecule_writer: MoleculeStoreWriter,
}

impl PersistStage {
    /// Creates a new persistence stage.
    pub fn new() -> Self {
        Self {
            molecule_writer: MoleculeStoreWriter::new(),
        }
    }

    /// Resolves the document ID for `ctx.source_path` by matching it against the
    /// documents known to the project at `project_root`.
    ///
    /// Returns the first matching `doc_id`, or an error when the project cannot be
    /// opened or no document source path matches.
    fn resolve_doc_id(
        &self,
        ctx: &PipelineContext,
        project_root: &Path,
    ) -> Result<String, PipelineError> {
        let source_path = &ctx.source_path;
        let project = Project::open(project_root).ok_or_else(|| {
            PipelineError::Persist(PersistError::DocIdNotResolved {
                path: source_path.display().to_string(),
            })
        })?;

        let target = source_path
            .canonicalize()
            .unwrap_or_else(|_| source_path.to_path_buf());

        for doc in project.list_documents() {
            let Some(full_source) = project.get_document_source_path(&doc.doc_id) else {
                continue;
            };
            let canonical_source = full_source
                .canonicalize()
                .unwrap_or_else(|_| full_source.to_path_buf());
            if canonical_source == target {
                return Ok(doc.doc_id.clone());
            }
        }

        Err(PipelineError::Persist(PersistError::DocIdNotResolved {
            path: source_path.display().to_string(),
        }))
    }
}

impl Default for PersistStage {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl Stage<(ExtractedDocument, EnrichedDocument), PersistedDocument> for PersistStage {
    /// Executes the persistence stage on an extracted and enriched document.
    async fn run(
        &self,
        input: (ExtractedDocument, EnrichedDocument),
        ctx: &PipelineContext,
    ) -> Result<StageOutcome<PersistedDocument>, PipelineError> {
        let (extracted, enriched) = input;

        let Some(project_root) = ctx.project_root.as_ref() else {
            return Err(PipelineError::Persist(PersistError::DocIdNotResolved {
                path: ctx.source_path.display().to_string(),
            }));
        };

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "persist".into(),
            message: "resolving document id".into(),
        });

        let doc_id = self.resolve_doc_id(ctx, project_root)?;

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "persist".into(),
            message: "writing text.md".into(),
        });

        let (text_md_path, verifications) = write_text_markdown(
            project_root,
            &doc_id,
            &extracted.raw_text,
            &extracted.images,
            extracted.page_count,
            &extracted.parser,
        )?;
        let unverified_image_count = verifications.iter().filter(|v| !v.verified).count();

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "persist".into(),
            message: "writing report.md".into(),
        });

        let report_md_path = write_agent_report(
            project_root,
            &doc_id,
            Some(&enriched.structured_data),
            enriched.sar_analysis.as_deref(),
            &extracted.parser,
        )?;

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "persist".into(),
            message: "persisting molecules".into(),
        });

        let persisted_molecule_count = self.molecule_writer.write(
            project_root,
            &enriched.structured_data,
            &extracted.parser,
        )?;

        let outcome = StageOutcome::new(PersistedDocument {
            doc_id,
            text_md_path,
            report_md_path,
            unverified_image_count,
            persisted_molecule_count,
        });

        Ok(outcome)
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::path::Path;

    use super::*;
    use crate::parsers::doc_types::{DocumentMetadata, StructuredData};
    use crate::parsers::pipeline_v2::context::PipelineContext;
    use crate::parsers::pipeline_v2::models::enriched::EnrichedDocument;
    use crate::parsers::pipeline_v2::models::extracted::{ExtractedDocument, ExtractedMetadata};
    use tempfile::TempDir;

    #[tokio::test]
    async fn test_persist_stage_writes_markdown_files() {
        let tmp = TempDir::new().unwrap();
        let root = tmp.path();
        let mut project = Project::create(root).expect("create project");

        let incoming = root.join("incoming");
        std::fs::create_dir_all(&incoming).unwrap();
        let source = incoming.join("test.pdf");
        std::fs::write(&source, b"%PDF-1.4").unwrap();

        let entry = project.add_file(&source).expect("add pdf");
        let doc_id = entry.doc_id.clone();
        let source_in_project = project.get_document_source_path(&doc_id).unwrap();

        let ctx = PipelineContext::new(&source_in_project, "").with_project_root(root);

        let extracted = ExtractedDocument {
            raw_text: "Hello world".into(),
            page_count: 1,
            parser: "test".into(),
            images: Vec::new(),
            ocr_blocks: Vec::new(),
            metadata: ExtractedMetadata::default(),
        };
        let enriched = EnrichedDocument {
            structured_data: StructuredData {
                metadata: DocumentMetadata {
                    title: None,
                    authors: Vec::new(),
                    document_type: "unknown".into(),
                    key_targets: Vec::new(),
                    source_file: None,
                },
                summary: "".into(),
                compounds: Vec::new(),
                activities: Vec::new(),
                key_findings: Vec::new(),
                uncertain_items: Vec::new(),
            },
            sar_analysis: None,
            molecule_results: Vec::new(),
            image_captions: HashMap::new(),
            sections: Vec::new(),
        };

        let stage = PersistStage::new();
        let outcome = stage.run((extracted, enriched), &ctx).await.unwrap();

        assert_eq!(outcome.output.doc_id, doc_id);
        assert!(outcome.output.text_md_path.exists());
        assert!(outcome.output.report_md_path.exists());
    }
}
