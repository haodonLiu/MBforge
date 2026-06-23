//! Tauri commands backing the PDF result pane (right-hand panel in the viewer).
//!
//! These extend the per-page detection cache wrappers in `detection_cache.rs`
//! with two read-only aggregations requested by `PDF_RESULT_PANE_API.md` §8:
//!
//! - `get_molecule_coref_chain` — given a canonical SMILES, list every page
//!   across the project where the molecule appears (per-page detection
//!   cache) together with a short text snippet around the bbox.
//! - `get_page_parse_result` — return the structured text (paragraph
//!   blocks) + cached molecule detections + heuristic findings for a
//!   single page.
//!
//! Both commands are pure readers: they never invoke the Python sidecar and
//! never mutate the cache.

use chematic_smiles::{canonical_smiles, parse as chematic_parse};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

use crate::core::document::detection_cache::{DetectionCache, PageDetection};
use crate::core::document::knowledge_base::get_or_init_kb;
use crate::core::helpers::clean_path;
use crate::core::molecule::molecule_store::MoleculeDatabase;
use crate::core::project::project::Project;
use crate::parsers::chem::label_assoc::{self, TextLine};

// ---------------------------------------------------------------------------
// §8.1 get_molecule_coref_chain
// ---------------------------------------------------------------------------

/// Single occurrence of a molecule on a page.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CorefOccurrence {
    pub doc_id: String,
    pub page: usize,
    pub bbox: [f64; 4],
    pub context: String,
    pub confidence: f64,
    pub smiles: String,
    pub esmiles: String,
}

/// Cross-page coref chain for one molecule.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CorefChain {
    pub mol_id: String,
    pub occurrences: Vec<CorefOccurrence>,
    /// Other names the molecule is known by. Empty for now — the molecule
    /// store has no dedicated alias table yet.
    pub aliases: Vec<String>,
}

/// Get every cached occurrence of `mol_id` (canonical SMILES or E-SMILES)
/// across the project.
///
/// `mol_id` is canonicalized before matching; ESMILES values are reduced
/// to the SMILES portion (before `<sep>`). Each occurrence includes the
/// PDF bbox and a 240-char text snippet of the lines that overlap the
/// bbox y-range.
#[tauri::command]
pub async fn get_molecule_coref_chain(
    project_root: String,
    mol_id: String,
) -> Result<CorefChain, String> {
    let project_root = clean_path(&project_root);
    let root = PathBuf::from(&project_root);
    let target = canonicalize_match_key(&mol_id)?;
    if target.is_empty() {
        return Ok(CorefChain {
            mol_id: mol_id.clone(),
            occurrences: vec![],
            aliases: vec![],
        });
    }

    let mut occurrences: Vec<CorefOccurrence> = Vec::new();

    let doc_ids: Vec<String> = match Project::open(&root) {
        Some(p) => p
            .list_documents()
            .iter()
            .filter(|d| d.doc_type == "pdf")
            .map(|d| d.doc_id.clone())
            .collect(),
        None => Vec::new(),
    };

    for doc_id in doc_ids {
        let (pdf_abs, _doc_slug, is_legacy) = match Project::open(&root)
            .and_then(|p| p.get_document_source_path(&doc_id))
        {
            Some(path) => {
                let slug = path
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or(&doc_id)
                    .to_string();
                let legacy = path.starts_with(
                    root.join(crate::core::config::constants::PAPERS_DIR),
                );
                (path, slug, legacy)
            }
            None => continue,
        };
        let cache_key = if is_legacy {
            // Legacy cache keyed by PDF file stem; we don't have it here,
            // skip — the bulk of detections live in DocumentProject cache.
            continue;
        } else {
            doc_id.clone()
        };

        let hash = match pdf_hash_cached(&pdf_abs).await {
            Some(h) => h,
            None => continue,
        };
        let cache = DetectionCache::for_document_project(&root, &doc_id);
        let pages = cache.list_pages_for_doc(&cache_key);
        for page in pages {
            let Some(entry) = cache.get(&cache_key, page, &hash) else {
                continue;
            };
            for det in &entry.detections {
                if !det.has_structure() {
                    continue;
                }
                let key = detection_match_key(det);
                if key.is_empty() || key != target {
                    continue;
                }
                let bbox_pdf = det.bbox_pdf;
                let context = extract_context_text(&pdf_abs, page, &bbox_pdf);
                occurrences.push(CorefOccurrence {
                    doc_id: doc_id.clone(),
                    page,
                    bbox: bbox_pdf,
                    context,
                    confidence: composite_conf(det),
                    smiles: det.smiles.clone().unwrap_or_default(),
                    esmiles: det.esmiles.clone().unwrap_or_default(),
                });
            }
        }
    }

    // Stable order: doc_id asc, then page asc.
    occurrences.sort_by(|a, b| a.doc_id.cmp(&b.doc_id).then(a.page.cmp(&b.page)));

    let aliases = collect_aliases(&root, &target);

    Ok(CorefChain {
        mol_id: mol_id.clone(),
        occurrences,
        aliases,
    })
}

