use super::post_process::extract_json;
use super::types::{DocProcessingContext, DocStructure, ExtractionPlan};

/// === A1: 意图路由模块 ===

/// Meta Prompt: 分析文档开头部分，判断文档类型和结构
/// 只读前 8000 字符 + 页码，不做全文分析
pub fn build_meta_prompt(context: &DocProcessingContext) -> String {
    let preview: String = context.raw_text.chars().take(8000).collect();

    format!(
        r#"分析以下文档开头部分，判断文档类型和结构。

文档开头（前 8000 字符）：
---
{preview}
---

要求输出 JSON（不要其他文字）：
{{
  "doc_type": "patent / paper / report / unknown",
  "page_count": {page_count},
  "has_compound_tables": true/false,
  "has_chemical_structures": true/false,
  "has_activity_data": true/false,
  "estimated_sections": ["title", "abstract", "background", ...],
  "key_terms": ["MrgprX2", "pIC50", ...],
  "recommended_approach": "full / table_only / structure_only / metadata_only"
}}
只输出 JSON。"#,
        preview = preview,
        page_count = context.page_count,
    )
}

/// 解析 LLM 返回的 DocStructure JSON
pub fn parse_meta_response(raw_response: &str) -> Result<DocStructure, String> {
    let val = extract_json(raw_response)?;

    let doc_type = val["doc_type"].as_str().unwrap_or("unknown").to_string();
    let page_count = val["page_count"].as_u64().unwrap_or(0) as usize;
    let has_compound_tables = val["has_compound_tables"].as_bool().unwrap_or(false);
    let has_chemical_structures = val["has_chemical_structures"].as_bool().unwrap_or(false);
    let has_activity_data = val["has_activity_data"].as_bool().unwrap_or(false);
    let estimated_sections = val["estimated_sections"].as_array()
        .map(|a| a.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
        .unwrap_or_default();
    let key_terms = val["key_terms"].as_array()
        .map(|a| a.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
        .unwrap_or_default();
    let recommended_approach = val["recommended_approach"].as_str().unwrap_or("full").to_string();

    Ok(DocStructure {
        doc_type,
        page_count,
        has_compound_tables,
        has_chemical_structures,
        has_activity_data,
        estimated_sections,
        key_terms,
        recommended_approach,
    })
}

/// 将用户指令解析为提取计划
///
/// 支持的中文/英文关键词：
///   - TABLE 1、活性数据、pIC50 → activities
///   - 化合物、SMILES、结构式 → compounds
///   - 无指令 → full（全量提取）
pub fn interpret_request(structure: &DocStructure, user_request: &str) -> ExtractionPlan {
    let to_strings = |slice: &[&str]| -> Vec<String> { slice.iter().map(|s| s.to_string()).collect() };

    let (target_sections, extraction_types): (Vec<String>, Vec<String>) = match infer_intent(user_request) {
        UserIntent::TableOnly => (
            to_strings(&["results", "table_1", "biological_data", "examples"]),
            to_strings(&["compounds", "activities"]),
        ),
        UserIntent::ActivityData => (
            to_strings(&["results", "table_1", "biological_data", "examples"]),
            to_strings(&["activities"]),
        ),
        UserIntent::Compounds => (
            to_strings(&["examples", "synthesis", "table_*", "claims"]),
            to_strings(&["compounds"]),
        ),
        UserIntent::MetadataOnly => (
            to_strings(&["title", "abstract", "background"]),
            to_strings(&["metadata"]),
        ),
        UserIntent::Full => (
            structure.estimated_sections.clone(),
            to_strings(&["compounds", "activities", "metadata", "findings"]),
        ),
    };

    let skip_sections: Vec<String> = structure.estimated_sections.iter()
        .filter(|s| !target_sections.contains(s))
        .cloned()
        .collect();

    ExtractionPlan {
        target_sections,
        extraction_types,
        skip_sections,
    }
}

#[derive(Debug, PartialEq)]
enum UserIntent {
    TableOnly,
    ActivityData,
    Compounds,
    MetadataOnly,
    Full,
}

fn infer_intent(request: &str) -> UserIntent {
    let r = request.to_lowercase();

    let table_keywords = ["table 1", "table ⅰ", "表1", "表格1", "table1"];
    let activity_keywords = ["活性", "pIC50", "ic50", "ec50", "potency", "活性数据", "抑制率"];
    let compound_keywords = ["化合物", "smiles", "结构", "分子", "实施例", "compound", "example"];
    let metadata_keywords = ["元数据", "标题", "metadata", "摘要", "abstract", "基本信息"];

    if table_keywords.iter().any(|k| r.contains(k)) {
        return UserIntent::TableOnly;
    }
    if activity_keywords.iter().any(|k| r.contains(k)) {
        if compound_keywords.iter().any(|k| r.contains(k)) {
            return UserIntent::TableOnly; // 化合物+活性 → 整表
        }
        return UserIntent::ActivityData;
    }
    if compound_keywords.iter().any(|k| r.contains(k)) {
        return UserIntent::Compounds;
    }
    if metadata_keywords.iter().any(|k| r.contains(k)) {
        return UserIntent::MetadataOnly;
    }

    UserIntent::Full
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_infer_intent_table() {
        assert_eq!(infer_intent("提取 TABLE 1 数据"), UserIntent::TableOnly);
        assert_eq!(infer_intent("把表1的活性数据提取出来"), UserIntent::TableOnly);
    }

    #[test]
    fn test_infer_intent_activity() {
        assert_eq!(infer_intent("提取所有pIC50值"), UserIntent::ActivityData);
        assert_eq!(infer_intent("活性数据有哪些"), UserIntent::ActivityData);
    }

    #[test]
    fn test_infer_intent_compound() {
        assert_eq!(infer_intent("提取化合物SMILES"), UserIntent::Compounds);
        assert_eq!(infer_intent("列出所有实施例化合物"), UserIntent::Compounds);
    }

    #[test]
    fn test_infer_intent_full() {
        assert_eq!(infer_intent("帮我分析这个文档"), UserIntent::Full);
        assert_eq!(infer_intent(""), UserIntent::Full);
    }

    #[test]
    fn test_interpret_request_full() {
        let structure = DocStructure {
            doc_type: "patent".into(),
            page_count: 100,
            has_compound_tables: true,
            has_chemical_structures: true,
            has_activity_data: true,
            estimated_sections: vec!["title".into(), "abstract".into(), "background".into(), "results".into()],
            key_terms: vec![],
            recommended_approach: "full".into(),
        };
        let plan = interpret_request(&structure, "帮我分析这个文档");
        assert_eq!(plan.target_sections.len(), 4);
        assert!(plan.skip_sections.is_empty());
    }

    #[test]
    fn test_interpret_request_table_only() {
        let structure = DocStructure {
            doc_type: "patent".into(),
            page_count: 100,
            has_compound_tables: true,
            has_chemical_structures: true,
            has_activity_data: true,
            estimated_sections: vec!["title".into(), "abstract".into(), "background".into(), "results".into(), "claims".into()],
            key_terms: vec![],
            recommended_approach: "full".into(),
        };
        let plan = interpret_request(&structure, "提取 TABLE 1");
        assert_eq!(plan.target_sections, vec!["results", "table_1", "biological_data", "examples"]);
        // estimated_sections = [title, abstract, background, results, claims]
        // target_sections = [results, table_1, biological_data, examples]
        // 跳过: title, abstract, background, claims (4个)
        assert_eq!(plan.skip_sections.len(), 4);
    }

    #[test]
    fn test_parse_meta_response() {
        let resp = r#"{"doc_type": "patent", "page_count": 100, "has_compound_tables": true, "has_chemical_structures": true, "has_activity_data": true, "estimated_sections": ["title", "abstract", "background", "results"], "key_terms": ["MrgprX2", "pIC50"], "recommended_approach": "full"}"#;
        let structure = parse_meta_response(resp).unwrap();
        assert_eq!(structure.doc_type, "patent");
        assert_eq!(structure.page_count, 100);
        assert!(structure.has_compound_tables);
        assert_eq!(structure.estimated_sections.len(), 4);
        assert_eq!(structure.key_terms, vec!["MrgprX2", "pIC50"]);
    }

    #[test]
    fn test_build_meta_prompt_short_text() {
        let ctx = DocProcessingContext::new("/tmp/test.pdf", "");
        let prompt = build_meta_prompt(&ctx);
        assert!(prompt.contains("8000"));
        assert!(prompt.contains("doc_type"));
    }
}
