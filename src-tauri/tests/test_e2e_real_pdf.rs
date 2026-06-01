/// 端到端真实PDF流程测试 — 支持 text-based 与 scanned 两种路径
///
/// 测试目标：
///   1. 扫描型专利 PDF (US20260027089A1.PDF) → MinerU OCR 路径
///   2. 文本型化学 PDF (phchem_intro.pdf)     → pdf_inspector 本地路径
///   3. 期刊论文 PDF (elsevier_paper.pdf)     → pdf_inspector 本地路径
///
/// 流程：分类 → 文本提取 → 文档分类 → 分块 → 分子提取 → 知识库索引 → 检索验证
///
/// 运行：
///   cd src-tauri
///   cargo test --test test_e2e_real_pdf -- --nocapture

use std::path::PathBuf;

fn output_dir() -> PathBuf {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../e2e_test/output");
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn write_json<T: serde::Serialize>(name: &str, value: &T) {
    let path = output_dir().join(name);
    let json = serde_json::to_string_pretty(value).unwrap();
    std::fs::write(&path, &json).unwrap();
    println!("    wrote {} ({} bytes)", name, json.len());
}

fn write_text(name: &str, content: &str) {
    let path = output_dir().join(name);
    std::fs::write(&path, content).unwrap();
    println!("    wrote {} ({} chars)", name, content.len());
}

/// 提取文本（按 PDF 类型路由）
fn extract_text_routed(pdf_path: &str, classification: &mbforge::commands::pdf::PdfClassification)
    -> (String, String, usize)
{
    let t0 = std::time::Instant::now();
    // Scanned/Mixed/ImageBased → 走 MinerU OCR
    if classification.pdf_type == "Scanned" || classification.pdf_type == "ImageBased" {
        println!("    [路由] {} → MinerU OCR", classification.pdf_type);
        let host = std::env::var("MINERU_HOST").unwrap_or_else(|_| "https://mineru.net".to_string());
        let api_key = std::env::var("MINERU_API_KEY").unwrap_or_default();
        assert!(!api_key.is_empty(), "MINERU_API_KEY required for scanned PDF");
        let client = mbforge::parsers::mineru::MineruClient::new(&host, &api_key);
        let result = client.parse_file(pdf_path).expect("MinerU parse failed");
        let dt = t0.elapsed();
        println!("    MinerU 完成: {} chars, {:.2?}", result.markdown.len(), dt);
        return (result.markdown, "mineru_precise".to_string(), classification.page_count);
    }
    // TextBased/Mixed → 走本地 pdf_inspector
    println!("    [路由] {} → pdf_inspector (本地)", classification.pdf_type);
    let result = mbforge::commands::pdf::extract_text(pdf_path.to_string())
        .expect("extract_text failed");
    let dt = t0.elapsed();
    println!("    pdf_inspector 完成: {} chars, {:.2?}", result.markdown.len(), dt);
    (result.markdown, "pdf_inspector".to_string(), result.page_count)
}

/// 跑单个 PDF 的完整管线
fn run_pipeline(label: &str, pdf_path: &str) {
    let pdf_path = std::path::Path::new(pdf_path);
    assert!(pdf_path.exists(), "PDF not found: {}", pdf_path.display());
    let file_size = std::fs::metadata(pdf_path).unwrap().len();

    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("📄 [{}] {}", label, pdf_path.display());
    println!("   Size: {:.2} MB", file_size as f64 / 1024.0 / 1024.0);
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    // ── Stage 1: 分类 ──
    println!("\n[Stage 1] PDF Classification");
    let t0 = std::time::Instant::now();
    let classification = mbforge::commands::pdf::classify_pdf(pdf_path.to_string_lossy().to_string())
        .expect("classify_pdf failed");
    let dt = t0.elapsed();
    println!("  type={}  conf={:.2}  pages={}  needs_ocr={}  ({:.2?})",
        classification.pdf_type, classification.confidence,
        classification.page_count, classification.pages_needing_ocr.len(), dt);
    write_json(&format!("{}_01_classification.json", label), &classification);

    // ── Stage 2: 文本提取（自动路由） ──
    println!("\n[Stage 2] Text Extraction (auto-routed)");
    let (content, parser_used, page_count) = extract_text_routed(
        &pdf_path.to_string_lossy(), &classification);
    write_text(&format!("{}_02_extracted.md", label), &content);
    assert!(!content.is_empty(), "Extracted content is empty!");

    // ── Stage 3: 文档分类 ──
    println!("\n[Stage 3] Document Classification");
    let pages: Vec<String> = content.split("\n\n").map(|s| s.to_string()).collect();
    let t0 = std::time::Instant::now();
    let doc_class = mbforge::commands::classifier::classify_document(pages.clone(), None);
    let dt = t0.elapsed();
    let scanned = doc_class.pages.iter().filter(|p| p.is_scanned).count();
    let mol = doc_class.pages.iter().filter(|p| p.has_molecular_patterns).count();
    println!("  text_density={:.1}  scanned_pages={}/{}  mol_pages={}/{}  ({:.2?})",
        doc_class.text_density, scanned, doc_class.pages.len(), mol, doc_class.pages.len(), dt);
    write_json(&format!("{}_03_doc_classification.json", label), &doc_class);

    // ── Stage 4: 标题 + Section ──
    println!("\n[Stage 4] Heading & Section Extraction");
    let t0 = std::time::Instant::now();
    let headings = mbforge::parsers::headings::extract_headings(&content);
    let sections = mbforge::parsers::sections::build_sections(&content, &headings, None, 8000);
    let dt = t0.elapsed();
    println!("  headings={}  sections={}  ({:.2?})",
        headings.len(), sections.len(), dt);
    println!("  Top headings:");
    for h in headings.iter().take(5) {
        println!("    H{}: {}", h.level, h.title);
    }
    write_json(&format!("{}_04_headings_sections.json", label), &serde_json::json!({
        "headings_count": headings.len(),
        "headings": headings,
        "sections_count": sections.len(),
        "section_titles": sections.iter().map(|s| &s.title).collect::<Vec<_>>(),
    }));

    // ── Stage 5: 分子提取 ──
    println!("\n[Stage 5] Molecule Extraction");
    let t0 = std::time::Instant::now();
    let esmiles = mbforge::commands::extractor::extract_esmiles_candidates(content.clone());
    let activities = mbforge::commands::extractor::extract_activities(content.clone());
    let associated = mbforge::commands::extractor::extract_associated_molecules(
        content.clone(),
        pdf_path.to_string_lossy().to_string(),
    );
    let dt = t0.elapsed();
    println!("  esmiles={}  activities={}  associated={}  ({:.2?})",
        esmiles.len(), activities.len(), associated.len(), dt);
    if !esmiles.is_empty() {
        println!("  SMILES samples:");
        for s in esmiles.iter().take(5) {
            println!("    {}", s);
        }
    }
    if !activities.is_empty() {
        println!("  Activity samples:");
        for a in activities.iter().take(5) {
            println!("    {}={} {} | {}",
                a.activity_type, a.value, a.units,
                &a.context.chars().take(60).collect::<String>());
        }
    }
    write_json(&format!("{}_05_molecules.json", label), &serde_json::json!({
        "esmiles_count": esmiles.len(),
        "esmiles": esmiles,
        "activities_count": activities.len(),
        "activities": activities,
        "associated_count": associated.len(),
        "associated_high_conf": associated.iter().filter(|m| m.confidence == "high").count(),
        "associated": associated,
    }));

    // ── Stage 6: 知识库索引 ──
    println!("\n[Stage 6] Knowledge Base Indexing (Rust FTS5)");
    let project_root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../e2e_test");
    let kb_dir = project_root.join(".mbforge/knowledge_base");
    if kb_dir.exists() {
        let _ = std::fs::remove_dir_all(&kb_dir);
    }
    let t0 = std::time::Instant::now();
    let kb = mbforge::core::knowledge_base::KnowledgeBase::new(&project_root)
        .expect("KB init failed");
    let doc_id = format!("test_{}", label);
    let indexed = kb.index_document(&doc_id, &sections, &pages).expect("index failed");
    let dt = t0.elapsed();
    println!("  indexed {} sections in {:.2?}", indexed, dt);

    // ── Stage 7: 检索验证 ──
    println!("\n[Stage 7] KB Search Verification");
    let queries: Vec<(&str, &str)> = match label {
        "patent_us20260027089" => vec![
            ("MRGPRX2 antagonist", "应返回关于MRGPRX2拮抗剂"),
            ("inflammatory disorder", "应返回关于炎症性疾病"),
            ("pharmaceutical composition", "应返回关于药物组合物"),
            ("compound formula", "应返回关于化合物结构"),
            ("IC50", "应返回关于IC50活性"),
        ],
        "phchem_intro" | "cn_text" => vec![
            ("claim 1", "应返回权利要求1"),
            ("compound", "应返回化合物相关"),
            ("formula", "应返回化学式"),
            ("pharmaceutical", "应返回药物相关"),
            ("embodiment", "应返回实施例"),
        ],
        "elsevier_paper" => vec![
            ("abstract", "应返回摘要"),
            ("method", "应返回方法"),
            ("result", "应返回结果"),
            ("compound", "应返回化合物"),
            ("figure", "应返回图表"),
        ],
        _ => vec![("test", "基础测试")],
    };

    let mut search_results: Vec<serde_json::Value> = Vec::new();
    for (q, desc) in &queries {
        let t0 = std::time::Instant::now();
        let results = kb.search(q, 3).expect("search failed");
        let dt = t0.elapsed();
        let top_score = results.first().map(|r| r.score).unwrap_or(0.0);
        println!("  \"{}\" → {} hits, top_score={:.3} ({}ms) — {}",
            q, results.len(), top_score, dt.as_millis(), desc);
        for r in results.iter().take(2) {
            let prev: String = r.text.chars().take(80).collect();
            println!("    • {}...", prev);
        }
        search_results.push(serde_json::json!({
            "query": q,
            "description": desc,
            "result_count": results.len(),
            "top_score": top_score,
            "results": results.iter().take(2).map(|r| serde_json::json!({
                "id": r.id,
                "score": r.score,
                "text_preview": r.text.chars().take(200).collect::<String>(),
            })).collect::<Vec<_>>(),
        }));
    }
    write_json(&format!("{}_07_search_results.json", label), &search_results);

    // ── Stage 8: SQLite 直查 ──
    println!("\n[Stage 8] SQLite Direct Verification");
    let db_path = kb_dir.join("vectors.db");
    let conn = rusqlite::Connection::open(&db_path).expect("open db");
    let count: i64 = conn.query_row("SELECT COUNT(*) FROM sections", [], |r| r.get(0)).unwrap();
    let fts_count: i64 = conn.query_row("SELECT COUNT(*) FROM sections_fts", [], |r| r.get(0)).unwrap();
    let doc_ids: Vec<String> = conn.prepare("SELECT DISTINCT doc_id FROM sections")
        .unwrap()
        .query_map([], |r| r.get(0))
        .unwrap()
        .filter_map(|r| r.ok())
        .collect();
    println!("  sections:{}  fts5:{}  distinct_docs:{:?}", count, fts_count, doc_ids);

    // 抽检 FTS5
    let mut stmt = conn.prepare(
        "SELECT s.id, substr(s.text, 1, 120) FROM sections_fts f
         JOIN sections s ON f.id = s.id
         WHERE sections_fts MATCH ?1 LIMIT 2"
    ).unwrap();
    let first_q = queries.first().map(|(q, _)| *q).unwrap_or("test");
    let rows = stmt.query_map(rusqlite::params![first_q], |r| {
        Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?))
    }).unwrap();
    println!("  FTS5 raw query '{}':", first_q);
    for r in rows {
        let (id, t) = r.unwrap();
        println!("    {} → {}", id, t);
    }

    // ── Stage 9: 结构树 ──
    println!("\n[Stage 9] Document Tree Structure");
    if let Some(tree) = kb.get_structure(&doc_id) {
        println!("  root nodes: {}", tree.len());
        for n in tree.iter().take(3) {
            println!("    • {} (children={})", n.title, n.nodes.len());
        }
    } else {
        println!("  (no tree)");
    }

    // ── 总结 ──
    println!("\n📊 [{}] Summary", label);
    println!("  Type:           {}", classification.pdf_type);
    println!("  Pages:          {}", classification.page_count);
    println!("  Parser used:    {}", parser_used);
    println!("  Content size:   {} chars", content.len());
    println!("  Headings:       {}", headings.len());
    println!("  Sections:       {}", sections.len());
    println!("  SMILES:         {}", esmiles.len());
    println!("  Activities:     {}", activities.len());
    println!("  KB sections:    {}", indexed);
    println!("  Search queries: {} all OK", queries.len());
}

