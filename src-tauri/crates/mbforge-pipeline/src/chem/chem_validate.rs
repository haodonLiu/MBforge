#![allow(dead_code)]
/// 化学结构验证模块（纯 Rust）
///
/// 使用 `chematic` crate 对 SMILES/E-SMILES 进行结构校验：
/// - SMILES 可解析性
/// - 规范化（canonicalization）
/// - Kekulize / 芳香性检查
///
/// 使用路径：Rust → `chematic_smiles::parse` + `canonical_smiles`

/// 单条验证结果
#[derive(Debug, Clone)]
pub struct ValidateResult {
    pub valid: bool,
    pub canonical_smiles: Option<String>,
    pub issues: Vec<ValidateIssue>,
}

#[derive(Debug, Clone)]
pub struct ValidateIssue {
    pub code: String,
    pub message: String,
    pub severity: String, // "error" | "warning"
}

/// 验证单条 E-SMILES（纯 Rust，使用 chematic）
pub fn validate_smiles(esmiles: &str) -> ValidateResult {
    let cleaned = sanitize_esmiles(esmiles);
    if cleaned.is_empty() {
        return ValidateResult {
            valid: false,
            canonical_smiles: None,
            issues: vec![ValidateIssue {
                code: "EMPTY_INPUT".into(),
                message: "Empty SMILES".into(),
                severity: "error".into(),
            }],
        };
    }

    match mbforge_chem::validate_smiles(&cleaned) {
        result if result.valid => ValidateResult {
            valid: true,
            canonical_smiles: result.canonical_smiles,
            issues: Vec::new(),
        },
        result => ValidateResult {
            valid: false,
            canonical_smiles: None,
            issues: vec![ValidateIssue {
                code: "PARSE_FAILED".into(),
                message: result.error.unwrap_or_else(|| "Unknown error".into()),
                severity: "error".into(),
            }],
        },
    }
}

/// 批量验证（纯 Rust，无 HTTP 开销）
pub fn validate_smiles_batch(esmiles_list: &[String]) -> Vec<(String, ValidateResult)> {
    esmiles_list
        .iter()
        .map(|s| (s.clone(), validate_smiles(s)))
        .collect()
}

/// 净化 E-SMILES：去除空白、E-SMILES 标签等常见 LLM 污染
pub fn sanitize_esmiles(raw: &str) -> String {
    let mut s = raw.trim().to_string();
    // 去除 markdown 代码块标记
    if s.starts_with('`') && s.ends_with('`') {
        s = s.trim_matches('`').to_string();
    }
    // 去除常见的解释性前缀
    for prefix in ["SMILES: ", "E-SMILES: ", "smiles: ", "esmiles: "] {
        if s.starts_with(prefix) {
            s = s[prefix.len()..].to_string();
        }
    }
    s.trim().to_string()
}

/// 三层分离：从 E-SMILES 中提取纯净 SMILES + 语义标签
///
/// E-SMILES 格式示例：`<c>1:R1</c>CC(=O)Oc1ccccc1C(=O)O`
/// - 标签: `<c>1:R1</c>` → semantic_tags: {"R1": "Me", ...}
/// - 纯净 SMILES: `CC(=O)Oc1ccccc1C(=O)O`
///
/// 返回 (clean_smiles, original_esmiles, semantic_tags_json)
pub fn separate_esmiles_layers(raw: &str) -> (String, Option<String>, Option<serde_json::Value>) {
    let cleaned = sanitize_esmiles(raw);
    if cleaned.is_empty() {
        return (String::new(), None, None);
    }

    // 检测是否包含 E-SMILES 标签（<c>N:VALUE</c> 或 <TAG>VALUE</TAG> 格式）
    let tag_re = regex::Regex::new(r"<[a-zA-Z]>\d+:[^<]+</[a-zA-Z]>").unwrap();
    let tags: Vec<(String, String)> = tag_re
        .find_iter(&cleaned)
        .filter_map(|m| {
            let tag_str = m.as_str();
            // 解析 <c>1:R1</c> → ("c", "R1") 或更精确地提取编号和值
            let inner = tag_str.split('>').nth(1)?.split('<').next()?;
            let parts: Vec<&str> = inner.splitn(2, ':').collect();
            if parts.len() == 2 {
                Some((format!("tag_{}", parts[0]), parts[1].to_string()))
            } else {
                None
            }
        })
        .collect();

    // 剥离标签得到纯净 SMILES
    let clean_smiles: String = tag_re.replace_all(&cleaned, "").to_string();
    let clean_smiles = clean_smiles.trim().to_string();

    // 构建 semantic_tags JSON
    let semantic_tags = if tags.is_empty() {
        None
    } else {
        let map: serde_json::Map<String, serde_json::Value> = tags
            .into_iter()
            .map(|(k, v)| (k, serde_json::Value::String(v)))
            .collect();
        Some(serde_json::Value::Object(map))
    };

    // 如果有标签，保留原始 E-SMILES；否则不存
    let esmiles = if semantic_tags.is_some() {
        Some(cleaned)
    } else {
        None
    };

    (clean_smiles, esmiles, semantic_tags)
}

/// 安全解析数值（处理 LLM 输出的各种格式问题）
pub fn sanitize_activity_value(raw: &str) -> Option<f64> {
    let cleaned: String = raw
        .chars()
        .filter(|c| c.is_ascii_digit() || *c == '.' || *c == '-' || *c == 'e' || *c == 'E')
        .collect();
    cleaned.parse().ok()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitize_esmiles() {
        assert_eq!(sanitize_esmiles("`CCO`"), "CCO");
        assert_eq!(sanitize_esmiles("SMILES: CCO"), "CCO");
        assert_eq!(sanitize_esmiles("  CCO  "), "CCO");
    }

    #[test]
    fn test_validate_smiles_valid() {
        let result = validate_smiles("CCO");
        assert!(result.valid);
        assert!(result.canonical_smiles.is_some());
        assert!(result.issues.is_empty());
    }

    #[test]
    fn test_validate_smiles_invalid() {
        // 使用包含非法字符的 SMILES（chematic 会拒绝）
        let result = validate_smiles("[Xx]");
        assert!(!result.valid);
        assert!(!result.issues.is_empty());
    }

    #[test]
    fn test_validate_smiles_empty() {
        let result = validate_smiles("");
        assert!(!result.valid);
    }

    #[test]
    fn test_sanitize_activity_value() {
        assert_eq!(sanitize_activity_value("5.2 nM"), Some(5.2));
        assert_eq!(sanitize_activity_value("< 10"), Some(10.0));
        assert_eq!(sanitize_activity_value("N/A"), None);
    }

    #[test]
    fn test_separate_esmiles_layers() {
        let (smiles, esmiles, tags) = separate_esmiles_layers("CCO");
        assert_eq!(smiles, "CCO");
        assert!(esmiles.is_none());
        assert!(tags.is_none());
    }
}
