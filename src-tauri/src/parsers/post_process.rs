use super::doc_types::{
    ActivityEntry, CompoundEntry, DocumentMetadata, FindingEntry, PdfParseResult,
    PostProcessResult, StructuredData, UncertainItem,
};

// ---------------------------------------------------------------------------
// Internal: LLM API config
// ---------------------------------------------------------------------------

pub struct LlmApiConfig {
    pub base_url: String,
    pub api_key: String,
    pub model: String,
}

/// 从 AppConfig 加载 LLM 配置（统一配置源，不再直接读 env var）。
pub fn load_llm_config() -> Result<LlmApiConfig, String> {
    let app_config = crate::core::config::AppConfig::load();
    let llm = &app_config.llm;

    if llm.api_key.is_empty() {
        // 兼容：如果 config.json 中 api_key 为空，尝试从环境变量读取
        let api_key = std::env::var("MBFORGE_LLM_API_KEY").unwrap_or_default();
        if api_key.is_empty() {
            return Err("LLM API key not configured. Set it in Settings or via MBFORGE_LLM_API_KEY env var.".into());
        }
        return Ok(LlmApiConfig {
            base_url: llm.base_url.clone(),
            api_key,
            model: llm.model_name.clone(),
        });
    }

    Ok(LlmApiConfig {
        base_url: llm.base_url.clone(),
        api_key: llm.api_key.clone(),
        model: llm.model_name.clone(),
    })
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

/// Stage 2 系统提示：分子科学文档分析专家
///
/// 角色定位：从科研文献（专利/论文/报告）提取结构化化合物和活性数据
/// 核心能力：识别化合物名称、验证 SMILES、提取活性数据、理解药物化学术语
/// 质量标准：来源可追溯、数据有效性、单位标准化、置信度诚实
const SYSTEM_PROMPT: &str = r#"你是分子科学文档分析专家，负责从科研文献中提取结构化的化合物和活性数据。

## 你的专长
- 识别化合物名称、代号、实施例编号（如 E041, A-001, Compound 1）
- 验证 SMILES/E-SMILES 化学结构有效性
- 提取定量活性数据（IC50, pIC50, EC50, Ki, 抑制率等）
- 理解药物化学术语（scaffold, SAR, lead, hit, hit-to-lead）

## 质量标准
1. **来源可追溯**: 每个条目必须有 source_ref 或 source_quote
2. **数据有效性**: SMILES 必须可通过 RDKit 解析，无效填 null
3. **单位标准化**: 活性数据使用 nM / μM / % 等标准单位
4. **置信度诚实**: 不确定的数据不要标注 high

## 输出格式
只输出 JSON（不含 report 字段）：
- metadata: title, authors, document_type, key_targets
- summary: 200-400字中文摘要
- compounds/activities/key_findings: 提取的条目列表
- uncertain_items: 无法确认的条目列表
"#;

/// 清理文本中的控制字符（LLM 会原样输出导致 JSON 解析失败）
fn sanitize_text(text: &str) -> String {
    text.chars()
        .filter(|c| !(*c as u32 <= 0x1F && *c != '\n' && *c != '\r' && *c != '\t'))
        .collect()
}

/// Stage 2 Prompt: 单批内容提取
///
/// 输入：文档内容 + 预提取的 SMILES/活性数据候选
/// 任务：识别化合物、验证结构、提取活性数据、标注不确定项
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

    // SMILES 预处理：标记候选数量和来源
    let smiles_section = if smiles.is_empty() {
        "（无预提取 SMILES）".to_string()
    } else {
        format!(
            "共 {} 个候选（需验证有效性）：\n{}",
            smiles.len(),
            smiles
                .iter()
                .take(30)
                .enumerate()
                .map(|(i, s)| format!("{}. {}", i + 1, s))
                .collect::<Vec<_>>()
                .join("\n")
        )
    };

    // 预提取活性数据
    let activities_section = if activities_str.is_empty() {
        "（无预提取活性数据）".to_string()
    } else {
        format!("\n{}", activities_str)
    };

    format!(
        r#"## 任务
分析以下文档内容{batch_info}，提取结构化的化合物和活性数据，输出 JSON。

## 文档信息
- **类型**: {pdf_type}
- **页数**: {page_count}

## 文档内容
```
{content}
```

## 预提取的化学信息
{smiles_section}

## 预提取的活性数据
{activities_section}

---

## 提取规范

### 化合物识别
识别以下类型的化合物：
- 目标化合物：如 "Compound 1", "E041", "A-001"
- 参考化合物：如 "DMSO", "positive control"
- 中间体：如 "intermediate 3"

### SMILES 验证
- 只接受 RDKit 可解析的标准 SMILES
- E-SMILES 格式：`CCO |c:1,t:2|`（含原子电荷和立体化学）
- 无法解析的结构：`"smiles": null`

### 活性数据提取
提取时必须包含：
1. **数值和单位**：如 "IC50 = 5.2 nM"
2. **完整句子**：引用原文，包含数值和单位的完整句子
3. **单位标准化**：优先使用 nM，抑制率使用 %

### 置信度评估
- **high**: 原文明确，数据完整，无歧义
- **medium**: 有部分描述，需要人工确认
- **low**: 推测性结论，数据不完整

---

## 输出格式
**只输出 JSON**，使用以下字段：

```json
{{
  "metadata": {{
    "title": "string | null",
    "authors": ["string"],
    "document_type": "patent | paper | report",
    "key_targets": ["string"],
    "source_file": "string | null"
  }},
  "summary": "200-400字中文摘要",
  "compounds": [
    {{
      "name": "string",
      "smiles": "string | null",
      "category": "lead | hit | reference | intermediate | null",
      "description": "string",
      "source_ref": "p.5 | Table 1 | Example 3",
      "confidence": "high | medium | low",
      "uncertainty_reason": "string | null"
    }}
  ],
  "activities": [
    {{
      "compound": "string",
      "activity_type": "IC50 | pIC50 | EC50 | Ki | Kd | 抑制率",
      "value": number,
      "units": "nM | μM | %",
      "target": "string | null",
      "source_quote": "原文完整句子",
      "source_ref": "p.5 | Table 1",
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
  "uncertain_items": [
    {{
      "item_type": "structure_ambiguous | activity_conflict | missing_data | format_unclear",
      "content": "string",
      "reason": "string",
      "suggested_action": "string"
    }}
  ]
}}
```

**禁止**：report 字段、解释性文字、markdown 代码块标记"#,
        batch_info = batch_info,
        pdf_type = pdf_type,
        page_count = page_count,
        content = sanitize_text(batch_content),
        smiles_section = smiles_section,
        activities_section = activities_section,
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
        r.push_str(&format!(
            "- **作者**: {}\n",
            data.metadata.authors.join(", ")
        ));
    }
    if !data.metadata.key_targets.is_empty() {
        r.push_str(&format!(
            "- **关键靶点**: {}\n",
            data.metadata.key_targets.join(", ")
        ));
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
            let esmiles = c.esmiles.as_deref().unwrap_or("-");
            r.push_str(&format!(
                "| {} | {} | `{}` | {} | {} | {} | {} |\n",
                i + 1,
                c.name,
                esmiles,
                c.category.as_deref().unwrap_or("-"),
                c.description,
                conf,
                c.source_ref
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
                i + 1,
                a.compound,
                a.activity_type,
                a.value,
                a.units,
                a.target.as_deref().unwrap_or("-"),
                conf,
                a.source_ref
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
            r.push_str(&format!(
                "- **[{}]** {} — {} (建议: {})\n",
                u.item_type, u.content, u.reason, u.suggested_action
            ));
        }
        r.push('\n');
    }

    r
}

/// 构建最终合并的 prompt — 将多批结果合并为一份数据
fn build_merge_prompt(batch_results: &[BatchResult], raw: &PdfParseResult) -> String {
    let mut batches_text = String::new();
    for (i, br) in batch_results.iter().enumerate() {
        batches_text.push_str(&format!(
            "--- 第 {} 批结果 ---\n{}\n\n",
            i + 1,
            br.data.summary
        ));
        for c in &br.data.compounds {
            batches_text.push_str(&format!(
                "  化合物: {} ({}) [{}]\n",
                c.name,
                c.esmiles.as_deref().unwrap_or("?"),
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
        title = raw
            .classification
            .metadata_hints
            .as_ref()
            .and_then(|v| v.get("title").and_then(|t| t.as_str()))
            .unwrap_or("未知"),
        page_count = raw.page_count,
        doc_type = if raw.classification.is_scanned {
            "扫描版"
        } else {
            "文字版"
        },
        batches_text = batches_text,
    )
}

// ---------------------------------------------------------------------------
// Batch result (internal)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
struct BatchResult {
    data: StructuredData,
}

// ---------------------------------------------------------------------------
// LLM API call
// ---------------------------------------------------------------------------

/// 构建 LLM 请求体
fn build_llm_body(config: &LlmApiConfig, system: &str, user: &str) -> serde_json::Value {
    serde_json::json!({
        "model": config.model,
        "messages": [
            { "role": "system", "content": system },
            { "role": "user", "content": user }
        ],
        "max_tokens": 8192,
        "temperature": 0.2,
    })
}

/// 解析 LLM 响应文本 → (content, tokens_used)
fn parse_llm_response(text: &str) -> Result<(String, Option<u32>), String> {
    let val: serde_json::Value =
        serde_json::from_str(text).map_err(|e| format!("LLM API JSON parse error: {}", e))?;

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

/// 构建 HTTP 错误消息
fn llm_http_error(status: reqwest::StatusCode, text: &str) -> String {
    format!(
        "LLM API HTTP {}: {}",
        status,
        &text[..text.floor_char_boundary(500)]
    )
}

pub fn call_llm_api(
    config: &LlmApiConfig,
    system: &str,
    user: &str,
) -> Result<(String, Option<u32>), String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(180))
        .build()
        .map_err(|e| format!("HTTP client error: {}", e))?;

    let url = format!("{}/chat/completions", config.base_url.trim_end_matches('/'));
    let body = build_llm_body(config, system, user);

    let resp = client
        .post(&url)
        .header("Content-Type", "application/json")
        .header("Authorization", format!("Bearer {}", config.api_key))
        .json(&body)
        .send()
        .map_err(|e| format!("LLM API request failed: {}", e))?;

    let status = resp.status();
    let text = resp
        .text()
        .map_err(|e| format!("LLM API read error: {}", e))?;

    if !status.is_success() {
        return Err(llm_http_error(status, &text));
    }
    parse_llm_response(&text)
}

/// Async 版本 — 在 async 上下文中使用，不阻塞 Tokio 运行时
pub async fn call_llm_api_async(
    config: &LlmApiConfig,
    system: &str,
    user: &str,
) -> Result<(String, Option<u32>), String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(180))
        .build()
        .map_err(|e| format!("HTTP client error: {}", e))?;

    let url = format!("{}/chat/completions", config.base_url.trim_end_matches('/'));
    let body = build_llm_body(config, system, user);

    let resp = client
        .post(&url)
        .header("Content-Type", "application/json")
        .header("Authorization", format!("Bearer {}", config.api_key))
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("LLM API request failed: {}", e))?;

    let status = resp.status();
    let text = resp
        .text()
        .await
        .map_err(|e| format!("LLM API read error: {}", e))?;

    if !status.is_success() {
        return Err(llm_http_error(status, &text));
    }
    parse_llm_response(&text)
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
    let cleaned: String = after_think
        .chars()
        .filter(|c| !(*c as u32 <= 0x1F && *c != '\n' && *c != '\r' && *c != '\t'))
        .collect();

    let s = cleaned
        .trim()
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
        response.chars().count(),
        preview
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
        if in_string {
            continue;
        }
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
    Ok(BatchResult { data })
}

