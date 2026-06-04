pub mod agent;
pub mod arxiv;
pub mod chem;
pub mod config;
pub mod constants;
pub mod context;
pub mod db;
pub mod document;
pub mod embedding;
pub mod executor;
pub mod error;
pub mod helpers;
pub mod http;
pub mod llm;
pub mod markush;
pub mod memory;
pub mod molecule;
pub mod notes;
pub mod observability;
pub mod project;
pub mod project_migrator;
pub mod resource_manager;
pub mod sar_query;
pub mod tools;
pub mod types;
pub mod sqlite_vector_store;
pub mod vector_store;

// Backward-compat re-exports — allow existing `crate::core::xxx` paths
// used by commands/ and parsers/ to continue working after the
// `core/memory/`, `core/document/`, `core/molecule/` refactor.
pub use document::document_tree;
pub use document::document_tree::{DocumentTreeIndex, PageContent};
pub use document::knowledge_base;
pub use document::file_cache;
pub use document::file_cache::{CacheStats, FileCache};
pub use document::knowledge_base::{
    get_or_init_kb, kb_get_pages, kb_get_structure, kb_search, kb_search_stream,
    search_with_cache, KnowledgeBase,
};
pub use sqlite_vector_store::{SqliteVectorStore, reciprocal_rank_fusion};
pub use document::semantic_cache;
pub use document::semantic_cache::{SemanticCache, SemanticCacheConfig};
pub use document::stream_search;
pub use document::stream_search::{StreamingResult, StreamingSearch, StreamingSearchConfig};
pub use document::summary;
pub use document::summary::SummaryManager;
pub use memory::memory::MemoryManager;
pub use memory::skills::SkillsManager;
pub use memory::trajectory::TrajectoryTracker;
pub use molecule::molecule_cluster;
pub use molecule::molecule_cluster::ClusterInfo;
pub use molecule::molecule_db;
pub use molecule::molecule_db::{
    MoleculeRelation, MoleculeRelationDb, RelationStats, RelationType, MOL_DB_FILENAME,
};
pub use molecule::molecule_dedup;
pub use molecule::molecule_dedup::{
    add_similarity_relation, run_dedup_batch, DedupPair, DedupResult,
};
pub use molecule::molecule_engine;
pub use molecule::molecule_engine::{
    ActivityCliff, ActivitySummary, AnalogWithActivity, MarkushOverlap, MarkushPattern,
    MoleculeEngine, ScaffoldActivityRecord, ScaffoldProfile,
};
pub use molecule::molecule_store;
pub use molecule::molecule_store::{MoleculeDatabase, MoleculeRecord};
