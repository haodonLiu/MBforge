use serde::{Deserialize, Serialize};
use tauri::Emitter;

use crate::core::constants::{EVT_DOC_PROGRESS, EVT_DOC_RESULT};

use crate::commands::classifier::classify_document;
use crate::commands::extractor::{extract_activities, extract_esmiles_candidates};
use crate::core::molecule_store::{MoleculeDatabase, MoleculeImage, MoleculeRecord};

use super::doc_types::{
    DocProcessingContext, DocStructure, DocumentMetadata, DocumentReport, ImageRef, PdfParseResult,
    PostProcessResult, ProcessingLog, StageLog, StructuredData, UncertainItem,
};

mod extract;
mod helpers;
mod merge;

use extract::extract_molecules_from_pdf;
use helpers::{activity_entry_to_record, compound_entry_to_record, extract_section_text};
use merge::{enhance_patent_data, merge_partial_results, run_merge_and_sar};

// Re-export for commands/pdf.rs and other modules
pub use extract::{WorkflowResult, extract_pdf_workflow, find_project_root, classify_and_extract};

// ============================================================================
// PipelineOutput — 三个入口的统一返回类型
// ============================================================================
//
// [方案 1] 三个 Tauri command 的差异之前散在各处。
// 用一个 enum 把"输出到哪一层"作为唯一差异，其它逻辑保持不变。
//
// 三种 variant：
// - `Filesystem`: extract_pdf_workflow 写到 `<output_dir>/<pdf_name>/`
// - `InMemory`:   process_document 写 SQLite + 发 Tauri Event
// - `Indexed`:    index_project_rust 写 SQLite + ChromaDB + file cache
//
// 前端可以 `match result` 区别处理 — 不需要 if-else 检查每个字段是否存在。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum PipelineOutput {
    /// 入口 1：文件输出
    Filesystem {
        text_path: String,
        manifest_path: String,
        text_chars: usize,
        molecule_count: usize,
    },
    /// 入口 2：单文档 + 前端事件
    InMemory {
        report: DocumentReport,
        lit_reviewed: bool,
        /// Frontend 用这个 event_id 关联 EVT_DOC_RESULT
        event_id: String,
    },
    /// 入口 3：批量索引
    Indexed {
        indexed: usize,
        sections: usize,
        cache_skipped: usize,
        errors: Vec<String>,
    },
}

impl PipelineOutput {
    /// Helper: 包装 Filesystem 输出
    pub fn from_filesystem(
        text_path: std::path::PathBuf,
        manifest_path: std::path::PathBuf,
        molecule_count: usize,
    ) -> Self {
        let text_chars = std::fs::metadata(&text_path)
            .map(|m| m.len() as usize)
            .unwrap_or(0);
        Self::Filesystem {
            text_path: text_path.to_string_lossy().to_string(),
            manifest_path: manifest_path.to_string_lossy().to_string(),
            text_chars,
            molecule_count,
        }
    }

    /// Helper: 包装 InMemory 输出
    pub fn from_in_memory(
        report: DocumentReport,
        event_id: String,
    ) -> Self {
        let lit_reviewed = report.lit_reviewed;
        Self::InMemory {
            report,
            lit_reviewed,
            event_id,
        }
    }

    /// Helper: 包装 Indexed 输出
    pub fn from_indexed(
        indexed: usize,
        sections: usize,
        cache_skipped: usize,
        errors: Vec<String>,
    ) -> Self {
        Self::Indexed {
            indexed,
            sections,
            cache_skipped,
            errors,
        }
    }
}


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
    let mut mineru_images: Vec<ImageRef> = Vec::new();
    let (content, page_count): (String, usize) = match parser_choice.as_str() {
        "uniparser" => {
            let host = std::env::var("UNIPARSER_HOST")
                .unwrap_or_else(|_| "https://uniparser.dp.tech/".to_string());
            let api_key = std::env::var("UNIPARSER_API_KEY").unwrap_or_default();
            if api_key.is_empty() {
                return Err("UNIPARSER_API_KEY not set".into());
            }
            let client = super::pdf::uniparser::UniParserClient::new(&host, &api_key);
            let result = client.parse_pdf(&path)?;
            (result.content, result.page_count)
        }
        "mineru" => {
            let host =
                std::env::var("MINERU_HOST").unwrap_or_else(|_| "https://mineru.net".to_string());
            let api_key = std::env::var("MINERU_API_KEY").unwrap_or_default();
            let client = super::pdf::mineru::MineruClient::new(&host, &api_key);
            let options = super::pdf::mineru::scanned_pdf_options(&path);
            let result = client.parse_file_with_options(&path, &options)?;
            mineru_images = result.images;
            (result.markdown, 0)
        }
        "llama_parse" => {
            let pdf_bytes =
                tokio::fs::read(&path).await.map_err(|e| format!("Failed to read PDF: {}", e))?;
            let result = super::pdf::llama_parse::parse_with_llamaparse_sync(
                &crate::core::constants::sidecar_url(),
                pdf_bytes,
                None,
            )?;
            (result.markdown, result.page_count)
        }
        "liteparse" => {
            let result = super::pdf::liteparse::parse_with_liteparse(&path, false, None).await?;
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
    let extracted = super::pdf::images::extract_images_from_pdf(
        &path,
        tmp_dir.path(),
        20, // max_images
        2,  // max_size_mb
    )
    .unwrap_or_default();
    let mut images: Vec<ImageRef> = extracted
        .into_iter()
        .map(|img| ImageRef {
            filename: img.filename,
            page: img.page,
            region: None,
            description: None,
            esmiles: None,
            rel_path: None,
        })
        .collect();
    images.extend(mineru_images);

    // Stage 2: Classification
    let pages: Vec<String> = content.split("\n\n").map(|s| s.to_string()).collect();
    let classification = classify_document(pages, None);

    // Stage 3: Section-based chunking (PageIndex)
    let headings = super::structure::sections::extract_headings(&content);
    let sections = super::structure::sections::build_sections(&content, &headings, None, chunk_size);
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
        page_texts: vec![], // page_texts populated by post_process_pdf if available
    })
}

/// Post-process PDF extraction results using LLM.
#[tauri::command]
pub fn post_process_pdf(parse_result: PdfParseResult) -> Result<PostProcessResult, String> {
    super::structure::post_process::post_process(&parse_result)
}

/// ===== 以下为 A3: 完整文档处理管线 =====

/// 处理进度事件（通过 Tauri event 发射给前端）
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "stage", content = "payload")]
pub enum DocProgressEvent {
    #[serde(rename = "classify")]
    Classify { parser: String, page_count: usize },
    #[serde(rename = "meta")]
    Meta {
        doc_type: String,
        sections: Vec<String>,
    },
    #[serde(rename = "plan")]
    Plan {
        target_sections: Vec<String>,
        extraction_types: Vec<String>,
    },
    #[serde(rename = "section")]
    Section {
        name: String,
        status: String,
        compounds: usize,
        activities: usize,
    },
    #[serde(rename = "vlm")]
    Vlm {
        image_count: usize,
        esmiles_found: usize,
    },
    #[serde(rename = "merge")]
    Merge {
        total_compounds: usize,
        total_activities: usize,
    },
    #[serde(rename = "persist")]
    Persist { saved: usize, skipped: usize },
    #[serde(rename = "report")]
    Report { report_len: usize },
    #[serde(rename = "error")]
    Error { stage: String, message: String },
}

