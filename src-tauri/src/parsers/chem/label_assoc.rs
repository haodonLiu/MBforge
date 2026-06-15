//! 文本-图像关联：在分子 bbox 邻域找化合物/章节标号
//!
//! 端口自原 Python 实现（`backends/moldet.py::find_label_for_bbox`）。
//! 之所以放在 Rust 而不是 Python sidecar：
//!   - text_line 已经在 PDF 解析阶段从 lopdf/pdf_inspector 拿到了，
//!     重复解析一次是浪费
//!   - regex 是纯文本处理，跟 ML 推理不在一个抽象层
//!   - 单测不需要起 PDF，纯文本+坐标即可
//!
//! 坐标系约定（与 Python 版一致）：
//!   - `mol_bbox_pdf` 参数：`(x1, y1, x2, y2)`，PDF 坐标系，**左下原点**，PDF 点单位
//!   - `TextLine::bbox`：`(x0, y0, x1, y1)`，**顶左原点**，PDF 点单位
//!
//! 中文/英文专利常见标号都被覆盖；使用 lookahead 等价物（match 后校验终止符）
//! 排除化学名中的假阳性 "化合物6-氯-2-甲基-..."。

use std::sync::OnceLock;

use regex::Regex;

/// 一行 PDF 文本（顶左原点，PDF 点单位）。
#[derive(Debug, Clone, PartialEq)]
pub struct TextLine {
    /// `(x0, y0, x1, y1)`，**顶左原点**，PDF 点单位
    pub bbox: [f64; 4],
    pub text: String,
}

/// label 匹配结果
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct LabelMatch {
    /// 抽取出的标识符字符串（含前导词），如 "化合物 26A"、"第一步"
    pub label: String,
    /// 匹配到的完整文本行（截断到 200 字符）
    pub context_text: String,
}

// ---------------------------------------------------------------------------
// 模式表
// ---------------------------------------------------------------------------

/// 化合物/中间体/产物类（高优先级）。捕获组 1 是标识符。
///
/// 注意：regex crate 不支持 lookaround，所以下面 `_with_term` 变体里我们
/// 匹配完再手工校验紧跟标识符的字符是不是终止符。
//  (前导词,  pattern (含两个捕获组：标识符 + 后续字符),  类型标签)
const LABEL_PATTERNS_ZH: &[(&str, &str)] = &[
    (
        "化合物",
        r"化合物\s*([A-Za-z]?\d+[A-Za-z]?(?:[-‐‑–—]\d+[A-Za-z]?)?)",
    ),
    (
        "中间体",
        r"中间体\s*([A-Za-z]?\d+[A-Za-z]?(?:[-‐‑–—]\d+[A-Za-z]?)?)",
    ),
    ("产物", r"产物\s*([A-Za-z]?\d+[A-Za-z]?)"),
    ("起始物料", r"起始\s*物料\s*([A-Za-z]?\d+[A-Za-z]?)"),
    ("原料", r"原料\s*([A-Za-z]?\d+[A-Za-z]?)"),
];
const LABEL_PATTERNS_EN: &[(&str, &str)] = &[
    ("Compound", r"Compound\s*([A-Za-z]?\d+[A-Za-z]?)"),
    ("Intermediate", r"Intermediate\s*([A-Za-z]?\d+[A-Za-z]?)"),
    ("Product", r"Product\s*([A-Za-z]?\d+[A-Za-z]?)"),
];
// 章节/图表类（fallback 上下文信号）。这些标号本身就在句末，不需要终止符校验。
const SECTION_PATTERNS: &[(&str, &str)] = &[
    ("实施例", r"实施例\s*(\d+)"),
    ("Example", r"Example\s*(\d+)"),
    ("Scheme", r"Scheme\s*(\d+)"),
    ("Figure", r"Figure\s*(\d+)"),
    ("Step", r"Step\s*(\d+)"),
    ("第N步", r"第[一二三四五六七八九十]+\s*步"),
];

