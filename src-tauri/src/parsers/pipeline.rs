use serde::{Deserialize, Serialize};
use tauri::Emitter;

use crate::commands::classifier::{classify_document, DocumentClassification};
use crate::commands::extractor::{extract_activities, extract_esmiles_candidates, ActivityData};

use super::types::{
    DocProcessingContext, DocStructure, DocumentMetadata, DocumentReport, ImageRef,
    PdfParseResult, PostProcessResult, ProcessingLog, StageLog, StructuredData,
    UncertainItem,
};

impl From<DocProcessingContext> for PdfParseResult {
    fn from(ctx: DocProcessingContext) -> Self {
        let classification = classify_document(
            ctx.raw_text.split("\n\n").map(|s| s.to_string()).collect(),
            None,
        );
        let chunks = crate::commands::text_ops::text_chunk(ctx.raw_text.clone(), 512, 128).chunks;
        let esmiles = extract_esmiles_candidates(ctx.raw_text.clone());
        let activities = extract_activities(ctx.raw_text.clone());

        PdfParseResult {
            content: ctx.raw_text,
            classification,
            chunks,
            esmiles,
            activities,
            parser: ctx.parser_used,
            page_count: ctx.page_count,
            images: ctx.images,
            headings: ctx.headings,
            sections: ctx.sections,
            page_texts: ctx.page_texts,
        }
    }
}

/// Parse a PDF using the full pipeline.
///
/// This chains: extraction → classification → chunking → molecule extraction.
#[tauri::command]
pub async fn parse_pdf(
    path: String,
    chunk_size: Option<usize>,
    _overlap: Option<usize>,
    parser: Option<String>,
) -> Result<PdfParseResult, String> {
    let chunk_size = chunk_size.unwrap_or(512);
    let parser_choice = parser.unwrap_or_else(|| "pdf_inspector".to_string());

    // Stage 1: Text extraction
    let (content, page_count): (String, usize) = match parser_choice.as_str() {
        "uniparser" => {
            let host = std::env::var("UNIPARSER_HOST")
                .unwrap_or_else(|_| "https://uniparser.dp.tech/".to_string());
            let api_key = std::env::var("UNIPARSER_API_KEY").unwrap_or_default();
            if api_key.is_empty() {
                return Err("UNIPARSER_API_KEY not set".into());
            }
            let client = super::uniparser::UniParserClient::new(&host, &api_key);
            let result = client.parse_pdf(&path)?;
            (result.content, result.page_count)
        }
        "mineru" => {
            let host =
                std::env::var("MINERU_HOST").unwrap_or_else(|_| "https://mineru.net".to_string());
            let api_key = std::env::var("MINERU_API_KEY").unwrap_or_default();
            let client = super::mineru::MineruClient::new(&host, &api_key);
            let result = client.parse_file(&path)?;
            (result.markdown, 0)
        }
        "llama_parse" => {
            let pdf_bytes =
                std::fs::read(&path).map_err(|e| format!("Failed to read PDF: {}", e))?;
            let result = super::llama_parse::parse_with_llamaparse_sync(
                "http://127.0.0.1:18792",
                pdf_bytes,
                None,
            )?;
            (result.markdown, result.page_count)
        }
        "liteparse" => {
            let result = super::liteparse::parse_with_liteparse(&path, false, None).await?;
            let page_count = result.pages.len();
            (result.text, page_count)
        }
        _ => {
            let result = pdf_inspector::process_pdf(&path)
                .map_err(|e| format!("pdf-inspector failed: {}", e))?;
            let md = result.markdown.unwrap_or_default();
            (md, result.page_count as usize)
        }
    };

    // Stage 1.5: Extract embedded images from PDF (lopdf)
    let tmp_dir = tempfile::tempdir().map_err(|e| format!("Temp dir error: {}", e))?;
    let extracted = super::images::extract_images_from_pdf(
        &path,
        tmp_dir.path(),
        20,  // max_images
        2,   // max_size_mb
    ).unwrap_or_default();
    let images: Vec<ImageRef> = extracted.into_iter().map(|img| ImageRef {
        filename: img.filename,
        page: img.page,
        region: None,
        description: None,
        esmiles: None,
    }).collect();

    // Stage 2: Classification
    let pages: Vec<String> = content.split("\n\n").map(|s| s.to_string()).collect();
    let classification = classify_document(pages, None);

    // Stage 3: Section-based chunking (PageIndex)
    let headings = super::headings::extract_headings(&content);
    let sections = super::sections::build_sections(&content, &headings, None, chunk_size);
    let chunks: Vec<String> = sections.iter().map(|s| s.text.clone()).collect();

    // Stage 4: Molecule extraction (text regex)
    let esmiles = extract_esmiles_candidates(content.clone());
    let activities = extract_activities(content.clone());

    Ok(PdfParseResult {
        content,
        classification,
        chunks,
        esmiles,
        activities,
        parser: parser_choice,
        page_count,
        images,
        headings,
        sections,
        page_texts: vec![],  // page_texts populated by post_process_pdf if available
    })
}

