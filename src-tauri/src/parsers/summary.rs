/// LLM 摘要生成 — 替代 Python DocumentSummarizer
///
/// 生成 L0（一句话）和 L1（结构化概览）摘要。

use serde::{Deserialize, Serialize};

use super::keywords::extract_keywords;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentSummary {
    pub l0_abstract: String,
    pub l1_overview: String,
    pub keywords: Vec<String>,
}

/// 生成文档摘要（调用 LLM）
pub fn generate_summary(content: &str, llm_url: &str) -> Result<DocumentSummary, String> {
    let mut config = super::post_process::load_llm_config()?;
    // 允许调用方覆盖 base_url（pipeline 传入 sidecar URL）
    if !llm_url.is_empty() {
        config.base_url = llm_url.to_string();
    }

    // L0: 一句话摘要
    let l0_prompt = format!(
        "用一句话（不超过100字）概括以下文档的核心内容。只输出摘要，不要其他文字。\n\n{}",
        &content[..content.len().min(4000)]
    );
    let (l0, _) = super::post_process::call_llm_api(
        &config,
        "你是文档分析专家。",
        &l0_prompt,
    )?;
    let l0_abstract = l0.trim().trim_matches('"').to_string();

    // L1: 结构化概览
    let l1_prompt = format!(
        r#"分析以下文档，输出 JSON 格式的结构化概览：
{{
  "background": "研究背景（1-2句）",
  "methods": "主要方法",
  "key_results": "关键发现",
  "molecules": "涉及的分子/化合物",
  "activity_data": "活性数据摘要"
}}

文档内容：
{}"#,
        &content[..content.len().min(8000)]
    );
    let (l1, _) = super::post_process::call_llm_api(
        &config,
        "你是文档分析专家。输出 JSON。",
        &l1_prompt,
    )?;
    let l1_overview = l1.trim().trim_matches('"').to_string();

    // 关键词提取（委托给 keywords.rs 的统一实现）
    let keywords = extract_keywords(content);

    Ok(DocumentSummary {
        l0_abstract,
        l1_overview,
        keywords,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parsers::keywords::extract_keywords;

    #[test]
    fn test_extract_keywords() {
        let text = "This patent relates to chemical compounds and their biological activity.";
        let keywords = extract_keywords(text);
        assert!(!keywords.is_empty());
        assert!(keywords.contains(&"patent".to_string()));
    }
}
