use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

use crate::core::config::constants::{
    INDEX_DIR, INDEX_FILE, MOLECULES_DIR, NOTES_DIR, NOTES_EXTS, PAPERS_DIR, PAPERS_EXTS,
    PROJECT_FORMAT_VERSION, PROJECT_META_DIR, REPORTS_DIR,
};
use crate::core::helpers::{generate_uuid, now_rfc3339, sha256_file};

/// The 5 user-visible folder names. Order matters for the bootstrap
/// and for any "expected layout" checks.
const CANONICAL_USER_DIRS: &[&str] = &[
    PAPERS_DIR,
    NOTES_DIR,
    MOLECULES_DIR,
    INDEX_DIR,
    REPORTS_DIR,
];

/// Create the 5 user folders + .mbforge if missing. Idempotent.
fn bootstrap_canonical_layout(root: &Path) {
    for dir in CANONICAL_USER_DIRS {
        let _ = std::fs::create_dir_all(root.join(dir));
    }
    let _ = std::fs::create_dir_all(root.join(PROJECT_META_DIR));
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentEntry {
    pub doc_id: String,
    pub path: String,
    pub doc_type: String,
    pub title: String,
    pub indexed: bool,
    /// Canonical folder the file lives in (`"papers"` or `"notes"`).
    /// Files in other locations are not indexed.
    #[serde(default)]
    pub folder: String,
    #[serde(default)]
    pub added_at: String,
    #[serde(default)]
    pub hash: String,
    #[serde(default)]
    pub mtime: f64,
    #[serde(default)]
    pub ocr_status: String,
    #[serde(default)]
    pub ocr_hash: String,
}

/// One scan warning — a file found in the project that was NOT
/// indexed because it was in the wrong folder or had a wrong
/// extension. Surfaced to the user verbatim so they can move it.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanWarning {
    pub path: String,
    pub reason: String,
    pub folder: String,
}

