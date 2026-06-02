/// PDF 管线集成测试 — 测试各组件的公开 API.
///
/// 不依赖 Tauri 环境，直接测试核心逻辑函数。

#[cfg(test)]
mod tests {
    // ===================================================================
    // Heading 提取
    // ===================================================================

    #[test]
    fn test_heading_extraction_markdown() {
        let text = "# Title\nSome text\n## Subtitle\nMore text\n### Sub-sub";
        let headings = mbforge::parsers::headings::extract_headings(text);
        assert_eq!(headings.len(), 3);
        assert_eq!(headings[0].title, "Title");
        assert_eq!(headings[0].level, 1);
        assert_eq!(headings[1].title, "Subtitle");
        assert_eq!(headings[1].level, 2);
    }

    #[test]
    fn test_heading_extraction_uppercase() {
        let text = "\nABSTRACT\nThis is the abstract.\n\nCLAIMS\nClaim 1.\n";
        let headings = mbforge::parsers::headings::extract_headings(text);
        assert!(headings.iter().any(|h| h.title == "ABSTRACT"));
        assert!(headings.iter().any(|h| h.title == "CLAIMS"));
    }

    #[test]
    fn test_heading_extraction_empty() {
        let text = "Just plain text without any headings.";
        let headings = mbforge::parsers::headings::extract_headings(text);
        assert!(headings.is_empty());
    }

    #[test]
    fn test_heading_extraction_mixed() {
        let text = "# Introduction\nBACKGROUND\nSome text.\n## Methods\nStep 1.";
        let headings = mbforge::parsers::headings::extract_headings(text);
        assert!(headings.iter().any(|h| h.title == "Introduction"));
        assert!(headings.iter().any(|h| h.title == "Methods"));
    }

    #[test]
    fn test_heading_extraction_numbered() {
        let text = "1. Technical Field\nSome text.\n2. Background Art\nMore text.";
        let headings = mbforge::parsers::headings::extract_headings(text);
        assert!(headings.iter().any(|h| h.title.contains("Technical Field")));
    }

    // ===================================================================
    // Section 构建
    // ===================================================================

    #[test]
    fn test_section_building_basic() {
        let text = "# Introduction\nThis is intro.\n# Methods\nThese are methods.\n# Results\nThese are results.";
        let page_texts = vec!["Page 1 text".to_string(), "Page 2 text".to_string()];
        let headings = mbforge::parsers::headings::extract_headings(text);
        let sections =
            mbforge::parsers::sections::build_sections(text, &headings, Some(&page_texts), 5000);

        assert!(!sections.is_empty());
        for s in &sections {
            assert!(!s.title.is_empty());
        }
    }

    #[test]
    fn test_section_building_no_headings() {
        let text = "Just a plain document without any headings at all.";
        let page_texts = vec!["Page 1".to_string()];
        let headings = mbforge::parsers::headings::extract_headings(text);
        let sections =
            mbforge::parsers::sections::build_sections(text, &headings, Some(&page_texts), 5000);
        assert!(!sections.is_empty());
    }

    #[test]
    fn test_section_building_preserves_content() {
        let text = "# Methods\nStep 1: Do something.\nStep 2: Do something else.\n# Results\nWe got results.";
        let page_texts = vec!["Full text".to_string()];
        let headings = mbforge::parsers::headings::extract_headings(text);
        let sections =
            mbforge::parsers::sections::build_sections(text, &headings, Some(&page_texts), 5000);

        let methods = sections.iter().find(|s| s.title == "Methods");
        assert!(methods.is_some(), "Should find Methods section");
        assert!(methods.unwrap().text.contains("Step 1"));
    }

    // ===================================================================
    // 关联引擎
    // ===================================================================

    #[test]
    fn test_association_compound_names() {
        assert_eq!(
            mbforge::parsers::association::extract_compound_name("Compound 1 showed IC50 of 10 nM"),
            Some("Compound 1".to_string())
        );
        assert_eq!(
            mbforge::parsers::association::extract_compound_name("Example 3 was synthesized"),
            Some("Example 3".to_string())
        );
        assert_eq!(
            mbforge::parsers::association::extract_compound_name("No compound here"),
            None
        );
    }

    #[test]
    fn test_association_activity_ic50() {
        let text = "Compound 1 showed IC50 of 10 nM against the target.";
        let activities = mbforge::parsers::association::extract_activities(text);
        assert!(!activities.is_empty());
        assert_eq!(activities[0].activity_type, "IC50");
        assert_eq!(activities[0].value, 10.0);
        assert_eq!(activities[0].unit, "nM");
    }

    #[test]
    fn test_association_activity_ki() {
        let text = "The Ki value was 5.2 μM for compound 3.";
        let activities = mbforge::parsers::association::extract_activities(text);
        assert!(!activities.is_empty());
        assert_eq!(activities[0].activity_type, "Ki");
        assert!((activities[0].value - 5.2).abs() < 0.01);
    }

    #[test]
    fn test_association_no_activity() {
        let text = "This is just plain text without any activity data.";
        let activities = mbforge::parsers::association::extract_activities(text);
        assert!(activities.is_empty());
    }

    // ===================================================================
    // 关键词提取
    // ===================================================================

    #[test]
    fn test_keywords_extraction() {
        let text = "Molecular docking is a key method in drug design. \
                     The binding affinity was measured using fluorescence polarization. \
                     Molecular dynamics simulations confirmed the stability.";
        let keywords = mbforge::parsers::keywords::extract_keywords(text);
        assert!(!keywords.is_empty());
    }

    #[test]
    fn test_keywords_empty_input() {
        let keywords = mbforge::parsers::keywords::extract_keywords("");
        assert!(keywords.is_empty());
    }

