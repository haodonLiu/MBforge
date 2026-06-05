//! MolDet / MolScribe Sidecar 客户端
//!
//! 调用 Python sidecar 的分子检测与识别端点：
//! - POST /api/v1/moldet/detect-page  → 检测分子 bbox
//! - POST /api/v1/vlm/molscribe       → 识别 SMILES
//!
//! Rust 端负责：截图/获取图片 → detect-page → 裁剪 → molscribe → 保存结果

use base64::Engine;
use image::GenericImageView;
use std::path::{Path, PathBuf};

/// MolDet 检测到的边界框（图像坐标系，像素单位）
#[derive(Debug, Clone)]
pub struct Bbox {
    pub x1: f64,
    pub y1: f64,
    pub x2: f64,
    pub y2: f64,
    pub conf: f64,
}

/// MolScribe 识别结果
#[derive(Debug, Clone)]
pub struct MolScribeResult {
    pub esmiles: String,
    pub confidence: f64,
    pub success: bool,
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

/// 读取图片并编码为 base64
fn read_image_base64(path: &str) -> Result<String, String> {
    let bytes = std::fs::read(path)
        .map_err(|e| format!("Failed to read image {}: {}", path, e))?;
    Ok(base64::engine::general_purpose::STANDARD.encode(&bytes))
}

/// 调用 sidecar /api/v1/moldet/detect-page 检测分子区域
///
/// # Arguments
/// * `image_path` - 本地图片路径（PNG/JPG）
/// * `sidecar_url` - sidecar 地址，如 http://127.0.0.1:18792
pub async fn detect_page(image_path: &str, sidecar_url: &str) -> Result<Vec<Bbox>, String> {
    let image_b64 = read_image_base64(image_path)?;

    let body = serde_json::json!({
        "image_base64": image_b64,
    });

    let client = crate::core::http::client_120s();
    let url = format!("{}/api/v1/moldet/detect-page", sidecar_url.trim_end_matches('/'));

    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("MolDet detect-page request failed: {}", e))?;

    let status = resp.status();
    let text = resp
        .text()
        .await
        .map_err(|e| format!("MolDet detect-page read error: {}", e))?;

    if !status.is_success() {
        return Err(format!(
            "MolDet detect-page HTTP {}: {}",
            status,
            &text[..text.floor_char_boundary(200)]
        ));
    }

    let val: serde_json::Value = serde_json::from_str(&text)
        .map_err(|e| format!("MolDet detect-page JSON parse error: {}", e))?;

    let boxes = val["boxes"].as_array().unwrap_or(&vec![]).clone();
    let mut result = Vec::with_capacity(boxes.len());
    for b in boxes {
        result.push(Bbox {
            x1: b["x1"].as_f64().unwrap_or(0.0),
            y1: b["y1"].as_f64().unwrap_or(0.0),
            x2: b["x2"].as_f64().unwrap_or(0.0),
            y2: b["y2"].as_f64().unwrap_or(0.0),
            conf: b["conf"].as_f64().unwrap_or(0.0),
        });
    }

    Ok(result)
}

/// 调用 sidecar /api/v1/vlm/molscribe 识别化学结构图
///
/// # Arguments
/// * `image_path` - 本地图片路径
/// * `sidecar_url` - sidecar 地址
pub async fn molscribe(image_path: &str, sidecar_url: &str) -> Result<MolScribeResult, String> {
    let image_b64 = read_image_base64(image_path)?;

    let ext = Path::new(image_path)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("png")
        .to_string();

    let body = serde_json::json!({
        "image_base64": image_b64,
        "ext": ext,
    });

    let client = crate::core::http::client_120s();
    let url = format!("{}/api/v1/vlm/molscribe", sidecar_url.trim_end_matches('/'));

    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("MolScribe request failed: {}", e))?;

    let status = resp.status();
    let text = resp
        .text()
        .await
        .map_err(|e| format!("MolScribe read error: {}", e))?;

    if !status.is_success() {
        return Err(format!(
            "MolScribe HTTP {}: {}",
            status,
            &text[..text.floor_char_boundary(200)]
        ));
    }

    let val: serde_json::Value = serde_json::from_str(&text)
        .map_err(|e| format!("MolScribe JSON parse error: {}", e))?;

    let esmiles = val["esmiles"].as_str().unwrap_or("").to_string();
    let confidence = val["confidence"].as_f64().unwrap_or(0.0);
    let success = val["success"].as_bool().unwrap_or(false);
    let has_esmiles = !esmiles.is_empty();

    Ok(MolScribeResult {
        esmiles,
        confidence,
        success: success && has_esmiles,
    })
}

