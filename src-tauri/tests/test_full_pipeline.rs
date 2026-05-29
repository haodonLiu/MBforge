/// Full pipeline integration test — runs on the real patent PDF
/// and writes all intermediate results to tests/integration/output/
///
/// Usage:
///   cd src-tauri
///   cargo test --test test_full_pipeline -- --nocapture

use std::path::PathBuf;

fn output_dir() -> PathBuf {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../tests/integration/output");
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn write_file(name: &str, content: &str) -> PathBuf {
    let path = output_dir().join(name);
    std::fs::write(&path, content).unwrap();
    println!("  -> wrote {} ({} chars)", name, content.len());
    path
}

#[test]
fn test_full_pipeline_with_real_patent() {
    // Load .env
    let _ = dotenvy::dotenv();

    let pdf_path = "C:/Users/10954/Desktop/X2/US20260027089A1.PDF";
    if !std::path::Path::new(pdf_path).exists() {
        eprintln!("Skipping: patent PDF not found");
        return;
    }

    println!("\n========== Stage 1: PDF Classification ==========");
    let classification = mbforge::commands::pdf::classify_pdf(pdf_path.to_string()).unwrap();
    let class_json = serde_json::to_string_pretty(&classification).unwrap();
    write_file("01_classification.json", &class_json);
    println!("  pdf_type: {}", classification.pdf_type);
    println!("  page_count: {}", classification.page_count);
    println!("  needs_ocr: {:?}", classification.pages_needing_ocr);

    println!("\n========== Stage 2: Text Extraction (MinerU Precise) ==========");
    let host = std::env::var("MINERU_HOST").unwrap_or_else(|_| "https://mineru.net".to_string());
    let api_key = std::env::var("MINERU_API_KEY").unwrap_or_default();
    assert!(!api_key.is_empty(), "MINERU_API_KEY must be set in .env");

    let client = mbforge::parsers::mineru::MineruClient::new(&host, &api_key);
    let mineru_result = client.parse_file(pdf_path).expect("MinerU Precise API failed");
    write_file("02_mineru_markdown.md", &mineru_result.markdown);
    println!("  markdown length: {} chars", mineru_result.markdown.len());
    println!("  source: {}", mineru_result.source);

    let content = mineru_result.markdown;
    let page_count = classification.page_count;

    println!("\n========== Stage 3: Document Classification ==========");
    let pages: Vec<String> = content.split("\n\n").map(|s| s.to_string()).collect();
    let doc_classification = mbforge::commands::classifier::classify_document(pages, None);
    let doc_class_json = serde_json::to_string_pretty(&doc_classification).unwrap();
    write_file("03_document_classification.json", &doc_class_json);
    println!("  text_density: {:.1}", doc_classification.text_density);
    println!("  is_scanned: {}", doc_classification.is_scanned);
    println!("  has_molecular_patterns: {}", doc_classification.has_molecular_patterns);

    println!("\n========== Stage 4: Text Chunking ==========");
    let chunk_result = mbforge::commands::text_ops::text_chunk(content.clone(), 512, 128);
    let chunks_json = serde_json::to_string_pretty(&serde_json::json!({
        "total_chunks": chunk_result.total_chunks,
        "chunks_preview": chunk_result.chunks.iter().take(5).enumerate().map(|(i, c)| {
            serde_json::json!({"index": i, "length": c.len(), "preview": &c[..c.len().min(200)]})
        }).collect::<Vec<_>>(),
    })).unwrap();
    write_file("04_chunks.json", &chunks_json);
    // Write full chunks to a separate file
    let full_chunks = chunk_result.chunks.join("\n\n---CHUNK---\n\n");
    write_file("04_chunks_full.txt", &full_chunks);
    println!("  total chunks: {}", chunk_result.total_chunks);

    println!("\n========== Stage 5: Molecule Extraction ==========");
    let smiles = mbforge::commands::extractor::extract_smiles_candidates(content.clone());
    let activities = mbforge::commands::extractor::extract_activities(content.clone());
    let mol_json = serde_json::to_string_pretty(&serde_json::json!({
        "smiles_count": smiles.len(),
        "smiles": smiles,
        "activities_count": activities.len(),
        "activities": activities,
    })).unwrap();
    write_file("05_molecules.json", &mol_json);
    println!("  SMILES candidates: {}", smiles.len());
    println!("  Activity records: {}", activities.len());

    println!("\n========== Stage 6: Assemble PdfParseResult ==========");
    let parse_result = mbforge::parsers::pipeline::PdfParseResult {
        content: content.clone(),
        classification: doc_classification,
        chunks: chunk_result.chunks,
        smiles: smiles.clone(),
        activities: activities.clone(),
        parser: "mineru_precise".to_string(),
        page_count,
    };
    let parse_json = serde_json::to_string_pretty(&parse_result).unwrap();
    write_file("06_parse_result.json", &parse_json);
    println!("  assembled PdfParseResult ({} chars)", parse_json.len());

    println!("\n========== Stage 7: LLM Post-Processing ==========");
    match mbforge::parsers::post_process::post_process(&parse_result) {
        Ok(post_result) => {
            let post_json = serde_json::to_string_pretty(&post_result).unwrap();
            write_file("07_post_process_result.json", &post_json);
            write_file("07_report.md", &post_result.report);
            println!("  model: {}", post_result.model);
            println!("  tokens_used: {:?}", post_result.tokens_used);
            println!("  batch_count: {}", post_result.batch_count);
            println!("  report: {} chars", post_result.report.len());
            println!("  compounds: {}", post_result.data.compounds.len());
            println!("  activities: {}", post_result.data.activities.len());
            println!("  key_findings: {}", post_result.data.key_findings.len());
            println!("  uncertain_items: {}", post_result.data.uncertain_items.len());
            for u in &post_result.data.uncertain_items {
                println!("    ⚠️  [{}] {} — {}", u.item_type, u.content, u.reason);
            }
        }
        Err(e) => {
            eprintln!("  LLM post-processing failed: {}", e);
            write_file("07_post_process_error.txt", &e);
        }
    }

    println!("\n========== Output Files ==========");
    let entries: Vec<_> = std::fs::read_dir(output_dir()).unwrap()
        .filter_map(|e| e.ok())
        .collect();
    for entry in entries {
        let meta = entry.metadata().unwrap();
        println!("  {} ({:.1} KB)", entry.file_name().to_string_lossy(), meta.len() as f64 / 1024.0);
    }

    println!("\nDone! All output in: {}", output_dir().display());
}
