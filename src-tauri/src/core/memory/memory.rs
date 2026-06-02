use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

use super::super::constants::{MEMORY_DIR, PROJECT_META_DIR};

pub const CATEGORIES: &[&str] = &["profile", "preferences", "entities", "events", "cases", "patterns"];

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct MemoryEntry {
    pub category: String,
    pub key: String,
    pub content: String,
    #[serde(default = "default_confidence")]
    pub confidence: f64,
    #[serde(default)]
    pub source: String,
    #[serde(default = "super::super::helpers::now_rfc3339")]
    pub created_at: String,
    #[serde(default = "super::super::helpers::now_rfc3339")]
    pub updated_at: String,
    #[serde(default)]
    pub access_count: u32,
}

fn default_confidence() -> f64 { 1.0 }

pub struct MemoryManager {
    memory_dir: PathBuf,
    cache: HashMap<String, Vec<MemoryEntry>>,
    turn_counter: u32,
    extract_interval: u32,
}

impl MemoryManager {
    pub fn new(project_root: &Path) -> Self {
        let memory_dir = project_root.join(PROJECT_META_DIR).join(MEMORY_DIR);
        let _ = std::fs::create_dir_all(&memory_dir);
        let mut mgr = Self {
            memory_dir,
            cache: HashMap::new(),
            turn_counter: 0,
            extract_interval: 5, // 每 5 轮提取一次
        };
        mgr.load_all();
        mgr
    }

    /// 记录一轮对话，返回是否应该触发提取
    pub fn record_turn(&mut self) -> bool {
        self.turn_counter += 1;
        self.turn_counter >= self.extract_interval
    }

    /// 重置计数器（提取完成后调用）
    pub fn reset_turn_counter(&mut self) {
        self.turn_counter = 0;
    }

    fn category_path(&self, category: &str) -> PathBuf {
        self.memory_dir.join(format!("{}.json", category))
    }

    fn load_all(&mut self) {
        for cat in CATEGORIES {
            let path = self.category_path(cat);
            let entries: Vec<MemoryEntry> = super::super::helpers::load_json(&path).unwrap_or_default();
            self.cache.insert(cat.to_string(), entries);
        }
    }

    fn save_category(&self, category: &str) {
        if let Some(entries) = self.cache.get(category) {
            let _ = super::super::helpers::save_json(&self.category_path(category), entries);
        }
    }

    pub fn add(&mut self, entry: MemoryEntry) {
        let cat = entry.category.clone();
        // Update existing entry with same key
        if let Some(entries) = self.cache.get_mut(&cat) {
            if let Some(existing) = entries.iter_mut().find(|e| e.key == entry.key) {
                existing.content = entry.content;
                existing.confidence = entry.confidence;
                existing.source = entry.source;
                existing.updated_at = super::super::helpers::now_rfc3339();
                self.save_category(&cat);
                return;
            }
        }
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

    /// 获取用户画像文本（profile + preferences + entities）
    pub fn get_user_profile_text(&self) -> String {
        let mut lines = Vec::new();
        for cat in &["profile", "preferences", "entities"] {
            if let Some(entries) = self.cache.get(*cat) {
                if !entries.is_empty() {
                    lines.push(format!("[{}]", cat));
                    for e in entries {
                        lines.push(format!("  {}: {}", e.key, e.content));
                    }
                }
            }
        }
        lines.join("\n")
    }

    /// 获取 Agent 学习记忆文本（cases + patterns）
    pub fn get_agent_memory_text(&self) -> String {
        let mut lines = Vec::new();
        for cat in &["cases", "patterns"] {
            if let Some(entries) = self.cache.get(*cat) {
                if !entries.is_empty() {
                    lines.push(format!("[{}]", cat));
                    for e in entries {
                        lines.push(format!("  {}: {}", e.key, e.content));
                    }
                }
            }
        }
        lines.join("\n")
    }

    pub fn count(&self) -> usize {
        self.cache.values().map(|v| v.len()).sum()
    }

    /// 通过 sidecar LLM 从对话中自动提取记忆
    pub async fn extract_from_conversation(&mut self, messages: &[super::super::context::Message], sidecar_url: &str) {
        if messages.len() < 2 {
            return;
        }
        // 取最近 10 条对话
        let recent: Vec<String> = messages.iter().rev().take(10).rev()
            .map(|m| format!("{}: {}", m.role, &m.content[..m.content.len().min(500)]))
            .collect();
        let conversation = recent.join("\n");

        let prompt = format!(
            "请分析以下对话，提取有价值的记忆条目。按 JSON 数组格式输出，每个条目包含：\n\
             - category: profile/preferences/entities/events/cases/patterns\n\
             - key: 简短的键名\n\
             - content: 具体内容\n\
             - confidence: 0.0-1.0\n\n\
             只输出 JSON 数组，不要其他说明。\n\n\
             对话：\n{}",
            conversation
        );

        let body = serde_json::json!({
            "messages": [
                {"role": "system", "content": "你是一位记忆提取专家。"},
                {"role": "user", "content": prompt}
            ]
        });

        let url = format!("{}/api/v1/llm/chat", sidecar_url.trim_end_matches('/'));
        let client = super::super::http::client_30s();

        let resp = match client.post(&url)
            .header("Content-Type", "application/json")
            .json(&body)
            .send()
            .await {
                Ok(r) => r,
                Err(_) => return,
            };

        let text = match resp.text().await {
            Ok(t) => t,
            Err(_) => return,
        };

        let val: serde_json::Value = match serde_json::from_str(&text) {
            Ok(v) => v,
            Err(_) => return,
        };

        let content = val["choices"][0]["message"]["content"]
            .as_str()
            .unwrap_or("");

        // 提取 JSON 数组
        if let Some(start) = content.find('[') {
            if let Some(end) = content.rfind(']') {
                let json_str = &content[start..=end];
                if let Ok(items) = serde_json::from_str::<Vec<serde_json::Value>>(json_str) {
                    for item in items {
                        let cat = item["category"].as_str().unwrap_or("");
                        if CATEGORIES.contains(&cat) {
                            self.add(MemoryEntry {
                                category: cat.to_string(),
                                key: item["key"].as_str().unwrap_or("unknown").to_string(),
                                content: item["content"].as_str().unwrap_or("").to_string(),
                                confidence: item["confidence"].as_f64().unwrap_or(0.5),
                                source: "auto_extraction".into(),
                                ..Default::default()
                            });
                        }
                    }
                }
            }
        }
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

    #[test]
    fn test_user_profile_text() {
        let dir = tempfile::tempdir().unwrap();
        let mut mgr = MemoryManager::new(dir.path());
        mgr.add(MemoryEntry {
            category: "profile".into(),
            key: "name".into(),
            content: "Bob".into(),
            ..Default::default()
        });
        let text = mgr.get_user_profile_text();
        assert!(text.contains("[profile]"));
        assert!(text.contains("name: Bob"));
    }

    #[test]
    fn test_update_existing() {
        let dir = tempfile::tempdir().unwrap();
        let mut mgr = MemoryManager::new(dir.path());
        mgr.add(MemoryEntry {
            category: "profile".into(),
            key: "name".into(),
            content: "Alice".into(),
            ..Default::default()
        });
        mgr.add(MemoryEntry {
            category: "profile".into(),
            key: "name".into(),
            content: "Bob".into(),
            ..Default::default()
        });
        assert_eq!(mgr.count(), 1);
        assert_eq!(mgr.get("profile")[0].content, "Bob");
    }
}
