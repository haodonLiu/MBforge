use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

use super::constants::{INDEX_FILE, PROJECT_META_DIR, SUPPORTED_DOC_EXTS, SUPPORTED_MOL_EXTS};
use super::helpers::{generate_uuid, sha256_file};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentEntry {
    pub doc_id: String,
    pub path: String,
    pub doc_type: String,
    pub title: String,
    pub indexed: bool,
    #[serde(default)]
    pub added_at: String,
    #[serde(default)]
    pub hash: String,
    #[serde(default)]
    pub mtime: f64,
}

impl DocumentEntry {
    fn detect_type(path: &Path) -> String {
        match path.extension().and_then(|e| e.to_str()) {
            Some("pdf") => "pdf",
            Some("md") => "markdown",
            Some("sdf") | Some("mol") | Some("mol2") | Some("pdb") | Some("smi") => "molecule",
            Some("csv") | Some("xlsx") | Some("json") => "data",
            _ => "text",
        }.to_string()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ProjectIndex {
    documents: Vec<DocumentEntry>,
}

pub struct Project {
    pub root: PathBuf,
    pub meta_dir: PathBuf,
    index: Vec<DocumentEntry>,
    path_map: HashMap<PathBuf, String>, // resolved path -> doc_id
}

impl Project {
    pub fn open(root: &Path) -> Option<Self> {
        let root = root.to_path_buf().canonicalize().ok()?;
        let meta_dir = root.join(PROJECT_META_DIR);
        let index_path = meta_dir.join(INDEX_FILE);
        let index: ProjectIndex = super::helpers::load_json(&index_path).unwrap_or(ProjectIndex { documents: vec![] });
        let mut path_map = HashMap::new();
        for doc in &index.documents {
            let full = root.join(&doc.path);
            path_map.insert(full, doc.doc_id.clone());
        }
        Some(Self { root, meta_dir, index: index.documents, path_map })
    }

    pub fn create(root: &Path) -> Option<Self> {
        let root = root.to_path_buf().canonicalize().ok()?;
        let meta_dir = root.join(PROJECT_META_DIR);
        std::fs::create_dir_all(&meta_dir).ok()?;
        Some(Self { root, meta_dir, index: vec![], path_map: HashMap::new() })
    }

    pub fn scan_files(&mut self) -> Vec<DocumentEntry> {
        let mut new_entries = Vec::new();
        let mut seen_paths = std::collections::HashSet::new();

        for entry in walkdir::WalkDir::new(&self.root).into_iter().filter_map(|e| e.ok()) {
            let path = entry.path();
            if path.starts_with(&self.meta_dir) { continue; }
            let name = path.file_name().and_then(|n: &std::ffi::OsStr| n.to_str()).unwrap_or("");
            if name.starts_with('.') { continue; }

                let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
                let all_exts: Vec<&str> = SUPPORTED_DOC_EXTS.iter().chain(SUPPORTED_MOL_EXTS.iter()).copied().collect();
                if !all_exts.contains(&ext) { continue; }

                seen_paths.insert(path.to_path_buf());

                if let Some(doc_id) = self.path_map.get(path) {
                    // Update hash if file changed
                    if let Some(doc) = self.index.iter_mut().find(|d| &d.doc_id == doc_id) {
                        if let Ok(new_hash) = sha256_file(path) {
                            if new_hash != doc.hash {
                                doc.hash = new_hash;
                                doc.indexed = false;
                            }
                        }
                    }
                } else {
                    // New file
                    let doc_id = generate_uuid();
                    let hash = sha256_file(path).unwrap_or_default();
                    let rel = path.strip_prefix(&self.root).unwrap_or(path);
                    let entry = DocumentEntry {
                        doc_id: doc_id.clone(),
                        path: rel.to_string_lossy().to_string(),
                        doc_type: DocumentEntry::detect_type(path),
                        title: path.file_stem().and_then(|s: &std::ffi::OsStr| s.to_str()).unwrap_or("Untitled").to_string(),
                        indexed: false,
                        added_at: chrono::Utc::now().to_rfc3339(),
                        hash,
                        mtime: 0.0,
                    };
                    self.path_map.insert(path.to_path_buf(), doc_id);
                    self.index.push(entry.clone());
                    new_entries.push(entry);
                }
            }

        // Remove deleted files
        self.index.retain(|d| {
            let full = self.root.join(&d.path);
            if !full.exists() {
                self.path_map.remove(&full);
                false
            } else {
                true
            }
        });

        self.save_index();
        new_entries
    }

    pub fn list_documents(&self) -> &[DocumentEntry] {
        &self.index
    }

    pub fn get_document(&self, doc_id: &str) -> Option<&DocumentEntry> {
        self.index.iter().find(|d| d.doc_id == doc_id)
    }

    pub fn save_index(&self) {
        let index = ProjectIndex { documents: self.index.clone() };
        let _ = super::helpers::save_json(&self.meta_dir.join(INDEX_FILE), &index);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_type() {
        assert_eq!(DocumentEntry::detect_type(Path::new("test.pdf")), "pdf");
        assert_eq!(DocumentEntry::detect_type(Path::new("test.md")), "markdown");
        assert_eq!(DocumentEntry::detect_type(Path::new("test.mol")), "molecule");
        assert_eq!(DocumentEntry::detect_type(Path::new("test.txt")), "text");
    }
}