// ---------------------------------------------------------------------------
// §8.2 get_page_parse_result
// ---------------------------------------------------------------------------

/// Block of structured text on a page.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StructuredTextBlock {
    /// Always `"paragraph"` for now. Kept as a string field for forward
    /// compat with `heading` / `table` / `figure` per the spec.
    pub kind: String,
    pub content: String,
    pub bbox: [f64; 4],
}

/// Heuristic finding (key sentence) on the page.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding {
    pub kind: String,
    pub text: String,
    pub bbox: [f64; 4],
}

/// Aggregated result for one page.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PageParseResult {
    pub page: usize,
    pub structured_text: Vec<StructuredTextBlock>,
    pub molecules: Vec<serde_json::Value>,
    pub findings: Vec<Finding>,
}

/// Read the cached parse result for a single page: structured text
/// blocks, cached molecule detections, and heuristic findings (sentences
/// matching common chemistry keywords).
///
/// `page_h_pts` is required because the cached text-line extractor needs
/// to flip bottom-left y-coordinates to top-left.
#[tauri::command]
pub async fn get_page_parse_result(
    project_root: String,
    doc_id: String,
    page: usize,
    page_h_pts: f64,
) -> Result<PageParseResult, String> {
    let project_root = clean_path(&project_root);
    let root = PathBuf::from(&project_root);

    let pdf_abs = Project::open(&root)
        .and_then(|p| p.get_document_source_path(&doc_id))
        .ok_or_else(|| format!("Document not found: {}", doc_id))?;

    // 1) Cached molecule detections (reusing the cache reader logic).
    let molecules = read_cached_molecules(&root, &doc_id, &pdf_abs, page).await?;

    // 2) Structured text blocks from the PDF.
    let text_lines = label_assoc::extract_page_text_lines(
        pdf_abs.to_string_lossy().as_ref(),
        page as u32,
        page_h_pts,
    )
    .unwrap_or_default();
    let structured_text = group_lines_into_paragraphs(&text_lines);

    // 3) Heuristic findings: sentences that mention common chem-activity
    //    keywords. Keeps the right-hand panel informative even when no
    //    LLM pass has run.
    let findings = extract_findings(&text_lines);

    Ok(PageParseResult {
        page,
        structured_text,
        molecules,
        findings,
    })
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

/// Re-hash a PDF only when its mtime changes. Cached in process memory
/// to avoid paying SHA-256 on every call.
async fn pdf_hash_cached(pdf_abs: &std::path::Path) -> Option<String> {
    use std::collections::HashMap;
    use std::sync::LazyLock;
    use std::time::{SystemTime, UNIX_EPOCH};
    use tokio::sync::Mutex;

    #[derive(Clone)]
    struct Entry {
        mtime_secs: u64,
        hash: String,
    }

    static CACHE: LazyLock<Mutex<HashMap<PathBuf, Entry>>> =
        LazyLock::new(|| Mutex::new(HashMap::new()));

    let mtime = std::fs::metadata(pdf_abs)
        .and_then(|m| m.modified())
        .ok()
        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_secs())
        .unwrap_or(0);

    {
        let cache = CACHE.lock().await;
        if let Some(e) = cache.get(pdf_abs) {
            if e.mtime_secs == mtime {
                return Some(e.hash.clone());
            }
        }
    }

    let hash = crate::core::helpers::sha256_file(pdf_abs).ok()?;
    let mut cache = CACHE.lock().await;
    cache.insert(
        pdf_abs.to_path_buf(),
        Entry {
            mtime_secs: mtime,
            hash: hash.clone(),
        },
    );
    Some(hash)
}

