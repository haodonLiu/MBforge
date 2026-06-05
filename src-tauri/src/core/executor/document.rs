//! Document access tools — abstracts, overviews, listing, finding, summary.

use std::collections::HashMap;

use crate::core::agent::tools::{ToolInfo, ToolRegistry};

/// Register all document-access native tools.
pub fn register(registry: &mut ToolRegistry, project_root: &str) {
    let root = project_root.to_string();

    // read_document_abstract — 从 SummaryManager 读 L0
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new(
            "read_document_abstract",
            "读取文档的一句话摘要（L0）",
            {
                let mut p = HashMap::new();
                p.insert("doc_id".into(), serde_json::json!({"type": "string"}));
                p
            },
        ),
        Box::new(move |args| {
            let doc_id = args["doc_id"].as_str().unwrap_or("");
            native_read_document_abstract(&r, doc_id)
        }),
    );

    // read_document_overview — 从 SummaryManager 读 L1
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new(
            "read_document_overview",
            "读取文档的结构化概览（L1）",
            {
                let mut p = HashMap::new();
                p.insert("doc_id".into(), serde_json::json!({"type": "string"}));
                p
            },
        ),
        Box::new(move |args| {
            let doc_id = args["doc_id"].as_str().unwrap_or("");
            native_read_document_overview(&r, doc_id)
        }),
    );

    // list_documents — 从 Project 查询
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

    // get_document_summary — 文档元数据摘要
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new("get_document_summary", "获取文档的元数据摘要", {
            let mut p = HashMap::new();
            p.insert("doc_id".into(), serde_json::json!({"type": "string"}));
            p
        }),
        Box::new(move |args| {
            let doc_id = args["doc_id"].as_str().unwrap_or("");
            native_get_document_summary(&r, doc_id)
        }),
    );

    // read_document_detail — 读取文档完整内容
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new(
            "read_document_detail",
            "读取文档的完整内容块（L2）",
            {
                let mut p = HashMap::new();
                p.insert("doc_id".into(), serde_json::json!({"type": "string"}));
                p.insert("max_chars".into(), serde_json::json!({"type": "integer"}));
                p
            },
        ),
        Box::new(move |args| {
            let doc_id = args["doc_id"].as_str().unwrap_or("");
            let max_chars = args["max_chars"].as_u64().unwrap_or(4000) as usize;
            native_read_document_detail(&r, doc_id, max_chars)
        }),
    );

    // find_documents — 按关键词查找文档
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new(
            "find_documents",
            "按关键词查找文档（支持 L0 摘要过滤）",
            {
                let mut p = HashMap::new();
                p.insert("keyword".into(), serde_json::json!({"type": "string"}));
                p.insert("doc_type".into(), serde_json::json!({"type": "string"}));
                p.insert("top_k".into(), serde_json::json!({"type": "integer"}));
                p
            },
        ),
        Box::new(move |args| {
            let keyword = args["keyword"].as_str().unwrap_or("");
            let doc_type = args["doc_type"].as_str().unwrap_or("");
            let top_k = args["top_k"].as_u64().unwrap_or(5) as usize;
            native_find_documents(&r, keyword, doc_type, top_k)
        }),
    );
}

// ===== Native implementations =====

fn native_read_document_abstract(root: &str, doc_id: &str) -> String {
    let project_root = std::path::PathBuf::from(root);
    match crate::core::document::summary::SummaryManager::new(&project_root) {
        Ok(mgr) => match mgr.load(doc_id) {
            Some(s) => s.l0_abstract,
            None => format!("No summary found for doc_id: {}", doc_id),
        },
        Err(e) => format!("SummaryManager init error: {}", e),
    }
}

fn native_read_document_overview(root: &str, doc_id: &str) -> String {
    let project_root = std::path::PathBuf::from(root);
    match crate::core::document::summary::SummaryManager::new(&project_root) {
        Ok(mgr) => match mgr.load(doc_id) {
            Some(s) => s.l1_overview,
            None => format!("No summary found for doc_id: {}", doc_id),
        },
        Err(e) => format!("SummaryManager init error: {}", e),
    }
}

fn native_list_documents(root: &str, doc_type: &str) -> String {
    let project_root = std::path::PathBuf::from(root);
    match crate::core::project::project::Project::open(&project_root) {
        Some(project) => {
            let docs = project.list_documents().to_vec();
            let filtered: Vec<_> = if doc_type.is_empty() {
                docs
            } else {
                docs.into_iter()
                    .filter(|d| d.doc_type == doc_type)
                    .collect()
            };
            let result: Vec<_> = filtered
                .iter()
                .map(|d| {
                    serde_json::json!({
                        "doc_id": d.doc_id,
                        "path": d.path,
                        "doc_type": d.doc_type,
                        "title": d.title,
                        "indexed": d.indexed,
                    })
                })
                .collect();
            serde_json::to_string(&result).unwrap_or_else(|e| format!("Serialize error: {}", e))
        }
        None => "Project not found".to_string(),
    }
}

