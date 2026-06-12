#![allow(dead_code)]
use regex::Regex;
use sha2::{Digest, Sha256};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

/// SMILES candidate pattern (simplified — no RDKit validation in Rust).
/// Shared between classifier.rs and extractor.rs to avoid duplication.
pub static SMILES_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"[A-Za-z0-9@.+\-=#$()\[\]\\/%~]{4,}").expect("valid SMILES regex"));

/// Get current UTC time as RFC 3339 string.
pub fn now_rfc3339() -> String {
    chrono::Utc::now().to_rfc3339()
}

/// Get current UNIX timestamp in seconds (f64 fractional).
///
/// Replaces inline `SystemTime::now() + duration_since(UNIX_EPOCH) + as_secs_f64()`
/// patterns scattered across the codebase. Centralized here so the conversion
/// policy (`as_secs_f64`) lives in one place.
pub fn now_secs_f64() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

/// Get current UNIX timestamp in whole seconds (u64).
///
/// Used by `vlm_chem.rs::ImageCaptionCache::set` and similar paths that need
/// an integer second timestamp.
pub fn now_secs_u64() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// Generate a UUID v4 string.
pub fn generate_uuid() -> String {
    uuid::Uuid::new_v4().to_string()
}

/// Compute SHA256 hash of a file.
pub fn sha256_file(path: &Path) -> Result<String, std::io::Error> {
    let bytes = std::fs::read(path)?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    Ok(format!("{:x}", hasher.finalize()))
}

/// Compute SHA256 hash of a text string.
pub fn sha256_text(text: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(text.as_bytes());
    format!("{:x}", hasher.finalize())
}

/// Truncate text to max_len, breaking at word boundary.
pub fn truncate_text(text: &str, max_len: usize) -> String {
    if text.len() <= max_len {
        return text.to_string();
    }
    let truncated = &text[..max_len];
    match truncated.rfind(' ') {
        Some(pos) => format!("{}...", &truncated[..pos]),
        None => format!("{}...", truncated),
    }
}

/// Truncate text to at most `max_bytes` bytes, never splitting a UTF-8 character.
///
/// Returns the longest valid `&str` prefix whose byte length is `<= max_bytes`.
/// Use this anywhere `&text[..N]` would otherwise panic on a multi-byte boundary
/// (CJK, emoji, combining marks). When `text.len() <= max_bytes` the slice is
/// returned unchanged — no allocation.
///
/// Backed by the stable [`str::floor_char_boundary`] method, so it is safe for
/// Backed by manual `is_char_boundary` walk — `str::floor_char_boundary` is
/// still nightly-only as of rustc 1.81, so we use the stable alternative.
pub fn safe_truncate(text: &str, max_bytes: usize) -> &str {
    if text.len() <= max_bytes {
        return text;
    }
    let mut i = max_bytes;
    while i > 0 && !text.is_char_boundary(i) {
        i -= 1;
    }
    &text[..i]
}

/// Safe filename: replace illegal characters with underscore.
pub fn safe_filename(name: &str) -> String {
    name.chars()
        .map(|c| {
            if matches!(c, '\\' | '/' | ':' | '*' | '?' | '"' | '<' | '>' | '|') {
                '_'
            } else {
                c
            }
        })
        .collect::<String>()
        .trim()
        .to_string()
}

/// Ensure directory exists.
pub fn ensure_dir(path: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(path)
}

