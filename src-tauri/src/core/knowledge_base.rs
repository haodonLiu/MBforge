use std::path::{Path, PathBuf};
use std::sync::Mutex;

use super::config::EmbedConfig;
use super::document_tree::DocumentTreeIndex;
use super::embedding::Embedder;
use super::vector_store::{SearchResult, SqliteVectorStore, VectorItem, VectorStore};
use crate::parsers::sections::SectionChunk;

// Re-export PageContent so executor can import from knowledge_base
pub use super::document_tree::PageContent;

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
    pub fn new(project_root: &Path, config: &EmbedConfig) -> Result<Self, String> {
        let kb_dir = project_root.join(".mbforge").join("knowledge_base");
        std::fs::create_dir_all(&kb_dir).map_err(|e| format!("Failed to create KB dir: {}", e))?;
        let db_path = kb_dir.join("vectors.db");
        let vector_store = SqliteVectorStore::new(&db_path)?;
        let tree_index = DocumentTreeIndex::new(project_root);
        let embedder = Embedder::new(config);
        Ok(Self {
            vector_store: Box::new(vector_store),
            tree_index: Mutex::new(tree_index),
            embedder,
            project_root: project_root.to_path_buf(),
        })
    }

    pub async fn index_document(
        &self,
        doc_id: &str,
        sections: &[SectionChunk],
        page_texts: &[String],
    ) -> Result<usize, String> {
        let texts: Vec<String> = sections.iter().map(|s| s.text.clone()).collect();
        let embeddings = self.embedder.embed(texts)?;

        let items: Vec<VectorItem> = sections
            .iter()
            .zip(embeddings.into_iter())
            .enumerate()
            .map(|(i, (section, embedding))| {
                VectorItem {
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
                }
            })
            .collect();

        self.vector_store.upsert(items)?;

        let tree = self.tree_index.lock().map_err(|e| format!("Lock error: {}", e))?;
        tree.index_document(doc_id, sections, page_texts)?;
        drop(tree); // Release lock
        Ok(sections.len())
    }

    pub async fn search(&self, query: &str, top_k: usize) -> Result<Vec<SearchResult>, String> {
        let query_embedding = self.embedder.embed_single(query)?;
        self.vector_store.search(&query_embedding, top_k, None)
    }

    pub fn get_pages(&self, doc_id: &str, pages: &str) -> Vec<PageContent> {
        let tree = match self.tree_index.lock() {
            Ok(t) => t,
            Err(_) => return Vec::new(),
        };
        tree.get_pages(doc_id, pages)
    }

    pub fn get_structure(&self, doc_id: &str) -> Option<Vec<crate::parsers::sections::TreeNode>> {
        let tree = match self.tree_index.lock() {
            Ok(t) => t,
            Err(_) => return None,
        };
        tree.get_structure(doc_id)
    }

    pub fn remove_document(&self, doc_id: &str) -> Result<(), String> {
        self.vector_store.delete(doc_id)?;
        let tree = self.tree_index.lock().map_err(|e| format!("Lock error: {}", e))?;
        tree.remove_document(doc_id)
    }

    pub fn stats(&self) -> KbStats {
        let total_vectors = self.vector_store.count().unwrap_or(0);
        let tree = self.tree_index.lock().ok();
        // Count documents from the trees map
        let document_count = tree.as_ref().and_then(|t| {
            let trees = t.load_trees();
            if trees.is_empty() { None } else { Some(trees.len()) }
        }).unwrap_or(0);
        KbStats {
            document_count,
            section_count: total_vectors,
            total_vectors,
        }
    }

    pub fn vector_store(&self) -> &dyn VectorStore {
        self.vector_store.as_ref()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::constants::DEFAULT_EMBED_BASE_URL;

    fn test_config() -> EmbedConfig {
        EmbedConfig {
            provider: "qwen3".into(),
            model_name: "test".into(),
            base_url: DEFAULT_EMBED_BASE_URL.into(),
            api_key: String::new(),
            device: "cpu".into(),
        }
    }

    #[test]
    fn test_kb_creation() {
        let dir = std::env::temp_dir().join(format!("kb_test_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        let kb = KnowledgeBase::new(&dir, &test_config());
        assert!(kb.is_ok());
        let kb = kb.unwrap();
        let stats = kb.stats();
        assert_eq!(stats.total_vectors, 0);
    }

    #[test]
    fn test_remove_nonexistent() {
        let dir = std::env::temp_dir().join(format!("kb_test_rm_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        let kb = KnowledgeBase::new(&dir, &test_config()).unwrap();
        assert!(kb.remove_document("nonexistent").is_ok());
    }
}
