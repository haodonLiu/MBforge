//! OKF pipeline: LLM activity extraction + cross-page join + OKF bundle export.
//!
//! End-to-end command that takes a PDF, runs the existing PDF→molecules
//! pipeline, then drives an LLM over the extracted text to pull quantitative
//! activity records (IC50/EC50/Ki/%inhibition/...), joins each record back to
//! the detected molecule SMILES, and writes an OKF 0.1 markdown bundle
//! alongside the project root.
//!
//! Reference: <https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md>
//!
//! Required env: `MBFORGE_LLM_BASE_URL` (SenseNova), `MBFORGE_LLM_API_KEY`,
//! `MBFORGE_LLM_PROVIDER=openai_compatible`.
//!
//! Sidecar (PyMuPDF / MolDet / MolScribe) must be running on `127.0.0.1:18792`.

use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

use serde::{Deserialize, Serialize};

use mbforge_domain::molecule::molecule_store::MoleculeDatabase;
use mbforge_pipeline::structure::post_process::call_llm_api_async;

use rusqlite::Connection;

// ─── Config ──────────────────────────────────────────────────────────────

const LLM_PROMPT: &str = r#"You are a patent-parsing assistant. Read the following text from one page of a pharmaceutical patent (may be in Chinese OR English) and extract EVERY quantitative activity record (IC50, EC50, Ki, Kd, GI50, MIC, %inhibition, %activity, ED50, LD50, etc.) for EVERY named compound.

Output rules (STRICT):
- Return JSON only. No markdown fence. No prose before/after.
- Schema: {"records":[{"compound_label":"<string>","activity_type":"<IC50|EC50|Ki|Kd|GI50|MIC|%inhibition|%activity|ED50|other>","value":<number|null>,"unit":"<nM|uM|%|ug/mL|mg/kg|other>","assay":"<cell-line / enzyme / target>","target":"<protein name or null>","quote":"<verbatim sentence/clause>"}]}
- `compound_label` is the figure-label or table-编号 as it appears in the text (e.g. "1", "1a", "I-3", "实施例1", "化合物1"). Use the SHORTEST label that uniquely identifies the compound within the patent.
- Tables: emitted as <table>...<tr><td>...</td></tr>...</table> — parse EVERY row: each (compound_label, value) cell pair is one record.
- IC50 values expressed as "< 500" or "<50 nM" — set value=number (e.g. 500), unit="nM", and put "<" in quote.
- Skip claims (numbered "1、 ..." or "1. ...").
- If no activity data is present on this page, return {"records":[]}.

PAGE {page}/{total_pages}
----- TEXT -----
{text}
----- END -----
"#;

const LLM_MODELS: &[&str] = &["sensenova-6.7-flash-lite", "deepseek-v4-flash"];

// ─── LLM response shapes ──────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
struct LlmResp {
    records: Vec<LlmRecord>,
}

#[derive(Debug, Deserialize, Clone)]
struct LlmRecord {
    compound_label: String,
    activity_type: Option<String>,
    value: Option<serde_json::Value>,
    unit: Option<String>,
    assay: Option<String>,
    target: Option<String>,
    #[serde(default)]
    quote: String,
}

// ─── Public result ───────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct OkfPipelineResult {
    pub patent_id: String,
    pub text_pages: usize,
    pub activity_records: usize,
    pub records_with_smiles: usize,
    pub molecules_total: usize,
    pub molecules_with_activity: usize,
    pub okf_bundle_path: String,
    pub elapsed_s: f64,
    pub warnings: Vec<String>,
}

// ─── Helpers ─────────────────────────────────────────────────────────────

