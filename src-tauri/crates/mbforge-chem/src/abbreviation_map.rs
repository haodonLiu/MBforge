//! 化学缩写展开映射表
//!
//! 移植自 MoleCode 的 `abbreviation_map.py`，提供：
//! - `SINGLE_ATOM_MAP`：单原子等价映射（Me→CH3, Et→CH2...）
//! - `SUBGRAPH_MAP`：多原子子图展开（Boc, Cbz, Ph, CF3...）
//! - `NON_EXPANDABLE`：不可展开的占位符（R, R1-R17, X, Y, Z...）
//! - `normalize_abbrev_name()`：缩写名称归一化
//!
//! 用于 Markush 结构匹配时的缩写感知比较。

use std::collections::HashMap;
use std::sync::LazyLock;

use regex::Regex;

// ============================================================================
// 数据类型
// ============================================================================

/// 缩写定义
#[derive(Debug, Clone)]
pub enum AbbrevDef {
    /// 单原子等价：Me → CH3
    SingleAtom(&'static str),
    /// 多原子子图：Boc → OC(=O)C(C)(C)C
    Subgraph(SubgraphDef),
    /// 不可展开的占位符：R1, R2, X, Y, Z...
    NonExpandable,
}

/// 多原子子图定义
#[derive(Debug, Clone)]
pub struct SubgraphDef {
    pub atoms: &'static [(&'static str, &'static str)],
    pub bonds: &'static [(&'static str, &'static str, &'static str)],
    pub attach: &'static str,
}

// ============================================================================
// 单原子映射表
// ============================================================================

fn build_single_atom_map() -> HashMap<&'static str, &'static str> {
    let mut m = HashMap::new();
    // 烷基
    m.insert("Me", "CH3");
    m.insert("CH3", "CH3");
    m.insert("Et", "CH2");
    m.insert("CH2CH3", "CH2");
    // 卤素 / 小基团
    m.insert("F", "F");
    m.insert("Cl", "Cl");
    m.insert("Br", "Br");
    m.insert("I", "I");
    // 功能团
    m.insert("CN", "C");
    m.insert("NC", "N");
    m.insert("N3", "N");
    m.insert("NO", "N");
    m.insert("CHO", "CH");
    // 带电原子
    m.insert("NH3+", "NH3(+)");
    m.insert("NH2+", "NH2(+)");
    m.insert("O-", "O(-)");
    m.insert("N+", "N(+)");
    m.insert("SO3-", "S");
    // 基础元素
    m.insert("H", "H");
    m.insert("N", "N");
    m.insert("C", "C");
    m.insert("O", "O");
    m.insert("B", "B");
    m.insert("OH", "OH");
    m
}

// ============================================================================
// 多原子子图映射表
// ============================================================================

