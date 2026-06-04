use base64::Engine;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

/// === A2: VLM 化学结构识别模块 ===
///
/// 将 MinerU 提取出的化学结构图传给 Python sidecar MolScribe 端点，
/// 返回 SMILES 字符串。
///
/// 调用路径：Rust → HTTP POST → /api/v1/vlm/molscribe (Python sidecar)

/// VLM API 配置
pub struct VlmConfig {
    pub sidecar_url: String,
}

impl Default for VlmConfig {
    fn default() -> Self {
        Self {
            sidecar_url: crate::core::constants::sidecar_url(),
        }
    }
}

/// MolScribe 识别结果
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ChemImageResult {
    pub esmiles: String,
    pub confidence: f64,
}

/// 用 MolScribe 识别化学结构图 → esmiles
///
/// # Arguments
/// * `image_path` - 图片本地路径
/// * `config` - VLM 端点配置
pub async fn image_to_esmiles(
    image_path: &str,
    config: &VlmConfig,
) -> Result<ChemImageResult, String> {
    let image_b64 = read_image_base64(image_path)?;

    let body = serde_json::json!({
        "image_base64": image_b64,
    });

    let client = crate::core::http::client_120s();

    let url = format!(
        "{}/api/v1/vlm/molscribe",
        config.sidecar_url.trim_end_matches('/')
    );

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

    let val: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| format!("MolScribe JSON parse error: {}", e))?;

    let esmiles = val["smiles"].as_str().unwrap_or("").to_string();
    let confidence = val["confidence"].as_f64().unwrap_or(0.0);

    Ok(ChemImageResult {
        esmiles,
        confidence,
    })
}

/// 用 MolScribe 批量识别多张图片
///
/// 返回 (filename → ChemImageResult) 的映射，识别失败的图片不在结果中
pub async fn batch_image_to_esmiles(
    image_paths: &[(String, String)], // (filename, full_path)
    config: &VlmConfig,
) -> Vec<(String, ChemImageResult)> {
    let mut results = Vec::new();
    for (filename, full_path) in image_paths {
        match image_to_esmiles(full_path, config).await {
            Ok(result) => results.push((filename.clone(), result)),
            Err(e) => {
                log::warn!("[vlm_chem] failed for {}: {}", filename, e);
            }
        }
    }
    results
}

/// 通用 VLM 图片描述 — 调 Python sidecar `/api/v1/vlm/describe`
///
/// 将图片发送给侧边车的 VLM 模型（如 Qwen-VL），返回文本描述。
///
/// # Arguments
/// * `image_path` - 图片本地路径
/// * `prompt` - 描述提示词（可选，默认："请详细描述这张图片的内容"）
/// * `sidecar_url` - 侧边车 URL（如 http://127.0.0.1:18792）
///
/// # Returns
/// 图片的文本描述
///
/// Port of the VLM describe API call from
/// `src/mbforge/model_server/routers/vlm.py`.
pub async fn describe_image(
    image_path: &str,
    prompt: &str,
    sidecar_url: &str,
) -> Result<String, String> {
    let image_b64 = read_image_base64(image_path)?;

    let ext = Path::new(image_path)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("png")
        .to_string();

    let body = serde_json::json!({
        "image_base64": image_b64,
        "prompt": if prompt.is_empty() { "请详细描述这张图片的内容" } else { prompt },
        "ext": ext,
    });

    let client = crate::core::http::client_300s();

    let url = format!("{}/api/v1/vlm/describe", sidecar_url.trim_end_matches('/'));

    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("VLM describe request failed: {}", e))?;

    let status = resp.status();
    let text = resp
        .text()
        .await
        .map_err(|e| format!("VLM describe read error: {}", e))?;

    if !status.is_success() {
        return Err(format!(
            "VLM describe HTTP {}: {}",
            status,
            &text[..text.floor_char_boundary(200)]
        ));
    }

    let val: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| format!("VLM JSON parse error: {}", e))?;

    Ok(val["description"].as_str().unwrap_or("").to_string())
}