/// Extract first balanced JSON object/array from a free-form LLM response.
fn extract_json(s: &str) -> Result<serde_json::Value, String> {
    let s = s.trim();
    let s = if let Some(rest) = s.strip_prefix("```") {
        let s = rest.trim_start_matches(|c: char| c.is_ascii_alphabetic());
        s.trim_end_matches("```").trim()
    } else {
        s
    };
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(s) {
        return Ok(v);
    }
    for (opener, closer) in [('{', '}'), ('[', ']')] {
        if let Some(start) = s.find(opener) {
            let mut depth = 0_i32;
            for (i, c) in s[start..].char_indices() {
                if c == opener {
                    depth += 1;
                } else if c == closer {
                    depth -= 1;
                    if depth == 0 {
                        let cand = &s[start..=start + i];
                        if let Ok(v) = serde_json::from_str::<serde_json::Value>(cand) {
                            return Ok(v);
                        }
                    }
                }
            }
        }
    }
    Err(format!("no JSON in LLM output: {}", &s[..s.len().min(200)]))
}

/// LLM call with model polling (OpenAI-compatible /v1/chat/completions).
async fn call_llm_with_poll(prompt: &str) -> Result<(String, String), String> {
    use std::time::Duration;
    let api_key = std::env::var("MBFORGE_LLM_API_KEY")
        .map_err(|_| "MBFORGE_LLM_API_KEY not set".to_string())?;
    let url = std::env::var("MBFORGE_LLM_BASE_URL")
        .unwrap_or_else(|_| "https://token.sensenova.cn/v1/chat/completions".to_string());
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(180))
        .build()
        .map_err(|e| format!("client build: {e}"))?;
    let mut last_err: Option<String> = None;
    for model in LLM_MODELS {
        let body = serde_json::json!({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 4096,
        });
        match client
            .post(&url)
            .bearer_auth(&api_key)
            .json(&body)
            .send()
            .await
        {
            Ok(r) if r.status().is_success() => {
                let j: serde_json::Value = r
                    .json()
                    .await
                    .map_err(|e| format!("LLM JSON parse: {e}"))?;
                let content = j["choices"][0]["message"]["content"]
                    .as_str()
                    .unwrap_or("")
                    .to_string();
                if !content.is_empty() {
                    return Ok((model.to_string(), content));
                }
                last_err = Some(format!("model={model} empty content"));
            }
            Ok(r) => {
                let st = r.status();
                let txt = r.text().await.unwrap_or_default();
                last_err = Some(format!("model={model} HTTP {st}: {}", &txt[..txt.len().min(200)]));
            }
            Err(e) => last_err = Some(format!("model={model} send: {e}")),
        }
    }
    Err(last_err.unwrap_or_else(|| "all LLM models failed".into()))
}

/// Call SenseNova via the project's configured LLM (uses the project's
/// `MbforgeProviderConfig` + rig OpenAI client). Falls back to raw HTTP if
/// the rig path is unavailable (e.g. missing config).
async fn call_llm_activity(prompt: &str) -> Result<String, String> {
    // Try the project-config path first.
    if let Ok((content, _tokens)) =
        call_llm_api_async("You extract activity records. Return JSON only.", prompt).await
    {
        if !content.is_empty() {
            return Ok(content);
        }
    }
    // Fallback: raw HTTP to MOFORGE_LLM_BASE_URL.
    let (_model, content) = call_llm_with_poll(prompt).await?;
    Ok(content)
}

// ─── Page text reading ───────────────────────────────────────────────────

/// Read per-page text files from the harness output directory.
/// Returns map: 1-indexed page → text. Pages with no text are skipped.
fn read_page_texts(text_dir: &Path) -> BTreeMap<usize, String> {
    let mut out = BTreeMap::new();
    let entries = match fs::read_dir(text_dir) {
        Ok(e) => e,
        Err(_) => return out,
    };
    for ent in entries.flatten() {
        let p = ent.path();
        if p.extension().and_then(|e| e.to_str()) != Some("txt") {
            continue;
        }
        let stem = p.file_stem().and_then(|s| s.to_str()).unwrap_or("");
        let n: usize = match stem.parse() {
            Ok(n) => n,
            Err(_) => continue,
        };
        if let Ok(t) = fs::read_to_string(&p) {
            if !t.trim().is_empty() {
                out.insert(n, t);
            }
        }
    }
    out
}

