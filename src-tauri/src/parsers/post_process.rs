use serde::{Deserialize, Serialize};

use super::pipeline::PdfParseResult;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/// LLM 后处理结果 — 结构化报告 + 机器可读数据
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PostProcessResult {
    /// 完整的 Markdown 格式报告（人类可读）
    pub report: String,
    /// 结构化数据（机器可读）
    pub data: StructuredData,
    /// 使用的模型
    pub model: String,
    /// token 使用量
    pub tokens_used: Option<u32>,
    /// 分批处理的批次数
    pub batch_count: usize,
}

/// 结构化数据 — 与报告一一对应
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StructuredData {
    pub metadata: DocumentMetadata,
    pub summary: String,
    pub compounds: Vec<CompoundEntry>,
    pub activities: Vec<ActivityEntry>,
    pub key_findings: Vec<FindingEntry>,
    pub uncertain_items: Vec<UncertainItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentMetadata {
    pub title: Option<String>,
    pub authors: Vec<String>,
    pub document_type: String,
    pub key_targets: Vec<String>,
    pub source_file: Option<String>,
}

/// 化合物条目 — 带溯源和置信度
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompoundEntry {
    /// 化合物名称
    pub name: String,
    /// SMILES 字符串（如果能确认）
    pub smiles: Option<String>,
    /// 所属类别（如 JAK inhibitor, MRGPRX2 antagonist）
    pub category: Option<String>,
    /// 关键描述
    pub description: String,
    /// 在原文中的位置引用（页码或段落）
    pub source_ref: String,
    /// 置信度: high / medium / low
    pub confidence: String,
    /// 不确定的原因（仅当 confidence != high 时）
    pub uncertainty_reason: Option<String>,
}

/// 活性数据条目 — 带溯源
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityEntry {
    /// 化合物（名称或 SMILES）
    pub compound: String,
    /// 活性类型
    pub activity_type: String,
    /// 数值
    pub value: f64,
    /// 单位
    pub units: String,
    /// 靶点
    pub target: Option<String>,
    /// 原文上下文（精确引用）
    pub source_quote: String,
    /// 来源页码/段落
    pub source_ref: String,
    pub confidence: String,
    pub uncertainty_reason: Option<String>,
}

/// 关键发现条目 — 带溯源
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FindingEntry {
    /// 发现内容
    pub finding: String,
    /// 支撑证据（原文引用）
    pub evidence: String,
    /// 来源
    pub source_ref: String,
    pub confidence: String,
    pub uncertainty_reason: Option<String>,
}

/// 不确定项 — 需要人工审核的条目
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UncertainItem {
    /// 项目类型: compound / activity / finding / classification
    pub item_type: String,
    /// 内容描述
    pub content: String,
    /// 不确定的原因
    pub reason: String,
    /// 建议的审核动作
    pub suggested_action: String,
}

// ---------------------------------------------------------------------------
// Internal: LLM API config
// ---------------------------------------------------------------------------

pub struct LlmApiConfig {
    pub base_url: String,
    pub api_key: String,
    pub model: String,
}

pub fn load_llm_config() -> Result<LlmApiConfig, String> {
    let base_url = std::env::var("MBFORGE_LLM_BASE_URL")
        .unwrap_or_else(|_| "http://localhost:8000/v1".to_string());
    let api_key = std::env::var("MBFORGE_LLM_API_KEY")
        .unwrap_or_default();
    let model = std::env::var("MBFORGE_LLM_MODEL")
        .unwrap_or_else(|_| "default".to_string());

    if api_key.is_empty() {
        return Err("MBFORGE_LLM_API_KEY not set".into());
    }

    Ok(LlmApiConfig { base_url, api_key, model })
}

// ---------------------------------------------------------------------------
// Batch splitting
// ---------------------------------------------------------------------------

/// 每批最大字符数（留出 prompt 和输出的空间）
const BATCH_MAX_CHARS: usize = 6000;

/// 将 content 按段落分割为多批，每批不超过 BATCH_MAX_CHARS
fn split_into_batches(content: &str) -> Vec<String> {
    if content.len() <= BATCH_MAX_CHARS {
        return vec![content.to_string()];
    }

    let mut batches = Vec::new();
    let mut current = String::new();

    // 按双换行（段落）分割
    for paragraph in content.split("\n\n") {
        if current.len() + paragraph.len() + 2 > BATCH_MAX_CHARS {
            if !current.is_empty() {
                batches.push(current.clone());
                current.clear();
            }
            // 如果单个段落超长，强制截断
            if paragraph.len() > BATCH_MAX_CHARS {
                for chunk in paragraph.as_bytes().chunks(BATCH_MAX_CHARS) {
                    batches.push(String::from_utf8_lossy(chunk).to_string());
                }
                continue;
            }
        }
        if !current.is_empty() {
            current.push_str("\n\n");
        }
        current.push_str(paragraph);
    }

    if !current.is_empty() {
        batches.push(current);
    }

    batches
}

// ---------------------------------------------------------------------------
// Prompt design — 核心
// ---------------------------------------------------------------------------

/// 系统提示 — 定义角色和输出格式（仅输出结构化数据，不包含报告）
const SYSTEM_PROMPT: &str = r#"你是分子科学文档分析专家。你的任务是从 PDF 提取结果中整理出结构化数据。

## 核心原则
1. **一一对应**: 每个化合物、活性数据、发现都必须标注原文出处（引用原文段落或页码）
2. **宁缺毋滥**: 不确定的信息宁可不提取，也不要编造
3. **置信度标注**: 每个条目标注 high/medium/low，low 的必须说明原因
4. **不确定项收集**: 把所有你无法确认的条目放入 uncertain_items，供人工审核

## 输出格式
严格输出以下 JSON，不要其他文字：

{
  "metadata": { "title": "文档标题", "authors": ["作者"], "document_type": "patent/paper", "key_targets": ["靶点"] },
  "summary": "200-400字中文摘要",
  "compounds": [{ "name": "名称", "smiles": "SMILES或null", "category": "类别", "description": "描述", "source_ref": "原文出处", "confidence": "high/medium/low", "uncertainty_reason": "仅low时" }],
  "activities": [{ "compound": "化合物", "activity_type": "IC50等", "value": 0.0, "units": "nM", "target": "靶点", "source_quote": "原文精确引用", "source_ref": "出处", "confidence": "high/medium/low", "uncertainty_reason": "仅low时" }],
  "key_findings": [{ "finding": "发现", "evidence": "证据", "source_ref": "出处", "confidence": "high/medium/low", "uncertainty_reason": "仅low时" }],
  "uncertain_items": [{ "item_type": "compound/activity/finding", "content": "内容", "reason": "原因", "suggested_action": "建议" }]
}

注意：只输出 JSON，不要添加 report 或其他字段。"#;

/// 清理文本中的控制字符（LLM 会原样输出导致 JSON 解析失败）
fn sanitize_text(text: &str) -> String {
    text.chars()
        .filter(|c| !(*c as u32 <= 0x1F && *c != '\n' && *c != '\r' && *c != '\t'))
        .collect()
}

/// 构建单批处理的 prompt
fn build_batch_prompt(
    batch_content: &str,
    batch_index: usize,
    total_batches: usize,
    smiles: &[String],
    activities_str: &str,
    pdf_type: &str,
    page_count: usize,
) -> String {
    let batch_info = if total_batches > 1 {
        format!("（第 {}/{} 批）", batch_index + 1, total_batches)
    } else {
        String::new()
    };

    let smiles_section = if smiles.is_empty() {
        "无候选".to_string()
    } else {
        // 只取前 30 个，避免 prompt 过长
        smiles.iter().take(30).enumerate()
            .map(|(i, s)| format!("{}. {}", i + 1, s))
            .collect::<Vec<_>>()
            .join("\n")
    };

    format!(
        r#"请分析以下 PDF 提取内容{batch_info}，输出结构化 JSON。

## PDF 基本信息
- 类型: {pdf_type}
- 页数: {page_count}

## 提取的文本内容
---
{content}
---

## 正则提取的 SMILES 候选（前30个，需验证真伪）
{smiles_section}

## 正则提取的活性数据
{activities}

## 分析要求
1. 仔细阅读文本，识别所有化合物（药物、中间体、参考化合物）
2. 验证 SMILES 候选：只有你确信是真实化学结构的才放入 compounds.smiles
3. 提取活性数据时，必须引用原文中包含数值和单位的完整句子
4. 对每个条目标注置信度，low 的说明原因
5. 把无法确认的条目放入 uncertain_items
6. 生成完整的 Markdown report

注意：
- report 字段必须是完整的 Markdown 文本
- 只输出 JSON，不要其他说明
- 如果这批内容没有有价值的信息，返回空的数组即可"#,
        batch_info = batch_info,
        pdf_type = pdf_type,
        page_count = page_count,
        content = sanitize_text(batch_content),
        smiles_section = smiles_section,
        activities = if activities_str.is_empty() { "无".to_string() } else { activities_str.to_string() },
    )
}

/// 从 StructuredData 生成 Markdown 报告（程序化生成，不依赖 LLM）
pub fn generate_report(data: &StructuredData) -> String {
    let mut r = String::new();

    // Title
    let title = data.metadata.title.as_deref().unwrap_or("未知文档");
    r.push_str(&format!("# {}\n\n", title));

    // Metadata
    r.push_str("## 文档信息\n\n");
    r.push_str(&format!("- **类型**: {}\n", data.metadata.document_type));
    if !data.metadata.authors.is_empty() {
        r.push_str(&format!("- **作者**: {}\n", data.metadata.authors.join(", ")));
    }
    if !data.metadata.key_targets.is_empty() {
        r.push_str(&format!("- **关键靶点**: {}\n", data.metadata.key_targets.join(", ")));
    }
    r.push('\n');

    // Summary
    r.push_str("## 摘要\n\n");
    r.push_str(&data.summary);
    r.push_str("\n\n");

    // Compounds
    if !data.compounds.is_empty() {
        r.push_str("## 化合物清单\n\n");
        r.push_str("| # | 名称 | SMILES | 类别 | 描述 | 置信度 | 出处 |\n");
        r.push_str("|---|------|--------|------|------|--------|------|\n");
        for (i, c) in data.compounds.iter().enumerate() {
            let conf = match c.confidence.as_str() {
                "high" => "✅",
                "medium" => "⚠️",
                _ => "❌",
            };
            let smiles = c.smiles.as_deref().unwrap_or("-");
            r.push_str(&format!(
                "| {} | {} | `{}` | {} | {} | {} | {} |\n",
                i + 1, c.name, smiles, c.category.as_deref().unwrap_or("-"),
                c.description, conf, c.source_ref
            ));
        }
        r.push('\n');
    }

    // Activities
    if !data.activities.is_empty() {
        r.push_str("## 活性数据\n\n");
        r.push_str("| # | 化合物 | 类型 | 值 | 单位 | 靶点 | 置信度 | 出处 |\n");
        r.push_str("|---|--------|------|-----|------|------|--------|------|\n");
        for (i, a) in data.activities.iter().enumerate() {
            let conf = match a.confidence.as_str() {
                "high" => "✅",
                "medium" => "⚠️",
                _ => "❌",
            };
            r.push_str(&format!(
                "| {} | {} | {} | {} | {} | {} | {} | {} |\n",
                i + 1, a.compound, a.activity_type, a.value, a.units,
                a.target.as_deref().unwrap_or("-"), conf, a.source_ref
            ));
        }
        r.push('\n');
    }

    // Key Findings
    if !data.key_findings.is_empty() {
        r.push_str("## 关键发现\n\n");
        for (i, f) in data.key_findings.iter().enumerate() {
            let conf = match f.confidence.as_str() {
                "high" => "✅",
                "medium" => "⚠️",
                _ => "❌",
            };
            r.push_str(&format!("{}. **[{}]** {}\n", i + 1, conf, f.finding));
            if !f.evidence.is_empty() {
                r.push_str(&format!("   > 原文引用: \"{}\"\n", f.evidence));
            }
            r.push_str(&format!("   > 来源: {}\n\n", f.source_ref));
        }
    }

    // Uncertain items
    if !data.uncertain_items.is_empty() {
        r.push_str("## ⚠️ 需要人工审核\n\n");
        for u in &data.uncertain_items {
            r.push_str(&format!("- **[{}]** {} — {} (建议: {})\n",
                u.item_type, u.content, u.reason, u.suggested_action));
        }
        r.push('\n');
    }

    r
}

/// 构建最终合并的 prompt — 将多批结果合并为一份数据
fn build_merge_prompt(batch_results: &[BatchResult], raw: &PdfParseResult) -> String {
    let mut batches_text = String::new();
    for (i, br) in batch_results.iter().enumerate() {
        batches_text.push_str(&format!("--- 第 {} 批结果 ---\n{}\n\n", i + 1, br.data.summary));
        for c in &br.data.compounds {
            batches_text.push_str(&format!("  化合物: {} ({}) [{}]\n", c.name, c.smiles.as_deref().unwrap_or("?"), c.confidence));
        }
        for a in &br.data.activities {
            batches_text.push_str(&format!("  活性: {} {} = {} {} [{}]\n", a.compound, a.activity_type, a.value, a.units, a.confidence));
        }
        for f in &br.data.key_findings {
            batches_text.push_str(&format!("  发现: {} [{}]\n", f.finding, f.confidence));
        }
        for u in &br.data.uncertain_items {
            batches_text.push_str(&format!("  ⚠️ {}: {} — {}\n", u.item_type, u.content, u.reason));
        }
    }

    format!(
        r#"请将以下分批分析结果合并为一份完整的结构化报告。

## 原始文档信息
- 标题: {title}
- 页数: {page_count}
- 类型: {doc_type}

## 各批分析结果
{batches_text}

## 合并要求
1. 去重：相同化合物/活性数据只保留一条
2. 合并：将各批的发现整合为完整列表
3. 汇总：生成 200-400 字的中文摘要
4. 不确定项：汇总所有批次的 uncertain_items
5. 只输出 JSON（metadata + summary + compounds + activities + key_findings + uncertain_items），不要其他字段
只输出 JSON。"#,
        title = raw.classification.metadata_hints.as_ref()
            .and_then(|v| v.get("title").and_then(|t| t.as_str()))
            .unwrap_or("未知"),
        page_count = raw.page_count,
        doc_type = if raw.classification.is_scanned { "扫描版" } else { "文字版" },
        batches_text = batches_text,
    )
}

// ---------------------------------------------------------------------------
// Batch result (internal)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
struct BatchResult {
    data: StructuredData,
    tokens_used: Option<u32>,
}

// ---------------------------------------------------------------------------
// LLM API call
// ---------------------------------------------------------------------------

pub fn call_llm_api(config: &LlmApiConfig, system: &str, user: &str) -> Result<(String, Option<u32>), String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(180))
        .build()
        .map_err(|e| format!("HTTP client error: {}", e))?;

    let url = format!("{}/chat/completions", config.base_url.trim_end_matches('/'));

    let body = serde_json::json!({
        "model": config.model,
        "messages": [
            { "role": "system", "content": system },
            { "role": "user", "content": user }
        ],
        "max_tokens": 8192,
        "temperature": 0.2,
    });

    let resp = client.post(&url)
        .header("Content-Type", "application/json")
        .header("Authorization", format!("Bearer {}", config.api_key))
        .json(&body)
        .send()
        .map_err(|e| format!("LLM API request failed: {}", e))?;

    let status = resp.status();
    let text = resp.text().map_err(|e| format!("LLM API read error: {}", e))?;

    if !status.is_success() {
        return Err(format!("LLM API HTTP {}: {}", status, &text[..text.len().min(500)]));
    }

    let val: serde_json::Value = serde_json::from_str(&text)
        .map_err(|e| format!("LLM API JSON parse error: {}", e))?;

    let content = val["choices"][0]["message"]["content"]
        .as_str().unwrap_or("").to_string();

    let tokens_used = val["usage"]["total_tokens"].as_u64().map(|v| v as u32);

    if content.is_empty() {
        return Err("LLM returned empty content".into());
    }

    Ok((content, tokens_used))
}