/// 去掉 Windows 长路径前缀 `\\?\`（浏览器拖拽 / 对话框可能带入）
pub fn clean_path(raw: &str) -> String {
    if cfg!(windows) {
        raw.trim_start_matches(r"\\?\").to_string()
    } else {
        raw.to_string()
    }
}

/// Save data as JSON file (2-space indent).
pub fn save_json<T: serde::Serialize>(
    path: &Path,
    data: &T,
) -> Result<(), Box<dyn std::error::Error>> {
    ensure_dir(path.parent().unwrap_or(Path::new(".")))?;
    let json = serde_json::to_string_pretty(data)?;
    std::fs::write(path, json)?;
    Ok(())
}

/// Atomically write `contents` to `path` using a temp file + fsync + rename.
///
/// Guarantees that either the old file remains, or the new file is fully
/// persisted. The temp file is created in the same directory as `path` so
/// `rename` is atomic on the same filesystem.
pub fn atomic_write<P: AsRef<Path>>(path: P, contents: &[u8]) -> std::io::Result<()> {
    let path = path.as_ref();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("tmp");
    {
        let mut file = std::fs::File::create(&tmp)?;
        file.write_all(contents)?;
        file.flush()?;
        file.sync_all()?;
    }
    std::fs::rename(&tmp, path)?;
    Ok(())
}

/// 获取指定路径所在文件系统的可用空间（字节）。
pub fn available_space_bytes(path: &Path) -> Result<u64, Box<dyn std::error::Error>> {
    let stat = fs2::statvfs(path)?;
    Ok(stat.available_space())
}

/// Load JSON file, returning default on error.
pub fn load_json<T: serde::de::DeserializeOwned>(path: &Path) -> Option<T> {
    let data = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&data).ok()
}

/// Estimate token count (rough heuristic: CJK ~1.5 token/char, other ~0.25 token/char).
pub fn estimate_tokens(text: &str) -> usize {
    let cjk = text
        .chars()
        .filter(|c| *c >= '\u{4e00}' && *c <= '\u{9fff}' || *c >= '\u{3400}' && *c <= '\u{4dbf}')
        .count();
    let other = text.len() - cjk;
    (cjk as f64 * 1.5 + other as f64 * 0.25) as usize
}

// ============================================================================
// Path Safety Utilities
// ============================================================================

/// Path safety check result containing the canonical path.
#[derive(Debug)]
pub struct PathSafetyCheck {
    /// Canonical (resolved) path
    pub canonical: PathBuf,
    /// Whether the path is within the root
    pub within_root: bool,
}

/// Check if the target path is within the root directory (prevents path traversal attacks).
///
/// # Arguments
/// * `root` - Project root directory
/// * `target` - Target path to check (can be relative or absolute)
///
/// # Returns
/// * `Ok(PathSafetyCheck)` - Check passed, contains the canonical path
/// * `Err(String)` - Check failed, contains error message
///
/// # Example
/// ```rust
/// let check = assert_within_root("/project", Path::new("docs/readme.md"))?;
/// assert!(check.within_root);
/// ```
pub fn assert_within_root(root: &str, target: &Path) -> Result<PathSafetyCheck, String> {
    let canonical_root = Path::new(root)
        .canonicalize()
        .map_err(|e| format!("Root canonicalize error: {}", e))?;

    let target_full = if target.is_absolute() {
        target.to_path_buf()
    } else {
        Path::new(root).join(target)
    };

    let canonical_target = target_full
        .canonicalize()
        .map_err(|e| format!("Path canonicalize error: {}", e))?;

    let within_root = canonical_target.starts_with(&canonical_root);

    if !within_root {
        return Err(format!(
            "Access denied: path '{}' escapes project root",
            target.display()
        ));
    }

    Ok(PathSafetyCheck {
        canonical: canonical_target,
        within_root: true,
    })
}

/// Safely join root and relative path, verifying the result is within root.
///
/// # Arguments
/// * `root` - Project root directory
/// * `relative` - Relative path to join
///
/// # Returns
/// * `Ok(PathBuf)` - Safe joined path
/// * `Err(String)` - Error if path escapes root
pub fn safe_join(root: &Path, relative: &str) -> Result<PathBuf, String> {
    let target = root.join(relative);
    assert_within_root(root.to_string_lossy().as_ref(), &target).map(|c| c.canonical)
}

/// 统一 Mutex poison 处理：将 `unwrap_or_else(|e| e.into_inner())` 简化为 `.into_inner()`。
pub trait LockResultExt<T> {
    fn into_inner(self) -> T;
}

