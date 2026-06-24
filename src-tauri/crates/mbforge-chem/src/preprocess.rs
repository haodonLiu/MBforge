//! SMILES / E-SMILES / Markush 预处理管线
//!
//! 将分散在 `chem.rs`、`esmiles.rs`、`abbreviation_map.rs`、`molecode.rs` 中的
//! 预处理逻辑统一为可组合的流水线，减少重复代码并提高可维护性。

// ============================================================================
// SMILES 文本级清洗
// ============================================================================

/// 预处理错误
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PreprocessError {
    Empty,
    TooLong { len: usize, max: usize },
    ContainsSpaces,
}

impl std::fmt::Display for PreprocessError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PreprocessError::Empty => write!(f, "SMILES is empty"),
            PreprocessError::TooLong { len, max } => {
                write!(f, "SMILES too long: {} > {}", len, max)
            }
            PreprocessError::ContainsSpaces => write!(f, "SMILES contains spaces"),
        }
    }
}

impl std::error::Error for PreprocessError {}

/// 基础文本校验（空串、长度、非法字符）。
///
/// 与 `chem::validate_smiles` 的前置检查保持一致，但返回结构化错误以便上游选择处理方式。
pub fn validate_smiles_text(smiles: &str, max_len: usize) -> Result<(), PreprocessError> {
    if smiles.is_empty() {
        return Err(PreprocessError::Empty);
    }
    if smiles.len() > max_len {
        return Err(PreprocessError::TooLong {
            len: smiles.len(),
            max: max_len,
        });
    }
    if smiles.contains(' ') {
        return Err(PreprocessError::ContainsSpaces);
    }
    Ok(())
}

/// 将 bare `*` 转换为 bracket `[*]`，使 chematic 可以解析。
///
/// Delegates to `esmiles::normalize_wildcards` (single source of truth).
pub fn normalize_wildcards(smiles: &str) -> String {
    crate::esmiles::normalize_wildcards(smiles)
}

/// 缩写名称归一化。
///
/// Delegates to `abbreviation_map::normalize_abbrev_name` (single source of truth).
pub fn normalize_abbrev_name(name: &str) -> String {
    crate::abbreviation_map::normalize_abbrev_name(name)
}

// ============================================================================
// 标识符清洗（Mermaid / 代码生成）
// ============================================================================

/// 清洗字符串，使其成为合法的 Mermaid / 编程标识符。
///
/// - 仅保留 ASCII 字母数字和下划线
/// - 空串 fallback 为 `"Molecule"`
/// - 数字开头时前缀 `M`
pub fn sanitize_identifier(name: &str) -> String {
    let mut out: String = name
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '_')
        .collect();
    if out.is_empty() {
        out = "Molecule".to_string();
    } else if out.chars().next().is_some_and(|c| c.is_ascii_digit()) {
        out = format!("M{}", out);
    }
    out
}

// ============================================================================
// 统一预处理管线
// ============================================================================

/// 可组合的预处理步骤。
///
/// 使用示例：
/// ```ignore
/// let steps = &[PreprocessStep::ValidateText, PreprocessStep::NormalizeWildcards];
/// let result = preprocess_smiles("*c1ccccc1", steps);
/// ```
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PreprocessStep {
    /// 文本级校验（空串、长度、空格）
    ValidateText,
    /// wildcard 归一化 `*` → `[*]`
    NormalizeWildcards,
    /// 缩写名称归一化（R-group / substituent 名称）
    NormalizeAbbrev,
    /// 标识符清洗（Mermaid 输出用）
    SanitizeIdentifier,
}

/// 对输入字符串按顺序应用一系列预处理步骤。
///
/// # 参数
/// - `input`: 原始字符串
/// - `steps`: 要应用的步骤列表
/// - `max_len`: `ValidateText` 步骤使用的最大长度（默认 10_000）
///
/// # 返回
/// 成功时返回处理后的字符串；失败时返回 `PreprocessError`。
pub fn preprocess(
    input: &str,
    steps: &[PreprocessStep],
    max_len: usize,
) -> Result<String, PreprocessError> {
    let mut s = input.to_string();

    for step in steps {
        match step {
            PreprocessStep::ValidateText => validate_smiles_text(&s, max_len)?,
            PreprocessStep::NormalizeWildcards => s = normalize_wildcards(&s),
            PreprocessStep::NormalizeAbbrev => s = normalize_abbrev_name(&s),
            PreprocessStep::SanitizeIdentifier => s = sanitize_identifier(&s),
        }
    }

    Ok(s)
}

// ============================================================================
// 常用快捷组合
// ============================================================================

/// 标准 SMILES 预处理（验证 + wildcard 归一化）。
/// 这是 `chem::validate_smiles` 和 `esmiles` 解析的公共前置步骤。
pub fn preprocess_smiles(smiles: &str) -> Result<String, PreprocessError> {
    preprocess(
        smiles,
        &[
            PreprocessStep::ValidateText,
            PreprocessStep::NormalizeWildcards,
        ],
        10000,
    )
}

