//! Structured error types for the PDF processing pipeline.

use std::path::PathBuf;
use thiserror::Error;

/// Top-level error type for the PDF processing pipeline.
#[derive(Debug, Clone, PartialEq, Error)]
pub enum PipelineError {
    /// An error occurred during the extract stage.
    #[error("extract stage failed: {0}")]
    Extract(#[from] ExtractError),
    /// An error occurred during the segment stage.
    #[error("segment stage failed: {0}")]
    Segment(#[from] SegmentError),
    /// An error occurred during the enrich stage.
    #[error("enrich stage failed: {0}")]
    Enrich(#[from] EnrichError),
    /// An error occurred during the persist stage.
    #[error("persist stage failed: {0}")]
    Persist(#[from] PersistError),
    /// An error occurred during the index stage.
    #[error("index stage failed: {0}")]
    Index(#[from] IndexError),
}

/// Errors that can occur while extracting content from a PDF source.
#[derive(Debug, Clone, PartialEq, Error)]
pub enum ExtractError {
    /// The source path is not valid or not accessible.
    #[error("source path invalid: {path}")]
    SourcePathInvalid { path: String },
    /// The project root could not be determined for the given path.
    #[error("project root not found for path: {path}")]
    ProjectRootNotFound { path: String },
    /// The PDF inspector failed to read the document.
    #[error("inspector failed for '{path}': {detail}")]
    InspectorFailed { path: String, detail: String },
    /// All configured OCR backends failed to process the document.
    #[error("all OCR backends failed for '{path}': {details}")]
    OcrAllBackendsFailed { path: String, details: String },
    /// No OCR backends are registered with the service.
    #[error("no OCR backends registered")]
    NoBackends,
    /// An extracted image could not be persisted to disk.
    #[error("image persist failed for '{filename}': {detail}")]
    ImagePersistFailed { filename: String, detail: String },
    /// Reading from a cache failed.
    #[error("cache read failed for '{cache}': {detail}")]
    CacheReadFailed { cache: String, detail: String },
    /// Writing to a cache failed.
    #[error("cache write failed for '{cache}': {detail}")]
    CacheWriteFailed { cache: String, detail: String },
}

/// Errors that can occur while segmenting document content.
#[derive(Debug, Clone, PartialEq, Error)]
pub enum SegmentError {
    /// The document contains no extractable text content.
    #[error("document contains no text content")]
    NoTextContent,
    /// A section exceeds the maximum allowed length.
    #[error("section '{title}' is too long ({chars} characters)")]
    SectionTooLong { title: String, chars: usize },
}

/// Errors that can occur while enriching document segments.
#[derive(Debug, Clone, PartialEq, Error)]
pub enum EnrichError {
    /// Processing a specific section failed.
    #[error("section processing failed for '{section}': {detail}")]
    SectionProcessingFailed { section: String, detail: String },
    /// The molecule service returned an error.
    #[error("molecule service failed: {detail}")]
    MoleculeServiceFailed { detail: String },
    /// The caption service failed for an image.
    #[error("caption service failed for '{filename}': {detail}")]
    CaptionServiceFailed { filename: String, detail: String },
    /// Merging enrichment results failed.
    #[error("merge failed: {detail}")]
    MergeFailed { detail: String },
    /// Chemical validation of an E-SMILES string failed.
    #[error("chemical validation failed for '{esmiles}': {detail}")]
    ChemValidationFailed { esmiles: String, detail: String },
}

/// Errors that can occur while persisting pipeline outputs.
#[derive(Debug, Clone, PartialEq, Error)]
pub enum PersistError {
    /// Writing the extracted text markdown file failed.
    #[error("text markdown write failed for '{path}': {detail}")]
    TextMdWriteFailed { path: PathBuf, detail: String },
    /// Writing the report markdown file failed.
    #[error("report markdown write failed for '{path}': {detail}")]
    ReportMdWriteFailed { path: PathBuf, detail: String },
    /// Persisting molecules to the store failed.
    #[error("molecule store failed: {detail}")]
    MoleculeStoreFailed { detail: String },
    /// The document id could not be resolved for the given path.
    #[error("document id not resolved for path: {path}")]
    DocIdNotResolved { path: String },
}

/// Errors that can occur while indexing document content.
#[derive(Debug, Clone, PartialEq, Error)]
pub enum IndexError {
    /// Generating embeddings for the content failed.
    #[error("embedding failed: {detail}")]
    EmbeddingFailed { detail: String },
    /// Writing vectors to the vector store failed.
    #[error("vector store failed: {detail}")]
    VectorStoreFailed { detail: String },
    /// Writing to the file cache failed.
    #[error("file cache write failed: {detail}")]
    FileCacheWriteFailed { detail: String },
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extract_error_display_includes_stage_and_details() {
        let err = PipelineError::Extract(ExtractError::InspectorFailed {
            path: "/tmp/x.pdf".into(),
            detail: "io".into(),
        });
        let msg = err.to_string();
        assert!(msg.contains("extract stage failed"));
        assert!(msg.contains("inspector failed for '/tmp/x.pdf': io"));
    }

    #[test]
    fn segment_error_display_includes_stage_and_details() {
        let err = PipelineError::Segment(SegmentError::SectionTooLong {
            title: "Introduction".into(),
            chars: 50000,
        });
        let msg = err.to_string();
        assert!(msg.contains("segment stage failed"));
        assert!(msg.contains("section 'Introduction' is too long (50000 characters)"));
    }

    #[test]
    fn enrich_error_display_includes_stage_and_details() {
        let err = PipelineError::Enrich(EnrichError::MoleculeServiceFailed {
            detail: "timeout".into(),
        });
        let msg = err.to_string();
        assert!(msg.contains("enrich stage failed"));
        assert!(msg.contains("molecule service failed: timeout"));
    }

    #[test]
    fn persist_error_display_includes_stage_and_details() {
        let err = PipelineError::Persist(PersistError::TextMdWriteFailed {
            path: PathBuf::from("/tmp/out.md"),
            detail: "permission denied".into(),
        });
        let msg = err.to_string();
        assert!(msg.contains("persist stage failed"));
        assert!(msg.contains("text markdown write failed for '/tmp/out.md': permission denied"));
    }

    #[test]
    fn index_error_display_includes_stage_and_details() {
        let err = PipelineError::Index(IndexError::EmbeddingFailed {
            detail: "model unavailable".into(),
        });
        let msg = err.to_string();
        assert!(msg.contains("index stage failed"));
        assert!(msg.contains("embedding failed: model unavailable"));
    }

    #[test]
    fn from_conversions_build_pipeline_error() {
        let extract: PipelineError = ExtractError::SourcePathInvalid {
            path: "/bad".into(),
        }
        .into();
        assert!(matches!(extract, PipelineError::Extract(_)));

        let segment: PipelineError = SegmentError::NoTextContent.into();
        assert!(matches!(segment, PipelineError::Segment(_)));

        let enrich: PipelineError = EnrichError::MergeFailed {
            detail: "conflict".into(),
        }
        .into();
        assert!(matches!(enrich, PipelineError::Enrich(_)));

        let persist: PipelineError = PersistError::DocIdNotResolved {
            path: "/missing".into(),
        }
        .into();
        assert!(matches!(persist, PipelineError::Persist(_)));

        let index: PipelineError = IndexError::VectorStoreFailed {
            detail: "disk full".into(),
        }
        .into();
        assert!(matches!(index, PipelineError::Index(_)));
    }
}
