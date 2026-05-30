use std::collections::HashMap;

use grep_regex::RegexMatcherBuilder;
use grep_searcher::sinks::UTF8;
use grep_searcher::SearcherBuilder;
use ignore::WalkBuilder;

use super::markush;
use super::tools::{ToolInfo, ToolRegistry};

pub struct ToolExecutor {
    pub sidecar_url: String,
    pub project_root: String,
    pub registry: ToolRegistry,
    // 可选依赖（Agent 工具 Native 化后注入）
    pub kb: Option<super::knowledge_base::KnowledgeBase>,
    pub tree_index: Option<super::document_tree::DocumentTreeIndex>,
    pub summary: Option<super::summary::SummaryManager>,
}

impl ToolExecutor {
    /// 原有构造函数（保持向后兼容，Agent::new() 调用这个）
    pub fn new(sidecar_url: &str, project_root: &str) -> Self {
        let mut registry = ToolRegistry::new();
        Self::register_native_tools(&mut registry, project_root);
        Self::register_sidecar_tools(&mut registry);
        Self {
            sidecar_url: sidecar_url.to_string(),
            project_root: project_root.to_string(),
            registry,
            kb: None,
            tree_index: None,
            summary: None,
        }
    }

    /// 带完整依赖的构造函数（index_project_rust 调用这个）
    pub fn new_with_deps(
        sidecar_url: &str,
        project_root: &str,
        kb: super::knowledge_base::KnowledgeBase,
        tree_index: super::document_tree::DocumentTreeIndex,
        summary: super::summary::SummaryManager,
    ) -> Self {
        let mut executor = Self::new(sidecar_url, project_root);
        executor.kb = Some(kb);
        executor.tree_index = Some(tree_index);
        executor.summary = Some(summary);
        executor.register_native_kb_tools();
        executor
    }

    /// 注入依赖（Agent 初始化后调用）
    pub fn set_kb(&mut self, kb: super::knowledge_base::KnowledgeBase) {
        self.kb = Some(kb);
        self.register_native_kb_tools();
    }
    pub fn set_tree_index(&mut self, tree: super::document_tree::DocumentTreeIndex) {
        self.tree_index = Some(tree);
    }
    pub fn set_summary(&mut self, summary: super::summary::SummaryManager) {
        self.summary = Some(summary);
    }

    /// 注册需要 KB/tree/summary 的 native 工具
    fn register_native_kb_tools(&mut self) {
        // search_knowledge_base — 如果 KB 可用则注册 native 版本
        if let Some(ref kb) = self.kb {
            // KB 搜索工具会在 KB 可用时覆盖 sidecar 版本
            // 但需要 async，暂时保留 sidecar
            let _ = kb; // 占位，后续 Agent C2 实现
        }
    }