/// Markush / R-group 名称预处理（验证 + 缩写归一化）。
pub fn preprocess_rgroup_name(name: &str) -> Result<String, PreprocessError> {
    preprocess(
        name,
        &[
            PreprocessStep::ValidateText,
            PreprocessStep::NormalizeAbbrev,
        ],
        1000,
    )
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_empty() {
        assert!(matches!(
            validate_smiles_text("", 100),
            Err(PreprocessError::Empty)
        ));
    }

    #[test]
    fn test_validate_too_long() {
        let s = "C".repeat(101);
        assert!(matches!(
            validate_smiles_text(&s, 100),
            Err(PreprocessError::TooLong { len: 101, max: 100 })
        ));
    }

    #[test]
    fn test_validate_spaces() {
        assert!(matches!(
            validate_smiles_text("C C", 100),
            Err(PreprocessError::ContainsSpaces)
        ));
    }

    #[test]
    fn test_normalize_wildcards() {
        assert_eq!(normalize_wildcards("*c1ccccc1"), "[*]c1ccccc1");
        assert_eq!(normalize_wildcards("[*]c1ccccc1"), "[*]c1ccccc1");
        assert_eq!(normalize_wildcards("CC*CC"), "CC[*]CC");
    }

    #[test]
    fn test_normalize_abbrev_name() {
        assert_eq!(normalize_abbrev_name("R[1]"), "R1");
        assert_eq!(normalize_abbrev_name("R^1"), "R1");
        assert_eq!(normalize_abbrev_name("boc"), "Boc");
        assert_eq!(normalize_abbrev_name("OCH3"), "OMe");
        assert_eq!(normalize_abbrev_name("B5,"), "B5");
    }

    #[test]
    fn test_sanitize_identifier() {
        assert_eq!(sanitize_identifier("Aspirin"), "Aspirin");
        assert_eq!(sanitize_identifier("(E)-2-Butene"), "E2Butene");
        assert_eq!(sanitize_identifier("123"), "M123");
        assert_eq!(sanitize_identifier(""), "Molecule");
    }

    #[test]
    fn test_preprocess_smiles_ok() {
        assert_eq!(preprocess_smiles("*c1ccccc1").unwrap(), "[*]c1ccccc1");
    }

    #[test]
    fn test_preprocess_smiles_err() {
        assert!(preprocess_smiles("").is_err());
        assert!(preprocess_smiles("C C").is_err());
    }

    #[test]
    fn test_rgroup_name_ok() {
        assert_eq!(preprocess_rgroup_name("R[1]").unwrap(), "R1");
        assert_eq!(preprocess_rgroup_name("boc").unwrap(), "Boc");
    }

    #[test]
    fn test_rgroup_name_empty() {
        assert!(matches!(
            preprocess_rgroup_name(""),
            Err(PreprocessError::Empty)
        ));
    }

    #[test]
    fn test_rgroup_name_too_long() {
        let long = "R".repeat(1001);
        assert!(matches!(
            preprocess_rgroup_name(&long),
            Err(PreprocessError::TooLong {
                len: 1001,
                max: 1000
            })
        ));
    }

    #[test]
    fn test_preprocess_validate_text_only() {
        assert_eq!(
            preprocess("CCO", &[PreprocessStep::ValidateText], 100).unwrap(),
            "CCO"
        );
    }

    #[test]
    fn test_preprocess_validate_text_err() {
        assert!(preprocess("", &[PreprocessStep::ValidateText], 100).is_err());
    }

    #[test]
    fn test_preprocess_wildcard_only() {
        assert_eq!(
            preprocess("*c1ccccc1", &[PreprocessStep::NormalizeWildcards], 100).unwrap(),
            "[*]c1ccccc1"
        );
    }

    #[test]
    fn test_preprocess_validate_then_wildcard() {
        assert_eq!(
            preprocess(
                "*c1ccccc1",
                &[
                    PreprocessStep::ValidateText,
                    PreprocessStep::NormalizeWildcards
                ],
                100,
            )
            .unwrap(),
            "[*]c1ccccc1"
        );
    }

    #[test]
    fn test_preprocess_abbrev_only() {
        assert_eq!(
            preprocess("boc", &[PreprocessStep::NormalizeAbbrev], 100).unwrap(),
            "Boc"
        );
    }

    #[test]
    fn test_preprocess_sanitize_only() {
        assert_eq!(
            preprocess("(E)-2-Butene", &[PreprocessStep::SanitizeIdentifier], 100).unwrap(),
            "E2Butene"
        );
    }

    #[test]
    fn test_preprocess_empty_steps() {
        assert_eq!(preprocess("  hello  ", &[], 100).unwrap(), "  hello  ");
    }
}