/// 对单页图片执行完整处理：检测 → 裁剪 → 识别 → 保存
///
/// # Arguments
/// * `image_path` - 整页图片路径
/// * `page_idx` - 页码（0-based）
/// * `sidecar_url` - sidecar 地址
/// * `output_dir` - 裁剪图片保存目录
///
/// # Returns
/// 识别出的分子列表（已保存裁剪图到 output_dir）
pub async fn process_page_image(
    image_path: &str,
    page_idx: i32,
    sidecar_url: &str,
    output_dir: &Path,
) -> Result<Vec<DetectedMolecule>, String> {
    // 1. 检测分子区域
    let bboxes = detect_page(image_path, sidecar_url).await?;
    if bboxes.is_empty() {
        return Ok(vec![]);
    }

    std::fs::create_dir_all(output_dir)
        .map_err(|e| format!("Failed to create output dir: {}", e))?;

    // 2. 打开原图
    let img = image::open(image_path)
        .map_err(|e| format!("Failed to open image {}: {}", image_path, e))?;
    let (img_w, img_h) = img.dimensions();

    let mut results = Vec::new();

    for (idx, bbox) in bboxes.iter().enumerate() {
        // 3. 裁剪（注意边界）
        let x1 = bbox.x1.max(0.0) as u32;
        let y1 = bbox.y1.max(0.0) as u32;
        let x2 = bbox.x2.min(img_w as f64) as u32;
        let y2 = bbox.y2.min(img_h as f64) as u32;

        if x2 <= x1 || y2 <= y1 {
            log::warn!(
                "[moldet_client] Invalid bbox for page {} mol {}: {:?}",
                page_idx, idx, bbox
            );
            continue;
        }

        let crop = img.crop_imm(x1, y1, x2 - x1, y2 - y1);

        // 4. 保存裁剪图
        let crop_filename = format!("page_{:04}_mol_{:03}.png", page_idx, idx);
        let crop_path = output_dir.join(&crop_filename);
        crop.save(&crop_path)
            .map_err(|e| format!("Failed to save crop {}: {}", crop_path.display(), e))?;

        // 5. MolScribe 识别
        match molscribe(crop_path.to_str().unwrap_or(""), sidecar_url).await {
            Ok(ms_result) if ms_result.success && !ms_result.esmiles.is_empty() => {
                results.push(DetectedMolecule {
                    esmiles: ms_result.esmiles,
                    confidence: ms_result.confidence,
                    moldet_conf: bbox.conf,
                    page: page_idx,
                    crop_path: crop_path.to_string_lossy().to_string(),
                });
            }
            Ok(_) => {
                log::debug!(
                    "[moldet_client] MolScribe returned empty for page {} mol {}",
                    page_idx, idx
                );
            }
            Err(e) => {
                log::warn!(
                    "[moldet_client] MolScribe failed for page {} mol {}: {}",
                    page_idx, idx, e
                );
            }
        }
    }

    log::info!(
        "[moldet_client] Page {}: detected {} molecules, recognized {} SMILES",
        page_idx,
        bboxes.len(),
        results.len()
    );

    Ok(results)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_read_image_base64_not_found() {
        let result = read_image_base64("/nonexistent/path.png");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Failed to read image"));
    }

    #[test]
    fn test_molscribe_result_default() {
        let r = MolScribeResult {
            esmiles: "CCO".into(),
            confidence: 0.95,
            success: true,
        };
        assert_eq!(r.esmiles, "CCO");
        assert!(r.success);
    }
}
