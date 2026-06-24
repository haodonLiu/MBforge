#![allow(dead_code)]
use mbforge_infra::config::constants::{INDEX_DIR, SUMMARY_DIR};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// Three-layer document summary (L0/L1/L2).
///
/// - L0 Abstract:   ~100 tokens, one-sentence summary for fast filtering
/// - L1 Overview:   ~2000 tokens, structured overview for Rerank
/// - L2 Detail:     full content, loaded on demand
///
/// Port of `DocumentSummary` from
/// `src/mbforge/core/summarizer.py`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentSummary {
    pub doc_id: String,
    #[serde(default)]
    pub l0_abstract: String,
    #[serde(default)]
    pub l1_overview: String,
    #[serde(default)]
    pub l2_detail_hint: String,
    #[serde(default)]
    pub keywords: Vec<String>,
    #[serde(default)]
    pub entity_tags: Vec<String>,
}

impl DocumentSummary {
    pub fn new(doc_id: &str) -> Self {
        Self {
            doc_id: doc_id.to_string(),
            l0_abstract: String::new(),
            l1_overview: String::new(),
            l2_detail_hint: String::new(),
            keywords: Vec::new(),
            entity_tags: Vec::new(),
        }
    }
}

/// Project-level summary manager.
///
/// Stores summaries under `{project_root}/index/summaries/{doc_id}.json`.
///
/// Port of `SummaryManager` from
/// `src/mbforge/core/summarizer.py`.
pub struct SummaryManager {
    summary_dir: PathBuf,
}

impl SummaryManager {
    /// Create a new SummaryManager for the given project root.
    ///
    /// Creates the summary directory if it doesn't exist.
    pub fn new(project_root: &Path) -> std::io::Result<Self> {
        let summary_dir = project_root.join(INDEX_DIR).join(SUMMARY_DIR);
        std::fs::create_dir_all(&summary_dir)?;
        Ok(Self { summary_dir })
    }

    /// Get the file path for a given doc_id.
    fn summary_path(&self, doc_id: &str) -> PathBuf {
        self.summary_dir.join(format!("{}.json", doc_id))
    }

    /// Save a document summary to disk.
    pub fn save(&self, summary: &DocumentSummary) -> std::io::Result<()> {
        let path = self.summary_path(&summary.doc_id);
        let json = serde_json::to_string_pretty(summary)?;
        std::fs::write(path, json)
    }

    /// Load a document summary from disk.
    ///
    /// Returns `None` if the file doesn't exist or fails to parse.
    pub fn load(&self, doc_id: &str) -> Option<DocumentSummary> {
        let path = self.summary_path(doc_id);
        if !path.exists() {
            return None;
        }
        match std::fs::read_to_string(&path) {
            Ok(content) => serde_json::from_str(&content).ok(),
            Err(_) => None,
        }
    }

    /// Delete a document summary from disk.
    pub fn delete(&self, doc_id: &str) -> std::io::Result<()> {
        let path = self.summary_path(doc_id);
        if path.exists() {
            std::fs::remove_file(path)
        } else {
            Ok(())
        }
    }

    /// List all document summaries.
    ///
    /// Silently skips files that fail to parse.
    pub fn list_all(&self) -> Vec<DocumentSummary> {
        // 单层：只取 `summary_dir` 的直接子项（.json 文件）。`min_depth(1)` 跳过目录自身。
        walkdir::WalkDir::new(&self.summary_dir)
            .min_depth(1)
            .max_depth(1)
            .into_iter()
            .filter_map(|e| e.ok())
            .filter(|e| e.path().extension().and_then(|x| x.to_str()) == Some("json"))
            .filter_map(|e| std::fs::read_to_string(e.path()).ok())
            .filter_map(|content| serde_json::from_str::<DocumentSummary>(&content).ok())
            .collect()
    }

    /// Return the summary directory path (useful for debugging).
    pub fn dir(&self) -> &Path {
        &self.summary_dir
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_summary_roundtrip() {
        let tmp = TempDir::new().unwrap();
        let mgr = SummaryManager::new(tmp.path()).unwrap();

        let summary = DocumentSummary {
            doc_id: "test-123".to_string(),
            l0_abstract: "A one-sentence summary.".to_string(),
            l1_overview: "Structured overview content.".to_string(),
            l2_detail_hint: "Full text: 5000 chars".to_string(),
            keywords: vec!["docking".to_string(), "kinase".to_string()],
            entity_tags: vec!["EGFR".to_string()],
        };

        mgr.save(&summary).unwrap();

        let loaded = mgr.load("test-123").unwrap();
        assert_eq!(loaded.doc_id, "test-123");
        assert_eq!(loaded.l0_abstract, "A one-sentence summary.");
        assert_eq!(loaded.keywords, vec!["docking", "kinase"]);
        assert_eq!(loaded.entity_tags, vec!["EGFR"]);
    }

    #[test]
    fn test_summary_load_nonexistent() {
        let tmp = TempDir::new().unwrap();
        let mgr = SummaryManager::new(tmp.path()).unwrap();
        assert!(mgr.load("nonexistent").is_none());
    }

    #[test]
    fn test_summary_delete() {
        let tmp = TempDir::new().unwrap();
        let mgr = SummaryManager::new(tmp.path()).unwrap();
        let summary = DocumentSummary::new("del-me");
        mgr.save(&summary).unwrap();
        assert!(mgr.load("del-me").is_some());
        mgr.delete("del-me").unwrap();
        assert!(mgr.load("del-me").is_none());
    }

    #[test]
    fn test_summary_list_all() {
        let tmp = TempDir::new().unwrap();
        let mgr = SummaryManager::new(tmp.path()).unwrap();

        mgr.save(&DocumentSummary::new("a")).unwrap();
        mgr.save(&DocumentSummary::new("b")).unwrap();
        mgr.save(&DocumentSummary::new("c")).unwrap();

        let all = mgr.list_all();
        assert_eq!(all.len(), 3);
        let ids: std::collections::HashSet<String> = all.into_iter().map(|s| s.doc_id).collect();
        assert!(ids.contains("a"));
        assert!(ids.contains("b"));
        assert!(ids.contains("c"));
    }

    #[test]
    fn test_summary_defaults() {
        let s = DocumentSummary::new("defaults");
        assert_eq!(s.l0_abstract, "");
        assert!(s.keywords.is_empty());
    }
}