/// Post-process PDF extraction results using LLM.
#[tauri::command]
pub fn post_process_pdf(
    parse_result: PdfParseResult,
) -> Result<PostProcessResult, String> {
    super::post_process::post_process(&parse_result)
}

/// ===== 以下为 A3: 完整文档处理管线 =====

/// 处理进度事件（通过 Tauri event 发射给前端）
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "stage", content = "payload")]
pub enum DocProgressEvent {
    #[serde(rename = "classify")]
    Classify { parser: String, page_count: usize },
    #[serde(rename = "meta")]
    Meta { doc_type: String, sections: Vec<String> },
    #[serde(rename = "plan")]
    Plan { target_sections: Vec<String>, extraction_types: Vec<String> },
    #[serde(rename = "section")]
    Section { name: String, status: String, compounds: usize, activities: usize },
    #[serde(rename = "vlm")]
    Vlm { image_count: usize, esmiles_found: usize },
    #[serde(rename = "merge")]
    Merge { total_compounds: usize, total_activities: usize },
    #[serde(rename = "report")]
    Report { report_len: usize },
    #[serde(rename = "error")]
    Error { stage: String, message: String },
}

/// 完整的文档处理入口
///
/// 异步执行 Stages 0-4，通过 Tauri event 发射进度。
#[tauri::command]
pub async fn process_document(
    path: String,
    user_request: Option<String>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    let user_req = user_request.unwrap_or_default();
    let mut ctx = DocProcessingContext::new(&path, &user_req);
    let mut processing_log = ProcessingLog {
        stages: vec![],
        uncertain_items: vec![],
        warnings: vec![],
    };

    // ===== Stage 0: 文件分类 + 提取 =====
    {
        let _ = app.emit("doc-progress", DocProgressEvent::Classify {
            parser: "auto".into(),
            page_count: 0,
        });

        let classified = classify_and_extract(&path).await?;
        ctx.raw_text = classified.text;
        ctx.page_count = classified.page_count;
        ctx.parser_used = classified.parser;
        ctx.images = classified.images;

        // Stage 0.5: Build sections
        ctx.headings = crate::parsers::headings::extract_headings(&ctx.raw_text);
        ctx.sections = crate::parsers::sections::build_sections(
            &ctx.raw_text,
            &ctx.headings,
            None,
            8000,
        );

        processing_log.stages.push(StageLog {
            stage: 0,
            name: "文件分类与提取".into(),
            status: "ok".into(),
            items_processed: ctx.page_count,
            tokens_used: 0,
            errors: vec![],
        });

        let _ = app.emit("doc-progress", DocProgressEvent::Classify {
            parser: ctx.parser_used.clone(),
            page_count: ctx.page_count,
        });
    }

    // ===== Stage 1: 快速结构分析（Meta Prompt）=====
    let doc_structure: DocStructure;
    {
        let _ = app.emit("doc-progress", DocProgressEvent::Meta {
            doc_type: "analyzing".into(),
            sections: vec![],
        });

        doc_structure = match run_meta_analysis(&ctx).await {
            Ok(s) => s,
            Err(e) => {
                processing_log.warnings.push(format!("Meta analysis failed: {}", e));
                // Fallback: 用空结构继续
                DocStructure {
                    doc_type: "unknown".into(),
                    page_count: ctx.page_count,
                    has_compound_tables: false,
                    has_chemical_structures: false,
                    has_activity_data: false,
                    estimated_sections: vec!["full_content".into()],
                    key_terms: vec![],
                    recommended_approach: "full".into(),
                }
            }
        };
        ctx.doc_type = Some(doc_structure.doc_type.clone());

        processing_log.stages.push(StageLog {
            stage: 1,
            name: "文档结构分析".into(),
            status: "ok".into(),
            items_processed: doc_structure.estimated_sections.len(),
            tokens_used: 0,
            errors: vec![],
        });

        let _ = app.emit("doc-progress", DocProgressEvent::Meta {
            doc_type: doc_structure.doc_type.clone(),
            sections: doc_structure.estimated_sections.clone(),
        });
    }

    // ===== Stage 1.5: 用户意图路由 =====
    let plan = crate::parsers::intent::interpret_request(&doc_structure, &user_req);

    let _ = app.emit("doc-progress", DocProgressEvent::Plan {
        target_sections: plan.target_sections.clone(),
        extraction_types: plan.extraction_types.clone(),
    });

    // ===== Stage 2: 逐 section 处理 =====
    let mut section_results: Vec<StructuredData> = Vec::new();
    // TODO-AUDIT: total_compounds and total_activities are incremented per section
    // but never used afterward — they accumulate but are discarded before return.
    let mut total_compounds = 0usize;
    let mut total_activities = 0usize;

    for section_name in &plan.target_sections {
        // 跳过不在 estimated_sections 中的 section（除非是 "table_*" 或特殊 section）
        if !doc_structure.estimated_sections.contains(section_name)
            && !section_name.contains('*')
            && section_name != &"table_1"
            && section_name != &"biological_data"
            && section_name != &"examples"
        {
            continue;
        }

        let section_text = extract_section_text(&ctx.raw_text, section_name);

        let result = match super::post_process::post_process_section(
            &section_text,
            &ctx.parser_used,
            ctx.page_count,
        )
        .await
        {
            Ok(r) => {
                let compounds = r.data.compounds.len();
                let activities = r.data.activities.len();
                total_compounds += compounds;
                total_activities += activities;

                let _ = app.emit("doc-progress", DocProgressEvent::Section {
                    name: section_name.clone(),
                    status: "ok".into(),
                    compounds,
                    activities,
                });

                Some(r.data)
            }
            Err(e) => {
                processing_log.warnings.push(format!(
                    "Section '{}' processing failed: {}. Skipping.",
                    section_name, e
                ));
                processing_log.uncertain_items.push(
                    UncertainItem {
                        item_type: "section_processing_error".into(),
                        content: format!("{} section could not be processed", section_name),
                        reason: e,
                        suggested_action: "Review this section manually".into(),
                    },
                );

                let _ = app.emit("doc-progress", DocProgressEvent::Error {
                    stage: format!("section:{}", section_name),
                    message: format!("Section processing failed, skipped"),
                });

                None
            }
        };

        if let Some(data) = result {
            section_results.push(data);
        }
    }

    processing_log.stages.push(StageLog {
        stage: 2,
        name: "逐段提取".into(),
        status: "ok".into(),
        items_processed: section_results.len(),
        tokens_used: 0,
        errors: vec![],
    });

    // ===== Stage 2b: VLM 化学结构识别 =====
    let vlm_config = crate::parsers::vlm_chem::VlmConfig::default();
    let mut vlm_esmiles_found = 0usize;
    let mut vlm_results: Vec<(String, crate::parsers::vlm_chem::ChemImageResult)> = Vec::new();

    if !ctx.images.is_empty() {
        let chem_images: Vec<(String, String)> = ctx
            .images
            .iter()
            .filter(|img| {
                crate::parsers::vlm_chem::is_likely_chemical_structure(
                    &img.filename,
                    img.region.as_deref(),
                )
            })
            .map(|img| {
                (
                    img.filename.clone(),
                    ctx.source_path
                        .parent()
                        .map(|p| p.join(&img.filename).to_string_lossy().to_string())
                        .unwrap_or_default(),
                )
            })
            .collect();

        if !chem_images.is_empty() {
            vlm_results =
                crate::parsers::vlm_chem::batch_image_to_esmiles(&chem_images, &vlm_config).await;
            vlm_esmiles_found = vlm_results.len();
        }

        let _ = app.emit("doc-progress", DocProgressEvent::Vlm {
            image_count: chem_images.len(),
            esmiles_found: vlm_esmiles_found,
        });
    }

    // ===== Stage 3: 合并 + 验证 + SAR =====
    let final_data: StructuredData;
    let sar_analysis: String;
    {
        if section_results.is_empty() && vlm_results.is_empty() {
            // 无任何结果 → 返回空报告
            final_data = StructuredData {
                metadata: DocumentMetadata {
                    title: ctx.source_path.to_string_lossy().to_string().into(),
                    authors: vec![],
                    document_type: doc_structure.doc_type.clone(),
                    key_targets: vec![],
                    source_file: Some(ctx.source_path.to_string_lossy().to_string()),
                },
                summary: "No data could be extracted from this document.".into(),
                compounds: vec![],
                activities: vec![],
                key_findings: vec![],
                uncertain_items: processing_log.uncertain_items.clone(),
            };
            sar_analysis = String::new();
        } else {
            match run_merge_and_sar(&section_results, &vlm_results, &doc_structure).await {
                Ok((data, sar)) => {
                    final_data = data;
                    sar_analysis = sar;
                }
                Err(e) => {
                    processing_log
                        .warnings
                        .push(format!("Merge analysis failed: {}. Using partial results.", e));
                    // Fallback: 合并已有结果
                    let combined = merge_partial_results(&section_results, &vlm_results);
                    final_data = combined;
                    sar_analysis = String::new();
                }
            }
        }

        let _ = app.emit("doc-progress", DocProgressEvent::Merge {
            total_compounds: final_data.compounds.len(),
            total_activities: final_data.activities.len(),
        });
    }

    processing_log.stages.push(StageLog {
        stage: 3,
        name: "合并与验证".into(),
        status: "ok".into(),
        items_processed: final_data.compounds.len() + final_data.activities.len(),
        tokens_used: 0,
        errors: vec![],
    });

    // ===== Stage 4: 报告生成 =====
    let report_md =
        crate::parsers::report::generate_full_report(&final_data, Some(&sar_analysis));

    let report = DocumentReport {
        metadata: final_data.metadata.clone(),
        compounds: final_data.compounds.clone(),
        activities: final_data.activities.clone(),
        key_findings: final_data.key_findings.clone(),
        sar_analysis,
        uncertain_items: final_data.uncertain_items.clone(),
        report_markdown: report_md.clone(),
    };

    let _ = app.emit("doc-progress", DocProgressEvent::Report {
        report_len: report_md.len(),
    });

    // 最终结果发射
    let _ = app.emit("doc-result", &report);

    Ok(())
}

