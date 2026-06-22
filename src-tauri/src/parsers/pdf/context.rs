//! PdfInspectorContext — single-load PDF detection + extraction.
//!
//! pdf-inspector is pinned to =0.1.0, so we use its in-memory API
//! `process_pdf_mem` to load bytes once and derive both classification
//! metadata and markdown text.

use std::sync::Arc;

/// Serde adapter for `pdf_inspector::PdfType`, which does not implement
/// `Serialize` / `Deserialize` in version 0.1.0.
mod pdf_type_serde {
    use serde::{Deserialize, Deserializer, Serializer};

    pub fn serialize<S>(pdf_type: &pdf_inspector::PdfType, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let name = match pdf_type {
            pdf_inspector::PdfType::TextBased => "TextBased",
            pdf_inspector::PdfType::Scanned => "Scanned",
            pdf_inspector::PdfType::ImageBased => "ImageBased",
            pdf_inspector::PdfType::Mixed => "Mixed",
        };
        serializer.serialize_str(name)
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<pdf_inspector::PdfType, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        match value.as_str() {
            "TextBased" => Ok(pdf_inspector::PdfType::TextBased),
            "Scanned" => Ok(pdf_inspector::PdfType::Scanned),
            "ImageBased" => Ok(pdf_inspector::PdfType::ImageBased),
            "Mixed" => Ok(pdf_inspector::PdfType::Mixed),
            _ => Err(serde::de::Error::custom(format!(
                "unknown PdfType: {value}"
            ))),
        }
    }
}

/// Classification metadata produced by pdf-inspector.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct PdfClassification {
    #[serde(with = "pdf_type_serde")]
    pub pdf_type: pdf_inspector::PdfType,
    pub confidence: f32,
    pub has_complex_layout: bool,
    pub has_encoding_issues: bool,
    pub title: Option<String>,
}

/// Shared context for all pdf-inspector operations on a single document.
#[derive(Clone)]
pub struct PdfInspectorContext {
    pub(crate) bytes: Arc<[u8]>,
    pub classification: PdfClassification,
    pub markdown: String,
    pub page_count: usize,
    pub pages_needing_ocr: Vec<usize>,
}

impl PdfInspectorContext {
    /// Build from a file path. Reads the file once.
    pub async fn from_path(path: &str) -> Result<Self, String> {
        let bytes: Vec<u8> = tokio::fs::read(path)
            .await
            .map_err(|e| format!("failed to read PDF {}: {}", path, e))?;
        Self::from_arc_bytes(Arc::from(bytes)).await
    }

    /// Build from an in-memory byte slice. Calls `process_pdf_mem` once.
    pub async fn from_bytes(bytes: &[u8]) -> Result<Self, String> {
        Self::from_arc_bytes(Arc::from(bytes)).await
    }

    /// Build from an already-owned `Arc<[u8]>` buffer.
    async fn from_arc_bytes(arc_bytes: Arc<[u8]>) -> Result<Self, String> {
        let task_bytes = arc_bytes.clone();
        let result = tokio::task::spawn_blocking(move || pdf_inspector::process_pdf_mem(&task_bytes))
            .await
            .map_err(|e| format!("process_pdf_mem join error: {e}"))?
            .map_err(|e| format!("process_pdf_mem failed: {e}"))?;

        let classification = PdfClassification {
            pdf_type: result.pdf_type,
            confidence: result.confidence,
            has_complex_layout: result.layout.is_complex,
            has_encoding_issues: result.has_encoding_issues,
            title: result.title.clone(),
        };

        Ok(Self {
            bytes: arc_bytes,
            classification,
            markdown: result.markdown.unwrap_or_default(),
            page_count: result.page_count as usize,
            pages_needing_ocr: result.pages_needing_ocr.iter().map(|&p| p as usize).collect(),
        })
    }

    /// Return a read-only view of the underlying PDF bytes.
    pub fn bytes(&self) -> &[u8] {
        &self.bytes
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_context_from_empty_bytes_fails() {
        let result = PdfInspectorContext::from_bytes(b"").await;
        assert!(result.is_err());
    }

    #[test]
    fn test_pdf_classification_round_trip() {
        let original = PdfClassification {
            pdf_type: pdf_inspector::PdfType::TextBased,
            confidence: 0.95,
            has_complex_layout: true,
            has_encoding_issues: false,
            title: Some("dummy title".to_string()),
        };

        let json = serde_json::to_string(&original).expect("serialize");
        let deserialized: PdfClassification = serde_json::from_str(&json).expect("deserialize");

        assert_eq!(deserialized, original);
    }
}