    /// 注册 Rust 原生工具（直接执行，不走 sidecar）
    fn register_native_tools(registry: &mut ToolRegistry, project_root: &str) {
        let root = project_root.to_string();

        // grep_search — ripgrep 库实现
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("grep_search", "在项目文件中正则搜索内容（ripgrep 级性能）", {
                    let mut p = HashMap::new();
                    p.insert("pattern".into(), serde_json::json!({"type": "string"}));
                    p.insert("path".into(), serde_json::json!({"type": "string"}));
                    p.insert("max_results".into(), serde_json::json!({"type": "integer"}));
                    p
                }),
                Box::new(move |args| {
                    let pattern = args["pattern"].as_str().unwrap_or("");
                    let search_path = args["path"].as_str().unwrap_or("");
                    let max_results = args["max_results"].as_u64().unwrap_or(20) as usize;
                    native_grep_search(&r, pattern, search_path, max_results)
                }),
            );
        }

        // list_files — ignore crate（.gitignore 感知）
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("list_files", "列出项目中的文件（遵循 .gitignore）", {
                    let mut p = HashMap::new();
                    p.insert("pattern".into(), serde_json::json!({"type": "string"}));
                    p.insert("max_results".into(), serde_json::json!({"type": "integer"}));
                    p
                }),
                Box::new(move |args| {
                    let pattern = args["pattern"].as_str().unwrap_or("");
                    let max_results = args["max_results"].as_u64().unwrap_or(50) as usize;
                    native_list_files(&r, pattern, max_results)
                }),
            );
        }

        // read_file
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("read_file", "读取项目中指定文件的内容", {
                    let mut p = HashMap::new();
                    p.insert("path".into(), serde_json::json!({"type": "string"}));
                    p.insert("max_lines".into(), serde_json::json!({"type": "integer"}));
                    p
                }),
                Box::new(move |args| {
                    let file_path = args["path"].as_str().unwrap_or("");
                    let max_lines = args["max_lines"].as_u64().unwrap_or(200) as usize;
                    native_read_file(&r, file_path, max_lines)
                }),
            );
        }

        // get_project_info
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("get_project_info", "获取项目基本信息（文件数、目录结构等）", HashMap::new()),
                Box::new(move |_args| native_get_project_info(&r)),
            );
        }

        // glob_search — globset crate
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("glob_search", "按 glob 模式搜索文件名", {
                    let mut p = HashMap::new();
                    p.insert("pattern".into(), serde_json::json!({"type": "string"}));
                    p.insert("max_results".into(), serde_json::json!({"type": "integer"}));
                    p
                }),
                Box::new(move |args| {
                    let pattern = args["pattern"].as_str().unwrap_or("");
                    let max_results = args["max_results"].as_u64().unwrap_or(50) as usize;
                    native_glob_search(&r, pattern, max_results)
                }),
            );
        }

        // check_markush_overlap — E-SMILES Markush 专利范围检查
        registry.register_with_fn(
            ToolInfo::new("check_markush_overlap", "检查一个分子（SMILES）是否落在一个 Markush 专利通式（E-SMILES）的范围内", {
                let mut p: HashMap<String, serde_json::Value> = HashMap::new();
                p.insert("esmiles".into(), serde_json::json!({"type": "string", "description": "E-SMILES Markush pattern (e.g. *c1ccccc1<sep><a>0:R[1]</a>)"}));
                p.insert("query_smiles".into(), serde_json::json!({"type": "string", "description": "Query molecule SMILES (e.g. Fc1ccccc1)"}));
                p.insert("rgroup_text".into(), serde_json::json!({"type": "string", "description": "Optional patent text defining R-groups (e.g. R[1] is halogen)"}));
                p
            }),
            Box::new(move |args| {
                let esmiles = args["esmiles"].as_str().unwrap_or("");
                let query = args["query_smiles"].as_str().unwrap_or("");
                let rtext = args.get("rgroup_text").and_then(|v| v.as_str());
                if esmiles.is_empty() || query.is_empty() {
                    return serde_json::json!({"error": "esmiles and query_smiles are required"}).to_string();
                }
                let result = markush::analyze_markush_coverage(esmiles, query, rtext);
                serde_json::to_string(&result).unwrap_or_else(|e| format!("Serialization error: {}", e))
            }),
        );

        // search_knowledge_base — Rust Native（替代 Sidecar）
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("search_knowledge_base", "搜索项目知识库，基于语义相似度检索相关文档内容", {
                    let mut p = HashMap::new();
                    p.insert("query".into(), serde_json::json!({"type": "string"}));
                    p.insert("top_k".into(), serde_json::json!({"type": "integer"}));
                    p
                }),
                Box::new(move |args| {
                    let query = args["query"].as_str().unwrap_or("");
                    let top_k = args["top_k"].as_u64().unwrap_or(5) as usize;
                    match native_search_knowledge_base(&r, query, top_k) {
                        Ok(results) => serde_json::to_string(&results).unwrap_or_else(|e| format!("Serialize error: {}", e)),
                        Err(e) => format!("Search error: {}", e),
                    }
                }),
            );
        }

        // get_document_structure — Rust Native
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("get_document_structure", "获取文档的章节结构树（heading 层级）", {
                    let mut p = HashMap::new();
                    p.insert("doc_id".into(), serde_json::json!({"type": "string"}));
                    p
                }),
                Box::new(move |args| {
                    let doc_id = args["doc_id"].as_str().unwrap_or("");
                    match native_get_document_structure(&r, doc_id) {
                        Ok(tree) => serde_json::to_string(&tree).unwrap_or_else(|e| format!("Serialize error: {}", e)),
                        Err(e) => format!("Structure error: {}", e),
                    }
                }),
            );
        }

        // get_document_pages — Rust Native
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("get_document_pages", "按页码获取文档的原始文本内容", {
                    let mut p = HashMap::new();
                    p.insert("doc_id".into(), serde_json::json!({"type": "string"}));
                    p.insert("pages".into(), serde_json::json!({"type": "string", "description": "页码范围，如 '5-7,10'"}));
                    p
                }),
                Box::new(move |args| {
                    let doc_id = args["doc_id"].as_str().unwrap_or("");
                    let pages = args["pages"].as_str().unwrap_or("");
                    match native_get_document_pages(&r, doc_id, pages) {
                        Ok(pages) => serde_json::to_string(&pages).unwrap_or_else(|e| format!("Serialize error: {}", e)),
                        Err(e) => format!("Pages error: {}", e),
                    }
                }),
            );
        }

        // read_document_abstract — 从 SummaryManager 读 L0
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("read_document_abstract", "读取文档的一句话摘要（L0）", {
                    let mut p = HashMap::new();
                    p.insert("doc_id".into(), serde_json::json!({"type": "string"}));
                    p
                }),
                Box::new(move |args| {
                    let doc_id = args["doc_id"].as_str().unwrap_or("");
                    native_read_document_abstract(&r, doc_id)
                }),
            );
        }

        // read_document_overview — 从 SummaryManager 读 L1
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("read_document_overview", "读取文档的结构化概览（L1）", {
                    let mut p = HashMap::new();
                    p.insert("doc_id".into(), serde_json::json!({"type": "string"}));
                    p
                }),
                Box::new(move |args| {
                    let doc_id = args["doc_id"].as_str().unwrap_or("");
                    native_read_document_overview(&r, doc_id)
                }),
            );
        }

        // list_molecules — 从 MoleculeDatabase 查询
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("list_molecules", "列出项目中的分子数据", {
                    let mut p = HashMap::new();
                    p.insert("limit".into(), serde_json::json!({"type": "integer"}));
                    p
                }),
                Box::new(move |args| {
                    let limit = args["limit"].as_u64().unwrap_or(20) as usize;
                    native_list_molecules(&r, limit)
                }),
            );
        }

        // search_molecule_by_smiles — 从 MoleculeDatabase 查询
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("search_molecule_by_smiles", "按 SMILES 字符串搜索分子", {
                    let mut p = HashMap::new();
                    p.insert("smiles".into(), serde_json::json!({"type": "string"}));
                    p
                }),
                Box::new(move |args| {
                    let smiles = args["smiles"].as_str().unwrap_or("");
                    native_search_molecule_by_smiles(&r, smiles)
                }),
            );
        }

        // list_documents — 从 Project 查询
        {
            let r = root.clone();
            registry.register_with_fn(
                ToolInfo::new("list_documents", "列出项目中的所有文档", {
                    let mut p = HashMap::new();
                    p.insert("doc_type".into(), serde_json::json!({"type": "string"}));
                    p
                }),
                Box::new(move |args| {
                    let doc_type = args["doc_type"].as_str().unwrap_or("");
                    native_list_documents(&r, doc_type)
                }),
            );
        }
    }

    /// 注册需要 Python sidecar 的工具
    fn register_sidecar_tools(registry: &mut ToolRegistry) {
        let tools: Vec<(&str, &str, &[(&str, &str)])> = vec![
            ("find_documents", "按关键词查找文档", &[("keyword", "string"), ("doc_type", "string"), ("top_k", "integer")]),
            ("read_document_detail", "读取文档的完整内容块（L2）", &[("doc_id", "string"), ("max_chars", "integer")]),
            ("get_document_summary", "获取文档的元数据摘要", &[("doc_id", "string")]),
        ];
        for (name, desc, params) in tools {
            let properties: HashMap<String, serde_json::Value> = params.iter()
                .map(|(k, v)| (k.to_string(), serde_json::json!({"type": v})))
                .collect();
            registry.register(ToolInfo::new(name, desc, properties));
        }
    }

    pub async fn execute(&self, name: &str, args: &serde_json::Value) -> String {
        // 先查 native 工具
        if let Some(func) = self.registry.get_native(name) {
            return func(args);
        }
        // 走 sidecar
        self.execute_sidecar(name, args).await
    }

    async fn execute_sidecar(&self, name: &str, args: &serde_json::Value) -> String {
        let url = format!("{}/api/v1/tools/call", self.sidecar_url.trim_end_matches('/'));
        let body = serde_json::json!({
            "tool": name,
            "args": args,
            "project_root": self.project_root,
        });
        let client = match reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build() {
                Ok(c) => c,
                Err(e) => return format!("HTTP client error: {}", e),
            };
        let resp = match client.post(&url)
            .header("Content-Type", "application/json")
            .json(&body)
            .send()
            .await
        {
            Ok(r) => r,
            Err(e) => return format!("Sidecar unavailable: {}", e),
        };
        let text = match resp.text().await {
            Ok(t) => t,
            Err(e) => return format!("Read error: {}", e),
        };
        match serde_json::from_str::<serde_json::Value>(&text) {
            Ok(val) => {
                if val["success"].as_bool().unwrap_or(false) {
                    val["result"].as_str().unwrap_or("").to_string()
                } else {
                    val["error"].as_str().unwrap_or("Tool execution failed").to_string()
                }
            }
            Err(_) => text,
        }
    }
}