// ---------------------------------------------------------------------------
// 项目级批量索引（Rust Native，替代 Python /project/index）
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, serde::Serialize)]
pub struct IndexResult {
    pub indexed: usize,
    pub sections: usize,
    pub errors: Vec<String>,
}

/// 扫描项目目录下的所有 PDF，提取 → 分 section → 索引到本地知识库。
#[tauri::command]
pub async fn index_project_rust(
    app: tauri::AppHandle,
    root: String,
) -> Result<IndexResult, String> {
    let project_root = std::path::PathBuf::from(&root);
    let config = crate::core::config::EmbedConfig::default();
    let kb = crate::core::knowledge_base::KnowledgeBase::new(&project_root, &config)
        .map_err(|e| format!("KB init failed: {}", e))?;

    // 扫描 PDF 文件
    let mut pdf_files: Vec<std::path::PathBuf> = Vec::new();
    for entry in walkdir::WalkDir::new(&project_root)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_file())
    {
        if let Some(ext) = entry.path().extension() {
            if ext.eq_ignore_ascii_case("pdf") {
                pdf_files.push(entry.path().to_path_buf());
            }
        }
    }

    let mut indexed = 0usize;
    let mut total_sections = 0usize;
    let mut errors = Vec::new();
    let total = pdf_files.len();

    for (i, pdf_path) in pdf_files.iter().enumerate() {
        let doc_id = uuid::Uuid::new_v4().to_string();
        let filename = pdf_path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_else(|| "unknown.pdf".to_string());

        // 发射进度事件
        let _ = app.emit(
            "doc-progress",
            DocProgressEvent::Classify {
                parser: format!("indexing {}/{}", i + 1, total),
                page_count: 0,
            },
        );

        let path_str = pdf_path.to_string_lossy().to_string();
        match classify_and_extract(&path_str).await {
            Ok(classified) => {
                let headings = crate::parsers::headings::extract_headings(&classified.text);
                let sections = crate::parsers::sections::build_sections(
                    &classified.text,
                    &headings,
                    None,
                    8000,
                );

                total_sections += sections.len();

                match kb.index_document(&doc_id, &sections, &[]).await {
                    Ok(_) => {
                        indexed += 1;
                    }
                    Err(e) => {
                        errors.push(format!("{}: {}", filename, e));
                    }
                }
            }
            Err(e) => {
                errors.push(format!("{}: {}", filename, e));
            }
        }
    }

    Ok(IndexResult {
        indexed,
        sections: total_sections,
        errors,
    })
}

