/// Heading 提取器 — 多策略识别文档结构
///
/// 支持：
/// - 策略 A: Markdown `#` heading
/// - 策略 B: 全大写行 + 前后空行（专利格式：ABSTRACT, CLAIMS）
/// - 策略 C: 冒号终止行（"Field of Invention:"）
/// - 策略 D: 数字编号 + 大写开头（"1. Technical Field"）

use regex::Regex;

#[derive(Debug, Clone, PartialEq)]
pub struct Heading {
    pub level: usize,
    pub title: String,
    pub line_num: usize,
}

/// 从文本中提取所有 heading
pub fn extract_headings(text: &str) -> Vec<Heading> {
    let mut headings = Vec::new();
    let lines: Vec<&str> = text.lines().collect();

    // 策略 A: Markdown # heading (最高优先级)
    let md_re = Regex::new(r"^(#{1,6})\s+(.+)$").unwrap();
    // 策略 B: 全大写行（至少 3 个大写字母，不含小写）
    let upper_re = Regex::new(r"^\s*([A-Z][A-Z\s]{2,})\s*$").unwrap();
    // 策略 C: 冒号终止行
    let colon_re = Regex::new(r"^([A-Z][\w\s]+):\s*$").unwrap();
    // 策略 D: 数字编号 + 大写开头
    let num_re = Regex::new(r"^(\d+)\.\s+([A-Z].+)$").unwrap();

    for (i, line) in lines.iter().enumerate() {
        let trimmed = line.trim();

        // 策略 A: Markdown
        if let Some(caps) = md_re.captures(trimmed) {
            let level = caps[1].len();
            let title = caps[2].trim().to_string();
            headings.push(Heading { level, title, line_num: i });
            continue;
        }

        // 策略 B: 全大写行（需要前后空行或首尾）
        if let Some(caps) = upper_re.captures(trimmed) {
            let title = caps[1].trim().to_string();
            // 检查前后是否为空行或文档边界
            let prev_empty = i == 0 || lines[i - 1].trim().is_empty();
            let next_empty = i + 1 >= lines.len() || lines[i + 1].trim().is_empty();
            if prev_empty && next_empty && title.len() >= 3 {
                headings.push(Heading { level: 1, title, line_num: i });
                continue;
            }
        }

        // 策略 C: 冒号终止
        if let Some(caps) = colon_re.captures(trimmed) {
            let title = caps[1].trim().to_string();
            // 排除太短的（如 "Note:"）和太长的
            if title.len() >= 5 && title.len() <= 60 {
                headings.push(Heading { level: 2, title, line_num: i });
                continue;
            }
        }

        // 策略 D: 数字编号
        if let Some(caps) = num_re.captures(trimmed) {
            let title = format!("{}. {}", &caps[1], caps[2].trim());
            headings.push(Heading { level: 2, title, line_num: i });
        }
    }

    headings
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_heading_markdown() {
        let text = "# Title\nSome text\n## Section\nMore text";
        let headings = extract_headings(text);
        assert_eq!(headings.len(), 2);
        assert_eq!(headings[0].level, 1);
        assert_eq!(headings[0].title, "Title");
        assert_eq!(headings[1].level, 2);
        assert_eq!(headings[1].title, "Section");
    }

    #[test]
    fn test_heading_patent_uppercase() {
        let text = "Some intro text.\n\nABSTRACT\n\nThis invention relates to...";
        let headings = extract_headings(text);
        assert!(headings.iter().any(|h| h.title == "ABSTRACT"));
    }

    #[test]
    fn test_heading_colon_terminated() {
        let text = "Background\n\nField of Invention:\nThis invention relates to...";
        let headings = extract_headings(text);
        assert!(headings.iter().any(|h| h.title == "Field of Invention"));
    }

    #[test]
    fn test_heading_numbered() {
        let text = "1. Technical Field\nSome text\n2. Background\nMore text";
        let headings = extract_headings(text);
        assert_eq!(headings.len(), 2);
        assert_eq!(headings[0].title, "1. Technical Field");
        assert_eq!(headings[1].title, "2. Background");
    }

    #[test]
    fn test_heading_mixed() {
        let text = "# Patent Application\n\nABSTRACT\n\nThis invention...\n\n1. Field of Invention\nDetailed description.";
        let headings = extract_headings(text);
        assert!(headings.len() >= 2);
    }

    #[test]
    fn test_no_headings() {
        let text = "This is just plain text without any headings.\nSecond line.";
        let headings = extract_headings(text);
        assert!(headings.is_empty());
    }
}
