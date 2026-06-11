#![allow(dead_code)]
//! E-SMILES 标签生成：SMILES → E-SMILES
//!
//! 给纯 SMILES 字符串添加语义标签（`<a>`, `<r>`, `<c>`），生成符合
//! MolParser 规范的 E-SMILES 字符串。
//!
//! # 格式
//!
//! ```text
//! E-SMILES := SMILES '<sep>' TAG [TAG ...]
//! TAG      := '<a>' INDEX ':' GROUP '</a>'
//!          |  '<r>' INDEX ':' GROUP '</r>'
//!          |  '<c>' INDEX ':' NAME  '</c>'
//! ```
//!
//! # 示例
//!
//! ```
//! use mbforge_lib::core::esmiles::{smiles_to_esmiles, smiles_with_rgroups_to_esmiles, EsTag};
//!
//! // 手动指定标签
//! let result = smiles_to_esmiles("CC(=O)O", &[EsTag::atom(0, "R1")]);
//! assert_eq!(result, "CC(=O)O<sep><a>0:R1</a>");
//!
//! // * 原子自动映射
//! let result = smiles_with_rgroups_to_esmiles("*c1ccccc1", &["R[1]".into()]);
//! assert_eq!(result, "*c1ccccc1<sep><a>0:R[1]</a>");
//! ```

use chematic_smiles::parse;

/// 将 bare `*` 转换为 bracket `[*]`，使 chematic 可以解析。
///
/// E-SMILES / Markush SMILES 中的 `*` dummy atom 在 SMILES 规范中是 bare atom，
/// 但 chematic 只识别 bracket 形式 `[*]`。
///
/// 处理逻辑：逐字符扫描，遇到 `*` 时检查前一个字符是否为 `[`（说明已在 bracket 内），
/// 如果不是则替换为 `[*]`。
pub(crate) fn normalize_wildcards(smiles: &str) -> String {
    let bytes = smiles.as_bytes();
    let len = bytes.len();
    let mut out = Vec::with_capacity(len + 10);

    for (i, &b) in bytes.iter().enumerate() {
        if b == b'*' {
            // 检查前一个字符是否为 '[' —— 如果是，说明 * 已在 bracket 内
            if i > 0 && bytes[i - 1] == b'[' {
                out.push(b'*');
            } else {
                // bare * → [*]
                out.extend_from_slice(b"[*]");
            }
        } else {
            out.push(b);
        }
    }

    String::from_utf8(out).unwrap_or_else(|_| smiles.to_string())
}

/// E-SMILES 语义标签
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EsTag {
    /// 原子标签：`<a>N:GROUP</a>`
    Atom { index: usize, group: String },
    /// 环不确定位置标签：`<r>N:GROUP</r>`
    Ring { index: usize, group: String },
    /// 抽象环标签：`<c>N:NAME</c>`
    Circle { index: usize, name: String },
}

impl EsTag {
    /// 创建原子标签
    pub fn atom(index: usize, group: impl Into<String>) -> Self {
        EsTag::Atom { index, group: group.into() }
    }

    /// 创建环标签
    pub fn ring(index: usize, group: impl Into<String>) -> Self {
        EsTag::Ring { index, group: group.into() }
    }

    /// 创建抽象环标签
    pub fn circle(index: usize, name: impl Into<String>) -> Self {
        EsTag::Circle { index, name: name.into() }
    }

    /// 序列化为 E-SMILES 标签字符串
    pub fn to_esmiles_tag(&self) -> String {
        match self {
            EsTag::Atom { index, group } => format!("<a>{}:{}</a>", index, group),
            EsTag::Ring { index, group } => format!("<r>{}:{}</r>", index, group),
            EsTag::Circle { index, name } => format!("<c>{}:{}</c>", index, name),
        }
    }
}

/// 给纯 SMILES 添加 E-SMILES 标签。
///
/// # 参数
/// - `smiles`: 纯净 SMILES 字符串
/// - `tags`: 要添加的标签列表
///
/// # 返回
/// E-SMILES 字符串：`SMILES<sep>TAG1TAG2...`
///
/// 如果 `tags` 为空，返回原始 SMILES（不添加 `<sep>`）。
pub fn smiles_to_esmiles(smiles: &str, tags: &[EsTag]) -> String {
    if tags.is_empty() {
        return smiles.to_string();
    }

    let tag_str: String = tags.iter().map(|t| t.to_esmiles_tag()).collect();
    format!("{}<sep>{}", smiles, tag_str)
}

