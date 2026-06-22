//! Raw extraction results produced by parser and OCR backends.

use serde::{Deserialize, Serialize};

/// The top-level document produced by the extraction stage.
///
/// This structure aggregates raw text, page-level images, OCR blocks and
/// lightweight bibliographic metadata returned by a parser backend.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractedDocument {
    /// Plain text extracted from the document, in reading order.
    pub raw_text: String,

    /// Total number of pages in the source document.
    pub page_count: usize,

    /// Name or identifier of the parser backend that produced this document.
    pub parser: String,

    /// Images discovered during extraction, typically molecule figures or schemes.
    pub images: Vec<ImageRef>,

    /// OCR text blocks, including their geometry and classification.
    pub ocr_blocks: Vec<OcrBlock>,

    /// Optional bibliographic and classification metadata.
    pub metadata: ExtractedMetadata,
}

/// Optional metadata attached to an extracted document.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ExtractedMetadata {
    /// Document title, if available.
    pub title: Option<String>,

    /// Document authors, in natural order.
    pub authors: Vec<String>,

    /// High-level document type, e.g. "patent" or "journal_article".
    pub document_type: Option<String>,
}

/// Reference to an image discovered during document extraction.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ImageRef {
    /// Stable filename for the extracted image.
    pub filename: String,

    /// One-based page number where the image appears.
    pub page: usize,

    /// Optional region identifier or crop description.
    pub region: Option<String>,

    /// Optional human-readable description or caption fragment.
    pub description: Option<String>,

    /// Optional E-SMILES string if the image was resolved to a chemical structure.
    pub esmiles: Option<String>,

    /// Optional path relative to the project output directory.
    pub rel_path: Option<String>,
}

/// A single OCR-detected text block with geometry and orientation.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OcrBlock {
    /// One-based page number where the block appears.
    pub page: usize,

    /// Block classification, e.g. "text", "table", "heading".
    pub block_type: String,

    /// Bounding box in the form `[x1, y1, x2, y2]`.
    pub bbox: [f64; 4],

    /// Recognized text content, if any.
    pub content: Option<String>,

    /// Ordinal index of this block within the page.
    pub index: usize,

    /// Detected rotation angle of the block in degrees.
    pub angle: i32,
}
