//! Document subsystem — tree index, summaries, KB, semantic cache, streaming search.
//!
//! Re-exports the public API at the `document` namespace so callers can
//! write `use crate::core::document::KnowledgeBase` instead of the longer
//! `crate::core::document::knowledge_base::KnowledgeBase`.

pub mod document_tree;
pub mod knowledge_base;
pub mod semantic_cache;
pub mod stream_search;
pub mod summary;

pub use document_tree::{DocumentTreeIndex, PageContent};
pub use knowledge_base::{get_or_init_kb, search_with_cache, KnowledgeBase};
pub use semantic_cache::{SemanticCache, SemanticCacheConfig};
pub use stream_search::{StreamingResult, StreamingSearch, StreamingSearchConfig};
pub use summary::SummaryManager;
