use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

use crate::document::detection_cache::DetectionCache;
use crate::document::knowledge_base::get_or_init_kb;
use crate::document::summary::SummaryManager;
use crate::molecule::molecule_store::MoleculeDatabase;
use crate::project::document_project::DocumentProject;
use mbforge_infra::config::constants::{
    INDEX_DIR, INDEX_FILE, MOLECULES_DIR, NOTES_DIR, NOTES_EXTS, PAPERS_DIR, PROJECTS_DIR,
    PROJECT_FORMAT_VERSION, PROJECT_META_DIR, REPORTS_DIR,
};
use mbforge_infra::helpers::{generate_uuid, now_rfc3339, sha256_file};

/// The 6 user-visible folder names. Order matters for the bootstrap
/// and for any "expected layout" checks.
const CANONICAL_USER_DIRS: &[&str] = &[
    PROJECTS_DIR,
    PAPERS_DIR,
    NOTES_DIR,
    MOLECULES_DIR,
    INDEX_DIR,
    REPORTS_DIR,
];

/// Create the 6 user folders + .mbforge if missing. Idempotent.
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
    #[serde(default)]
    pub source_path: Option<String>,
    pub doc_type: String,
    pub title: String,
    #[serde(default)]
    pub indexed: bool,
    #[serde(default)]
    pub folder: String,
    #[serde(default)]
    pub added_at: String,
    #[serde(default)]
    pub hash: String,
    #[serde(default)]
    pub mtime: f64,
    #[serde(default)]
    pub inspector_status: String,
    #[serde(default)]
    pub text_status: String,
    #[serde(default)]
    pub ocr_status: String,
    #[serde(default)]
    pub ocr_hash: String,
    #[serde(default)]
    pub moldet_status: String,
    #[serde(default)]
    pub moldet_pages: Vec<usize>,
    #[serde(default)]
    pub index_status: String,
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

    /// Build a lightweight `DocumentEntry` from a loaded `DocumentProject`.
    fn from_document_project(project_root: &Path, dp: &DocumentProject) -> Self {
        let paths = dp.paths();
        let rel = paths
            .source_path
            .strip_prefix(project_root)
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|_| paths.source_path.to_string_lossy().to_string());
        Self {
            doc_id: dp.doc_id.clone(),
            path: rel.clone(),
            source_path: Some(rel),
            doc_type: dp.meta.doc_type.clone(),
            title: dp.meta.title.clone(),
            indexed: false,
            folder: PROJECTS_DIR.to_string(),
            added_at: dp.meta.added_at.clone(),
            hash: dp.meta.hash.clone(),
            mtime: dp.meta.mtime,
            inspector_status: dp.meta.inspector_status.clone(),
            text_status: dp.meta.text_status.clone(),
            ocr_status: dp.meta.ocr_status.clone(),
            ocr_hash: String::new(),
            moldet_status: dp.meta.moldet_status.clone(),
            moldet_pages: dp.meta.moldet_pages.clone(),
            index_status: dp.meta.index_status.clone(),
        }
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
        let version: u32 = mbforge_infra::helpers::load_json(&version_path)
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

        let index: ProjectIndex =
            match mbforge_infra::helpers::load_json::<ProjectIndex>(&index_path) {
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
            if let Some(sp) = &doc.source_path {
                let full_source = root.join(sp);
                path_map.insert(full_source, doc.doc_id.clone());
            }
        }

        let mut project = Self {
            root,
            meta_dir,
            index: index.documents,
            path_map,
        };

        // Lazy-bootstrap: ensure all 6 user folders exist. This is not
        // a data migration — it only creates empty directories. Files
        // that already exist in the wrong place are left alone (the
        // scanner will report them as warnings on next scan).
        bootstrap_canonical_layout(&project.root);

        // Migrate legacy v1 projects (papers/*.pdf) to v2 DocumentProjects.
        if version < PROJECT_FORMAT_VERSION {
            log::info!(
                "Project format version {} < {}, running legacy migration",
                version,
                PROJECT_FORMAT_VERSION
            );
            let _warnings = project.migrate_legacy_papers();
            let version_path = project.root.join(".mbforge").join("version.json");
            let version_data = serde_json::json!({ "version": PROJECT_FORMAT_VERSION });
            let _ = mbforge_infra::helpers::save_json(&version_path, &version_data);
        }

        log::trace!("[Rust Project::open] Project opened successfully");
        Some(project)
    }

    pub fn create(root: &Path) -> Option<Self> {
        log::trace!("[Rust Project::create] Starting... root: {:?}", root);

        let root = root.to_path_buf().canonicalize().ok()?;
        log::trace!("[Rust Project::create] Canonicalized root: {:?}", root);

        let meta_dir = root.join(PROJECT_META_DIR);

        // Bootstrap the full 6-folder skeleton (projects, papers, notes,
        // molecules, index, reports, .mbforge). Idempotent.
        bootstrap_canonical_layout(&root);

        // 写入版本信息
        let version_path = root.join(".mbforge").join("version.json");
        let version_data = serde_json::json!({ "version": PROJECT_FORMAT_VERSION });
        if mbforge_infra::helpers::save_json(&version_path, &version_data).is_err() {
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
    /// - Walks `projects/*/.mbforge/index.json` to discover DocumentProjects.
    /// - Walks `papers/` and `notes/` for migration/legacy detection.
    /// - `papers/` accepts `.pdf` only.
    /// - `notes/` accepts `.md` and `.txt` only.
    /// - Files in any other location are NOT indexed. Misplaced files are
    ///   returned as warnings so the user can move them.
    ///
    /// Returns `(new_entries, warnings)`. `new_entries` are the
    /// freshly-added `DocumentEntry`s; `warnings` describe files
    /// that exist in the project but were skipped.
    pub fn scan_files(&mut self) -> (Vec<DocumentEntry>, Vec<ScanWarning>) {
        let mut new_entries = Vec::new();
        let mut warnings: Vec<ScanWarning> = Vec::new();

        // Primary source of truth: DocumentProjects under projects/.
        self.scan_document_projects(&mut new_entries, &mut warnings);

        // Legacy papers/ migration: any PDF without a project gets migrated.
        let papers_dir = self.root.join(PAPERS_DIR);
        if papers_dir.exists() {
            let migrated = self.migrate_legacy_papers();
            for warning in migrated {
                // Existing entries have already been added; warnings about
                // legacy migration are surfaced to the user.
                if !new_entries.iter().any(|e| e.path == warning.path) {
                    warnings.push(warning);
                }
            }
        }

        // Scan notes/ (recursive, accept .md/.txt)
        let notes_dir = self.root.join(NOTES_DIR);
        self.scan_canonical_folder(
            &notes_dir,
            NOTES_EXTS,
            NOTES_DIR,
            &mut new_entries,
            &mut warnings,
        );

        // Sweep the rest of the project tree for misplaced files.
        // We exclude the 5 output/meta folders, but anything else
        // (root-level files, dot-dirs, ad-hoc subdirs) is reported
        // as a warning.
        let excluded: Vec<PathBuf> = [
            self.meta_dir.as_path(),
            self.root.join(PROJECTS_DIR).as_path(),
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
                reason: "文件位置不符合规范：只接受 projects/ (PDF)、papers/ (PDF, 旧版) 或 notes/ (MD/TXT)".to_string(),
                folder,
            });
        }

        // Remove deleted files from the index
        self.index.retain(|d| {
            let full = self.root.join(&d.path);
            let source_full = d.source_path.as_ref().map(|p| self.root.join(p));
            let exists = full.exists() || source_full.as_ref().map(|p| p.exists()).unwrap_or(false);
            if !exists {
                if let Some(sp) = &d.source_path {
                    self.path_map.remove(&self.root.join(sp));
                }
                self.path_map.remove(&full);
                false
            } else {
                true
            }
        });

        self.save_index();
        (new_entries, warnings)
    }

    /// Discover DocumentProjects by walking `projects/*/.mbforge/index.json`.
    fn scan_document_projects(
        &mut self,
        new_entries: &mut Vec<DocumentEntry>,
        _warnings: &mut Vec<ScanWarning>,
    ) {
        let projects_dir = self.root.join(PROJECTS_DIR);
        if !projects_dir.exists() {
            return;
        }

        let entries = match std::fs::read_dir(&projects_dir) {
            Ok(e) => e,
            Err(_) => return,
        };

        for entry in entries.flatten() {
            let doc_id = match entry.file_name().into_string() {
                Ok(s) => s,
                Err(_) => continue,
            };
            let meta_path = entry.path().join(PROJECT_META_DIR).join(INDEX_FILE);
            if !meta_path.exists() {
                continue;
            }
            let Some(dp) = DocumentProject::load(&self.root, &doc_id) else {
                continue;
            };
            let source_full = dp.paths().source_path;

            if let Some(existing_id) = self.path_map.get(&source_full).cloned() {
                // Existing file — update hash if changed
                if let Some(doc) = self.index.iter_mut().find(|d| d.doc_id == existing_id) {
                    if let Ok(new_hash) = sha256_file(&source_full) {
                        if new_hash != doc.hash {
                            doc.hash = new_hash;
                            doc.indexed = false;
                        }
                    }
                }
            } else {
                let entry = DocumentEntry::from_document_project(&self.root, &dp);
                self.path_map.insert(source_full, entry.doc_id.clone());
                self.index.push(entry.clone());
                new_entries.push(entry);
            }
        }
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
            // Skip the meta dir just in case.
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
                    source_path: Some(rel.to_string_lossy().to_string()),
                    doc_type: DocumentEntry::detect_type(path),
                    title: path
                        .file_stem()
                        .and_then(|s: &std::ffi::OsStr| s.to_str())
                        .unwrap_or("Untitled")
                        .to_string(),
                    indexed: false,
                    folder: folder_name.to_string(),
                    added_at: mbforge_infra::helpers::now_rfc3339(),
                    hash,
                    mtime: 0.0,
                    inspector_status: "pending".to_string(),
                    text_status: "pending".to_string(),
                    ocr_status: "not_processed".to_string(),
                    ocr_hash: String::new(),
                    moldet_status: "not_processed".to_string(),
                    moldet_pages: Vec::new(),
                    index_status: "pending".to_string(),
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

    /// Return the absolute source path for a document.
    pub fn get_document_source_path(&self, doc_id: &str) -> Option<PathBuf> {
        let doc = self.get_document(doc_id)?;
        if let Some(sp) = &doc.source_path {
            let full = self.root.join(sp);
            if full.exists() {
                return Some(full);
            }
        }
        let full = self.root.join(&doc.path);
        if full.exists() {
            return Some(full);
        }
        None
    }

    /// 更新文档的 OCR 状态与 hash，并持久化 index。
    pub fn set_document_ocr(&mut self, doc_id: &str, status: &str, hash: &str) -> bool {
        let Some(doc) = self.get_document_mut(doc_id) else {
            return false;
        };
        doc.ocr_status = status.to_string();
        doc.ocr_hash = hash.to_string();
        if let Some(mut dp) = DocumentProject::load(&self.root, doc_id) {
            dp.set_ocr_status(status);
        }
        self.save_index();
        true
    }

    /// 通用状态更新：按字段名更新 DocumentEntry 和 DocumentProject meta。
    /// 支持的字段名：`inspector_status`, `text_status`, `ocr_status`, `moldet_status`, `index_status`。
    pub fn set_document_status(&mut self, doc_id: &str, field: &str, status: &str) -> bool {
        let Some(doc) = self.get_document_mut(doc_id) else {
            return false;
        };
        match field {
            "inspector_status" => doc.inspector_status = status.to_string(),
            "text_status" => doc.text_status = status.to_string(),
            "ocr_status" => doc.ocr_status = status.to_string(),
            "moldet_status" => doc.moldet_status = status.to_string(),
            "index_status" => doc.index_status = status.to_string(),
            _ => {
                log::warn!("set_document_status: unknown field {}", field);
                return false;
            }
        }
        if let Some(mut dp) = DocumentProject::load(&self.root, doc_id) {
            match field {
                "inspector_status" => dp.set_inspector_status(status),
                "text_status" => dp.set_text_status(status),
                "ocr_status" => dp.set_ocr_status(status),
                "moldet_status" => dp.set_moldet_status(status, &[]),
                "index_status" => dp.set_index_status(status),
                _ => {}
            }
        }
        self.save_index();
        true
    }

    /// 更新文档的快速 MoldDet 扫描状态，并持久化 index。
    pub fn set_document_moldet(&mut self, doc_id: &str, status: &str, pages: &[usize]) -> bool {
        let Some(doc) = self.get_document_mut(doc_id) else {
            return false;
        };
        doc.moldet_status = status.to_string();
        doc.moldet_pages = pages.to_vec();
        if let Some(mut dp) = DocumentProject::load(&self.root, doc_id) {
            dp.set_moldet_status(status, pages);
        }
        self.save_index();
        true
    }

    /// 将外部文件添加到项目索引。
    ///
    /// - PDFs create a new isolated `DocumentProject` under `projects/<doc_id>/`.
    /// - Other files are copied into the project root and indexed by path.
    pub fn add_file(&mut self, source_path: &Path) -> Option<DocumentEntry> {
        let full = source_path.canonicalize().ok()?;
        if !full.exists() {
            return None;
        }

        let ext = full
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();

        if ext == "pdf" {
            // Create an isolated DocumentProject.
            let dp = DocumentProject::create(&self.root, &full).ok()?;
            let entry = DocumentEntry::from_document_project(&self.root, &dp);
            self.path_map
                .insert(dp.paths().source_path, entry.doc_id.clone());
            self.index.push(entry.clone());
            self.save_index();
            return Some(entry);
        }

        // Non-PDF: keep the old root-level indexing behaviour.
        if let Some(doc_id) = self.path_map.get(&full).cloned() {
            return self.index.iter().find(|d| d.doc_id == doc_id).cloned();
        }

        let doc_id = generate_uuid();
        let hash = sha256_file(&full).unwrap_or_default();
        let rel = full.strip_prefix(&self.root).unwrap_or(&full);
        let entry = DocumentEntry {
            doc_id: doc_id.clone(),
            path: rel.to_string_lossy().to_string(),
            source_path: Some(rel.to_string_lossy().to_string()),
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
            inspector_status: "pending".to_string(),
            text_status: "pending".to_string(),
            ocr_status: "not_processed".to_string(),
            ocr_hash: String::new(),
            moldet_status: "not_processed".to_string(),
            moldet_pages: Vec::new(),
            index_status: "pending".to_string(),
        };
        self.path_map.insert(full, doc_id);
        self.index.push(entry.clone());
        self.save_index();
        Some(entry)
    }

    /// 从项目索引中移除文档，并删除 DocumentProject 目录。
    pub fn remove_document(&mut self, doc_id: &str) -> bool {
        let pos = match self.index.iter().position(|d| d.doc_id == doc_id) {
            Some(p) => p,
            None => return false,
        };
        let entry = self.index.remove(pos);

        // 清理全局索引、向量、分子、摘要、缓存等残余数据。
        let source_filename = entry
            .source_path
            .as_deref()
            .or(Some(entry.path.as_str()))
            .and_then(|p| Path::new(p).file_name())
            .and_then(|n| n.to_str())
            .unwrap_or("")
            .to_string();
        let _ = Self::cleanup_document_data(
            &self.root,
            doc_id,
            &source_filename,
            entry.source_path.as_deref(),
            false,
        );

        if let Some(sp) = &entry.source_path {
            let dir = self.root.join(sp).parent().map(|p| p.to_path_buf());
            if let Some(dir) = dir {
                if dir.starts_with(self.root.join(PROJECTS_DIR)) && dir.exists() {
                    if let Err(e) = std::fs::remove_dir_all(&dir) {
                        log::warn!("Failed to remove document project dir {:?}: {}", dir, e);
                    }
                }
            }
            self.path_map.remove(&self.root.join(sp));
        }
        let full = self.root.join(&entry.path);
        self.path_map.remove(&full);
        self.save_index();
        true
    }

    /// 删除文档的所有派生数据。若 `keep_source` 为 true，保留 `source.pdf` 与 `.mbforge/index.json`。
    fn cleanup_document_data(
        root: &Path,
        doc_id: &str,
        source_filename: &str,
        source_path: Option<&str>,
        keep_source: bool,
    ) -> Result<(), String> {
        let mut errors: Vec<String> = Vec::new();

        // 1. 检测缓存（DocumentProject + 旧版全局）
        let dp_cache = DetectionCache::for_document_project(root, doc_id);
        if let Err(e) = dp_cache.clear_doc(doc_id) {
            errors.push(format!("detection cache (doc): {e}"));
        }
        let legacy_cache = DetectionCache::new(root);
        let _ = legacy_cache.clear_doc(doc_id);
        if !source_filename.is_empty() {
            let _ = legacy_cache.clear_doc(source_filename);
        }

        // 2. 分子数据库：按 source_doc 查 mol_id，再级联删除关系、检测、图片、分子。
        if let Ok(db) = MoleculeDatabase::open(root) {
            let targets: Vec<String> = [source_filename, doc_id]
                .iter()
                .filter(|s| !s.is_empty())
                .flat_map(|key| {
                    db.search_by_source(key)
                        .unwrap_or_default()
                        .into_iter()
                        .map(|r| r.mol_id)
                })
                .collect::<HashSet<_>>()
                .into_iter()
                .collect();

            if let Err(e) = db.delete_relations_for_mol_ids(&targets) {
                errors.push(format!("molecule relations: {e}"));
            }
            if let Err(e) = db.delete_detections_for_doc(doc_id) {
                errors.push(format!("molecule detections: {e}"));
            }
            for mol_id in &targets {
                if let Err(e) = db.delete_molecule(mol_id) {
                    errors.push(format!("molecule {mol_id}: {e}"));
                }
            }
        }

        // 3. 知识库：向量 + 文档树 + coref 标注 + 文件缓存
        let root_str = root.to_string_lossy().to_string();
        if let Ok(kb) = get_or_init_kb(&root_str) {
            if let Err(e) = kb.remove_document(doc_id) {
                errors.push(format!("knowledge base: {e}"));
            }
            if let Err(e) = kb.delete_figure_annotations(doc_id) {
                errors.push(format!("figure annotations: {e}"));
            }
            if let Some(sp) = source_path {
                let full = root.join(sp);
                if let Err(e) = kb.file_cache().invalidate(&full) {
                    errors.push(format!("file cache: {e}"));
                }
            }
        }

        // 4. 文档摘要
        if let Ok(sm) = SummaryManager::new(root) {
            if let Err(e) = sm.delete(doc_id) {
                errors.push(format!("summary: {e}"));
            }
        }

        // 5. 处理队列：直接通过 knowledge_base.db 同步连接删除该 doc 的任务和日志
        let kb_db_path = root.join(INDEX_DIR).join("knowledge_base.db");
        if kb_db_path.exists() {
            if let Ok(conn) = rusqlite::Connection::open(&kb_db_path) {
                let _ = conn.execute(
                    "DELETE FROM ingest_queue WHERE doc_id = ?1",
                    rusqlite::params![doc_id],
                );
                let _ = conn.execute(
                    "DELETE FROM ingest_logs WHERE doc_id = ?1",
                    rusqlite::params![doc_id],
                );
            }
        }

        // 6. 文件系统：保留或删除 DocumentProject 目录
        let project_dir = root.join(PROJECTS_DIR).join(doc_id);
        if project_dir.exists() {
            if keep_source {
                let paths = [
                    project_dir.join("text.md"),
                    project_dir.join("report.md"),
                    project_dir.join("cache"),
                    project_dir.join("molecules"),
                    project_dir.join("reports"),
                ];
                for p in &paths {
                    if p.exists() {
                        let res = if p.is_dir() {
                            std::fs::remove_dir_all(p)
                        } else {
                            std::fs::remove_file(p)
                        };
                        if let Err(e) = res {
                            errors.push(format!("fs cleanup {:?}: {e}", p));
                        }
                    }
                }
            } else if let Err(e) = std::fs::remove_dir_all(&project_dir) {
                errors.push(format!("remove project dir {:?}: {e}", project_dir));
            }
        }

        if errors.is_empty() {
            Ok(())
        } else {
            Err(format!(
                "cleanup_document_data for {} completed with errors: {}",
                doc_id,
                errors.join("; ")
            ))
        }
    }

    /// 彻底删除文档：清理所有数据，从索引移除，并删除 DocumentProject 目录。
    pub fn delete_document(&mut self, doc_id: &str) -> Result<(), String> {
        let entry = self
            .get_document(doc_id)
            .ok_or_else(|| format!("Document {doc_id} not found"))?;
        let source_filename = entry
            .source_path
            .as_deref()
            .or(Some(entry.path.as_str()))
            .and_then(|p| Path::new(p).file_name())
            .and_then(|n| n.to_str())
            .unwrap_or("")
            .to_string();
        let source_path = entry.source_path.clone();

        Self::cleanup_document_data(
            &self.root,
            doc_id,
            &source_filename,
            source_path.as_deref(),
            false,
        )?;

        let pos = self
            .index
            .iter()
            .position(|d| d.doc_id == doc_id)
            .ok_or_else(|| format!("Document {doc_id} not found"))?;
        let entry = self.index.remove(pos);
        if let Some(sp) = &entry.source_path {
            self.path_map.remove(&self.root.join(sp));
        }
        self.path_map.remove(&self.root.join(&entry.path));
        self.save_index();
        Ok(())
    }

    /// 重新读取文档：保留 source.pdf，清空派生数据，重置状态，并入队。
    pub fn reingest_document(&mut self, doc_id: &str) -> Result<(), String> {
        let entry = self
            .get_document(doc_id)
            .ok_or_else(|| format!("Document {doc_id} not found"))?;
        if entry.doc_type != "pdf" {
            return Err(format!("Only PDF documents can be re-ingested: {doc_id}"));
        }
        let source_path = entry
            .source_path
            .clone()
            .ok_or_else(|| format!("Document {doc_id} has no source_path"))?;
        let source_filename = Path::new(&source_path)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("")
            .to_string();

        // 清理派生数据，保留 source.pdf
        Self::cleanup_document_data(
            &self.root,
            doc_id,
            &source_filename,
            Some(&source_path),
            true,
        )?;

        // 重置 DocumentProject meta 状态
        if let Some(mut dp) = DocumentProject::load(&self.root, doc_id) {
            dp.meta.inspector_status = "pending".to_string();
            dp.meta.text_status = "pending".to_string();
            dp.meta.ocr_status = "pending".to_string();
            dp.meta.moldet_status = "not_processed".to_string();
            dp.meta.moldet_pages = Vec::new();
            dp.meta.index_status = "pending".to_string();
            let _ = dp.save_meta();
        }

        // 重置 Project index 状态
        self.set_document_status(doc_id, "inspector_status", "pending");
        self.set_document_status(doc_id, "text_status", "pending");
        self.set_document_status(doc_id, "ocr_status", "pending");
        self.set_document_status(doc_id, "moldet_status", "not_processed");
        self.set_document_status(doc_id, "index_status", "pending");

        Ok(())
    }

    /// Migrate legacy `papers/*.pdf` files into isolated DocumentProjects.
    ///
    /// For each PDF in `papers/` that does not already have a corresponding
    /// DocumentProject, creates one and adds a lightweight index entry.
    /// Returns warnings about migrated legacy files.
    pub fn migrate_legacy_papers(&mut self) -> Vec<ScanWarning> {
        let mut warnings = Vec::new();
        let papers_dir = self.root.join(PAPERS_DIR);
        if !papers_dir.exists() {
            return warnings;
        }

        // Build a set of hashes already known to the index. A legacy PDF whose
        // hash matches an existing DocumentProject is considered migrated.
        let known_hashes: std::collections::HashSet<String> = self
            .index
            .iter()
            .map(|d| d.hash.clone())
            .filter(|h| !h.is_empty())
            .collect();

        for entry in walkdir::WalkDir::new(&papers_dir)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            let path = entry.path();
            if !path.is_file() {
                continue;
            }
            let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
            if name.starts_with('.') {
                continue;
            }
            let ext = path
                .extension()
                .and_then(|e| e.to_str())
                .unwrap_or("")
                .to_lowercase();
            if ext != "pdf" {
                continue;
            }

            // Skip if this papers/ file has already been migrated.
            if let Ok(hash) = sha256_file(path) {
                if known_hashes.contains(&hash) {
                    continue;
                }
            }

            match DocumentProject::create(&self.root, path) {
                Ok(dp) => {
                    let entry = DocumentEntry::from_document_project(&self.root, &dp);
                    self.path_map
                        .insert(dp.paths().source_path, entry.doc_id.clone());
                    self.index.push(entry);
                    warnings.push(ScanWarning {
                        path: path
                            .strip_prefix(&self.root)
                            .unwrap_or(path)
                            .to_string_lossy()
                            .to_string(),
                        reason: "已自动迁移到 projects/<doc_id>/ 文档项目".to_string(),
                        folder: PAPERS_DIR.to_string(),
                    });
                }
                Err(e) => {
                    log::error!("Failed to migrate legacy PDF {:?}: {}", path, e);
                    warnings.push(ScanWarning {
                        path: path
                            .strip_prefix(&self.root)
                            .unwrap_or(path)
                            .to_string_lossy()
                            .to_string(),
                        reason: format!("迁移失败: {e}"),
                        folder: PAPERS_DIR.to_string(),
                    });
                }
            }
        }

        self.save_index();
        warnings
    }

    pub fn save_index(&self) {
        let index = ProjectIndex {
            version: PROJECT_FORMAT_VERSION,
            updated_at: now_rfc3339(),
            documents: self.index.clone(),
        };
        let _ = mbforge_infra::helpers::save_json(&self.meta_dir.join(INDEX_FILE), &index);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use mbforge_infra::config::constants::PROJECT_SOURCE_FILE;
    use std::io::Write;
    use tempfile::TempDir;

    fn make_pdf(dir: &Path, name: &str, content: &[u8]) -> PathBuf {
        let path = dir.join(name);
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(content).unwrap();
        path
    }

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

    #[test]
    fn test_migrate_legacy_papers() {
        let tmp = TempDir::new().unwrap();
        let root = tmp.path();

        // Create a legacy v1 project manually.
        std::fs::create_dir_all(root.join(PAPERS_DIR)).unwrap();
        std::fs::create_dir_all(root.join(PROJECT_META_DIR)).unwrap();
        let version_path = root.join(PROJECT_META_DIR).join("version.json");
        mbforge_infra::helpers::save_json(&version_path, &serde_json::json!({ "version": 1 }))
            .unwrap();
        mbforge_infra::helpers::save_json(
            &root.join(PROJECT_META_DIR).join(INDEX_FILE),
            &serde_json::json!({ "documents": [] }),
        )
        .unwrap();

        let _pdf = make_pdf(&root.join(PAPERS_DIR), "legacy.pdf", b"%PDF-1.4 legacy");

        let mut project = Project::open(root).expect("open should succeed");

        // Migration runs automatically during open for v1 projects.
        let docs: Vec<_> = project.list_documents().to_vec();
        assert_eq!(docs.len(), 1);

        // Calling migrate again should be idempotent.
        let warnings = project.migrate_legacy_papers();
        assert!(
            warnings.is_empty(),
            "re-migration should produce no warnings"
        );
        assert_eq!(project.list_documents().len(), 1);
        assert_eq!(docs[0].title, "legacy");
        assert_eq!(docs[0].doc_type, "pdf");
        assert!(docs[0].source_path.as_ref().unwrap().contains(PROJECTS_DIR));

        // Source file copied into projects/<doc_id>/source.pdf.
        let source = project.get_document_source_path(&docs[0].doc_id).unwrap();
        assert!(source.exists());
        assert!(source.to_string_lossy().contains(PROJECT_SOURCE_FILE));

        // Re-opening should keep the migrated project and not duplicate it.
        let project2 = Project::open(root).expect("re-open should succeed");
        assert_eq!(project2.list_documents().len(), 1);
    }

    #[test]
    fn test_add_pdf_creates_document_project() {
        let tmp = TempDir::new().unwrap();
        let root = tmp.path();

        let mut project = Project::create(root).expect("create should succeed");
        let source_dir = root.join("incoming");
        std::fs::create_dir_all(&source_dir).unwrap();
        let pdf = make_pdf(&source_dir, "new.pdf", b"%PDF-1.4 new");

        let entry = project.add_file(&pdf).expect("add_file should succeed");
        assert_eq!(entry.title, "new");
        assert_eq!(entry.doc_type, "pdf");
        assert!(entry.source_path.as_ref().unwrap().contains(PROJECTS_DIR));

        let source = root.join(entry.source_path.as_ref().unwrap());
        assert!(source.exists());
    }

    #[test]
    fn test_remove_document_cleans_orphaned_data() {
        use crate::document::detection_cache::{
            Detection, DetectionCache, PageDetection, DETECTION_CACHE_SCHEMA_VERSION,
        };
        use crate::document::summary::{DocumentSummary, SummaryManager};

        let tmp = TempDir::new().unwrap();
        let root = tmp.path();

        let mut project = Project::create(root).expect("create should succeed");
        let source_dir = root.join("incoming");
        std::fs::create_dir_all(&source_dir).unwrap();
        let pdf = make_pdf(&source_dir, "gc.pdf", b"%PDF-1.4 gc");
        let entry = project.add_file(&pdf).expect("add_file should succeed");
        let doc_id = entry.doc_id.clone();

        // 写入摘要
        let sm = SummaryManager::new(root).unwrap();
        let mut summary = DocumentSummary::new(&doc_id);
        summary.l0_abstract = "abstract".into();
        sm.save(&summary).unwrap();
        assert!(sm.load(&doc_id).is_some());

        // 写入检测缓存
        let cache = DetectionCache::for_document_project(root, &doc_id);
        let page_det = PageDetection {
            doc_id: doc_id.clone(),
            page: 1,
            pdf_hash: "hash".into(),
            mtime: 0.0,
            detected_at: 0.0,
            schema_version: DETECTION_CACHE_SCHEMA_VERSION,
            detections: vec![Detection {
                bbox_pdf: [0.0, 0.0, 10.0, 10.0],
                smiles: None,
                esmiles: None,
                conf_moldet: 0.9,
                conf_molscribe: 0.0,
                vlm_caption: None,
                vlm_esmiles: None,
                crop_relpath: None,
                is_quick_scan: true,
            }],
        };
        cache.put(&page_det).unwrap();
        assert!(cache.get(&doc_id, 1, "hash").is_some());

        // 写入分子记录
        use crate::molecule::molecule_store::MoleculeDatabase;
        let mol_db = MoleculeDatabase::open(root).unwrap();
        let mut rec = crate::molecule::molecule_store::MoleculeRecord::new("m1", "CCO");
        rec.source_doc = doc_id.clone();
        mol_db.add_molecule(&rec).unwrap();
        assert_eq!(mol_db.search_by_source(&doc_id).unwrap().len(), 1);

        // 删除文档
        assert!(project.remove_document(&doc_id));
        assert!(project.get_document(&doc_id).is_none());

        // 摘要、检测缓存、项目目录、分子记录都应被清理
        assert!(sm.load(&doc_id).is_none());
        assert!(cache.get(&doc_id, 1, "hash").is_none());
        assert!(!root.join(PROJECTS_DIR).join(&doc_id).exists());
        assert!(mol_db.search_by_source(&doc_id).unwrap().is_empty());
    }

    #[test]
    fn test_reingest_document_resets_status() {
        let tmp = TempDir::new().unwrap();
        let root = tmp.path();

        let mut project = Project::create(root).expect("create should succeed");
        let source_dir = root.join("incoming");
        std::fs::create_dir_all(&source_dir).unwrap();
        let pdf = make_pdf(&source_dir, "reingest.pdf", b"%PDF-1.4 reingest");
        let entry = project.add_file(&pdf).expect("add_file should succeed");
        let doc_id = entry.doc_id.clone();

        // 模拟处理完成状态
        project.set_document_status(&doc_id, "inspector_status", "text_based");
        project.set_document_status(&doc_id, "text_status", "done");
        project.set_document_status(&doc_id, "index_status", "done");

        // 写入派生文件
        let dp_dir = root.join(PROJECTS_DIR).join(&doc_id);
        std::fs::write(dp_dir.join("text.md"), "# text").unwrap();
        std::fs::write(dp_dir.join("report.md"), "# report").unwrap();

        // 重新读取
        project.reingest_document(&doc_id).unwrap();

        let doc = project.get_document(&doc_id).unwrap();
        assert_eq!(doc.inspector_status, "pending");
        assert_eq!(doc.text_status, "pending");
        assert_eq!(doc.index_status, "pending");
        assert_eq!(doc.ocr_status, "pending");
        assert_eq!(doc.moldet_status, "not_processed");

        // source.pdf 必须保留，派生文件应被清理
        assert!(dp_dir.join(PROJECT_SOURCE_FILE).exists());
        assert!(!dp_dir.join("text.md").exists());
        assert!(!dp_dir.join("report.md").exists());
    }
}