/// Canonical form used for chain matching: split ESMILES at `<sep>` then
/// chematic-canonicalize. Returns empty string when parsing fails so the
/// caller can skip the entry instead of erroring the whole command.
fn canonicalize_match_key(input: &str) -> Result<String, String> {
    let trimmed = input.trim();
    if trimmed.is_empty() {
        return Ok(String::new());
    }
    let smiles_part = trimmed.split("<sep>").next().unwrap_or(trimmed).trim();
    if smiles_part.is_empty() {
        return Ok(String::new());
    }
    match chematic_parse(smiles_part) {
        Ok(mol) => Ok(canonical_smiles(&mol)),
        Err(_) => Ok(String::new()),
    }
}

fn detection_match_key(det: &crate::core::document::detection_cache::Detection) -> String {
    if let Some(s) = det.esmiles.as_deref() {
        let key = canonicalize_match_key(s).unwrap_or_default();
        if !key.is_empty() {
            return key;
        }
    }
    if let Some(s) = det.smiles.as_deref() {
        let key = canonicalize_match_key(s).unwrap_or_default();
        if !key.is_empty() {
            return key;
        }
    }
    String::new()
}

/// Collect every distinct non-empty `name` of any molecule whose
/// canonical SMILES matches `target`. Molecule records are loaded with a
/// generous cap (10k) — projects larger than that should switch to a
/// proper FTS or structural index.
fn collect_aliases(root: &std::path::Path, target: &str) -> Vec<String> {
    if target.is_empty() {
        return Vec::new();
    }
    let db = match MoleculeDatabase::open(root) {
        Ok(d) => d,
        Err(e) => {
            log::warn!("[get_molecule_coref_chain] open molecule db: {}", e);
            return Vec::new();
        }
    };
    // list_all is paginated; fetch the full table in one shot with the
    // documented cap and the default page size.
    let rows = match db.list_all(10_000, 0, None, None) {
        Ok(r) => r,
        Err(e) => {
            log::warn!("[get_molecule_coref_chain] list molecules: {}", e);
            return Vec::new();
        }
    };
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut out: Vec<String> = Vec::new();
    for rec in rows {
        if rec.smiles.is_empty() {
            continue;
        }
        let key = match canonicalize_match_key(&rec.smiles) {
            Ok(k) => k,
            Err(_) => continue,
        };
        if key != target {
            continue;
        }
        let name = rec.name.trim();
        if name.is_empty() {
            continue;
        }
        if seen.insert(name.to_string()) {
            out.push(name.to_string());
        }
    }
    out
}

fn composite_conf(det: &crate::core::document::detection_cache::Detection) -> f64 {
    if det.conf_molscribe > 0.0 {
        (det.conf_moldet + det.conf_molscribe) / 2.0
    } else {
        det.conf_moldet
    }
}

/// Pull a 240-char text snippet from the lines that vertically overlap
/// the bbox. The bbox is in PDF bottom-left coords; the lines we got
/// from `label_assoc` are top-left, so we flip by `page_h_pts` here.
fn extract_context_text(
    pdf_abs: &std::path::Path,
    page: usize,
    bbox_pdf: &[f64; 4],
) -> String {
    let page_h_pts = estimate_page_h_pts(pdf_abs, page);
    let lines = label_assoc::extract_page_text_lines(
        pdf_abs.to_string_lossy().as_ref(),
        page as u32,
        page_h_pts,
    )
    .unwrap_or_default();
    let flipped = flip_bbox(*bbox_pdf, page_h_pts);
    let mut hits: Vec<&TextLine> = lines
        .iter()
        .filter(|l| line_overlaps_y(&flipped, l))
        .collect();
    hits.sort_by(|a, b| a.bbox[1].partial_cmp(&b.bbox[1]).unwrap_or(std::cmp::Ordering::Equal));
    let joined: String = hits
        .iter()
        .map(|l| l.text.as_str())
        .collect::<Vec<_>>()
        .join(" ");
    if joined.len() > 240 {
        let mut end = 240;
        while !joined.is_char_boundary(end) {
            end -= 1;
        }
        format!("{}…", &joined[..end])
    } else {
        joined
    }
}

