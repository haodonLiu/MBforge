//! VLM 化学结构识别 + MolDet 分子检测客户端
//!
//! 统一调用 Python sidecar 的化学图像识别端点：
//! - POST /api/v1/vlm/molscribe  → 识别 SMILES（两种响应格式）
//! - POST /api/v1/moldet/detect-page → 检测分子 bbox
//! - POST /api/v1/vlm/describe → 通用图片描述

use base64::Engine;
use image::GenericImageView;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

// ─── 共享类型 ────────────────────────────────────────────────────

/// VLM API 配置
pub struct VlmConfig {
    pub sidecar_url: String,
}

impl Default for VlmConfig {
    fn default() -> Self {
        Self {
            sidecar_url: crate::core::config::constants::sidecar_url(),
        }
    }
}

/// MolScribe 识别结果（简单格式，用于 image_to_esmiles）
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ChemImageResult {
    pub esmiles: String,
    pub confidence: f64,
}

/// MolScribe 识别结果（完整格式，用于 process_page_image）
#[derive(Debug, Clone)]
pub struct MolScribeResult {
    pub esmiles: String,
    pub confidence: f64,
    pub success: bool,
}

/// MolDet 检测到的边界框（图像坐标系，像素单位）
#[derive(Debug, Clone)]
pub struct Bbox {
    pub x1: f64,
    pub y1: f64,
    pub x2: f64,
    pub y2: f64,
    pub conf: f64,
}

/// 检测并识别出的分子（单页中的单个分子）
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct DetectedMolecule {
    pub esmiles: String,
    pub confidence: f64,
    pub moldet_conf: f64,
    pub page: i32,
    pub crop_path: String,
}

// ─── 共享工具 ────────────────────────────────────────────────────

/// 读取图片并编码为 base64
pub(crate) fn read_image_base64(path: &str) -> Result<String, String> {
    let bytes = std::fs::read(path).map_err(|e| format!("Failed to read image {}: {}", path, e))?;
    Ok(base64::engine::general_purpose::STANDARD.encode(&bytes))
}

// ─── MolScribe 化学结构识别 ──────────────────────────────────────

/// 用 MolScribe 识别化学结构图 → esmiles（简单格式，读 val["smiles"]）
pub async fn image_to_esmiles(
    image_path: &str,
    config: &VlmConfig,
) -> Result<ChemImageResult, String> {
    let image_b64 = read_image_base64(image_path)?;

    let body = serde_json::json!({ "image_base64": image_b64 });
    let client = crate::core::http::client_120s();
    let url = format!("{}/api/v1/vlm/molscribe", config.sidecar_url.trim_end_matches('/'));

    let resp = client.post(&url).json(&body).send().await
        .map_err(|e| format!("MolScribe request failed: {}", e))?;
    let status = resp.status();
    let text = resp.text().await
        .map_err(|e| format!("MolScribe read error: {}", e))?;

    if !status.is_success() {
        return Err(format!("MolScribe HTTP {}: {}", status, &text[..text.floor_char_boundary(200)]));
    }

    let val: serde_json::Value = serde_json::from_str(&text)
        .map_err(|e| format!("MolScribe JSON parse error: {}", e))?;

    Ok(ChemImageResult {
        esmiles: val["smiles"].as_str().unwrap_or("").to_string(),
        confidence: val["confidence"].as_f64().unwrap_or(0.0),
    })
}

/// 用 MolScribe 批量识别多张图片
pub async fn batch_image_to_esmiles(
    image_paths: &[(String, String)],
    config: &VlmConfig,
) -> Vec<(String, ChemImageResult)> {
    let mut results = Vec::new();
    for (filename, full_path) in image_paths {
        match image_to_esmiles(full_path, config).await {
            Ok(result) => results.push((filename.clone(), result)),
            Err(e) => log::warn!("[vlm_chem] failed for {}: {}", filename, e),
        }
    }
    results
}

/// 调用 sidecar /api/v1/vlm/molscribe 识别化学结构图（完整格式，读 val["esmiles"]）
pub async fn molscribe(image_path: &str, sidecar_url: &str) -> Result<MolScribeResult, String> {
    let image_b64 = read_image_base64(image_path)?;

    let ext = Path::new(image_path)
        .extension().and_then(|e| e.to_str()).unwrap_or("png").to_string();

    let body = serde_json::json!({ "image_base64": image_b64, "ext": ext });
    let client = crate::core::http::client_120s();
    let url = format!("{}/api/v1/vlm/molscribe", sidecar_url.trim_end_matches('/'));

    let resp = client.post(&url).json(&body).send().await
        .map_err(|e| format!("MolScribe request failed: {}", e))?;
    let status = resp.status();
    let text = resp.text().await
        .map_err(|e| format!("MolScribe read error: {}", e))?;

    if !status.is_success() {
        return Err(format!("MolScribe HTTP {}: {}", status, &text[..text.floor_char_boundary(200)]));
    }

    let val: serde_json::Value = serde_json::from_str(&text)
        .map_err(|e| format!("MolScribe JSON parse error: {}", e))?;

    let esmiles = val["esmiles"].as_str().unwrap_or("").to_string();
    let confidence = val["confidence"].as_f64().unwrap_or(0.0);
    let success = val["success"].as_bool().unwrap_or(false);
    let has_esmiles = !esmiles.is_empty();

    Ok(MolScribeResult { esmiles, confidence, success: success && has_esmiles })
}

