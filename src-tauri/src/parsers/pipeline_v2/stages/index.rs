//! Indexing stage for the PDF processing pipeline.
//!
//! This stage turns a [`PersistedDocument`] into an [`IndexedDocument`] by:
//!
//! 1. Loading the application configuration.
//! 2. Opening the project knowledge base.
//! 3. Retrieving cached section chunks from the file cache.
//! 4. Indexing the sections into the vector store and FTS5 index.

use async_trait::async_trait;

use crate::core::config::settings::AppConfig;
use crate::core::document::knowledge_base::KnowledgeBase;
use crate::core::types::SectionChunk;
use crate::parsers::pipeline_v2::context::{PipelineContext, PipelineEvent};
use crate::parsers::pipeline_v2::error::{IndexError, PipelineError};
use crate::parsers::pipeline_v2::models::persisted::{IndexedDocument, PersistedDocument};
use crate::parsers::pipeline_v2::runner::{Stage, StageOutcome};

/// Pipeline stage that indexes persisted document sections for search.
pub struct IndexStage;

impl IndexStage {
    /// Creates a new indexing stage.
    pub fn new() -> Self {
        Self
    }
}

impl Default for IndexStage {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl Stage<PersistedDocument, IndexedDocument> for IndexStage {
    /// Executes the index stage on a persisted document.
    async fn run(
        &self,
        input: PersistedDocument,
        ctx: &PipelineContext,
    ) -> Result<StageOutcome<IndexedDocument>, PipelineError> {
        let project_root = ctx.project_root.as_ref().ok_or_else(|| {
            PipelineError::Index(IndexError::VectorStoreFailed {
                detail: "project root not available for indexing".into(),
            })
        })?;

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "index".into(),
            message: "loading configuration".into(),
        });

        let config = AppConfig::load();

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "index".into(),
            message: "opening knowledge base".into(),
        });

        let kb = KnowledgeBase::new(project_root, Some(&config.embed)).map_err(|e| {
            PipelineError::Index(IndexError::VectorStoreFailed {
                detail: format!("failed to open knowledge base: {e}"),
            })
        })?;

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "index".into(),
            message: "retrieving cached sections".into(),
        });

        let sections: Vec<SectionChunk> = match kb.file_cache().get(&ctx.source_path) {
            Ok(Some(cached)) => {
                match serde_json::from_str::<Vec<SectionChunk>>(&cached.sections_json) {
                    Ok(sections) => sections,
                    Err(e) => {
                        log::warn!(
                            "failed to parse cached sections for {:?}: {}",
                            ctx.source_path,
                            e
                        );
                        Vec::new()
                    }
                }
            }
            Ok(None) => Vec::new(),
            Err(e) => {
                log::warn!("file cache read failed for {:?}: {}", ctx.source_path, e);
                Vec::new()
            }
        };

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "index".into(),
            message: format!("indexing {} sections", sections.len()),
        });

        // NOTE: page-level texts are not currently cached separately, so an empty
        // slice is passed here; the tree index still receives section coordinates.
        kb.index_document(&input.doc_id, &sections, &[])
            .map_err(|e| {
                PipelineError::Index(IndexError::EmbeddingFailed {
                    detail: format!("failed to index document: {e}"),
                })
            })?;

        let outcome = StageOutcome::new(IndexedDocument {
            doc_id: input.doc_id,
            indexed_sections: sections.len(),
        });

        Ok(outcome)
    }
}
