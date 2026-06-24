//! End-to-end integration test for the v2 PDF processing pipeline.

use mbforge_domain::project::project::Project;
use mbforge_pipeline::pipeline::context::PipelineContext;
use mbforge_pipeline::pipeline::models::source::SourceInput;
use mbforge_pipeline::pipeline::runner::run_pipeline;
use mbforge_pipeline::pipeline::services::cache::{Cache, CachedExtractResult};
use tempfile::TempDir;

#[tokio::test]
async fn pipeline_v2_processes_cached_pdf() {
    let tmp = TempDir::new().unwrap();
    let root = tmp.path();

    // Bootstrap an MBForge project and register a PDF document.
    let mut project = Project::create(root).expect("create project");
    let incoming = root.join("incoming");
    std::fs::create_dir_all(&incoming).unwrap();
    let source = incoming.join("sample.pdf");
    // Minimal valid PDF with one page and no embedded images so lopdf does not hang.
    let pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n196\n%%EOF\n";
    std::fs::write(&source, pdf_content).unwrap();

    let entry = project.add_file(&source).expect("add pdf");
    let doc_id = entry.doc_id.clone();
    let source_in_project = project
        .get_document_source_path(&doc_id)
        .expect("source path");

    // Pre-populate the file cache so the extract stage can run without a
    // real PDF parser or OCR backend. Empty text keeps the enrichment stage
    // sidecar-free and the index stage deterministic.
    let cache = mbforge_pipeline::pipeline::services::cache::FileCache::new(root);
    cache
        .put(
            &source_in_project.display().to_string(),
            &CachedExtractResult {
                text: "".into(),
                sections_json: "[]".into(),
                metadata_json: r#"{"page_count":1,"parser":"mineru"}"#.into(),
            },
        )
        .unwrap();

    let ctx = PipelineContext::new(&source_in_project, "").with_project_root(root);
    let input = SourceInput::new(&source_in_project).with_allow_ocr(false);

    let indexed = run_pipeline(input, &ctx)
        .await
        .expect("pipeline should succeed");
    assert_eq!(indexed.doc_id, doc_id);
    assert_eq!(indexed.indexed_sections, 0);

    // Verify the expected output artifacts were written.
    let project_dir = root.join("projects").join(&doc_id);
    assert!(
        project_dir.join("text.md").exists(),
        "text.md should be generated"
    );
    assert!(
        project_dir.join("report.md").exists(),
        "report.md should be generated"
    );
}
