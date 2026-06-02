use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use super::super::embedding::Embedder;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheEntry {
    pub query_hash: String,
    pub query_text: String,
    pub embedding: Option<Vec<f32>>,
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
    pub similarity_threshold: f64,
    pub disk_persist: bool,
    pub hot_query_threshold: u64,
}

impl Default for SemanticCacheConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            max_size: 1000,
            ttl_seconds: 3600.0,
            similarity_threshold: 0.95,
            disk_persist: true,
            hot_query_threshold: 3,
        }
    }
}

struct CacheInner {
    entries: HashMap<String, CacheEntry>,
    lru: VecDeque<String>,
    hot_queries: Vec<String>,
}

pub struct SemanticCache {
    project_root: PathBuf,
    embedder: Option<Embedder>,
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
    pub fn new(
        project_root: &Path,
        embedder: Option<Embedder>,
        config: SemanticCacheConfig,
    ) -> Self {
        let cache_path = project_root
            .join(".mbforge")
            .join("cache")
            .join("semantic_cache.json");

        if let Some(parent) = cache_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }

        let cache = Self {
            project_root: project_root.to_path_buf(),
            embedder,
            config,
            cache: Mutex::new(CacheInner {
                entries: HashMap::new(),
                lru: VecDeque::new(),
                hot_queries: Vec::new(),
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

    /// L2 embedding similarity match
    pub fn get_l2(&self, query: &str) -> Option<Vec<serde_json::Value>> {
        if !self.config.enabled {
            return None;
        }
        let query_emb = self.embedder.as_ref()?.embed_single(query).ok()?;

        let mut inner = self.cache.lock().unwrap_or_else(|e| e.into_inner());
        let ttl = self.config.ttl_seconds;
        let threshold = self.config.similarity_threshold;

        let mut best_key: Option<String> = None;
        let mut best_sim = 0.0f64;

        for (key, entry) in &inner.entries {
            if let Some(ref emb) = entry.embedding {
                if entry.is_expired(ttl) {
                    continue;
                }
                let sim = cosine(query_emb.as_slice(), emb.as_slice());
                if sim > best_sim {
                    best_sim = sim;
                    best_key = Some(key.clone());
                }
            }
        }

        if let Some(ref key) = best_key {
            if best_sim >= threshold {
                let results = inner.entries.get(key).map(|e| e.results.clone());
                if results.is_some() {
                    if let Some(entry) = inner.entries.get_mut(key) {
                        entry.update_hit();
                    }
                    move_to_back(&mut inner.lru, key);
                    return results;
                }
            }
        }

        None
    }

    /// L3 hot query prefetch
    pub fn prefetch_hot_queries(&self) {
        let mut inner = self.cache.lock().unwrap_or_else(|e| e.into_inner());
        let threshold = self.config.hot_query_threshold;
        inner.hot_queries = inner
            .entries
            .iter()
            .filter(|(_, e)| e.hit_count >= threshold)
            .map(|(k, _)| k.clone())
            .collect();
    }

    /// Store results in cache
    pub fn store(&self, query: &str, results: Vec<serde_json::Value>) {
        if !self.config.enabled || results.is_empty() {
            return;
        }
        let key = hash_query(query);

        let embedding = if self.config.similarity_threshold > 0.0 {
            self.embedder
                .as_ref()
                .and_then(|e| e.embed_single(query).ok())
        } else {
            None
        };

        let now = now_secs();

        let entry = CacheEntry {
            query_hash: key.clone(),
            query_text: query.to_string(),
            embedding,
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
            if let Ok(entry) = serde_json::from_value::<CacheEntry>(item) {
                inner.entries.insert(key.clone(), entry);
                inner.lru.push_back(key);
            }
        }
        drop(inner);

        self.prefetch_hot_queries();
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
        inner.hot_queries.clear();
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
            "hot_queries": inner.hot_queries.len(),
            "max_size": self.config.max_size,
            "ttl_seconds": self.config.ttl_seconds,
            "similarity_threshold": self.config.similarity_threshold,
        })
    }
}

fn cosine(a: &[f32], b: &[f32]) -> f64 {
    let dot: f64 = a
        .iter()
        .zip(b.iter())
        .map(|(x, y)| (*x as f64) * (*y as f64))
        .sum();
    let na: f64 = a.iter().map(|x| (*x as f64).powi(2)).sum::<f64>().sqrt();
    let nb: f64 = b.iter().map(|x| (*x as f64).powi(2)).sum::<f64>().sqrt();
    if na == 0.0 || nb == 0.0 {
        0.0
    } else {
        dot / (na * nb)
    }
}

fn move_to_back(lru: &mut VecDeque<String>, key: &str) {
    if let Some(pos) = lru.iter().position(|k| k == key) {
        lru.remove(pos);
    }
    lru.push_back(key.to_string());
}

fn retain_lru(lru: &mut VecDeque<String>, key: &str) {
    if let Some(pos) = lru.iter().position(|k| k == key) {
        lru.remove(pos);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_hash_query() {
        let h1 = hash_query("test query");
        let h2 = hash_query("test query");
        let h3 = hash_query("different");
        assert_eq!(h1, h2);
        assert_ne!(h1, h3);
        assert_eq!(h1.len(), 32);
    }

    #[test]
    fn test_cache_entry_expiry() {
        let mut entry = CacheEntry {
            query_hash: "hash".into(),
            query_text: "test".into(),
            embedding: None,
            results: vec![],
            project_root: "/tmp".into(),
            created_at: now_secs() - 10.0,
            hit_count: 1,
            last_hit: now_secs() - 10.0,
        };
        assert!(!entry.is_expired(100.0));
        assert!(entry.is_expired(5.0));

        entry.update_hit();
        assert_eq!(entry.hit_count, 2);
    }

    #[test]
    fn test_l1_hit() {
        let tmp = TempDir::new().unwrap();
        let cache = SemanticCache::new(
            tmp.path(),
            None,
            SemanticCacheConfig {
                disk_persist: false,
                ..Default::default()
            },
        );

        let results = vec![serde_json::json!({"id": 1})];
        cache.store("hello", results.clone());

        let cached = cache.get_l1("hello");
        assert!(cached.is_some());
        assert_eq!(cached.unwrap().len(), 1);

        let miss = cache.get_l1("nonexistent");
        assert!(miss.is_none());
    }

    #[test]
    fn test_l1_ttl_expiry() {
        let tmp = TempDir::new().unwrap();
        let cache = SemanticCache::new(
            tmp.path(),
            None,
            SemanticCacheConfig {
                ttl_seconds: 0.0,
                disk_persist: false,
                ..Default::default()
            },
        );

        cache.store("expire_me", vec![serde_json::json!({"x": 1})]);
        let result = cache.get_l1("expire_me");
        assert!(result.is_none());
    }

    #[test]
    fn test_cache_eviction() {
        let tmp = TempDir::new().unwrap();
        let cache = SemanticCache::new(
            tmp.path(),
            None,
            SemanticCacheConfig {
                max_size: 2,
                disk_persist: false,
                ..Default::default()
            },
        );

        cache.store("a", vec![serde_json::json!({"k": "a"})]);
        cache.store("b", vec![serde_json::json!({"k": "b"})]);

        // should evict "a" (oldest)
        cache.store("c", vec![serde_json::json!({"k": "c"})]);

        assert!(cache.get_l1("a").is_none());
        assert!(cache.get_l1("b").is_some());
        assert!(cache.get_l1("c").is_some());
    }

    #[test]
    fn test_disabled_cache() {
        let tmp = TempDir::new().unwrap();
        let cache = SemanticCache::new(
            tmp.path(),
            None,
            SemanticCacheConfig {
                enabled: false,
                disk_persist: false,
                ..Default::default()
            },
        );

        cache.store("x", vec![serde_json::json!({"k": "v"})]);
        assert!(cache.get_l1("x").is_none());
    }

    #[test]
    fn test_clear() {
        let tmp = TempDir::new().unwrap();
        let cache = SemanticCache::new(
            tmp.path(),
            None,
            SemanticCacheConfig {
                disk_persist: false,
                ..Default::default()
            },
        );

        cache.store("a", vec![serde_json::json!({"k": "v"})]);
        assert!(cache.get_l1("a").is_some());

        cache.clear();
        assert!(cache.get_l1("a").is_none());
    }

    #[test]
    fn test_cosine_similarity() {
        // 正交向量 → 0.0
        let a = vec![1.0f32, 0.0, 0.0];
        let b = vec![0.0f32, 1.0, 0.0];
        assert!((cosine(&a, &b) - 0.0).abs() < 1e-6);

        // 相同向量 → 1.0（余弦相似度，归一化后）
        let c = vec![0.5f32, 0.5, 0.0];
        let d = vec![0.5f32, 0.5, 0.0];
        assert!((cosine(&c, &d) - 1.0).abs() < 1e-6);

        // 45度角 → cos(45°) ≈ 0.707
        let e = vec![1.0f32, 0.0];
        let f = vec![1.0f32, 1.0];
        let expected = 1.0 / 2.0_f64.sqrt();
        assert!((cosine(&e, &f) - expected).abs() < 1e-6);
    }

    #[test]
    fn test_move_to_back_reorders() {
        let mut lru: VecDeque<String> = VecDeque::new();
        lru.push_back("a".into());
        lru.push_back("b".into());
        lru.push_back("c".into());

        move_to_back(&mut lru, "a");
        assert_eq!(lru[0], "b");
        assert_eq!(lru[1], "c");
        assert_eq!(lru[2], "a");
    }
}
