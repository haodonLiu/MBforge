//! Document subsystem — tree index, summaries, KB, semantic cache, streaming search.
//!
//! Re-exports the public API at the `document` namespace so callers can
//! write `use crate::document::KnowledgeBase` instead of the longer
//! `crate::document::knowledge_base::KnowledgeBase`.
//!
//! `pub use` items below are part of the public API surface (also reachable
//! via the inner module path); the unused-import warning is rustc not seeing
//! downstream consumers within this crate. Suppress per-line.

pub mod content_cache;
pub mod detection_cache;
pub mod document_tree;
pub mod file_cache;
pub mod knowledge_base;
pub mod search_engine;
pub mod semantic_cache;
pub mod stream_search;
pub mod summary;

#[allow(unused_imports)]
pub use content_cache::{ContentCache, ContentCacheStats};
#[allow(unused_imports)]
pub use document_tree::{DocumentTreeIndex, PageContent};
#[allow(unused_imports)]
pub use file_cache::{CacheStats, FileCache};
#[allow(unused_imports)]
pub use knowledge_base::{get_or_init_kb, search_with_cache, KnowledgeBase};
#[allow(unused_imports)]
pub use search_engine::{SearchEngine, SearchResult};
#[allow(unused_imports)]
pub use semantic_cache::{SemanticCache, SemanticCacheConfig};
#[allow(unused_imports)]
pub use stream_search::{StreamingResult, StreamingSearch, StreamingSearchConfig};
#[allow(unused_imports)]
pub use summary::SummaryManager;
