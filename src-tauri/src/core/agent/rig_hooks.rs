#![allow(dead_code)]
//! Rig PromptHook adapters for the existing MBForge observability layer.
//!
//! Two newtypes wrap the (non-`Clone`) `AuditLog` and `TrajectoryTracker`
//! so they can be plugged into rig's `PromptHook<M>` trait, which requires
//! `Clone + WasmCompatSend + WasmCompatSync`. Both newtypes manually impl
//! `Clone` (clones the inner smart pointer).
//!
//! The `on_completion_response` and `on_tool_result` overrides forward the
//! rig event into the corresponding audit / trajectory sink; everything
//! else falls through to the default `HookAction::cont()`.
//!
//! NOTE: The assignment spec described an earlier rig 0.38 trait shape that
//! carried `serde_json::Value` arguments and a `&[Message]` history on
//! `on_completion_response`. Rig 0.38.1 changed that — hook methods now
//! take `&str` arguments (and `on_completion_response` no longer receives
//! the full history). This file follows the actual 0.38.1 surface, which is
//! the only one that can compile against the locked dep version.

use rig_core::agent::{
    HookAction, InvalidToolCallContext, InvalidToolCallHookAction, PromptHook, ToolCallHookAction,
};
use rig_core::completion::{CompletionModel, CompletionResponse};
use rig_core::message::Message;
use rig_core::wasm_compat::WasmCompatSend;
use serde_json::Value;
use std::future::Future;
use std::sync::{Arc, Mutex};
use uuid::Uuid;

// ---------------------------------------------------------------------------
// AuditLogHook
// ---------------------------------------------------------------------------

/// `PromptHook` adapter that writes a single `llm_call` audit entry per
/// completion response and a `tool_call` entry per tool result.
///
/// `AuditLog` is intentionally not `Clone` (it holds a `Mutex<File>`), so
/// we share it through an `Arc`. The hook is `Clone` because the trait
/// requires it — cloning just clones the `Arc`.
pub struct AuditLogHook {
    /// Shared audit log (file + mutex live inside `Arc<AuditLog>`).
    pub audit: Arc<crate::core::agent::observability::AuditLog>,
    /// Stable trace id stamped on every audit entry this hook emits. The
    /// rig 0.38.1 hook trait does not surface a trace id per call, so the
    /// hook falls back to the value captured at construction.
    pub trace_id: String,
}

impl Clone for AuditLogHook {
    fn clone(&self) -> Self {
        Self {
            audit: Arc::clone(&self.audit),
            trace_id: self.trace_id.clone(),
        }
    }
}

impl AuditLogHook {
    /// Wrap an `AuditLog` in a fresh hook with a generated trace id.
    pub fn new(audit: Arc<crate::core::agent::observability::AuditLog>) -> Self {
        Self {
            audit,
            trace_id: Uuid::new_v4().to_string(),
        }
    }

    /// Wrap an `AuditLog` and pin the trace id to a caller-supplied value
    /// (useful for correlating the hook with an outer `TraceContext`).
    pub fn with_trace_id(
        audit: Arc<crate::core::agent::observability::AuditLog>,
        trace_id: impl Into<String>,
    ) -> Self {
        Self {
            audit,
            trace_id: trace_id.into(),
        }
    }

    fn record_llm_call(&self, usage: &rig_core::completion::Usage) {
        let _ = self.audit.append_llm_call(
            &self.trace_id,
            None,
            "rig-agent",
            usage.input_tokens,
            usage.output_tokens,
            0,
        );
    }

    fn record_tool_call(&self, tool_name: &str, args: &str, result: &str) {
        // `AuditLog::append_tool_call` takes `args: &Value`; the rig 0.38.1
        // trait hands us a JSON `&str`. Parse best-effort, fall back to a
        // raw `Value::String` so a malformed payload is still captured.
        let args_value: Value =
            serde_json::from_str(args).unwrap_or(Value::String(args.to_string()));
        let _ = self
            .audit
            .append_tool_call(&self.trace_id, None, tool_name, &args_value, 0);
        // Stash the tool result string on a sibling entry so an offline
        // auditor can see the body without re-running the tool. Kept as a
        // second append rather than threading the result through
        // `append_tool_call` to avoid changing that signature.
        let _ = self
            .audit
            .append(&crate::core::agent::observability::AuditEntry {
                trace_id: self.trace_id.clone(),
                span_id: None,
                timestamp: 0.0,
                action: "tool_result".to_string(),
                details: serde_json::json!({
                    "tool": tool_name,
                    "result": result,
                }),
                tokens_used: 0,
                duration_ms: 0,
            });
    }
}

