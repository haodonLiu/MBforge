// PDF inspection commands — Task 2: classify_pdf

use serde::Serialize;

/// Classification result returned to the frontend via Tauri IPC.
///
/// This struct is intentionally kept lean — it carries only the fields
/// the frontend needs for routing (text vs scanned vs mixed) and for
/// displaying a progress / quality indicator.
#[derive(Debug, Serialize)]
pub struct PdfClassification {
    /// PDF type: "TextBased", "Scanned", "Mixed", or "ImageBased".
    pub pdf_type: String,
    /// Detection confidence (0.0–1.0).
    pub confidence: f64,
    /// Total number of pages.
    pub page_count: usize,
    /// 1-indexed page numbers that need OCR.
    pub pages_needing_ocr: Vec<usize>,
    /// Average text density across all pages (characters per square point).
    /// `0.0` when text extraction was not performed (detect-only mode).
    pub text_density_avg: f64,
    /// Whether any page has tables or multi-column layout.
    pub has_complex_layout: bool,
    /// `true` when broken font encodings are detected (garbled text).
    pub has_encoding_issues: bool,
    /// Title from PDF metadata (if available).
    pub title: Option<String>,
}

/// Tauri command: classify a PDF without full text extraction.
///
/// Uses `pdf_inspector::detect_pdf` (ProcessMode::DetectOnly) for fast
/// classification (~10–50ms).  The returned `PdfClassification` contains
/// the PDF type, per-page OCR needs, and layout / encoding diagnostics
/// that the frontend can surface to the user.
#[tauri::command]
pub fn classify_pdf(path: String) -> Result<PdfClassification, String> {
    let result = pdf_inspector::detect_pdf(&path).map_err(|e| {
        log::error!("classify_pdf failed for path={}: {}", path, e);
        format!("pdf-inspector detect failed: {}", e)
    })?;

    let pdf_type = match result.pdf_type {
        pdf_inspector::PdfType::TextBased => "TextBased",
        pdf_inspector::PdfType::Scanned => "Scanned",
        pdf_inspector::PdfType::Mixed => "Mixed",
        pdf_inspector::PdfType::ImageBased => "ImageBased",
    };

    log::info!(
        "classify_pdf: path={} type={} pages={} ocr={:?}",
        path,
        pdf_type,
        result.page_count,
        result.pages_needing_ocr
    );

    Ok(PdfClassification {
        pdf_type: pdf_type.to_string(),
        confidence: result.confidence as f64,
        page_count: result.page_count as usize,
        pages_needing_ocr: result
            .pages_needing_ocr
            .iter()
            .map(|&p| p as usize)
            .collect(),
        // text_density_avg requires full text extraction (ProcessMode::Full);
        // detect-only mode does not extract text, so this is 0.0 here.
        // The Python pipeline can compute a real value when it runs full extraction.
        text_density_avg: 0.0,
        has_complex_layout: result.layout.is_complex,
        has_encoding_issues: result.has_encoding_issues,
        title: result.title,
    })
}

// =========================================================================
// Task 3: extract_text
// =========================================================================

/// Extraction result returned to the frontend via Tauri IPC.
#[derive(Debug, Serialize)]
pub struct PdfExtraction {
    /// Structured Markdown output (headings, tables, lists).
    pub markdown: String,
    /// Total page count.
    pub page_count: usize,
    /// 1-indexed page numbers that need OCR.
    pub pages_needing_ocr: Vec<usize>,
    /// Detection confidence (0.0–1.0).
    pub confidence: f32,
    /// Whether any page has tables or multi-column layout.
    pub has_complex_layout: bool,
    /// `true` when broken font encodings are detected.
    pub has_encoding_issues: bool,
}

/// Tauri command: extract structured Markdown from a PDF.
///
/// Uses `pdf_inspector::process_pdf` (ProcessMode::Full) for complete
/// extraction including text, tables, and layout detection.
#[tauri::command]
pub fn extract_text(path: String) -> Result<PdfExtraction, String> {
    let result = pdf_inspector::process_pdf(&path).map_err(|e| {
        log::error!("extract_text failed for path={}: {}", path, e);
        format!("pdf-inspector process failed: {}", e)
    })?;

    log::info!(
        "extract_text: path={} pages={} ocr={:?}",
        path,
        result.page_count,
        result.pages_needing_ocr
    );

    Ok(PdfExtraction {
        markdown: result.markdown.unwrap_or_default(),
        page_count: result.page_count as usize,
        pages_needing_ocr: result
            .pages_needing_ocr
            .iter()
            .map(|&p| p as usize)
            .collect(),
        confidence: result.confidence,
        has_complex_layout: result.layout.is_complex,
        has_encoding_issues: result.has_encoding_issues,
    })
}
