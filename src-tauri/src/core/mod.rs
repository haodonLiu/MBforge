// Subdirectory modules
pub mod agent;
pub mod chem;
pub mod config;
pub mod document;
pub mod models;
pub mod molecule;
pub mod project;
pub mod vector;

// Top-level modules
pub mod error;
pub mod helpers;
pub mod http;
pub mod types;

// Backward-compat re-exports for chem modules
pub use chem::abbreviation_map;
pub use chem::chem as chem_functions;
pub use chem::esmiles;
pub use chem::gesim;
pub use chem::markush;
pub use chem::molecode;
pub use chem::sar_query;

// Backward-compat re-exports for agent modules
pub use agent::context;
pub use agent::llm;
pub use agent::observability;
pub use agent::specialist_agent;
pub use agent::tools;

// Backward-compat re-exports for document modules
pub use document::document_tree;
pub use document::document_tree::{DocumentTreeIndex, PageContent};
pub use document::knowledge_base;
pub use document::file_cache;
pub use document::file_cache::{CacheStats, FileCache};
pub use document::knowledge_base::{
    get_or_init_kb, kb_get_pages, kb_get_structure, kb_search, kb_search_stream,
    search_with_cache, KnowledgeBase,
};
pub use vector::sqlite_vector_store::{SqliteVectorStore, reciprocal_rank_fusion};
pub use document::semantic_cache;
pub use document::semantic_cache::{SemanticCache, SemanticCacheConfig};
pub use document::stream_search;
pub use document::stream_search::{StreamingResult, StreamingSearch, StreamingSearchConfig};
pub use document::summary;
pub use document::summary::SummaryManager;

// Backward-compat re-exports for config modules
pub use config::constants;
pub use config::settings;

// Backward-compat re-exports for memory modules
pub use agent::memory::MemoryManager;
pub use agent::skills::SkillsManager;
pub use agent::trajectory::TrajectoryTracker;

// Backward-compat re-exports for molecule modules
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

// Backward-compat re-exports for project modules
pub use project::notes;
pub use project::resource_manager;
pub use project::project as project_ops;
pub use project::project::Project;

// Backward-compat re-exports for vector modules
pub use vector::embedding;
pub use vector::vector_store;
