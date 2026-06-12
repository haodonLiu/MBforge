#![allow(dead_code)]
//! Per-PDF page-level molecule detection cache.
//!
//! Layout (new DocumentProject layout):
//!   `projects/<doc_id>/cache/detections/page_<N>.json`
//!
//! Legacy layout (v1 projects):
//!   `index/detections/<doc_id>/page_<N>.json`
//!
//! Each file holds the FULL raw output of one detection pass on one page:
//! bounding boxes, SMILES, eSMILES, MolDet/MolScribe confidences, optional
//! VLM caption + eSMILES, and the relative path to the cropped figure image.
//!
//! **What is NOT cached:** `context_text` (the PDF text inside the bbox).
//! It can be re-extracted cheaply at lookup time from
//! `projects/<doc_id>/cache/pages/page_<N>.txt` by the caller. This keeps the
//! cache ~50% smaller.
//!
//! **Invalidation:** every entry records the SHA-256 of the source PDF.
//! On lookup the caller passes the current hash; a mismatch returns `None`
//! and the caller falls back to re-running detection.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

use crate::core::config::constants::{INDEX_DIR, PROJECTS_DIR};
use crate::core::error::AppResult;

/// One molecule detected on one page of one PDF.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Detection {
    /// Bounding box in PDF coordinates: [x0, y0, x1, y1].
    pub bbox_pdf: [f64; 4],
    /// Canonical SMILES (clean, no semantic tags). `None` for quick-scan bbox-only entries.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub smiles: Option<String>,
    /// E-SMILES (with semantic tags). `None` for quick-scan bbox-only entries.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub esmiles: Option<String>,
    /// MolDet (object detection) confidence, 0.0 - 1.0.
    pub conf_moldet: f64,
    /// MolScribe (structure recognition) confidence, 0.0 - 1.0.
    pub conf_molscribe: f64,
    /// VLM-generated image caption. `None` if VLM was not run for this page.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub vlm_caption: Option<String>,
    /// VLM-verified eSMILES (often equals `esmiles`; differs when VLM corrected).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub vlm_esmiles: Option<String>,
    /// Path to the cropped figure image, relative to the project root.
    /// e.g. `"reports/figures/us/page_003_mol_002.png"`.
    /// `None` for quick-scan bbox-only entries.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub crop_relpath: Option<String>,
    /// Whether this detection only contains a bbox from a quick MoldDet scan.
    /// Full MolScribe results set this to `false`.
    #[serde(default)]
    pub is_quick_scan: bool,
}

impl Detection {
    /// Returns true if this detection contains a recognized structure (SMILES).
    pub fn has_structure(&self) -> bool {
        self.smiles.as_deref().map(|s| !s.is_empty()).unwrap_or(false)
            || self.esmiles.as_deref().map(|s| !s.is_empty()).unwrap_or(false)
    }
}

/// All detections for one page of one PDF.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PageDetection {
    /// Document UUID (matches `DocumentEntry.doc_id` in `index.json`).
    pub doc_id: String,
    /// 1-indexed page number.
    pub page: usize,
    /// SHA-256 of the source PDF at the time of detection. Used for
    /// invalidation: a hash mismatch at lookup time means the PDF has
    /// changed and the cache entry is stale.
    pub pdf_hash: String,
    /// Source PDF mtime (unix seconds). Diagnostic only — `pdf_hash`
    /// is the authoritative invalidator.
    pub mtime: f64,
    /// When the detection was run (unix seconds).
    pub detected_at: f64,
    /// Schema version of this cache entry. Bump if the on-disk format
    /// changes in a non-backwards-compatible way.
    pub schema_version: u32,
    /// All molecules detected on this page.
    pub detections: Vec<Detection>,
}

pub const DETECTION_CACHE_SCHEMA_VERSION: u32 = 1;

/// Read/write access to the per-PDF detection cache.
pub struct DetectionCache {
    project_root: PathBuf,
}

impl DetectionCache {
    /// Legacy constructor using the global `index/detections` path.
    ///
    /// Kept for backwards compatibility with v1 projects where PDFs live in
    /// `papers/<doc_slug>.pdf` and caches are shared under `index/`.
    pub fn new(project_root: &Path) -> Self {
        Self {
            project_root: project_root.to_path_buf(),
        }
    }

    /// Constructor for the new DocumentProject layout.
    ///
    /// Cache base directory is `projects/<doc_id>/cache/detections`.
    pub fn for_document_project(project_root: &Path, doc_id: &str) -> Self {
        Self {
            project_root: project_root.join(PROJECTS_DIR).join(doc_id),
        }
    }