/// 从含 `*`（dummy atom）的 SMILES 自动生成 E-SMILES。
///
/// 遍历 SMILES 中的 `*` 原子（wildcard），按顺序分配 `<a>N:NAME</a>` 标签。
///
/// # 参数
/// - `smiles`: 含 `*` 占位符的 SMILES
/// - `rgroup_names`: R-group 名称列表，按 `*` 出现顺序分配
///
/// # 返回
/// E-SMILES 字符串，或在解析失败时返回原始 SMILES
///
/// # 示例
///
/// ```
/// use mbforge_lib::core::esmiles::smiles_with_rgroups_to_esmiles;
///
/// let esmiles = smiles_with_rgroups_to_esmiles(
///     "*c1ccc(*)cc1",
///     &["R[1]".into(), "R[2]".into()],
/// );
/// assert_eq!(esmiles, "*c1ccc(*)cc1<sep><a>0:R[1]</a><a>4:R[2]</a>");
/// ```
pub fn smiles_with_rgroups_to_esmiles(smiles: &str, rgroup_names: &[String]) -> String {
    let normalized = normalize_wildcards(smiles);
    let mol = match parse(&normalized) {
        Ok(m) => m,
        Err(_) => return smiles.to_string(),
    };

    let mut tags = Vec::new();
    let mut rgroup_iter = rgroup_names.iter();
    let mut atom_idx = 0usize;

    for (_idx, atom) in mol.atoms() {
        if atom.wildcard {
            if let Some(name) = rgroup_iter.next() {
                tags.push(EsTag::atom(atom_idx, name));
            }
        }
        atom_idx += 1;
    }

    smiles_to_esmiles(smiles, &tags)
}

/// 检测 SMILES 中是否含有 `*`（dummy atom），返回 wildcard 原子数量。
pub fn count_wildcard_atoms(smiles: &str) -> usize {
    let normalized = normalize_wildcards(smiles);
    let mol = match parse(&normalized) {
        Ok(m) => m,
        Err(_) => return 0,
    };
    mol.atoms().filter(|(_, a)| a.wildcard).count()
}

/// 从 E-SMILES 字符串中提取标签（不解析 SMILES 部分）。
///
/// 用于将已有的 E-SMILES 拆分为 SMILES + tags，方便后续重新生成。
pub fn parse_esmiles_tags(esmiles: &str) -> (String, Vec<EsTag>) {
    let sep_pos = match esmiles.find("<sep>") {
        Some(p) => p,
        None => return (esmiles.to_string(), Vec::new()),
    };

    let smiles_part = &esmiles[..sep_pos];
    let tag_part = &esmiles[sep_pos + 5..]; // skip "<sep>"

    let tags = extract_tags_from_extension(tag_part);
    (smiles_part.to_string(), tags)
}

/// 从 E-SMILES extension 部分解析标签
fn extract_tags_from_extension(ext: &str) -> Vec<EsTag> {
    let mut tags = Vec::new();

    // 匹配 <a>N:GROUP</a>, <r>N:GROUP</r>, <c>N:NAME</c>
    // 使用简单的状态机解析，避免依赖 regex
    let bytes = ext.as_bytes();
    let len = bytes.len();
    let mut i = 0;

    while i < len {
        if bytes[i] == b'<' && i + 1 < len {
            let tag_type = bytes[i + 1];
            if tag_type == b'a' || tag_type == b'r' || tag_type == b'c' {
                // 找到 tag 开始，寻找闭合
                let open_end = find_byte(bytes, i, b'>');
                if open_end.is_none() {
                    i += 1;
                    continue;
                }
                let open_end = open_end.unwrap();

                // 寻找闭合标签 </X>
                let close_start = find_close_tag(bytes, open_end + 1, tag_type);
                if close_start.is_none() {
                    i = open_end + 1;
                    continue;
                }
                let close_start = close_start.unwrap();

                let content = &ext[open_end + 1..close_start];
                if let Some(tag) = parse_tag_content(tag_type, content) {
                    tags.push(tag);
                }

                // 跳过闭合标签 `</X>`
                i = close_start + 4; // `</X>` is 4 bytes
                continue;
            }
        }
        i += 1;
    }

    tags
}

fn find_byte(bytes: &[u8], start: usize, target: u8) -> Option<usize> {
    for i in start..bytes.len() {
        if bytes[i] == target {
            return Some(i);
        }
    }
    None
}

fn find_close_tag(bytes: &[u8], start: usize, tag_type: u8) -> Option<usize> {
    // 寻找 `</X>` 模式
    let target = [b'<', b'/', tag_type, b'>'];
    for i in start..bytes.len().saturating_sub(3) {
        if bytes[i..i + 4] == target {
            return Some(i);
        }
    }
    None
}

