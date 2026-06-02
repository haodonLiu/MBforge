use serde::{Deserialize, Serialize};
use tauri::Emitter;

use crate::core::constants::{EVT_DOC_PROGRESS, EVT_DOC_RESULT};

use crate::commands::classifier::classify_document;
use crate::commands::extractor::{extract_activities, extract_esmiles_candidates};
use crate::core::molecule_store::{MoleculeDatabase, MoleculeRecord};

use super::doc_types::{
    DocProcessingContext, DocStructure, DocumentMetadata, DocumentReport, ImageRef,
    PdfParseResult, PostProcessResult, ProcessingLog, StageLog, StructuredData,
    UncertainItem,
};

mod extract;
mod helpers;
mod merge;

use extract::{classify_and_extract, find_project_root};
use helpers::{activity_entry_to_record, compound_entry_to_record, extract_section_text};
use merge::{enhance_patent_data, merge_partial_results, run_merge_and_sar};

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
                &crate::core::constants::sidecar_url(),
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
    #[serde(rename = "persist")]
    Persist { saved: usize, skipped: usize },
    #[serde(rename = "report")]
    Report { report_len: usize },
    #[serde(rename = "error")]
    Error { stage: String, message: String },
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

// ---------------------------------------------------------------------------
// Project-root detection, record mapping, and helper re-exports
// ---------------------------------------------------------------------------
//
// Moved to sub-modules:
//   - extract::{classify_and_extract, find_project_root}
//   - helpers::{compound_entry_to_record, activity_entry_to_record, extract_section_text}
//   - merge::{run_merge_and_sar, merge_partial_results, enhance_patent_data}

