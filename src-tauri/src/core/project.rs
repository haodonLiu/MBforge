use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

use super::constants::{INDEX_FILE, PROJECT_FORMAT_VERSION, PROJECT_META_DIR, SUPPORTED_DOC_EXTS, SUPPORTED_MOL_EXTS};
use super::helpers::{generate_uuid, now_rfc3339, sha256_file};

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
    #[serde(default)]
    version: u32,
    #[serde(default)]
    updated_at: String,
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
        println!("[Rust Project::open] Starting... root: {:?}", root);
        
        let root = root.to_path_buf().canonicalize().ok()?;
        println!("[Rust Project::open] Canonicalized root: {:?}", root);
        
        let meta_dir = root.join(PROJECT_META_DIR);
        println!("[Rust Project::open] Meta dir: {:?}", meta_dir);
        println!("[Rust Project::open] Meta dir exists: {}", meta_dir.exists());

        if !meta_dir.exists() {
            println!("[Rust Project::open] Meta dir does not exist, returning None (not a project)");
            return None;
        }

        // Version check & migration
        let version = super::project_migrator::ProjectMigrator::read_version(&root);
        println!("[Rust Project::open] Project version: {}", version);
        if version > PROJECT_FORMAT_VERSION {
            log::error!(
                "Project version {} > app version {}, cannot open",
                version, PROJECT_FORMAT_VERSION
            );
            println!("[Rust Project::open] Version too new, returning None");
            return None;
        }

        if let Err(e) = super::project_migrator::ProjectMigrator::migrate(&root) {
            log::error!("Migration failed: {}, attempting recovery", e);
            println!("[Rust Project::open] Migration failed: {}", e);
            if let Err(e2) = super::project_migrator::ProjectMigrator::recover(&root) {
                log::error!("Recovery also failed: {}", e2);
                println!("[Rust Project::open] Recovery also failed: {}", e2);
                return None;
            }
        } else {
            println!("[Rust Project::open] Migration succeeded or not needed");
        }

        // Load index
        let index_path = meta_dir.join(INDEX_FILE);
        println!("[Rust Project::open] Index path: {:?}", index_path);
        println!("[Rust Project::open] Index file exists: {}", index_path.exists());
        
        let index: ProjectIndex = match super::helpers::load_json::<ProjectIndex>(&index_path) {
            Some(idx) => {
                println!("[Rust Project::open] Loaded existing index with {} documents", idx.documents.len());
                idx
            }
            None => {
                println!("[Rust Project::open] No existing index, creating empty");
                ProjectIndex {
                    version: PROJECT_FORMAT_VERSION,
                    updated_at: now_rfc3339(),
                    documents: vec![],
                }
            }
        };

        let mut path_map = HashMap::new();
        for doc in &index.documents {
            let full = root.join(&doc.path);
            path_map.insert(full, doc.doc_id.clone());
        }

        let mut project = Self {
            root,
            meta_dir,
            index: index.documents,
            path_map,
        };

        // NOTE: Scanning removed - use scan_files() explicitly when needed
        // This avoids slow directory traversal on project open

        println!("[Rust Project::open] Project opened successfully");
        Some(project)
    }

    pub fn create(root: &Path) -> Option<Self> {
        println!("[Rust Project::create] Starting... root: {:?}", root);
        
        let root = root.to_path_buf().canonicalize().ok()?;
        println!("[Rust Project::create] Canonicalized root: {:?}", root);
        
        let meta_dir = root.join(PROJECT_META_DIR);
        println!("[Rust Project::create] Creating meta dir: {:?}", meta_dir);
        
        if std::fs::create_dir_all(&meta_dir).is_err() {
            println!("[Rust Project::create] Failed to create meta dir");
            return None;
        }
        println!("[Rust Project::create] Meta dir created");
        
        if super::project_migrator::ProjectMigrator::write_version(&root, PROJECT_FORMAT_VERSION).is_err() {
            println!("[Rust Project::create] Failed to write version");
            return None;
        }
        println!("[Rust Project::create] Version written");
        println!("[Rust Project::create] Project created successfully");
        
        Some(Self { root, meta_dir, index: vec![], path_map: HashMap::new() })
    }

    pub fn scan_files(&mut self) -> Vec<DocumentEntry> {
        let mut new_entries = Vec::new();
        let mut seen_paths = std::collections::HashSet::new();

        let all_exts: Vec<&str> = SUPPORTED_DOC_EXTS.iter().chain(SUPPORTED_MOL_EXTS.iter()).copied().collect();
        for entry in walkdir::WalkDir::new(&self.root).into_iter().filter_map(|e| e.ok()) {
            let path = entry.path();
            if !path.is_file() { continue; }
            if path.starts_with(&self.meta_dir) { continue; }
            let name = path.file_name().and_then(|n: &std::ffi::OsStr| n.to_str()).unwrap_or("");
            if name.starts_with('.') { continue; }
            let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("").to_lowercase();
            if !all_exts.contains(&ext.as_str()) { continue; }

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
                        added_at: super::helpers::now_rfc3339(),
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

    /// 将外部文件添加到项目索引。文件必须已存在于项目根目录或其子目录下。
    pub fn add_file(&mut self, path: &Path) -> Option<DocumentEntry> {
        let full = path.canonicalize().ok()?;
        if !full.exists() {
            return None;
        }

        // 已在索引中则直接返回
        if let Some(doc_id) = self.path_map.get(&full) {
            return self.index.iter().find(|d| &d.doc_id == doc_id).cloned();
        }

        let doc_id = generate_uuid();
        let hash = sha256_file(&full).unwrap_or_default();
        let rel = full.strip_prefix(&self.root).unwrap_or(&full);
        let entry = DocumentEntry {
            doc_id: doc_id.clone(),
            path: rel.to_string_lossy().to_string(),
            doc_type: DocumentEntry::detect_type(&full),
            title: full.file_stem().and_then(|s: &std::ffi::OsStr| s.to_str()).unwrap_or("Untitled").to_string(),
            indexed: false,
            added_at: now_rfc3339(),
            hash,
            mtime: 0.0,
        };
        self.path_map.insert(full, doc_id);
        self.index.push(entry.clone());
        self.save_index();
        Some(entry)
    }

    /// 从项目索引中移除文档。不删除物理文件（由调用方负责）。
    pub fn remove_document(&mut self, doc_id: &str) -> bool {
        let pos = match self.index.iter().position(|d| d.doc_id == doc_id) {
            Some(p) => p,
            None => return false,
        };
        let entry = self.index.remove(pos);
        let full = self.root.join(&entry.path);
        self.path_map.remove(&full);
        self.save_index();
        true
    }

    pub fn save_index(&self) {
        let index = ProjectIndex {
            version: PROJECT_FORMAT_VERSION,
            updated_at: now_rfc3339(),
            documents: self.index.clone(),
        };
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