    fn base_dir(&self) -> PathBuf {
        // If the cached root already looks like a DocumentProject directory
        // (i.e. ends with projects/<doc_id>), store detections under
        // `cache/detections`. Otherwise use the legacy `index/detections`
        // path for backwards compatibility.
        let tail = self.project_root.iter().rev().take(2).collect::<Vec<_>>();
        if tail.len() == 2
            && tail[1].to_string_lossy() == PROJECTS_DIR
            && !tail[0].to_string_lossy().is_empty()
        {
            self.project_root.join("cache").join("detections")
        } else {
            self.project_root.join(INDEX_DIR).join("detections")
        }
    }

    fn page_path(&self, doc_id: &str, page: usize) -> PathBuf {
        self.base_dir()
            .join(doc_id)
            .join(format!("page_{:04}.json", page))
    }

    /// Look up the cached detections for a page.
    ///
    /// Returns `None` when:
    /// - the file does not exist
    /// - the file is not valid JSON
    /// - the entry's `pdf_hash` does not match `expected_pdf_hash`
    ///   (i.e. the PDF has changed since the cache was written)
    pub fn get(
        &self,
        doc_id: &str,
        page: usize,
        expected_pdf_hash: &str,
    ) -> Option<PageDetection> {
        let path = self.page_path(doc_id, page);
        let text = std::fs::read_to_string(&path).ok()?;
        let entry: PageDetection = match serde_json::from_str(&text) {
            Ok(e) => e,
            Err(err) => {
                log::warn!(
                    "DetectionCache: corrupt entry at {} ({}); will be regenerated",
                    path.display(),
                    err
                );
                return None;
            }
        };
        if entry.pdf_hash != expected_pdf_hash {
            log::debug!(
                "DetectionCache: hash mismatch for {} page {} (cached={}, expected={})",
                doc_id,
                page,
                &entry.pdf_hash[..8.min(entry.pdf_hash.len())],
                &expected_pdf_hash[..8.min(expected_pdf_hash.len())]
            );
            return None;
        }
        Some(entry)
    }

    /// Persist a page's detection results. Atomic write: temp + rename.
    ///
    /// Write policy:
    /// - A quick-scan entry never overwrites a full entry that already has
    ///   recognized structures (SMILES/eSMILES).
    /// - A full entry always overwrites an older entry of any kind.
    pub fn put(&self, entry: &PageDetection) -> AppResult<()> {
        let path = self.page_path(&entry.doc_id, entry.page);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        // If this is a quick-scan, check whether a full result already exists.
        if entry.detections.iter().all(|d| d.is_quick_scan) {
            if let Ok(text) = std::fs::read_to_string(&path) {
                if let Ok(existing) = serde_json::from_str::<PageDetection>(&text) {
                    let has_full = existing
                        .detections
                        .iter()
                        .any(|d| !d.is_quick_scan && d.has_structure());
                    if has_full {
                        log::debug!(
                            "DetectionCache: skip quick-scan overwrite for {} page {}",
                            entry.doc_id,
                            entry.page
                        );
                        return Ok(());
                    }
                }
            }
        }

        let json = serde_json::to_string_pretty(entry)?;
        crate::core::helpers::atomic_write(&path, json.as_bytes())?;
        Ok(())
    }

    /// Delete all cached detections for a single document.
    pub fn clear_doc(&self, doc_id: &str) -> AppResult<()> {
        let dir = self.base_dir().join(doc_id);
        if dir.exists() {
            std::fs::remove_dir_all(&dir)?;
        }
        Ok(())
    }

    /// Delete ALL cached detections in the project. Used by the
    /// "清空检测缓存" button in Settings.
    pub fn clear_all(&self) -> AppResult<()> {
        let base = self.base_dir();
        if base.exists() {
            std::fs::remove_dir_all(&base)?;
        }
        Ok(())
    }

    /// Total disk usage in bytes (sum of all detection JSON files).
    pub fn disk_usage_bytes(&self) -> u64 {
        walk_size(&self.base_dir())
    }

    /// Number of cached pages.
    pub fn cached_page_count(&self) -> usize {
        count_pages(&self.base_dir())
    }
}

/// Compute SHA-256 of a file's contents, returned as a lowercase hex string.
pub fn pdf_hash(path: &Path) -> Option<String> {
    let bytes = std::fs::read(path).ok()?;
    Some(sha256_hex(&bytes))
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hasher
        .finalize()
        .iter()
        .map(|b| format!("{:02x}", b))
        .collect()
}

fn walk_size(dir: &Path) -> u64 {
    walkdir::WalkDir::new(dir)
        .follow_links(false)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().is_file())
        .filter_map(|e| e.metadata().ok().map(|m| m.len()))
        .sum()
}