fn flip_bbox(bbox: [f64; 4], page_h_pts: f64) -> [f64; 4] {
    [bbox[0], page_h_pts - bbox[3], bbox[2], page_h_pts - bbox[1]]
}

fn line_overlaps_y(flipped: &[f64; 4], line: &TextLine) -> bool {
    let ly0 = line.bbox[1];
    let ly1 = line.bbox[3];
    flipped[1] <= ly1 && flipped[3] >= ly0
}

/// Try to get a real page height from the PDF; fall back to A4 height
/// so the bbox-flip never produces a wildly wrong number on failure.
fn estimate_page_h_pts(pdf_abs: &std::path::Path, page: usize) -> f64 {
    let Ok(doc) = lopdf::Document::load(pdf_abs) else {
        return 842.0;
    };
    let pages = doc.get_pages();
    // Pages are 1-indexed in the PDF spec; lopdf stores them 1-indexed too.
    let Some(&page_id) = pages.get(&(page as u32)) else {
        return 842.0;
    };
    let Ok(page_dict) = doc.get_dictionary(page_id) else {
        return 842.0;
    };
    let Ok(arr) = page_dict.get(b"MediaBox").and_then(|o| o.as_array()) else {
        return 842.0;
    };
    if arr.len() < 4 {
        return 842.0;
    }
    let h = match &arr[3] {
        lopdf::Object::Real(r) => *r as f64,
        lopdf::Object::Integer(i) => *i as f64,
        _ => return 842.0,
    };
    h.max(1.0)
}

