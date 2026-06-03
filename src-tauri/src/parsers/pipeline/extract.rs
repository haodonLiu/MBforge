use crate::parsers::doc_types::ImageRef;
use std::path::{Path, PathBuf};

/// 分类并提取文件（自动检测 parser）
pub struct ClassifyResult {
    pub text: String,
    pub page_count: usize,
    pub parser: String,
    pub images: Vec<ImageRef>,
}

/// 将提取的图片持久化到项目 .mbforge/media/ 下
fn persist_extracted_images(
    path: &str,
    extracted: &[crate::parsers::images::ExtractedImage],
) -> Vec<ImageRef> {
    let source_path = Path::new(path);
    let project_root = find_project_root(source_path, None);
    let doc_slug = source_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_string();

    let media_dir = project_root.as_ref().map(|root| {
        root.join(crate::core::constants::PROJECT_META_DIR)
            .join("media")
            .join(&doc_slug)
    });

    extracted
        .iter()
        .map(|img| {
            let rel_path = if let Some(ref dir) = media_dir {
                if std::fs::create_dir_all(dir).is_ok() {
                    let dest = dir.join(&img.filename);
                    if let Err(e) = std::fs::copy(&img.path, &dest) {
                        log::warn!(
                            "Failed to copy image {} to {}: {}",
                            img.path.display(),
                            dest.display(),
                            e
                        );
                    } else {
                        // 计算相对项目根目录的路径
                        if let Some(ref root) = project_root {
                            if let Ok(rp) = dest.strip_prefix(root) {
                                return ImageRef {
                                    filename: img.filename.clone(),
                                    page: img.page,
                                    region: None,
                                    description: None,
                                    esmiles: None,
                                    rel_path: Some(rp.to_string_lossy().to_string()),
                                };
                            }
                        }
                    }
                }
                None
            } else {
                None
            };
            ImageRef {
                filename: img.filename.clone(),
                page: img.page,
                region: None,
                description: None,
                esmiles: None,
                rel_path,
            }
        })
        .collect()
}

pub async fn classify_and_extract(path: &str) -> Result<ClassifyResult, String> {
    // 先尝试 pdf-inspector
    let pdf_result =
        pdf_inspector::process_pdf(path).map_err(|e| format!("pdf-inspector failed: {}", e))?;
    let md = pdf_result.markdown.unwrap_or_default();
    let page_count = pdf_result.page_count as usize;

    // 提取嵌入图片并持久化到项目目录
    let tmp_dir = tempfile::tempdir().map_err(|e| format!("Temp dir error: {}", e))?;
    let extracted = crate::parsers::images::extract_images_from_pdf(path, tmp_dir.path(), 20, 2)
        .unwrap_or_default();
    let images = persist_extracted_images(path, &extracted);

    // 如果 pdf-inspector 提取不到内容，且内容是扫描件 → 自动升到 MinerU 或 LiteParse
    if md.len() < 100 && page_count > 0 {
        // 优先尝试 MinerU（云端 OCR）
        if std::env::var("MINERU_API_KEY").is_ok() {
            let host =
                std::env::var("MINERU_HOST").unwrap_or_else(|_| "https://mineru.net".to_string());
            let api_key = std::env::var("MINERU_API_KEY").unwrap_or_default();
            let client = crate::parsers::mineru::MineruClient::new(&host, &api_key);
            let result = client.parse_file(path)?;
            return Ok(ClassifyResult {
                text: result.markdown,
                page_count: 0,
                parser: "mineru".into(),
                images: vec![],
            });
        }
        // 回退到 LiteParse（本地 OCR）
        if let Ok(result) = crate::parsers::liteparse::parse_with_liteparse(path, true, None).await
        {
            if !result.text.trim().is_empty() {
                return Ok(ClassifyResult {
                    text: result.text,
                    page_count: result.pages.len(),
                    parser: "liteparse".into(),
                    images: vec![],
                });
            }
        }
    }

    Ok(ClassifyResult {
        text: md,
        page_count,
        parser: "pdf_inspector".into(),
        images,
    })
}

/// 查找项目根目录（用于持久化）
pub fn find_project_root(
    start: &std::path::Path,
    explicit: Option<&str>,
) -> Option<std::path::PathBuf> {
    if let Some(root) = explicit {
        let p = std::path::PathBuf::from(root);
        if p.join(".mbforge").is_dir() {
            return Some(p);
        }
    }
    let mut current = start.parent()?;
    for _ in 0..5 {
        if current.join(".mbforge").is_dir() {
            return Some(current.to_path_buf());
        }
        current = current.parent()?;
    }
    None
}
