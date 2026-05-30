/// LLM 摘要生成 — 替代 Python DocumentSummarizer
///
/// 生成 L0（一句话）和 L1（结构化概览）摘要。

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentSummary {
    pub l0_abstract: String,
    pub l1_overview: String,
    pub keywords: Vec<String>,
}

/// 生成文档摘要（调用 LLM）
pub fn generate_summary(content: &str, llm_url: &str) -> Result<DocumentSummary, String> {
    let config = super::post_process::LlmApiConfig {
        base_url: llm_url.to_string(),
        api_key: std::env::var("MBFORGE_LLM_API_KEY").unwrap_or_default(),
        model: std::env::var("MBFORGE_LLM_MODEL").unwrap_or_default(),
    };

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

    // 关键词提取（简单版：高频词）
    let keywords = extract_keywords(content);

    Ok(DocumentSummary {
        l0_abstract,
        l1_overview,
        keywords,
    })
}

/// 简单关键词提取（基于词频）
fn extract_keywords(text: &str) -> Vec<String> {
    use std::collections::HashMap;

    let stop_words: std::collections::HashSet<&str> = [
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "out", "off", "over",
        "under", "again", "further", "then", "once", "and", "but", "or", "nor",
        "not", "so", "very", "just", "than", "too", "also", "this", "that",
        "these", "those", "it", "its", "the", "is", "are", "was", "were",
        "的", "了", "在", "是", "和", "与", "或", "等", "等", "中",
    ].iter().cloned().collect();

    let mut word_count: HashMap<String, usize> = HashMap::new();
    for word in text.split_whitespace() {
        let clean: String = word.chars()
            .filter(|c| c.is_alphanumeric() || *c == '-' || *c == '_')
            .collect();
        let lower = clean.to_lowercase();
        if lower.len() >= 3 && !stop_words.contains(lower.as_str()) {
            *word_count.entry(lower).or_insert(0) += 1;
        }
    }

    let mut words: Vec<(String, usize)> = word_count.into_iter().collect();
    words.sort_by(|a, b| b.1.cmp(&a.1));
    words.into_iter().take(10).map(|(w, _)| w).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_keywords() {
        let text = "This patent relates to chemical compounds and their biological activity.";
        let keywords = extract_keywords(text);
        assert!(!keywords.is_empty());
        assert!(keywords.contains(&"patent".to_string()));
    }
}
