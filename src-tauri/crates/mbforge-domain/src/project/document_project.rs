use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

use mbforge_infra::config::constants::{
    INDEX_FILE, MOLECULES_DIR, PROJECTS_DIR, PROJECT_META_DIR, PROJECT_SOURCE_FILE, REPORTS_DIR,
};
use mbforge_infra::helpers::{generate_uuid, now_rfc3339, save_json, sha256_file};

/// Metadata stored in `projects/<doc_id>/.mbforge/index.json`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentProjectMeta {
    pub doc_id: String,
    pub title: String,
    pub doc_type: String,
    pub source_filename: String,
    pub added_at: String,
    pub hash: String,
    pub mtime: f64,
    /// pending / text_based / scanned / mixed / image_based / error
    pub inspector_status: String,
    /// pending / done / not_needed / error
    pub text_status: String,
    /// pending / pending_confirmation / processing / done / skipped / not_needed / error
    pub ocr_status: String,
    /// not_processed / processing / has_molecule / no_molecule / error
    pub moldet_status: String,
    #[serde(default)]
    pub moldet_pages: Vec<usize>,
    /// pending / done / error
    pub index_status: String,
}

impl Default for DocumentProjectMeta {
    fn default() -> Self {
        Self {
            doc_id: String::new(),
            title: String::new(),
            doc_type: String::from("pdf"),
            source_filename: String::new(),
            added_at: String::new(),
            hash: String::new(),
            mtime: 0.0,
            inspector_status: String::from("pending"),
            text_status: String::from("pending"),
            ocr_status: String::from("pending"),
            moldet_status: String::from("not_processed"),
            moldet_pages: Vec::new(),
            index_status: String::from("pending"),
        }
    }
}

/// An isolated DocumentProject under `projects/<doc_id>/`.
pub struct DocumentProject {
    /// Project root (the parent project that owns this document-project).
    pub project_root: PathBuf,
    pub doc_id: String,
    pub meta: DocumentProjectMeta,
}

/// All canonical paths for a DocumentProject.
pub struct DocumentProjectPaths {
    pub project_dir: PathBuf,
    pub source_path: PathBuf,
    pub meta_dir: PathBuf,
    pub meta_path: PathBuf,
    pub cache_dir: PathBuf,
    pub detection_cache_dir: PathBuf,
    pub ocr_cache_dir: PathBuf,
    pub pages_cache_dir: PathBuf,
    pub tmp_dir: PathBuf,
    pub molecules_dir: PathBuf,
    pub reports_dir: PathBuf,
}

impl DocumentProject {
    /// Compute all canonical paths for this document-project.
    pub fn paths(&self) -> DocumentProjectPaths {
        let project_dir = self.project_root.join(PROJECTS_DIR).join(&self.doc_id);
        let meta_dir = project_dir.join(PROJECT_META_DIR);
        let cache_dir = project_dir.join("cache");
        DocumentProjectPaths {
            source_path: project_dir.join(PROJECT_SOURCE_FILE),
            meta_dir: meta_dir.clone(),
            meta_path: meta_dir.join(INDEX_FILE),
            cache_dir: cache_dir.clone(),
            detection_cache_dir: cache_dir.join("detections"),
            ocr_cache_dir: cache_dir.join("ocr"),
            pages_cache_dir: cache_dir.join("pages"),
            tmp_dir: cache_dir.join("tmp"),
            molecules_dir: project_dir.join(MOLECULES_DIR),
            reports_dir: project_dir.join(REPORTS_DIR),
            project_dir,
        }
    }

    /// Create a new DocumentProject from a source file.
    ///
    /// Generates a fresh `doc_id`, copies `source_file` to
    /// `projects/<doc_id>/source.pdf`, creates all subdirectories, writes the
    /// metadata file, and returns the loaded `DocumentProject`.
    pub fn create(project_root: &Path, source_file: &Path) -> Result<Self, String> {
        if !source_file.exists() {
            return Err(format!(
                "Source file does not exist: {}",
                source_file.display()
            ));
        }

        let doc_id = generate_uuid();
        let mut project = Self {
            project_root: project_root.to_path_buf(),
            doc_id,
            meta: DocumentProjectMeta::default(),
        };
        let paths = project.paths();

        std::fs::create_dir_all(&paths.project_dir)
            .map_err(|e| format!("Failed to create project dir: {e}"))?;
        std::fs::create_dir_all(&paths.meta_dir)
            .map_err(|e| format!("Failed to create meta dir: {e}"))?;
        std::fs::create_dir_all(&paths.cache_dir)
            .map_err(|e| format!("Failed to create cache dir: {e}"))?;
        std::fs::create_dir_all(&paths.detection_cache_dir)
            .map_err(|e| format!("Failed to create detection cache dir: {e}"))?;
        std::fs::create_dir_all(&paths.ocr_cache_dir)
            .map_err(|e| format!("Failed to create OCR cache dir: {e}"))?;
        std::fs::create_dir_all(&paths.pages_cache_dir)
            .map_err(|e| format!("Failed to create pages cache dir: {e}"))?;
        std::fs::create_dir_all(&paths.tmp_dir)
            .map_err(|e| format!("Failed to create tmp dir: {e}"))?;
        std::fs::create_dir_all(&paths.molecules_dir)
            .map_err(|e| format!("Failed to create molecules dir: {e}"))?;
        std::fs::create_dir_all(&paths.reports_dir)
            .map_err(|e| format!("Failed to create reports dir: {e}"))?;

        std::fs::copy(source_file, &paths.source_path)
            .map_err(|e| format!("Failed to copy source file: {e}"))?;

        let hash = sha256_file(&paths.source_path)
            .map_err(|e| format!("Failed to hash source file: {e}"))?;
        let mtime = std::fs::metadata(&paths.source_path)
            .and_then(|m| m.modified())
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0);