impl<M> PromptHook<M> for AuditLogHook
where
    M: CompletionModel + 'static,
{
    fn on_completion_call(
        &self,
        _prompt: &Message,
        _history: &[Message],
    ) -> impl Future<Output = HookAction> + WasmCompatSend {
        async { HookAction::cont() }
    }

    fn on_completion_response(
        &self,
        _prompt: &Message,
        response: &CompletionResponse<M::Response>,
    ) -> impl Future<Output = HookAction> + WasmCompatSend {
        self.record_llm_call(&response.usage);
        async { HookAction::cont() }
    }

    fn on_invalid_tool_call(
        &self,
        _ctx: &InvalidToolCallContext,
    ) -> impl Future<Output = InvalidToolCallHookAction> + WasmCompatSend {
        async { InvalidToolCallHookAction::fail() }
    }

    fn on_tool_call(
        &self,
        _tool_name: &str,
        _tool_call_id: Option<String>,
        _internal_call_id: &str,
        _args: &str,
    ) -> impl Future<Output = ToolCallHookAction> + WasmCompatSend {
        async { ToolCallHookAction::cont() }
    }

    fn on_tool_result(
        &self,
        tool_name: &str,
        _tool_call_id: Option<String>,
        _internal_call_id: &str,
        args: &str,
        result: &str,
    ) -> impl Future<Output = HookAction> + WasmCompatSend {
        self.record_tool_call(tool_name, args, result);
        async { HookAction::cont() }
    }

    fn on_text_delta(
        &self,
        _text_delta: &str,
        _aggregated_text: &str,
    ) -> impl Future<Output = HookAction> + Send {
        async { HookAction::cont() }
    }

    fn on_tool_call_delta(
        &self,
        _tool_call_id: &str,
        _internal_call_id: &str,
        _tool_name: Option<&str>,
        _tool_call_delta: &str,
    ) -> impl Future<Output = HookAction> + Send {
        async { HookAction::cont() }
    }
    fn on_stream_completion_response_finish(
        &self,
        _prompt: &Message,
        _response: &M::StreamingResponse,
    ) -> impl Future<Output = HookAction> + Send {
        // The streaming response type is provider-defined; we don't have
        // a uniform `Usage` accessor on it, so just continue without
        // recording an `llm_call` here. (The non-streaming
        // `on_completion_response` already captures the same logical
        // event when it fires.)
        async { HookAction::cont() }
    }
}

// ---------------------------------------------------------------------------
// TrajectoryHook
// ---------------------------------------------------------------------------

/// `PromptHook` adapter that records every tool call into a shared
/// `TrajectoryTracker`.
///
/// The 0.38.1 trait methods all take `&self`, but `TrajectoryTracker::record_tool`
/// takes `&mut self` (it appends to an internal `Vec`). The only way to
/// bridge those is interior mutability on the hook side, so we wrap the
/// tracker in `Arc<Mutex<…>>`. This is the standard "shared mutable
/// singleton" shape and matches what the rest of mbforge already does for
/// similar patterns.
pub struct TrajectoryHook {
    /// Shared trajectory tracker behind a mutex (record_tool needs &mut).
    pub tracker: Arc<Mutex<crate::core::agent::trajectory::TrajectoryTracker>>,
    /// Stable trace id stamped on every recorded step.
    pub trace_id: String,
}

impl Clone for TrajectoryHook {
    fn clone(&self) -> Self {
        Self {
            tracker: Arc::clone(&self.tracker),
            trace_id: self.trace_id.clone(),
        }
    }
}

