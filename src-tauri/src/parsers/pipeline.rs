use serde::{Deserialize, Serialize};

use crate::commands::classifier::{classify_document, DocumentClassification};
use crate::commands::extractor::{extract_activities, extract_smiles_candidates, ActivityData};

/// Unified PDF parsing result.
#[derive(Debug, Clone, Serialize, Deserialize)]
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
    /// Parser used: "pdf_inspector", "llama_parse", "uniparser", or "mineru".
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
        "uniparser" => {
            // UniParser path — Rust native HTTP client
            let host = std::env::var("UNIPARSER_HOST")
                .unwrap_or_else(|_| "https://uniparser.dp.tech/".to_string());
            let api_key = std::env::var("UNIPARSER_API_KEY")
                .unwrap_or_default();
            if api_key.is_empty() {
                return Err("UNIPARSER_API_KEY not set".into());
            }
            let client = super::uniparser::UniParserClient::new(&host, &api_key);
            let result = client.parse_pdf(&path)?;
            (result.content, result.page_count)
        }
        "mineru" => {
            // MinerU path — Rust native HTTP client
            let host = std::env::var("MINERU_HOST")
                .unwrap_or_else(|_| "https://mineru.net".to_string());
            let api_key = std::env::var("MINERU_API_KEY")
                .unwrap_or_default();
            let client = super::mineru::MineruClient::new(&host, &api_key);
            let result = client.parse_file(&path)?;
            (result.markdown, 0)
        }
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

/// Post-process PDF extraction results using LLM.
///
/// Takes a PdfParseResult (from Stage 0-6) and uses the configured LLM to:
/// - Generate a structured summary
/// - Validate SMILES candidates (filter false positives)
/// - Extract structured activity data
/// - Identify key findings and document metadata
#[tauri::command]
pub fn post_process_pdf(
    parse_result: PdfParseResult,
) -> Result<super::post_process::PostProcessResult, String> {
    super::post_process::post_process(&parse_result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_pdf_inspector_with_real_patent() {
        let pdf_path = std::path::PathBuf::from("C:/Users/10954/Desktop/X2/US20260027089A1.PDF");

        if !pdf_path.exists() {
            eprintln!("Skipping: patent PDF not found at {:?}", pdf_path);
            return;
        }

        let result = parse_pdf(
            pdf_path.to_string_lossy().to_string(),
            Some(512),
            Some(128),
            Some("pdf_inspector".into()),
        );

        assert!(result.is_ok(), "parse_pdf failed: {:?}", result.err());
        let parsed = result.unwrap();

        // Write report to temp file so we can inspect it outside cargo test capture
        let report = format!(
            "=== PDF Parse Result ===\n\
             Parser:       {}\n\
             Pages:        {}\n\
             Content len:  {} chars\n\
             Chunks:       {}\n\
             SMILES found: {}\n\
             Activities:   {}\n\
             Classification: {:?}\n\n\
             --- Content preview (first 1500 chars) ---\n{}\n\n\
             --- First 3 chunks ---\n{}\n",
            parsed.parser,
            parsed.page_count,
            parsed.content.len(),
            parsed.chunks.len(),
            parsed.smiles.len(),
            parsed.activities.len(),
            parsed.classification,
            &parsed.content[..parsed.content.len().min(1500)],
            parsed.chunks.iter().take(3).cloned().collect::<Vec<_>>().join("\n---\n"),
        );

        let out_path = std::env::temp_dir().join("mbforge_pdf_test_report.txt");
        let _ = std::fs::write(&out_path, report);

        assert!(parsed.page_count > 0, "Expected at least 1 page");
        assert_eq!(parsed.parser, "pdf_inspector");
    }

    #[test]
    fn test_text_chunk_smoke() {
        let text = "第一章\n\n这是第一段。这是第二段。\n\n第二章\n\n更多内容在这里。".to_string();
        let result = crate::commands::text_ops::text_chunk(text, 20, 5);
        assert!(result.total_chunks > 0);
    }

    #[test]
    fn test_uniparser_client_creation() {
        let client = crate::parsers::uniparser::UniParserClient::new("https://example.com/", "test_key");
        // Just verify it doesn't panic
        let _ = client;
    }

    #[test]
    fn test_mineru_client_creation() {
        let _client = crate::parsers::mineru::MineruClient::new("https://mineru.net", "");
        // Just verify it doesn't panic (empty api_key = agent mode)
    }

    #[test]
    fn test_parse_pdf_mineru_agent_with_real_patent() {
        let pdf_path = std::path::PathBuf::from("C:/Users/10954/Desktop/X2/US20260027089A1.PDF");

        if !pdf_path.exists() {
            eprintln!("Skipping: patent PDF not found at {:?}", pdf_path);
            return;
        }

        // MinerU Agent mode (no API key required, IP rate-limited)
        let result = parse_pdf(
            pdf_path.to_string_lossy().to_string(),
            Some(512),
            Some(128),
            Some("mineru".into()),
        );

        if let Err(ref e) = result {
            let report = format!("MinerU parse failed: {}", e);
            let out_path = std::env::temp_dir().join("mbforge_mineru_test_report.txt");
            let _ = std::fs::write(&out_path, report);
            eprintln!("MinerU failed: {}", e);
            return;
        }

        let parsed = result.unwrap();

        let report = format!(
            "=== MinerU Parse Result ===\n\
             Parser:       {}\n\
             Pages:        {}\n\
             Content len:  {} chars\n\
             Chunks:       {}\n\
             SMILES found: {}\n\
             Activities:   {}\n\
             Classification: {:?}\n\n\
             --- Content preview (first 2000 chars) ---\n{}\n\n\
             --- First 3 chunks ---\n{}\n",
            parsed.parser,
            parsed.page_count,
            parsed.content.len(),
            parsed.chunks.len(),
            parsed.smiles.len(),
            parsed.activities.len(),
            parsed.classification,
            &parsed.content[..parsed.content.len().min(2000)],
            parsed.chunks.iter().take(3).cloned().collect::<Vec<_>>().join("\n---\n"),
        );

        let out_path = std::env::temp_dir().join("mbforge_mineru_test_report.txt");
        let _ = std::fs::write(&out_path, report);

        assert_eq!(parsed.parser, "mineru");
    }
}
