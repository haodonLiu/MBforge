//! Persisted document models for the PDF pipeline v2.
//!
//! This module defines the `PersistedDocument` and `IndexedDocument`, which
//! represent the outputs of the persistence and indexing stages respectively.

use std::path::PathBuf;

/// A document after it has been persisted to disk.
#[derive(Debug, Clone)]
pub struct PersistedDocument {
    /// Unique document identifier.
    pub doc_id: String,
    /// Path to the extracted Markdown text file.
    pub text_md_path: PathBuf,
    /// Path to the generated report Markdown file.
    pub report_md_path: PathBuf,
    /// Number of molecular images that still require verification.
    pub unverified_image_count: usize,
    /// Number of molecules persisted to the molecule store.
    pub persisted_molecule_count: usize,
}

/// A document after its sections have been indexed for search.
#[derive(Debug, Clone)]
pub struct IndexedDocument {
    /// Unique document identifier.
    pub doc_id: String,
    /// Number of section chunks indexed into the vector store.
    pub indexed_sections: usize,
}