impl TrajectoryHook {
    /// Wrap a `TrajectoryTracker` in a fresh hook with a generated trace id.
    pub fn new(tracker: crate::core::agent::trajectory::TrajectoryTracker) -> Self {
        Self {
            tracker: Arc::new(Mutex::new(tracker)),
            trace_id: Uuid::new_v4().to_string(),
        }
    }

    /// Wrap a `TrajectoryTracker` and pin the trace id.
    pub fn with_trace_id(
        tracker: crate::core::agent::trajectory::TrajectoryTracker,
        trace_id: impl Into<String>,
    ) -> Self {
        Self {
            tracker: Arc::new(Mutex::new(tracker)),
            trace_id: trace_id.into(),
        }
    }

    /// Build a hook that shares an existing `Arc<Mutex<…>>` (e.g. one
    /// handed to us by the M2 layer where the trajectory was already
    /// wrapped to satisfy a `Clone` bound upstream).
    pub fn from_arc(
        tracker: Arc<Mutex<crate::core::agent::trajectory::TrajectoryTracker>>,
    ) -> Self {
        Self {
            tracker,
            trace_id: Uuid::new_v4().to_string(),
        }
    }

    fn record(&self, tool_name: &str, args: &str, result: &str) {
        let args_value: Value =
            serde_json::from_str(args).unwrap_or(Value::String(args.to_string()));
        if let Ok(mut guard) = self.tracker.lock() {
            // `record_tool` is `&mut self`; the MutexGuard is `DerefMut`.
            guard.record_tool(tool_name, &args_value, result);
        }
    }
}

impl<M> PromptHook<M> for TrajectoryHook
where
    M: CompletionModel + 'static,
{
    fn on_tool_result(
        &self,
        tool_name: &str,
        _tool_call_id: Option<String>,
        _internal_call_id: &str,
        args: &str,
        result: &str,
    ) -> impl Future<Output = HookAction> + WasmCompatSend {
        self.record(tool_name, args, result);
        async { HookAction::cont() }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::agent::observability::AuditLog;
    use crate::core::agent::trajectory::TrajectoryTracker;

    /// Cloning the hook must yield a second handle over the same `Arc`,
    /// not duplicate the underlying log.
    #[test]
    fn test_audit_log_hook_clone() {
        let dir = tempfile::tempdir().unwrap();
        let audit = AuditLog::new(dir.path()).unwrap();
        let h1 = AuditLogHook::new(Arc::new(audit));
        let h2 = h1.clone();
        assert!(Arc::ptr_eq(&h1.audit, &h2.audit));
        assert_eq!(h1.trace_id, h2.trace_id);
    }

    /// Cloning the trajectory hook yields a second handle over the same
    /// `Arc<Mutex<TrajectoryTracker>>`.
    #[test]
    fn test_trajectory_hook_clone() {
        let dir = tempfile::tempdir().unwrap();
        let tracker = TrajectoryTracker::new(dir.path());
        let h1 = TrajectoryHook::new(tracker);
        let h2 = h1.clone();
        assert!(Arc::ptr_eq(&h1.tracker, &h2.tracker));
        assert_eq!(h1.trace_id, h2.trace_id);
    }

    /// Compile-time proof that the hook satisfies the rig `PromptHook`
    /// trait. We can't easily reach `rig_core::test_utils::MockCompletionModel`
    /// without flipping the `test-utils` feature on rig (forbidden by
    /// the "no new deps" constraint). Instead we assert the trait via
    /// a generic function: if `AuditLogHook` didn't implement
    /// `PromptHook<M>` for some `M: CompletionModel`, the call would
    /// not type-check.
    #[test]
    fn test_audit_log_hook_is_prompt_hook() {
        fn assert_is_prompt_hook<M: CompletionModel, H: PromptHook<M>>(_: &H) {}
        let dir = tempfile::tempdir().unwrap();
        let audit = AuditLog::new(dir.path()).unwrap();
        let hook = AuditLogHook::new(Arc::new(audit));
        // Use a concrete `M` from a provider that compiles in by
        // default with the `reqwest` feature the crate already enables.
        // No API call is made — `M` is purely a type witness.
        assert_is_prompt_hook::<rig_core::providers::openai::CompletionModel, _>(&hook);
    }
}