/// Greedy paragraph grouping: adjacent text lines whose y-ranges touch or
/// have a gap ≤ `LINE_GAP_PTS` collapse into one block. Each emitted
/// block is then classified (paragraph / heading / figure / table) from
/// its joined content.
fn group_lines_into_paragraphs(lines: &[TextLine]) -> Vec<StructuredTextBlock> {
    const LINE_GAP_PTS: f64 = 6.0;
    let mut sorted: Vec<&TextLine> = lines.iter().collect();
    sorted.sort_by(|a, b| {
        a.bbox[1]
            .partial_cmp(&b.bbox[1])
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    let mut out: Vec<StructuredTextBlock> = Vec::new();
    let mut cur: Vec<&TextLine> = Vec::new();
    for line in sorted {
        match cur.last() {
            Some(prev) => {
                let gap = line.bbox[1] - prev.bbox[3];
                if gap <= LINE_GAP_PTS {
                    cur.push(line);
                } else {
                    push_block(&mut out, &cur);
                    cur.clear();
                    cur.push(line);
                }
            }
            None => cur.push(line),
        }
    }
    if !cur.is_empty() {
        push_block(&mut out, &cur);
    }
    out
}

fn push_block(out: &mut Vec<StructuredTextBlock>, lines: &[&TextLine]) {
    if lines.is_empty() {
        return;
    }
    let x0 = lines
        .iter()
        .map(|l| l.bbox[0])
        .fold(f64::INFINITY, f64::min);
    let y0 = lines
        .iter()
        .map(|l| l.bbox[1])
        .fold(f64::INFINITY, f64::min);
    let x1 = lines
        .iter()
        .map(|l| l.bbox[2])
        .fold(f64::NEG_INFINITY, f64::max);
    let y1 = lines
        .iter()
        .map(|l| l.bbox[3])
        .fold(f64::NEG_INFINITY, f64::max);
    let content = lines
        .iter()
        .map(|l| l.text.as_str())
        .collect::<Vec<_>>()
        .join(" ");
    let kind = classify_block(&content, lines.len());
    out.push(StructuredTextBlock {
        kind,
        content,
        bbox: [x0, y0, x1, y1],
    });
}

/// Classify a block of text. Patterns are intentionally narrow — the
/// spec reserves `heading` / `figure` / `table` for future expansion, so
/// we only tag cases we are confident about and default the rest to
/// `paragraph`.
fn classify_block(content: &str, line_count: usize) -> String {
    let trimmed = content.trim();
    if trimmed.is_empty() {
        return "paragraph".to_string();
    }
    // Captions: "Figure 1.", "Fig. 2.", "Scheme 3.", "Table 4." appear as
    // single lines anchored by a number. Match the start of the block.
    if line_count == 1 {
        let lower = trimmed.to_lowercase();
        for prefix in &["figure ", "fig. ", "scheme ", "fig ", "sch "] {
            if lower.starts_with(prefix) {
                let tail = &trimmed[prefix.len()..];
                if tail
                    .chars()
                    .next()
                    .map(|c| c.is_ascii_digit())
                    .unwrap_or(false)
                {
                    return if lower.starts_with("table ") {
                        "table".to_string()
                    } else {
                        "figure".to_string()
                    };
                }
            }
        }
        if lower.starts_with("table ") {
            let tail = &trimmed[6..];
            if tail
                .chars()
                .next()
                .map(|c| c.is_ascii_digit())
                .unwrap_or(false)
            {
                return "table".to_string();
            }
        }
    }
    // Headings: short, single-line, no terminal period, often a
    // capitalized phrase. Avoid tagging long sentences or captions.
    if line_count == 1 && trimmed.len() <= 80 && !trimmed.ends_with('.') {
        let words: Vec<&str> = trimmed.split_whitespace().collect();
        if !words.is_empty() && words.len() <= 12 {
            let first = words[0].chars().next().unwrap_or(' ');
            if first.is_ascii_uppercase() {
                return "heading".to_string();
            }
        }
    }
    "paragraph".to_string()
}

/// Heuristic chem-bio findings: match lines against a fixed list of
/// activity / outcome keywords. Lines that match contribute the whole
/// line as a finding.
fn extract_findings(lines: &[TextLine]) -> Vec<Finding> {
    const KEYWORDS: &[&str] = &[
        "IC50",
        "EC50",
        "Ki",
        "Kd",
        "MIC",
        "% inhibition",
        "binding affinity",
        "synthesized",
        "yield",
        "selectivity",
        "potency",
        "agonist",
        "antagonist",
        "inhibitor",
    ];
    let mut out: Vec<Finding> = Vec::new();
    for line in lines {
        let lower = line.text.to_lowercase();
        if KEYWORDS.iter().any(|k| lower.contains(&k.to_lowercase())) {
            out.push(Finding {
                kind: "keyword".to_string(),
                text: line.text.clone(),
                bbox: line.bbox,
            });
        }
    }
    out
}

/// Read the cached detections for a single page using the same key
/// resolution rules as `cached_extract_page` / `get_cached_page_detections`.
async fn read_cached_molecules(
    project_root: &std::path::Path,
    doc_id: &str,
    pdf_abs: &std::path::Path,
    page: usize,
) -> Result<Vec<serde_json::Value>, String> {
    let root = project_root;
    let (doc_slug, is_legacy) = match Project::open(root).and_then(|p| p.get_document_source_path(doc_id)) {
        Some(path) => {
            let slug = path
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or(doc_id)
                .to_string();
            let legacy = path.starts_with(root.join(crate::core::config::constants::PAPERS_DIR));
            (slug, legacy)
        }
        None => (doc_id.to_string(), true),
    };
    let cache_key = if is_legacy { doc_slug } else { doc_id.to_string() };

    let hash = match pdf_hash_cached(pdf_abs).await {
        Some(h) => h,
        None => return Ok(vec![]),
    };
    let cache = if is_legacy {
        DetectionCache::new(root)
    } else {
        DetectionCache::for_document_project(root, doc_id)
    };
    let entry: PageDetection = match cache.get(&cache_key, page, &hash) {
        Some(e) => e,
        None => return Ok(vec![]),
    };
    Ok(entry
        .detections
        .iter()
        .map(|d| {
            let composite = if d.conf_molscribe > 0.0 {
                (d.conf_moldet + d.conf_molscribe) / 2.0
            } else {
                d.conf_moldet
            };
            let has_structure = d.has_structure();
            serde_json::json!({
                "esmiles": d.esmiles.as_deref().unwrap_or(""),
                "smiles": d.smiles.as_deref().unwrap_or(""),
                "name": "",
                "source": "image",
                "moldet_conf": d.conf_moldet,
                "scribe_conf": d.conf_molscribe,
                "composite_conf": composite,
                "bbox_pdf": if d.bbox_pdf[2] > d.bbox_pdf[0] && d.bbox_pdf[3] > d.bbox_pdf[1] {
                    Some(d.bbox_pdf.to_vec())
                } else {
                    None
                },
                "page_idx": page as i32,
                "context_text": "",
                "mol_img_path": d.crop_relpath.as_deref().unwrap_or(""),
                "status": if has_structure { "done" } else { "pending" },
                "is_quick_scan": d.is_quick_scan,
                "properties": {},
            })
        })
        .collect())
}

// ---------------------------------------------------------------------------
// ensure_coref_for_image（懒迁移：旧 PDF 首次打开时按需补 coref）
// ---------------------------------------------------------------------------

/// Coref 懒迁移结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnsureCorefResult {
    pub doc_id: String,
    pub page: i64,
    pub already_existed: bool, // true = KB 已有数据，跳过
    pub labels_written: usize,
    pub predictions_written: usize,
    pub error: Option<String>,
}

/// 确保指定 (doc_id, page) 的 coref 标注存在。
///
/// 旧 PDF 首次打开页面时调用：
/// - KB 中已有 figure_labels → 跳过（already_existed=true）
/// - 无 → 调 sidecar 跑 coref，写 KB
#[tauri::command]
pub async fn ensure_coref_for_image(
    project_root: String,
    doc_id: String,
    page: i64,
    image_path: String,
) -> Result<EnsureCorefResult, String> {
    use crate::core::document::knowledge_base::get_or_init_kb;
    use crate::parsers::pipeline::services::coref_persist::CorefPersistService;

    let resolved = if std::path::Path::new(&image_path).is_absolute() {
        std::path::PathBuf::from(&image_path)
    } else {
        std::path::PathBuf::from(clean_path(&project_root)).join(&image_path)
    };

    // 1. 检查 KB 是否已有数据
    let kb_guard = get_or_init_kb(&project_root).map_err(|e| e.to_string())?;
    let kb = kb_guard.value();
    let existing = kb
        .get_figure_labels(&doc_id, page)
        .map_err(|e| e.to_string())?;
    if !existing.is_empty() {
        return Ok(EnsureCorefResult {
            doc_id,
            page,
            already_existed: true,
            labels_written: 0,
            predictions_written: 0,
            error: None,
        });
    }

    // 2. 跑 coref 写 KB
    let service = CorefPersistService::new();
    match service
        .persist_for_image(kb, &doc_id, page, &resolved, true, true)
        .await
    {
        Ok(res) => Ok(EnsureCorefResult {
            doc_id,
            page,
            already_existed: false,
            labels_written: res.labels_written,
            predictions_written: res.predictions_written,
            error: None,
        }),
        Err(e) => Ok(EnsureCorefResult {
            doc_id,
            page,
            already_existed: false,
            labels_written: 0,
            predictions_written: 0,
            error: Some(format!("{e}")),
        }),
    }
}

// ---------------------------------------------------------------------------
// Coref 校对：confirm / update pair / delete
// ---------------------------------------------------------------------------

/// 标记 coref 预测为人工确认（或撤销）
#[tauri::command]
pub fn confirm_coref_prediction(
    project_root: String,
    prediction_id: i64,
    is_confirmed: bool,
) -> Result<(), String> {
    let kb_guard = get_or_init_kb(&project_root).map_err(|e| e.to_string())?;
    kb_guard
        .value()
        .confirm_coref_prediction(prediction_id, is_confirmed)
        .map_err(|e| e.to_string())
}

/// 人工重选 coref pair：删旧的，写新的，source='manual', is_confirmed=true
#[tauri::command]
pub fn update_coref_pair(
    project_root: String,
    doc_id: String,
    page: i64,
    old_prediction_id: Option<i64>,
    mol_image_id: Option<i64>,
    mol_smiles: Option<String>,
    mol_bbox: Option<Vec<f64>>,
    label_id: i64,
) -> Result<i64, String> {
    use crate::core::document::knowledge_base::CorefPrediction;

    let kb_guard = get_or_init_kb(&project_root).map_err(|e| e.to_string())?;
    let kb = kb_guard.value();

    // 1. 删旧（如果指定）
    if let Some(old_id) = old_prediction_id {
        // 先查出旧的 label_id 以匹配要删的记录
        let existing = kb
            .get_coref_predictions(&doc_id, page)
            .map_err(|e| e.to_string())?;
        if existing.iter().any(|p| p.id == old_id) {
            // 简单做法：upsert 时用 (mol_smiles, label_text) 唯一键，
            // 改 mol_smiles 即替换。
            // 这里直接 delete by id（需要新方法）
            // 暂用 delete_coref_predictions 全删（粗暴）— TODO: 细粒度
            // 实际：先读出现有 (mol_smiles, label_text) 再 upsert 替换
        }
    }

    // 2. 查 label 信息（用 label_id）
    let labels = kb
        .get_figure_labels(&doc_id, page)
        .map_err(|e| e.to_string())?;
    let label = labels
        .iter()
        .find(|l| l.id == label_id)
        .ok_or_else(|| format!("label_id {label_id} not found"))?;

    // 3. 写新 prediction（手动 source=manual, is_confirmed=true）
    let new_pred = CorefPrediction {
        id: 0,
        doc_id: doc_id.clone(),
        page,
        mol_smiles: mol_smiles.clone(),
        mol_bbox: mol_bbox.clone(),
        mol_conf: None,
        label_id: Some(label_id),
        label_text: Some(label.label_text.clone()),
        label_bbox: Some(label.label_bbox.clone()),
        confidence: 1.0,
        source: "manual".to_string(),
        is_confirmed: true,
    };

    // 4. 如果有旧的（mol_smiles, label_text）配对，先删
    if let (Some(old_smiles), Some(old_text)) = (
        mol_smiles.as_ref().or(if old_prediction_id.is_some() {
            // 从 existing 查旧 mol_smiles
            None
        } else {
            None
        }),
        Some(&label.label_text),
    ) {
        let _ = kb
            .delete_predictions_by_pair(&doc_id, page, old_smiles, old_text);
    }

    kb.upsert_coref_predictions(&doc_id, page, &[new_pred])
        .map_err(|e| e.to_string())?;

    // 5. 返回新 id（查最新）
    let preds = kb
        .get_coref_predictions(&doc_id, page)
        .map_err(|e| e.to_string())?;
    preds
        .iter()
        .find(|p| p.label_id == Some(label_id) && p.mol_smiles == mol_smiles)
        .map(|p| p.id)
        .ok_or_else(|| "updated prediction not found".to_string())
}

/// 删除指定 coref 预测
#[tauri::command]
pub fn delete_coref_prediction(
    project_root: String,
    prediction_id: i64,
) -> Result<(), String> {
    let kb_guard = get_or_init_kb(&project_root).map_err(|e| e.to_string())?;
    let kb = kb_guard.value();

    // 查 pred 拿 (doc_id, page) 再 delete
    // 简单做法：query 所有 predictions 找匹配的
    // 优化：给 KB 加 delete_by_id 方法（下次迭代）
    // 现在用 delete_predictions_by_pair 没法直接 by id — 用 0/0 trick 不行
    // 直接全删该 doc 的 predictions 太重
    // 临时方案：读取所有页找到后用 delete_coref_predictions
    // 简化：暂时不实现单点删除，要求前端调 confirm_coref_prediction(false) 标记
    let _ = (kb, prediction_id);
    Err("Single-id delete not yet implemented. Use confirm_coref_prediction(false) to unconfirm.".to_string())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn line(y0: f64, y1: f64, text: &str) -> TextLine {
        TextLine {
            bbox: [50.0, y0, 500.0, y1],
            text: text.to_string(),
        }
    }

    #[test]
    fn canonicalize_match_key_strips_esmiles_tags() {
        let key = canonicalize_match_key("c1ccccc1<sep><a>0:Ph</a>").unwrap();
        assert!(!key.is_empty());
        // Chematic canonical form is deterministic.
        assert_eq!(key, canonical_smiles(&chematic_parse("c1ccccc1").unwrap()));
    }

    #[test]
    fn canonicalize_match_key_empty_inputs() {
        assert_eq!(canonicalize_match_key("").unwrap(), "");
        assert_eq!(canonicalize_match_key("   ").unwrap(), "");
    }

    #[test]
    fn canonicalize_match_key_invalid_returns_empty() {
        // Not a SMILES, but not a hard error: caller treats empty as "skip".
        assert_eq!(canonicalize_match_key("@#$").unwrap(), "");
    }

    #[test]
    fn flip_bbox_round_trip() {
        let bbox = [10.0, 50.0, 100.0, 150.0];
        let flipped = flip_bbox(bbox, 842.0);
        let back = flip_bbox(flipped, 842.0);
        for (a, b) in bbox.iter().zip(back.iter()) {
            assert!((a - b).abs() < 1e-6);
        }
    }

    #[test]
    fn line_overlaps_y_handles_disjoint() {
        let flipped = [10.0, 100.0, 200.0, 200.0];
        let disjoint = line(0.0, 50.0, "above");
        let overlap = line(150.0, 180.0, "inside");
        assert!(!line_overlaps_y(&flipped, &disjoint));
        assert!(line_overlaps_y(&flipped, &overlap));
    }

    #[test]
    fn group_lines_into_paragraphs_merges_close_lines() {
        let lines = vec![
            line(100.0, 112.0, "line A"),
            line(112.0, 124.0, "line B"),
            line(150.0, 162.0, "line C (gap 26)"),
            line(162.0, 174.0, "line D"),
        ];
        let blocks = group_lines_into_paragraphs(&lines);
        assert_eq!(blocks.len(), 2);
        assert!(blocks[0].content.contains("line A"));
        assert!(blocks[0].content.contains("line B"));
        assert!(blocks[1].content.contains("line C"));
        assert!(blocks[1].content.contains("line D"));
    }

    #[test]
    fn extract_findings_matches_chem_keywords() {
        let lines = vec![
            line(0.0, 12.0, "Compound 1 was synthesized in 80% yield."),
            line(12.0, 24.0, "IC50 = 12 nM against target X."),
            line(24.0, 36.0, "Plain body text without markers."),
        ];
        let findings = extract_findings(&lines);
        assert_eq!(findings.len(), 2);
        let texts: Vec<&str> = findings.iter().map(|f| f.text.as_str()).collect();
        assert!(texts.iter().any(|t| t.contains("synthesized")));
        assert!(texts.iter().any(|t| t.contains("IC50")));
    }

    #[test]
    fn classify_block_detects_figure_caption() {
        assert_eq!(classify_block("Figure 1. Synthetic route to compound 7", 1), "figure");
        assert_eq!(classify_block("Fig. 3. Inhibition curve of analog 12", 1), "figure");
        assert_eq!(classify_block("Scheme 2. Retrosynthesis overview", 1), "figure");
    }

    #[test]
    fn classify_block_detects_table_caption() {
        assert_eq!(classify_block("Table 2. IC50 values for series A", 1), "table");
    }

    #[test]
    fn classify_block_detects_heading() {
        assert_eq!(classify_block("Results and Discussion", 1), "heading");
        assert_eq!(classify_block("Experimental Section", 1), "heading");
    }

    #[test]
    fn classify_block_falls_back_to_paragraph() {
        // Multi-line block: never a caption or heading.
        let para = "This is a long sentence that should not be classified as a heading because it is way too long for that and has too many words to be considered a heading.";
        assert_eq!(classify_block(para, 1), "paragraph");
        // Period-terminated single line: not a heading.
        assert_eq!(classify_block("Introduction.", 1), "paragraph");
        // Caption-like prefix but no number: not a caption.
        assert_eq!(classify_block("Figure caption without a number", 1), "heading");
    }
}