/// Stage 1: 调用 LLM 做文档结构分析
async fn run_meta_analysis(ctx: &DocProcessingContext) -> Result<DocStructure, String> {
    let prompt = crate::parsers::structure::intent::build_meta_prompt(ctx);

    let (response, _tokens) = crate::parsers::structure::post_process::call_llm_api_async(
        "你是文档分析专家。分析文档开头部分，判断文档类型和结构。只输出 JSON。",
        &prompt,
    )
    .await?;

    crate::parsers::structure::intent::parse_meta_response(&response)
}

// ---------------------------------------------------------------------------
// Project-root detection, record mapping, and helper re-exports
// ---------------------------------------------------------------------------
//
// Moved to sub-modules:
//   - extract::{classify_and_extract, find_project_root}
//   - helpers::{compound_entry_to_record, activity_entry_to_record, extract_section_text}
//   - merge::{run_merge_and_sar, merge_partial_results, enhance_patent_data}

/// [方案 3] 在 Stage 4 之后调 LiteratureAgent 做二次审阅
///
/// # 行为
/// - 同步等 30s（timeout）
/// - 把 `report` 序列化成 JSON 喂给 LiteratureAgent
/// - 失败降级：超时 / LLM 不可用 / 任何错误 → 静默 return false，**不**阻断主流程
/// - 成功：mutate `report.lit_reviewed = true` + `lit_decision_summary = Some(...)`
///
/// # 为何 timeout 30s？
/// - LiteratureAgent 会调 LLM + 可能调多个工具（注册 / 笔记 / 标签）
/// - 在 30s 内通常能完成（无 LLM key 跳过直接退化为 0ms）
/// - 但不让它阻塞 Stage 4.5 持久化
async fn review_with_lit_agent(
    report: &mut DocumentReport,
    _project_root: Option<&std::path::Path>,
) {
    use crate::core::agent::rig_adapter::{MbforgeAgent, MbforgeAgentSpec, MbforgeProviderConfig};
    use std::time::Duration;
    use tokio::time::timeout;

    // 1. 构造 LitAgent — 走 MbforgeAgent (rig-core adapter)。
    //    spec 的 system_prompt 已经从 specialist_agent 迁移过来 (M5)；
    //    factory 走 from_config() 按 AppConfig 自动选 OpenAI/Anthropic 路径。
    //    旧 LiteratureAgent 的 AuditLog 钩子 M6 删除 specialist_agent 时一并下线。
    let agent = match MbforgeProviderConfig::from_app_config() {
        Ok(cfg) => {
            use rig_core::memory::InMemoryConversationMemory;
            let memory = std::sync::Arc::new(
                crate::core::agent::managed_memory::MbforgeManagedMemory::new(
                    std::sync::Arc::new(InMemoryConversationMemory::new()),
                ),
            );
            match MbforgeAgent::from_config(
                &cfg,
                &MbforgeAgentSpec::literature(),
                Vec::new(),
                memory,
            ) {
                Ok(a) => a,
                Err(e) => {
                    log::warn!("[LitAgent] Failed to build MbforgeAgent: {}", e);
                    return;
                }
            }
        }
        Err(e) => {
            log::warn!("[LitAgent] Failed to load provider config: {}", e);
            return;
        }
    };

    // 2. 序列化 report → JSON 喂给 LitAgent
    let extraction_json = match serde_json::to_value(&*report) {
        Ok(v) => v,
        Err(e) => {
            log::warn!("[LitAgent] Failed to serialize report: {}", e);
            return;
        }
    };
    let prompt_text = match serde_json::to_string(&extraction_json) {
        Ok(s) => s,
        Err(e) => {
            log::warn!("[LitAgent] Failed to stringify report: {}", e);
            return;
        }
    };

    // 3. timeout 30s；失败 → 静默跳过
    let outcome = timeout(
        Duration::from_secs(30),
        agent.prompt(
            &crate::core::agent::session_id::SessionId::from("lit-review-oneshot"),
            &prompt_text,
        ),
    )
    .await;

    match outcome {
        Ok(Ok(text)) => {
            // [方案 3] 写入决策回执
            report.lit_reviewed = true;
            report.lit_decision_summary = Some(text);
            log::info!("[LitAgent] Review complete (MbforgeAgent single-shot)");
        }
        Ok(Err(e)) => {
            log::warn!("[LitAgent] prompt failed: {}", e);
        }
        Err(_elapsed) => {
            log::warn!("[LitAgent] review timed out after 30s, skipping");
        }
    }
}

