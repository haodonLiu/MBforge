//! Tauri commands wrapping the per-PDF detection cache.
//!
//! These commands intercept the **on-demand** molecule detection path that
//! the frontend hits when a user opens a PDF page in the viewer. They:
//!
//! 1. Compute (or look up in an in-memory LRU) the SHA-256 of the PDF.
//! 2. Try `DetectionCache::get(doc_slug, page, pdf_hash)` — return on hit.
//! 3. On miss, POST to the Python sidecar at `<sidecar>/api/v1/moldet/extract-page`,
//!    save the result to the cache, and return it.
//!
//! Net effect: opening a previously-detected page in the PdfViewer is a
//! single disk read + JSON parse (~1 ms) instead of an HTTP roundtrip +
//! MolDet + MolScribe inference (~1-3 s).

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use std::sync::LazyLock;
use serde::{Deserialize, Serialize};

use crate::core::config::constants::{sidecar_url, PAPERS_DIR};
use crate::core::document::detection_cache::{
    Detection as CachedDetection, DetectionCache, PageDetection, DETECTION_CACHE_SCHEMA_VERSION,
};
use crate::core::helpers::clean_path;
use crate::core::helpers::sha256_file;

// ---------------------------------------------------------------------------
// In-memory PDF hash LRU — avoid re-hashing unchanged files
// ---------------------------------------------------------------------------

#[derive(Clone)]
struct HashEntry {
    mtime_secs: u64,
    hash: String,
}

/// Per-process LRU keyed by absolute PDF path. Holds the most-recent
/// (mtime, hash) so a session that revisits the same PDF doesn't pay
/// the SHA-256 cost (which on a 50 MB PDF is ~500 ms) twice.
///
/// We only hold at most a handful of entries (current PDF + the
/// recently-opened ones), so a simple `HashMap` is sufficient.
static PDF_HASH_CACHE: LazyLock<Mutex<HashMap<PathBuf, HashEntry>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

fn pdf_hash_cached(pdf_abs: &std::path::Path) -> Option<String> {
    let mtime = std::fs::metadata(pdf_abs)
        .and_then(|m| m.modified())
        .ok()
        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_secs())
        .unwrap_or(0);

    // Fast path: re-hash only if mtime changed (or no entry).
    {
        let cache: std::sync::MutexGuard<HashMap<PathBuf, HashEntry>> =
        PDF_HASH_CACHE.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(entry) = cache.get(pdf_abs) {
            if entry.mtime_secs == mtime {
                return Some(entry.hash.clone());
            }
        }
    }

    // Slow path: actually hash the file.
    let hash = sha256_file(pdf_abs).ok()?;

    let mut cache: std::sync::MutexGuard<HashMap<PathBuf, HashEntry>> =
        PDF_HASH_CACHE.lock().unwrap_or_else(|e| e.into_inner());
    cache.insert(
        pdf_abs.to_path_buf(),
        HashEntry {
            mtime_secs: mtime,
            hash: hash.clone(),
        },
    );
    Some(hash)
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

/// Cached single-page detection. Returns the same shape as the Python
/// sidecar's `/api/v1/moldet/extract-page` so the frontend can swap
/// implementations transparently.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedExtractPageResponse {
    pub results: Vec<serde_json::Value>,
    pub count: usize,
    /// `"cache"` (served from `index/detections/`), `"sidecar"` (model ran),
    /// or `"sidecar_error"` (cache miss + sidecar failed; `error` is set).
    pub source: String,
    /// Disk path that was actually read, useful for debug overlays.
    pub cache_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// Frontend-facing wrapper around `extractPage`. On cache hit, returns