// ---------------------------------------------------------------------------
// Response parsing
// ---------------------------------------------------------------------------

/// 从 LLM 响应中提取 JSON（处理 think blocks、code fences、控制字符、截断等）
pub fn extract_json(response: &str) -> Result<serde_json::Value, String> {
    // Strip <think>...</think>
    let after_think = if let Some(end) = response.rfind("</think>") {
        &response[end + 9..]
    } else {
        response
    };

    // Remove control characters (except \n, \r, \t) that break JSON parsing
    let cleaned: String = after_think.chars()
        .filter(|c| !(*c as u32 <= 0x1F && *c != '\n' && *c != '\r' && *c != '\t'))
        .collect();

    let s = cleaned.trim()
        .trim_start_matches("```json")
        .trim_start_matches("```")
        .trim_end_matches("```")
        .trim();

    let s = if !s.starts_with('{') {
        s.find('{').map(|i| &s[i..]).unwrap_or(s)
    } else {
        s
    };

    // Try direct parse first
    if let Ok(val) = serde_json::from_str::<serde_json::Value>(s) {
        return Ok(val);
    }

    // Attempt repair: try to fix truncated JSON by closing open brackets
    let repaired = repair_truncated_json(s);
    if let Ok(val) = serde_json::from_str::<serde_json::Value>(&repaired) {
        return Ok(val);
    }

    // Last resort: try to extract individual fields from the text
    let preview: String = response.chars().take(100).collect();
    Err(format!(
        "JSON parse error (after repair attempt)\nResponse length: {} chars\nPreview: {}",
        response.chars().count(), preview
    ))
}

