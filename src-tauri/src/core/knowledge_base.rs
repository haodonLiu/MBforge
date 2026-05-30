use std::path::Path;
use std::sync::Mutex;

use super::config::EmbedConfig;
use super::document_tree::DocumentTreeIndex;
use super::embedding::Embedder;
use super::vector_store::{SearchResult, SqliteVectorStore, VectorItem, VectorStore};
use crate::parsers::sections::{SectionChunk, TreeNode};

// Re-export PageContent so it can be imported from knowledge_base module
pub use super::document_tree::PageContent;

/// Count total nodes in a tree recursively
fn count_nodes(nodes: &[TreeNode]) -> usize {
    nodes.iter().map(|n| 1 + count_nodes(&n.nodes)).sum()
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

        let tree = self.tree_index.lock().map_err(|e| format!("Lock error: {}", e))?;
        tree.index_document(doc_id, sections, page_texts)?;
        Ok(sections.len())
    }

    pub async fn search(&self, query: &str, top_k: usize) -> Result<Vec<SearchResult>, String> {
        let query_embedding = self.embedder.embed_single(query)?;
        self.vector_store.search(&query_embedding, top_k, None)
    }

    pub fn get_structure(&self, doc_id: &str) -> Option<Vec<TreeNode>> {
        let tree = self.tree_index.lock().ok()?;
        tree.get_structure(doc_id)
    }

    pub fn get_pages(&self, doc_id: &str, pages: &str) -> Vec<PageContent> {
        self.tree_index
            .lock()
            .ok()
            .map(|tree| tree.get_pages(doc_id, pages))
            .unwrap_or_default()
    }

    pub fn remove_document(&self, doc_id: &str) -> Result<(), String> {
        self.vector_store.delete(doc_id)?;
        let tree = self.tree_index.lock().map_err(|e| format!("Lock error: {}", e))?;
        tree.remove_document(doc_id)
    }

    pub fn stats(&self) -> KbStats {
        let total_vectors = self.vector_store.count().unwrap_or(0);
        let (document_count, section_count) = self
            .tree_index
            .lock()
            .ok()
            .map(|t| {
                let trees = t.load_trees();
                let doc_count = trees.len();
                // Sum up section counts from all documents
                let sec_count: usize = trees.values().map(|nodes| count_nodes(nodes)).sum();
                (doc_count, sec_count)
            })
            .unwrap_or((0, 0));
        KbStats {
            document_count,
            section_count,
            total_vectors,
        }
    }

    pub fn vector_store(&self) -> &dyn VectorStore {
        self.vector_store.as_ref()
    }
}

// ============================================================================
// Tauri 命令层
// ============================================================================

#[tauri::command]
pub async fn kb_search(
    root: String,
    query: String,
    top_k: Option<usize>,
) -> Result<Vec<serde_json::Value>, String> {
    let top_k = top_k.unwrap_or(5);
    let config = super::config::EmbedConfig::default();
    let kb = KnowledgeBase::new(std::path::Path::new(&root), &config)
        .map_err(|e| format!("KB init failed: {}", e))?;
    let results = kb
        .search(&query, top_k)
        .await
        .map_err(|e| format!("Search failed: {}", e))?;
    Ok(results
        .into_iter()
        .map(|r| {
            serde_json::json!({
                "id": r.id,
                "text": r.text,
                "metadata": r.metadata,
                "score": r.score,
            })
        })
        .collect())
}

#[tauri::command]
pub fn kb_get_structure(
    root: String,
    doc_id: String,
) -> Result<Option<Vec<TreeNode>>, String> {
    let config = super::config::EmbedConfig::default();
    let kb = KnowledgeBase::new(std::path::Path::new(&root), &config)
        .map_err(|e| format!("KB init failed: {}", e))?;
    Ok(kb.get_structure(&doc_id))
}

#[tauri::command]
pub fn kb_get_pages(root: String, doc_id: String, pages: String) -> Vec<PageContent> {
    let config = super::config::EmbedConfig::default();
    if let Ok(kb) = KnowledgeBase::new(std::path::Path::new(&root), &config) {
        kb.get_pages(&doc_id, &pages)
    } else {
        Vec::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kb_creation() {
        let dir = std::env::temp_dir().join(format!("kb_test_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        let config = EmbedConfig::default();
        let kb = KnowledgeBase::new(&dir, &config);
        assert!(kb.is_ok());
    }

    #[test]
    fn test_remove_nonexistent() {
        let dir = std::env::temp_dir().join(format!("kb_test_rm_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        let config = EmbedConfig::default();
        let kb = KnowledgeBase::new(&dir, &config).unwrap();
        assert!(kb.remove_document("nonexistent").is_ok());
    }
}
