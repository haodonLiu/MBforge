use regex::Regex;
use sha2::{Digest, Sha256};
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
    fn test_safe_filename() {
        assert_eq!(safe_filename("a/b:c*d?e"), "a_b_c_d_e");
    }

    #[test]
    fn test_estimate_tokens() {
        let tokens = estimate_tokens("Hello 你好");
        assert!(tokens > 0);
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
}