// ===== Rust 原生工具实现（均使用第三方 crate）=====

fn native_grep_search(root: &str, pattern: &str, search_path: &str, max_results: usize) -> String {
    let matcher = match RegexMatcherBuilder::new().build(pattern) {
        Ok(m) => m,
        Err(e) => return format!("Invalid regex: {}", e),
    };

    let target = if search_path.is_empty() {
        std::path::PathBuf::from(root)
    } else {
        std::path::PathBuf::from(root).join(search_path)
    };

    let mut results = Vec::new();
    let mut searcher = SearcherBuilder::new().line_number(true).build();

    let _ = searcher.search_path(&matcher, &target, UTF8(|line_number, line| {
        if results.len() >= max_results {
            return Ok(false);
        }
        results.push(format!("{}:{}:{}", target.display(), line_number, line.trim()));
        Ok(true)
    }));

    if results.is_empty() {
        "No matches found".to_string()
    } else {
        results.join("\n")
    }
}

fn native_list_files(root: &str, pattern: &str, max_results: usize) -> String {
    let walker = WalkBuilder::new(root).build();
    let glob = if pattern.is_empty() {
        None
    } else {
        match globset::Glob::new(pattern) {
            Ok(g) => Some(g.compile_matcher()),
            Err(e) => return format!("Invalid glob: {}", e),
        }
    };

    let mut results = Vec::new();
    for entry in walker.filter_map(|e| e.ok()) {
        if results.len() >= max_results {
            break;
        }
        let path = entry.path();
        if path.is_dir() {
            continue;
        }
        if let Some(ref g) = glob {
            if !g.is_match(path) {
                continue;
            }
        }
        if let Ok(rel) = path.strip_prefix(root) {
            results.push(rel.to_string_lossy().to_string());
        }
    }

    if results.is_empty() {
        "No files found".to_string()
    } else {
        format!("Found {} files:\n{}", results.len(), results.join("\n"))
    }
}