        let title = source_file
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("Untitled")
            .to_string();
        let source_filename = source_file
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("source.pdf")
            .to_string();

        project.meta = DocumentProjectMeta {
            doc_id: project.doc_id.clone(),
            title,
            doc_type: String::from("pdf"),
            source_filename,
            added_at: now_rfc3339(),
            hash,
            mtime,
            inspector_status: String::from("pending"),
            text_status: String::from("pending"),
            ocr_status: String::from("pending"),
            moldet_status: String::from("not_processed"),
            moldet_pages: Vec::new(),
            index_status: String::from("pending"),
        };

        project.save_meta()?;
        Ok(project)
    }

    /// Load an existing DocumentProject by `doc_id`.
    ///
    /// Returns `None` if the project directory or metadata file is missing.
    pub fn load(project_root: &Path, doc_id: &str) -> Option<Self> {
        let project_dir = project_root.join(PROJECTS_DIR).join(doc_id);
        let meta_path = project_dir.join(PROJECT_META_DIR).join(INDEX_FILE);
        let meta: DocumentProjectMeta = mbforge_infra::helpers::load_json(&meta_path)?;
        Some(Self {
            project_root: project_root.to_path_buf(),
            doc_id: doc_id.to_string(),
            meta,
        })
    }

    /// Persist metadata to `projects/<doc_id>/.mbforge/index.json`.
    pub fn save_meta(&self) -> Result<(), String> {
        let paths = self.paths();
        save_json(&paths.meta_path, &self.meta)
            .map_err(|e| format!("Failed to save document project meta: {e}"))
    }

    /// Update the inspector status and persist.
    pub fn set_inspector_status(&mut self, status: &str) {
        self.meta.inspector_status = status.to_string();
        let _ = self.save_meta();
    }

    /// Update the text extraction status and persist.
    pub fn set_text_status(&mut self, status: &str) {
        self.meta.text_status = status.to_string();
        let _ = self.save_meta();
    }

    /// Update the OCR status and persist.
    pub fn set_ocr_status(&mut self, status: &str) {
        self.meta.ocr_status = status.to_string();
        let _ = self.save_meta();
    }

    /// Update the MoldDet status + pages and persist.
    pub fn set_moldet_status(&mut self, status: &str, pages: &[usize]) {
        self.meta.moldet_status = status.to_string();
        self.meta.moldet_pages = pages.to_vec();
        let _ = self.save_meta();
    }

    /// Update the indexing status and persist.
    pub fn set_index_status(&mut self, status: &str) {
        self.meta.index_status = status.to_string();
        let _ = self.save_meta();
    }

    /// Compute the SHA-256 of `source.pdf`.
    pub fn source_hash(&self) -> Result<String, String> {
        sha256_file(&self.paths().source_path)
            .map_err(|e| format!("Failed to hash source.pdf: {e}"))
    }

    /// Whether the project directory and source file exist on disk.
    pub fn exists(&self) -> bool {
        let paths = self.paths();
        paths.project_dir.exists() && paths.source_path.exists()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::TempDir;

    fn make_pdf(dir: &Path, name: &str, content: &[u8]) -> PathBuf {
        let path = dir.join(name);
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(content).unwrap();
        path
    }

    #[test]
    fn test_document_project_create_and_load() {
        let tmp = TempDir::new().unwrap();
        let root = tmp.path();
        let source = make_pdf(root, "paper.pdf", b"%PDF-1.4 test");

        let doc = DocumentProject::create(root, &source).expect("create should succeed");
        assert!(!doc.doc_id.is_empty());
        assert!(doc.exists());

        let paths = doc.paths();
        assert!(paths.source_path.exists());
        assert!(paths.meta_path.exists());
        assert!(paths.cache_dir.exists());
        assert!(paths.detection_cache_dir.exists());
        assert!(paths.molecules_dir.exists());
        assert!(paths.reports_dir.exists());

        let loaded = DocumentProject::load(root, &doc.doc_id).expect("load should succeed");
        assert_eq!(loaded.doc_id, doc.doc_id);
        assert_eq!(loaded.meta.title, "paper");
        assert_eq!(loaded.meta.source_filename, "paper.pdf");
        assert_eq!(loaded.meta.hash, doc.meta.hash);

        let hash = loaded.source_hash().expect("hash should succeed");
        assert_eq!(hash, doc.meta.hash);
    }
}