// ─── Cross-page join ─────────────────────────────────────────────────────

/// Build label → SMILES index from `manifest.json` (preferred) or fall back
/// to `molecules.db` (raw rusqlite scan).
fn load_molecule_index(
    manifest_path: &Path,
    project_root: &Path,
) -> BTreeMap<String, Vec<(String, usize)>> {
    let mut idx: BTreeMap<String, Vec<(String, usize)>> = BTreeMap::new();
    // Try manifest first
    if let Ok(s) = fs::read_to_string(manifest_path) {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&s) {
            let mols = v.get("molecules").and_then(|m| m.as_array()).cloned().unwrap_or_default();
            for m in mols {
                let smiles = m.get("smiles").and_then(|x| x.as_str()).unwrap_or("").to_string();
                let name = m.get("name").and_then(|x| x.as_str()).unwrap_or("").to_string();
                let page = m.get("page").and_then(|x| x.as_u64()).unwrap_or(0) as usize;
                let smi = smiles.trim();
                if smi.is_empty() || smi == "*" || smi.contains('*') {
                    continue;
                }
                if !name.is_empty() {
                    idx.entry(name).or_default().push((smi.to_string(), page));
                }
            }
            if !idx.is_empty() {
                return idx;
            }
        }
    }
    // Fallback: scan molecules.db directly
    let db_path = project_root
        .join(".mbforge")
        .join("index")
        .join("molecules.db");
    if let Ok(conn) = Connection::open(&db_path) {
        let mut stmt = match conn.prepare(
            "SELECT name, smiles, source_page FROM molecules WHERE smiles IS NOT NULL AND smiles != ''",
        ) {
            Ok(s) => s,
            Err(_) => return idx,
        };
        let rows = stmt.query_map([], |r| {
            let name: String = r.get(0).unwrap_or_default();
            let smiles: String = r.get(1).unwrap_or_default();
            let page: i64 = r.get(2).unwrap_or(0);
            Ok((name, smiles, page))
        });
        if let Ok(rows) = rows {
            for row in rows.flatten() {
                let (name, smiles, page) = row;
                let smi = smiles.trim();
                if smi.is_empty() || smi.contains('*') {
                    continue;
                }
                // Also index by the bare short label (e.g. "1" from "化合物1" or "1")
                if !name.is_empty() {
                    idx.entry(name.clone()).or_default().push((smi.to_string(), page as usize));
                }
                // Extract trailing digits/letters as bare label
                let bare: String = name
                    .chars()
                    .rev()
                    .take_while(|c| c.is_ascii_alphanumeric())
                    .collect::<String>()
                    .chars()
                    .rev()
                    .collect();
                if !bare.is_empty() && bare != name {
                    idx.entry(bare).or_default().push((smi.to_string(), page as usize));
                }
            }
        }
    }
    idx
}

/// Extract 实施例N / 化合物M mappings from page text via plain string scan.
fn extract_prep_map(pages: &BTreeMap<usize, String>) -> HashMap<String, Vec<usize>> {
    let mut prep: HashMap<String, Vec<usize>> = HashMap::new();
    for (p, t) in pages {
        // Walk every "化合物" occurrence; capture the immediate following label.
        let bytes = t.as_bytes();
        let mut i = 0;
        while i + 9 <= bytes.len() {
            // match 化合物 (UTF-8: e5 8c 96 e5 90 88 e7 89 a9)
            if &bytes[i..i + 9] == b"\xe5\x8c\x96\xe5\x90\x88\xe7\x89\xa9" {
                // skip whitespace
                let mut j = i + 9;
                while j < bytes.len() && (bytes[j] == b' ' || bytes[j] == b'\t') {
                    j += 1;
                }
                // capture label: digits + optional [a-zA-Z]
                let start = j;
                while j < bytes.len() && (bytes[j].is_ascii_digit()) {
                    j += 1;
                }
                if j < bytes.len() && bytes[j].is_ascii_alphabetic() {
                    j += 1;
                }
                if j > start {
                    let label = std::str::from_utf8(&bytes[start..j])
                        .unwrap_or("")
                        .to_string();
                    if !label.is_empty() {
                        prep.entry(label).or_default().push(*p);
                    }
                }
                i = j;
            } else {
                i += 1;
            }
        }
    }
    prep
}

