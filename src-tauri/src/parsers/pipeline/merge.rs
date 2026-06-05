use crate::parsers::doc_types::{
    CompoundEntry, DocStructure, DocumentMetadata, FindingEntry, PhysicochemicalProperty,
    StructuredData, UncertainItem,
};
use crate::parsers::chem::vlm_chem::ChemImageResult;

/// Stage 3: 多 section 结果合并 + 构效关系 (SAR) 分析
///
/// 输入：各 section 的提取结果 + VLM 识别的 SMILES
/// 任务：
/// 1. 去重合并相同化合物/活性数据
/// 2. 交叉验证文字提取与 VLM 结果
/// 3. 分析构效关系 (SAR)
/// 4. 生成最终结构化报告
pub async fn run_merge_and_sar(
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

    let config = crate::parsers::structure::post_process::load_llm_config()?;
    let (response, _tokens) = crate::parsers::structure::post_process::call_llm_api_async(
        &config,
        "你是分子科学文档分析专家。合并多部分提取结果，进行去重、验证和构效关系分析，输出 JSON。",
        &prompt,
    )
    .await?;

    let val = crate::parsers::structure::post_process::extract_json(&response)?;

    let data_val = val.get("data").unwrap_or(&val);
    let data = crate::parsers::structure::post_process::parse_structured_data(data_val)?;
    let sar = val["sar_analysis"].as_str().unwrap_or("").to_string();

    Ok((data, sar))
}

