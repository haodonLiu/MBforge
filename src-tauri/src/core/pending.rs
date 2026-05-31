use crate::core::constants::PROJECT_META_DIR;
use crate::core::types::ExtractionResult;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// Container for pending extractions serialized to disk.
#[derive(Debug, Serialize, Deserialize)]
struct PendingContainer {
    doc_id: String,
    results: Vec<ExtractionResult>,
}

/// Build the pending.json path for a given project and doc_id.
///
/// Pattern: `{project_root}/.mbforge/extractions/{doc_id}/pending.json`
///
/// Port of `PDFParserPipeline._pending_extractions_path` from
/// `src/mbforge/parsers/pdf_parser.py`.
pub fn pending_path(project_root: &Path, doc_id: &str) -> PathBuf {
    project_root
        .join(PROJECT_META_DIR)
        .join("extractions")
        .join(doc_id)
        .join("pending.json")
}

/// Save pending extraction results to disk.
///
/// Port of `PDFParserPipeline._save_pending_extractions` from
/// `src/mbforge/parsers/pdf_parser.py`.
pub fn save_pending(
    project_root: &Path,
    doc_id: &str,
    results: &[ExtractionResult],
) -> std::io::Result<()> {
    let path = pending_path(project_root, doc_id);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }

    let container = PendingContainer {
        doc_id: doc_id.to_string(),
        results: results.to_vec(),
    };

    let json = serde_json::to_string_pretty(&container)?;
    std::fs::write(path, json)
}

/// Load pending extraction results from disk.
///
/// Returns an empty vec if the file doesn't exist or fails to parse.
///
/// Port of `PDFParserPipeline.load_pending_extractions` from
/// `src/mbforge/parsers/pdf_parser.py`.
pub fn load_pending(project_root: &Path, doc_id: &str) -> Vec<ExtractionResult> {
    let path = pending_path(project_root, doc_id);
    if !path.exists() {
        return Vec::new();
    }

    match std::fs::read_to_string(&path) {
        Ok(content) => {
            match serde_json::from_str::<PendingContainer>(&content) {
                Ok(container) => container.results,
                Err(_) => Vec::new(),
            }
        }
        Err(_) => Vec::new(),
    }
}

/// Delete pending extractions for a given doc_id.
pub fn delete_pending(project_root: &Path, doc_id: &str) -> std::io::Result<()> {
    let dir = pending_path(project_root, doc_id);
    // Remove the pending.json file
    if dir.exists() {
        std::fs::remove_file(&dir)?;
    }
    // Remove the parent directory if empty
    if let Some(parent) = dir.parent() {
        let _ = std::fs::remove_dir(parent);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn make_result(name: &str, context: &str) -> ExtractionResult {
        ExtractionResult {
            name: name.to_string(),
            context_text: context.to_string(),
            properties: serde_json::json!({}),
            esmiles: String::new(),
            source: "image".into(),
            moldet_conf: 0.0,
            scribe_conf: 0.0,
            composite_conf: 0.0,
            bbox_pdf: None,
            page_idx: None,
            mol_img_path: None,
            status: "pending".into(),
        }
    }

    #[test]
    fn test_save_and_load_pending() {
        let tmp = TempDir::new().unwrap();
        let results = vec![
            make_result("Compound 1", "IC50 = 5.2 nM"),
            make_result("Compound 2", "EC50 = 10 µM"),
        ];

        save_pending(tmp.path(), "test-doc", &results).unwrap();

        let loaded = load_pending(tmp.path(), "test-doc");
        assert_eq!(loaded.len(), 2);
        assert_eq!(loaded[0].name, "Compound 1");
        assert_eq!(loaded[1].context_text, "EC50 = 10 µM");
    }

    #[test]
    fn test_load_pending_nonexistent() {
        let tmp = TempDir::new().unwrap();
        let loaded = load_pending(tmp.path(), "nonexistent");
        assert!(loaded.is_empty());
    }

    #[test]
    fn test_delete_pending() {
        let tmp = TempDir::new().unwrap();
        let results = vec![make_result("Test", "context")];
        save_pending(tmp.path(), "del-doc", &results).unwrap();
        assert!(!load_pending(tmp.path(), "del-doc").is_empty());
        delete_pending(tmp.path(), "del-doc").unwrap();
        assert!(load_pending(tmp.path(), "del-doc").is_empty());
    }

    #[test]
    fn test_pending_path_format() {
        let path = pending_path(Path::new("/project"), "doc-123");
        assert!(path.ends_with(".mbforge\\extractions\\doc-123\\pending.json")
            || path.ends_with(".mbforge/extractions/doc-123/pending.json"));
    }

    #[test]
    fn test_save_empty_list() {
        let tmp = TempDir::new().unwrap();
        save_pending(tmp.path(), "empty", &[]).unwrap();
        let loaded = load_pending(tmp.path(), "empty");
        assert!(loaded.is_empty());
    }
}
