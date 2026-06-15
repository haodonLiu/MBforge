//! Agentic Data API client — arXiv / PMC / bioRxiv / medRxiv paper access.
//!
//! Provides shared HTTP helpers and URL encoding utilities used by the rig-core
//! literature tools in `arxiv_rig.rs`.  The legacy `tool_arxiv_*` / `tool_pmc_*`
//! free functions were removed in favour of the rig `#[rig_tool]` macro versions.
//!
//! Free papers (`2409.05591`, `2504.21776`) and three free search queries
//! ("transformer", "attention mechanism", "large language model") require no token.

use serde_json::Value;

pub const BASE_ARXIV: &str = "https://data.rag.ac.cn/arxiv";
pub const BASE_PMC: &str = "https://data.rag.ac.cn/pmc";

// ---------------------------------------------------------------------------
//  Internal helpers
// ---------------------------------------------------------------------------

fn get(timeout_secs: u64) -> reqwest::blocking::Client {
    reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(timeout_secs))
        .build()
        .expect("arxiv blocking client")
}

pub fn text(url: &str) -> Result<String, String> {
    get(30)
        .get(url)
        .send()
        .map_err(|e| format!("HTTP error: {e}"))?
        .error_for_status()
        .map_err(|e| format!("API error: {e} (URL: {url})"))?
        .text()
        .map_err(|e| format!("Read error: {e}"))
}

pub fn json(url: &str) -> Result<Value, String> {
    let body = text(url)?;
    serde_json::from_str(&body).map_err(|e| format!("JSON parse error: {e}"))
}

pub fn param_url(base: &str, pairs: &[(&str, &str)]) -> String {
    let qs: Vec<String> = pairs
        .iter()
        .filter(|(_, v)| !v.is_empty())
        .map(|(k, v)| format!("{}={}", urlencoding(k), urlencoding(v)))
        .collect();
    format!("{base}?{}", qs.join("&"))
}

/// Percent-encode a string for use in a URL query string.
///
/// Unreserved characters per RFC 3986 (`A-Z a-z 0-9 - _ . ~`) are kept verbatim;
/// space is encoded as `+` (form-style, matching the previous behavior for the
/// data.rag.ac.cn API); every other character is percent-encoded byte-by-byte
/// over its UTF-8 representation.
///
/// **Correctness note**: `c as u8` on a `char` is wrong for any code point
/// above U+007F because it truncates to the low 8 bits (e.g. `'药' (U+836F)`
/// becomes `0x6F = 'o'`). We instead encode via `c.encode_utf8(&mut buf)` and
/// then percent-encode each byte — this is the only way to round-trip
/// CJK, emoji, and other multi-byte characters correctly.
pub fn urlencoding(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            'A'..='Z' | 'a'..='z' | '0'..='9' | '-' | '_' | '.' | '~' => out.push(c),
            ' ' => out.push('+'),
            _ => {
                let mut buf = [0u8; 4];
                let encoded = c.encode_utf8(&mut buf);
                for b in encoded.as_bytes() {
                    out.push_str(&format!("%{:02X}", b));
                }
            }
        }
    }
    out
}

pub fn args_err(msg: &str) -> String {
    serde_json::json!({"error": msg}).to_string()
}

#[cfg(test)]
mod tests {
    use super::urlencoding;

    #[test]
    fn urlencoding_passes_through_unreserved() {
        // RFC 3986 unreserved characters are kept verbatim.
        assert_eq!(urlencoding("abcXYZ0123-_.~"), "abcXYZ0123-_.~");
    }

    #[test]
    fn urlencoding_encodes_space_as_plus() {
        // data.rag.ac.cn API expects form-style space encoding.
        assert_eq!(urlencoding("hello world"), "hello+world");
    }

    #[test]
    fn urlencoding_handles_ascii_punctuation() {
        // Non-unreserved ASCII becomes percent-encoded.
        assert_eq!(urlencoding("a&b=c"), "a%26b%3Dc");
    }

    #[test]
    fn urlencoding_handles_cjk() {
        // 药 (U+836F) is E8 8D AF in UTF-8 — the legacy `c as u8` bug produced
        // `%6F` (a single 'o'). The correct encoding is the full 3-byte sequence.
        assert_eq!(urlencoding("药"), "%E8%8D%AF");
        // 4-char CJK string → 12 bytes total
        assert_eq!(
            urlencoding("药物化学"),
            "%E8%8D%AF%E7%89%A9%E5%8C%96%E5%AD%A6"
        );
    }

    #[test]
    fn urlencoding_handles_emoji() {
        // 🚀 (U+1F680) is F0 9F 9A 80 in UTF-8 (4 bytes).
        assert_eq!(urlencoding("🚀"), "%F0%9F%9A%80");
    }

    #[test]
    fn urlencoding_handles_mixed_cjk_and_ascii() {
        // Mixed query like an Agent prompt — must not corrupt the ASCII parts.
        assert_eq!(
            urlencoding("query 药物 hello"),
            "query+%E8%8D%AF%E7%89%A9+hello"
        );
    }

    #[test]
    fn urlencoding_handles_empty_string() {
        assert_eq!(urlencoding(""), "");
    }

    #[test]
    fn urlencoding_is_idempotent() {
        // Encoding an already-percent-encoded string is unsafe (over-encodes `%`),
        // but a plain string round-trips through encoding+decoding to itself.
        let s = "药物化学 2.0 🚀";
        // Decode by reversing each `%XX` triplet back to the byte and then to UTF-8.
        let mut bytes = Vec::new();
        let mut i = 0;
        let encoded = urlencoding(s);
        while i < encoded.len() {
            if encoded.as_bytes()[i] == b'%' && i + 2 < encoded.len() {
                let h = u8::from_str_radix(&encoded[i + 1..i + 3], 16).unwrap();
                bytes.push(h);
                i += 3;
            } else if encoded.as_bytes()[i] == b'+' {
                bytes.push(b' ');
                i += 1;
            } else {
                bytes.push(encoded.as_bytes()[i]);
                i += 1;
            }
        }
        let decoded = String::from_utf8(bytes).unwrap();
        assert_eq!(decoded, s);
    }
}