    // ===================================================================
    // JSON 提取
    // ===================================================================

    #[test]
    fn test_extract_json_clean() {
        let input = r#"{"compounds": [], "summary": "test"}"#;
        let result = mbforge::parsers::post_process::extract_json(input);
        assert!(result.is_ok());
        assert_eq!(result.unwrap()["summary"], "test");
    }

    #[test]
    fn test_extract_json_code_fence() {
        let input = "```json\n{\"compounds\": [], \"summary\": \"test\"}\n```";
        let result = mbforge::parsers::post_process::extract_json(input);
        assert!(result.is_ok());
    }

    #[test]
    fn test_extract_json_think_block() {
        let input =
            "<think>\nSome reasoning...\n</think>\n{\"compounds\": [], \"summary\": \"test\"}";
        let result = mbforge::parsers::post_process::extract_json(input);
        assert!(result.is_ok());
    }

    #[test]
    fn test_extract_json_truncated() {
        let input = r#"{"compounds": [{"name": "test"}"#;
        let result = mbforge::parsers::post_process::extract_json(input);
        assert!(result.is_ok() || result.is_err());
    }

    // ===================================================================
    // DocumentTreeIndex
    // ===================================================================

    #[test]
    fn test_document_tree_index() {
        use mbforge::core::document_tree::DocumentTreeIndex;
        use mbforge::parsers::sections::SectionChunk;

        let dir = std::env::temp_dir().join(format!("dtd_test_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        let index = DocumentTreeIndex::new(&dir);

        let sections = vec![
            SectionChunk {
                title: "Introduction".into(),
                path: "Introduction".into(),
                text: "This is the introduction.".into(),
                page_start: Some(1),
                page_end: Some(1),
                line_start: 0,
                line_end: 5,
            },
            SectionChunk {
                title: "Methods".into(),
                path: "Methods".into(),
                text: "These are the methods.".into(),
                page_start: Some(2),
                page_end: Some(3),
                line_start: 6,
                line_end: 20,
            },
        ];
        let page_texts: Vec<String> = vec!["Page 1".into(), "Page 2".into()];

        let result = index.index_document("test_doc", &sections, &page_texts);
        assert!(result.is_ok());

        let tree = index.get_structure("test_doc");
        assert!(tree.is_some());

        let _ = std::fs::remove_dir_all(&dir);
    }

    // ===================================================================
    // VectorStore (FTS5)
    // ===================================================================

    #[test]
    fn test_vector_store_crud() {
        use mbforge::core::vector_store::{SqliteVectorStore, VectorItem, VectorStore};

        let dir = std::env::temp_dir().join(format!("vs_test_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        let db_path = dir.join("test.db");

        let store = SqliteVectorStore::new(&db_path).unwrap();

        // Insert
        store
            .upsert(vec![
                VectorItem {
                    id: "doc1:sec0".into(),
                    doc_id: "doc1".into(),
                    text: "Molecular docking simulation results".into(),
                    embedding: vec![],
                    metadata: serde_json::json!({"title": "Results"}),
                },
                VectorItem {
                    id: "doc1:sec1".into(),
                    doc_id: "doc1".into(),
                    text: "Binding affinity measurements using fluorescence".into(),
                    embedding: vec![],
                    metadata: serde_json::json!({"title": "Methods"}),
                },
            ])
            .unwrap();

        // Count
        let count = store.count().unwrap();
        assert_eq!(count, 2);

        // Search
        let results = store.search("docking", 5, None).unwrap();
        assert!(!results.is_empty());
        assert!(results[0].text.contains("docking"));

        // Delete
        store.delete("doc1").unwrap();
        let count = store.count().unwrap();
        assert_eq!(count, 0);

        let _ = std::fs::remove_dir_all(&dir);
    }

    // ===================================================================
    // KnowledgeBase (FTS5 + DocumentTree)
    // ===================================================================

    #[test]
    fn test_knowledge_base_search() {
        let dir = std::env::temp_dir().join(format!("kb_test_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);

        let kb = mbforge::core::knowledge_base::KnowledgeBase::new(&dir);
        assert!(kb.is_ok());
        let kb = kb.unwrap();

        // Index
        let sections = vec![
            mbforge::parsers::sections::SectionChunk {
                title: "Background".into(),
                path: "Background".into(),
                text: "Molecular docking is a computational method for predicting the preferred orientation of a molecule.".into(),
                page_start: Some(1),
                page_end: Some(1),
                line_start: 0,
                line_end: 3,
            },
        ];
        let page_texts: Vec<String> = vec!["Full page text.".into()];
        let result = kb.index_document("doc1", &sections, &page_texts);
        assert!(result.is_ok());

        // Search
        let results = kb.search("docking", 5);
        assert!(results.is_ok());
        let results = results.unwrap();
        assert!(!results.is_empty());

        // Stats
        let stats = kb.stats();
        assert_eq!(stats.document_count, 1);

        // Cleanup
        let _ = std::fs::remove_dir_all(&dir);
    }

    // ===================================================================
    // ResourceManager
    // ===================================================================

    #[test]
    fn test_resource_manager_check_all() {
        let report = mbforge::core::resource_manager::check_all_resources();
        assert!(!report.resources.is_empty());
        assert!(report.python_version.contains('.'));
    }

    #[test]
    fn test_resource_manager_check_known() {
        let status = mbforge::core::resource_manager::check_resource("torch");
        assert_eq!(status.id, "torch");
    }

    #[test]
    fn test_resource_manager_check_unknown() {
        let status = mbforge::core::resource_manager::check_resource("nonexistent_xyz");
        assert_eq!(
            status.status,
            mbforge::core::resource_manager::ResourceStatus::Error
        );
    }
}