#[allow(clippy::unwrap_used)] // aliases reference keys inserted just above; guaranteed present
fn build_subgraph_map() -> HashMap<&'static str, SubgraphDef> {
    let mut m = HashMap::new();

    // Boc: t-Butyloxycarbonyl
    m.insert(
        "Boc",
        SubgraphDef {
            atoms: &[
                ("C1", "C"),
                ("O1", "O"),
                ("O2", "O"),
                ("C2", "C"),
                ("C3", "CH3"),
                ("C4", "CH3"),
                ("C5", "CH3"),
            ],
            bonds: &[
                ("C1", "O1", "==="),
                ("C1", "O2", "---"),
                ("O2", "C2", "---"),
                ("C2", "C3", "---"),
                ("C2", "C4", "---"),
                ("C2", "C5", "---"),
            ],
            attach: "C1",
        },
    );
    m.insert("BOC", m.get("Boc").unwrap().clone());
    m.insert("boc", m.get("Boc").unwrap().clone());

    // Cbz: Benzyloxycarbonyl
    m.insert(
        "Cbz",
        SubgraphDef {
            atoms: &[
                ("C1", "C"),
                ("O1", "O"),
                ("O2", "O"),
                ("C2", "CH2"),
                ("C3", "C"),
                ("C4", "CH"),
                ("C5", "CH"),
                ("C6", "CH"),
                ("C7", "CH"),
                ("C8", "CH"),
            ],
            bonds: &[
                ("C1", "O1", "==="),
                ("C1", "O2", "---"),
                ("O2", "C2", "---"),
                ("C2", "C3", "---"),
                ("C3", "C4", "==="),
                ("C4", "C5", "---"),
                ("C5", "C6", "==="),
                ("C6", "C7", "---"),
                ("C7", "C8", "==="),
                ("C8", "C3", "---"),
            ],
            attach: "C1",
        },
    );

    // Ac: Acetyl
    m.insert(
        "Ac",
        SubgraphDef {
            atoms: &[("C1", "C"), ("O1", "O"), ("C2", "CH3")],
            bonds: &[("C1", "O1", "==="), ("C1", "C2", "---")],
            attach: "C1",
        },
    );

    // Ts: Tosyl
    m.insert(
        "Ts",
        SubgraphDef {
            atoms: &[
                ("S1", "S"),
                ("O1", "O"),
                ("O2", "O"),
                ("C1", "C"),
                ("C2", "CH"),
                ("C3", "CH"),
                ("C4", "C"),
                ("C5", "CH"),
                ("C6", "CH"),
                ("C7", "CH3"),
            ],
            bonds: &[
                ("S1", "O1", "==="),
                ("S1", "O2", "==="),
                ("S1", "C1", "---"),
                ("C1", "C2", "==="),
                ("C2", "C3", "---"),
                ("C3", "C4", "==="),
                ("C4", "C5", "---"),
                ("C5", "C6", "==="),
                ("C6", "C1", "---"),
                ("C4", "C7", "---"),
            ],
            attach: "S1",
        },
    );
    m.insert("Tos", m.get("Ts").unwrap().clone());

    // Ph: Phenyl
    m.insert(
        "Ph",
        SubgraphDef {
            atoms: &[
                ("C1", "C"),
                ("C2", "CH"),
                ("C3", "CH"),
                ("C4", "CH"),
                ("C5", "CH"),
                ("C6", "CH"),
            ],
            bonds: &[
                ("C1", "C2", "==="),
                ("C2", "C3", "---"),
                ("C3", "C4", "==="),
                ("C4", "C5", "---"),
                ("C5", "C6", "==="),
                ("C6", "C1", "---"),
            ],
            attach: "C1",
        },
    );

    // Bn: Benzyl
    m.insert(
        "Bn",
        SubgraphDef {
            atoms: &[
                ("C0", "CH2"),
                ("C1", "C"),
                ("C2", "CH"),
                ("C3", "CH"),
                ("C4", "CH"),
                ("C5", "CH"),
                ("C6", "CH"),
            ],
            bonds: &[
                ("C0", "C1", "---"),
                ("C1", "C2", "==="),
                ("C2", "C3", "---"),
                ("C3", "C4", "==="),
                ("C4", "C5", "---"),
                ("C5", "C6", "==="),
                ("C6", "C1", "---"),
            ],
            attach: "C0",
        },
    );

    // CF3
    m.insert(
        "CF3",
        SubgraphDef {
            atoms: &[("C1", "C"), ("F1", "F"), ("F2", "F"), ("F3", "F")],
            bonds: &[
                ("C1", "F1", "---"),
                ("C1", "F2", "---"),
                ("C1", "F3", "---"),
            ],
            attach: "C1",
        },
    );

    // CHF2
    m.insert(
        "CHF2",
        SubgraphDef {
            atoms: &[("C1", "CH"), ("F1", "F"), ("F2", "F")],
            bonds: &[("C1", "F1", "---"), ("C1", "F2", "---")],
            attach: "C1",
        },
    );

    // OCF3
    m.insert(
        "OCF3",
        SubgraphDef {
            atoms: &[
                ("O1", "O"),
                ("C1", "C"),
                ("F1", "F"),
                ("F2", "F"),
                ("F3", "F"),
            ],
            bonds: &[
                ("O1", "C1", "---"),
                ("C1", "F1", "---"),
                ("C1", "F2", "---"),
                ("C1", "F3", "---"),
            ],
            attach: "O1",
        },
    );

    // OMe / OCH3 / MeO
    m.insert(
        "OMe",
        SubgraphDef {
            atoms: &[("O1", "O"), ("C1", "CH3")],
            bonds: &[("O1", "C1", "---")],
            attach: "O1",
        },
    );
    m.insert("OCH3", m.get("OMe").unwrap().clone());
    m.insert("MeO", m.get("OMe").unwrap().clone());

    // OEt
    m.insert(
        "OEt",
        SubgraphDef {
            atoms: &[("O1", "O"), ("C1", "CH2"), ("C2", "CH3")],
            bonds: &[("O1", "C1", "---"), ("C1", "C2", "---")],
            attach: "O1",
        },
    );

    // OAc
    m.insert(
        "OAc",
        SubgraphDef {
            atoms: &[("O1", "O"), ("C1", "C"), ("O2", "O"), ("C2", "CH3")],
            bonds: &[
                ("O1", "C1", "---"),
                ("C1", "O2", "==="),
                ("C1", "C2", "---"),
            ],
            attach: "O1",
        },
    );

    // OBn
    m.insert(
        "OBn",
        SubgraphDef {
            atoms: &[
                ("O1", "O"),
                ("C0", "CH2"),
                ("C1", "C"),
                ("C2", "CH"),
                ("C3", "CH"),
                ("C4", "CH"),
                ("C5", "CH"),
                ("C6", "CH"),
            ],
            bonds: &[
                ("O1", "C0", "---"),
                ("C0", "C1", "---"),
                ("C1", "C2", "==="),
                ("C2", "C3", "---"),
                ("C3", "C4", "==="),
                ("C4", "C5", "---"),
                ("C5", "C6", "==="),
                ("C6", "C1", "---"),
            ],
            attach: "O1",
        },
    );

    // NO2
    m.insert(
        "NO2",
        SubgraphDef {
            atoms: &[("N1", "N(+)"), ("O1", "O"), ("O2", "O(-)")],
            bonds: &[("N1", "O1", "==="), ("N1", "O2", "---")],
            attach: "N1",
        },
    );

    // COOH / CO2H
    m.insert(
        "COOH",
        SubgraphDef {
            atoms: &[("C1", "C"), ("O1", "O"), ("O2", "OH")],
            bonds: &[("C1", "O1", "==="), ("C1", "O2", "---")],
            attach: "C1",
        },
    );
    m.insert("CO2H", m.get("COOH").unwrap().clone());

    // COOMe / CO2Me
    m.insert(
        "COOMe",
        SubgraphDef {
            atoms: &[("C1", "C"), ("O1", "O"), ("O2", "O"), ("C2", "CH3")],
            bonds: &[
                ("C1", "O1", "==="),
                ("C1", "O2", "---"),
                ("O2", "C2", "---"),
            ],
            attach: "C1",
        },
    );
    m.insert("CO2Me", m.get("COOMe").unwrap().clone());
    m.insert("COOCH3", m.get("COOMe").unwrap().clone());

    // COOEt / CO2Et
    m.insert(
        "COOEt",
        SubgraphDef {
            atoms: &[
                ("C1", "C"),
                ("O1", "O"),
                ("O2", "O"),
                ("C2", "CH2"),
                ("C3", "CH3"),
            ],
            bonds: &[
                ("C1", "O1", "==="),
                ("C1", "O2", "---"),
                ("O2", "C2", "---"),
                ("C2", "C3", "---"),
            ],
            attach: "C1",
        },
    );
    m.insert("CO2Et", m.get("COOEt").unwrap().clone());

    // NHBoc
    m.insert(
        "NHBoc",
        SubgraphDef {
            atoms: &[
                ("N1", "NH"),
                ("C1", "C"),
                ("O1", "O"),
                ("O2", "O"),
                ("C2", "C"),
                ("C3", "CH3"),
                ("C4", "CH3"),
                ("C5", "CH3"),
            ],
            bonds: &[
                ("N1", "C1", "---"),
                ("C1", "O1", "==="),
                ("C1", "O2", "---"),
                ("O2", "C2", "---"),
                ("C2", "C3", "---"),
                ("C2", "C4", "---"),
                ("C2", "C5", "---"),
            ],
            attach: "N1",
        },
    );

    // NHAc / AcHN
    m.insert(
        "NHAc",
        SubgraphDef {
            atoms: &[("N1", "NH"), ("C1", "C"), ("O1", "O"), ("C2", "CH3")],
            bonds: &[
                ("N1", "C1", "---"),
                ("C1", "O1", "==="),
                ("C1", "C2", "---"),
            ],
            attach: "N1",
        },
    );
    m.insert("AcHN", m.get("NHAc").unwrap().clone());

    // NHMe
    m.insert(
        "NHMe",
        SubgraphDef {
            atoms: &[("N1", "NH"), ("C1", "CH3")],
            bonds: &[("N1", "C1", "---")],
            attach: "N1",
        },
    );

    // NMe2
    m.insert(
        "NMe2",
        SubgraphDef {
            atoms: &[("N1", "N"), ("C1", "CH3"), ("C2", "CH3")],
            bonds: &[("N1", "C1", "---"), ("N1", "C2", "---")],
            attach: "N1",
        },
    );

    // NHOH
    m.insert(
        "NHOH",
        SubgraphDef {
            atoms: &[("N1", "NH"), ("O1", "OH")],
            bonds: &[("N1", "O1", "---")],
            attach: "N1",
        },
    );

    // SMe
    m.insert(
        "SMe",
        SubgraphDef {
            atoms: &[("S1", "S"), ("C1", "CH3")],
            bonds: &[("S1", "C1", "---")],
            attach: "S1",
        },
    );

    // SO2Me
    m.insert(
        "SO2Me",
        SubgraphDef {
            atoms: &[("S1", "S"), ("O1", "O"), ("O2", "O"), ("C1", "CH3")],
            bonds: &[
                ("S1", "O1", "==="),
                ("S1", "O2", "==="),
                ("S1", "C1", "---"),
            ],
            attach: "S1",
        },
    );

    // SO3H
    m.insert(
        "SO3H",
        SubgraphDef {
            atoms: &[("S1", "S"), ("O1", "O"), ("O2", "O"), ("O3", "OH")],
            bonds: &[
                ("S1", "O1", "==="),
                ("S1", "O2", "==="),
                ("S1", "O3", "---"),
            ],
            attach: "S1",
        },
    );

    // TMS
    m.insert(
        "TMS",
        SubgraphDef {
            atoms: &[("Si1", "Si"), ("C1", "CH3"), ("C2", "CH3"), ("C3", "CH3")],
            bonds: &[
                ("Si1", "C1", "---"),
                ("Si1", "C2", "---"),
                ("Si1", "C3", "---"),
            ],
            attach: "Si1",
        },
    );

    // tBu
    m.insert(
        "tBu",
        SubgraphDef {
            atoms: &[("C1", "C"), ("C2", "CH3"), ("C3", "CH3"), ("C4", "CH3")],
            bonds: &[
                ("C1", "C2", "---"),
                ("C1", "C3", "---"),
                ("C1", "C4", "---"),
            ],
            attach: "C1",
        },
    );

    // iPr
    m.insert(
        "iPr",
        SubgraphDef {
            atoms: &[("C1", "CH"), ("C2", "CH3"), ("C3", "CH3")],
            bonds: &[("C1", "C2", "---"), ("C1", "C3", "---")],
            attach: "C1",
        },
    );

    // Bz: Benzoyl
    m.insert(
        "Bz",
        SubgraphDef {
            atoms: &[
                ("C1", "C"),
                ("O1", "O"),
                ("C2", "C"),
                ("C3", "CH"),
                ("C4", "CH"),
                ("C5", "CH"),
                ("C6", "CH"),
                ("C7", "CH"),
            ],
            bonds: &[
                ("C1", "O1", "==="),
                ("C1", "C2", "---"),
                ("C2", "C3", "==="),
                ("C3", "C4", "---"),
                ("C4", "C5", "==="),
                ("C5", "C6", "---"),
                ("C6", "C7", "==="),
                ("C7", "C2", "---"),
            ],
            attach: "C1",
        },
    );

    // CONH2
    m.insert(
        "CONH2",
        SubgraphDef {
            atoms: &[("C1", "C"), ("O1", "O"), ("N1", "NH2")],
            bonds: &[("C1", "O1", "==="), ("C1", "N1", "---")],
            attach: "C1",
        },
    );

    // SO2
    m.insert(
        "SO2",
        SubgraphDef {
            atoms: &[("S1", "S"), ("O1", "O"), ("O2", "O")],
            bonds: &[("S1", "O1", "==="), ("S1", "O2", "===")],
            attach: "S1",
        },
    );

    m
}