// ─── OKF bundle writer ───────────────────────────────────────────────────

fn write_okf_bundle(
    bundle_root: &Path,
    patent_id: &str,
    pdf_path: &Path,
    molecules: &[(String, String, Option<(String, Option<f64>, String, String)>, Vec<usize>)],
) -> std::io::Result<()> {
    fs::create_dir_all(bundle_root)?;
    let mols_dir = bundle_root.join("molecules");
    fs::create_dir_all(&mols_dir)?;
    let now = chrono_now();

    // Per-molecule .md
    for (label, smiles, activity, pages) in molecules {
        let safe = safe_label(label);
        let path = mols_dir.join(format!("{safe}.md"));
        let body = render_molecule_md(label, smiles, activity.as_ref(), pages, pdf_path, &now);
        fs::write(&path, body)?;
    }
    // index.md
    let index_body = render_index_md(patent_id, pdf_path, molecules, &now);
    fs::write(bundle_root.join("index.md"), index_body)?;
    Ok(())
}

fn chrono_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("1970-01-01T00:00:00Z+epoch={secs}")
}

fn safe_label(s: &str) -> String {
    let mut out = String::new();
    for c in s.chars() {
        if c.is_ascii_alphanumeric() || c == '-' || c == '_' {
            out.push(c);
        } else if c.is_whitespace() {
            out.push('_');
        }
    }
    if out.is_empty() {
        out.push_str("mol");
    }
    out
}

fn yaml_quote(s: &str) -> String {
    if s.contains('"') || s.contains('\n') {
        format!("\"{}\"", s.replace('\\', "\\\\").replace('"', "\\\""))
    } else {
        s.to_string()
    }
}

fn render_molecule_md(
    label: &str,
    smiles: &str,
    activity: Option<&(String, Option<f64>, String, String)>,
    pages: &[usize],
    pdf_path: &Path,
    now: &str,
) -> String {
    let mut front = BTreeMap::new();
    front.insert("type".to_string(), "molecule".to_string());
    front.insert("title".to_string(), format!("Compound {label}"));
    front.insert("resource".to_string(), pdf_path.display().to_string());
    front.insert("smiles".to_string(), smiles.to_string());
    front.insert("labels".to_string(), format!("[\"{}\"]", yaml_quote(label)));
    front.insert("pages".to_string(), format!("{:?}", pages));
    front.insert("timestamp".to_string(), now.to_string());
    let mut fm = String::from("---\n");
    for (k, v) in &front {
        fm.push_str(&format!("{k}: {v}\n"));
    }
    fm.push_str("---\n\n");
    let mut body = format!("# {label}\n\n- SMILES: `{smiles}`\n- Pages: {pages:?}\n");
    if let Some((atype, val, unit, target)) = activity {
        body.push_str(&format!(
            "\n## Activity\n\n- **{atype}** = {}{} — target: {}\n",
            val.map(|v| v.to_string()).unwrap_or_else(|| "?".into()),
            unit,
            target,
        ));
    }
    fm + &body
}