impl DocumentEntry {
    fn detect_type(path: &Path) -> String {
        match path.extension().and_then(|e| e.to_str()) {
            Some("pdf") => "pdf",
            Some("md") => "markdown",
            Some("sdf") | Some("mol") | Some("mol2") | Some("pdb") | Some("smi") => "molecule",
            Some("csv") | Some("xlsx") | Some("json") => "data",
            _ => "text",
        }
        .to_string()
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
        log::trace!("[Rust Project::open] Starting... root: {:?}", root);

        let root = root.to_path_buf().canonicalize().ok()?;
        log::trace!("[Rust Project::open] Canonicalized root: {:?}", root);

        let meta_dir = root.join(PROJECT_META_DIR);
        log::trace!("[Rust Project::open] Meta dir: {:?}", meta_dir);
        log::trace!(
            "[Rust Project::open] Meta dir exists: {}",
            meta_dir.exists()
        );

        if !meta_dir.exists() {
            log::trace!(
                "[Rust Project::open] Meta dir does not exist, returning None (not a project)"
            );
            return None;
        }

        // Version check（仅向前兼容，不支持降级打开）
        let version_path = root.join(".mbforge").join("version.json");
        let version: u32 = crate::core::helpers::load_json(&version_path)
            .and_then(|v: serde_json::Value| v["version"].as_u64().map(|n| n as u32))
            .unwrap_or(0);
        log::trace!("[Rust Project::open] Project version: {}", version);
        if version > PROJECT_FORMAT_VERSION {
            log::error!(
                "Project version {} > app version {}, cannot open",
                version,
                PROJECT_FORMAT_VERSION
            );
            return None;
        }

        // Load index
        let index_path = meta_dir.join(INDEX_FILE);
        log::trace!("[Rust Project::open] Index path: {:?}", index_path);
        log::trace!(
            "[Rust Project::open] Index file exists: {}",
            index_path.exists()
        );

        let index: ProjectIndex = match crate::core::helpers::load_json::<ProjectIndex>(&index_path) {
            Some(idx) => {
                log::trace!(
                    "[Rust Project::open] Loaded existing index with {} documents",
                    idx.documents.len()
                );
                idx
            }
            None => {
                log::trace!("[Rust Project::open] No existing index, creating empty");
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

        let project = Self {
            root,
            meta_dir,
            index: index.documents,
            path_map,
        };

        // Lazy-bootstrap: ensure all 5 user folders exist. This is not
        // a data migration — it only creates empty directories. Files
        // that already exist in the wrong place are left alone (the
        // scanner will report them as warnings on next scan).
        bootstrap_canonical_layout(&project.root);

        // NOTE: Scanning removed - use scan_files() explicitly when needed
        // This avoids slow directory traversal on project open

        log::trace!("[Rust Project::open] Project opened successfully");
        Some(project)
    }

    pub fn create(root: &Path) -> Option<Self> {
        log::trace!("[Rust Project::create] Starting... root: {:?}", root);

        let root = root.to_path_buf().canonicalize().ok()?;
        log::trace!("[Rust Project::create] Canonicalized root: {:?}", root);

        let meta_dir = root.join(PROJECT_META_DIR);

        // Bootstrap the full 6-folder skeleton (papers, notes, molecules,
        // index, reports, .mbforge). Idempotent.
        bootstrap_canonical_layout(&root);

        // 写入版本信息
        let version_path = root.join(".mbforge").join("version.json");
        let version_data = serde_json::json!({ "version": PROJECT_FORMAT_VERSION });
        if crate::core::helpers::save_json(&version_path, &version_data).is_err() {
            log::trace!("[Rust Project::create] Failed to write version");
            return None;
        }
        log::trace!("[Rust Project::create] Version written");
        log::trace!("[Rust Project::create] Project created successfully");

        Some(Self {
            root,
            meta_dir,
            index: vec![],
            path_map: HashMap::new(),
        })
    }

    /// Scan the project for input files.
    ///
    /// **Strict canonical layout enforced:**
    /// - Walks ONLY `papers/` and `notes/` (plus their subfolders).
    /// - `papers/` accepts `.pdf` only.
    /// - `notes/` accepts `.md` and `.txt` only.
    /// - Files in any other location (root, `molecules/`, `index/`,
    ///   `reports/`, `.mbforge/`, or non-canonical dirs) are NOT
    ///   indexed. Misplaced files are returned as warnings so the
    ///   user can move them to the right folder.
    ///
    /// Returns `(new_entries, warnings)`. `new_entries` are the
    /// freshly-added `DocumentEntry`s; `warnings` describe files
    /// that exist in the project but were skipped.
    pub fn scan_files(&mut self) -> (Vec<DocumentEntry>, Vec<ScanWarning>) {
        let mut new_entries = Vec::new();
        let mut warnings: Vec<ScanWarning> = Vec::new();

        let papers_dir = self.root.join(PAPERS_DIR);
        let notes_dir = self.root.join(NOTES_DIR);

        // Scan papers/ (recursive, accept .pdf)
        self.scan_canonical_folder(
            &papers_dir,
            PAPERS_EXTS,
            PAPERS_DIR,
            &mut new_entries,
            &mut warnings,
        );
        // Scan notes/ (recursive, accept .md/.txt)
        self.scan_canonical_folder(
            &notes_dir,
            NOTES_EXTS,
            NOTES_DIR,
            &mut new_entries,
            &mut warnings,
        );

        // Sweep the rest of the project tree for misplaced files.
        // We exclude the 4 output/meta folders, but anything else
        // (root-level files, dot-dirs, ad-hoc subdirs) is reported
        // as a warning.
        let excluded: Vec<PathBuf> = [
            self.meta_dir.as_path(),
            papers_dir.as_path(),
            notes_dir.as_path(),
            self.root.join(MOLECULES_DIR).as_path(),
            self.root.join(INDEX_DIR).as_path(),
            self.root.join(REPORTS_DIR).as_path(),
        ]
        .into_iter()
        .map(|p| p.to_path_buf())
        .collect();

        for entry in walkdir::WalkDir::new(&self.root)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            let path = entry.path();
            if !path.is_file() {
                continue;
            }
            if excluded.iter().any(|ex| path.starts_with(ex)) {
                continue;
            }
            let rel = path.strip_prefix(&self.root).unwrap_or(path);
            let rel_str = rel.to_string_lossy().to_string();
            let folder = rel
                .components()
                .next()
                .and_then(|c| c.as_os_str().to_str())
                .unwrap_or("(root)")
                .to_string();
            warnings.push(ScanWarning {
                path: rel_str,
                reason: "文件位置不符合规范：只接受 papers/ (PDF) 或 notes/ (MD/TXT)".to_string(),
                folder,
            });
        }

        // Remove deleted files from the index
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
        (new_entries, warnings)
    }

    /// Walk one canonical input folder, index allowed files,
    /// warn on disallowed files within it.
    fn scan_canonical_folder(
        &mut self,
        folder: &Path,
        allowed_exts: &[&str],
        folder_name: &str,
        new_entries: &mut Vec<DocumentEntry>,
        warnings: &mut Vec<ScanWarning>,
    ) {
        if !folder.exists() {
            // Folder missing — silently skip (bootstrap on open/create
            // ensures it exists, but a project opened on a read-only
            // filesystem may lack it).
            return;
        }

        for entry in walkdir::WalkDir::new(folder)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            let path = entry.path();
            if !path.is_file() {
                continue;
            }
            // Skip the meta dir just in case (e.g. if user symlinked
            // it inside papers/ — extremely unlikely but cheap to check).
            if path.starts_with(&self.meta_dir) {
                continue;
            }
            let name = path
                .file_name()
                .and_then(|n: &std::ffi::OsStr| n.to_str())
                .unwrap_or("");
            if name.starts_with('.') {
                continue;
            }
            let ext = path
                .extension()
                .and_then(|e| e.to_str())
                .unwrap_or("")
                .to_lowercase();

            if !allowed_exts.contains(&ext.as_str()) {
                let rel = path.strip_prefix(&self.root).unwrap_or(path);
                let allowed = allowed_exts.join(", ");
                warnings.push(ScanWarning {
                    path: rel.to_string_lossy().to_string(),
                    reason: format!(
                        "{}/ 目录只接受扩展名为 [{}] 的文件，发现 .{}",
                        folder_name, allowed, ext
                    ),
                    folder: folder_name.to_string(),
                });
                continue;
            }

            if let Some(doc_id) = self.path_map.get(path).cloned() {
                // Existing file — update hash if changed
                if let Some(doc) = self.index.iter_mut().find(|d| d.doc_id == doc_id) {
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
                let new_doc = DocumentEntry {
                    doc_id: doc_id.clone(),
                    path: rel.to_string_lossy().to_string(),
                    doc_type: DocumentEntry::detect_type(path),
                    title: path
                        .file_stem()
                        .and_then(|s: &std::ffi::OsStr| s.to_str())
                        .unwrap_or("Untitled")
                        .to_string(),
                    indexed: false,
                    folder: folder_name.to_string(),
                    added_at: crate::core::helpers::now_rfc3339(),
                    hash,
                    mtime: 0.0,
                    ocr_status: "not_processed".to_string(),
                    ocr_hash: String::new(),
                };
                self.path_map.insert(path.to_path_buf(), doc_id);
                self.index.push(new_doc.clone());
                new_entries.push(new_doc);
            }
        }
    }

    pub fn list_documents(&self) -> &[DocumentEntry] {
        &self.index
    }

    pub fn get_document(&self, doc_id: &str) -> Option<&DocumentEntry> {
        self.index.iter().find(|d| d.doc_id == doc_id)
    }

    pub fn get_document_mut(&mut self, doc_id: &str) -> Option<&mut DocumentEntry> {
        self.index.iter_mut().find(|d| d.doc_id == doc_id)
    }

    /// 更新文档的 OCR 状态与 hash，并持久化 index。
    pub fn set_document_ocr(&mut self, doc_id: &str, status: &str, hash: &str) -> bool {
        let Some(doc) = self.get_document_mut(doc_id) else {
            return false;
        };
        doc.ocr_status = status.to_string();
        doc.ocr_hash = hash.to_string();
        self.save_index();
        true
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
            title: full
                .file_stem()
                .and_then(|s: &std::ffi::OsStr| s.to_str())
                .unwrap_or("Untitled")
                .to_string(),
            indexed: false,
            folder: String::new(),
            added_at: now_rfc3339(),
            hash,
            mtime: 0.0,
            ocr_status: "not_processed".to_string(),
            ocr_hash: String::new(),
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
        let _ = crate::core::helpers::save_json(&self.meta_dir.join(INDEX_FILE), &index);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_type() {
        assert_eq!(DocumentEntry::detect_type(Path::new("test.pdf")), "pdf");
        assert_eq!(DocumentEntry::detect_type(Path::new("test.md")), "markdown");
        assert_eq!(
            DocumentEntry::detect_type(Path::new("test.mol")),
            "molecule"
        );
        assert_eq!(DocumentEntry::detect_type(Path::new("test.txt")), "text");
    }
}
