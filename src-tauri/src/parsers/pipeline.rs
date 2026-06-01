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
                let _ = app.emit("doc-progress", DocProgressEvent::Section {
                    name: section_name.clone(),
                    status: "ok".into(),
                    compounds: r.data.compounds.len(),
                    activities: r.data.activities.len(),
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

    // ===== Stage 2a: 专利命名化合物提取（仅专利文档）=====
    let mut molecule_traces: Vec<crate::parsers::molecule_extractor::MoleculeTrace> = Vec::new();
    let mut claim_graph: Option<crate::parsers::claim_parser::ClaimDependencyGraph> = None;

    if doc_structure.doc_type == "patent" {
        // 合并所有 section 的文本用于分子提取
        let all_section_text = section_results
            .iter()
            .map(|s| s.summary.clone())
            .collect::<Vec<_>>()
            .join("\n");
        let full_text = if all_section_text.len() > 100 {
            all_section_text
        } else {
            ctx.raw_text.clone()
        };

        let named_mols = crate::parsers::molecule_extractor::extract_named_molecule_series(&full_text);
        if !named_mols.is_empty() {
            let mut traces = crate::parsers::molecule_extractor::link_molecules_to_images(
                &named_mols,
                &ctx.images,
                &[],
            );
            // 提取理化性质
            for trace in traces.iter_mut() {
                trace.properties = crate::parsers::molecule_extractor::extract_properties_for_molecule(
                    &trace.molecule,
                    &full_text,
                    500,
                );
            }
            molecule_traces = traces;
        }

        // 解析 claims section
        let claims_text = extract_section_text(&ctx.raw_text, "claims");
        if !claims_text.is_empty() && claims_text.len() > 20 {
            claim_graph = Some(crate::parsers::claim_parser::parse_claims_section(&claims_text));
        }

        let _ = app.emit("doc-progress", DocProgressEvent::Section {
            name: "patent_molecule_extraction".into(),
            status: "ok".into(),
            compounds: molecule_traces.len(),
            activities: molecule_traces.iter().map(|t| t.properties.len()).sum(),
        });
    }

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

        // 回填 VLM 识别结果到 molecule_traces
        for trace in molecule_traces.iter_mut() {
            for img in &trace.related_images {
                if let Some((_, chem_result)) = vlm_results.iter().find(|(fname, _)| fname == &img.filename) {
                    trace.vlm_verified_esmiles = Some(chem_result.esmiles.clone());
                    trace.vlm_confidence = chem_result.confidence;
                }
            }
        }
    }

    // ===== Stage 3: 合并 + 验证 + SAR =====
    let mut final_data: StructuredData;
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

    // 专利数据增强：将 molecule_traces 的信息整合进 final_data
    if doc_structure.doc_type == "patent" {
        enhance_patent_data(&mut final_data, &molecule_traces, &claim_graph, &mut processing_log);
    }

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
    let kb = crate::core::knowledge_base::KnowledgeBase::new(&project_root)
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

                match kb.index_document(&doc_id, &sections, &[]) {
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
    let (response, _tokens) = crate::parsers::post_process::call_llm_api_async(
        &config,
        "你是文档分析专家。分析文档开头部分，判断文档类型和结构。只输出 JSON。",
        &prompt,
    ).await?;

    crate::parsers::intent::parse_meta_response(&response)
}

/// Stage 3: 多 section 结果合并 + 构效关系 (SAR) 分析
/// 
/// 输入：各 section 的提取结果 + VLM 识别的 SMILES
/// 任务：
/// 1. 去重合并相同化合物/活性数据
/// 2. 交叉验证文字提取与 VLM 结果
/// 3. 分析构效关系 (SAR)
/// 4. 生成最终结构化报告
async fn run_merge_and_sar(
    section_results: &[StructuredData],
    vlm_results: &[(String, crate::parsers::vlm_chem::ChemImageResult)],
    structure: &DocStructure,
) -> Result<(StructuredData, String), String> {
    // 构建 section 摘要
    let sections_text: Vec<String> = section_results
        .iter()
        .enumerate()
        .map(|(i, s)| {
            let title = s.metadata.title.as_deref().unwrap_or("未命名");
            format!(
                "## Section {}: {}\n摘要: {}\n化合物: {} 个 | 活性数据: {} 条",
                i + 1,
                title,
                &s.summary[..s.summary.len().min(300)],
                s.compounds.len(),
                s.activities.len(),
            )
        })
        .collect();

    // VLM 识别的化学结构
    let vlm_text: Vec<String> = vlm_results
        .iter()
        .map(|(fname, result)| {
            format!(
                "- **{}**: `{}` (置信度: {:.0}%)",
                fname,
                result.esmiles,
                result.confidence * 100.0
            )
        })
        .collect();

    let prompt = format!(
        r#"## 任务
合并多个 section 的提取结果，进行去重、交叉验证和构效关系分析，生成最终报告。

## 文档信息
- **原始类型**: {doc_type}
- **Section 数量**: {section_count}
- **VLM 识别**: {vlm_count} 个化学结构

## 各 Section 提取结果
{sections}

## VLM 图像识别结果
{vlm}

---

## 合并与验证规范

### 1. 去重规则
| 类型 | 去重依据 |
|------|----------|
| 化合物 | name 完全相同，或 SMILES 完全相同 |
| 活性数据 | compound + activity_type + value 完全相同 |
| 发现 | finding 内容高度相似 |

### 2. 冲突处理
- **文字 vs VLM**: 如 SMILES 不一致，保留文字提取结果，VLM 结果标记为 uncertain
- **数值冲突**: 以原文引用更明确的为准

### 3. 构效关系 (SAR) 分析
分析以下内容：
- **活性趋势**: 哪些结构修饰提高/降低了活性
- **关键基团**: 哪些官能团对活性有显著影响
- **构效规律**: 总结活性与结构的关系
- **参考化合物对比**: 与已知化合物比较

输出要求：
- 500 字以内
- 中文
- 包含具体数据支持

---

## 输出格式
**只输出 JSON**：

```json
{{
  "metadata": {{
    "title": "string | null",
    "authors": ["string"],
    "document_type": "string",
    "key_targets": ["string"]
  }},
  "summary": "200-400字中文摘要",
  "compounds": [
    {{
      "name": "string",
      "smiles": "string | null",
      "category": "lead | hit | reference | intermediate | null",
      "description": "string",
      "source_ref": "string",
      "confidence": "high | medium | low",
      "uncertainty_reason": "string | null"
    }}
  ],
  "activities": [
    {{
      "compound": "string",
      "activity_type": "IC50 | pIC50 | EC50 | Ki | 抑制率",
      "value": number,
      "units": "nM | μM | %",
      "target": "string | null",
      "source_quote": "string",
      "source_ref": "string",
      "confidence": "high | medium | low",
      "uncertainty_reason": "string | null"
    }}
  ],
  "key_findings": [
    {{
      "finding": "string",
      "evidence": "string",
      "source_ref": "string",
      "confidence": "high | medium | low",
      "uncertainty_reason": "string | null"
    }}
  ],
  "sar_analysis": "构效关系总结（500字以内）",
  "uncertain_items": [
    {{
      "item_type": "string",
      "content": "string",
      "reason": "string",
      "suggested_action": "string"
    }}
  ]
}}
```"#,
        doc_type = structure.doc_type,
        section_count = section_results.len(),
        vlm_count = vlm_results.len(),
        sections = sections_text.join("\n\n---\n\n"),
        vlm = if vlm_text.is_empty() {
            "（无 VLM 识别结果）".to_string()
        } else {
            vlm_text.join("\n")
        },
    );

    let config = crate::parsers::post_process::load_llm_config()?;
    let (response, _tokens) = crate::parsers::post_process::call_llm_api_async(
        &config,
        "你是分子科学文档分析专家。合并多部分提取结果，进行去重、验证和构效关系分析，输出 JSON。",
        &prompt,
    ).await?;

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

/// 专利数据增强：将 molecule_traces 和 claim_graph 的信息整合进 StructuredData。
///
/// 1. 为现有 CompoundEntry 补充理化性质、图像、VLM 验证
/// 2. 若 LLM 未提取到某命名化合物，则追加新 CompoundEntry
/// 3. 将理化性质中的活性数据转为 ActivityEntry
/// 4. 若有 claim_graph，执行范围评估并加入 key_findings
fn enhance_patent_data(
    data: &mut StructuredData,
    traces: &[crate::parsers::molecule_extractor::MoleculeTrace],
    claim_graph: &Option<crate::parsers::claim_parser::ClaimDependencyGraph>,
    processing_log: &mut ProcessingLog,
) {
    use crate::parsers::molecule_extractor::MoleculeTrace;
    use crate::parsers::types::{CompoundEntry, PhysicochemicalProperty};

    let mut existing_names: std::collections::HashSet<String> =
        data.compounds.iter().map(|c| c.name.clone()).collect();
    let mut new_activities = Vec::new();

    for trace in traces {
        let mol = &trace.molecule;
        let props: Vec<PhysicochemicalProperty> = trace
            .properties
            .iter()
            .map(|p| PhysicochemicalProperty {
                property_type: p.property_type.clone(),
                value: p.value,
                unit: p.unit.clone(),
                source_quote: p.source_quote.clone(),
                confidence: p.confidence.clone(),
            })
            .collect();

        let related_images: Vec<String> = trace
            .related_images
            .iter()
            .map(|img| img.filename.clone())
            .collect();

        // 尝试找到同名的现有 CompoundEntry 并增强
        let mut found = false;
        for compound in data.compounds.iter_mut() {
            if compound.name == mol.name {
                found = true;
                if !props.is_empty() {
                    compound.physicochemical_props = Some(props.clone());
                }
                if !related_images.is_empty() {
                    compound.related_images = Some(related_images.clone());
                }
                if let Some(ref esmiles) = trace.vlm_verified_esmiles {
                    compound.vlm_verified_esmiles = Some(esmiles.clone());
                    if compound.esmiles.is_none() {
                        compound.esmiles = Some(esmiles.clone());
                    }
                }
                compound.page_location = mol.page_hint;
                // 提升置信度
                if compound.confidence != "high" {
                    compound.confidence = "high".into();
                }
                break;
            }
        }

        // 若未找到，追加新 CompoundEntry
        if !found {
            let description = if trace.properties.is_empty() {
                mol.context_text.chars().take(200).collect()
            } else {
                format!(
                    "从专利文本提取的命名化合物。关联属性: {}",
                    trace
                        .properties
                        .iter()
                        .map(|p| format!("{}={} {}", p.property_type, p.value, p.unit))
                        .collect::<Vec<_>>()
                        .join(", ")
                )
            };

            data.compounds.push(CompoundEntry {
                name: mol.name.clone(),
                esmiles: trace.vlm_verified_esmiles.clone(),
                category: None,
                description,
                source_ref: mol.page_hint.map(|p| format!("p.{}", p)).unwrap_or_else(|| mol.section.clone()),
                confidence: if trace.vlm_verified_esmiles.is_some() {
                    "high"
                } else {
                    "medium"
                }.into(),
                uncertainty_reason: if trace.vlm_verified_esmiles.is_none() {
                    Some("缺少图像验证的化学结构".into())
                } else {
                    None
                },
                physicochemical_props: if props.is_empty() { None } else { Some(props.clone()) },
                related_images: if related_images.is_empty() { None } else { Some(related_images) },
                vlm_verified_esmiles: trace.vlm_verified_esmiles.clone(),
                page_location: mol.page_hint,
            });
            existing_names.insert(mol.name.clone());
        }

        // 将活性类理化性质转为 ActivityEntry
        for prop in &trace.properties {
            let is_activity = matches!(
                prop.property_type.as_str(),
                "IC50" | "EC50" | "EC90" | "KI" | "KD" | "IC90"
            );
            if is_activity {
                new_activities.push(crate::parsers::types::ActivityEntry {
                    compound: mol.name.clone(),
                    activity_type: prop.property_type.clone(),
                    value: prop.value,
                    units: prop.unit.clone(),
                    target: None,
                    source_quote: prop.source_quote.clone(),
                    source_ref: mol.page_hint.map(|p| format!("p.{}", p)).unwrap_or_default(),
                    confidence: prop.confidence.clone(),
                    uncertainty_reason: None,
                });
            }
        }
    }

    // 追加新活性数据（去重）
    let existing_activity_keys: std::collections::HashSet<String> = data
        .activities
        .iter()
        .map(|a| format!("{}|{}|{}", a.compound, a.activity_type, a.value))
        .collect();
    for activity in new_activities {
        let key = format!("{}|{}|{}", activity.compound, activity.activity_type, activity.value);
        if !existing_activity_keys.contains(&key) {
            data.activities.push(activity);
        }
    }

    // Claim 范围评估
    if let Some(ref graph) = claim_graph {
        let assessments =
            crate::parsers::claim_policy::assess_all_compounds(traces, graph);
        for assessment in &assessments {
            let finding_text = format!(
                "化合物 '{}' 的专利范围评估: {:?}",
                assessment.compound_name, assessment.risk_level
            );
            let evidence = assessment.assessment_summary.clone();
            data.key_findings.push(crate::parsers::types::FindingEntry {
                finding: finding_text,
                evidence,
                source_ref: "claims_section".into(),
                confidence: match assessment.risk_level {
                    crate::parsers::claim_policy::RiskLevel::High => "high",
                    crate::parsers::claim_policy::RiskLevel::Medium => "medium",
                    crate::parsers::claim_policy::RiskLevel::Low => "low",
                    crate::parsers::claim_policy::RiskLevel::Clear => "high",
                }.into(),
                uncertainty_reason: if assessment.covered_claims.is_empty() {
                    Some("未检测到权利要求覆盖".into())
                } else {
                    None
                },
            });
        }

        processing_log.stages.push(StageLog {
            stage: 3,
            name: "专利范围评估".into(),
            status: "ok".into(),
            items_processed: assessments.len(),
            tokens_used: 0,
            errors: vec![],
        });
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
                physicochemical_props: None,
                related_images: None,
                vlm_verified_esmiles: None,
                page_location: None,
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
                physicochemical_props: None,
                related_images: None,
                vlm_verified_esmiles: None,
                page_location: None,
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


