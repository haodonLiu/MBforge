//! OCR backend helpers for scanned PDFs.
//!
//! Each backend exposes a plain async `run` function returning
//! [`OcrOutput`]. The fallback chain in `classify_and_extract`
//! branches on env-var presence + backend availability before calling
//! each `run`.
//!
//! Scanned PDFs fall back to pdf-inspector text when no cloud OCR
//! backend is available.
//!
//! Status:
//! - MinerU: real impl in `parsers/pdf/mineru.rs` (re-exported here)
//! - Uniparser online: real impl (markdown only)
//! - PaddleOCR online: real impl
//! - PaddleOCR local: stub, returns `not_implemented`

pub mod backend;
pub mod mineru;
pub mod paddle;
pub mod uniparser;

pub use backend::OcrOutput;


