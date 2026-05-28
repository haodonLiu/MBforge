use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

use super::constants::{MEMORY_DIR, PROJECT_META_DIR};

pub const CATEGORIES: &[&str] = &["profile", "preferences", "entities", "events", "cases", "patterns"];

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryEntry {
    pub category: String,
    pub key: String,
    pub content: String,
    #[serde(default = "default_confidence")]
    pub confidence: f64,
    #[serde(default)]
    pub source: String,
    #[serde(default = "default_timestamp")]
    pub created_at: String,
    #[serde(default = "default_timestamp")]
    pub updated_at: String,
    #[serde(default)]
    pub access_count: u32,
}

fn default_confidence() -> f64 { 1.0 }
fn default_timestamp() -> String { chrono::Utc::now().to_rfc3339() }

pub struct MemoryManager {
    memory_dir: PathBuf,
    cache: HashMap<String, Vec<MemoryEntry>>,
}

impl MemoryManager {
    pub fn new(project_root: &Path) -> Self {
        let memory_dir = project_root.join(PROJECT_META_DIR).join(MEMORY_DIR);
        let _ = std::fs::create_dir_all(&memory_dir);
        let mut mgr = Self { memory_dir, cache: HashMap::new() };
        mgr.load_all();
        mgr
    }

    fn category_path(&self, category: &str) -> PathBuf {
        self.memory_dir.join(format!("{}.json", category))
    }

    fn load_all(&mut self) {
        for cat in CATEGORIES {
            let path = self.category_path(cat);
            let entries: Vec<MemoryEntry> = super::helpers::load_json(&path).unwrap_or_default();
            self.cache.insert(cat.to_string(), entries);
        }
    }

    fn save_category(&self, category: &str) {
        if let Some(entries) = self.cache.get(category) {
            let _ = super::helpers::save_json(&self.category_path(category), entries);
        }
    }

    pub fn add(&mut self, entry: MemoryEntry) {
        let cat = entry.category.clone();
        self.cache.entry(cat.clone()).or_default().push(entry);
        self.save_category(&cat);
    }

    pub fn get(&self, category: &str) -> &[MemoryEntry] {
        match self.cache.get(category) {
            Some(v) => v.as_slice(),
            None => &[],
        }
    }

    pub fn search(&self, query: &str) -> Vec<&MemoryEntry> {
        let q = query.to_lowercase();
        self.cache.values()
            .flat_map(|entries| entries.iter())
            .filter(|e| e.content.to_lowercase().contains(&q) || e.key.to_lowercase().contains(&q))
            .collect()
    }

    pub fn get_all_text(&self) -> String {
        let mut lines = Vec::new();
        for cat in CATEGORIES {
            if let Some(entries) = self.cache.get(*cat) {
                for e in entries {
                    lines.push(format!("[{}] {}: {}", cat, e.key, e.content));
                }
            }
        }
        lines.join("\n")
    }

    pub fn count(&self) -> usize {
        self.cache.values().map(|v| v.len()).sum()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_memory_manager() {
        let dir = tempfile::tempdir().unwrap();
        let mut mgr = MemoryManager::new(dir.path());
        mgr.add(MemoryEntry {
            category: "profile".into(),
            key: "user_name".into(),
            content: "Alice".into(),
            ..Default::default()
        });
        assert_eq!(mgr.count(), 1);
        assert!(!mgr.get_all_text().is_empty());
    }
}