/// 手动合并部分结果（当 LLM merge 失败时用）
pub fn merge_partial_results(
    section_results: &[StructuredData],
    _vlm_results: &[(String, ChemImageResult)],
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
        metadata: metadata.unwrap_or(DocumentMetadata {
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

/// 专利数据增强：将 molecule_traces 和 claim_graph 的信息整合进 StructuredData。
///
/// 1. 为现有 CompoundEntry 补充理化性质、图像、VLM 验证
/// 2. 若 LLM 未提取到某命名化合物，则追加新 CompoundEntry
/// 3. 将理化性质中的活性数据转为 ActivityEntry
/// 4. 若有 claim_graph，执行范围评估并加入 key_findings
pub fn enhance_patent_data(
    data: &mut StructuredData,
    traces: &[crate::parsers::chem::molecule_extractor::MoleculeTrace],
    claim_graph: &Option<crate::parsers::chem::claim_parser::ClaimDependencyGraph>,
    processing_log: &mut crate::parsers::doc_types::ProcessingLog,
) {
    let mut existing_names: std::collections::HashSet<String> =
        data.compounds.iter().map(|c| c.name.clone()).collect();
    let mut new_activities = Vec::new();

    for trace in traces {
        let mol = &trace.molecule;
        let props: Vec<PhysicochemicalProperty> = trace
            .properties
            .iter()
            .map(|p| PhysicochemicalProperty {
                property_type: p.property_type.clone(),
                value: p.value,
                unit: p.unit.clone(),
                source_quote: p.source_quote.clone(),
                confidence: p.confidence.clone(),
            })
            .collect();

        let related_images: Vec<String> = trace
            .related_images
            .iter()
            .map(|img| img.filename.clone())
            .collect();

        // 尝试找到同名的现有 CompoundEntry 并增强
        let mut found = false;
        for compound in data.compounds.iter_mut() {
            if compound.name == mol.name {
                found = true;
                if !props.is_empty() {
                    compound.physicochemical_props = Some(props.clone());
                }
                if !related_images.is_empty() {
                    compound.related_images = Some(related_images.clone());
                }
                if let Some(ref esmiles) = trace.vlm_verified_esmiles {
                    compound.vlm_verified_esmiles = Some(esmiles.clone());
                    if compound.esmiles.is_none() {
                        compound.esmiles = Some(esmiles.clone());
                    }
                }
                compound.page_location = mol.page_hint;
                // 提升置信度
                if compound.confidence != "high" {
                    compound.confidence = "high".into();
                }
                break;
            }
        }

        // 若未找到，追加新 CompoundEntry
        if !found {
            let description = if trace.properties.is_empty() {
                mol.context_text.chars().take(200).collect()
            } else {
                format!(
                    "从专利文本提取的命名化合物。关联属性: {}",
                    trace
                        .properties
                        .iter()
                        .map(|p| format!("{}={} {}", p.property_type, p.value, p.unit))
                        .collect::<Vec<_>>()
                        .join(", ")
                )
            };

            data.compounds.push(CompoundEntry {
                name: mol.name.clone(),
                esmiles: trace.vlm_verified_esmiles.clone(),
                category: None,
                description,
                source_ref: mol
                    .page_hint
                    .map(|p| format!("p.{}", p))
                    .unwrap_or_else(|| mol.section.clone()),
                confidence: if trace.vlm_verified_esmiles.is_some() {
                    "high"
                } else {
                    "medium"
                }
                .into(),
                uncertainty_reason: if trace.vlm_verified_esmiles.is_none() {
                    Some("缺少图像验证的化学结构".into())
                } else {
                    None
                },
                physicochemical_props: if props.is_empty() {
                    None
                } else {
                    Some(props.clone())
                },
                related_images: if related_images.is_empty() {
                    None
                } else {
                    Some(related_images)
                },
                vlm_verified_esmiles: trace.vlm_verified_esmiles.clone(),
                page_location: mol.page_hint,
            });
            existing_names.insert(mol.name.clone());
        }

        // 将活性类理化性质转为 ActivityEntry
        for prop in &trace.properties {
            let is_activity = matches!(
                prop.property_type.as_str(),
                "IC50" | "EC50" | "EC90" | "KI" | "KD" | "IC90"
            );
            if is_activity {
                new_activities.push(crate::parsers::doc_types::ActivityEntry {
                    compound: mol.name.clone(),
                    activity_type: prop.property_type.clone(),
                    value: prop.value,
                    units: prop.unit.clone(),
                    target: None,
                    source_quote: prop.source_quote.clone(),
                    source_ref: mol
                        .page_hint
                        .map(|p| format!("p.{}", p))
                        .unwrap_or_default(),
                    confidence: prop.confidence.clone(),
                    uncertainty_reason: None,
                });
            }
        }
    }

    // 追加新活性数据（去重）
    let existing_activity_keys: std::collections::HashSet<String> = data
        .activities
        .iter()
        .map(|a| format!("{}|{}|{}", a.compound, a.activity_type, a.value))
        .collect();
    for activity in new_activities {
        let key = format!(
            "{}|{}|{}",
            activity.compound, activity.activity_type, activity.value
        );
        if !existing_activity_keys.contains(&key) {
            data.activities.push(activity);
        }
    }

    // Claim 范围评估
    if let Some(ref graph) = claim_graph {
        let assessments = crate::parsers::chem::claim_policy::assess_all_compounds(traces, graph);

        for assessment in &assessments {
            let finding_text = format!(
                "化合物 '{}' 的专利范围评估: {:?}",
                assessment.compound_name, assessment.risk_level
            );
            let evidence = assessment.assessment_summary.clone();
            data.key_findings.push(FindingEntry {
                finding: finding_text,
                evidence,
                source_ref: "claims_section".into(),
                confidence: match assessment.risk_level {
                    crate::parsers::chem::claim_policy::RiskLevel::High => "high",
                    crate::parsers::chem::claim_policy::RiskLevel::Medium => "medium",
                    crate::parsers::chem::claim_policy::RiskLevel::Low => "low",
                    crate::parsers::chem::claim_policy::RiskLevel::Clear => "high",
                }
                .into(),
                uncertainty_reason: if assessment.covered_claims.is_empty() {
                    Some("未检测到权利要求覆盖".into())
                } else {
                    None
                },
            });
        }

        processing_log
            .stages
            .push(crate::parsers::doc_types::StageLog {
                stage: 3,
                name: "专利范围评估".into(),
                status: "ok".into(),
                items_processed: assessments.len(),
                tokens_used: 0,
                errors: vec![],
            });
    }
}
