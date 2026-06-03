//! L1 语义缓存 — 基于 SHA-256 精确哈希的查询结果缓存
//!
//! 缓存搜索结果以避免重复查询。仅使用 L1（精确哈希匹配）。
//! L2（embedding 相似度）已移除 — LanceDB 自身处理语义搜索。

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheEntry {
    pub query_hash: String,
    pub query_text: String,
    pub results: Vec<serde_json::Value>,
    pub project_root: String,
    pub created_at: f64,
    pub hit_count: u64,
    pub last_hit: f64,
}

impl CacheEntry {
    pub fn is_expired(&self, ttl: f64) -> bool {
        let now = now_secs();
        (now - self.created_at) > ttl
    }

    pub fn update_hit(&mut self) {
        self.hit_count += 1;
        self.last_hit = now_secs();
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SemanticCacheConfig {
    pub enabled: bool,
    pub max_size: usize,
    pub ttl_seconds: f64,
    pub disk_persist: bool,
}

impl Default for SemanticCacheConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            max_size: 1000,
            ttl_seconds: 3600.0,
            disk_persist: true,
        }
    }
}

struct CacheInner {
    entries: HashMap<String, CacheEntry>,
    lru: VecDeque<String>,
}

pub struct SemanticCache {
    project_root: PathBuf,
    config: SemanticCacheConfig,
    cache: Mutex<CacheInner>,
    cache_path: PathBuf,
}

fn now_secs() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

fn hash_query(query: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(query.as_bytes());
    let result = hasher.finalize();
    result[..16].iter().map(|b| format!("{:02x}", b)).collect()
}

impl SemanticCache {
    pub fn new(project_root: &Path, config: SemanticCacheConfig) -> Self {
        let cache_path = project_root
            .join(".mbforge")
            .join("cache")
            .join("semantic_cache.json");

        if let Some(parent) = cache_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }

        let cache = Self {
            project_root: project_root.to_path_buf(),
            config,
            cache: Mutex::new(CacheInner {
                entries: HashMap::new(),
                lru: VecDeque::new(),
            }),
            cache_path: cache_path.clone(),
        };

        if cache.config.disk_persist {
            cache.load_from_disk();
        }

        cache
    }

    /// L1 exact hash match
    pub fn get_l1(&self, query: &str) -> Option<Vec<serde_json::Value>> {
        if !self.config.enabled {
            return None;
        }
        let key = hash_query(query);
        let mut inner = self.cache.lock().unwrap_or_else(|e| e.into_inner());

        let expired = inner
            .entries
            .get(&key)
            .map_or(false, |e| e.is_expired(self.config.ttl_seconds));

        if expired {
            inner.entries.remove(&key);
            retain_lru(&mut inner.lru, &key);
            return None;
        }

        let results = inner.entries.get(&key).map(|e| e.results.clone());
        if results.is_some() {
            if let Some(entry) = inner.entries.get_mut(&key) {
                entry.update_hit();
            }
            move_to_back(&mut inner.lru, &key);
        }
        results
    }

    /// Store results in cache
    pub fn store(&self, query: &str, results: Vec<serde_json::Value>) {
        if !self.config.enabled || results.is_empty() {
            return;
        }
        let key = hash_query(query);
        let now = now_secs();

        let entry = CacheEntry {
            query_hash: key.clone(),
            query_text: query.to_string(),
            results,
            project_root: self.project_root.to_string_lossy().to_string(),
            created_at: now,
            hit_count: 1,
            last_hit: now,
        };

        let mut inner = self.cache.lock().unwrap_or_else(|e| e.into_inner());

        if inner.entries.len() >= self.config.max_size && !inner.entries.contains_key(&key) {
            if let Some(evicted) = inner.lru.pop_front() {
                inner.entries.remove(&evicted);
            }
        }

        inner.entries.insert(key.clone(), entry);
        inner.lru.push_back(key);

        drop(inner);

        if self.config.disk_persist {
            self.save_to_disk();
        }
    }

    fn load_from_disk(&self) {
        let data: HashMap<String, serde_json::Value> =
            match std::fs::read_to_string(&self.cache_path) {
                Ok(c) => serde_json::from_str(&c).unwrap_or_default(),
                Err(_) => return,
            };

        let mut inner = self.cache.lock().unwrap_or_else(|e| e.into_inner());
        for (key, item) in data {
            if let Ok(mut entry) = serde_json::from_value::<CacheEntry>(item) {
                // 清理旧格式中的 embedding 字段（反序列化时忽略）
                // 迁移：重新存储时不写入 embedding
                inner.entries.insert(key.clone(), entry);
                inner.lru.push_back(key);
            }
        }
    }

    fn save_to_disk(&self) {
        let inner = self.cache.lock().unwrap_or_else(|e| e.into_inner());
        if let Ok(data) = serde_json::to_string(&inner.entries) {
            let _ = std::fs::write(&self.cache_path, data);
        }
    }

    pub fn clear(&self) {
        let mut inner = self.cache.lock().unwrap_or_else(|e| e.into_inner());
        inner.entries.clear();
        inner.lru.clear();
        drop(inner);
        if self.cache_path.exists() {
            let _ = std::fs::remove_file(&self.cache_path);
        }
    }

    pub fn stats(&self) -> serde_json::Value {
        let inner = self.cache.lock().unwrap_or_else(|e| e.into_inner());
        let total_hits: u64 = inner.entries.values().map(|e| e.hit_count).sum();
        serde_json::json!({
            "entries": inner.entries.len(),
            "total_hits": total_hits,
            "max_size": self.config.max_size,
            "ttl_seconds": self.config.ttl_seconds,
        })
    }
}

fn move_to_back(lru: &mut VecDeque<String>, key: &str) {
    if let Some(pos) = lru.iter().position(|k| k == key) {
        if let Some(val) = lru.remove(pos) {
            lru.push_back(val);
        }
    }
}

fn retain_lru(lru: &mut VecDeque<String>, key: &str) {
    lru.retain(|k| k != key);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_l1_cache_hit() {
        let dir = tempfile::tempdir().unwrap();
        let sc = SemanticCache::new(dir.path(), SemanticCacheConfig::default());

        assert!(sc.get_l1("test").is_none());

        sc.store("test", vec![serde_json::json!({"text": "result"})]);
        let results = sc.get_l1("test").unwrap();
        assert_eq!(results.len(), 1);
    }

    #[test]
    fn test_l1_cache_miss_different_query() {
        let dir = tempfile::tempdir().unwrap();
        let sc = SemanticCache::new(dir.path(), SemanticCacheConfig::default());

        sc.store("query1", vec![serde_json::json!({"text": "result1"})]);
        assert!(sc.get_l1("query2").is_none());
    }
}