fn native_read_file(root: &str, file_path: &str, max_lines: usize) -> String {
    let path = std::path::PathBuf::from(root).join(file_path);
    if !path.exists() {
        return format!("File not found: {}", file_path);
    }
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(e) => return format!("Read error: {}", e),
    };
    let lines: Vec<&str> = content.lines().take(max_lines).collect();
    let total = content.lines().count();
    let truncated = if total > max_lines {
        format!("\n... ({} more lines)", total - max_lines)
    } else {
        String::new()
    };
    format!("{}{}", lines.join("\n"), truncated)
}

fn native_get_project_info(root: &str) -> String {
    let root_path = std::path::PathBuf::from(root);
    let mut file_count = 0u64;
    let mut dir_count = 0u64;
    let mut total_size = 0u64;
    let mut ext_counts: HashMap<String, u64> = HashMap::new();

    let walker = WalkBuilder::new(root).build();
    for entry in walker.filter_map(|e| e.ok()) {
        if entry.path().is_dir() {
            dir_count += 1;
        } else {
            file_count += 1;
            if let Ok(meta) = entry.metadata() {
                total_size += meta.len();
            }
            if let Some(ext) = entry.path().extension().and_then(|e| e.to_str()) {
                *ext_counts.entry(ext.to_string()).or_default() += 1;
            }
        }
    }

    let mut lines = vec![
        format!("Project: {}", root_path.file_name().unwrap_or_default().to_string_lossy()),
        format!("Path: {}", root),
        format!("Files: {}", file_count),
        format!("Directories: {}", dir_count),
        format!("Total size: {:.2} MB", total_size as f64 / 1_048_576.0),
    ];

    if !ext_counts.is_empty() {
        let mut sorted: Vec<_> = ext_counts.into_iter().collect();
        sorted.sort_by(|a, b| b.1.cmp(&a.1));
        lines.push("File types:".to_string());
        for (ext, count) in sorted.iter().take(10) {
            lines.push(format!("  .{}: {}", ext, count));
        }
    }

    lines.join("\n")
}

