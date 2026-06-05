//! Agentic Data API client — arXiv / PMC / bioRxiv / medRxiv paper access.
//!
//! Native Rust tools for the Agent executor to query the RAG API at
//! `https://data.rag.ac.cn`.  Free papers (`2409.05591`, `2504.21776`)
//! and three free search queries ("transformer", "attention mechanism",
//! "large language model") require no token.

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

fn extract(args: &Value, key: &str) -> String {
    args.get(key)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

fn extract_i64(args: &Value, key: &str, default: i64) -> i64 {
    args.get(key).and_then(|v| v.as_i64()).unwrap_or(default)
}

fn extract_bool(args: &Value, key: &str) -> bool {
    args.get(key).and_then(|v| v.as_bool()).unwrap_or(false)
}

pub fn args_err(msg: &str) -> String {
    serde_json::json!({"error": msg}).to_string()
}

// ---------------------------------------------------------------------------
//  Public tools — each returns a JSON string for the agent
// ---------------------------------------------------------------------------

pub fn tool_arxiv_metadata(args: &Value) -> String {
    let id = extract(args, "arxiv_id");
    if id.is_empty() {
        return args_err("arxiv_id is required");
    }
    let token = extract(args, "token");
    let url = param_url(
        BASE_ARXIV,
        &[("type", "head"), ("arxiv_id", &id), ("token", &token)],
    );
    match json(&url) {
        Ok(v) => v.to_string(),
        Err(e) => args_err(&e),
    }
}

pub fn tool_arxiv_brief(args: &Value) -> String {
    let id = extract(args, "arxiv_id");
    if id.is_empty() {
        return args_err("arxiv_id is required");
    }
    let token = extract(args, "token");
    let url = param_url(
        BASE_ARXIV,
        &[("type", "brief"), ("arxiv_id", &id), ("token", &token)],
    );
    match json(&url) {
        Ok(v) => v.to_string(),
        Err(e) => args_err(&e),
    }
}

pub fn tool_arxiv_preview(args: &Value) -> String {
    let id = extract(args, "arxiv_id");
    if id.is_empty() {
        return args_err("arxiv_id is required");
    }
    let token = extract(args, "token");
    let chars = extract_i64(args, "characters", 10000);
    let url = param_url(
        BASE_ARXIV,
        &[
            ("type", "preview"),
            ("arxiv_id", &id),
            ("characters", &chars.to_string()),
            ("token", &token),
        ],
    );
    match json(&url) {
        Ok(v) => v.to_string(),
        Err(e) => args_err(&e),
    }
}

pub fn tool_arxiv_raw(args: &Value) -> String {
    let id = extract(args, "arxiv_id");
    if id.is_empty() {
        return args_err("arxiv_id is required");
    }
    let token = extract(args, "token");
    let url = param_url(
        BASE_ARXIV,
        &[("type", "raw"), ("arxiv_id", &id), ("token", &token)],
    );
    match text(&url) {
        Ok(v) => serde_json::json!({"content": v}).to_string(),
        Err(e) => args_err(&e),
    }
}

pub fn tool_arxiv_section(args: &Value) -> String {
    let id = extract(args, "arxiv_id");
    let section = extract(args, "section");
    if id.is_empty() || section.is_empty() {
        return args_err("arxiv_id and section are required");
    }
    let token = extract(args, "token");
    let url = param_url(
        BASE_ARXIV,
        &[
            ("type", "section"),
            ("arxiv_id", &id),
            ("section", &section),
            ("token", &token),
        ],
    );
    match text(&url) {
        Ok(v) => serde_json::json!({"section": section, "content": v}).to_string(),
        Err(e) => args_err(&e),
    }
}

pub fn tool_arxiv_search(args: &Value) -> String {
    let query = extract(args, "query");
    if query.is_empty() {
        return args_err("query is required");
    }
    let source = extract(args, "source"); // arxiv / biorxiv / medrxiv
    let top_k = extract_i64(args, "top_k", 10);
    let offset = extract_i64(args, "offset", 0);
    let categories = extract(args, "categories");
    let authors = extract(args, "authors");
    let orgs = extract(args, "orgs");
    let date_search_type = extract(args, "date_search_type");
    let date_str = extract(args, "date_str");
    let min_citation = extract_i64(args, "min_citation", 0);
    let use_fine_rerank = extract_bool(args, "use_fine_rerank");
    let return_contents = extract_bool(args, "return_contents");
    let return_roc = extract_bool(args, "return_roc");
    let token = extract(args, "token");

    let mut pairs: Vec<(&str, String)> = vec![
        ("type", "retrieve".into()),
        ("query", query),
        ("top_k", top_k.to_string()),
    ];
    if !source.is_empty() {
        pairs.push(("source", source));
    }
    if offset > 0 {
        pairs.push(("offset", offset.to_string()));
    }
    if !categories.is_empty() {
        pairs.push(("categories", categories));
    }
    if !authors.is_empty() {
        pairs.push(("authors", authors));
    }
    if !orgs.is_empty() {
        pairs.push(("orgs", orgs));
    }
    if !date_search_type.is_empty() {
        pairs.push(("date_search_type", date_search_type));
    }
    if !date_str.is_empty() {
        pairs.push(("date_str", date_str));
    }
    if min_citation > 0 {
        pairs.push(("min_citation", min_citation.to_string()));
    }
    if !use_fine_rerank {
        pairs.push(("use_fine_rerank", "false".into()));
    }
    if return_contents {
        pairs.push(("return_contents", "true".into()));
    }
    if return_roc {
        pairs.push(("return_roc", "true".into()));
    }
    if !token.is_empty() {
        pairs.push(("token", token));
    }

    let qs: Vec<String> = pairs
        .iter()
        .map(|(k, v)| format!("{}={}", urlencoding(k), urlencoding(v)))
        .collect();
    let url = format!("{}?{}", BASE_ARXIV, qs.join("&"));

    match json(&url) {
        Ok(v) => v.to_string(),
        Err(e) => args_err(&e),
    }
}

pub fn tool_arxiv_trending(args: &Value) -> String {
    let id = extract(args, "arxiv_id");
    if id.is_empty() {
        return args_err("arxiv_id is required");
    }
    let token = extract(args, "token");
    let url = format!(
        "{}/trending_signal?arxiv_id={}&token={}",
        BASE_ARXIV,
        urlencoding(&id),
        urlencoding(&token),
    );
    match json(&url) {
        Ok(v) => v.to_string(),
        Err(e) => args_err(&e),
    }
}

pub fn tool_pmc_metadata(args: &Value) -> String {
    let id = extract(args, "pmc_id");
    if id.is_empty() {
        return args_err("pmc_id is required");
    }
    let token = extract(args, "token");
    let url = param_url(
        BASE_PMC,
        &[("type", "head"), ("pmc_id", &id), ("token", &token)],
    );
    match json(&url) {
        Ok(v) => v.to_string(),
        Err(e) => args_err(&e),
    }
}

pub fn tool_pmc_json(args: &Value) -> String {
    let id = extract(args, "pmc_id");
    if id.is_empty() {
        return args_err("pmc_id is required");
    }
    let token = extract(args, "token");
    let url = param_url(
        BASE_PMC,
        &[("type", "json"), ("pmc_id", &id), ("token", &token)],
    );
    match json(&url) {
        Ok(v) => v.to_string(),
        Err(e) => args_err(&e),
    }
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
        assert_eq!(urlencoding("药物化学"), "%E8%8D%AF%E7%89%A9%E5%8C%96%E5%AD%A6");
    }

    #[test]
    fn urlencoding_handles_emoji() {
        // 🚀 (U+1F680) is F0 9F 9A 80 in UTF-8 (4 bytes).
        assert_eq!(urlencoding("🚀"), "%F0%9F%9A%80");
    }

    #[test]
    fn urlencoding_handles_mixed_cjk_and_ascii() {
        // Mixed query like an Agent prompt — must not corrupt the ASCII parts.
        assert_eq!(urlencoding("query 药物 hello"), "query+%E8%8D%AF%E7%89%A9+hello");
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
