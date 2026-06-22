//! File-backed caching service for extracted PDF content.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::parsers::pipeline_v2::error::{ExtractError, PipelineError};

/// A generic key/value cache used by the extract stage.
///
/// Implementations must be thread-safe so they can be shared across async
/// pipeline workers.
pub trait Cache<K, V>: Send + Sync {
    /// Returns the cached value for `key`, or `None` if no entry exists.
    fn get(&self, key: &K) -> Result<Option<V>, PipelineError>;

    /// Writes `value` to the cache under `key`.
    fn put(&self, key: &K, value: &V) -> Result<(), PipelineError>;
}

/// A serialised extract-stage result stored in the file cache.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedExtractResult {
    /// Plain text extracted from the source document.
    pub text: String,
    /// JSON-encoded document sections.
    pub sections_json: String,
    /// JSON-encoded document metadata.
    pub metadata_json: String,
}

/// File-system implementation of [`Cache`] that stores entries as JSON.
pub struct FileCache {
    root: PathBuf,
}

impl FileCache {
    /// Creates a new file cache rooted at `root`.
    ///
    /// Actual cache entries are written to `root/index/file-cache/`.
    pub fn new(root: impl AsRef<Path>) -> Self {
        Self {
            root: root.as_ref().to_path_buf(),
        }
    }

    /// Returns a deterministic, filesystem-safe filename for `key`.
    ///
    /// The key is hashed with SHA-256 so arbitrary caller-supplied strings
    /// (including path separators and parent-directory components) cannot
    /// escape the cache root or create overly long filenames. The full hex
    /// digest is used to keep the collision probability negligible.
    fn safe_key(key: &str) -> String {
        let digest = Sha256::digest(key.as_bytes());
        format!("{:x}", digest)
    }

    fn cache_path(&self, key: &str) -> PathBuf {
        self.root
            .join("index")
            .join("file-cache")
            .join(format!("{}.json", Self::safe_key(key)))
    }
}

impl Cache<String, CachedExtractResult> for FileCache {
    fn get(&self, key: &String) -> Result<Option<CachedExtractResult>, PipelineError> {
        let path = self.cache_path(key);
        if !path.exists() {
            return Ok(None);
        }
        let content = std::fs::read_to_string(&path).map_err(|e| {
            PipelineError::Extract(ExtractError::CacheReadFailed {
                cache: "FileCache".into(),
                detail: e.to_string(),
            })
        })?;
        let val: CachedExtractResult = serde_json::from_str(&content).map_err(|e| {
            PipelineError::Extract(ExtractError::CacheReadFailed {
                cache: "FileCache".into(),
                detail: e.to_string(),
            })
        })?;
        Ok(Some(val))
    }

    fn put(&self, key: &String, value: &CachedExtractResult) -> Result<(), PipelineError> {
        let path = self.cache_path(key);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| {
                PipelineError::Extract(ExtractError::CacheWriteFailed {
                    cache: "FileCache".into(),
                    detail: e.to_string(),
                })
            })?;
        }
        let content = serde_json::to_string_pretty(value).map_err(|e| {
            PipelineError::Extract(ExtractError::CacheWriteFailed {
                cache: "FileCache".into(),
                detail: e.to_string(),
            })
        })?;
        std::fs::write(&path, content).map_err(|e| {
            PipelineError::Extract(ExtractError::CacheWriteFailed {
                cache: "FileCache".into(),
                detail: e.to_string(),
            })
        })
    }
}
