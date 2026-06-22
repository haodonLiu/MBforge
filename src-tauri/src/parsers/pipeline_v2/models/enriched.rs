//! Enriched document models for the PDF pipeline v2.
//!
//! This module defines the `EnrichedDocument`, which is the output of the
//! enrichment stage: structured data, SAR analysis, detected molecule results,
//! image captions, and semantic section chunks.

use std::collections::HashMap;

use crate::parsers::doc_types::StructuredData;
use crate::parsers::pipeline_v2::models::segmented::SectionChunk;

/// A document after the enrichment stage.
#[derive(Debug, Clone)]
pub struct EnrichedDocument {
    /// Structured chemical and document data extracted from the PDF.
    pub structured_data: StructuredData,
    /// Optional SAR (Structure-Activity Relationship) analysis text.
    pub sar_analysis: Option<String>,
    /// Molecules detected from molecular images in the document.
    pub molecule_results: Vec<DetectedMoleculeResult>,
    /// Mapping from image identifier to generated caption.
    pub image_captions: HashMap<String, String>,
    /// Semantic sections produced during segmentation.
    pub sections: Vec<SectionChunk>,
}

/// A molecule detected from a molecular image in a PDF.
#[derive(Debug, Clone)]
pub struct DetectedMoleculeResult {
    /// Canonical E-SMILES representation of the detected molecule.
    pub esmiles: String,
    /// Overall confidence score for the detection.
    pub confidence: f64,
    /// Confidence score from the MolDet detection model.
    pub moldet_conf: f64,
    /// One-based page number where the molecule was detected.
    pub page: usize,
    /// File system path to the cropped image used for recognition.
    pub crop_path: String,
    /// Bounding box in PDF coordinates: `[x1, y1, x2, y2]`.
    pub bbox_pdf: [f64; 4],
}
