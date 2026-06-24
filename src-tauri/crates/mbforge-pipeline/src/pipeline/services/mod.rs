//! Pipeline services.

/// Persistent JSON file cache.
pub mod cache;
/// VLM image captioning.
pub mod captions;
/// Chemical structure validation.
pub mod chem_validate;
/// Coref 持久化（molecule ↔ label 配对写入 KB）
pub mod coref_persist;
/// Helpers for mapping extracted entries to molecule records.
pub mod helpers;
/// Embedded image extraction and persistence.
pub mod images;
/// PDF metadata inspection.
pub mod inspector;
/// Structured data merging and SAR analysis.
pub mod merge;
/// Persists extracted molecules to the molecule store.
pub mod molecule_store;
/// Molecule detection and recognition.
pub mod molecules;
/// OCR backend orchestration.
pub mod ocr;
/// OCR layout block extraction.
pub mod ocr_layout;
/// Quick page-level MoldDet scan (bbox only).
pub mod quick_moldet;
/// Section LLM post-processing.
pub mod section_processor;
/// Source path and project root resolution.
pub mod source;