// ============================================================================
// 不可展开缩写集合
// ============================================================================

fn build_non_expandable() -> Vec<&'static str> {
    vec![
        "R",
        "R1",
        "R2",
        "R3",
        "R4",
        "R5",
        "R6",
        "R7",
        "R8",
        "R9",
        "R10",
        "R11",
        "R12",
        "R13",
        "R14",
        "R15",
        "R16",
        "R17",
        "R1a",
        "R1b",
        "R2a",
        "R2b",
        "R3a",
        "R4a",
        "R5a",
        "R'",
        "Ra",
        "Rb",
        "Rf",
        "Rg",
        "X",
        "X1",
        "Y",
        "Y1",
        "Z",
        "Z1",
        "Z2",
        "W",
        "A",
        "A1",
        "A2",
        "B",
        "B1",
        "D",
        "E",
        "Q",
        "Q1",
        "Q2",
        "Ar",
        "Ar1",
        "Ar2",
        "PG",
        "FG",
        "Alkyl",
        "Cyc",
        "Chx",
        "dum",
        "(CH2)n",
        "(CH2)x",
        "(CH2)m-1",
        "CH[2]n",
        "CH[2]?n",
        "CH2n",
        "CH2?n",
        "CH2?x",
        "CH2",
        "(R1)n",
        "(R5)t",
        "()n",
        "R1?n",
        "X(CH2)n",
        "[OCH2CH2]2",
        "OCH2CH22",
        "HX",
        "NR",
        "ORd",
        "Rd",
        "G2",
        "G3",
        "G4",
        "x",
        "O(N)",
        "X/B(OH)2",
        "PG1",
        "PG1N",
        "PG2",
        "NPG2",
        "RN1",
        "R27",
        "Y8",
        "X1Z",
    ]
}