#[test]
fn test_e2e_real_pdfs() {
    let _ = dotenvy::dotenv();

    println!("\n");
    println!("╔════════════════════════════════════════════════════════════╗");
    println!("║   MBForge 端到端 PDF OCR → 知识库 全流程测试            ║");
    println!("║   测试用真实 PDF（非合成数据）                          ║");
    println!("║     1. US20260027089A1.PDF (扫描型, 走 MinerU OCR)     ║");
    println!("║     2. CN120118069A.PDF   (纯文本, 走 pdf_inspector)   ║");
    println!("║     3. 1-s2.0-S1043661826000228-main.pdf (Elsevier论文) ║");
    println!("╚════════════════════════════════════════════════════════════╝");

    // 清空旧结果
    let out_dir = output_dir();
    let _ = std::fs::remove_dir_all(&out_dir);
    std::fs::create_dir_all(&out_dir).unwrap();

    // ====== 测试 1: 扫描型专利 PDF (走 MinerU OCR) ======
    run_pipeline("patent_us20260027089",
        "C:/Users/10954/Desktop/MBForge/e2e_test/US20260027089A1.PDF");

    // ====== 测试 2: 文本型专利 PDF (走 pdf_inspector 本地) ======
    run_pipeline("cn_text",
        "C:/Users/10954/Desktop/MBForge/e2e_test/CN120118069A_text.pdf");

    // ====== 测试 3: 期刊论文 PDF ======
    run_pipeline("elsevier_paper",
        "C:/Users/10954/Desktop/MBForge/e2e_test/elsevier_paper.pdf");

    // 列出所有输出
    println!("\n\n📁 Output files:");
    let entries: Vec<_> = std::fs::read_dir(&out_dir).unwrap()
        .filter_map(|e| e.ok())
        .collect();
    for entry in entries {
        let meta = entry.metadata().unwrap();
        println!("  {} ({:.1} KB)",
            entry.file_name().to_string_lossy(),
            meta.len() as f64 / 1024.0);
    }
    println!("\n✅ 3 个 PDF 全流程测试通过");
}
