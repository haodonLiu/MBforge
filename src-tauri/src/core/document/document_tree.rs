//! DocumentTreeIndex — 文档结构树 + 页码原文持久化
//!
//! 提供文档导航（结构树）和按页读取原文的能力，供 Agent B/C 调用。
//!
//! 存储格式：
//!   - 结构树：`.mbforge/doc_trees.json`  — `{doc_id: TreeNode[]}` 的 JSON
//!   - 页缓存：`.mbforge/pages/{doc_id}/page_{i}.txt` — 每页一个文件

use std::fs;
use std::path::{Path, PathBuf};

use crate::core::types::{SectionChunk, TreeNode};

const DOC_TREES_FILE: &str = "doc_trees.json";
const PAGES_DIR: &str = "pages";

#[derive(Debug, Clone)]
pub struct DocumentTreeIndex {
    project_root: PathBuf,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PageContent {
    pub page: usize,
    pub content: String,
}

impl DocumentTreeIndex {
    pub fn new(project_root: &Path) -> Self {
        Self {
            project_root: project_root.to_path_buf(),
        }
    }

    fn meta_dir(&self) -> PathBuf {
        self.project_root.join(".mbforge")
    }

    fn trees_path(&self) -> PathBuf {
        self.meta_dir().join(DOC_TREES_FILE)
    }

    fn pages_dir(&self) -> PathBuf {
        self.meta_dir().join(PAGES_DIR)
    }

    fn doc_pages_dir(&self, doc_id: &str) -> PathBuf {
        self.pages_dir().join(doc_id)
    }

    pub fn load_trees(&self) -> std::collections::HashMap<String, Vec<TreeNode>> {
        let path = self.trees_path();
        if !path.exists() {
            return std::collections::HashMap::new();
        }
        match fs::read_to_string(&path) {
            Ok(content) => serde_json::from_str(&content).unwrap_or_default(),
            Err(_) => std::collections::HashMap::new(),
        }
    }

    fn save_trees(
        &self,
        trees: &std::collections::HashMap<String, Vec<TreeNode>>,
    ) -> Result<(), String> {
        let dir = self.meta_dir();
        fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let content = serde_json::to_string_pretty(trees).map_err(|e| e.to_string())?;
        fs::write(self.trees_path(), content).map_err(|e| e.to_string())
    }

    /// 索引文档：保存结构树 + 页缓存
    pub fn index_document(
        &self,
        doc_id: &str,
        sections: &[SectionChunk],
        page_texts: &[String],
    ) -> Result<(), String> {
        let meta_dir = self.meta_dir();
        fs::create_dir_all(&meta_dir).map_err(|e| e.to_string())?;

        // 构建 TreeNode 树
        let nodes = build_tree_nodes(sections);
        let mut trees = self.load_trees();
        trees.insert(doc_id.to_string(), nodes);
        self.save_trees(&trees)?;

        // 保存页缓存
        if !page_texts.is_empty() {
            let doc_pages = self.doc_pages_dir(doc_id);
            fs::create_dir_all(&doc_pages).map_err(|e| e.to_string())?;
            for (i, text) in page_texts.iter().enumerate() {
                let page_path = doc_pages.join(format!("page_{}.txt", i + 1));
                fs::write(&page_path, text).map_err(|e| e.to_string())?;
            }
        }

        Ok(())
    }

    /// 获取文档结构树（不含正文，用于 Agent 导航）
    pub fn get_structure(&self, doc_id: &str) -> Option<Vec<TreeNode>> {
        let trees = self.load_trees();
        trees.get(doc_id).cloned()
    }

    /// 获取指定页码的原文
    ///
    /// `pages` 格式：`"1"` 或 `"1-3"` 或 `"1,3,5"`
    pub fn get_pages(&self, doc_id: &str, pages: &str) -> Vec<PageContent> {
        let doc_pages = self.doc_pages_dir(doc_id);
        if !doc_pages.exists() {
            return Vec::new();
        }

        let page_indices: Vec<usize> = parse_page_range(pages);
        let mut result = Vec::new();

        for idx in page_indices {
            let page_path = doc_pages.join(format!("page_{}.txt", idx));
            if let Ok(content) = fs::read_to_string(&page_path) {
                result.push(PageContent { page: idx, content });
            }
        }

        result
    }