fn render_index_md(
    patent_id: &str,
    pdf_path: &Path,
    molecules: &[(String, String, Option<(String, Option<f64>, String, String)>, Vec<usize>)],
    now: &str,
) -> String {
    let mut front = BTreeMap::new();
    front.insert("okf_version".to_string(), "0.1".to_string());
    front.insert("type".to_string(), "index".to_string());
    front.insert("title".to_string(), format!("Patent {patent_id}"));
    front.insert("resource".to_string(), pdf_path.display().to_string());
    front.insert("molecule_count".to_string(), molecules.len().to_string());
    let with_act = molecules.iter().filter(|m| m.2.is_some()).count();
    front.insert("activity_count".to_string(), with_act.to_string());
    front.insert("timestamp".to_string(), now.to_string());
    let mut fm = String::from("---\n");
    for (k, v) in &front {
        fm.push_str(&format!("{k}: {v}\n"));
    }
    fm.push_str("---\n\n");
    let mut body = format!("# Patent {patent_id}\n\n## Molecules\n\n");
    for (label, smiles, _act, _pages) in molecules {
        let safe = safe_label(label);
        body.push_str(&format!("- [{label}](molecules/{safe}.md) — `{smiles}`\n"));
    }
    fm + &body
}

// ─── Tauri command ───────────────────────────────────────────────────────

