//! Literature review for document reports — decouples parsers/ from agent/.
//!
//! Issue #3 fix: parsers/pipeline.rs should not directly instantiate MbforgeAgent.
//! All agent-dependent literature review logic lives here in core/.

use std::time::Duration;
use tokio::time::timeout;

use crate::core::agent::rig_adapter::{MbforgeAgent, MbforgeAgentSpec, MbforgeProviderConfig};
use crate::parsers::doc_types::DocumentReport;

/// Run a lightweight literature review over a parsed document report.
///
/// - Failure is silent: timeout / LLM unavailable / any error → returns without mutating.
/// - Success: sets `report.lit_reviewed = true` and `lit_decision_summary = Some(...)`.
/// - 30s timeout so it never blocks Stage 4.5 persistence.
pub async fn review_document_report(report: &mut DocumentReport, _project_root: Option<&std::path::Path>) {
    let agent = match MbforgeProviderConfig::from_app_config() {
        Ok(cfg) => {
            use rig_core::memory::InMemoryConversationMemory;
            let memory = std::sync::Arc::new(
                crate::core::agent::managed_memory::MbforgeManagedMemory::new(
                    std::sync::Arc::new(InMemoryConversationMemory::new()),
                ),
            );
            match MbforgeAgent::from_config(
                &cfg,
                &MbforgeAgentSpec::literature(),
                Vec::new(),
                memory,
            ) {
                Ok(a) => a,
                Err(e) => {
                    log::warn!("[LitAgent] Failed to build MbforgeAgent: {}", e);
                    return;
                }
            }
        }
        Err(e) => {
            log::warn!("[LitAgent] Failed to load provider config: {}", e);
            return;
        }
    };

    let extraction_json = match serde_json::to_value(&*report) {
        Ok(v) => v,
        Err(e) => {
            log::warn!("[LitAgent] Failed to serialize report: {}", e);
            return;
        }
    };
    let prompt_text = match serde_json::to_string(&extraction_json) {
        Ok(s) => s,
        Err(e) => {
            log::warn!("[LitAgent] Failed to stringify report: {}", e);
            return;
        }
    };

    let outcome = timeout(
        Duration::from_secs(30),
        agent.prompt(
            &crate::core::agent::session_id::SessionId::from("lit-review-oneshot"),
            &prompt_text,
        ),
    )
    .await;

    match outcome {
        Ok(Ok(text)) => {
            report.lit_reviewed = true;
            report.lit_decision_summary = Some(text);
            log::info!("[LitAgent] Review complete (MbforgeAgent single-shot)");
        }
        Ok(Err(e)) => {
            log::warn!("[LitAgent] prompt failed: {}", e);
        }
        Err(_elapsed) => {
            log::warn!("[LitAgent] review timed out after 30s, skipping");
        }
    }
}
