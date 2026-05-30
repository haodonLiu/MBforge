use std::path::Path;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};

use super::config::EmbedConfig;
use super::document_tree::DocumentTreeIndex;
use super::embedding::Embedder;
use super::vector_store::{SearchResult, SqliteVectorStore, VectorItem, VectorStore};
use crate::parsers::sections::{SectionChunk, TreeNode};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PageContent {
    pub page: usize,
    pub text: String,
}

pub struct KbStats {
    pub document_count: usize,
    pub section_count: usize,
    pub total_vectors: usize,
}

pub struct KnowledgeBase {
    vector_store: Box<dyn VectorStore>,
    tree_index: Mutex<DocumentTreeIndex>,
    embedder: Embedder,
    project_root: PathBuf,
}

impl KnowledgeBase {
    pub fn new(project_root: &Path) -> Result<Self, String> {
        let kb_dir = project_root.join(".mbforge").join("knowledge_base");
        std::fs::create_dir_all(&kb_dir).map_err(|e| format!("Failed to create KB dir: {}", e))?;
        let db_path = kb_dir.join("vectors.db");
        let vector_store = SqliteVectorStore::new(&db_path)?;
        let tree_index = DocumentTreeIndex::new(project_root);
        let embedder = Embedder::new(&EmbedConfig::default());
        Ok(Self {
            vector_store: Box::new(vector_store),
            tree_index: Mutex::new(tree_index),
            embedder,
            project_root: project_root.to_path_buf(),
        })
    }

    pub fn index_document(
        &self,
        doc_id: &str,
        sections: &[SectionChunk],
        page_texts: &[String],
    ) -> Result<usize, String> {
        let texts: Vec<String> = sections.iter().map(|s| s.text.clone()).collect();
        let embeddings = self.embedder.embed(texts)?;

        let items: Vec<VectorItem> = sections
            .iter()
            .enumerate()
            .filter_map(|(i, section)| {
                let embedding = embeddings.get(i)?.clone();
                Some(VectorItem {
                    id: format!("{}:sec{}", doc_id, i),
                    doc_id: doc_id.to_string(),
                    text: section.text.clone(),
                    embedding,
                    metadata: serde_json::json!({
                        "title": section.title,
                        "path": section.path,
                        "page_start": section.page_start,
                        "page_end": section.page_end,
                    }),
                })
            })
            .collect();

        self.vector_store.upsert(items)?;

        let mut tree = self.tree_index.lock().map_err(|e| format!("Lock error: {}", e))?;
        tree.index_document(doc_id, sections, page_texts)?;
        Ok(sections.len())
    }

    pub fn search(&self, query: &str, top_k: usize) -> Result<Vec<SearchResult>, String> {
        let query_embedding = self.embedder.embed_single(query)?;
        self.vector_store.search(&query_embedding, top_k, None)
    }

    pub fn get_structure(&self, doc_id: &str) -> Result<Option<Vec<TreeNode>>, String> {
        let tree = self.tree_index.lock().map_err(|e| format!("Lock error: {}", e))?;
        let doc = tree.get_document(doc_id);
        match doc {
            Some(_) => {
                let nodes: Vec<TreeNode> = tree
                    .list_all()
                    .into_iter()
                    .filter(|d| d == doc_id)
                    .map(|_| TreeNode {
                        title: doc_id.to_string(),
                        node_id: doc_id.to_string(),
                        line_num: 0,
                        nodes: vec![],
                    })
                    .collect();
                Ok(Some(nodes))
            }
            None => Ok(None),
        }
    }

    pub fn get_pages(&self, doc_id: &str, pages: &str) -> Result<Vec<PageContent>, String> {
        let tree = self.tree_index.lock().map_err(|e| format!("Lock error: {}", e))?;
        let doc = tree.get_document(doc_id);
        match doc {
            Some(_) => {
                let mut result = Vec::new();
                if let Ok(parsed) = parse_page_spec(pages) {
                    for page in parsed {
                        result.push(PageContent {
                            page,
                            text: format!("Page {} content (from {})", page, doc_id),
                        });
                    }
                }
                Ok(result)
            }
            None => Ok(Vec::new()),
        }
    }

    pub fn remove_document(&self, doc_id: &str) -> Result<(), String> {
        self.vector_store.delete(doc_id)?;
        let mut tree = self.tree_index.lock().map_err(|e| format!("Lock error: {}", e))?;
        tree.remove_document(doc_id)
    }

    pub fn stats(&self) -> KbStats {
        let total_vectors = self.vector_store.count().unwrap_or(0);
        let tree = self.tree_index.lock().ok();
        let document_count = tree.as_ref().map(|t| t.doc_count()).unwrap_or(0);
        KbStats {
            document_count,
            section_count: 0,
            total_vectors,
        }
    }

    pub fn vector_store(&self) -> &dyn VectorStore {
        self.vector_store.as_ref()
    }
}

fn parse_page_spec(spec: &str) -> Result<Vec<usize>, String> {
    let mut pages = Vec::new();
    for part in spec.split(',') {
        let part = part.trim();
        if part.is_empty() {
            continue;
        }
        if let Some((start, end)) = part.split_once('-') {
            let s: usize = start.trim().parse().map_err(|_| format!("Invalid page range: {}", part))?;
            let e: usize = end.trim().parse().map_err(|_| format!("Invalid page range: {}", part))?;
            for p in s..=e {
                pages.push(p);
            }
        } else {
            let p: usize = part.parse().map_err(|_| format!("Invalid page number: {}", part))?;
            pages.push(p);
        }
    }
    pages.sort();
    pages.dedup();
    Ok(pages)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_page_spec_single() {
        let pages = parse_page_spec("5").unwrap();
        assert_eq!(pages, vec![5]);
    }

    #[test]
    fn test_parse_page_spec_range() {
        let pages = parse_page_spec("3-5").unwrap();
        assert_eq!(pages, vec![3, 4, 5]);
    }

    #[test]
    fn test_parse_page_spec_complex() {
        let pages = parse_page_spec("1,3-5,10").unwrap();
        assert_eq!(pages, vec![1, 3, 4, 5, 10]);
    }

    #[test]
    fn test_kb_creation() {
        let dir = std::env::temp_dir().join(format!("kb_test_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        let kb = KnowledgeBase::new(&dir);
        assert!(kb.is_ok());
        let kb = kb.unwrap();
        let stats = kb.stats();
        assert_eq!(stats.total_vectors, 0);
    }

    #[test]
    fn test_remove_nonexistent() {
        let dir = std::env::temp_dir().join(format!("kb_test_rm_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        let kb = KnowledgeBase::new(&dir).unwrap();
        assert!(kb.remove_document("nonexistent").is_ok());
    }
}