/// 修复被截断的 JSON — 补全未关闭的括号和引号
fn repair_truncated_json(s: &str) -> String {
    let mut result = s.to_string();

    // Count open braces and brackets
    let mut brace_count = 0i32;
    let mut bracket_count = 0i32;
    let mut in_string = false;
    let mut escaped = false;

    for c in s.chars() {
        if escaped {
            escaped = false;
            continue;
        }
        if c == '\\' && in_string {
            escaped = true;
            continue;
        }
        if c == '"' {
            in_string = !in_string;
            continue;
        }
        if in_string { continue; }
        match c {
            '{' => brace_count += 1,
            '}' => brace_count -= 1,
            '[' => bracket_count += 1,
            ']' => bracket_count -= 1,
            _ => {}
        }
    }

    // If we're inside a string, close it
    if in_string {
        result.push('"');
    }

    // Close any open brackets (innermost first)
    for _ in 0..bracket_count {
        result.push(']');
    }
    for _ in 0..brace_count {
        result.push('}');
    }

    result
}

/// 解析单批 LLM 响应为 BatchResult
fn parse_batch_response(response: &str) -> Result<BatchResult, String> {
    let val = extract_json(response)?;
    // Support both flat format and { "data": {...} } wrapper
    let data_val = val.get("data").unwrap_or(&val);
    let data = parse_structured_data(data_val)?;
    Ok(BatchResult { data, tokens_used: None })
}

