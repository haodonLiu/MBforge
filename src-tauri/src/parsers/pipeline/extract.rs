use crate::parsers::doc_types::ImageRef;

/// 分类并提取文件（自动检测 parser）
pub struct ClassifyResult {
    pub text: String,
    pub page_count: usize,
    pub parser: String,
    pub images: Vec<ImageRef>,
}

pub async fn classify_and_extract(path: &str) -> Result<ClassifyResult, String> {
    // 先尝试 pdf-inspector
    let pdf_result =
        pdf_inspector::process_pdf(path).map_err(|e| format!("pdf-inspector failed: {}", e))?;
    let md = pdf_result.markdown.unwrap_or_default();
    let page_count = pdf_result.page_count as usize;

    // 提取嵌入图片
    let tmp_dir = tempfile::tempdir().map_err(|e| format!("Temp dir error: {}", e))?;
    let extracted = crate::parsers::images::extract_images_from_pdf(path, tmp_dir.path(), 20, 2)
        .unwrap_or_default();

    // 转换为 ImageRef
    let images: Vec<ImageRef> = extracted
        .iter()
        .map(|img| ImageRef {
            filename: img.filename.clone(),
            page: img.page,
            region: None,
            description: None,
            esmiles: None,
        })
        .collect();

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