// ============================================================================
// 名称归一化
// ============================================================================

#[allow(clippy::expect_used)] // regex is static and validated at compile time
static BRACKET_DIGITS_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[(\d+)\]").expect("valid bracket digits regex"));
#[allow(clippy::expect_used)] // regex is static and validated at compile time
static CHAIN_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"CH\[2\](?:\?[nx])?|CH2(?:\?[nx])?").expect("valid chain regex"));

/// 缩写名称归一化
///
/// 处理：方括号、Unicode 上下标、大小写、同义词、尾部标点
pub fn normalize_abbrev_name(name: &str) -> String {
    let mut s = name.trim().to_string();

    // 1. 去 ^
    s = s.replace('^', "");

    // 2. 去方括号数字：R[1] → R1
    s = BRACKET_DIGITS_RE.replace_all(&s, "$1").to_string();

    // 3. Unicode 上下标转 ASCII
    s = s.replace('⁰', "0").replace('¹', "1").replace('²', "2");
    s = s.replace('³', "3").replace('⁴', "4").replace('⁵', "5");
    s = s.replace('⁶', "6").replace('⁷', "7").replace('⁸', "8");
    s = s.replace('⁹', "9");
    s = s.replace('₀', "0").replace('₁', "1").replace('₂', "2");
    s = s.replace('₃', "3").replace('₄', "4").replace('₅', "5");
    s = s.replace('₆', "6").replace('₇', "7").replace('₈', "8");
    s = s.replace('₉', "9");

    // 4. 变量链归一化
    s = CHAIN_RE.replace_all(&s, "(CH2)n").to_string();

    // 5. 大小写归一化
    let lower = s.to_lowercase();
    let case_map: &[(&str, &str)] = &[
        ("boc", "Boc"),
        ("cbz", "Cbz"),
        ("fmoc", "Fmoc"),
        ("tbdms", "TBDMS"),
        ("tms", "TMS"),
        ("ac", "Ac"),
        ("ts", "Ts"),
        ("tf", "Tf"),
        ("me", "Me"),
        ("et", "Et"),
        ("ph", "Ph"),
        ("bn", "Bn"),
        ("ome", "OMe"),
        ("oet", "OEt"),
        ("oac", "OAc"),
        ("obn", "OBn"),
    ];
    for &(from, to) in case_map {
        if lower == from {
            return to.to_string();
        }
    }

    // 6. 同义词归一化
    let synonym_map: &[(&str, &str)] = &[
        ("CO2R", "COOR"),
        ("COOMe", "CO2Me"),
        ("COOEt", "CO2Et"),
        ("COOCH3", "CO2Me"),
        ("CO2H", "COOH"),
        ("MeO", "OMe"),
        ("OCH3", "OMe"),
        ("EtO", "OEt"),
        ("AcHN", "NHAc"),
        ("MeO2C", "CO2Me"),
        ("O2N", "NO2"),
        ("Tos", "Ts"),
        ("BOC", "Boc"),
    ];
    for &(from, to) in synonym_map {
        if s == from {
            return to.to_string();
        }
    }

    // 7. 去尾部标点
    s = s.trim_end_matches([',', '.', ' ']).to_string();

    s
}

