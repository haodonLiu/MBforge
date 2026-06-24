use super::post_process::extract_json;
use crate::doc_types::{DocProcessingContext, DocStructure, ExtractionPlan};

/// === A1: 意图路由模块 ===

/// Stage 1 Prompt: 文档结构分析
///
/// 分析文档开头部分，判断：
/// 1. 文档类型（专利/论文/报告）
/// 2. 是否包含化合物表格、化学结构图、活性数据
/// 3. 章节结构（通过标题识别）
/// 4. 关键术语（靶点、活性指标、化合物代号等）
/// 5. 推荐提取策略
///
/// 输入：前 8000 字符 + 页码
/// 输出：结构化元数据 JSON
pub fn build_meta_prompt(context: &DocProcessingContext) -> String {
    let preview: String = context.raw_text.chars().take(8000).collect();

    // 从用户请求中提取关键意图（如果有）
    let user_hint = if context.user_request.is_empty() {
        String::new()
    } else {
        format!("\n\n## 用户查询意图\n{}", context.user_request)
    };

    format!(
        r#"## 任务
分析以下文档的元信息，判断文档类型、结构和关键内容。

## 输入文档（前 8000 字符）
```
{preview}
```

## 文档基本信息
- 页数: {page_count}{user_hint}

## 分析要求

### 1. 文档类型判断
根据文档特征判断类型：
- `patent`: 含权利要求书、说明书、引用号（如 WO/EP/CN/US 专利）
- `paper`: 含摘要、实验方法、参考文献（期刊/会议论文）
- `report`: 含摘要、结论、附录（研究报告/综述）
- `unknown`: 无法判断

### 2. 内容特征检测
判断文档是否包含以下内容（基于关键词和模式）：
- `has_compound_tables`: 化合物表格（Table 1, 实施例表, 化合物代号如 E041, A-001）
- `has_chemical_structures`: 化学结构（SMILES, E-SMILES, 化学结构描述）
- `has_activity_data`: 活性数据（IC50, pIC50, EC50, Ki, 抑制率, Kd）

### 3. 章节结构识别
通过标题模式识别章节：
常见专利章节: title, abstract, background, summary, detailed_description, examples, claims
常见论文章节: title, abstract, introduction, methods, results, discussion, conclusion

### 4. 关键术语提取
提取：
- 靶点/疾病: 如 MrgprX2, HER2, COVID-19
- 活性指标: 如 pIC50, IC50, EC50
- 化合物代号: 如 E041, A-001, compound 1
- 化学术语: 如 scaffold, hit, lead, SAR

### 5. 推荐策略
根据文档特征推荐后续处理策略：
- `full`: 全量提取（默认）
- `table_only`: 重点提取表格数据
- `structure_only`: 重点提取化学结构
- `metadata_only`: 仅提取元数据

## 输出格式
只输出 JSON，不要其他文字：
```json
{{
  "doc_type": "patent | paper | report | unknown",
  "page_count": {page_count},
  "has_compound_tables": true | false,
  "has_chemical_structures": true | false,
  "has_activity_data": true | false,
  "estimated_sections": ["title", "abstract", "background", ...],
  "key_terms": ["term1", "term2", ...],
  "recommended_approach": "full | table_only | structure_only | metadata_only"
}}
```

**重要**：只输出 JSON，不要解释或其他内容。"#,
        preview = preview,
        page_count = context.page_count,
        user_hint = user_hint,
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
    let estimated_sections = val["estimated_sections"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();
    let key_terms = val["key_terms"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();
    let recommended_approach = val["recommended_approach"]
        .as_str()
        .unwrap_or("full")
        .to_string();

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
    let to_strings =
        |slice: &[&str]| -> Vec<String> { slice.iter().map(|s| s.to_string()).collect() };

    let (target_sections, extraction_types): (Vec<String>, Vec<String>) =
        match infer_intent(user_request) {
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

    let skip_sections: Vec<String> = structure
        .estimated_sections
        .iter()
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
    let activity_keywords = [
        "活性",
        "pIC50",
        "ic50",
        "ec50",
        "potency",
        "活性数据",
        "抑制率",
    ];
    let compound_keywords = [
        "化合物",
        "smiles",
        "结构",
        "分子",
        "实施例",
        "compound",
        "example",
    ];
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
        assert_eq!(
            infer_intent("把表1的活性数据提取出来"),
            UserIntent::TableOnly
        );
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
            estimated_sections: vec![
                "title".into(),
                "abstract".into(),
                "background".into(),
                "results".into(),
            ],
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
            estimated_sections: vec![
                "title".into(),
                "abstract".into(),
                "background".into(),
                "results".into(),
                "claims".into(),
            ],
            key_terms: vec![],
            recommended_approach: "full".into(),
        };
        let plan = interpret_request(&structure, "提取 TABLE 1");
        assert_eq!(
            plan.target_sections,
            vec!["results", "table_1", "biological_data", "examples"]
        );
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