/// instantly; on miss, proxies to the Python sidecar and persists the
/// result.
///
/// `project_root` + `doc_slug` together identify the PDF (we look it up
/// at `<project_root>/papers/<doc_slug>.pdf`). The image args are passed
/// through to the sidecar unchanged.
#[tauri::command]
pub async fn cached_extract_page(
    project_root: String,
    doc_slug: String,
    page: usize,
    image_base64: String,
    page_w_pts: f64,
    page_h_pts: f64,
    image_w: u32,
    image_h: u32,
) -> Result<CachedExtractPageResponse, String> {
    let project_root = clean_path(&project_root);
    let project_path = std::path::PathBuf::from(&project_root);

    // Resolve PDF path: convention is papers/<doc_slug>.pdf. If that
    // doesn't exist, we still try (and the cache will just be empty);
    // the sidecar call uses the cropped image directly, not the PDF.
    let pdf_abs = project_path.join(PAPERS_DIR).join(format!("{}.pdf", doc_slug));

    // Try cache.
    if let Some(hash) = pdf_hash_cached(&pdf_abs) {
        let cache = DetectionCache::new(&project_path);
        if let Some(entry) = cache.get(&doc_slug, page, &hash) {
            let results: Vec<serde_json::Value> = entry
                .detections
                .iter()
                .map(|d| detection_to_sidecar_shape(d, page))
                .collect();
            log::debug!(
                "[cached_extract_page] HIT {}/page {} ({} results)",
                doc_slug,
                page,
                results.len()
            );
            return Ok(CachedExtractPageResponse {
                count: results.len(),
                results,
                source: "cache".to_string(),
                cache_path: Some(format!(
                    "{}/{}/page_{:04}.json",
                    project_path
                        .join("index")
                        .join("detections")
                        .display(),
                    doc_slug,
                    page
                )),
                error: None,
            });
        }
    }

    // Cache miss: call the sidecar.
    let url = format!("{}/api/v1/moldet/extract-page", sidecar_url());
    let body = serde_json::json!({
        "image_base64": image_base64,
        "page_idx": (page as i32) - 1,           // sidecar is 0-indexed
        "page_w_pts": page_w_pts,
        "page_h_pts": page_h_pts,
        "image_w": image_w,
        "image_h": image_h,
    });

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(60))
        .build()
        .map_err(|e| format!("HTTP client init: {}", e))?;

    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Sidecar request failed: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let text = resp.text().await.unwrap_or_default();
        return Ok(CachedExtractPageResponse {
            results: vec![],
            count: 0,
            source: "sidecar_error".to_string(),
            cache_path: None,
            error: Some(format!("sidecar HTTP {} — {}", status, text)),
        });
    }

    #[derive(Deserialize)]
    struct SidecarExtract {
        results: Vec<serde_json::Value>,
        count: usize,
    }
    let parsed: SidecarExtract = resp
        .json()
        .await
        .map_err(|e| format!("Sidecar JSON parse failed: {}", e))?;

    // Persist to cache (best-effort).
    if let Some(hash) = pdf_hash_cached(&pdf_abs) {
        let cached: Vec<CachedDetection> = parsed
            .results
            .iter()
            .filter_map(|v| sidecar_to_cached(v))
            .collect();
        if !cached.is_empty() || !parsed.results.is_empty() {
            let now = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|d| d.as_secs_f64())
                .unwrap_or(0.0);
            let mtime = std::fs::metadata(&pdf_abs)
                .and_then(|m| m.modified())
                .ok()
                .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                .map(|d| d.as_secs_f64())
                .unwrap_or(0.0);
            let entry = PageDetection {
                doc_id: doc_slug.clone(),
                page,
                pdf_hash: hash,
                mtime,
                detected_at: now,
                schema_version: DETECTION_CACHE_SCHEMA_VERSION,
                detections: cached,
            };
            let cache = DetectionCache::new(&project_path);
            if let Err(e) = cache.put(&entry) {
                log::warn!("[cached_extract_page] cache write failed: {}", e);
            }
        }
    }

    log::debug!(
        "[cached_extract_page] MISS {}/page {} → sidecar ({} results)",
        doc_slug,
        page,
        parsed.count
    );
    Ok(CachedExtractPageResponse {
        results: parsed.results,
        count: parsed.count,
        source: "sidecar".to_string(),
        cache_path: None,
        error: None,
    })
}

// ---------------------------------------------------------------------------
// Shape conversion: detection_cache::Detection <-> sidecar ExtractionResult
// ---------------------------------------------------------------------------