// ============================================================================
// 公共 API
// ============================================================================

/// 全局缩写展开映射（懒加载）
pub fn get_abbrev_map() -> &'static HashMap<&'static str, AbbrevDef> {
    use std::sync::OnceLock;
    static MAP: OnceLock<HashMap<&'static str, AbbrevDef>> = OnceLock::new();
    MAP.get_or_init(|| {
        let mut m = HashMap::new();

        // 单原子映射
        for (k, v) in build_single_atom_map() {
            m.insert(k, AbbrevDef::SingleAtom(v));
        }

        // 多原子子图
        for (k, v) in build_subgraph_map() {
            m.insert(k, AbbrevDef::Subgraph(v));
        }

        // 不可展开
        for k in build_non_expandable() {
            m.insert(k, AbbrevDef::NonExpandable);
        }

        m
    })
}

/// 查找缩写定义（归一化后查找）
pub fn find_abbrev(name: &str) -> Option<&'static AbbrevDef> {
    let normalized = normalize_abbrev_name(name);
    let map = get_abbrev_map();

    // 直接查找
    if let Some(def) = map.get(normalized.as_str()) {
        return Some(def);
    }

    // 大小写不敏感查找
    let lower = normalized.to_lowercase();
    for (k, v) in map.iter() {
        if k.to_lowercase() == lower {
            return Some(v);
        }
    }

    None
}