/// 完整的文档处理入口

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

    // ===== Stage 0: 文件分类 + 提取（带文件缓存） =====
    {
        let _ = app.emit(
            EVT_DOC_PROGRESS,
            DocProgressEvent::Classify {
                parser: "auto".into(),
                page_count: 0,
            },
        );

        // 尝试从文件缓存加载
        let file_path = std::path::Path::new(&path);
        let mut cache_hit = false;

        if let Some(root) = find_project_root(file_path, project_root.as_deref()) {
            if let Ok(kb) = crate::core::get_or_init_kb(root.to_string_lossy().as_ref()) {
                match kb.file_cache().get(file_path) {
                    Ok(Some(cached)) => {
                        log::info!("File cache HIT for: {}", path);
                        // 从缓存恢复上下文
                        ctx.raw_text = cached.text;
                        ctx.parser_used = serde_json::from_str::<serde_json::Value>(&cached.metadata_json)
                            .ok()
                            .and_then(|m| m.get("parser").and_then(|p| p.as_str()).map(String::from))
                            .unwrap_or_else(|| "cached".into());
                        ctx.page_count = serde_json::from_str::<serde_json::Value>(&cached.metadata_json)
                            .ok()
                            .and_then(|m| m.get("page_count").and_then(|p| p.as_u64()))
                            .unwrap_or(0) as usize;
                        ctx.images = serde_json::from_str::<serde_json::Value>(&cached.metadata_json)
                            .ok()
                            .and_then(|m| m.get("images").cloned())
                            .and_then(|v| serde_json::from_value(v).ok())
                            .unwrap_or_default();
                        ctx.headings = crate::parsers::structure::sections::extract_headings(&ctx.raw_text);
                        ctx.sections = serde_json::from_str(&cached.sections_json)
                            .unwrap_or_default();
                        cache_hit = true;
                    }
                    Ok(None) => {
                        log::debug!("File cache MISS for: {}", path);
                    }
                    Err(e) => {
                        log::warn!("File cache error: {}", e);
                    }
                }
            }
        }

        if !cache_hit {
            let classified = classify_and_extract(&path).await?;
            ctx.raw_text = classified.text;
            ctx.page_count = classified.page_count;
            ctx.parser_used = classified.parser;
            ctx.images = classified.images;

            // Stage 0.5: Build sections
            ctx.headings = crate::parsers::structure::sections::extract_headings(&ctx.raw_text);
            ctx.sections =
                crate::parsers::structure::sections::build_sections(&ctx.raw_text, &ctx.headings, None, 8000);

            // 写入文件缓存
            if let Some(root) = find_project_root(file_path, project_root.as_deref()) {
                if let Ok(kb) = crate::core::get_or_init_kb(root.to_string_lossy().as_ref()) {
                    let sections_json = serde_json::to_string(&ctx.sections).unwrap_or_default();
                    let meta_json = serde_json::to_string(&serde_json::json!({
                        "parser": ctx.parser_used,
                        "page_count": ctx.page_count,
                        "images": ctx.images,
                    }))
                    .unwrap_or_default();
                    if let Err(e) = kb.file_cache().put(file_path, &ctx.raw_text, &sections_json, &meta_json) {
                        log::warn!("File cache write failed: {}", e);
                    }
                }
            }
        }
        processing_log.stages.push(StageLog {
            stage: 0,
            name: "文件分类与提取".into(),
            status: "ok".into(),
            items_processed: ctx.page_count,
            tokens_used: 0,
            errors: vec![],
        });

        let _ = app.emit(
            EVT_DOC_PROGRESS,
            DocProgressEvent::Classify {
                parser: ctx.parser_used.clone(),
                page_count: ctx.page_count,
            },
        );
    }

    // ===== Stage 1: 快速结构分析（Meta Prompt）=====
    let doc_structure: DocStructure;
    {
        let _ = app.emit(
            EVT_DOC_PROGRESS,
            DocProgressEvent::Meta {
                doc_type: "analyzing".into(),
                sections: vec![],
            },
        );

        doc_structure = match run_meta_analysis(&ctx).await {
            Ok(s) => s,
            Err(e) => {
                processing_log
                    .warnings
                    .push(format!("Meta analysis failed: {}", e));
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

        let _ = app.emit(
            EVT_DOC_PROGRESS,
            DocProgressEvent::Meta {
                doc_type: doc_structure.doc_type.clone(),
                sections: doc_structure.estimated_sections.clone(),
            },
        );
    }

    // ===== Stage 1.5: 用户意图路由 =====
    let plan = crate::parsers::structure::intent::interpret_request(&doc_structure, &user_req);

    let _ = app.emit(
        EVT_DOC_PROGRESS,
        DocProgressEvent::Plan {
            target_sections: plan.target_sections.clone(),
            extraction_types: plan.extraction_types.clone(),
        },
    );

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

        let result = match super::structure::post_process::post_process_section(
            &section_text,
            &ctx.parser_used,
            ctx.page_count,
        )
        .await
        {
            Ok(r) => {
                let _ = app.emit(
                    EVT_DOC_PROGRESS,
                    DocProgressEvent::Section {
                        name: section_name.clone(),
                        status: "ok".into(),
                        compounds: r.data.compounds.len(),
                        activities: r.data.activities.len(),
                    },
                );

                Some(r.data)
            }
            Err(e) => {
                processing_log.warnings.push(format!(
                    "Section '{}' processing failed: {}. Skipping.",
                    section_name, e
                ));
                processing_log.uncertain_items.push(UncertainItem {
                    item_type: "section_processing_error".into(),
                    content: format!("{} section could not be processed", section_name),
                    reason: e,
                    suggested_action: "Review this section manually".into(),
                });

                let _ = app.emit(
                    EVT_DOC_PROGRESS,
                    DocProgressEvent::Error {
                        stage: format!("section:{}", section_name),
                        message: format!("Section processing failed, skipped"),
                    },
                );

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
    let mut molecule_traces: Vec<crate::parsers::chem::molecule_extractor::MoleculeTrace> = Vec::new();
    let mut claim_graph: Option<crate::parsers::chem::claim_parser::ClaimDependencyGraph> = None;

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

        let named_mols =
            crate::parsers::chem::molecule_extractor::extract_named_molecule_series(&full_text);
        if !named_mols.is_empty() {
            let mut traces = crate::parsers::chem::molecule_extractor::link_molecules_to_images(
                &named_mols,
                &ctx.images,
                &[],
            );
            // 提取理化性质
            for trace in traces.iter_mut() {
                trace.properties =
                    crate::parsers::chem::molecule_extractor::extract_properties_for_molecule(
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
            claim_graph = Some(crate::parsers::chem::claim_parser::parse_claims_section(
                &claims_text,
            ));
        }

        let _ = app.emit(
            EVT_DOC_PROGRESS,
            DocProgressEvent::Section {
                name: "patent_molecule_extraction".into(),
                status: "ok".into(),
                compounds: molecule_traces.len(),
                activities: molecule_traces.iter().map(|t| t.properties.len()).sum(),
            },
        );
    }

    // ===== Stage 2b: VLM 化学结构识别 =====
    let vlm_config = crate::parsers::chem::vlm_chem::VlmConfig::default();
    let mut vlm_esmiles_found = 0usize;
    let mut vlm_results: Vec<(String, crate::parsers::chem::vlm_chem::ChemImageResult)> = Vec::new();

    // 解析图片的完整路径（优先使用持久化后的 rel_path）
    let project_root = extract::find_project_root(&ctx.source_path, project_root.as_deref());
    let resolve_image_path = |img: &crate::parsers::doc_types::ImageRef| -> Option<String> {
        if let Some(ref rel) = img.rel_path {
            if let Some(ref root) = project_root {
                let full = root.join(rel);
                if full.exists() {
                    return Some(full.to_string_lossy().to_string());
                }
            }
        }
        ctx.source_path
            .parent()
            .map(|p| p.join(&img.filename))
            .filter(|p| p.exists())
            .map(|p| p.to_string_lossy().to_string())
    };

    // ===== Stage 2b: MolDet + MolScribe 分子图像提取 =====
    // 统一处理：Scanned（lopdf 位图）和 TextBased（LiteParse 截图）都走 MolDet → 裁剪 → MolScribe
    if let Some(ref root) = project_root {
        let classified_for_mol = extract::ClassifyResult {
            text: ctx.raw_text.clone(),
            page_count: ctx.page_count,
            parser: ctx.parser_used.clone(),
            images: ctx.images.clone(),
            ocr_blocks: vec![],
        };
        match extract_molecules_from_pdf(
            &path,
            &classified_for_mol,
            &vlm_config.sidecar_url,
            root,
        )
        .await
        {
            Ok(detected) if !detected.is_empty() => {
                let mut file_results: Vec<(String, crate::parsers::chem::vlm_chem::ChemImageResult)> = Vec::new();
                for mol in detected.iter() {
                    file_results.push((
                        std::path::Path::new(&mol.crop_path)
                            .file_name()
                            .and_then(|s| s.to_str())
                            .unwrap_or("unknown")
                            .to_string(),
                        crate::parsers::chem::vlm_chem::ChemImageResult {
                            esmiles: mol.esmiles.clone(),
                            confidence: mol.confidence,
                        },
                    ));
                }
                vlm_esmiles_found = file_results.len();
                // [方案 2] 把结果挂到 ctx 上，让 DocumentReport / 前端能看到
                for (fname, chem) in &file_results {
                    ctx.chem_images.insert(fname.clone(), chem.clone());
                }
                ctx.detected_molecules = detected;
                vlm_results = file_results;
                let _ = app.emit(
                    EVT_DOC_PROGRESS,
                    DocProgressEvent::Vlm {
                        image_count: vlm_results.len(),
                        esmiles_found: vlm_esmiles_found,
                    },
                );

                // 回填识别结果到 molecule_traces（按文件名匹配）
                for trace in molecule_traces.iter_mut() {
                    for img in &trace.related_images {
                        if let Some((_, chem_result)) =
                            vlm_results.iter().find(|(fname, _)| fname == &img.filename)
                        {
                            trace.vlm_verified_esmiles = Some(chem_result.esmiles.clone());
                            trace.vlm_confidence = chem_result.confidence;
                        }
                    }
                }
            }
            Ok(_) => {
                let _ = app.emit(
                    EVT_DOC_PROGRESS,
                    DocProgressEvent::Vlm {
                        image_count: 0,
                        esmiles_found: 0,
                    },
                );
            }
            Err(e) => {
                log::warn!("[process_document] MolDet image extraction failed: {}", e);
            }
        }
    }

    // ===== Stage 2c: VLM 图片描述（非化学结构图） =====
    if !ctx.images.is_empty() {
        if let Some(ref root) = project_root {
             let mut cache = crate::parsers::chem::vlm_chem::ImageCaptionCache::new(root);
            let prompt = "请详细描述这张科学文献图片的内容。如果是图表，请说明其中的关键数据和趋势；如果是分子结构图，请描述其骨架特征和官能团；如果是实验流程图，请概述主要步骤。用中文回答，不超过100字。";

            for img in ctx.images.iter_mut() {
                // 跳过化学结构图（已由 MolScribe 处理）
                if crate::parsers::chem::vlm_chem::is_likely_chemical_structure(
                    &img.filename,
                    img.region.as_deref(),
                ) {
                    continue;
                }
                let Some(full_path) = resolve_image_path(img) else {
                    continue;
                };
                match crate::parsers::chem::vlm_chem::describe_image_cached(
                    &full_path,
                    prompt,
                    &vlm_config.sidecar_url,
                    &mut cache,
                )
                .await
                {
                    Ok(caption) => {
                        img.description = Some(caption);
                    }
                    Err(e) => {
                        log::warn!("[process_document] Image caption failed for {}: {}", img.filename, e);
                    }
                }
            }

            if let Err(e) = cache.save() {
                log::warn!("[process_document] Failed to save caption cache: {}", e);
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
                    processing_log.warnings.push(format!(
                        "Merge analysis failed: {}. Using partial results.",
                        e
                    ));
                    // Fallback: 合并已有结果
                    let combined = merge_partial_results(&section_results, &vlm_results);
                    final_data = combined;
                    sar_analysis = String::new();
                }
            }
        }

        let _ = app.emit(
            EVT_DOC_PROGRESS,
            DocProgressEvent::Merge {
                total_compounds: final_data.compounds.len(),
                total_activities: final_data.activities.len(),
            },
        );
    }

    // ===== Stage 3.5: 化学结构验证（RDKit 校验 + 规范化） =====
    {
        // 1. 收集待验证的 SMILES（去重）。`validate_smiles_batch` 内部会做净化，
        //    故无需在此处额外 sanitize（O-10 收尾：移除冗余净化循环）。
        let esmiles_to_validate: Vec<String> = final_data
            .compounds
            .iter()
            .filter_map(|c| c.esmiles.clone())
            .collect::<std::collections::HashSet<_>>()
            .into_iter()
            .collect();

        if !esmiles_to_validate.is_empty() {
            let validate_results = crate::parsers::chem::chem_validate::validate_smiles_batch(
                &esmiles_to_validate,
            );

            let mut validated_count = 0usize;
            let mut invalid_count = 0usize;

            for compound in final_data.compounds.iter_mut() {
                let Some(ref esmiles) = compound.esmiles else { continue };
                let Some((_, result)) = validate_results.iter().find(|(s, _)| s == esmiles) else {
                    continue;
                };

                if result.valid {
                    validated_count += 1;
                    // 使用规范化后的 SMILES
                    if let Some(ref canonical) = result.canonical_smiles {
                        if canonical != esmiles {
                            compound.esmiles = Some(canonical.clone());
                        }
                    }
                    // 如果原本 confidence 不高，提升到 high
                    if compound.confidence != "high" && result.issues.is_empty() {
                        compound.confidence = "high".into();
                    }
                } else {
                    invalid_count += 1;
                    compound.confidence = "low".into();
                    let issue_msgs: Vec<String> = result
                        .issues
                        .iter()
                        .map(|i| format!("[{}] {}", i.code, i.message))
                        .collect();
                    compound.uncertainty_reason = Some(format!(
                        "化学结构验证失败: {}",
                        issue_msgs.join("; ")
                    ));
                }
            }

            processing_log.stages.push(StageLog {
                stage: 3,
                name: "化学结构验证".into(),
                status: "ok".into(),
                items_processed: validated_count + invalid_count,
                tokens_used: 0,
                errors: if invalid_count > 0 {
                    vec![format!("{} 个化合物结构验证失败", invalid_count)]
                } else {
                    vec![]
                },
            });
        }
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
        enhance_patent_data(
            &mut final_data,
            &molecule_traces,
            &claim_graph,
            &mut processing_log,
        );
    }

    // ===== Stage 4: 报告生成 =====
    let report_md = crate::parsers::structure::report::generate_full_report(&final_data, Some(&sar_analysis));

    let mut report = DocumentReport {
        metadata: final_data.metadata.clone(),
        compounds: final_data.compounds.clone(),
        activities: final_data.activities.clone(),
        key_findings: final_data.key_findings.clone(),
        sar_analysis,
        uncertain_items: final_data.uncertain_items.clone(),
        report_markdown: report_md.clone(),
        // [方案 3] LitAgent 二次审阅入口已迁移到 review_with_lit_agent (M5)，
        // 用 MbforgeAgent::from_config + MbforgeAgentSpec::literature() 调一次 prompt。
        // review_with_lit_agent 会 set true + 写 decision_summary。
        lit_reviewed: false,
        lit_decision_summary: None,
    };

    let _ = app.emit(
        EVT_DOC_PROGRESS,
        DocProgressEvent::Report {
            report_len: report_md.len(),
        },
    );

    // ===== Stage 4.1: LiteratureAgent 二次审阅（[方案 3]）=====
    // 阻塞模式 + 30s timeout；失败降级 — 不阻断 Stage 4.5 持久化
    review_with_lit_agent(
        &mut report,
        project_root.as_deref().and_then(|s| std::path::Path::new(s).parent()),
    )
    .await;

    // ===== Stage 4.5: Persist extracted molecules to project store =====
    {
        let source_doc = final_data.metadata.source_file.as_deref().unwrap_or(&path);
        let source_type = &doc_structure.doc_type;

        if let Some(root) = find_project_root(&ctx.source_path, project_root.as_ref().and_then(|s| s.to_str())) {
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
                                    DocProgressEvent::Persist { saved, skipped },
                                );
                                processing_log.stages.push(StageLog {
                                    stage: 5,
                                    name: "分子库存储".into(),
                                    status: "ok".into(),
                                    items_processed: saved,
                                    tokens_used: 0,
                                    errors: vec![],
                                });
                                log::info!("Persisted {}/{} molecules to {:?}", saved, total, root);
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
                    DocProgressEvent::Persist { saved: 0, skipped },
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

    log::info!("[process_document] completed: path={}, compounds={}", path, report.compounds.len());

    // 注：[方案 1] 包装 PipelineOutput::InMemory 在 Rust 内部调用者
    // （tests, future REST API）有用；但 Tauri command 保持 () 返回以兼容
    // 前端（前端走 EVT_DOC_RESULT 事件订阅）。
    let _event_id = format!("doc-result-{}", chrono::Utc::now().timestamp_millis());
    let _out = PipelineOutput::from_in_memory(report, _event_id);
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
    /// 从文件缓存跳过的文件数（避免重复解析）
    #[serde(default)]
    pub cache_skipped: usize,
}

/// 扫描项目目录下的所有 PDF，提取 → 分 section → 索引到本地知识库。
#[tauri::command]
pub async fn index_project_rust(
    app: tauri::AppHandle,
    root: String,
) -> Result<IndexResult, String> {
    let project_root = std::path::PathBuf::from(&root);
    let config = crate::core::config::AppConfig::load();
    let kb = crate::core::document::knowledge_base::KnowledgeBase::new(&project_root, Some(&config.embed))
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
    let mut cache_skipped = 0usize;
    let mut total_sections = 0usize;
    let mut errors = Vec::new();
    let total = pdf_files.len();
    let sidecar_url = crate::core::constants::sidecar_url();

    // Phase 1: 并行提取（I/O 密集：MinerU OCR、LiteParse 截图、MolDet 检测）
    // 缓存命中的直接处理，未命中的并行 extract
    let mut cache_hits: Vec<(std::path::PathBuf, Vec<crate::parsers::structure::sections::SectionChunk>)> = Vec::new();
    let mut to_extract: Vec<(usize, std::path::PathBuf)> = Vec::new();

    for (i, pdf_path) in pdf_files.iter().enumerate() {
        let filename = pdf_path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_else(|| "unknown.pdf".to_string());

        let cached_sections = match kb.file_cache().get(pdf_path) {
            Ok(Some(cached)) => {
                log::info!("Batch index: cache HIT for {}", filename);
                serde_json::from_str::<Vec<crate::parsers::structure::sections::SectionChunk>>(&cached.sections_json)
                    .ok()
            }
            _ => None,
        };

        if let Some(sections) = cached_sections {
            cache_hits.push((pdf_path.clone(), sections));
        } else {
            to_extract.push((i, pdf_path.clone()));
        }
    }

    // 处理缓存命中
    for (pdf_path, sections) in &cache_hits {
        let doc_id = uuid::Uuid::new_v4().to_string();
        total_sections += sections.len();
        match kb.index_document(&doc_id, sections, &[]) {
            Ok(_) => {
                indexed += 1;
                cache_skipped += 1;
            }
            Err(e) => {
                let filename = pdf_path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
                errors.push(format!("{}: {}", filename, e));
            }
        }
    }

    // 并行提取未缓存的 PDF
    use futures::stream::{self, StreamExt};

    let extraction_results: Vec<_> = stream::iter(to_extract.into_iter())
        .map(|(i, pdf_path)| {
            let path_str = pdf_path.to_string_lossy().to_string();
            let filename = pdf_path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| "unknown.pdf".to_string());
            let sidecar = sidecar_url.clone();
            let root = project_root.clone();
            let _ = app.emit(
                EVT_DOC_PROGRESS,
                DocProgressEvent::Classify {
                    parser: format!("indexing {}/{}", i + 1, total),
                    page_count: 0,
                },
            );
            async move {
                let classified = classify_and_extract(&path_str).await?;
                let detected = extract_molecules_from_pdf(
                    &path_str, &classified, &sidecar, &root,
                ).await.unwrap_or_else(|e| {
                    log::warn!("[index_project] Molecule extraction failed for {}: {}", filename, e);
                    vec![]
                });
                Ok::<_, String>((pdf_path, classified, detected, filename))
            }
        })
        .buffer_unordered(4)
        .collect()
        .await;

    // Phase 2: 串行写入 KB + DB（SQLite 不适合并发写）
    for result in extraction_results {
        match result {
            Ok((pdf_path, classified, detected, filename)) => {
                let doc_id = uuid::Uuid::new_v4().to_string();
                let headings = crate::parsers::structure::sections::extract_headings(&classified.text);
                let sections = crate::parsers::structure::sections::build_sections(
                    &classified.text, &headings, None, 8000,
                );
                total_sections += sections.len();

                // 写入文件缓存
                let sections_json = serde_json::to_string(&sections).unwrap_or_default();
                let meta_json = serde_json::to_string(&serde_json::json!({
                    "parser": classified.parser,
                    "page_count": classified.page_count,
                    "images": classified.images,
                })).unwrap_or_default();
                if let Err(e) = kb.file_cache().put(&pdf_path, &classified.text, &sections_json, &meta_json) {
                    log::warn!("File cache write failed for {}: {}", filename, e);
                }

                match kb.index_document(&doc_id, &sections, &[]) {
                    Ok(_) => { indexed += 1; }
                    Err(e) => { errors.push(format!("{}: {}", filename, e)); }
                }

                // 持久化分子图像提取结果
                if !detected.is_empty() {
                    if let Ok(db) = MoleculeDatabase::open(&project_root) {
                        let mut saved = 0usize;
                        for mol in &detected {
                            let (clean_smiles, esmiles_opt, semantic_tags) =
                                crate::parsers::chem::chem_validate::separate_esmiles_layers(&mol.esmiles);
                            let mol_id = crate::core::helpers::generate_uuid();
                            let record = MoleculeRecord {
                                mol_id: mol_id.clone(),
                                smiles: clean_smiles.clone(),
                                esmiles: esmiles_opt,
                                semantic_tags,
                                name: format!("IMG-{}-P{}", filename, mol.page),
                                source_doc: filename.clone(),
                                activity: None,
                                activity_type: String::new(),
                                units: "nM".to_string(),
                                source_type: "patent_image".to_string(),
                                status: "pending".to_string(),
                                properties: serde_json::json!({}),
                                labels: vec!["image_extracted".to_string()],
                                notes: format!(
                                    "Auto-extracted from page {} via MolDet (conf={:.2}) + MolScribe (conf={:.2})",
                                    mol.page, mol.moldet_conf, mol.confidence
                                ),
                                created_at: None,
                                related_image_paths: vec![mol.crop_path.clone()],
                                vlm_verified_esmiles: Some(mol.esmiles.clone()),
                                vlm_confidence: mol.confidence,
                            };
                            if let Err(e) = db.add_molecule(&record) {
                                log::warn!("[index_project] Failed to add molecule {}: {}", mol_id, e);
                            } else {
                                let img = MoleculeImage {
                                    image_id: crate::core::helpers::generate_uuid(),
                                    mol_id: mol_id.clone(),
                                    image_path: mol.crop_path.clone(),
                                    page: Some(mol.page as usize),
                                    vlm_esmiles: Some(mol.esmiles.clone()),
                                    vlm_confidence: mol.confidence,
                                    is_structure_diagram: true,
                                    created_at: None,
                                };
                                if let Err(e) = db.add_molecule_image(&img) {
                                    log::warn!("[index_project] Failed to add molecule image: {}", e);
                                } else {
                                    saved += 1;
                                }
                            }
                        }
                        log::info!("[index_project] Saved {}/{} image-extracted molecules from {}", saved, detected.len(), filename);
                    }
                }
            }
            Err(e) => {
                errors.push(e);
            }
        }
    }

    // 注：[方案 1] 在 Rust 内部调用者用 PipelineOutput::from_indexed，
    // 但 Tauri command 保持 IndexResult 返回以兼容前端 kb.ts。
    let _pipeline = PipelineOutput::from_indexed(
        indexed,
        total_sections,
        cache_skipped,
        errors.clone(),
    );
    Ok(IndexResult {
        indexed,
        sections: total_sections,
        errors,
        cache_skipped,
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
        use crate::parsers::doc_types::{CompoundEntry, DocumentMetadata};
        let r1 = StructuredData {
            metadata: DocumentMetadata {
                title: None,
                authors: vec![],
                document_type: "patent".into(),
                key_targets: vec![],
                source_file: None,
            },
            summary: "".into(),
            compounds: vec![CompoundEntry {
                name: "E041".into(),
                esmiles: Some("C1CC1".into()),
                category: None,
                description: "test".into(),
                source_ref: "p5".into(),
                confidence: "high".into(),
                uncertainty_reason: None,
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
            metadata: DocumentMetadata {
                title: None,
                authors: vec![],
                document_type: "patent".into(),
                key_targets: vec![],
                source_file: None,
            },
            summary: "".into(),
            compounds: vec![CompoundEntry {
                name: "E041".into(),
                esmiles: Some("C1CC1".into()),
                category: None,
                description: "test duplicate".into(),
                source_ref: "p12".into(),
                confidence: "high".into(),
                uncertainty_reason: None,
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
            headings: vec![crate::parsers::structure::sections::Heading {
                level: 1,
                title: "Introduction".into(),
                line_num: 0,
            }],
            sections: vec![crate::parsers::structure::sections::SectionChunk {
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
        use crate::parsers::doc_types::{CompoundEntry, PhysicochemicalProperty};

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
        // "CCO" is pure SMILES without E-SMILES tags → esmiles should be None
        assert_eq!(rec.esmiles, None);
        assert_eq!(rec.smiles, "CCO");
        assert_eq!(rec.status, "confirmed");
        assert_eq!(rec.source_type, "patent");
        assert_eq!(rec.source_doc, "test.pdf");
        assert!(rec.labels.contains(&"inhibitor".to_string()));
        assert_eq!(rec.properties["IC50"]["value"], 12.5);
        assert!(rec.notes.contains("VLM verified"));
    }

    #[test]
    fn test_compound_entry_to_record_skips_empty_esmiles() {
        use crate::parsers::doc_types::CompoundEntry;

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
        use crate::parsers::doc_types::ActivityEntry;

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
        assert_eq!(rec.esmiles, None);
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

    /// 快速验证：两个专利 PDF 的图片提取能力
    #[test]
    #[ignore]
    fn test_extract_images_from_both_patents() {
        use std::path::Path;
        let us_pdf = r"C:\Users\10954\Desktop\X2\US20260027089A1.PDF";
        let cn_pdf = r"C:\Users\10954\Desktop\X2\CN120118069A.PDF";

        for (name, path) in [("US", us_pdf), ("CN", cn_pdf)] {
            let tmp = tempfile::tempdir().unwrap();
            let extracted = crate::parsers::pdf::images::extract_images_from_pdf(path, tmp.path(), 50, 5)
                .unwrap_or_default();
            println!(
                "[DIAG] {} patent: extracted {} images (max 50, max 5MB each)",
                name,
                extracted.len()
            );
            for (i, img) in extracted.iter().take(5).enumerate() {
                println!(
                    "  img[{}]: page={}, filename={}, size={} bytes",
                    i,
                    img.page,
                    img.filename,
                    std::fs::metadata(&img.path).map(|m| m.len()).unwrap_or(0)
                );
            }
        }
    }

    /// 有监督的全流程集成测试：CN120118069A.PDF（中国专利，14.9MB）
    #[test]
    #[ignore]
    fn test_supervised_pipeline_cn_patent() {
        use super::extract::ClassifyResult;

        let _ = dotenvy::dotenv();

        let pdf_path = r"C:\Users\10954\Desktop\X2\CN120118069A.PDF";
        let project_root = std::path::Path::new(r"C:\Users\10954\Desktop\X2");
        let mbforge_dir = project_root.join(".mbforge");

        if mbforge_dir.exists() {
            std::fs::remove_dir_all(&mbforge_dir).unwrap();
        }

        let pdf_type = pdf_inspector::detect_pdf(pdf_path).expect("PDF 类型检测失败");
        println!("[DIAG] PDF 类型检测: {:?}", pdf_type);

        let rt = tokio::runtime::Runtime::new().unwrap();
        let classified: ClassifyResult = rt.block_on(async {
            let path = pdf_path.to_string();
            tokio::task::spawn_blocking(move || {
                let pdf_result = pdf_inspector::process_pdf(&path)
                    .map_err(|e| format!("pdf-inspector failed: {}", e))
                    .unwrap();
                let md = pdf_result.markdown.unwrap_or_default();
                let page_count = pdf_result.page_count as usize;

                println!("[DIAG] pdf_inspector: text_len={}, page_count={}", md.len(), page_count);

                if md.len() < 100 && page_count > 0 && std::env::var("MINERU_API_KEY").is_ok() {
                    println!("[DIAG] 降级到 MinerU...");
                    let host = std::env::var("MINERU_HOST")
                        .unwrap_or_else(|_| "https://mineru.net".to_string());
                    let api_key = std::env::var("MINERU_API_KEY").unwrap_or_default();
                    let client = crate::parsers::pdf::mineru::MineruClient::new(&host, &api_key);
                    let options = crate::parsers::pdf::mineru::scanned_pdf_options(&path);
                    let result = client.parse_file_with_options(&path, &options).expect("MinerU 解析失败");
                    return ClassifyResult {
                        text: result.markdown,
                        page_count: 0,
                        parser: "mineru".into(),
                        images: result.images,
                        ocr_blocks: result.ocr_blocks,
                    };
                }

                ClassifyResult {
                    text: md,
                    page_count,
                    parser: "pdf_inspector".into(),
                    images: vec![],
                    ocr_blocks: vec![],
                }
            })
            .await
            .unwrap()
        });

        assert!(!classified.text.is_empty(), "提取文本为空，parser={}", classified.parser);
        println!(
            "Stage 0 完成: parser={}, pages={}, text_len={}, images={}",
            classified.parser,
            classified.page_count,
            classified.text.len(),
            classified.images.len()
        );

        let headings = crate::parsers::structure::sections::extract_headings(&classified.text);
        let sections = crate::parsers::structure::sections::build_sections(
            &classified.text,
            &headings,
            None,
            8000,
        );
        assert!(!sections.is_empty(), "分块结果为空");
        println!("Stage 0.5 完成: headings={}, sections={}", headings.len(), sections.len());

        let embed_config = crate::core::config::EmbedConfig {
            provider: "qwen3".into(),
            model_name: crate::core::constants::DEFAULT_EMBED_MODEL.into(),
            base_url: "http://127.0.0.1:18792".into(),
            api_key: "test".into(),
            device: "cuda".into(),
            mrl_dim: None,
            instruction: String::new(),
        };

        let kb = crate::core::document::knowledge_base::KnowledgeBase::new(
            project_root,
            Some(&embed_config),
        )
        .expect("KnowledgeBase 创建失败");
        assert!(kb.has_vector_search(), "Embedder 未初始化");

        let doc_id = uuid::Uuid::new_v4().to_string();
        let indexed = kb.index_document(&doc_id, &sections, &[])
            .expect("index_document 失败");
        assert!(indexed > 0, "未索引任何 section");
        println!("Stage 1 完成: indexed={} sections into vectors.db", indexed);

        assert!(mbforge_dir.exists(), ".mbforge 目录未创建");
        assert!(
            mbforge_dir.join("knowledge_base").join("vectors.db").exists(),
            "vectors.db 未创建"
        );

        let search_results = kb.search("compound", 5).expect("搜索失败");
        println!("向量搜索测试: query='compound', results={}", search_results.len());
        for (i, r) in search_results.iter().take(3).enumerate() {
            println!("  Result[{}]: score={:.4}, text_len={}", i, r.score, r.text.len());
        }
    }

    /// 有监督的全流程集成测试：US20260027089A1.PDF
    /// 覆盖 Stage 0(提取) → Stage 0.5(分块) → Stage 1(向量入库)
    #[test]
    #[ignore] // 需要 sidecar 运行，手动执行: cargo test --lib parsers::pipeline::tests::test_supervised_pipeline_us_patent -- --ignored
    fn test_supervised_pipeline_us_patent() {
        use super::extract::ClassifyResult;

        // 加载 .env 使 MINERU_API_KEY 等环境变量可用
        let _ = dotenvy::dotenv();

        let pdf_path = r"C:\Users\10954\Desktop\X2\US20260027089A1.PDF";
        let project_root = std::path::Path::new(r"C:\Users\10954\Desktop\X2");
        let mbforge_dir = project_root.join(".mbforge");

        // 清理旧产物，确保测试可重复
        if mbforge_dir.exists() {
            std::fs::remove_dir_all(&mbforge_dir).unwrap();
        }

        // 诊断：检测 PDF 类型
        let pdf_type = pdf_inspector::detect_pdf(pdf_path).expect("PDF 类型检测失败");
        println!("[DIAG] PDF 类型检测: {:?}", pdf_type);

        // ===== Stage 0: 提取（MinerU 解析在 spawn_blocking 中执行，避免 runtime 嵌套） =====
        let rt = tokio::runtime::Runtime::new().unwrap();
        let classified: ClassifyResult = rt.block_on(async {
            let path = pdf_path.to_string();
            tokio::task::spawn_blocking(move || {
                // 先尝试 pdf_inspector
                let pdf_result = pdf_inspector::process_pdf(&path)
                    .map_err(|e| format!("pdf-inspector failed: {}", e))
                    .unwrap();
                let md = pdf_result.markdown.unwrap_or_default();
                let page_count = pdf_result.page_count as usize;

                println!(
                    "[DIAG] pdf_inspector: text_len={}, page_count={}",
                    md.len(), page_count
                );

                // 若文本不足，降级到 MinerU
                if md.len() < 100 && page_count > 0 && std::env::var("MINERU_API_KEY").is_ok() {
                    println!("[DIAG] 降级到 MinerU...");
                    let host = std::env::var("MINERU_HOST")
                        .unwrap_or_else(|_| "https://mineru.net".to_string());
                    let api_key = std::env::var("MINERU_API_KEY").unwrap_or_default();
                    let client = crate::parsers::pdf::mineru::MineruClient::new(&host, &api_key);
                    let options = crate::parsers::pdf::mineru::scanned_pdf_options(&path);
                    let result = client.parse_file_with_options(&path, &options).expect("MinerU 解析失败");
                    return ClassifyResult {
                        text: result.markdown,
                        page_count: 0,
                        parser: "mineru".into(),
                        images: result.images,
                        ocr_blocks: result.ocr_blocks,
                    };
                }

                ClassifyResult {
                    text: md,
                    page_count,
                    parser: "pdf_inspector".into(),
                    images: vec![],
                    ocr_blocks: vec![],
                }
            })
            .await
            .unwrap()
        });

        assert!(
            !classified.text.is_empty(),
            "提取文本为空，parser={}",
            classified.parser
        );
        println!(
            "Stage 0 完成: parser={}, pages={}, text_len={}, images={}",
            classified.parser,
            classified.page_count,
            classified.text.len(),
            classified.images.len()
        );

        // ===== Stage 0.5: headings + sections =====
        let headings = crate::parsers::structure::sections::extract_headings(&classified.text);
        let sections = crate::parsers::structure::sections::build_sections(
            &classified.text,
            &headings,
            None,
            8000,
        );
        assert!(!sections.is_empty(), "分块结果为空");
        log::info!(
            "Stage 0.5 完成: headings={}, sections={}",
            headings.len(),
            sections.len()
        );
        for (i, sec) in sections.iter().take(5).enumerate() {
            log::info!(
                "  Section[{}]: title='{}', path='{}', chars={}, pages={:?}",
                i,
                sec.title,
                sec.path,
                sec.text.len(),
                (sec.page_start, sec.page_end)
            );
        }

        // ===== Stage 1: KnowledgeBase + index_document =====
        let embed_config = crate::core::config::EmbedConfig {
            provider: "qwen3".into(),
            model_name: crate::core::constants::DEFAULT_EMBED_MODEL.into(),
            base_url: "http://127.0.0.1:18792".into(),
            api_key: "test".into(), // 非空以触发 SidecarEmbedder
            device: "cuda".into(),
            mrl_dim: None,
            instruction: String::new(),
        };

        let kb = crate::core::document::knowledge_base::KnowledgeBase::new(
            project_root,
            Some(&embed_config),
        )
        .expect("KnowledgeBase 创建失败");
        assert!(kb.has_vector_search(), "Embedder 未初始化");

        let doc_id = uuid::Uuid::new_v4().to_string();
        let indexed = kb.index_document(&doc_id, &sections, &[])
            .expect("index_document 失败");
        assert!(indexed > 0, "未索引任何 section");
        log::info!("Stage 1 完成: indexed={} sections into vectors.db", indexed);

        // ===== 验证产物 =====
        assert!(mbforge_dir.exists(), ".mbforge 目录未创建");
        assert!(
            mbforge_dir.join("knowledge_base").join("vectors.db").exists(),
            "vectors.db 未创建"
        );
        assert!(
            mbforge_dir.join("knowledge_base").join("cache.db").exists(),
            "cache.db 未创建"
        );

        // 验证向量搜索可用
        let search_results = kb.search("compound", 5).expect("搜索失败");
        log::info!("向量搜索测试: query='compound', results={}", search_results.len());
        for (i, r) in search_results.iter().take(3).enumerate() {
            log::info!("  Result[{}]: score={:.4}, text_len={}", i, r.score, r.text.len());
        }
    }
}

#[cfg(test)]
mod lit_agent_tests {
    use super::*;
    use std::path::PathBuf;

    /// 验证 review_with_lit_agent 在 LLM 不可用时**不会** panic，
    /// 失败时静默返回（不修改 report.lit_reviewed）。
    ///
    /// [方案 3] 安全保证：LitAgent 故障**永远**不能阻断主流程。
    ///
    /// M5 迁移：原 `LiteratureAgent::new` 已经在没 API key 时静默跳过。
    /// 新 `MbforgeAgent::from_config` 在 provider build 失败时也走静默 return 路径。
    /// 标记 `#[ignore]`：未配置真实 LLM provider 时这个测试会撞 30s timeout，
    /// CI 跑 `cargo test --lib` 时默认不带任何 key，会把测试从秒级拖到 30s+。
    /// 想验证 LitAgent 集成的人取消 ignore 并配置 OPENAI_API_KEY / ANTHROPIC_API_KEY。
    #[tokio::test]
    #[ignore = "requires a configured LLM provider; the function under test still silently no-ops when the provider config build fails"]
    async fn test_review_with_lit_agent_failure_does_not_panic() {
        // 构造一个最小 DocumentReport
        let mut report = DocumentReport {
            metadata: crate::parsers::doc_types::DocumentMetadata {
                title: Some("test".into()),
                authors: vec![],
                document_type: "paper".into(),
                key_targets: vec![],
                source_file: None,
            },
            compounds: vec![],
            activities: vec![],
            key_findings: vec![],
            sar_analysis: String::new(),
            uncertain_items: vec![],
            report_markdown: "# test".into(),
            lit_reviewed: false,
            lit_decision_summary: None,
        };
        // project_root 走测试用路径；不要求真实项目。
        review_with_lit_agent(&mut report, Some(&PathBuf::from("/tmp"))).await;
        // 不论成功失败，**不**触发 panic 即可
        // (实际是否 lit_reviewed 取决于 LLM 调用，断言不强求)
    }
}


#[cfg(test)]
mod pipeline_output_tests {
    use super::*;

    /// [方案 1] 验证 PipelineOutput::from_filesystem
    #[test]
    fn test_pipeline_output_from_filesystem() {
        let tmp = tempfile::tempdir().unwrap();
        let text_path = tmp.path().join("text.md");
        std::fs::write(&text_path, "# Hello\n\nThis is a test document.").unwrap();
        let manifest_path = tmp.path().join("manifest.json");
        std::fs::write(&manifest_path, "{}").unwrap();

        let output = PipelineOutput::from_filesystem(text_path.clone(), manifest_path, 3);
        match output {
            PipelineOutput::Filesystem { text_chars, molecule_count, .. } => {
                assert!(text_chars > 0);
                assert_eq!(molecule_count, 3);
            }
            _ => panic!("expected Filesystem variant"),
        }
    }

    /// [方案 1] 验证 PipelineOutput::from_in_memory 携带 lit_reviewed
    #[test]
    fn test_pipeline_output_from_in_memory() {
        let report = DocumentReport {
            metadata: crate::parsers::doc_types::DocumentMetadata {
                title: Some("test".into()),
                authors: vec![],
                document_type: "paper".into(),
                key_targets: vec![],
                source_file: None,
            },
            compounds: vec![],
            activities: vec![],
            key_findings: vec![],
            sar_analysis: String::new(),
            uncertain_items: vec![],
            report_markdown: String::new(),
            lit_reviewed: true,
            lit_decision_summary: Some("approved".into()),
        };
        let output = PipelineOutput::from_in_memory(report, "evt-123".to_string());
        match output {
            PipelineOutput::InMemory { lit_reviewed, event_id, .. } => {
                assert!(lit_reviewed);
                assert_eq!(event_id, "evt-123");
            }
            _ => panic!("expected InMemory variant"),
        }
    }

    /// [方案 1] 验证 PipelineOutput::from_indexed
    #[test]
    fn test_pipeline_output_from_indexed() {
        let output = PipelineOutput::from_indexed(5, 42, 3, vec!["err1".into()]);
        match output {
            PipelineOutput::Indexed { indexed, sections, cache_skipped, errors } => {
                assert_eq!(indexed, 5);
                assert_eq!(sections, 42);
                assert_eq!(cache_skipped, 3);
                assert_eq!(errors.len(), 1);
            }
            _ => panic!("expected Indexed variant"),
        }
    }

    /// [方案 1] 验证 PipelineOutput JSON 序列化的 tag discriminator
    /// （前端的 `if (output.kind === "filesystem")` 模式依赖此格式）
    #[test]
    fn test_pipeline_output_serde_tag() {
        let output = PipelineOutput::from_indexed(1, 2, 0, vec![]);
        let json = serde_json::to_string(&output).unwrap();
        assert!(json.contains("\"kind\":\"indexed\""), "missing tag: {}", json);
    }
}
