use crate::doc_types::StructuredData;

/// === A4: 报告生成模块 ===
///
/// 从 StructuredData 程序化生成 Markdown 报告，不依赖 LLM。

/// 从 StructuredData 生成基础 Markdown 报告
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

/// 生成完整 Markdown 报告（基础报告 + SAR 分析 + 不确定项汇总）
pub fn generate_full_report(data: &StructuredData, sar_analysis: Option<&str>) -> String {
    let mut r = generate_report(data);

    // SAR 分析（如果存在）
    if let Some(sar) = sar_analysis {
        if !sar.is_empty() {
            r.push_str("## 构效关系分析 (SAR)\n\n");
            r.push_str(sar);
            r.push('\n');
            r.push('\n');
        }
    }

    // 不确定项汇总（给人工审核用）
    if !data.uncertain_items.is_empty() {
        r.push_str("## ⚠️ 需要人工审核\n\n");
        r.push_str("| 类型 | 内容 | 原因 | 建议操作 |\n");
        r.push_str("|------|------|------|----------|\n");
        for u in &data.uncertain_items {
            r.push_str(&format!(
                "| {} | {} | {} | {} |\n",
                u.item_type, u.content, u.reason, u.suggested_action
            ));
        }
        r.push('\n');
    }

    r
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::doc_types::DocumentMetadata;

    fn make_test_data() -> StructuredData {
        StructuredData {
            metadata: DocumentMetadata {
                title: Some("Test Patent".into()),
                authors: vec!["Author A".into()],
                document_type: "patent".into(),
                key_targets: vec!["MRGPRX2".into()],
                source_file: Some("test.pdf".into()),
            },
            summary: "This is a test summary.".into(),
            compounds: vec![],
            activities: vec![],
            key_findings: vec![],
            uncertain_items: vec![],
        }
    }

    #[test]
    fn test_generate_report() {
        let data = make_test_data();
        let report = generate_report(&data);
        assert!(report.contains("Test Patent"));
        assert!(report.contains("文档信息"));
    }

    #[test]
    fn test_generate_full_report() {
        let data = make_test_data();
        let report = generate_full_report(&data, Some("氰基取代显著提高活性 (pIC50 8.5→9.1)"));
        assert!(report.contains("Test Patent"));
        assert!(report.contains("SAR"));
        assert!(report.contains("氰基取代"));
    }

    #[test]
    fn test_generate_full_report_no_sar() {
        let data = make_test_data();
        let report = generate_full_report(&data, None);
        assert!(report.contains("Test Patent"));
        assert!(!report.contains("SAR"));
    }
}