/// 完整的文档处理入口
///
/// 异步执行 Stages 0-4，通过 Tauri event 发射进度。
#[tauri::command]
pub async fn process_document(
    path: String,
    user_request: Option<String>,
    project_root: Option<String>,
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
        let _ = app.emit(EVT_DOC_PROGRESS, DocProgressEvent::Classify {
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

        let _ = app.emit(EVT_DOC_PROGRESS, DocProgressEvent::Classify {
            parser: ctx.parser_used.clone(),
            page_count: ctx.page_count,
        });
    }

    // ===== Stage 1: 快速结构分析（Meta Prompt）=====
    let doc_structure: DocStructure;
    {
        let _ = app.emit(EVT_DOC_PROGRESS, DocProgressEvent::Meta {
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

        let _ = app.emit(EVT_DOC_PROGRESS, DocProgressEvent::Meta {
            doc_type: doc_structure.doc_type.clone(),
            sections: doc_structure.estimated_sections.clone(),
        });
    }

    // ===== Stage 1.5: 用户意图路由 =====
    let plan = crate::parsers::intent::interpret_request(&doc_structure, &user_req);

    let _ = app.emit(EVT_DOC_PROGRESS, DocProgressEvent::Plan {
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
                let _ = app.emit(EVT_DOC_PROGRESS, DocProgressEvent::Section {
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

                let _ = app.emit(EVT_DOC_PROGRESS, DocProgressEvent::Error {
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

        let _ = app.emit(EVT_DOC_PROGRESS, DocProgressEvent::Section {
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

        let _ = app.emit(EVT_DOC_PROGRESS, DocProgressEvent::Vlm {
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

        let _ = app.emit(EVT_DOC_PROGRESS, DocProgressEvent::Merge {
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

    let _ = app.emit(EVT_DOC_PROGRESS, DocProgressEvent::Report {
        report_len: report_md.len(),
    });

    // ===== Stage 4.5: Persist extracted molecules to project store =====
    {
        let source_doc = final_data
            .metadata
            .source_file
            .as_deref()
            .unwrap_or(&path);
        let source_type = &doc_structure.doc_type;

        if let Some(root) = find_project_root(&ctx.source_path, project_root.as_deref()) {
            let mut records: Vec<MoleculeRecord> = Vec::new();
            let mut skipped = 0usize;

            for compound in &final_data.compounds {
                match compound_entry_to_record(compound, source_doc, source_type) {
                    Some(rec) => records.push(rec),
                    None => skipped += 1,
                }
            }

            for activity in &final_data.activities {
                records.push(activity_entry_to_record(activity, source_doc, source_type));
            }

            if !records.is_empty() {
                match MoleculeDatabase::open(&root) {
                    Ok(db) => {
                        let total = records.len();
                        match db.add_molecules_batch(&records) {
                            Ok(saved) => {
                                let _ = app.emit(
                                    EVT_DOC_PROGRESS,
                                    DocProgressEvent::Persist {
                                        saved,
                                        skipped,
                                    },
                                );
                                processing_log.stages.push(StageLog {
                                    stage: 5,
                                    name: "分子库存储".into(),
                                    status: "ok".into(),
                                    items_processed: saved,
                                    tokens_used: 0,
                                    errors: vec![],
                                });
                                log::info!(
                                    "Persisted {}/{} molecules to {:?}",
                                    saved,
                                    total,
                                    root
                                );
                            }
                            Err(e) => {
                                let _ = app.emit(
                                    EVT_DOC_PROGRESS,
                                    DocProgressEvent::Error {
                                        stage: "persist".into(),
                                        message: e.clone(),
                                    },
                                );
                                processing_log.warnings.push(format!(
                                    "Molecule store batch insert failed: {}. {}/{} records not saved.",
                                    e, total, total
                                ));
                                log::error!("Molecule store batch insert failed: {}", e);
                            }
                        }
                    }
                    Err(e) => {
                        processing_log.warnings.push(format!(
                            "Failed to open molecule database at {:?}: {}. Skipping persistence.",
                            root, e
                        ));
                        log::warn!("Failed to open molecule DB at {:?}: {}", root, e);
                    }
                }
            } else {
                let _ = app.emit(
                    EVT_DOC_PROGRESS,
                    DocProgressEvent::Persist {
                        saved: 0,
                        skipped,
                    },
                );
            }
        } else {
            log::warn!(
                "No project root found for {}. Skipping molecule persistence.",
                path
            );
        }
    }

    // 最终结果发射
    let _ = app.emit(EVT_DOC_RESULT, &report);

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
    let kb = crate::core::document::knowledge_base::KnowledgeBase::new(&project_root)
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
            EVT_DOC_PROGRESS,
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
        use super::super::doc_types::{CompoundEntry, DocumentMetadata};
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

    #[test]
    fn test_compound_entry_to_record() {
        use super::super::doc_types::{CompoundEntry, PhysicochemicalProperty};

        let compound = CompoundEntry {
            name: "Compound-1".into(),
            esmiles: Some("CCO".into()),
            category: Some("inhibitor".into()),
            description: "desc".into(),
            source_ref: "p.5".into(),
            confidence: "high".into(),
            uncertainty_reason: None,
            physicochemical_props: Some(vec![PhysicochemicalProperty {
                property_type: "IC50".into(),
                value: 12.5,
                unit: "nM".into(),
                source_quote: "IC50 = 12.5 nM".into(),
                confidence: "high".into(),
            }]),
            related_images: None,
            vlm_verified_esmiles: Some("CCO".into()),
            page_location: Some(5),
        };

        let rec = compound_entry_to_record(&compound, "test.pdf", "patent").unwrap();
        assert_eq!(rec.name, "Compound-1");
        assert_eq!(rec.esmiles, "CCO");
        assert_eq!(rec.status, "confirmed");
        assert_eq!(rec.source_type, "patent");
        assert_eq!(rec.source_doc, "test.pdf");
        assert!(rec.tags.contains(&"inhibitor".to_string()));
        assert_eq!(rec.properties["IC50"]["value"], 12.5);
        assert!(rec.notes.contains("VLM verified"));
    }

    #[test]
    fn test_compound_entry_to_record_skips_empty_esmiles() {
        use super::super::doc_types::CompoundEntry;

        let compound = CompoundEntry {
            name: "No-Structure".into(),
            esmiles: Some("".into()),
            category: None,
            description: "desc".into(),
            source_ref: "p.1".into(),
            confidence: "medium".into(),
            uncertainty_reason: None,
            physicochemical_props: None,
            related_images: None,
            vlm_verified_esmiles: None,
            page_location: None,
        };

        assert!(compound_entry_to_record(&compound, "test.pdf", "paper").is_none());
    }

    #[test]
    fn test_activity_entry_to_record() {
        use super::super::doc_types::ActivityEntry;

        let activity = ActivityEntry {
            compound: "Compound-1".into(),
            activity_type: "IC50".into(),
            value: 12.5,
            units: "nM".into(),
            target: Some("JAK2".into()),
            source_quote: "IC50 = 12.5 nM".into(),
            source_ref: "p.5".into(),
            confidence: "high".into(),
            uncertainty_reason: None,
        };

        let rec = activity_entry_to_record(&activity, "test.pdf", "patent");
        assert_eq!(rec.name, "Compound-1");
        assert_eq!(rec.esmiles, "");
        assert_eq!(rec.activity, Some(12.5));
        assert_eq!(rec.activity_type, "IC50");
        assert_eq!(rec.units, "nM");
        assert_eq!(rec.status, "confirmed");
        assert_eq!(rec.source_type, "patent_activity");
        assert!(rec.notes.contains("12.5"));
    }

    #[test]
    fn test_find_project_root_explicit() {
        let tmp = std::env::temp_dir().join(format!("mbforge-test-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&tmp.join(".mbforge")).unwrap();
        let pdf = tmp.join("sub").join("doc.pdf");
        std::fs::create_dir_all(pdf.parent().unwrap()).unwrap();

        let root = find_project_root(&pdf, Some(tmp.to_str().unwrap()));
        assert_eq!(root, Some(tmp.clone()));

        std::fs::remove_dir_all(&tmp).unwrap();
    }

    #[test]
    fn test_find_project_root_walk_up() {
        let tmp = std::env::temp_dir().join(format!("mbforge-test-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&tmp.join(".mbforge")).unwrap();
        let pdf = tmp.join("papers").join("sub").join("doc.pdf");
        std::fs::create_dir_all(pdf.parent().unwrap()).unwrap();

        let root = find_project_root(&pdf, None);
        assert_eq!(root, Some(tmp.clone()));

        std::fs::remove_dir_all(&tmp).unwrap();
    }
}