// ===== 知识库 Native 工具 =====

fn native_search_knowledge_base(
    root: &str,
    query: &str,
    top_k: usize,
) -> Result<Vec<serde_json::Value>, String> {
    let config = crate::core::config::EmbedConfig::default();
    let kb = crate::core::knowledge_base::KnowledgeBase::new(std::path::Path::new(root), &config)
        .map_err(|e| format!("KB init failed: {}", e))?;
    let results = futures::executor::block_on(kb.search(query, top_k))
        .map_err(|e| format!("Search failed: {}", e))?;
    Ok(results.into_iter().map(|r| serde_json::json!({
        "id": r.id,
        "text": r.text,
        "metadata": r.metadata,
        "score": r.score,
    })).collect())
}

fn native_get_document_structure(
    root: &str,
    doc_id: &str,
) -> Result<Option<Vec<crate::parsers::sections::TreeNode>>, String> {
    let config = crate::core::config::EmbedConfig::default();
    let kb = crate::core::knowledge_base::KnowledgeBase::new(std::path::Path::new(root), &config)
        .map_err(|e| format!("KB init failed: {}", e))?;
    Ok(kb.get_structure(doc_id))
}

fn native_get_document_pages(
    root: &str,
    doc_id: &str,
    pages: &str,
) -> Result<Vec<crate::core::knowledge_base::PageContent>, String> {
    let config = crate::core::config::EmbedConfig::default();
    let kb = crate::core::knowledge_base::KnowledgeBase::new(std::path::Path::new(root), &config)
        .map_err(|e| format!("KB init failed: {}", e))?;
    Ok(kb.get_pages(doc_id, pages))
}

// ===== 摘要 Native 工具 =====

fn native_read_document_abstract(root: &str, doc_id: &str) -> String {
    let project_root = std::path::PathBuf::from(root);
    match super::summary::SummaryManager::new(&project_root) {
        Ok(mgr) => match mgr.load(doc_id) {
            Some(s) => s.l0_abstract,
            None => format!("No summary found for doc_id: {}", doc_id),
        },
        Err(e) => format!("SummaryManager init error: {}", e),
    }
}

fn native_read_document_overview(root: &str, doc_id: &str) -> String {
    let project_root = std::path::PathBuf::from(root);
    match super::summary::SummaryManager::new(&project_root) {
        Ok(mgr) => match mgr.load(doc_id) {
            Some(s) => s.l1_overview,
            None => format!("No summary found for doc_id: {}", doc_id),
        },
        Err(e) => format!("SummaryManager init error: {}", e),
    }
}

