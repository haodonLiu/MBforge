use sha2::{Digest, Sha256};
use std::path::Path;

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
        .map(|c| if matches!(c, '\\' | '/' | ':' | '*' | '?' | '"' | '<' | '>' | '|') { '_' } else { c })
        .collect::<String>()
        .trim()
        .to_string()
}

/// Ensure directory exists.
pub fn ensure_dir(path: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(path)
}

/// Save data as JSON file (2-space indent).
pub fn save_json<T: serde::Serialize>(path: &Path, data: &T) -> Result<(), Box<dyn std::error::Error>> {
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
    let cjk = text.chars().filter(|c| *c >= '\u{4e00}' && *c <= '\u{9fff}' || *c >= '\u{3400}' && *c <= '\u{4dbf}').count();
    let other = text.len() - cjk;
    (cjk as f64 * 1.5 + other as f64 * 0.25) as usize
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