/// Convert a cached `Detection` into the JSON shape the sidecar would
/// have returned. We only populate the fields the frontend uses for
/// bbox overlay + name; missing fields default to empty.
fn detection_to_sidecar_shape(d: &CachedDetection, page: usize) -> serde_json::Value {
    serde_json::json!({
        "esmiles": d.esmiles,
        "name": "",
        "source": "image",
        "moldet_conf": d.conf_moldet,
        "scribe_conf": d.conf_molscribe,
        "composite_conf": (d.conf_moldet + d.conf_molscribe) / 2.0,
        // vlm_chem doesn't currently populate bbox_pdf; we store zeros in
        // the cache. The frontend treats null bbox as "no overlay" so
        // this is safe.
        "bbox_pdf": if d.bbox_pdf[2] > d.bbox_pdf[0] && d.bbox_pdf[3] > d.bbox_pdf[1] {
            Some(d.bbox_pdf.to_vec())
        } else {
            None
        },
        "page_idx": page as i32,
        "context_text": "",
        "mol_img_path": d.crop_relpath,
        "status": "pending",
        "properties": {},
    })
}

/// Inverse: parse a sidecar result JSON into a `CachedDetection`.
/// Returns `None` if the JSON is missing required fields.
fn sidecar_to_cached(v: &serde_json::Value) -> Option<CachedDetection> {
    let bbox_arr = v.get("bbox_pdf").and_then(|b| b.as_array());
    let bbox_pdf = if let Some(arr) = bbox_arr {
        if arr.len() == 4 {
            [
                arr[0].as_f64().unwrap_or(0.0),
                arr[1].as_f64().unwrap_or(0.0),
                arr[2].as_f64().unwrap_or(0.0),
                arr[3].as_f64().unwrap_or(0.0),
            ]
        } else {
            [0.0, 0.0, 0.0, 0.0]
        }
    } else {
        [0.0, 0.0, 0.0, 0.0]
    };
    Some(CachedDetection {
        bbox_pdf,
        smiles: v
            .get("smiles")
            .and_then(|s| s.as_str())
            .unwrap_or("")
            .to_string(),
        esmiles: v
            .get("esmiles")
            .and_then(|s| s.as_str())
            .unwrap_or("")
            .to_string(),
        conf_moldet: v.get("moldet_conf").and_then(|n| n.as_f64()).unwrap_or(0.0),
        conf_molscribe: v
            .get("scribe_conf")
            .and_then(|n| n.as_f64())
            .unwrap_or(0.0),
        vlm_caption: v
            .get("vlm_caption")
            .and_then(|s| s.as_str())
            .map(|s| s.to_string()),
        vlm_esmiles: v
            .get("vlm_esmiles")
            .and_then(|s| s.as_str())
            .map(|s| s.to_string()),
        crop_relpath: v
            .get("mol_img_path")
            .and_then(|s| s.as_str())
            .unwrap_or("")
            .to_string(),
    })
}

// ---------------------------------------------------------------------------
// Cache management commands (used by Settings UI)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetectionCacheStats {
    /// Total disk usage in bytes (sum of all `index/detections/**/*.json`).
    pub disk_usage_bytes: u64,
    /// Number of cached pages.
    pub cached_page_count: usize,
    /// Number of distinct documents that have at least one cached page.
    pub cached_doc_count: usize,
    /// Schema version this build writes/reads.
    pub schema_version: u32,
}

#[tauri::command]
pub fn get_detection_cache_stats(project_root: String) -> Result<DetectionCacheStats, String> {
    let root = std::path::PathBuf::from(clean_path(&project_root));
    let cache = DetectionCache::new(&root);
    Ok(DetectionCacheStats {
        disk_usage_bytes: cache.disk_usage_bytes(),
        cached_page_count: cache.cached_page_count(),
        cached_doc_count: count_cached_docs(&root),
        schema_version: DETECTION_CACHE_SCHEMA_VERSION,
    })
}

#[tauri::command]
pub fn clear_detection_cache(project_root: String) -> Result<(), String> {
    let root = std::path::PathBuf::from(clean_path(&project_root));
    DetectionCache::new(&root)
        .clear_all()
        .map_err(|e: crate::core::error::AppError| e.to_string())
}

fn count_cached_docs(root: &std::path::Path) -> usize {
    let base = root.join("index").join("detections");
    let entries = match std::fs::read_dir(&base) {
        Ok(e) => e,
        Err(_) => return 0,
    };
    entries
        .flatten()
        .filter(|e| e.path().is_dir())
        .count()
}
