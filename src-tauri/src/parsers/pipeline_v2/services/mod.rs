//! Pipeline services.

/// Persistent JSON file cache.
pub mod cache;
/// VLM image captioning.
pub mod captions;
/// Chemical structure validation.
pub mod chem_validate;
/// Embedded image extraction and persistence.
pub mod images;
/// PDF metadata inspection.
pub mod inspector;
/// Structured data merging and SAR analysis.
pub mod merge;
/// Molecule detection and recognition.
pub mod molecules;
/// OCR backend orchestration.
pub mod ocr;
/// Section LLM post-processing.
pub mod section_processor;
/// Source path and project root resolution.
pub mod source;