fn native_get_document_summary(root: &str, doc_id: &str) -> String {
    let project_root = std::path::PathBuf::from(root);
    match crate::core::project::project::Project::open(&project_root) {
        Some(project) => match project.get_document(doc_id) {
            Some(entry) => {
                let hash_prefix = if entry.hash.len() > 16 {
                    &entry.hash[..16]
                } else {
                    &entry.hash
                };
                let filename = entry
                    .path
                    .split('/')
                    .last()
                    .or(entry.path.split('\\').last())
                    .unwrap_or(&entry.path);
                format!(
                    "文件名: {}\n类型: {}\n路径: {}\n已索引: {}\n哈希: {}...",
                    filename,
                    entry.doc_type,
                    entry.path,
                    if entry.indexed { "是" } else { "否" },
                    hash_prefix,
                )
            }
            None => format!("未找到文档: {}", doc_id),
        },
        None => "项目未打开".to_string(),
    }
}

fn native_read_document_detail(root: &str, doc_id: &str, max_chars: usize) -> String {
    let project_root = std::path::PathBuf::from(root);

    // 尝试从 document_tree 读取页面内容
    let tree_index = crate::core::document::document_tree::DocumentTreeIndex::new(&project_root);
    let pages = tree_index.get_pages(doc_id, "1-50");

    if pages.is_empty() {
        // 回退：尝试从 summary 读取 L1 overview
        match crate::core::document::summary::SummaryManager::new(&project_root) {
            Ok(mgr) => match mgr.load(doc_id) {
                Some(s) => {
                    let content = format!("{}\n\n{}", s.l0_abstract, s.l1_overview);
                    if content.len() > max_chars {
                        let cut = crate::core::helpers::safe_truncate(&content, max_chars);
                        format!("[{}] 内容:\n{}...\n[已截断]", doc_id, cut)
                    } else {
                        format!("[{}] 内容:\n{}", doc_id, content)
                    }
                }
                None => format!("文档 {} 暂无索引内容", doc_id),
            },
            Err(e) => format!("读取失败: {}", e),
        }
    } else {
        let full_text: String = pages
            .iter()
            .map(|p| p.content.as_str())
            .collect::<Vec<_>>()
            .join("\n\n");
        if full_text.len() > max_chars {
            let cut = crate::core::helpers::safe_truncate(&full_text, max_chars);
            format!(
                "[{}] 完整内容:\n{}...\n[已截断]",
                doc_id,
                cut
            )
        } else {
            format!("[{}] 完整内容:\n{}", doc_id, full_text)
        }
    }
}

fn native_find_documents(root: &str, keyword: &str, _doc_type: &str, top_k: usize) -> String {
    let project_root = std::path::PathBuf::from(root);

    // 1. 用 KnowledgeBase 语义搜索获取候选文档
    let config = crate::core::config::settings::AppConfig::load();
    let candidates = match crate::core::document::knowledge_base::KnowledgeBase::new(&project_root, Some(&config.embed))
    {
        Ok(kb) => kb.search_sync(keyword, top_k * 3),
        Err(_) => vec![],
    };

    let candidate_ids: std::collections::HashSet<String> = candidates
        .iter()
        .filter_map(|r| {
            r.metadata
                .get("doc_id")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        })
        .collect();

    // 2. 加载候选文档的 L0 摘要，按关键词过滤
    #[derive(Clone)]
    struct MatchedSummary {
        doc_id: String,
        l0_abstract: String,
        entity_tags: Vec<String>,
    }
    let mut matched: Vec<MatchedSummary> = Vec::new();
    if let Ok(mgr) = super::super::document::summary::SummaryManager::new(&project_root) {
        let summaries = mgr.list_all();
        let keyword_lower = keyword.to_lowercase();

        for s in summaries.iter() {
            if !candidate_ids.contains(&s.doc_id) {
                continue;
            }
            if keyword_lower.contains(&s.l0_abstract.to_lowercase())
                || s.l0_abstract.to_lowercase().contains(&keyword_lower)
                || s.keywords
                    .iter()
                    .any(|k| k.to_lowercase().contains(&keyword_lower))
                || s.entity_tags
                    .iter()
                    .any(|t| t.to_lowercase().contains(&keyword_lower))
            {
                matched.push(MatchedSummary {
                    doc_id: s.doc_id.clone(),
                    l0_abstract: s.l0_abstract.clone(),
                    entity_tags: s.entity_tags.clone(),
                });
            }
        }
    }

    if matched.is_empty() {
        // 回退到纯 KB 搜索结果
        if candidates.is_empty() {
            return format!("未找到与 \"{}\" 相关的文档", keyword);
        }
        let mut lines = vec![format!(
            "找到 {} 个相关文档（语义搜索）:",
            candidates.len().min(top_k)
        )];
        for r in candidates.iter().take(top_k) {
            let doc_id = r
                .metadata
                .get("doc_id")
                .and_then(|v| v.as_str())
                .unwrap_or("?");
            let text = if r.text.len() > 120 {
                crate::core::helpers::safe_truncate(&r.text, 120)
            } else {
                &r.text
            };
            lines.push(format!("- {}: {}...", doc_id, text));
        }
        return lines.join("\n");
    }

    let mut lines = vec![format!(
        "找到 {} 个相关文档（按 L0 摘要过滤）:",
        matched.len().min(top_k)
    )];
    for s in matched.iter().take(top_k) {
        let abstract_text = if s.l0_abstract.len() > 120 {
            crate::core::helpers::safe_truncate(&s.l0_abstract, 120)
        } else {
            s.l0_abstract.as_str()
        };
        lines.push(format!("- {}: {}...", s.doc_id, abstract_text));
        if !s.entity_tags.is_empty() {
            lines.push(format!("  实体: {}", s.entity_tags.join(", ")));
        }
    }
    lines.join("\n")
}
