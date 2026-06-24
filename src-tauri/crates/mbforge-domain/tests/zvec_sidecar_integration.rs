//! End-to-end integration test for the Zvec sidecar-backed SearchEngine.
//!
//! This test assumes a Python sidecar is running on `127.0.0.1:18792`.
//! Run it manually with:
//!
//! ```bash
//! # Terminal 1
//! uv run uvicorn mbforge.server:app --host 127.0.0.1 --port 18792
//!
//! # Terminal 2
//! cd src-tauri && cargo test --test zvec_sidecar_integration -- --nocapture
//! ```

use std::path::PathBuf;

use mbforge_domain::document::search_engine::{SearchEngine, SearchResult};
use tempfile::TempDir;

#[test]
fn search_engine_indexes_and_searches_via_sidecar() {
    let tmp = TempDir::new().unwrap();
    let path: PathBuf = tmp.path().join("search.zvec");

    let engine = SearchEngine::open(&path, 4).expect("open collection via sidecar");

    engine
        .index_document(
            "doc1",
            &["doc1__sec0".to_string(), "doc1__sec1".to_string()],
            &["hello world".to_string(), "foo bar".to_string()],
            &[
                r#"{"title":"Intro"}"#.to_string(),
                r#"{"title":"Body"}"#.to_string(),
            ],
            &[vec![1.0, 0.0, 0.0, 0.0], vec![0.0, 1.0, 0.0, 0.0]],
        )
        .expect("index document");

    assert_eq!(engine.count().expect("count"), 2);

    let vector_results: Vec<SearchResult> = engine
        .vector_search(&[1.0, 0.0, 0.0, 0.0], 5, None)
        .expect("vector search");
    assert!(!vector_results.is_empty());
    assert_eq!(vector_results[0].id, "doc1__sec0");

    let text_results = engine.text_search("hello", 5, None).expect("text search");
    assert!(text_results.iter().any(|r| r.id == "doc1__sec0"));

    let hybrid_results = engine
        .hybrid_search(&[1.0, 0.0, 0.0, 0.0], "hello world", 5, None)
        .expect("hybrid search");
    assert!(!hybrid_results.is_empty());

    engine.delete_document("doc1").expect("delete document");
    assert_eq!(engine.count().expect("count after delete"), 0);
}
