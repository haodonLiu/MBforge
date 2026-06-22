//! Pipeline v2 stage implementations.

/// Enriches sections with molecules, captions, and structured data.
pub mod enrich;
/// Extracts raw text, images, and OCR output from a source document.
pub mod extract;
/// Indexes persisted document sections into the vector store and FTS5 index.
pub mod index;
/// Persists enriched documents to text.md, report.md, and the molecule store.
pub mod persist;
/// Segments extracted text into sections and a document tree.
pub mod segment;