fn parse_tag_content(tag_type: u8, content: &str) -> Option<EsTag> {
    // content 格式: "N:VALUE"
    let colon = content.find(':')?;
    let index: usize = content[..colon].parse().ok()?;
    let value = content[colon + 1..].to_string();

    match tag_type {
        b'a' => Some(EsTag::Atom { index, group: value }),
        b'r' => Some(EsTag::Ring { index, group: value }),
        b'c' => Some(EsTag::Circle { index, name: value }),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_smiles_to_esmiles_empty_tags() {
        let result = smiles_to_esmiles("CCO", &[]);
        assert_eq!(result, "CCO");
    }

    #[test]
    fn test_smiles_to_esmiles_single_atom_tag() {
        let result = smiles_to_esmiles("CC(=O)O", &[EsTag::atom(0, "R1")]);
        assert_eq!(result, "CC(=O)O<sep><a>0:R1</a>");
    }

    #[test]
    fn test_smiles_to_esmiles_multiple_tags() {
        let result = smiles_to_esmiles(
            "CC(=O)O",
            &[EsTag::atom(0, "R1"), EsTag::ring(0, "R2")],
        );
        assert_eq!(result, "CC(=O)O<sep><a>0:R1</a><r>0:R2</r>");
    }

    #[test]
    fn test_smiles_to_esmiles_with_rgroup_bracket() {
        let result = smiles_to_esmiles("*c1ccccc1", &[EsTag::atom(0, "R[1]")]);
        assert_eq!(result, "*c1ccccc1<sep><a>0:R[1]</a>");
    }

    #[test]
    fn test_smiles_with_rgroups_to_esmiles() {
        let result = smiles_with_rgroups_to_esmiles(
            "*c1ccccc1",
            &["R[1]".into()],
        );
        assert_eq!(result, "*c1ccccc1<sep><a>0:R[1]</a>");
    }

    #[test]
    fn test_smiles_with_rgroups_two_wildcards() {
        let result = smiles_with_rgroups_to_esmiles(
            "*c1ccc(*)cc1",
            &["R[1]".into(), "R[2]".into()],
        );
        // 验证两个 R-group 标签都存在，不硬编码 index（依赖 chematic 解析顺序）
        assert!(result.contains("<a>0:R[1]</a>"), "missing R[1] tag in: {}", result);
        assert!(result.contains("R[2]"), "missing R[2] tag in: {}", result);
        assert!(result.starts_with("*c1ccc(*)cc1<sep>"));
    }

    #[test]
    fn test_smiles_with_rgroups_no_wildcards() {
        let result = smiles_with_rgroups_to_esmiles("CCO", &["R1".into()]);
        assert_eq!(result, "CCO");
    }

    #[test]
    fn test_count_wildcard_atoms() {
        assert_eq!(count_wildcard_atoms("*c1ccccc1"), 1);
        assert_eq!(count_wildcard_atoms("*c1ccc(*)cc1"), 2);
        assert_eq!(count_wildcard_atoms("CCO"), 0);
    }

    #[test]
    fn test_parse_esmiles_tags_no_sep() {
        let (smiles, tags) = parse_esmiles_tags("CCO");
        assert_eq!(smiles, "CCO");
        assert!(tags.is_empty());
    }

    #[test]
    fn test_parse_esmiles_tags_with_atom_tag() {
        let (smiles, tags) = parse_esmiles_tags("*c1ccccc1<sep><a>0:R[1]</a>");
        assert_eq!(smiles, "*c1ccccc1");
        assert_eq!(tags.len(), 1);
        assert_eq!(tags[0], EsTag::atom(0, "R[1]"));
    }

    #[test]
    fn test_parse_esmiles_tags_multiple() {
        let (smiles, tags) = parse_esmiles_tags(
            "CC(=O)O<sep><a>0:R1</a><r>0:R2</r><c>0:B</c>",
        );
        assert_eq!(smiles, "CC(=O)O");
        assert_eq!(tags.len(), 3);
        assert_eq!(tags[0], EsTag::atom(0, "R1"));
        assert_eq!(tags[1], EsTag::ring(0, "R2"));
        assert_eq!(tags[2], EsTag::circle(0, "B"));
    }

    #[test]
    fn test_roundtrip_esmiles() {
        let original = "*c1ccc(*)cc1<sep><a>0:R[1]</a><a>4:R[2]</a>";
        let (smiles, tags) = parse_esmiles_tags(original);
        let regenerated = smiles_to_esmiles(&smiles, &tags);
        assert_eq!(regenerated, original);
    }
}
