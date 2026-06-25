pub mod constants;
pub mod generated;
pub mod llm_config;
pub mod settings;

// Re-export YAML-derived constants so call sites can write
// `use crate::config::DEFAULT_SIDECAR_PORT;` unchanged.
#[allow(unused_imports)]
pub use generated::*;

#[allow(unused_imports)]
pub use settings::{AppConfig, EmbedConfig, ModelConfig};
