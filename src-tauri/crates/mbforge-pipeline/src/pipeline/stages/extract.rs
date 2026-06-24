//! Extract stage for the PDF processing pipeline.
//!
//! This stage turns a [`SourceInput`] into an [`ExtractedDocument`] by:
//!
//! 1. Resolving the MBForge project root for the source document.
//! 2. Returning a cached result when the file cache already contains an entry.
//! 3. Running the PDF inspector to obtain native text and metadata.
//! 4. Falling back to OCR when the document appears to be scanned and OCR is
//!    permitted.
//! 5. Extracting and persisting embedded images into the project's reports
//!    directory.

use std::path::PathBuf;

use async_trait::async_trait;
use serde_json::Value;

use crate::pipeline::context::{PipelineContext, PipelineEvent};
use crate::pipeline::error::{ExtractError, PipelineError};
use crate::pipeline::models::extracted::{
    ExtractedDocument, ExtractedMetadata, ImageRef, OcrBlock,
};
use crate::pipeline::models::source::SourceInput;
use crate::pipeline::runner::{Stage, StageOutcome};
use crate::pipeline::services::cache::{Cache, CachedExtractResult, FileCache};
use crate::pipeline::services::images::ImageService;
use crate::pipeline::services::inspector::InspectorService;
use crate::pipeline::services::ocr::OcrService;
use crate::pipeline::services::source::SourceResolver;

/// Pipeline stage that extracts raw content from a PDF source document.
pub struct ExtractStage {
    /// Native PDF text inspector.
    pub inspector: InspectorService,

    /// OCR fallback service.
    pub ocr: OcrService,

    /// Embedded image extraction and persistence service.
    pub images: ImageService,

    /// Project root resolver for the source document.
    pub resolver: SourceResolver,
}

impl ExtractStage {
    /// Creates a new [`ExtractStage`] with the supplied OCR service.
    ///
    /// The inspector, image service and source resolver are constructed with
    /// their default configurations.
    pub fn new(ocr: OcrService) -> Self {
        Self {
            inspector: InspectorService::new(),
            ocr,
            images: ImageService::new(),
            resolver: SourceResolver::new(),
        }
    }

    /// Builds an [`ExtractedDocument`] from a cached extract result.
    fn document_from_cache(
        cached: CachedExtractResult,
    ) -> Result<ExtractedDocument, PipelineError> {
        let metadata: Value = serde_json::from_str(&cached.metadata_json).unwrap_or_default();

        let images: Vec<ImageRef> = metadata
            .get("images")
            .and_then(|v| serde_json::from_value(v.clone()).ok())
            .unwrap_or_default();

        let ocr_blocks: Vec<OcrBlock> = metadata
            .get("ocr_blocks")
            .and_then(|v| serde_json::from_value(v.clone()).ok())
            .unwrap_or_default();

        let page_count = metadata
            .get("page_count")
            .and_then(|v| v.as_u64())
            .map(|n| n as usize)
            .unwrap_or(0);

        let parsed_metadata = ExtractedMetadata {
            title: metadata
                .get("title")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string()),
            authors: metadata
                .get("authors")
                .and_then(|v| serde_json::from_value(v.clone()).ok())
                .unwrap_or_default(),
            document_type: metadata
                .get("document_type")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string()),
        };

        Ok(ExtractedDocument {
            raw_text: cached.text,
            page_count,
            parser: "cached".into(),
            images,
            ocr_blocks,
            metadata: parsed_metadata,
        })
    }
}

