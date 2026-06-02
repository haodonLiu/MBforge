use serde_json::Value;
use std::fs;
use std::path::Path;

use crate::core::constants::{INDEX_FILE, PROJECT_FORMAT_VERSION, PROJECT_META_DIR, SETTINGS_FILE};
use crate::core::helpers::{now_rfc3339, save_json};

pub struct ProjectMigrator;

impl ProjectMigrator {
    /// Read the project format version from `.mbforge/version`.
    /// Returns 0 if the file does not exist (legacy project).
    pub fn read_version(project_root: &Path) -> u32 {
        let version_path = project_root.join(PROJECT_META_DIR).join("version");
        match fs::read_to_string(&version_path) {
            Ok(content) => content.trim().parse::<u32>().unwrap_or(0),
            Err(_) => 0,
        }
    }

    /// Write the project format version.
    pub fn write_version(
        project_root: &Path,
        version: u32,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let version_path = project_root.join(PROJECT_META_DIR).join("version");
        fs::write(&version_path, version.to_string())?;
        Ok(())
    }

    /// Migrate a project from its current version to the latest version.
    /// Automatically backs up `.mbforge/` before making changes.
    pub fn migrate(project_root: &Path) -> Result<u32, Box<dyn std::error::Error>> {
        let from_version = Self::read_version(project_root);
        let target_version = PROJECT_FORMAT_VERSION;

        if from_version >= target_version {
            return Ok(from_version);
        }

        // If this is a brand-new project (version 0 and no index.json), just stamp the version.
        let meta_dir = project_root.join(PROJECT_META_DIR);
        if from_version == 0 && !meta_dir.join(INDEX_FILE).exists() {
            Self::write_version(project_root, target_version)?;
            return Ok(target_version);
        }

        // Backup existing metadata before migration.
        let timestamp = chrono::Utc::now().format("%Y%m%d_%H%M%S").to_string();
        let backup_dir = project_root.join(format!("{}.backup.{}", PROJECT_META_DIR, timestamp));
        if meta_dir.exists() {
            copy_dir_all(&meta_dir, &backup_dir)?;
            log::info!(
                "Backed up .mbforge to {:?} before migration v{} -> v{}",
                backup_dir,
                from_version,
                target_version
            );
        }

        // Run migration chain.
        let mut current = from_version;
        while current < target_version {
            let next = current + 1;
            log::info!("Migrating project from v{} to v{}", current, next);
            Self::run_migration(project_root, current, next)?;
            current = next;
        }

        Self::write_version(project_root, target_version)?;
        Ok(target_version)
    }

    /// Recovery mode: called when migration itself fails or metadata is severely corrupted.
    /// Moves the old `.mbforge/` to `.mbforge.corrupted.{timestamp}/` and rebuilds defaults.
    pub fn recover(project_root: &Path) -> Result<(), Box<dyn std::error::Error>> {
        let meta_dir = project_root.join(PROJECT_META_DIR);
        let timestamp = chrono::Utc::now().format("%Y%m%d_%H%M%S").to_string();
        let corrupted_dir =
            project_root.join(format!("{}.corrupted.{}", PROJECT_META_DIR, timestamp));

        if meta_dir.exists() {
            copy_dir_all(&meta_dir, &corrupted_dir)?;
            fs::remove_dir_all(&meta_dir)?;
            log::warn!("Moved corrupted .mbforge to {:?}", corrupted_dir);
        }

        fs::create_dir_all(&meta_dir)?;

        // Write default settings.
        let settings_path = meta_dir.join(SETTINGS_FILE);
        let default_settings = Self::default_settings(project_root);
        save_json(&settings_path, &default_settings)?;

        // Write current version.
        Self::write_version(project_root, PROJECT_FORMAT_VERSION)?;

        // Write empty index.
        let index_path = meta_dir.join(INDEX_FILE);
        let empty_index = serde_json::json!({
            "version": PROJECT_FORMAT_VERSION,
            "documents": []
        });
        save_json(&index_path, &empty_index)?;

        log::info!("Recovered project metadata at {:?}", project_root);
        Ok(())
    }

    // ------------------------------------------------------------------
    // Private helpers
    // ------------------------------------------------------------------

    fn run_migration(
        project_root: &Path,
        from: u32,
        to: u32,
    ) -> Result<(), Box<dyn std::error::Error>> {
        match (from, to) {
            (0, 1) => Self::migrate_v0_to_v1(project_root),
            _ => Err(format!("No migration path from v{} to v{}", from, to).into()),
        }
    }

    /// v0 -> v1:
    /// - Stamp version into index.json if missing.
    /// - Ensure settings.json exists with default values.
    fn migrate_v0_to_v1(project_root: &Path) -> Result<(), Box<dyn std::error::Error>> {
        let meta_dir = project_root.join(PROJECT_META_DIR);

        // Heal index.json: add version field, or delete if unreadable so scan_files rebuilds it.
        let index_path = meta_dir.join(INDEX_FILE);
        if index_path.exists() {
            match fs::read_to_string(&index_path) {
                Ok(content) => {
                    if let Ok(mut value) = serde_json::from_str::<Value>(&content) {
                        if value.get("version").is_none() {
                            value["version"] = 1.into();
                            value["migrated_at"] = now_rfc3339().into();
                            let _ = fs::write(&index_path, serde_json::to_string_pretty(&value)?);
                        }
                    } else {
                        log::warn!("index.json corrupted during migration, will rebuild from scan");
                        let _ = fs::remove_file(&index_path);
                    }
                }
                Err(e) => log::warn!("Cannot read index.json for migration: {}", e),
            }
        }

        // Ensure settings.json exists.
        let settings_path = meta_dir.join(SETTINGS_FILE);
        if !settings_path.exists() {
            let default = Self::default_settings(project_root);
            save_json(&settings_path, &default)?;
        }

        Ok(())
    }

    fn default_settings(project_root: &Path) -> Value {
        serde_json::json!({
            "name": project_root
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("Untitled"),
            "description": "",
            "created_at": now_rfc3339(),
            "llm_model": "default",
            "embed_model": "default",
            "auto_index": true,
            "auto_process": true,
            "pdf_ocr_enabled": true,
            "pdf_extract_molecules": true,
            "theme_override": "system",
            "workflows_enabled": {
                "generation": false,
                "docking": false,
                "qsar": false,
                "md": false
            }
        })
    }
}

/// Simple recursive directory copy (no external dependencies).
fn copy_dir_all(src: impl AsRef<Path>, dst: impl AsRef<Path>) -> std::io::Result<()> {
    fs::create_dir_all(&dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let ty = entry.file_type()?;
        if ty.is_dir() {
            copy_dir_all(entry.path(), dst.as_ref().join(entry.file_name()))?;
        } else {
            fs::copy(entry.path(), dst.as_ref().join(entry.file_name()))?;
        }
    }
    Ok(())
}
