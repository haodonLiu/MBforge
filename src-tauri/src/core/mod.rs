// Subdirectory modules
pub mod chem;
pub mod config;
pub mod document;
pub mod models;
pub mod molecule;
pub mod project;
pub mod vector;

// Top-level modules
pub mod db;
pub mod error;
pub mod helpers;
pub mod http;
pub mod sidecar_client;
pub mod trace;
pub mod types;

// Note: prior to refactoring, this file held ~65 lines of `pub use` re-exports
// creating dual import paths (e.g. `core::molecule_store` and
// `core::molecule::molecule_store`). All canonical callers have been migrated
// to the subdirectory paths; the only remaining external users (if any) should
// be addressed by adding an explicit `pub use` for the specific symbol they
// need rather than blanket re-exports.

pub use config::constants;