impl<T> LockResultExt<T> for std::sync::LockResult<T> {
    fn into_inner(self) -> T {
        self.unwrap_or_else(|e| e.into_inner())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_generate_uuid() {
        let uuid = generate_uuid();
        assert_eq!(uuid.len(), 36);
        assert_eq!(uuid.chars().filter(|c| *c == '-').count(), 4);
    }

    #[test]
    fn test_sha256_text() {
        let hash = sha256_text("hello");
        assert_eq!(hash.len(), 64);
    }

    #[test]
    fn test_truncate_text() {
        assert_eq!(truncate_text("hello world", 5), "hello...");
        assert_eq!(truncate_text("hi", 10), "hi");
    }

    #[test]
    fn test_safe_truncate() {
        // ASCII short input: returned unchanged
        assert_eq!(safe_truncate("hi", 10), "hi");

        // ASCII truncation: simple cut
        assert_eq!(safe_truncate("hello world", 5), "hello");

        // CJK: 药 takes 3 bytes (E8 8D AF). Floor must not panic on 500.
        let s = "药".repeat(200); // 600 bytes
        let cut = safe_truncate(&s, 500);
        // Must end on a complete character and be <= 500 bytes
        assert!(cut.len() <= 500);
        // Result must be a valid string prefix
        assert!(s.starts_with(cut));
        // The next byte after cut is the start of a new char (or end of string)
        if cut.len() < s.len() {
            assert!(s.is_char_boundary(cut.len()));
        }

        // Emoji: 🚀 takes 4 bytes (F0 9F 9A 80). Floor must respect 4-byte width.
        let s = "🚀".repeat(150); // 600 bytes
        let cut = safe_truncate(&s, 500);
        assert!(cut.len() <= 500);
        // 500 / 4 = 125 complete emoji (no partial 4-byte sequences)
        assert_eq!(cut.len() % 4, 0);
    }

    #[test]
    fn test_assert_within_root_valid() {
        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path();

        // Create a subdirectory
        let subdir = root.join("docs");
        fs::create_dir_all(&subdir).unwrap();

        // Create a file in the subdirectory
        let file_path = subdir.join("readme.txt");
        fs::write(&file_path, "test").unwrap();

        // Valid path within root
        let result = assert_within_root(
            root.to_string_lossy().as_ref(),
            Path::new("docs/readme.txt"),
        );
        assert!(result.is_ok(), "Expected Ok but got: {:?}", result);
        assert!(result.unwrap().within_root);
    }

    #[test]
    fn test_assert_within_root_traversal() {
        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path();

        // Path traversal attempt - non-existent path should fail canonicalize
        let result = assert_within_root(
            root.to_string_lossy().as_ref(),
            Path::new("../../../etc/passwd"),
        );
        // This should fail because the path doesn't exist
        assert!(
            result.is_err(),
            "Expected error for non-existent traversal path"
        );
    }

    #[test]
    fn test_assert_within_root_absolute_inside() {
        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path();

        // Create a file
        let file_path = root.join("test.txt");
        fs::write(&file_path, "test").unwrap();

        // Absolute path within root should work
        let result = assert_within_root(root.to_string_lossy().as_ref(), &file_path);
        assert!(result.is_ok(), "Expected Ok but got: {:?}", result);
        assert!(result.unwrap().within_root);
    }

    #[test]
    fn test_safe_join() {
        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path();

        // Create the directory that safe_join will reference
        let docs_dir = root.join("docs");
        fs::create_dir_all(&docs_dir).unwrap();

        let joined = safe_join(root, "docs");
        assert!(joined.is_ok(), "Expected Ok but got: {:?}", joined);
        assert!(joined.unwrap().to_string_lossy().contains("docs"));
    }

    #[test]
    fn test_safe_filename() {
        assert_eq!(safe_filename("a/b:c*d?e"), "a_b_c_d_e");
    }

    #[test]
    fn test_estimate_tokens() {
        let tokens = estimate_tokens("Hello 你好");
        assert!(tokens > 0);
    }

    #[test]
    fn test_now_secs_f64_monotonic() {
        let a = now_secs_f64();
        std::thread::sleep(std::time::Duration::from_millis(10));
        let b = now_secs_f64();
        assert!(b >= a);
        // Sanity: must be a plausible UNIX timestamp (post-2020).
        assert!(a > 1_577_836_800.0);
    }

    #[test]
    fn test_now_secs_u64_is_integer() {
        let v = now_secs_u64();
        assert!(v > 1_577_836_800);
    }

    #[test]
    fn test_now_rfc3339_format() {
        let s = now_rfc3339();
        // RFC 3339: e.g. "2026-06-10T12:34:56.789012345+00:00"
        assert!(s.contains('T'));
        assert!(s.ends_with("+00:00"));
    }
}