#[async_trait]
impl Stage<SourceInput, ExtractedDocument> for ExtractStage {
    async fn run(
        &self,
        input: SourceInput,
        ctx: &PipelineContext,
    ) -> Result<StageOutcome<ExtractedDocument>, PipelineError> {
        let source_path: PathBuf = input.path;

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "extract".into(),
            message: "resolving project root".into(),
        });

        let project_root = self
            .resolver
            .resolve_project_root(&source_path, ctx.project_root.as_deref())?;

        // File-cache lookup keyed by the source path.
        let file_cache = FileCache::new(&project_root);
        let cache_key = source_path.display().to_string();
        if let Some(cached) = file_cache.get(&cache_key)? {
            ctx.reporter.report(PipelineEvent::StageProgress {
                stage: "extract".into(),
                message: "file cache hit".into(),
            });
            let document = Self::document_from_cache(cached)?;
            return Ok(StageOutcome::new(document));
        }

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "extract".into(),
            message: "running pdf-inspector".into(),
        });

        let mut extracted = self.inspector.extract(&source_path).await?;

        let is_scanned = (extracted.raw_text.len() < 100 && extracted.page_count > 0)
            || !extracted.ocr_blocks.is_empty();

        if is_scanned && input.allow_ocr {
            ctx.reporter.report(PipelineEvent::StageProgress {
                stage: "extract".into(),
                message: "running OCR".into(),
            });

            match self.ocr.run(&source_path).await {
                Ok((ocr_out, backend_name)) => {
                    let doc_slug = source_path
                        .file_stem()
                        .and_then(|s| s.to_str())
                        .unwrap_or("unknown");
                    let backend_images = self.images.persist_backend_images(
                        &project_root,
                        &ocr_out.images,
                        backend_name,
                        doc_slug,
                    );

                    extracted.raw_text = ocr_out.text;
                    extracted.page_count = ocr_out.page_count.max(extracted.page_count);
                    extracted.parser = backend_name.into();
                    extracted.images.extend(backend_images);
                    extracted.ocr_blocks = ocr_out.ocr_blocks;
                }
                Err(e) => {
                    return Ok(StageOutcome::new(extracted).with_warning(format!(
                        "OCR failed, falling back to inspector text: {}",
                        e
                    )));
                }
            }
        }

        // Extract embedded images into a temporary directory, then persist them
        // under the project root.
        let tmp = tempfile::tempdir().map_err(|e| {
            PipelineError::Extract(ExtractError::ImagePersistFailed {
                filename: source_path.display().to_string(),
                detail: e.to_string(),
            })
        })?;
        let embedded = self
            .images
            .extract_embedded_images(&source_path, tmp.path())
            .await?;
        let mut embedded_images =
            self.images
                .persist_extracted_images(&source_path, &project_root, &embedded);
        embedded_images.extend(extracted.images.drain(..));
        extracted.images = embedded_images;

        Ok(StageOutcome::new(extracted))
    }
}

#[cfg(test)]
mod tests {
    use std::path::Path;

    use super::*;
    use crate::pipeline::context::PipelineContext;
    use crate::pipeline::services::cache::{Cache, CachedExtractResult};
    use tempfile::TempDir;

    #[tokio::test]
    async fn test_extract_stage_returns_cached_document() {
        let tmp = TempDir::new().unwrap();
        let root = tmp.path();
        std::fs::create_dir_all(root.join(".mbforge")).unwrap();

        let source = root.join("sample.pdf");
        std::fs::write(&source, b"%PDF-1.4").unwrap();

        let cache = FileCache::new(root);
        let key = source.display().to_string();
        cache
            .put(
                &key,
                &CachedExtractResult {
                    text: "cached text".into(),
                    sections_json: "[]".into(),
                    metadata_json: r#"{"page_count":3,"parser":"cached"}"#.into(),
                },
            )
            .unwrap();

        let ctx = PipelineContext::new(&source, "").with_project_root(root);
        let stage = ExtractStage::new(OcrService::new(vec![]));
        let outcome = stage
            .run(SourceInput::new(&source).with_allow_ocr(true), &ctx)
            .await
            .unwrap();

        assert_eq!(outcome.output.raw_text, "cached text");
        assert_eq!(outcome.output.page_count, 3);
        assert_eq!(outcome.output.parser, "cached");
    }

    #[test]
    fn test_document_from_cache_parses_metadata() {
        let cached = CachedExtractResult {
            text: "text".into(),
            sections_json: "[]".into(),
            metadata_json: r#"{"title":"T","authors":["A"],"document_type":"journal","page_count":2,"images":[{"filename":"x.png","page":1,"region":null,"description":null,"esmiles":null,"rel_path":null}],"ocr_blocks":[]}"#.into(),
        };
        let doc = ExtractStage::document_from_cache(cached).unwrap();
        assert_eq!(doc.metadata.title, Some("T".into()));
        assert_eq!(doc.metadata.authors, vec!["A"]);
        assert_eq!(doc.metadata.document_type, Some("journal".into()));
        assert_eq!(doc.page_count, 2);
        assert_eq!(doc.images.len(), 1);
    }
}
