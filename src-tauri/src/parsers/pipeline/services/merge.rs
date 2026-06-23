//! Structured data merging service for the PDF processing pipeline.
//!
//! This service combines per-section extraction results and VLM chemical
//! structure recognition results into a single consolidated [`StructuredData`]
//! document. It also produces a SAR (structure-activity relationship) analysis
//! text by prompting an LLM to merge, deduplicate and cross-validate the
//! inputs.

use crate::parsers::chem::vlm_chem::ChemImageResult;
use crate::parsers::doc_types::{DocStructure, StructuredData};
use crate::parsers::pipeline::error::{EnrichError, PipelineError};
use crate::parsers::structure::post_process::{
    call_llm_api_async, extract_json, parse_structured_data,
};

/// Service that merges structured section results and VLM chemistry results.
#[derive(Debug, Clone)]
pub struct StructuredDataMerger;

impl StructuredDataMerger {
    /// Creates a new [`StructuredDataMerger`].
    pub fn new() -> Self {
        Self
    }

    /// Merges `section_results` and `vlm_results` into a single document.
    ///
    /// A default [`DocStructure`] is used because the merger only relies on it
    /// for prompt context. On success, returns the merged [`StructuredData`] and
    /// the generated SAR analysis text.
    ///
    /// # Arguments
    /// - `section_results`: Structured data extracted from each document section.
    /// - `vlm_results`: VLM-recognized chemical structures keyed by image file
    ///   name.
    ///
    /// # Errors
    /// Returns [`PipelineError::Enrich`] with [`EnrichError::MergeFailed`] if the
    /// underlying merge step fails.
    pub async fn merge(
        &self,
        section_results: &[StructuredData],
        vlm_results: &[(String, ChemImageResult)],
    ) -> Result<(StructuredData, Option<String>), PipelineError> {
        let structure = DocStructure {
            doc_type: "unknown".into(),
            page_count: 0,
            has_compound_tables: false,
            has_chemical_structures: false,
            has_activity_data: false,
            estimated_sections: Vec::new(),
            key_terms: Vec::new(),
            recommended_approach: "default".into(),
        };

        let (data, sar) = run_merge_and_sar(section_results, vlm_results, &structure)
            .await
            .map_err(|e| PipelineError::Enrich(EnrichError::MergeFailed { detail: e }))?;

        Ok((data, Some(sar)))
    }
}

/// Stage 3: 多 section 结果合并 + 构效关系 (SAR) 分析
///
/// 输入：各 section 的提取结果 + VLM 识别的 SMILES
/// 任务：
/// 1. 去重合并相同化合物/活性数据
/// 2. 交叉验证文字提取与 VLM 结果
/// 3. 分析构效关系 (SAR)
/// 4. 生成最终结构化报告
async fn run_merge_and_sar(
    section_results: &[StructuredData],
    vlm_results: &[(String, ChemImageResult)],
    structure: &DocStructure,
) -> Result<(StructuredData, String), String> {
    // 构建 section 摘要
    let sections_text: Vec<String> = section_results
        .iter()
        .enumerate()
        .map(|(i, s)| {
            let title = s.metadata.title.as_deref().unwrap_or("未命名");
            format!(
                "## Section {}: {}\n摘要: {}\n化合物: {} 个 | 活性数据: {} 条",
                i + 1,
                title,
                &s.summary[..s.summary.len().min(300)],
                s.compounds.len(),
                s.activities.len(),
            )
        })
        .collect();

    // VLM 识别的化学结构
    let vlm_text: Vec<String> = vlm_results
        .iter()
        .map(|(fname, result)| {
            format!(
                "- **{}**: `{}` (置信度: {:.0}%)",
                fname,
                result.esmiles,
                result.confidence * 100.0
            )
        })
        .collect();

    let prompt = format!(
        r#"## 任务
合并多个 section 的提取结果，进行去重、交叉验证和构效关系分析，生成最终报告。

## 文档信息
- **原始类型**: {doc_type}
- **Section 数量**: {section_count}
- **VLM 识别**: {vlm_count} 个化学结构

## 各 Section 提取结果
{sections}

## VLM 图像识别结果
{vlm}

---

## 合并与验证规范

### 1. 去重规则
| 类型 | 去重依据 |
|------|----------|
| 化合物 | name 完全相同，或 SMILES 完全相同 |
| 活性数据 | compound + activity_type + value 完全相同 |
| 发现 | finding 内容高度相似 |

### 2. 冲突处理
- **文字 vs VLM**: 如 SMILES 不一致，保留文字提取结果，VLM 结果标记为 uncertain
- **数值冲突**: 以原文引用更明确的为准

### 3. 构效关系 (SAR) 分析
分析以下内容：
- **活性趋势**: 哪些结构修饰提高/降低了活性
- **关键基团**: 哪些官能团对活性有显著影响
- **构效规律**: 总结活性与结构的关系
- **参考化合物对比**: 与已知化合物比较

输出要求：
- 500 字以内
- 中文
- 包含具体数据支持

---

## 输出格式
**只输出 JSON**：

```json
{{
  "metadata": {{
    "title": "string | null",
    "authors": ["string"],
    "document_type": "string",
    "key_targets": ["string"]
  }},
  "summary": "200-400字中文摘要",
  "compounds": [
    {{
      "name": "string",
      "smiles": "string | null",
      "category": "lead | hit | reference | intermediate | null",
      "description": "string",
      "source_ref": "string",
      "confidence": "high | medium | low",
      "uncertainty_reason": "string | null"
    }}
  ],
  "activities": [
    {{
      "compound": "string",
      "activity_type": "IC50 | pIC50 | EC50 | Ki | 抑制率",
      "value": number,
      "units": "nM | μM | %",
      "target": "string | null",
      "source_quote": "string",
      "source_ref": "string",
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
  "sar_analysis": "构效关系总结（500字以内）",
  "uncertain_items": [
    {{
      "item_type": "string",
      "content": "string",
      "reason": "string",
      "suggested_action": "string"
    }}
  ]
}}
```"#,
        doc_type = structure.doc_type,
        section_count = section_results.len(),
        vlm_count = vlm_results.len(),
        sections = sections_text.join("\n\n---\n\n"),
        vlm = if vlm_text.is_empty() {
            "（无 VLM 识别结果）".to_string()
        } else {
            vlm_text.join("\n")
        },
    );

    let (response, _tokens) = call_llm_api_async(
        "你是分子科学文档分析专家。合并多部分提取结果，进行去重、验证和构效关系分析，输出 JSON。",
        &prompt,
    )
    .await?;

    let val = extract_json(&response)?;

    let data_val = val.get("data").unwrap_or(&val);
    let data = parse_structured_data(data_val)?;
    let sar = val["sar_analysis"].as_str().unwrap_or("").to_string();

    Ok((data, sar))
}
