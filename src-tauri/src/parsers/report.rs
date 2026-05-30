use super::post_process::{DocumentMetadata, StructuredData};

use crate::parsers::post_process::generate_report as post_process_generate_report;

/// === A4: 报告生成模块 ===
///
/// 从 StructuredData 程序化生成 Markdown 报告，不依赖 LLM。
/// 在 post_process::generate_report() 基础上扩展 SAR 分析 + 处理日志。

/// 生成完整 Markdown 报告
pub fn generate_full_report(
    data: &StructuredData,
    sar_analysis: Option<&str>,
) -> String {
    let mut r = post_process_generate_report(data);

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

/// 生成简短的 Markdown 摘要（用于预览/通知）
pub fn generate_summary(data: &StructuredData) -> String {
    let mut r = String::new();

    r.push_str(&format!("**{}**\n\n", data.metadata.title.as_deref().unwrap_or("未知文档")));
    r.push_str(&format!("- 类型: {}\n", data.metadata.document_type));
    r.push_str(&format!("- 化合物: {} 个\n", data.compounds.len()));
    r.push_str(&format!("- 活性数据: {} 条\n", data.activities.len()));
    r.push_str(&format!("- 关键发现: {} 条\n", data.key_findings.len()));

    if !data.uncertain_items.is_empty() {
        r.push_str(&format!("- ⚠️ 不确定项: {} 条（需要人工审核）\n", data.uncertain_items.len()));
    }

    if !data.summary.is_empty() {
        r.push_str(&format!("\n{}\n", &data.summary[..data.summary.len().min(200)]));
    }

    r
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

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

    #[test]
    fn test_generate_summary() {
        let data = make_test_data();
        let summary = generate_summary(&data);
        assert!(summary.contains("Test Patent"));
        assert!(summary.contains("类型"));
    }
}