// ===== 内部辅助函数 =====

/// 分类并提取文件（自动检测 parser）
struct ClassifyResult {
    text: String,
    page_count: usize,
    parser: String,
    images: Vec<ImageRef>,
}

async fn classify_and_extract(path: &str) -> Result<ClassifyResult, String> {
    // 先尝试 pdf-inspector
    let pdf_result = pdf_inspector::process_pdf(path)
        .map_err(|e| format!("pdf-inspector failed: {}", e))?;
    let md = pdf_result.markdown.unwrap_or_default();
    let page_count = pdf_result.page_count as usize;

    // 提取嵌入图片
    let tmp_dir = tempfile::tempdir().map_err(|e| format!("Temp dir error: {}", e))?;
    let extracted = super::images::extract_images_from_pdf(
        path,
        tmp_dir.path(),
        20,
        2,
    ).unwrap_or_default();

    // 转换为 ImageRef
    let images: Vec<ImageRef> = extracted.iter().map(|img| ImageRef {
        filename: img.filename.clone(),
        page: img.page,
        region: None,
        description: None,
        esmiles: None,
    }).collect();

    // 如果 pdf-inspector 提取不到内容，且内容是扫描件 → 自动升到 MinerU 或 LiteParse
    if md.len() < 100 && page_count > 0 {
        // 优先尝试 MinerU（云端 OCR）
        if std::env::var("MINERU_API_KEY").is_ok() {
            let host = std::env::var("MINERU_HOST").unwrap_or_else(|_| "https://mineru.net".to_string());
            let api_key = std::env::var("MINERU_API_KEY").unwrap_or_default();
            let client = super::mineru::MineruClient::new(&host, &api_key);
            let result = client.parse_file(path)?;
            return Ok(ClassifyResult {
                text: result.markdown,
                page_count: 0,
                parser: "mineru".into(),
                images: vec![],
            });
        }
        // 回退到 LiteParse（本地 OCR）
        if let Ok(result) = super::liteparse::parse_with_liteparse(path, true, None).await {
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

/// Stage 1: 调用 LLM 做文档结构分析
async fn run_meta_analysis(ctx: &DocProcessingContext) -> Result<DocStructure, String> {
    let prompt = crate::parsers::intent::build_meta_prompt(ctx);

    let config = crate::parsers::post_process::load_llm_config()?;
    let (response, _tokens) = crate::parsers::post_process::call_llm_api(
        &config,
        "你是文档分析专家。分析文档开头部分，判断文档类型和结构。只输出 JSON。",
        &prompt,
    )?;

    crate::parsers::intent::parse_meta_response(&response)
}

/// Stage 3: 调用 LLM 合并多 section 结果 + SAR 分析
async fn run_merge_and_sar(
    section_results: &[StructuredData],
    vlm_results: &[(String, crate::parsers::vlm_chem::ChemImageResult)],
    structure: &DocStructure,
) -> Result<(StructuredData, String), String> {
    let sections_text: Vec<String> = section_results
        .iter()
        .map(|s| {
            format!(
                "摘要: {}\n化合物: {} 个\n活性数据: {} 条",
                &s.summary[..s.summary.len().min(200)],
                s.compounds.len(),
                s.activities.len(),
            )
        })
        .collect();

    let vlm_text: Vec<String> = vlm_results
        .iter()
        .map(|(fname, result)| format!("{}: {} (conf: {:.2})", fname, result.esmiles, result.confidence))
        .collect();

    let prompt = format!(
        r#"请验证并合并以下多部分提取结果，生成最终报告。

原始文档类型: {doc_type}

各部分的提取结果：
{sections}

VLM 识别的 SMILES：
{vlm}

验证要求：
1. 去重：相同化合物只保留一条
2. 交叉验证：文字提取与 VLM 图像识别结果不一致时标记 uncertain
3. 构效关系分析：总结关键 SAR 发现（500字以内）
4. 标注不确定项

输出 JSON（只输出 JSON，不要其他文字）：
{{
  "metadata": {{"title": "...", "document_type": "...", "key_targets": ["..."], "authors": ["..."]}},
  "summary": "200字中文摘要",
  "compounds": [{{"name": "...", "smiles": "...或null", "category": "...", "description": "...", "source_ref": "...", "confidence": "high/medium/low", "uncertainty_reason": "..."}}],
  "activities": [{{"compound": "...", "activity_type": "...", "value": 0.0, "units": "nM", "target": "...", "source_quote": "...", "source_ref": "...", "confidence": "high/medium/low", "uncertainty_reason": "..."}}],
  "key_findings": [{{"finding": "...", "evidence": "...", "source_ref": "...", "confidence": "high/medium/low", "uncertainty_reason": "..."}}],
  "sar_analysis": "构效关系总结（500字以内）",
  "uncertain_items": [{{"item_type": "...", "content": "...", "reason": "...", "suggested_action": "..."}}]
}}"#,
        doc_type = structure.doc_type,
        sections = sections_text.join("\n---\n"),
        vlm = if vlm_text.is_empty() {
            "无".to_string()
        } else {
            vlm_text.join("\n")
        },
    );

    let config = crate::parsers::post_process::load_llm_config()?;
    let (response, _tokens) = crate::parsers::post_process::call_llm_api(
        &config,
        "你是分子科学文档分析专家。从 PDF 提取结果中整理出结构化数据，输出 JSON。",
        &prompt,
    )?;

    let val = crate::parsers::post_process::extract_json(&response)?;

    let data_val = val.get("data").unwrap_or(&val);
    let data = crate::parsers::post_process::parse_structured_data(data_val)?;
    let sar = val["sar_analysis"].as_str().unwrap_or("").to_string();

    Ok((data, sar))
}

/// 提取指定 section 的文本（基于 section name 尝试搜索）
fn extract_section_text(raw_text: &str, section_name: &str) -> String {
    // 简单启发式：在文本中搜索 section 标题附近的段落
    let markers = [
        &format!("{}", section_name),
        &format!("# {}", section_name),
        &format!("## {}", section_name),
        &format!("【{}】", section_name),
    ];

    for marker in &markers {
        if let Some(pos) = raw_text.find(marker.as_str()) {
            let start = pos.saturating_sub(50);
            let end = (pos + 10000).min(raw_text.len());
            return raw_text[start..end].to_string();
        }
    }

    // Fallback: 取全文（限制前 10000 字符）
    raw_text.chars().take(10000).collect()
}

/// 手动合并部分结果（当 LLM merge 失败时用）
fn merge_partial_results(
    section_results: &[StructuredData],
    _vlm_results: &[(String, crate::parsers::vlm_chem::ChemImageResult)],
) -> StructuredData {
    let mut all_compounds = Vec::new();
    let mut all_activities = Vec::new();
    let mut all_findings = Vec::new();
    let mut all_uncertain = Vec::new();
    let mut summary_parts = Vec::new();
    let mut metadata = None;

    for r in section_results {
        all_compounds.extend(r.compounds.clone());
        all_activities.extend(r.activities.clone());
        all_findings.extend(r.key_findings.clone());
        all_uncertain.extend(r.uncertain_items.clone());
        summary_parts.push(r.summary.clone());
        if metadata.is_none() {
            metadata = Some(r.metadata.clone());
        }
    }

    // 简单位置去重：按 name 去重
    let mut seen = std::collections::HashSet::new();
    all_compounds.retain(|c| {
        if seen.contains(&c.name) {
            false
        } else {
            seen.insert(c.name.clone());
            true
        }
    });

    StructuredData {
        metadata: metadata.unwrap_or(DocumentMetadata {
            title: None,
            authors: vec![],
            document_type: "unknown".into(),
            key_targets: vec![],
            source_file: None,
        }),
        summary: summary_parts.join("\n"),
        compounds: all_compounds,
        activities: all_activities,
        key_findings: all_findings,
        uncertain_items: all_uncertain,
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_section_text_found() {
        let text = "## background\nThis is the background section.\n## results\nThese are the results.\n## claims";
        let extracted = extract_section_text(text, "results");
        assert!(extracted.contains("These are the results"));
    }

    #[test]
    fn test_extract_section_text_not_found() {
        let text = "Short text without sections.";
        let extracted = extract_section_text(text, "nonexistent");
        assert!(!extracted.is_empty());
    }

    #[test]
    fn test_merge_partial_results_empty() {
        let result = merge_partial_results(&[], &[]);
        assert_eq!(result.compounds.len(), 0);
        assert_eq!(result.activities.len(), 0);
    }

    #[test]
    fn test_merge_partial_results_dedup() {
        use super::super::types::{CompoundEntry, DocumentMetadata};
        let r1 = StructuredData {
            metadata: DocumentMetadata { title: None, authors: vec![], document_type: "patent".into(), key_targets: vec![], source_file: None },
            summary: "".into(),
            compounds: vec![CompoundEntry {
                name: "E041".into(), esmiles: Some("C1CC1".into()), category: None,
                description: "test".into(), source_ref: "p5".into(),
                confidence: "high".into(), uncertainty_reason: None,
            }],
            activities: vec![],
            key_findings: vec![],
            uncertain_items: vec![],
        };
        let r2 = StructuredData {
            metadata: DocumentMetadata { title: None, authors: vec![], document_type: "patent".into(), key_targets: vec![], source_file: None },
            summary: "".into(),
            compounds: vec![CompoundEntry {
                name: "E041".into(), esmiles: Some("C1CC1".into()), category: None,
                description: "test duplicate".into(), source_ref: "p12".into(),
                confidence: "high".into(), uncertainty_reason: None,
            }],
            activities: vec![],
            key_findings: vec![],
            uncertain_items: vec![],
        };
        let result = merge_partial_results(&[r1, r2], &[]);
        assert_eq!(result.compounds.len(), 1);
    }

    #[test]
    fn test_pdf_parse_from_processing_context() {
        let ctx = DocProcessingContext::new("/tmp/test.pdf", "");
        let result = PdfParseResult::from(ctx);
        assert_eq!(result.parser, "");
        assert_eq!(result.page_count, 0);
    }

    #[test]
    fn test_pdf_parse_result_serde_roundtrip() {
        use crate::commands::classifier::DocumentClassification;

        let result = PdfParseResult {
            content: "test content".into(),
            classification: DocumentClassification {
                text_density: 0.5,
                is_scanned: false,
                has_molecular_patterns: true,
                metadata_hints: None,
                pages: vec![],
                needs_confirmation: false,
            },
            chunks: vec!["chunk1".into(), "chunk2".into()],
            esmiles: vec!["CCO".into()],
            activities: vec![],
            parser: "test".into(),
            page_count: 1,
            images: vec![],
            headings: vec![crate::parsers::headings::Heading {
                level: 1,
                title: "Introduction".into(),
                line_num: 0,
            }],
            sections: vec![crate::parsers::sections::SectionChunk {
                title: "Introduction".into(),
                path: "Introduction".into(),
                text: "intro text".into(),
                page_start: Some(1),
                page_end: Some(3),
                line_start: 0,
                line_end: 10,
            }],
            page_texts: vec!["page 1".into()],
        };

        let json = serde_json::to_string(&result).unwrap();
        let roundtrip: PdfParseResult = serde_json::from_str(&json).unwrap();

        assert_eq!(roundtrip.content, "test content");
        assert_eq!(roundtrip.parser, "test");
        assert_eq!(roundtrip.headings.len(), 1);
        assert_eq!(roundtrip.headings[0].title, "Introduction");
        assert_eq!(roundtrip.sections.len(), 1);
        assert_eq!(roundtrip.page_texts.len(), 1);
        assert_eq!(roundtrip.esmiles, vec!["CCO"]);
    }
}

// ===== KB 索引（通过 Python sidecar）=====

/// 通过 HTTP 调用 Python sidecar 索引 sections 到知识库
pub async fn index_sections_to_kb(
    project_root: &str,
    doc_id: &str,
    sections: &[crate::parsers::sections::SectionChunk],
    filename: &str,
) -> Result<(), String> {
    let sidecar_url = crate::core::constants::sidecar_url();

    let body = serde_json::json!({
        "project_root": project_root,
        "doc_id": doc_id,
        "filename": filename,
        "sections": sections.iter().map(|s| serde_json::json!({
            "title": s.title,
            "path": s.path,
            "text": s.text,
            "page_start": s.page_start,
            "page_end": s.page_end,
        })).collect::<Vec<_>>(),
    });

    let client = crate::core::http::client_120s();

    let url = format!("{}/api/v1/kb/index-sections", sidecar_url.trim_end_matches('/'));

    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("KB index request failed: {}", e))?;

    if !resp.status().is_success() {
        let text = resp.text().await.unwrap_or_default();
        return Err(format!("KB index HTTP error: {}", text));
    }

    Ok(())
}