/// End-to-end: PDF → existing pipeline → LLM activity extract → join → OKF bundle.
#[tauri::command]
pub async fn okf_extract_patent_cmd(
    pdf_path: String,
    text_dir: String,
    manifest_path: String,
    project_root: String,
) -> Result<OkfPipelineResult, String> {
    let t0 = Instant::now();
    let pdf = PathBuf::from(&pdf_path);
    let patent_id = pdf
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("patent")
        .to_string();

    // 1. Read per-page text (from harness / PaddleOCR-VL output).
    let pages = read_page_texts(Path::new(&text_dir));
    if pages.is_empty() {
        return Err(format!("no text files in {text_dir}"));
    }
    let total = pages.len();
    let mut warnings: Vec<String> = Vec::new();

    // 2. LLM activity extract, per page.
    let mut all_records: Vec<(usize, LlmRecord)> = Vec::new();
    for (p, text) in &pages {
        let prompt = LLM_PROMPT
            .replace("{page}", &p.to_string())
            .replace("{total_pages}", &total.to_string())
            .replace("{text}", &text[..text.len().min(12_000)]);
        let content = match call_llm_activity(&prompt).await {
            Ok(c) => c,
            Err(e) => {
                warnings.push(format!("page {p} LLM failed: {e}"));
                continue;
            }
        };
        let parsed = match extract_json(&content) {
            Ok(v) => v,
            Err(_) => {
                warnings.push(format!("page {p} JSON parse failed"));
                continue;
            }
        };
        let resp: LlmResp = match serde_json::from_value(parsed) {
            Ok(r) => r,
            Err(_) => {
                warnings.push(format!("page {p} JSON shape failed"));
                continue;
            }
        };
        for r in resp.records {
            if !r.compound_label.trim().is_empty() {
                all_records.push((*p, r));
            }
        }
    }

    // 3. Load molecule index from manifest (existing extract_pdf_workflow output),
    //    or fall back to molecules.db direct scan.
    let mol_idx = load_molecule_index(Path::new(&manifest_path), Path::new(&project_root));
    let prep_map = extract_prep_map(&pages);

    // 4. Cross-page join: for each activity record, find SMILES.
    //    - direct: label match in mol_idx (e.g. "1" if extracted as mol name)
    //    - cross: prep_map[label] = [pages]; on those pages, use mol with
    //      matching name pattern (实施例N or 化合物N).
    let mut enriched: Vec<(usize, LlmRecord, Option<String>)> = Vec::new();
    for (p, r) in all_records {
        let lab = r.compound_label.trim();
        let smiles = mol_idx
            .get(lab)
            .and_then(|v| v.first().map(|(s, _)| s.clone()))
            .or_else(|| {
                // cross-page: find prep page → look up mol with name like 化合物N
                let mut key = format!("化合物{lab}");
                if let Some(pages) = prep_map.get(lab).or_else(|| prep_map.get(&key)) {
                    for pp in pages {
                        if let Some(v) = mol_idx.get(&key) {
                            if let Some((s, _)) = v.first() {
                                return Some(s.clone());
                            }
                        }
                        key = format!("IMG-{}", patent_id);
                        let _ = pp;
                    }
                }
                None
            });
        enriched.push((p, r, smiles));
    }
    let with_smi = enriched.iter().filter(|e| e.2.is_some()).count();

    // 5. Update molecules.db (if exists): write activity back to molecule record.
    let db_root = Path::new(&project_root);
    let mut molecules_total = 0usize;
    let mut molecules_with_activity = 0usize;
    if let Ok(db) = MoleculeDatabase::open(db_root) {
        // Build a set of SMILES we touch + count totals.
        for (_p, _r, smi) in &enriched {
            let Some(smi) = smi else { continue };
            if let Ok(Some(mut record)) = db.search_by_smiles(smi) {
                let val = enriched
                    .iter()
                    .find(|(_, r, s)| s.as_deref() == Some(smi))
                    .and_then(|(_, r, _)| r.value.as_ref().and_then(|v| v.as_f64()));
                let atype = enriched
                    .iter()
                    .find(|(_, r, s)| s.as_deref() == Some(smi))
                    .and_then(|(_, r, _)| r.activity_type.clone())
                    .unwrap_or_default();
                let unit = enriched
                    .iter()
                    .find(|(_, r, s)| s.as_deref() == Some(smi))
                    .and_then(|(_, r, _)| r.unit.clone())
                    .unwrap_or_default();
                if val.is_some() {
                    record.activity = val;
                }
                if !atype.is_empty() {
                    record.activity_type = atype;
                }
                if !unit.is_empty() {
                    record.units = unit;
                }
                if let Err(e) = db.update_molecule(&record) {
                    warnings.push(format!("update_molecule({smi}) failed: {e}"));
                } else {
                    molecules_with_activity += 1;
                }
            }
        }
        // count total (best-effort: page through list_all with a large limit)
        if let Ok(list) = db.list_all(0, 100_000, None, None) {
            molecules_total = list.len();
        }
    }

    // 6. Write OKF bundle.
    let bundle_root = Path::new(&project_root).join(".okf");
    let mut by_label: BTreeMap<String, (String, Option<(String, Option<f64>, String, String)>, Vec<usize>)> = BTreeMap::new();
    for (p, r, smi) in &enriched {
        let lab = r.compound_label.trim().to_string();
        let entry = by_label.entry(lab.clone()).or_insert_with(|| {
            (smi.clone().unwrap_or_default(), None, Vec::new())
        });
        if entry.0.is_empty() {
            if let Some(s) = smi {
                entry.0 = s.clone();
            }
        }
        if entry.1.is_none() {
            entry.1 = Some((
                r.activity_type.clone().unwrap_or_default(),
                r.value.as_ref().and_then(|v| v.as_f64()),
                r.unit.clone().unwrap_or_default(),
                r.target.clone().unwrap_or_default(),
            ));
        }
        if !entry.2.contains(p) {
            entry.2.push(*p);
        }
    }
    let molecules: Vec<_> = by_label
        .into_iter()
        .map(|(k, (s, a, ps))| (k, s, a, ps))
        .collect();
    write_okf_bundle(&bundle_root, &patent_id, &pdf, &molecules).map_err(|e| e.to_string())?;

    Ok(OkfPipelineResult {
        patent_id,
        text_pages: total,
        activity_records: enriched.len(),
        records_with_smiles: with_smi,
        molecules_total,
        molecules_with_activity,
        okf_bundle_path: bundle_root.display().to_string(),
        elapsed_s: t0.elapsed().as_secs_f64(),
        warnings,
    })
}
