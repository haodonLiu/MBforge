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

use crate::core::config::constants::sidecar_url;
use crate::core::project::project::Project;
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
/// `project_root` + `doc_id` together identify the PDF. The source path is
/// resolved from the project index (DocumentProject `source.pdf`). The image
/// args are passed through to the sidecar unchanged.
#[tauri::command]
pub async fn cached_extract_page(
    project_root: String,
    doc_id: String,
    page: usize,
    image_base64: String,
    page_w_pts: f64,
    page_h_pts: f64,
    image_w: u32,
    image_h: u32,
) -> Result<CachedExtractPageResponse, String> {
    let project_root = clean_path(&project_root);
    let project_path = std::path::PathBuf::from(&project_root);

    // Resolve PDF path from the project index. Falls back to the legacy
    // `papers/<doc_slug>.pdf` convention if the document is not yet in a
    // DocumentProject.
    let (pdf_abs, doc_slug, is_legacy) = match Project::open(&project_path)
        .and_then(|p| p.get_document_source_path(&doc_id))
    {
        Some(path) => {
            let slug = path
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or(&doc_id)
                .to_string();
            let legacy = path.starts_with(project_path.join(crate::core::config::constants::PAPERS_DIR));
            (path, slug, legacy)
        }
        None => {
            // Fallback: assume legacy papers/<doc_id>.pdf for backwards compat.
            let path = project_path
                .join(crate::core::config::constants::PAPERS_DIR)
                .join(format!("{}.pdf", doc_id));
            (path, doc_id.clone(), true)
        }
    };

    // Try cache.
    if let Some(hash) = pdf_hash_cached(&pdf_abs) {
        let cache = if is_legacy {
            DetectionCache::new(&project_path)
        } else {
            DetectionCache::for_document_project(&project_path, &doc_id)
        };
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
            let cache_path = if is_legacy {
                project_path.join("index").join("detections")
            } else {
                project_path
                    .join(crate::core::config::constants::PROJECTS_DIR)
                    .join(&doc_id)
                    .join("cache")
                    .join("detections")
            };
            return Ok(CachedExtractPageResponse {
                count: results.len(),
                results,
                source: "cache".to_string(),
                cache_path: Some(format!(
                    "{}/{}/page_{:04}.json",
                    cache_path.display(),
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
        .map_err(|e| {
            if e.is_connect() || e.is_timeout() {
                format!(
                    "无法连接到 Python sidecar ({})。请确认模型服务器已启动：uv run uvicorn mbforge.server:app --host 127.0.0.1 --port 18792",
                    url
                )
            } else {
                format!("Sidecar request failed: {}", e)
            }
        })?;

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
            let cache = if is_legacy {
                DetectionCache::new(&project_path)
            } else {
                DetectionCache::for_document_project(&project_path, &doc_id)
            };
            if let Err(e) = cache.put(&entry) {
                log::warn!("[cached_extract_page] cache write failed: {}", e);
            }
        }
    }

    log::debug!(
        "[cached_extract_page] MISS {}/page {} → sidecar ({} results)",
        doc_id,
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

/// 仅读取 detection cache，不触发 sidecar。用于 PDF 预览进入检测模式时
/// 优先展示已缓存的 bbox，避免自动调用慢速 MolScribe。
#[tauri::command]
pub async fn get_cached_page_detections(
    project_root: String,
    doc_id: String,
    page: usize,
) -> Result<CachedExtractPageResponse, String> {
    let project_root = clean_path(&project_root);
    let project_path = std::path::PathBuf::from(&project_root);

    // Resolve PDF path from the project index.
    let (pdf_abs, doc_slug, is_legacy) = match Project::open(&project_path)
        .and_then(|p| p.get_document_source_path(&doc_id))
    {
        Some(path) => {
            let slug = path
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or(&doc_id)
                .to_string();
            let legacy = path.starts_with(project_path.join(crate::core::config::constants::PAPERS_DIR));
            (path, slug, legacy)
        }
        None => {
            let path = project_path
                .join(crate::core::config::constants::PAPERS_DIR)
                .join(format!("{}.pdf", doc_id));
            (path, doc_id.clone(), true)
        }
    };

    if let Some(hash) = pdf_hash_cached(&pdf_abs) {
        let cache = if is_legacy {
            DetectionCache::new(&project_path)
        } else {
            DetectionCache::for_document_project(&project_path, &doc_id)
        };
        if let Some(entry) = cache.get(&doc_slug, page, &hash) {
            let results: Vec<serde_json::Value> = entry
                .detections
                .iter()
                .map(|d| detection_to_sidecar_shape(d, page))
                .collect();
            log::debug!(
                "[get_cached_page_detections] HIT {}/page {} ({} results)",
                doc_id,
                page,
                results.len()
            );
            let cache_path = if is_legacy {
                project_path.join("index").join("detections")
            } else {
                project_path
                    .join(crate::core::config::constants::PROJECTS_DIR)
                    .join(&doc_id)
                    .join("cache")
                    .join("detections")
            };
            return Ok(CachedExtractPageResponse {
                count: results.len(),
                results,
                source: "cache".to_string(),
                cache_path: Some(format!(
                    "{}/{}/page_{:04}.json",
                    cache_path.display(),
                    doc_slug,
                    page
                )),
                error: None,
            });
        }
    }

    Ok(CachedExtractPageResponse {
        results: vec![],
        count: 0,
        source: "cache_miss".to_string(),
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
    let composite_conf = if d.conf_molscribe > 0.0 {
        (d.conf_moldet + d.conf_molscribe) / 2.0
    } else {
        d.conf_moldet
    };
    let has_structure = d.has_structure();
    serde_json::json!({
        "esmiles": d.esmiles.as_deref().unwrap_or(""),
        "smiles": d.smiles.as_deref().unwrap_or(""),
        "name": "",
        "source": "image",
        "moldet_conf": d.conf_moldet,
        "scribe_conf": d.conf_molscribe,
        "composite_conf": composite_conf,
        "bbox_pdf": if d.bbox_pdf[2] > d.bbox_pdf[0] && d.bbox_pdf[3] > d.bbox_pdf[1] {
            Some(d.bbox_pdf.to_vec())
        } else {
            None
        },
        "page_idx": page as i32,
        "context_text": "",
        "mol_img_path": d.crop_relpath.as_deref().unwrap_or(""),
        "status": if has_structure { "done" } else { "pending" },
        "is_quick_scan": d.is_quick_scan,
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
            .filter(|s| !s.is_empty())
            .map(|s| s.to_string()),
        esmiles: v
            .get("esmiles")
            .and_then(|s| s.as_str())
            .filter(|s| !s.is_empty())
            .map(|s| s.to_string()),
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
            .filter(|s| !s.is_empty())
            .map(|s| s.to_string()),
        is_quick_scan: false,
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

/// VLM 化学共指检测：调用 sidecar `/api/v1/moldet/coref` 识别页面图中的
/// 分子 + 标识符 bbox 及二者配对关系。返回 raw `CorefResult` + 转换后的
/// `Vec<CorefMolecule>`（含 PDF 归一化坐标与标号）。
///
/// - `image_path`: 绝对或 project_root-相对的图像文件路径
/// - `sidecar_url`: sidecar base URL（默认 `crate::core::constants::sidecar_url()`）
/// - `use_molscribe` / `use_ocr`: 是否启用对应子模型
/// - `page_idx`: PDF 页码（0-based），写入 `CorefMolecule.page`
/// - `page_w_pts` / `page_h_pts`: 页面尺寸（pts），用于坐标归一化
/// - `image_w` / `image_h`: 图像像素尺寸
#[tauri::command]
pub async fn vlm_chem_coref(
    project_root: String,
    image_path: String,
    sidecar_url: Option<String>,
    use_molscribe: Option<bool>,
    use_ocr: Option<bool>,
    page_idx: i32,
    page_w_pts: f64,
    page_h_pts: f64,
    image_w: u32,
    image_h: u32,
) -> Result<
    crate::parsers::chem::vlm_chem::CorefOutput,
    String,
> {
    use crate::parsers::chem::vlm_chem;

    let resolved = if std::path::Path::new(&image_path).is_absolute() {
        std::path::PathBuf::from(&image_path)
    } else {
        std::path::PathBuf::from(clean_path(&project_root)).join(&image_path)
    };
    let url = sidecar_url.unwrap_or_else(crate::core::constants::sidecar_url);

    let coref = vlm_chem::detect_coref(
        resolved.to_string_lossy().as_ref(),
        &url,
        use_molscribe.unwrap_or(true),
        use_ocr.unwrap_or(true),
    )
    .await?;

    let molecules = vlm_chem::coref_to_molecules(
        &coref,
        page_idx,
        page_w_pts,
        page_h_pts,
        image_w,
        image_h,
    );

    Ok(vlm_chem::CorefOutput { coref, molecules })
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

/// 给定 PDF 页面上的分子 bbox，找出最接近的标签（化合物 / 章节类）。
/// 内部用 `label_assoc::extract_page_text_lines` 抽取文字行，再调
/// `label_assoc::find_label_for_bbox` 做垂直方向上最近匹配。
///
/// - `pdf_path`: 绝对或 project_root-相对的 PDF 路径
/// - `page`: 0-based 页号
/// - `page_h_pts`: 页面高度（pts）
/// - `mol_bbox`: `[x1, y1, x2, y2]` PDF 坐标（bottom-left 原点）
/// - `v_search_pts`: 垂直方向搜索半径，默认 80 pts（约 1 英寸）
#[tauri::command]
pub fn label_for_mol_bbox(
    project_root: String,
    pdf_path: String,
    page: u32,
    page_h_pts: f64,
    mol_bbox: [f64; 4],
    v_search_pts: Option<f64>,
) -> Result<Option<crate::parsers::chem::label_assoc::LabelMatch>, String> {
    use crate::parsers::chem::label_assoc;

    let pdf_full = if std::path::Path::new(&pdf_path).is_absolute() {
        std::path::PathBuf::from(&pdf_path)
    } else {
        std::path::PathBuf::from(clean_path(&project_root)).join(&pdf_path)
    };

    let text_lines = label_assoc::extract_page_text_lines(
        pdf_full.to_string_lossy().as_ref(),
        page,
        page_h_pts,
    )?;

    let bbox_tuple = (mol_bbox[0], mol_bbox[1], mol_bbox[2], mol_bbox[3]);
    let search = v_search_pts.unwrap_or(80.0);
    Ok(label_assoc::find_label_for_bbox(
        bbox_tuple,
        &text_lines,
        page_h_pts,
        search,
    ))
}

// ---------------------------------------------------------------------------
// 批量快速 MoldDet 扫描
// ---------------------------------------------------------------------------

/// 批量快速 MoldDet 扫描请求。
#[derive(Debug, Deserialize)]
pub struct BatchQuickMoldetRequest {
    pub project_root: String,
    pub doc_ids: Vec<String>,
}

/// 批量快速 MoldDet 扫描结果。
#[derive(Debug, Serialize)]
pub struct BatchQuickMoldetResponse {
    pub results: Vec<crate::parsers::pipeline::QuickMoldetDocResult>,
    pub processed: usize,
    pub total: usize,
    pub errors: Vec<String>,
}

/// 对项目中的多个 PDF 进行快速 MoldDet 扫描。
///
/// 只检测分子 bbox，不识别 SMILES；扫描完成后更新项目 index 中每个文档的
/// `moldet_status` 和 `moldet_pages` 字段，方便前端文档列表展示“哪些页面
/// 可能存在分子”。
#[tauri::command]
pub async fn batch_quick_moldet_scan(
    request: BatchQuickMoldetRequest,
) -> Result<BatchQuickMoldetResponse, String> {
    use crate::core::project::project::Project;
    use crate::parsers::pipeline::quick_moldet_scan_pdf;

    let project_root = clean_path(&request.project_root);
    let root_path = std::path::PathBuf::from(&project_root);
    let sidecar = sidecar_url();
    let config = crate::core::config::settings::AppConfig::load();
    let batch_size = config.moldet.moldet_batch_size.max(1);

    let project = Project::open(&root_path).ok_or_else(|| {
        format!("Cannot open project at {}", project_root)
    })?;

    let mut pdf_entries: Vec<(String, String)> = Vec::new(); // (doc_id, abs_path)
    {
        let docs = project.list_documents();
        for doc in docs {
            if doc.doc_type != "pdf" {
                continue;
            }
            if !request.doc_ids.is_empty() && !request.doc_ids.contains(&doc.doc_id) {
                continue;
            }
            let abs_path = root_path.join(&doc.path);
            if abs_path.exists() {
                pdf_entries.push((doc.doc_id.clone(), abs_path.to_string_lossy().to_string()));
            }
        }
    }

    let total = pdf_entries.len();
    let mut results: Vec<crate::parsers::pipeline::QuickMoldetDocResult> = Vec::new();
    let mut errors: Vec<String> = Vec::new();

    for (doc_id, abs_path) in pdf_entries {
        match quick_moldet_scan_pdf(&abs_path, &root_path, &sidecar, &doc_id, batch_size).await {
            Ok(mut result) => {
                let pages = result.pages_with_molecules.clone();
                let status = if pages.is_empty() { "no_molecule" } else { "has_molecule" };
                let mut proj = Project::open(&root_path).ok_or_else(|| {
                    format!("Cannot open project at {}", project_root)
                })?;
                proj.set_document_moldet(&doc_id, status, &pages);
                result.moldet_status = status.to_string();
                results.push(result);
            }
            Err(e) => {
                log::error!("[batch_quick_moldet_scan] failed for {}: {}", abs_path, e);
                errors.push(format!("{}: {}", abs_path, e));
                // 仍然记录失败状态
                if let Some(mut proj) = Project::open(&root_path) {
                    proj.set_document_moldet(&doc_id, "error", &[]);
                }
            }
        }
    }

    Ok(BatchQuickMoldetResponse {
        processed: results.len(),
        total,
        results,
        errors,
    })
}
