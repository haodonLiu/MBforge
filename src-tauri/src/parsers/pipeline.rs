use serde::{Deserialize, Serialize};
use tauri::Emitter;

use crate::commands::classifier::{classify_document, DocumentClassification};
use crate::commands::extractor::{extract_activities, extract_smiles_candidates, ActivityData};

use super::post_process::StructuredData;
use super::types::{
    DocProcessingContext, DocStructure, DocumentReport, ImageRef, ProcessingLog,
    StageLog,
};

/// Unified PDF parsing result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PdfParseResult {
    /// Extracted text/markdown content.
    pub content: String,
    /// Classification result.
    pub classification: DocumentClassification,
    /// Chunks after splitting.
    pub chunks: Vec<String>,
    /// Extracted SMILES candidates.
    pub smiles: Vec<String>,
    /// Extracted activity data.
    pub activities: Vec<ActivityData>,
    /// Parser used: "pdf_inspector", "llama_parse", "uniparser", or "mineru".
    pub parser: String,
    /// Page count.
    pub page_count: usize,
    /// Images extracted (MinerU path only).
    pub images: Vec<ImageRef>,
}

impl From<DocProcessingContext> for PdfParseResult {
    fn from(ctx: DocProcessingContext) -> Self {
        let classification = classify_document(
            ctx.raw_text.split("\n\n").map(|s| s.to_string()).collect(),
            None,
        );
        let chunks = crate::commands::text_ops::text_chunk(ctx.raw_text.clone(), 512, 128).chunks;
        let smiles = extract_smiles_candidates(ctx.raw_text.clone());
        let activities = extract_activities(ctx.raw_text.clone());

        PdfParseResult {
            content: ctx.raw_text,
            classification,
            chunks,
            smiles,
            activities,
            parser: ctx.parser_used,
            page_count: ctx.page_count,
            images: ctx.images,
        }
    }
}

/// Parse a PDF using the full pipeline.
///
/// This chains: extraction → classification → chunking → molecule extraction.
#[tauri::command]
pub fn parse_pdf(
    path: String,
    chunk_size: Option<usize>,
    overlap: Option<usize>,
    parser: Option<String>,
) -> Result<PdfParseResult, String> {
    let chunk_size = chunk_size.unwrap_or(512);
    let overlap = overlap.unwrap_or(128);
    let parser_choice = parser.unwrap_or_else(|| "pdf_inspector".to_string());

    // Stage 1: Text extraction
    let (content, page_count, images): (String, usize, Vec<ImageRef>) = match parser_choice.as_str() {
        "uniparser" => {
            let host = std::env::var("UNIPARSER_HOST")
                .unwrap_or_else(|_| "https://uniparser.dp.tech/".to_string());
            let api_key = std::env::var("UNIPARSER_API_KEY").unwrap_or_default();
            if api_key.is_empty() {
                return Err("UNIPARSER_API_KEY not set".into());
            }
            let client = super::uniparser::UniParserClient::new(&host, &api_key);
            let result = client.parse_pdf(&path)?;
            (result.content, result.page_count, vec![])
        }
        "mineru" => {
            let host =
                std::env::var("MINERU_HOST").unwrap_or_else(|_| "https://mineru.net".to_string());
            let api_key = std::env::var("MINERU_API_KEY").unwrap_or_default();
            let client = super::mineru::MineruClient::new(&host, &api_key);
            let result = client.parse_file(&path)?;
            (result.markdown, 0, vec![])
        }
        "llama_parse" => {
            let pdf_bytes =
                std::fs::read(&path).map_err(|e| format!("Failed to read PDF: {}", e))?;
            let result = super::llama_parse::parse_with_llamaparse_sync(
                "http://127.0.0.1:18792",
                pdf_bytes,
                None,
            )?;
            (result.markdown, result.page_count, vec![])
        }
        _ => {
            let result = pdf_inspector::process_pdf(&path)
                .map_err(|e| format!("pdf-inspector failed: {}", e))?;
            let md = result.markdown.unwrap_or_default();
            (md, result.page_count as usize, vec![])
        }
    };

    // Stage 2: Classification
    let pages: Vec<String> = content.split("\n\n").map(|s| s.to_string()).collect();
    let classification = classify_document(pages, None);

    // Stage 3: Chunking
    let chunks =
        crate::commands::text_ops::text_chunk(content.clone(), chunk_size, overlap).chunks;

    // Stage 4: Molecule extraction (text regex)
    let smiles = extract_smiles_candidates(content.clone());
    let activities = extract_activities(content.clone());

    Ok(PdfParseResult {
        content,
        classification,
        chunks,
        smiles,
        activities,
        parser: parser_choice,
        page_count,
        images: vec![],
    })
}

/// Post-process PDF extraction results using LLM.
#[tauri::command]
pub fn post_process_pdf(
    parse_result: PdfParseResult,
) -> Result<super::post_process::PostProcessResult, String> {
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
    Vlm { image_count: usize, smiles_found: usize },
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
                    super::post_process::UncertainItem {
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
    let mut vlm_smiles_found = 0usize;
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
                crate::parsers::vlm_chem::batch_image_to_smiles(&chem_images, &vlm_config).await;
            vlm_smiles_found = vlm_results.len();
        }

        let _ = app.emit("doc-progress", DocProgressEvent::Vlm {
            image_count: chem_images.len(),
            smiles_found: vlm_smiles_found,
        });
    }

    // ===== Stage 3: 合并 + 验证 + SAR =====
    let final_data: StructuredData;
    let sar_analysis: String;
    {
        if section_results.is_empty() && vlm_results.is_empty() {
            // 无任何结果 → 返回空报告
            final_data = StructuredData {
                metadata: super::post_process::DocumentMetadata {
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

    // 如果 pdf-inspector 提取不到内容，且内容是扫描件 → 自动升到 MinerU
    if md.len() < 100
        && (page_count > 0)
        && std::env::var("MINERU_API_KEY").is_ok()
    {
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

    Ok(ClassifyResult {
        text: md,
        page_count,
        parser: "pdf_inspector".into(),
        images: vec![],
    })
}

/// Stage 1: 调用 LLM 做文档结构分析
async fn run_meta_analysis(ctx: &DocProcessingContext) -> Result<DocStructure, String> {
    let prompt = crate::parsers::intent::build_meta_prompt(ctx);

    let config = load_llm_config_for_doc()?;
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
        .map(|(fname, result)| format!("{}: {} (conf: {:.2})", fname, result.smiles, result.confidence))
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

    let config = load_llm_config_for_doc()?;
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

/// 在 post_process::call_llm_api 暴露后调用
/// 加载 LLM 配置用于文档处理
fn load_llm_config_for_doc() -> Result<crate::parsers::post_process::LlmApiConfig, String> {
    crate::parsers::post_process::load_llm_config()
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
        metadata: metadata.unwrap_or(super::post_process::DocumentMetadata {
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
        use super::super::post_process::{CompoundEntry, DocumentMetadata};
        let r1 = StructuredData {
            metadata: DocumentMetadata { title: None, authors: vec![], document_type: "patent".into(), key_targets: vec![], source_file: None },
            summary: "".into(),
            compounds: vec![CompoundEntry {
                name: "E041".into(), smiles: Some("C1CC1".into()), category: None,
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
                name: "E041".into(), smiles: Some("C1CC1".into()), category: None,
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
}
