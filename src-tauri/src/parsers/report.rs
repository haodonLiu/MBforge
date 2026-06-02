// TODO-AUDIT: DocumentMetadata is imported but rustc reports it as unused at top level.
// It IS used inside mod tests via `use super::*` glob re-export, but the explicit
// import is technically redundant. Move into tests block or remove explicit import.
use super::doc_types::StructuredData;

use crate::parsers::post_process::generate_report as post_process_generate_report;

/// === A4: 报告生成模块 ===
///
/// 从 StructuredData 程序化生成 Markdown 报告，不依赖 LLM。
/// 在 post_process::generate_report() 基础上扩展 SAR 分析 + 处理日志。

/// 生成完整 Markdown 报告
pub fn generate_full_report(data: &StructuredData, sar_analysis: Option<&str>) -> String {
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parsers::doc_types::DocumentMetadata;

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
}
