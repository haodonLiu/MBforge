/// Shared pipeline execution context and event reporting.
pub mod context;
/// Pipeline error types and stage-specific sub-errors.
pub mod error;
/// Pipeline data models (source, extracted, segmented, enriched, persisted, indexed).
pub mod models;
/// Pipeline runner, stage trait, and the top-level `run_pipeline` entry point.
pub mod runner;
/// Shared services used by pipeline stages.
pub mod services;
/// Pipeline stage implementations.
pub mod stages;
/// Output writers for text, report, and molecule store artifacts.
pub mod writer;

pub use runner::run_pipeline;