fn count_pages(dir: &Path) -> usize {
    walkdir::WalkDir::new(dir)
        .follow_links(false)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().is_file())
        .filter(|e| e.path().extension().and_then(|x| x.to_str()) == Some("json"))
        .count()
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn sample_entry(doc_id: &str, page: usize, hash: &str) -> PageDetection {
        PageDetection {
            doc_id: doc_id.to_string(),
            page,
            pdf_hash: hash.to_string(),
            mtime: 1.7e9,
            detected_at: 1.7e9,
            schema_version: DETECTION_CACHE_SCHEMA_VERSION,
            detections: vec![Detection {
                bbox_pdf: [10.0, 20.0, 110.0, 120.0],
                smiles: Some("CCO".to_string()),
                esmiles: Some("<a>C:ALK</a>CCO".to_string()),
                conf_moldet: 0.95,
                conf_molscribe: 0.88,
                vlm_caption: Some("Ethanol molecule diagram".to_string()),
                vlm_esmiles: None,
                crop_relpath: Some("reports/figures/x/page_001_mol_000.png".to_string()),
                is_quick_scan: false,
            }],
        }
    }

    #[test]
    fn put_get_round_trip() {
        let tmp = TempDir::new().unwrap();
        let cache = DetectionCache::new(tmp.path());
        let entry = sample_entry("doc-1", 3, "abc123");
        cache.put(&entry).unwrap();

        let loaded = cache.get("doc-1", 3, "abc123").expect("must hit");
        assert_eq!(loaded.doc_id, "doc-1");
        assert_eq!(loaded.page, 3);
        assert_eq!(loaded.detections.len(), 1);
        assert_eq!(loaded.detections[0].smiles.as_deref(), Some("CCO"));
        assert_eq!(loaded.detections[0].vlm_caption.as_deref(), Some("Ethanol molecule diagram"));
    }

    #[test]
    fn hash_mismatch_returns_none() {
        let tmp = TempDir::new().unwrap();
        let cache = DetectionCache::new(tmp.path());
        cache.put(&sample_entry("doc-2", 5, "old-hash")).unwrap();

        // Same page, different PDF hash → cache miss
        assert!(cache.get("doc-2", 5, "new-hash").is_none());
        // Original hash still hits
        assert!(cache.get("doc-2", 5, "old-hash").is_some());
    }

    #[test]
    fn clear_doc_removes_only_that_doc() {
        let tmp = TempDir::new().unwrap();
        let cache = DetectionCache::new(tmp.path());
        cache.put(&sample_entry("doc-a", 1, "h")).unwrap();
        cache.put(&sample_entry("doc-b", 1, "h")).unwrap();
        assert_eq!(cache.cached_page_count(), 2);

        cache.clear_doc("doc-a").unwrap();
        assert!(cache.get("doc-a", 1, "h").is_none());
        assert!(cache.get("doc-b", 1, "h").is_some());
    }

    #[test]
    fn clear_all_removes_everything() {
        let tmp = TempDir::new().unwrap();
        let cache = DetectionCache::new(tmp.path());
        cache.put(&sample_entry("a", 1, "h")).unwrap();
        cache.put(&sample_entry("b", 2, "h")).unwrap();
        assert!(cache.disk_usage_bytes() > 0);

        cache.clear_all().unwrap();
        assert_eq!(cache.disk_usage_bytes(), 0);
    }

    #[test]
    fn corrupted_json_returns_none() {
        let tmp = TempDir::new().unwrap();
        let cache = DetectionCache::new(tmp.path());
        let path = tmp.path().join(INDEX_DIR).join("detections").join("doc-x").join("page_0001.json");
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, "{ this is not valid json").unwrap();
        assert!(cache.get("doc-x", 1, "any").is_none());
    }

    #[test]
    fn disk_usage_tracks_writes() {
        let tmp = TempDir::new().unwrap();
        let cache = DetectionCache::new(tmp.path());
        let before = cache.disk_usage_bytes();
        cache.put(&sample_entry("size-test", 1, "h")).unwrap();
        let after = cache.disk_usage_bytes();
        assert!(after > before, "disk usage should grow after put");
    }

    #[test]
    fn for_document_project_uses_project_cache_dir() {
        let tmp = TempDir::new().unwrap();
        let cache = DetectionCache::for_document_project(tmp.path(), "doc-1");
        let entry = sample_entry("doc-1", 3, "abc123");
        cache.put(&entry).unwrap();

        let expected_path = tmp
            .path()
            .join(PROJECTS_DIR)
            .join("doc-1")
            .join("cache")
            .join("detections")
            .join("doc-1")
            .join("page_0003.json");
        assert!(expected_path.exists(), "cache should be written under projects/<doc_id>/cache/detections");

        let loaded = cache.get("doc-1", 3, "abc123").expect("must hit");
        assert_eq!(loaded.doc_id, "doc-1");
        assert_eq!(loaded.detections.len(), 1);
    }
}