// ===== 分子数据库 Native 工具 =====

fn native_list_molecules(root: &str, limit: usize) -> String {
    let db_path = std::path::PathBuf::from(root)
        .join(".mbforge")
        .join("molecules.db");
    if !db_path.exists() {
        return "No molecule database found".to_string();
    }
    match super::molecule_store::MoleculeDatabase::open(&db_path) {
        Ok(db) => match db.list_all(limit, 0, None, None) {
            Ok(mols) => serde_json::to_string(&mols).unwrap_or_else(|e| format!("Serialize error: {}", e)),
            Err(e) => format!("List error: {}", e),
        },
        Err(e) => format!("DB error: {}", e),
    }
}

fn native_search_molecule_by_smiles(root: &str, smiles: &str) -> String {
    let db_path = std::path::PathBuf::from(root)
        .join(".mbforge")
        .join("molecules.db");
    if !db_path.exists() {
        return "No molecule database found".to_string();
    }
    match super::molecule_store::MoleculeDatabase::open(&db_path) {
        Ok(db) => {
            let mut results = Vec::new();
            if let Ok(Some(rec)) = db.search_by_esmiles(smiles) {
                results.push(rec);
            }
            if let Ok(recs) = db.search_text(smiles) {
                for r in recs {
                    if !results.iter().any(|x| x.mol_id == r.mol_id) {
                        results.push(r);
                    }
                }
            }
            serde_json::to_string(&results).unwrap_or_else(|e| format!("Serialize error: {}", e))
        },
        Err(e) => format!("DB error: {}", e),
    }
}

// ===== 文档列表 Native 工具 =====

fn native_list_documents(root: &str, doc_type: &str) -> String {
    let project_root = std::path::PathBuf::from(root);
    match super::project::Project::open(&project_root) {
        Some(project) => {
            let docs = project.list_documents().to_vec();
            let filtered: Vec<_> = if doc_type.is_empty() {
                docs
            } else {
                docs.into_iter().filter(|d| d.doc_type == doc_type).collect()
            };
            let result: Vec<_> = filtered.iter().map(|d| {
                serde_json::json!({
                    "doc_id": d.doc_id,
                    "path": d.path,
                    "doc_type": d.doc_type,
                    "title": d.title,
                    "indexed": d.indexed,
                })
            }).collect();
            serde_json::to_string(&result).unwrap_or_else(|e| format!("Serialize error: {}", e))
        },
        None => "Project not found".to_string(),
    }
}

// ===== 文件搜索 Native 工具 =====

fn native_glob_search(root: &str, pattern: &str, max_results: usize) -> String {
    let glob = match globset::Glob::new(pattern) {
        Ok(g) => g.compile_matcher(),
        Err(e) => return format!("Invalid glob: {}", e),
    };

    let walker = WalkBuilder::new(root).build();
    let mut results = Vec::new();
    for entry in walker.filter_map(|e| e.ok()) {
        if results.len() >= max_results {
            break;
        }
        if entry.path().is_file() && glob.is_match(entry.path()) {
            if let Ok(rel) = entry.path().strip_prefix(root) {
                results.push(rel.to_string_lossy().to_string());
            }
        }
    }

    if results.is_empty() {
        "No files matched".to_string()
    } else {
        format!("Found {} files:\n{}", results.len(), results.join("\n"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tool_registration() {
        let executor = ToolExecutor::new("http://localhost:18792", "/tmp/test");
        // native + sidecar
        let tools = executor.registry.list();
        assert!(tools.len() >= 15);
        assert!(executor.registry.get("grep_search").is_some());
        assert!(executor.registry.get("search_knowledge_base").is_some());
    }

    #[test]
    fn test_tool_executor_defaults() {
        let executor = ToolExecutor::new("http://localhost:18792", "/tmp/test");
        assert!(executor.kb.is_none());
        assert!(executor.tree_index.is_none());
        assert!(executor.summary.is_none());
    }
}