/// 检查是否为不可展开的占位符
#[allow(dead_code)] // public API; currently exercised only in unit tests
pub fn is_non_expandable(name: &str) -> bool {
    matches!(find_abbrev(name), Some(AbbrevDef::NonExpandable))
}

/// 获取单原子等价标签
pub fn get_single_atom_label(name: &str) -> Option<&'static str> {
    match find_abbrev(name) {
        Some(AbbrevDef::SingleAtom(label)) => Some(label),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_bracket_digits() {
        assert_eq!(normalize_abbrev_name("R[1]"), "R1");
        assert_eq!(normalize_abbrev_name("R[2]"), "R2");
    }

    #[test]
    fn test_normalize_caret() {
        assert_eq!(normalize_abbrev_name("R^1"), "R1");
        assert_eq!(normalize_abbrev_name("R^a"), "Ra");
    }

    #[test]
    fn test_normalize_case() {
        assert_eq!(normalize_abbrev_name("boc"), "Boc");
        assert_eq!(normalize_abbrev_name("cbz"), "Cbz");
        assert_eq!(normalize_abbrev_name("Boc"), "Boc");
    }

    #[test]
    fn test_normalize_synonym() {
        assert_eq!(normalize_abbrev_name("OCH3"), "OMe");
        assert_eq!(normalize_abbrev_name("MeO"), "OMe");
        assert_eq!(normalize_abbrev_name("CO2H"), "COOH");
        assert_eq!(normalize_abbrev_name("Tos"), "Ts");
    }

    #[test]
    fn test_normalize_trailing_punct() {
        assert_eq!(normalize_abbrev_name("B5,"), "B5");
        assert_eq!(normalize_abbrev_name("R1."), "R1");
    }

    #[test]
    fn test_find_abbrev_boc() {
        let def = find_abbrev("Boc");
        assert!(matches!(def, Some(AbbrevDef::Subgraph(_))));
    }

    #[test]
    fn test_find_abbrev_me() {
        let label = get_single_atom_label("Me");
        assert_eq!(label, Some("CH3"));
    }

    #[test]
    fn test_is_non_expandable() {
        assert!(is_non_expandable("R1"));
        assert!(is_non_expandable("X"));
        assert!(is_non_expandable("Ar"));
        assert!(!is_non_expandable("Boc"));
        assert!(!is_non_expandable("Me"));
    }

    #[test]
    fn test_find_abbrev_case_insensitive() {
        // boc 归一化后为 Boc
        let def = find_abbrev("boc");
        assert!(matches!(def, Some(AbbrevDef::Subgraph(_))));
    }
}