/// 解析合并响应为最终 PostProcessResult（程序化生成报告）
fn parse_merge_response(
    response: &str,
    model: &str,
    tokens_used: Option<u32>,
    batch_count: usize,
) -> Result<PostProcessResult, String> {
    let val = extract_json(response)?;

    let data_val = val.get("data").unwrap_or(&val);
    let data = parse_structured_data(data_val)?;
    let report = generate_report(&data);

    Ok(PostProcessResult {
        report,
        data,
        model: model.to_string(),
        tokens_used,
        batch_count,
    })
}

pub fn parse_structured_data(val: &serde_json::Value) -> Result<StructuredData, String> {
    let metadata = DocumentMetadata {
        title: val["metadata"]["title"].as_str().map(|s| s.to_string()),
        authors: val["metadata"]["authors"]
            .as_array()
            .map(|a| {
                a.iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default(),
        document_type: val["metadata"]["document_type"]
            .as_str()
            .unwrap_or("unknown")
            .to_string(),
        key_targets: val["metadata"]["key_targets"]
            .as_array()
            .map(|a| {
                a.iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default(),
        source_file: val["metadata"]["source_file"]
            .as_str()
            .map(|s| s.to_string()),
    };

    let summary = val["summary"].as_str().unwrap_or("").to_string();

    let compounds = val["compounds"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .map(|v| CompoundEntry {
                    name: v["name"].as_str().unwrap_or("").to_string(),
                    esmiles: v["smiles"].as_str().map(|s| s.to_string()),
                    category: v["category"].as_str().map(|s| s.to_string()),
                    description: v["description"].as_str().unwrap_or("").to_string(),
                    source_ref: v["source_ref"].as_str().unwrap_or("").to_string(),
                    confidence: v["confidence"].as_str().unwrap_or("medium").to_string(),
                    uncertainty_reason: v["uncertainty_reason"].as_str().map(|s| s.to_string()),
                    physicochemical_props: None,
                    related_images: None,
                    vlm_verified_esmiles: None,
                    page_location: None,
                })
                .collect()
        })
        .unwrap_or_default();

    let activities = val["activities"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .map(|v| ActivityEntry {
                    compound: v["compound"].as_str().unwrap_or("").to_string(),
                    activity_type: v["activity_type"].as_str().unwrap_or("").to_string(),
                    value: v["value"].as_f64().unwrap_or(0.0),
                    units: v["units"].as_str().unwrap_or("").to_string(),
                    target: v["target"].as_str().map(|s| s.to_string()),
                    source_quote: v["source_quote"].as_str().unwrap_or("").to_string(),
                    source_ref: v["source_ref"].as_str().unwrap_or("").to_string(),
                    confidence: v["confidence"].as_str().unwrap_or("medium").to_string(),
                    uncertainty_reason: v["uncertainty_reason"].as_str().map(|s| s.to_string()),
                })
                .collect()
        })
        .unwrap_or_default();

    let key_findings = val["key_findings"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .map(|v| FindingEntry {
                    finding: v["finding"].as_str().unwrap_or("").to_string(),
                    evidence: v["evidence"].as_str().unwrap_or("").to_string(),
                    source_ref: v["source_ref"].as_str().unwrap_or("").to_string(),
                    confidence: v["confidence"].as_str().unwrap_or("medium").to_string(),
                    uncertainty_reason: v["uncertainty_reason"].as_str().map(|s| s.to_string()),
                })
                .collect()
        })
        .unwrap_or_default();

    let uncertain_items = val["uncertain_items"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .map(|v| UncertainItem {
                    item_type: v["item_type"].as_str().unwrap_or("").to_string(),
                    content: v["content"].as_str().unwrap_or("").to_string(),
                    reason: v["reason"].as_str().unwrap_or("").to_string(),
                    suggested_action: v["suggested_action"].as_str().unwrap_or("").to_string(),
                })
                .collect()
        })
        .unwrap_or_default();

    Ok(StructuredData {
        metadata,
        summary,
        compounds,
        activities,
        key_findings,
        uncertain_items,
    })
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
    let activities_str = raw
        .activities
        .iter()
        .take(10)
        .map(|a| format!("{} = {} {}", a.activity_type, a.value, a.units))
        .collect::<Vec<_>>()
        .join("; ");

    let pdf_type = if raw.classification.is_scanned {
        "Scanned"
    } else {
        "TextBased"
    };

    if batch_count == 1 {
        // 单批：直接处理
        let prompt = build_batch_prompt(
            &batches[0],
            0,
            1,
            &raw.esmiles,
            &activities_str,
            pdf_type,
            raw.page_count,
        );
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
            let prompt = build_batch_prompt(
                batch,
                i,
                batch_count,
                &raw.esmiles,
                &activities_str,
                pdf_type,
                raw.page_count,
            );
            let (response, tokens) = call_llm_api(&config, SYSTEM_PROMPT, &prompt)?;
            let br = parse_batch_response(&response)?;
            total_tokens += tokens.unwrap_or(0);
            batch_results.push(br);
        }

        // 合并
        if batch_count > 1 {
            let merge_prompt = build_merge_prompt(&batch_results, raw);
            let (response, tokens) = call_llm_api(&config, SYSTEM_PROMPT, &merge_prompt)?;
            let mut result = parse_merge_response(
                &response,
                &config.model,
                tokens.map(|t| t + total_tokens),
                batch_count,
            )?;
            result.data.metadata.source_file = Some(raw.parser.clone());
            Ok(result)
        } else {
            // 单批：无需 LLM 合并，直接构造 PostProcessResult
            let batch_result = batch_results.into_iter().next()
                .ok_or_else(|| "No batch results in single-batch path".to_string())?;
            let report = generate_report(&batch_result.data);
            let mut data = batch_result.data;
            data.metadata.source_file = Some(raw.parser.clone());
            Ok(PostProcessResult {
                report,
                data,
                model: config.model.clone(),
                tokens_used: Some(total_tokens),
                batch_count: 1,
            })
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
        let merge_prompt =
            build_section_merge_prompt(&batch_results, content, pdf_type, page_count);
        let (response, tokens) = call_llm_api(&config, SYSTEM_PROMPT, &merge_prompt)?;
        let mut result = parse_merge_response(
            &response,
            &config.model,
            tokens.map(|t| t + total_tokens),
            batch_count,
        )?;
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
        batches_text.push_str(&format!(
            "--- 第 {} 批结果 ---\n{}\n\n",
            i + 1,
            br.data.summary
        ));
        for c in &br.data.compounds {
            batches_text.push_str(&format!(
                "  化合物: {} ({}) [{}]\n",
                c.name,
                c.esmiles.as_deref().unwrap_or("?"),
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
