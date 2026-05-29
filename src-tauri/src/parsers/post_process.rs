use serde::{Deserialize, Serialize};

use super::pipeline::PdfParseResult;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/// LLM post-processing result — structured output from the AI organizer.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PostProcessResult {
    /// 200字以内的中文摘要
    pub summary: String,
    /// 按主题整理的结构化内容
    pub structured_content: String,
    /// 验证后的 SMILES 列表 (去假阳性)
    pub validated_smiles: Vec<String>,
    /// 结构化活性数据
    pub activity_records: Vec<ActivityRecord>,
    /// 关键发现
    pub key_findings: Vec<String>,
    /// 文档元信息
    pub metadata: DocumentMetadata,
    /// 使用的模型名称
    pub model: String,
    /// token 使用量 (如果 API 返回)
    pub tokens_used: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityRecord {
    pub compound: String,
    pub activity_type: String,
    pub value: f64,
    pub units: String,
    pub target: Option<String>,
    pub context: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentMetadata {
    pub title: Option<String>,
    pub authors: Vec<String>,
    /// patent, paper, report, review, etc.
    pub document_type: String,
    pub key_compounds: Vec<String>,
    pub key_targets: Vec<String>,
}

// ---------------------------------------------------------------------------
// Internal: LLM API config
// ---------------------------------------------------------------------------

struct LlmApiConfig {
    base_url: String,
    api_key: String,
    model: String,
}

fn load_llm_config() -> Result<LlmApiConfig, String> {
    let base_url = std::env::var("MBFORGE_LLM_BASE_URL")
        .unwrap_or_else(|_| "http://localhost:8000/v1".to_string());
    let api_key = std::env::var("MBFORGE_LLM_API_KEY")
        .unwrap_or_default();
    let model = std::env::var("MBFORGE_LLM_MODEL")
        .unwrap_or_else(|_| "default".to_string());

    if api_key.is_empty() {
        return Err("MBFORGE_LLM_API_KEY not set — cannot call LLM for post-processing".into());
    }

    Ok(LlmApiConfig { base_url, api_key, model })
}

// ---------------------------------------------------------------------------
// Prompt
// ---------------------------------------------------------------------------

fn build_post_process_prompt(raw: &PdfParseResult) -> String {
    // Truncate content to avoid exceeding context window
    let content_preview = if raw.content.len() > 8000 {
        format!("{}... (截断，共 {} 字符)", &raw.content[..8000], raw.content.len())
    } else {
        raw.content.clone()
    };

    let smiles_list = if raw.smiles.is_empty() {
        "无".to_string()
    } else {
        raw.smiles.iter().take(50).cloned().collect::<Vec<_>>().join(", ")
    };

    let activities_list = if raw.activities.is_empty() {
        "无".to_string()
    } else {
        raw.activities.iter().take(20)
            .map(|a| format!("{} = {} {} ({})", a.activity_type, a.value, a.units, &a.context[..a.context.len().min(80)]))
            .collect::<Vec<_>>()
            .join("\n")
    };

    format!(
        r#"你是一个分子科学文档分析专家。请整理以下 PDF 提取结果，输出 JSON。

## 输入内容
{content_preview}

## 已提取的 SMILES 候选 (前50个)
{smiles_list}

## 已提取的活性数据
{activities_list}

## PDF 分类信息
- 文档类型判断: {classification}
- 页数: {page_count}

## 输出要求
请输出以下 JSON 结构（只输出 JSON，不要其他说明文字）：

{{
  "summary": "200字以内的中文摘要，概述文档核心内容、主要化合物和发现",
  "structured_content": "按主题/章节整理的内容，保留关键数据和结论",
  "validated_smiles": ["只保留你认为是真实化学分子的SMILES字符串，过滤掉明显的噪声"],
  "activity_records": [
    {{
      "compound": "化合物名称或SMILES",
      "activity_type": "IC50/EC50/Ki/Kd等",
      "value": 数值,
      "units": "nM/uM/mM等",
      "target": "靶点名称（如果能识别）",
      "context": "来源上下文片段"
    }}
  ],
  "key_findings": ["关键发现1", "关键发现2", "..."],
  "metadata": {{
    "title": "文档标题（如果能识别）",
    "authors": ["作者列表"],
    "document_type": "patent/paper/review/report",
    "key_compounds": ["核心化合物名称或SMILES"],
    "key_targets": ["关键靶点/适应症"]
  }}
}}

注意：
1. validated_smiles 只保留你确信是真实 SMILES 的字符串，宁少勿多
2. activity_records 尽量从上下文中提取完整的 值+单位+靶点 信息
3. 如果信息不足以填写某个字段，用空数组或 null，不要编造"#,
        content_preview = content_preview,
        smiles_list = smiles_list,
        activities_list = activities_list,
        classification = format!("{:?}", raw.classification.is_scanned),
        page_count = raw.page_count,
    )
}

// ---------------------------------------------------------------------------
// LLM API call
// ---------------------------------------------------------------------------

/// Call OpenAI-compatible chat completions endpoint.
fn call_llm_api(config: &LlmApiConfig, prompt: &str) -> Result<(String, Option<u32>), String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .map_err(|e| format!("HTTP client error: {}", e))?;

    let url = format!("{}/chat/completions", config.base_url.trim_end_matches('/'));

    let body = serde_json::json!({
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": "你是分子科学文档分析专家。请严格按照要求输出 JSON 格式的结果，不要添加任何其他说明文字。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 4096,
        "temperature": 0.3,
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
        .as_str()
        .unwrap_or("")
        .to_string();

    let tokens_used = val["usage"]["total_tokens"].as_u64().map(|v| v as u32);

    if content.is_empty() {
        return Err("LLM returned empty content".into());
    }

    Ok((content, tokens_used))
}

// ---------------------------------------------------------------------------
// Response parsing
// ---------------------------------------------------------------------------

/// Parse the LLM JSON response into PostProcessResult.
/// Handles cases where the LLM wraps JSON in markdown code blocks.
fn parse_llm_response(response: &str, model: &str, tokens_used: Option<u32>) -> Result<PostProcessResult, String> {
    // Strip markdown code fences if present
    let json_str = response
        .trim()
        .trim_start_matches("```json")
        .trim_start_matches("```")
        .trim_end_matches("```")
        .trim();

    let val: serde_json::Value = serde_json::from_str(json_str)
        .map_err(|e| format!("Failed to parse LLM JSON response: {}\nResponse preview: {}", e, &response[..response.len().min(300)]))?;

    // Extract fields with defaults for missing ones
    let summary = val["summary"].as_str().unwrap_or("").to_string();
    let structured_content = val["structured_content"].as_str().unwrap_or("").to_string();

    let validated_smiles = val["validated_smiles"].as_array()
        .map(|arr| arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
        .unwrap_or_default();

    let activity_records = val["activity_records"].as_array()
        .map(|arr| {
            arr.iter().filter_map(|v| {
                Some(ActivityRecord {
                    compound: v["compound"].as_str().unwrap_or("").to_string(),
                    activity_type: v["activity_type"].as_str().unwrap_or("").to_string(),
                    value: v["value"].as_f64().unwrap_or(0.0),
                    units: v["units"].as_str().unwrap_or("").to_string(),
                    target: v["target"].as_str().map(|s| s.to_string()),
                    context: v["context"].as_str().unwrap_or("").to_string(),
                })
            }).collect()
        })
        .unwrap_or_default();

    let key_findings = val["key_findings"].as_array()
        .map(|arr| arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
        .unwrap_or_default();

    let metadata = DocumentMetadata {
        title: val["metadata"]["title"].as_str().map(|s| s.to_string()),
        authors: val["metadata"]["authors"].as_array()
            .map(|arr| arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
            .unwrap_or_default(),
        document_type: val["metadata"]["document_type"].as_str().unwrap_or("unknown").to_string(),
        key_compounds: val["metadata"]["key_compounds"].as_array()
            .map(|arr| arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
            .unwrap_or_default(),
        key_targets: val["metadata"]["key_targets"].as_array()
            .map(|arr| arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
            .unwrap_or_default(),
    };

    Ok(PostProcessResult {
        summary,
        structured_content,
        validated_smiles,
        activity_records,
        key_findings,
        metadata,
        model: model.to_string(),
        tokens_used,
    })
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// Post-process PDF extraction results using LLM.
///
/// Takes a `PdfParseResult` (from Stage 0-6) and calls the configured LLM
/// to generate a structured summary, validate SMILES, extract activity data,
/// and identify key findings.
pub fn post_process(raw: &PdfParseResult) -> Result<PostProcessResult, String> {
    let config = load_llm_config()?;
    let prompt = build_post_process_prompt(raw);

    let (response, tokens_used) = call_llm_api(&config, &prompt)?;

    parse_llm_response(&response, &config.model, tokens_used)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_load_llm_config() {
        // This test verifies the function doesn't panic
        // It will return Err if env vars aren't set, which is fine
        let _ = load_llm_config();
    }

    #[test]
    fn test_parse_llm_response_json() {
        let response = "\
{\
\"summary\": \"test summary\",\
\"structured_content\": \"test content\",\
\"validated_smiles\": [\"C1CC1\", \"C(=O)O\"],\
\"activity_records\": [{\
\"compound\": \"test\",\
\"activity_type\": \"IC50\",\
\"value\": 5.2,\
\"units\": \"nM\",\
\"target\": \"JAK1\",\
\"context\": \"IC50 = 5.2 nM\"\
}],\
\"key_findings\": [\"finding1\"],\
\"metadata\": {\
\"title\": \"test title\",\
\"authors\": [\"author1\"],\
\"document_type\": \"patent\",\
\"key_compounds\": [\"C1CC1\"],\
\"key_targets\": [\"JAK1\"]\
}\
}";

        let result = parse_llm_response(response, "test-model", Some(100)).unwrap();
        assert_eq!(result.summary, "test summary");
        assert_eq!(result.validated_smiles.len(), 2);
        assert_eq!(result.activity_records.len(), 1);
        assert_eq!(result.activity_records[0].value, 5.2);
        assert_eq!(result.key_findings.len(), 1);
        assert_eq!(result.metadata.document_type, "patent");
        assert_eq!(result.model, "test-model");
        assert_eq!(result.tokens_used, Some(100));
    }

    #[test]
    fn test_parse_llm_response_with_code_fences() {
        let response = "```json\n\
{\"summary\": \"test\", \"structured_content\": \"\", \"validated_smiles\": [], \"activity_records\": [], \"key_findings\": [], \"metadata\": {\"title\": null, \"authors\": [], \"document_type\": \"paper\", \"key_compounds\": [], \"key_targets\": []}}\n\
```";

        let result = parse_llm_response(response, "test", None).unwrap();
        assert_eq!(result.summary, "test");
    }

    #[test]
    fn test_build_prompt_truncation() {
        let raw = PdfParseResult {
            content: "x".repeat(10000),
            classification: crate::commands::classifier::DocumentClassification {
                text_density: 100.0,
                is_scanned: false,
                has_molecular_patterns: true,
                metadata_hints: None,
                pages: vec![],
                needs_confirmation: false,
            },
            chunks: vec!["chunk1".into()],
            smiles: vec!["C1CC1".into()],
            activities: vec![],
            parser: "pdf_inspector".into(),
            page_count: 10,
        };

        let prompt = build_post_process_prompt(&raw);
        // Content should be truncated to ~8000 chars + suffix
        assert!(prompt.len() < 12000, "Prompt too long: {}", prompt.len());
        assert!(prompt.contains("截断"));
    }
}
