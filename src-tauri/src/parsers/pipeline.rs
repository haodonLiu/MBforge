use serde::Serialize;
use std::path::PathBuf;

use crate::commands::classifier::{classify_document, DocumentClassification};
use crate::commands::extractor::{extract_activities, extract_smiles_candidates, ActivityData};

/// Unified PDF parsing result.
#[derive(Debug, Serialize)]
pub struct PdfParseResult {
    /// Extracted text/markdown content.
    pub content: String,
    /// Classification result.
    pub classification: DocumentClassification,
    /// Chunks after splitting.
    pub chunks: Vec<String>,
    /// Extracted SMILES candidates.
    pub smiles: Vec<String>,
    /// Extracted activity data.
    pub activities: Vec<ActivityData>,
    /// Parser used: "pdf_inspector", "llama_parse", or "pymupdf".
    pub parser: String,
    /// Page count.
    pub page_count: usize,
}

/// Parse a PDF using the full pipeline.
///
/// This chains: extraction → classification → chunking → molecule extraction.
#[tauri::command]
pub fn parse_pdf(
    path: String,
    chunk_size: Option<usize>,
    overlap: Option<usize>,
    parser: Option<String>,
) -> Result<PdfParseResult, String> {
    let chunk_size = chunk_size.unwrap_or(512);
    let overlap = overlap.unwrap_or(128);
    let parser_choice = parser.unwrap_or_else(|| "pdf_inspector".to_string());

    // Stage 1: Text extraction
    let (content, page_count) = match parser_choice.as_str() {
        "llama_parse" => {
            // LlamaParse path — read file and call Python sidecar
            let pdf_bytes = std::fs::read(&path)
                .map_err(|e| format!("Failed to read PDF: {}", e))?;
            let result = super::llama_parse::parse_with_llamaparse_sync(
                "http://127.0.0.1:18792",
                pdf_bytes,
                None,
            )?;
            (result.markdown, result.page_count)
        }
        _ => {
            // pdf-inspector path (default)
            let result = pdf_inspector::process_pdf(&path)
                .map_err(|e| format!("pdf-inspector failed: {}", e))?;
            let md = result.markdown.unwrap_or_default();
            (md, result.page_count as usize)
        }
    };

    // Stage 2: Classification
    let pages: Vec<String> = content
        .split("\n\n")
        .map(|s| s.to_string())
        .collect();
    let classification = classify_document(pages, None);

    // Stage 3: Chunking
    let chunks = crate::commands::text_ops::text_chunk(content.clone(), chunk_size, overlap)
        .chunks;

    // Stage 4: Molecule extraction (text regex)
    let smiles = extract_smiles_candidates(content.clone());
    let activities = extract_activities(content.clone());

    Ok(PdfParseResult {
        content,
        classification,
        chunks,
        smiles,
        activities,
        parser: parser_choice,
        page_count,
    })
}