/// 解析合并响应为最终 PostProcessResult（程序化生成报告）
fn parse_merge_response(response: &str, model: &str, tokens_used: Option<u32>, batch_count: usize) -> Result<PostProcessResult, String> {
    let val = extract_json(response)?;

    let data_val = val.get("data").unwrap_or(&val);
    let data = parse_structured_data(data_val)?;
    let report = generate_report(&data);

    Ok(PostProcessResult { report, data, model: model.to_string(), tokens_used, batch_count })
}

pub fn parse_structured_data(val: &serde_json::Value) -> Result<StructuredData, String> {
    let metadata = DocumentMetadata {
        title: val["metadata"]["title"].as_str().map(|s| s.to_string()),
        authors: val["metadata"]["authors"].as_array()
            .map(|a| a.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
            .unwrap_or_default(),
        document_type: val["metadata"]["document_type"].as_str().unwrap_or("unknown").to_string(),
        key_targets: val["metadata"]["key_targets"].as_array()
            .map(|a| a.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
            .unwrap_or_default(),
        source_file: val["metadata"]["source_file"].as_str().map(|s| s.to_string()),
    };

    let summary = val["summary"].as_str().unwrap_or("").to_string();

    let compounds = val["compounds"].as_array()
        .map(|arr| arr.iter().map(|v| CompoundEntry {
            name: v["name"].as_str().unwrap_or("").to_string(),
            smiles: v["smiles"].as_str().map(|s| s.to_string()),
            category: v["category"].as_str().map(|s| s.to_string()),
            description: v["description"].as_str().unwrap_or("").to_string(),
            source_ref: v["source_ref"].as_str().unwrap_or("").to_string(),
            confidence: v["confidence"].as_str().unwrap_or("medium").to_string(),
            uncertainty_reason: v["uncertainty_reason"].as_str().map(|s| s.to_string()),
        }).collect())
        .unwrap_or_default();

    let activities = val["activities"].as_array()
        .map(|arr| arr.iter().map(|v| ActivityEntry {
            compound: v["compound"].as_str().unwrap_or("").to_string(),
            activity_type: v["activity_type"].as_str().unwrap_or("").to_string(),
            value: v["value"].as_f64().unwrap_or(0.0),
            units: v["units"].as_str().unwrap_or("").to_string(),
            target: v["target"].as_str().map(|s| s.to_string()),
            source_quote: v["source_quote"].as_str().unwrap_or("").to_string(),
            source_ref: v["source_ref"].as_str().unwrap_or("").to_string(),
            confidence: v["confidence"].as_str().unwrap_or("medium").to_string(),
            uncertainty_reason: v["uncertainty_reason"].as_str().map(|s| s.to_string()),
        }).collect())
        .unwrap_or_default();

    let key_findings = val["key_findings"].as_array()
        .map(|arr| arr.iter().map(|v| FindingEntry {
            finding: v["finding"].as_str().unwrap_or("").to_string(),
            evidence: v["evidence"].as_str().unwrap_or("").to_string(),
            source_ref: v["source_ref"].as_str().unwrap_or("").to_string(),
            confidence: v["confidence"].as_str().unwrap_or("medium").to_string(),
            uncertainty_reason: v["uncertainty_reason"].as_str().map(|s| s.to_string()),
        }).collect())
        .unwrap_or_default();

    let uncertain_items = val["uncertain_items"].as_array()
        .map(|arr| arr.iter().map(|v| UncertainItem {
            item_type: v["item_type"].as_str().unwrap_or("").to_string(),
            content: v["content"].as_str().unwrap_or("").to_string(),
            reason: v["reason"].as_str().unwrap_or("").to_string(),
            suggested_action: v["suggested_action"].as_str().unwrap_or("").to_string(),
        }).collect())
        .unwrap_or_default();

    Ok(StructuredData { metadata, summary, compounds, activities, key_findings, uncertain_items })
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// Post-process PDF extraction results using LLM — 分批处理 + 合并
pub fn post_process(raw: &PdfParseResult) -> Result<PostProcessResult, String> {
    let config = load_llm_config()?;

    // 分批
    let batches = split_into_batches(&raw.content);
    let batch_count = batches.len();
    let activities_str = raw.activities.iter()
        .take(10)
        .map(|a| format!("{} = {} {}", a.activity_type, a.value, a.units))
        .collect::<Vec<_>>()
        .join("; ");

    let pdf_type = if raw.classification.is_scanned { "Scanned" } else { "TextBased" };

    if batch_count == 1 {
        // 单批：直接处理
        let prompt = build_batch_prompt(&batches[0], 0, 1, &raw.smiles, &activities_str, pdf_type, raw.page_count);
        let (response, tokens) = call_llm_api(&config, SYSTEM_PROMPT, &prompt)?;
        let val = extract_json(&response)?;
        let data = parse_structured_data(&val)?;
        let report = generate_report(&data);
        Ok(PostProcessResult {
            report,
            data,
            model: config.model,
            tokens_used: tokens,
            batch_count: 1,
        })
    } else {
        // 多批：逐批处理，最后合并
        let mut batch_results = Vec::new();
        let mut total_tokens = 0u32;

        for (i, batch) in batches.iter().enumerate() {
            let prompt = build_batch_prompt(batch, i, batch_count, &raw.smiles, &activities_str, pdf_type, raw.page_count);
            let (response, tokens) = call_llm_api(&config, SYSTEM_PROMPT, &prompt)?;
            let br = parse_batch_response(&response)?;
            total_tokens += tokens.unwrap_or(0);
            batch_results.push(br);
        }

        // 合并
        if batch_count > 1 {
            let merge_prompt = build_merge_prompt(&batch_results, raw);
            let (response, tokens) = call_llm_api(&config, SYSTEM_PROMPT, &merge_prompt)?;
            let mut result = parse_merge_response(&response, &config.model, tokens.map(|t| t + total_tokens), batch_count)?;
            result.data.metadata.source_file = Some(raw.parser.clone());
            Ok(result)
        } else {
            unreachable!()
        }
    }
}

/// 简化的 section 后处理 — 适用于 Doc Agent 的单段处理
///
/// 与 `post_process()` 的区别：
/// - 不接受整个 PdfParseResult，只接受 text content
/// - 不依赖 PdfParseResult 的 classification/smiles/activities/chunks 字段
/// - 直接用全量 content 跑单批 LLM 提取
pub async fn post_process_section(
    content: &str,
    parser: &str,
    page_count: usize,
) -> Result<PostProcessResult, String> {
    let config = load_llm_config()?;
    let batches = split_into_batches(content);
    let batch_count = batches.len();
    let pdf_type = parser;

    if batch_count == 1 {
        let prompt = build_batch_prompt(&batches[0], 0, 1, &[], "", pdf_type, page_count);
        let (response, tokens) = call_llm_api(&config, SYSTEM_PROMPT, &prompt)?;
        let val = extract_json(&response)?;
        let data = parse_structured_data(&val)?;
        let report = generate_report(&data);
        Ok(PostProcessResult {
            report,
            data,
            model: config.model,
            tokens_used: tokens,
            batch_count: 1,
        })
    } else {
        let mut batch_results = Vec::new();
        let mut total_tokens = 0u32;
        for (i, batch) in batches.iter().enumerate() {
            let prompt = build_batch_prompt(batch, i, batch_count, &[], "", pdf_type, page_count);
            let (response, tokens) = call_llm_api(&config, SYSTEM_PROMPT, &prompt)?;
            let br = parse_batch_response(&response)?;
            total_tokens += tokens.unwrap_or(0);
            batch_results.push(br);
        }
        let merge_prompt = build_section_merge_prompt(&batch_results, content, pdf_type, page_count);
        let (response, tokens) = call_llm_api(&config, SYSTEM_PROMPT, &merge_prompt)?;
        let mut result =
            parse_merge_response(&response, &config.model, tokens.map(|t| t + total_tokens), batch_count)?;
        result.data.metadata.source_file = Some(parser.to_string());
        Ok(result)
    }
}

/// 构建合并 prompt（接受纯文本 content，用于 post_process_section）
fn build_section_merge_prompt(
    batch_results: &[BatchResult],
    _content: &str,
    pdf_type: &str,
    page_count: usize,
) -> String {
    let mut batches_text = String::new();
    for (i, br) in batch_results.iter().enumerate() {
        batches_text.push_str(&format!("--- 第 {} 批结果 ---\n{}\n\n", i + 1, br.data.summary));
        for c in &br.data.compounds {
            batches_text.push_str(&format!(
                "  化合物: {} ({}) [{}]\n",
                c.name,
                c.smiles.as_deref().unwrap_or("?"),
                c.confidence
            ));
        }
        for a in &br.data.activities {
            batches_text.push_str(&format!(
                "  活性: {} {} = {} {} [{}]\n",
                a.compound, a.activity_type, a.value, a.units, a.confidence
            ));
        }
        for f in &br.data.key_findings {
            batches_text.push_str(&format!("  发现: {} [{}]\n", f.finding, f.confidence));
        }
        for u in &br.data.uncertain_items {
            batches_text.push_str(&format!(
                "  ⚠️ {}: {} — {}\n",
                u.item_type, u.content, u.reason
            ));
        }
    }

    format!(
        r#"请将以下分批分析结果合并为一份完整的结构化报告。

## 原始文档信息
- 页数: {page_count}
- 类型: {pdf_type}

## 各批分析结果
{batches_text}

## 合并要求
1. 去重：相同化合物/活性数据只保留一条
2. 合并：将各批的发现整合为完整列表
3. 汇总：生成 200-400 字的中文摘要
4. 不确定项：汇总所有批次的 uncertain_items
5. 只输出 JSON（metadata + summary + compounds + activities + key_findings + uncertain_items），不要其他字段
只输出 JSON。"#,
        page_count = page_count,
        pdf_type = pdf_type,
        batches_text = batches_text,
    )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_split_into_batches_short() {
        let content = "Short content.";
        let batches = split_into_batches(content);
        assert_eq!(batches.len(), 1);
        assert_eq!(batches[0], content);
    }

    #[test]
    fn test_split_into_batches_long() {
        let content = "Paragraph one.\n\n".repeat(500); // ~7500 chars
        let batches = split_into_batches(&content);
        assert!(batches.len() > 1);
        for b in &batches {
            assert!(b.len() <= BATCH_MAX_CHARS + 100); // small margin for paragraph boundary
        }
    }

    #[test]
    fn test_extract_json_clean() {
        let resp = "{\"report\": \"test report\", \"data\": {\"summary\": \"ok\"}}";
        let val = extract_json(resp).unwrap();
        assert_eq!(val["data"]["summary"], "ok");
    }

    #[test]
    fn test_extract_json_with_think() {
        let resp = "<think>reasoning\n</think>\n{\"report\": \"test\", \"data\": {\"summary\": \"result\"}}";
        let val = extract_json(resp).unwrap();
        assert_eq!(val["data"]["summary"], "result");
    }

    #[test]
    fn test_extract_json_with_code_fence() {
        let resp = "```json\n{\"report\": \"test\", \"data\": {\"summary\": \"fenced\"}}\n```";
        let val = extract_json(resp).unwrap();
        assert_eq!(val["data"]["summary"], "fenced");
    }

    #[test]
    fn test_parse_batch_response_full() {
        let resp = "\
{\"report\": \"Test Report\", \"data\": {\"metadata\": {\"title\": \"Test\", \"authors\": [\"A\"], \"document_type\": \"paper\", \"key_targets\": [\"T1\"]}, \"summary\": \"Test summary\", \"compounds\": [{\"name\": \"C1\", \"smiles\": \"C1CC1\", \"category\": \"inhibitor\", \"description\": \"desc\", \"source_ref\": \"p.5\", \"confidence\": \"high\", \"uncertainty_reason\": null}], \"activities\": [{\"compound\": \"C1\", \"activity_type\": \"IC50\", \"value\": 5.0, \"units\": \"nM\", \"target\": \"T1\", \"source_quote\": \"IC50 = 5 nM\", \"source_ref\": \"p.5\", \"confidence\": \"high\", \"uncertainty_reason\": null}], \"key_findings\": [{\"finding\": \"f1\", \"evidence\": \"e1\", \"source_ref\": \"p.5\", \"confidence\": \"medium\", \"uncertainty_reason\": \"partial data\"}], \"uncertain_items\": [{\"item_type\": \"compound\", \"content\": \"C2?\", \"reason\": \"unclear structure\", \"suggested_action\": \"verify with RDKit\"}]}}";
        let result = parse_batch_response(resp).unwrap();
        assert_eq!(result.data.compounds.len(), 1);
        assert_eq!(result.data.activities[0].value, 5.0);
        assert_eq!(result.data.uncertain_items[0].item_type, "compound");
    }
}