/// VLM 图片描述缓存 — 基于 SHA-256 避免重复调用
///
/// 缓存文件存储在项目 .mbforge/image-caption-cache.json 中：
/// { "sha256": { "caption": "...", "timestamp": 1234567890 } }
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
    /// 打开或创建指定项目根目录下的缓存
    pub fn new(project_root: &Path) -> Self {
        let path = project_root
            .join(crate::core::constants::PROJECT_META_DIR)
            .join("image-caption-cache.json");
        let entries = if path.exists() {
            std::fs::read_to_string(&path)
                .ok()
                .and_then(|s| serde_json::from_str::<HashMap<String, CacheEntry>>(&s).ok())
                .unwrap_or_default()
        } else {
            HashMap::new()
        };
        Self {
            path,
            entries,
            dirty: false,
        }
    }

    /// 根据图片 SHA-256 查找缓存
    pub fn get(&self, sha256: &str) -> Option<String> {
        self.entries.get(sha256).map(|e| e.caption.clone())
    }

    /// 写入缓存并标记脏
    pub fn set(&mut self, sha256: &str, caption: &str) {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        self.entries.insert(
            sha256.to_string(),
            CacheEntry {
                caption: caption.to_string(),
                timestamp: now,
            },
        );
        self.dirty = true;
    }

    /// 持久化到磁盘（建议在批量操作后调用一次）
    pub fn save(&mut self) -> Result<(), String> {
        if !self.dirty {
            return Ok(());
        }
        if let Some(parent) = self.path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("Failed to create cache dir: {}", e))?;
        }
        let json = serde_json::to_string_pretty(&self.entries)
            .map_err(|e| format!("Failed to serialize cache: {}", e))?;
        std::fs::write(&self.path, json)
            .map_err(|e| format!("Failed to write cache: {}", e))?;
        self.dirty = false;
        Ok(())
    }

    /// 计算文件 SHA-256
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
///
/// 先查缓存，未命中再调用 VLM API，成功后写入缓存。
pub async fn describe_image_cached(
    image_path: &str,
    prompt: &str,
    sidecar_url: &str,
    cache: &mut ImageCaptionCache,
) -> Result<String, String> {
    let path = Path::new(image_path);
    let hash = ImageCaptionCache::sha256_file(path)?;

    if let Some(cached) = cache.get(&hash) {
        log::debug!("[vlm_chem] Caption cache HIT for {}", image_path);
        return Ok(cached);
    }

    log::debug!("[vlm_chem] Caption cache MISS for {}", image_path);
    let caption = describe_image(image_path, prompt, sidecar_url).await?;
    cache.set(&hash, &caption);
    Ok(caption)
}

/// 判断一个图片是否可能是化学结构图（基于 MinerU 提供的元数据或文件名启发式）
pub fn is_likely_chemical_structure(filename: &str, region: Option<&str>) -> bool {
    if let Some(r) = region {
        if r == "figure" || r == "structure" || r == "table" {
            return true;
        }
        return false;
    }

    // 无区域标注时，用文件名校验
    let lowercase = filename.to_lowercase();
    if lowercase.contains("struct")
        || lowercase.contains("mol")
        || lowercase.contains("chem")
        || lowercase.contains("table")
        || lowercase.contains("fig")
    {
        return true;
    }

    false
}

fn read_image_base64(path: &str) -> Result<String, String> {
    let bytes = std::fs::read(path).map_err(|e| format!("Failed to read image {}: {}", path, e))?;
    Ok(base64::engine::general_purpose::STANDARD.encode(&bytes))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_likely_chemical_structure() {
        assert!(is_likely_chemical_structure(
            "page_05_img_02.png",
            Some("structure")
        ));
        assert!(is_likely_chemical_structure("fig_table_1.png", None));
        assert!(is_likely_chemical_structure("mol_compound.png", None));
        assert!(!is_likely_chemical_structure("page_01_bg.png", None));
        assert!(!is_likely_chemical_structure(
            "header_logo.png",
            Some("decorative")
        ));
    }

    #[test]
    fn test_vlm_config_default() {
        let config = VlmConfig::default();
        assert!(!config.sidecar_url.is_empty());
    }
}