    /// 删除文档索引
    pub fn remove_document(&self, doc_id: &str) -> Result<(), String> {
        // 从 trees.json 移除
        let mut trees = self.load_trees();
        trees.remove(doc_id);
        self.save_trees(&trees)?;

        // 删除页缓存目录
        let doc_pages = self.doc_pages_dir(doc_id);
        if doc_pages.exists() {
            fs::remove_dir_all(&doc_pages).map_err(|e| e.to_string())?;
        }

        Ok(())
    }
}

/// 将 SectionChunk 列表转换为 TreeNode 树
fn build_tree_nodes(sections: &[SectionChunk]) -> Vec<TreeNode> {
    if sections.is_empty() {
        return Vec::new();
    }

    #[derive(Debug)]
    struct StackEntry {
        depth: usize,
        node: TreeNode,
    }

    let mut stack: Vec<StackEntry> = Vec::new();
    let mut roots: Vec<TreeNode> = Vec::new();

    for section in sections {
        let depth = section.path.matches(" > ").count();
        let node = TreeNode {
            title: section.title.clone(),
            node_id: section.path.clone(),
            line_num: section.line_start,
            nodes: Vec::new(),
        };

        // Pop stack frames that are at same or deeper depth
        while stack.len() > 1 && stack[stack.len() - 1].depth >= depth {
            if let Some(entry) = stack.pop() {
                if let Some(parent) = stack.last_mut() {
                    parent.node.nodes.push(entry.node);
                } else {
                    roots.push(entry.node);
                }
            }
        }

        // Push new node onto stack
        stack.push(StackEntry { depth, node });
    }

    // Flush remaining stack to roots
    while stack.len() > 1 {
        if let Some(entry) = stack.pop() {
            if let Some(parent) = stack.last_mut() {
                parent.node.nodes.push(entry.node);
            } else {
                roots.push(entry.node);
            }
        }
    }
    if let Some(entry) = stack.pop() {
        roots.push(entry.node);
    }

    roots
}

/// 解析页码字符串为页码索引列表
/// `"1"` → [1]
/// `"1-3"` → [1, 2, 3]
/// `"1,3,5"` → [1, 3, 5]
fn parse_page_range(pages: &str) -> Vec<usize> {
    let mut result = Vec::new();
    for part in pages.split(',') {
        let part = part.trim();
        if part.contains('-') {
            let range: Vec<&str> = part.split('-').collect();
            if range.len() == 2 {
                if let (Ok(start), Ok(end)) = (
                    range[0].trim().parse::<usize>(),
                    range[1].trim().parse::<usize>(),
                ) {
                    for i in start..=end {
                        result.push(i);
                    }
                }
            }
        } else if let Ok(idx) = part.parse::<usize>() {
            result.push(idx);
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_build_tree_nodes() {
        let sections = vec![
            SectionChunk {
                title: "Introduction".to_string(),
                path: "Introduction".to_string(),
                text: "intro text".to_string(),
                page_start: Some(1),
                page_end: Some(3),
                line_start: 0,
                line_end: 10,
            },
            SectionChunk {
                title: "Background".to_string(),
                path: "Introduction/Background".to_string(),
                text: "bg text".to_string(),
                page_start: Some(1),
                page_end: Some(2),
                line_start: 5,
                line_end: 8,
            },
        ];
        let nodes = build_tree_nodes(&sections);
        assert_eq!(nodes.len(), 1);
        assert_eq!(nodes[0].title, "Introduction");
        assert_eq!(nodes[0].nodes.len(), 1);
        assert_eq!(nodes[0].nodes[0].title, "Background");
    }

    #[test]
    fn test_parse_page_range() {
        assert_eq!(parse_page_range("1"), vec![1]);
        assert_eq!(parse_page_range("1-3"), vec![1, 2, 3]);
        assert_eq!(parse_page_range("1,3,5"), vec![1, 3, 5]);
        assert_eq!(parse_page_range("1-2,5"), vec![1, 2, 5]);
    }

    #[test]
    fn test_index_and_retrieve() {
        let tmp = tempfile::tempdir().unwrap();
        let idx = DocumentTreeIndex::new(tmp.path());
        let sections = vec![SectionChunk {
            title: "Test".to_string(),
            path: "Test".to_string(),
            text: "test content".to_string(),
            page_start: Some(1),
            page_end: Some(1),
            line_start: 0,
            line_end: 1,
        }];
        let page_texts = vec!["page 1 content".to_string()];
        idx.index_document("doc1", &sections, &page_texts).unwrap();
        let structure = idx.get_structure("doc1");
        assert!(structure.is_some());
        assert_eq!(structure.unwrap().len(), 1);
        let pages = idx.get_pages("doc1", "1");
        assert_eq!(pages.len(), 1);
        assert_eq!(pages[0].content, "page 1 content");
        idx.remove_document("doc1").unwrap();
        assert!(idx.get_structure("doc1").is_none());
    }
}
