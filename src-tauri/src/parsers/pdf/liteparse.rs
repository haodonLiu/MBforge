#![allow(dead_code)]
//! LiteParse 解析器 — 基于 PDFium 的本地 PDF 解析
//!
//! 功能：
//! - 文本型 PDF 的高质量文本提取（含 bounding box）
//! - 扫描型 PDF 的本地 OCR（需 Tesseract）
//! - 页面截图生成（供 VLM 化学结构识别）
//!
//! 依赖：liteparse crate + PDFium 二进制（vendor/pdfium/）

use serde::{Deserialize, Serialize};

/// LiteParse 解析结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LiteParseResult {
    /// 完整文档文本
    pub text: String,
    /// 逐页数据
    pub pages: Vec<LiteParsePage>,
    /// 解析器名称
    pub parser: String,
}

/// 单页解析结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LiteParsePage {
    /// 页码（1-indexed）
    pub page_number: usize,
    /// 页面宽度（PDF points）
    pub page_width: f32,
    /// 页面高度（PDF points）
    pub page_height: f32,
    /// 页面文本
    pub text: String,
    /// 文本条目数量
    pub text_item_count: usize,
}

/// 用 LiteParse 解析 PDF 文件
///
/// # Arguments
/// * `path` - PDF 文件路径
/// * `ocr_enabled` - 是否启用 OCR（扫描页自动触发）
/// * `target_pages` - 指定页码（None = 全部）
pub async fn parse_with_liteparse(
    path: &str,
    ocr_enabled: bool,
    target_pages: Option<String>,
) -> Result<LiteParseResult, String> {
    use liteparse::{LiteParse, LiteParseConfig, OutputFormat};

    // 从用户配置读取 OCR 语言；回退到 "eng"
    let ocr_language = crate::core::config::settings::AppConfig::load()
        .pdf_parse
        .ocr_language;

    let config = LiteParseConfig {
        ocr_enabled,
        ocr_language: ocr_language.clone(),
        output_format: OutputFormat::Json,
        target_pages,
        dpi: 300.0,
        quiet: true,
        ..Default::default()
    };

    let parser = LiteParse::new(config);
    let result = parser
        .parse(path)
        .await
        .map_err(|e| format!("LiteParse error: {}", e))?;

    let pages: Vec<LiteParsePage> = result
        .pages
        .iter()
        .map(|p| LiteParsePage {
            page_number: p.page_number,
            page_width: p.page_width,
            page_height: p.page_height,
            text: p.text.clone(),
            text_item_count: p.text_items.len(),
        })
        .collect();

    Ok(LiteParseResult {
        text: result.text,
        pages,
        parser: "liteparse".to_string(),
    })
}

/// 用 LiteParse 生成页面截图
pub async fn screenshot_with_liteparse(
    path: &str,
    page_numbers: Option<Vec<u32>>,
) -> Result<Vec<LiteScreenshot>, String> {
    use liteparse::LiteParse;

    let parser = LiteParse::new(liteparse::LiteParseConfig {
        quiet: true,
        ..Default::default()
    });

    let screenshots = parser
        .screenshot(path, page_numbers)
        .await
        .map_err(|e| format!("LiteParse screenshot error: {}", e))?;

    Ok(screenshots
        .into_iter()
        .map(|s| LiteScreenshot {
            page_num: s.page_num,
            width: s.width,
            height: s.height,
            image_bytes: s.image_bytes,
        })
        .collect())
}

/// 截图结果
#[derive(Debug, Clone)]
pub struct LiteScreenshot {
    pub page_num: u32,
    pub width: u32,
    pub height: u32,
    pub image_bytes: Vec<u8>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_liteparse_result_structure() {
        let result = LiteParseResult {
            text: "test".into(),
            pages: vec![LiteParsePage {
                page_number: 1,
                page_width: 595.0,
                page_height: 842.0,
                text: "page 1".into(),
                text_item_count: 10,
            }],
            parser: "liteparse".into(),
        };
        assert_eq!(result.pages.len(), 1);
        assert_eq!(result.parser, "liteparse");
    }

    /// 诊断测试：验证 LiteParse 截图 CN 专利（TextBased，矢量图）
    #[test]
    #[ignore]
    fn test_screenshot_cn_patent() {
        let path = r"C:\Users\10954\Desktop\X2\CN120118069A.PDF";
        let rt = tokio::runtime::Runtime::new().unwrap();
        let screenshots =
            rt.block_on(async { screenshot_with_liteparse(path, Some(vec![1, 2, 3])).await });
        match screenshots {
            Ok(ss) => {
                println!("[DIAG] Screenshot {} pages from CN patent", ss.len());
                for s in &ss {
                    println!(
                        "  page={}, size={}x{}, bytes={}",
                        s.page_num,
                        s.width,
                        s.height,
                        s.image_bytes.len()
                    );
                }
                assert!(!ss.is_empty(), "Should have at least one screenshot");
            }
            Err(e) => {
                panic!("LiteParse screenshot failed: {}", e);
            }
        }
    }
}