/// 编译后的 regex 缓存。
struct CompiledPatterns {
    zh: Vec<(&'static str, Regex)>,
    en: Vec<(&'static str, Regex)>,
    section: Vec<(&'static str, Regex)>,
}

static COMPILED: OnceLock<CompiledPatterns> = OnceLock::new();

fn compiled() -> &'static CompiledPatterns {
    COMPILED.get_or_init(|| {
        let compile = |table: &[(&'static str, &'static str)]| {
            table
                .iter()
                .map(|(name, pat)| {
                    (
                        *name,
                        Regex::new(pat).unwrap_or_else(|e| {
                            panic!("invalid label regex {name:?} ({pat:?}): {e}")
                        }),
                    )
                })
                .collect()
        };
        CompiledPatterns {
            zh: compile(LABEL_PATTERNS_ZH),
            en: compile(LABEL_PATTERNS_EN),
            section: compile(SECTION_PATTERNS),
        }
    })
}

// ---------------------------------------------------------------------------
// 终止符校验（lookaround 等价物）
// ---------------------------------------------------------------------------

/// 标识符后允许的"终止字符"。`None` 表示到字符串末尾。
fn is_terminator(c: Option<char>) -> bool {
    match c {
        None => true,
        Some(' ' | '\t' | '\n' | '\r') => true,
        Some('的' | '，' | '。' | '；' | '、' | '(' | ')') => true,
        Some('（' | '）') => true,
        _ => false,
    }
}

/// 在文本中尝试用 `re` 匹配"前导词 + 标识符"。匹配后必须满足：
///   1. 紧跟标识符的字符是终止符（空白/标点/EOS）
///   2. 标识符至少 1 个字符
///
/// 返回 `Some((label_text, identifier))` 或 `None`。
fn match_label(re: &Regex, text: &str) -> Option<(String, String)> {
    let caps = re.captures(text)?;
    let id_m = caps.get(1)?;
    let id = id_m.as_str();
    if id.is_empty() {
        return None;
    }
    let after = text[id_m.end()..].chars().next();
    if !is_terminator(after) {
        return None;
    }
    let full = caps.get(0)?;
    Some((full.as_str().trim().to_string(), id.to_string()))
}

// ---------------------------------------------------------------------------
// 主函数
// ---------------------------------------------------------------------------

/// 在分子 bbox 正上方的文本行里找化合物/章节标号。
///
/// # Arguments
/// - `mol_bbox_pdf`: `(x1, y1, x2, y2)`，PDF 坐标系，**左下原点**，PDF 点单位
/// - `text_lines`: 候选文本行，顶左原点
/// - `page_h_pts`: PDF 页面高度（点单位），用于坐标方向转换
/// - `v_search_pts`: 向上搜索的最大垂直距离（点单位，默认 80）
///
/// # Returns
/// - `Some(LabelMatch)`：命中
/// - `None`：无候选
///
/// 优先级：化合物类（ZH+EN） > 章节类。同一类中取**最靠近 bbox 顶部**的。
pub fn find_label_for_bbox(
    mol_bbox_pdf: (f64, f64, f64, f64),
    text_lines: &[TextLine],
    page_h_pts: f64,
    v_search_pts: f64,
) -> Option<LabelMatch> {
    let (x1, y1, x2, y2) = mol_bbox_pdf;
    // bbox 顶边在 top-left 坐标系的 y
    let ml_top = page_h_pts - y2;
    // bbox 底边在 top-left 坐标系的 y（用于过滤掉 bbox 下方的行）
    let ml_bot = page_h_pts - y1;
    let _ = (x1, x2, ml_bot); // 横坐标和底边用不到，先保留字段

    let c = compiled();

    // 候选：(gap, label, context_text)
    // 优先化合物类；同一类中按 gap 最小（即最靠近 bbox 顶部）选择。
    let mut best_label: Option<(f64, String, String)> = None;
    let mut best_section: Option<(f64, String, String)> = None;

    for line in text_lines {
        let line_text = line.text.trim();
        if line_text.is_empty() {
            continue;
        }
        let (_, _ly0, _, ly1) = (line.bbox[0], line.bbox[1], line.bbox[2], line.bbox[3]);
        // 行必须在 bbox 之上（ly1 ≤ ml_top）
        if ly1 > ml_top + 2.0 {
            continue;
        }
        let gap = ml_top - ly1;
        if gap > v_search_pts {
            continue;
        }
        // 化合物类（先 ZH 后 EN，取首个命中）
        for (name, re) in c.zh.iter().chain(c.en.iter()) {
            if let Some((label, _id)) = match_label(re, line_text) {
                let candidate = (gap, label.clone(), truncate(&line.text, 200));
                match &best_label {
                    None => best_label = Some(candidate),
                    Some((g, _, _)) if gap < *g => best_label = Some(candidate),
                    _ => {}
                }
                let _ = name;
                break; // 一行只取首个化合物类匹配
            }
        }
        // 章节类
        for (_name, re) in c.section.iter() {
            if let Some(caps) = re.captures(line_text) {
                if let Some(m) = caps.get(0) {
                    let candidate = (
                        gap,
                        m.as_str().trim().to_string(),
                        truncate(&line.text, 200),
                    );
                    match &best_section {
                        None => best_section = Some(candidate),
                        Some((g, _, _)) if gap < *g => best_section = Some(candidate),
                        _ => {}
                    }
                    break;
                }
            }
        }
    }

    let chosen = best_label.or(best_section)?;
    Some(LabelMatch {
        label: chosen.1,
        context_text: chosen.2,
    })
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        let mut out: String = s.chars().take(max).collect();
        out.push('\u{2026}');
        out
    }
}

// ---------------------------------------------------------------------------
// Page text-line extraction (thin wrapper over pdf_inspector)
// ---------------------------------------------------------------------------

/// 从 PDF 提取指定页的文本行（顶左原点，PDF 点单位）。
///
/// 内部使用 `pdf_inspector::extractor::extract_text_with_positions_and_rects`
/// + `group_into_lines`，把每个 line 投影为 (x0, y0, x1, y1, text)。
///
/// # Arguments
/// - `pdf_path`: PDF 文件路径
/// - `page_num`: 1-indexed 页码
/// - `page_h_pts`: 页面高度（点单位），用于坐标方向转换
///
/// # Returns
/// - `Ok(Vec<TextLine>)`：该页所有文本行（空文本行被过滤）
/// - `Err(String)`：PDF 解析失败
///
/// 注：这是一个较重的调用（整个 PDF 解析一次），调用方应缓存或复用。
/// `find_label_for_bbox` 接受任意 `&[TextLine]`，所以本函数也可以只调用一次
/// 拿所有页，再按页号过滤。
pub fn extract_page_text_lines(
    pdf_path: &str,
    page_num: u32,
    page_h_pts: f64,
) -> Result<Vec<TextLine>, String> {
    use pdf_inspector::extractor::extract_text_with_positions_pages;
    use pdf_inspector::extractor::group_into_lines;
    use std::collections::HashSet;

    let page_filter: HashSet<u32> = [page_num].into_iter().collect();
    let items = extract_text_with_positions_pages(pdf_path, Some(&page_filter))
        .map_err(|e| format!("pdf_inspector text extraction failed: {e}"))?;

    let pdf_lines = group_into_lines(items);
    let mut out = Vec::new();
    for line in pdf_lines {
        // 只保留请求的页
        if line.page != page_num {
            continue;
        }
        let text = line.text();
        let text = text.trim();
        if text.is_empty() {
            continue;
        }
        // line.y 是该 line 的 y 坐标 (bottom-left, PDF points)
        // line.items[0].x 是起始 x，items[last].x + last.width 是结束 x
        // line.items[0].y 是 baseline，但我们用 height 近似
        // 简化：取第一个 item 的 x 和 最后一个 item 的 x+width
        if let (Some(first), Some(last)) = (line.items.first(), line.items.last()) {
            let x0 = first.x as f64;
            let x1 = (last.x + last.width) as f64;
            // line.y 是 baseline (bottom-left)，近似为 line 的 y 中心
            // 用 line.items[0].y 作为底线，height 作为 line 高度估算
            let baseline = first.y as f64;
            let height = first.height as f64;
            // 顶左原点：top_y = page_h - (baseline + height),  bottom_y = page_h - baseline
            let y0 = page_h_pts - (baseline + height);
            let y1 = page_h_pts - baseline;
            out.push(TextLine {
                bbox: [x0, y0.max(0.0), x1, y1.max(0.0)],
                text: text.to_string(),
            });
        }
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// 单测
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// 固定 page_h=842。
    ///
    /// 约定：text line bbox 在 top-left 坐标系中给出 (y 向下)。
    /// `find_label_for_bbox` 接收的 `mol_bbox_pdf` 在 bottom-left 坐标系。
    ///
    /// 常用 fixture:
    ///   molecule bbox (PDF bottom-left): y1=400 (bottom), y2=500 (top)
    ///   -> top-left bbox top = 842 - 500 = 342
    ///   text line at top-left y=300..312 -> ly1=312, gap = 342-312=30 (在 80pt 内)

    /// 文本行（顶左原点）：y0 是顶，y1 是底
    fn line(y0: f64, text: &str) -> TextLine {
        TextLine {
            bbox: [50.0, y0, 500.0, y0 + 12.0],
            text: text.to_string(),
        }
    }

    /// 默认 molecule bbox (PDF bottom-left)，约 200x100pt，下半页
    fn default_mol() -> (f64, f64, f64, f64) {
        (100.0, 400.0, 300.0, 500.0)
    }

    /// 集成测试：在真 PDF 上验证 label 关联。
    /// 仅在 `MBFORGE_RUN_PDF_INTEG=1` 时跑（避免 CI 缺文件时挂）。
    #[test]
    fn test_integration_cn_patent_page_60() {
        let pdf = std::env::var("MBFORGE_TEST_PDF")
            .unwrap_or_else(|_| r"C:\Users\10954\Desktop\CN120118069A.PDF".to_string());
        if !std::path::Path::new(&pdf).exists() {
            eprintln!("[skip] PDF not found: {pdf}");
            return;
        }
        // Page 60 (1-indexed = 61) 有 10 个分子，所有都应被识别为 "化合物26A"
        let lines =
            extract_page_text_lines(&pdf, 61, 842.0).expect("text extraction should succeed");
        assert!(!lines.is_empty(), "page 61 should have text lines");

        // 找一个典型的 bbox（页 61, 任意位置，y 范围 200-400）
        let mol_bbox = (100.0, 200.0, 300.0, 400.0);
        let m = find_label_for_bbox(mol_bbox, &lines, 842.0, 200.0);
        assert!(m.is_some(), "should find some label near bbox");
        let m = m.unwrap();
        // 期望至少包含 "化合物" 或 "实施例" 或 "第一步" 等中文标号
        let label = &m.label;
        assert!(
            label.contains("化合物") || label.contains("实施例") || label.starts_with("第"),
            "unexpected label: {label}"
        );
    }

    /// 多页集成：扫描 46-95 范围内若干页面，对每页用典型 bbox 跑 find_label_for_bbox
    /// 验证 Rust 实现能给出有意义的中文标号。
    #[test]
    fn test_integration_cn_patent_pages_46_95() {
        let pdf = std::env::var("MBFORGE_TEST_PDF")
            .unwrap_or_else(|_| r"C:\Users\10954\Desktop\CN120118069A.PDF".to_string());
        if !std::path::Path::new(&pdf).exists() {
            eprintln!("[skip] PDF not found: {pdf}");
            return;
        }
        // 抽样 5 个实施例页 (1-indexed)
        let sample_pages = [49u32, 61, 66, 76, 86];
        let mut matched = 0;
        let mut total = 0;
        for page_num in sample_pages {
            let lines = match extract_page_text_lines(&pdf, page_num, 842.0) {
                Ok(l) => l,
                Err(e) => {
                    eprintln!("[skip] page {page_num} text extraction failed: {e}");
                    continue;
                }
            };
            // 模拟多种 bbox 位置
            for y_mid in [250.0_f64, 350.0, 450.0, 550.0, 650.0] {
                total += 1;
                let mol_bbox = (100.0, y_mid - 50.0, 300.0, y_mid + 50.0);
                if let Some(m) = find_label_for_bbox(mol_bbox, &lines, 842.0, 200.0) {
                    let label = &m.label;
                    if label.contains("化合物")
                        || label.contains("实施例")
                        || label.starts_with("第")
                    {
                        matched += 1;
                    }
                }
            }
            eprintln!("page {page_num}: {} lines extracted", lines.len());
        }
        eprintln!("Rust hit rate on sample: {matched}/{total}");
        assert!(
            matched > 0,
            "should match at least one label across sample pages"
        );
    }

    #[test]
    fn test_is_terminator_set() {
        for c in [
            ' ', '\t', '\n', '的', '，', '。', '；', '、', '(', ')', '（', '）',
        ] {
            assert!(is_terminator(Some(c)), "{c:?} should be terminator");
        }
        for c in ['-', 'A', '1', '氯', '甲'] {
            assert!(!is_terminator(Some(c)), "{c:?} should NOT be terminator");
        }
        assert!(is_terminator(None));
    }

    #[test]
    fn test_compound_zh_above() {
        // 文本行紧贴在 bbox 上方
        let lines = vec![line(310.0, "实施例5：1-甲基-N-... (化合物26A)的制备")];
        let m = find_label_for_bbox(default_mol(), &lines, 842.0, 80.0);
        let m = m.expect("should match");
        assert_eq!(m.label, "化合物26A");
    }

    #[test]
    fn test_chemical_name_no_false_positive() {
        // "化合物6-氯-2-甲基-..." 中 "6" 是化学编号，不是标识符
        let lines = vec![line(
            310.0,
            "得到化合物6-氯-2-甲基-4-(三氟甲基)哒嗪-3(2H)-酮(300mg)",
        )];
        let m = find_label_for_bbox(default_mol(), &lines, 842.0, 80.0);
        assert!(
            m.is_none(),
            "should reject chemical-name false positive: {:?}",
            m
        );
    }

    #[test]
    fn test_step_label() {
        let lines = vec![line(
            310.0,
            "第一步：6-氯-2-甲基-4-(三氟甲基)哒嗪-3(2H)-酮的合成",
        )];
        let m = find_label_for_bbox(default_mol(), &lines, 842.0, 80.0);
        let m = m.expect("should match step label");
        assert!(
            m.label.starts_with("第") && m.label.ends_with("步"),
            "got {:?}",
            m.label
        );
    }

    #[test]
    fn test_section_fallback() {
        // 章节：没找到化合物类匹配时退到章节类
        let lines = vec![line(310.0, "实施例3：化合物X的合成")];
        let m = find_label_for_bbox(default_mol(), &lines, 842.0, 80.0);
        let m = m.expect("should match section");
        // 章节 "实施例3" 应该是标签
        assert!(m.label.contains("实施例3"), "got {:?}", m.label);
    }

    #[test]
    fn test_english_compound() {
        let lines = vec![line(310.0, "Compound 26A was prepared as follows:")];
        let m = find_label_for_bbox(default_mol(), &lines, 842.0, 80.0);
        let m = m.expect("should match english compound");
        assert!(m.label.starts_with("Compound"), "got {:?}", m.label);
        assert!(m.label.contains("26A"));
    }

    #[test]
    fn test_too_far_no_match() {
        // 文本行距 bbox 太远 (>80pt)
        let lines = vec![line(100.0, "化合物99A的合成")];
        let m = find_label_for_bbox(default_mol(), &lines, 842.0, 80.0);
        assert!(m.is_none(), "should be out of vertical search range");
    }

    #[test]
    fn test_picks_closest_among_multiple() {
        // 两条候选都"在上方"且都在 v_search 范围内 -> 选最近的
        let lines = vec![
            line(200.0, "化合物99A的合成"), // 远
            line(330.0, "化合物26A的合成"), // 近
        ];
        let m = find_label_for_bbox(default_mol(), &lines, 842.0, 200.0);
        let m = m.expect("should match");
        assert_eq!(m.label, "化合物26A", "expected closest, got {:?}", m.label);
    }

    #[test]
    fn test_below_bbox_not_matched() {
        // 文本行在 bbox 下方（top-left y > ml_top），不匹配
        // bbox top-left top = 342；下方 = y > 342
        let lines = vec![line(500.0, "化合物99A的合成")];
        let m = find_label_for_bbox(default_mol(), &lines, 842.0, 200.0);
        assert!(m.is_none(), "lines below bbox should not match");
    }

    #[test]
    fn test_compound_with_hyphen_suffix() {
        // "化合物28A-4" 形式
        let lines = vec![line(
            310.0,
            "第二步：3-氯-1-(2,2,2-三氟乙基)-1H-吡唑-4-甲酸(化合物28A-4)的合成",
        )];
        let m = find_label_for_bbox(default_mol(), &lines, 842.0, 80.0);
        // 化合物类应该匹配 "化合物28A-4"（连字符接 -4 也是合法标识符）
        // 但因为终止符校验：紧跟 -4 的是 ")"，是终止符，所以 OK
        let m = m.expect("should match 化合物28A-4");
        assert!(
            m.label.contains("28A-4") || m.label.contains("第二步"),
            "expected compound 28A-4 or step 2, got {:?}",
            m.label
        );
    }
}