// ─── MolDet 分子检测 ────────────────────────────────────────────

/// 调用 sidecar /api/v1/moldet/detect-page 检测分子区域
pub async fn detect_page(image_path: &str, sidecar_url: &str) -> Result<Vec<Bbox>, String> {
    let image_b64 = read_image_base64(image_path)?;

    let body = serde_json::json!({ "image_base64": image_b64 });
    let client = crate::core::http::client_120s();
    let url = format!("{}/api/v1/moldet/detect-page", sidecar_url.trim_end_matches('/'));

    let resp = client.post(&url).json(&body).send().await
        .map_err(|e| format!("MolDet detect-page request failed: {}", e))?;
    let status = resp.status();
    let text = resp.text().await
        .map_err(|e| format!("MolDet detect-page read error: {}", e))?;

    if !status.is_success() {
        return Err(format!("MolDet detect-page HTTP {}: {}", status, &text[..text.floor_char_boundary(200)]));
    }

    let val: serde_json::Value = serde_json::from_str(&text)
        .map_err(|e| format!("MolDet detect-page JSON parse error: {}", e))?;

    let boxes = val["boxes"].as_array().unwrap_or(&vec![]).clone();
    Ok(boxes.iter().map(|b| Bbox {
        x1: b["x1"].as_f64().unwrap_or(0.0),
        y1: b["y1"].as_f64().unwrap_or(0.0),
        x2: b["x2"].as_f64().unwrap_or(0.0),
        y2: b["y2"].as_f64().unwrap_or(0.0),
        conf: b["conf"].as_f64().unwrap_or(0.0),
    }).collect())
}

/// 对单页图片执行完整处理：检测 → 裁剪 → 识别 → 保存
pub async fn process_page_image(
    image_path: &str,
    page_idx: i32,
    sidecar_url: &str,
    output_dir: &Path,
) -> Result<Vec<DetectedMolecule>, String> {
    let bboxes = detect_page(image_path, sidecar_url).await?;
    if bboxes.is_empty() { return Ok(vec![]); }

    std::fs::create_dir_all(output_dir)
        .map_err(|e| format!("Failed to create output dir: {}", e))?;

    let img = image::open(image_path)
        .map_err(|e| format!("Failed to open image {}: {}", image_path, e))?;
    let (img_w, img_h) = img.dimensions();
    let mut results = Vec::new();

    for (idx, bbox) in bboxes.iter().enumerate() {
        let x1 = bbox.x1.max(0.0) as u32;
        let y1 = bbox.y1.max(0.0) as u32;
        let x2 = bbox.x2.min(img_w as f64) as u32;
        let y2 = bbox.y2.min(img_h as f64) as u32;

        if x2 <= x1 || y2 <= y1 {
            log::warn!("[vlm_chem] Invalid bbox for page {} mol {}: {:?}", page_idx, idx, bbox);
            continue;
        }

        let crop = img.crop_imm(x1, y1, x2 - x1, y2 - y1);
        let crop_filename = format!("page_{:04}_mol_{:03}.png", page_idx, idx);
        let crop_path = output_dir.join(&crop_filename);
        crop.save(&crop_path)
            .map_err(|e| format!("Failed to save crop {}: {}", crop_path.display(), e))?;

        match molscribe(crop_path.to_str().unwrap_or(""), sidecar_url).await {
            Ok(ms) if ms.success && !ms.esmiles.is_empty() => {
                results.push(DetectedMolecule {
                    esmiles: ms.esmiles, confidence: ms.confidence,
                    moldet_conf: bbox.conf, page: page_idx,
                    crop_path: crop_path.to_string_lossy().to_string(),
                });
            }
            Ok(_) => log::debug!("[vlm_chem] MolScribe empty for page {} mol {}", page_idx, idx),
            Err(e) => log::warn!("[vlm_chem] MolScribe failed for page {} mol {}: {}", page_idx, idx, e),
        }
    }

    log::info!("[vlm_chem] Page {}: detected {} mols, recognized {} SMILES", page_idx, bboxes.len(), results.len());
    Ok(results)
}

// ─── VLM 通用图片描述 ───────────────────────────────────────────

