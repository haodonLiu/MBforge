//! Custom URI scheme protocol for serving project files with Range support.
//!
//! Registered as `mbforge` and consumed via `convertFileSrc(path, "mbforge")` on the frontend.
//! URL path is percent-encoded (same convention as Tauri's built-in `asset` protocol).

use std::path::PathBuf;
use tauri::http::{header, Request, Response, StatusCode};

/// Simple percent-decoder (no external crate needed).
fn percent_decode(input: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(input.len());
    let mut i = 0;
    while i < input.len() {
        if input[i] == b'%' && i + 2 < input.len() {
            if let Ok(hex_str) = std::str::from_utf8(&input[i + 1..i + 3]) {
                if let Ok(hex) = u8::from_str_radix(hex_str, 16) {
                    out.push(hex);
                    i += 3;
                    continue;
                }
            }
        }
        out.push(input[i]);
        i += 1;
    }
    out
}

/// Guess MIME type from file extension.
fn guess_mime(path: &PathBuf) -> &'static str {
    match path.extension().and_then(|e| e.to_str()) {
        Some("pdf") => "application/pdf",
        Some("png") => "image/png",
        Some("jpg") | Some("jpeg") => "image/jpeg",
        Some("gif") => "image/gif",
        Some("svg") => "image/svg+xml",
        Some("webp") => "image/webp",
        _ => "application/octet-stream",
    }
}

/// Parse a `bytes=start-end` Range header against a file size.
fn parse_range(range_str: &str, file_size: u64) -> Option<(u64, u64)> {
    let range_str = range_str.strip_prefix("bytes=")?;
    let parts: Vec<&str> = range_str.split('-').collect();
    if parts.len() != 2 {
        return None;
    }
    let start: u64 = parts[0].parse().ok()?;
    let end: u64 = if parts[1].is_empty() {
        file_size
    } else {
        parts[1]
            .parse::<u64>()
            .ok()?
            .saturating_add(1)
            .min(file_size)
    };
    if start >= end || end > file_size {
        return None;
    }
    Some((start, end))
}

/// Build an HTTP response for a file request, supporting Range headers and CORS.
fn build_file_response(
    path: &PathBuf,
    range: Option<&str>,
) -> Result<Response<Vec<u8>>, Box<dyn std::error::Error>> {
    let file_size = std::fs::metadata(path)?.len();

    let (status, body, content_range) = if let Some(range_str) = range {
        if let Some((start, end)) = parse_range(range_str, file_size) {
            let bytes = std::fs::read(path)?;
            let sliced = bytes[start as usize..end as usize].to_vec();
            let content_range = format!("bytes {}-{}/{}", start, end.saturating_sub(1), file_size);
            (StatusCode::PARTIAL_CONTENT, sliced, Some(content_range))
        } else {
            return Ok(Response::builder()
                .status(StatusCode::RANGE_NOT_SATISFIABLE)
                .header(header::CONTENT_RANGE, format!("bytes */{}", file_size))
                .header("Access-Control-Allow-Origin", "*")
                .body(Vec::new())?);
        }
    } else {
        let bytes = std::fs::read(path)?;
        (StatusCode::OK, bytes, None)
    };

    let mut response = Response::builder()
        .status(status)
        .header(header::CONTENT_TYPE, guess_mime(path))
        .header(header::ACCEPT_RANGES, "bytes")
        .header("Access-Control-Allow-Origin", "*")
        .header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        .header("Access-Control-Allow-Headers", "Range, Content-Type");

    if let Some(cr) = content_range {
        response = response.header(header::CONTENT_RANGE, cr);
    }

    Ok(response.body(body)?)
}

/// Handle incoming requests on the `mbforge://` scheme.
///
/// Path decoding follows Tauri's `asset` protocol convention:
/// `request.uri().path()` is percent-encoded, e.g. `/C%3A%5Cfile.txt`.
pub fn handle_mbforge_request(
    _ctx: tauri::UriSchemeContext<'_, tauri::Wry>,
    request: Request<Vec<u8>>,
    responder: tauri::UriSchemeResponder,
) {
    // Handle CORS preflight
    if request.method().as_str() == "OPTIONS" {
        let response = Response::builder()
            .status(StatusCode::NO_CONTENT)
            .header("Access-Control-Allow-Origin", "*")
            .header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            .header("Access-Control-Allow-Headers", "Range, Content-Type")
            .body(Vec::new())
            .unwrap_or_default();
        responder.respond(response);
        return;
    }

    // Percent-decode the URI path (same as Tauri asset protocol)
    let path =
        String::from_utf8_lossy(&percent_decode(request.uri().path().as_bytes())).to_string();

    // Remove leading slash
    let path_str = path.trim_start_matches('/');
    let path_buf = PathBuf::from(path_str);

    // Security: path must exist and be a regular file
    if !path_buf.exists() || !path_buf.is_file() {
        let response = Response::builder()
            .status(StatusCode::NOT_FOUND)
            .header("Access-Control-Allow-Origin", "*")
            .body(b"File not found".to_vec())
            .unwrap_or_default();
        responder.respond(response);
        return;
    }

    // Security: reject relative paths
    #[cfg(windows)]
    let is_valid = path_buf.is_absolute();
    #[cfg(not(windows))]
    let is_valid = path_str.starts_with('/');

    if !is_valid {
        let response = Response::builder()
            .status(StatusCode::FORBIDDEN)
            .header("Access-Control-Allow-Origin", "*")
            .body(b"Invalid path".to_vec())
            .unwrap_or_default();
        responder.respond(response);
        return;
    }

    let range = request.headers().get("range").and_then(|v| v.to_str().ok());

    let response = match build_file_response(&path_buf, range) {
        Ok(resp) => resp,
        Err(e) => {
            log::error!("[mbforge protocol] Failed to read file: {}", e);
            Response::builder()
                .status(StatusCode::INTERNAL_SERVER_ERROR)
                .header("Access-Control-Allow-Origin", "*")
                .body(b"Internal server error".to_vec())
                .unwrap_or_default()
        }
    };
    responder.respond(response);
}
