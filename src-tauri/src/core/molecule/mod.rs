//! Molecule subsystem — SQLite store, relations, clusters, dedup, engine, SAR.
//!
//! Re-exports the public API at the `molecule` namespace so callers can
//! write `use crate::core::molecule::MoleculeEngine` instead of the longer
//! `crate::core::molecule::molecule_engine::MoleculeEngine`.

pub mod molecule_cluster;
pub mod molecule_db;
pub mod molecule_dedup;
pub mod molecule_engine;
pub mod molecule_store;

pub use molecule_cluster::{
    assign_to_cluster, get_cluster_members, get_molecule_clusters, list_clusters,
    remove_from_cluster, ClusterInfo,
};
pub use molecule_db::{
    MoleculeRelation, MoleculeRelationDb, RelationStats, RelationType, MOL_DB_FILENAME,
};
pub use molecule_dedup::{add_similarity_relation, run_dedup_batch, DedupPair, DedupResult};
pub use molecule_engine::{
    ActivityCliff, ActivitySummary, AnalogWithActivity, MarkushOverlap, MarkushPattern,
    MoleculeEngine, ScaffoldActivityRecord, ScaffoldProfile,
};
pub use molecule_store::{MoleculeDatabase, MoleculeRecord};