/// 通用 VLM 图片描述 — 调 Python sidecar `/api/v1/vlm/describe`
pub async fn describe_image(image_path: &str, prompt: &str, sidecar_url: &str) -> Result<String, String> {
    let image_b64 = read_image_base64(image_path)?;

    let ext = Path::new(image_path)
        .extension().and_then(|e| e.to_str()).unwrap_or("png").to_string();

    let body = serde_json::json!({
        "image_base64": image_b64,
        "prompt": if prompt.is_empty() { "请详细描述这张图片的内容" } else { prompt },
        "ext": ext,
    });

    let client = crate::core::http::client_300s();
    let url = format!("{}/api/v1/vlm/describe", sidecar_url.trim_end_matches('/'));

    let resp = client.post(&url).json(&body).send().await
        .map_err(|e| format!("VLM describe request failed: {}", e))?;
    let status = resp.status();
    let text = resp.text().await
        .map_err(|e| format!("VLM describe read error: {}", e))?;

    if !status.is_success() {
        return Err(format!("VLM describe HTTP {}: {}", status, &text[..text.floor_char_boundary(200)]));
    }

    let val: serde_json::Value = serde_json::from_str(&text)
        .map_err(|e| format!("VLM JSON parse error: {}", e))?;

    Ok(val["description"].as_str().unwrap_or("").to_string())
}

/// VLM 图片描述缓存
pub struct ImageCaptionCache {
    path: PathBuf,
    entries: HashMap<String, CacheEntry>,
    dirty: bool,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
struct CacheEntry {
    caption: String,
    #[serde(default)]
    timestamp: u64,
}

impl ImageCaptionCache {
    pub fn new(project_root: &Path) -> Self {
        let path = project_root
            .join(crate::core::config::constants::INDEX_DIR)
            .join("image-caption-cache.json");
        let entries = if path.exists() {
            std::fs::read_to_string(&path).ok()
                .and_then(|s| serde_json::from_str::<HashMap<String, CacheEntry>>(&s).ok())
                .unwrap_or_default()
        } else { HashMap::new() };
        Self { path, entries, dirty: false }
    }

    pub fn get(&self, sha256: &str) -> Option<String> {
        self.entries.get(sha256).map(|e| e.caption.clone())
    }

    pub fn set(&mut self, sha256: &str, caption: &str) {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_secs();
        self.entries.insert(sha256.to_string(), CacheEntry { caption: caption.to_string(), timestamp: now });
        self.dirty = true;
    }

    pub fn save(&mut self) -> Result<(), String> {
        if !self.dirty { return Ok(()); }
        if let Some(parent) = self.path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| format!("Failed to create cache dir: {}", e))?;
        }
        let json = serde_json::to_string_pretty(&self.entries)
            .map_err(|e| format!("Failed to serialize cache: {}", e))?;
        std::fs::write(&self.path, json).map_err(|e| format!("Failed to write cache: {}", e))?;
        self.dirty = false;
        Ok(())
    }

    pub fn sha256_file(path: &Path) -> Result<String, String> {
        use sha2::Digest;
        let mut file = std::fs::File::open(path)
            .map_err(|e| format!("Failed to open image {}: {}", path.display(), e))?;
        let mut hasher = sha2::Sha256::new();
        std::io::copy(&mut file, &mut hasher)
            .map_err(|e| format!("Failed to hash image {}: {}", path.display(), e))?;
        Ok(format!("{:x}", hasher.finalize()))
    }
}

/// 带缓存的 VLM 图片描述
pub async fn describe_image_cached(
    image_path: &str, prompt: &str, sidecar_url: &str, cache: &mut ImageCaptionCache,
) -> Result<String, String> {
    let hash = ImageCaptionCache::sha256_file(Path::new(image_path))?;
    if let Some(cached) = cache.get(&hash) {
        log::debug!("[vlm_chem] Caption cache HIT for {}", image_path);
        return Ok(cached);
    }
    log::debug!("[vlm_chem] Caption cache MISS for {}", image_path);
    let caption = describe_image(image_path, prompt, sidecar_url).await?;
    cache.set(&hash, &caption);
    Ok(caption)
}

/// 判断图片是否可能是化学结构图
pub fn is_likely_chemical_structure(filename: &str, region: Option<&str>) -> bool {
    if let Some(r) = region {
        return matches!(r, "figure" | "structure" | "table");
    }
    let lower = filename.to_lowercase();
    lower.contains("struct") || lower.contains("mol") || lower.contains("chem")
        || lower.contains("table") || lower.contains("fig")
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_read_image_base64_not_found() {
        assert!(read_image_base64("/nonexistent/path.png").is_err());
    }

    #[test]
    fn test_chem_image_result() {
        let r = ChemImageResult { esmiles: "CCO".into(), confidence: 0.95 };
        assert_eq!(r.esmiles, "CCO");
    }

    #[test]
    fn test_molscribe_result() {
        let r = MolScribeResult { esmiles: "CCO".into(), confidence: 0.95, success: true };
        assert!(r.success);
    }

    #[test]
    fn test_is_likely_chemical_structure() {
        assert!(is_likely_chemical_structure("page_05_img_02.png", Some("structure")));
        assert!(is_likely_chemical_structure("fig_table_1.png", None));
        assert!(!is_likely_chemical_structure("page_01_bg.png", None));
    }

    #[test]
    fn test_vlm_config_default() {
        let config = VlmConfig::default();
        assert!(!config.sidecar_url.is_empty());
    }
}
