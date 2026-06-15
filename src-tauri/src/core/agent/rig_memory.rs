#![allow(dead_code)]
//! `MbforgeConversationMemory` trait and three impls that bridge MBForge's
//! existing long-term memory + procedural-skills stores into a shape that
//! rig's agent loop can call after every turn.
//!
//! rig-core 0.38 ships no `ConversationMemory` trait of its own, so we
//! define the minimum surface area we need here:
//!
//! * `inject_into_system_prompt` — long-form text to prepend to the
//!   system prompt before the model is called.
//! * `observe_turn` — background hook fired after a turn completes;
//!   implementations may do LLM-driven extraction and persistence.
//! * `memory_summary` — short diagnostic string for tests and logging.

use std::future::Future;
use std::path::Path;
use std::pin::Pin;
use std::sync::Arc;
use tokio::sync::Mutex;

use crate::core::agent::context::Message;
use crate::core::agent::memory::MemoryManager;
use crate::core::agent::skills::SkillsManager;
use crate::core::constants::sidecar_url;

/// Async trait surface for conversation-scoped memory used by the rig-based
/// agent loop. Implemented for `MemoryManagerMemory`, `SkillsManagerMemory`,
/// and `CompositeMemory` (which holds both).
pub trait MbforgeConversationMemory: Send + Sync {
    /// Long-term memory text to prepend to the system prompt. May be empty
    /// if no memory has been recorded yet.
    fn inject_into_system_prompt<'a>(&'a self)
        -> Pin<Box<dyn Future<Output = String> + Send + 'a>>;

    /// Observe a completed turn for background extraction. The
    /// implementation decides what (if anything) to persist; the rig loop
    /// calls this fire-and-forget after each assistant response.
    fn observe_turn<'a>(
        &'a self,
        user_input: &'a str,
        assistant_output: &'a str,
    ) -> Pin<Box<dyn Future<Output = ()> + Send + 'a>>;

    /// Optional count / debug string. Default implementation returns empty.
    fn memory_summary(&self) -> String {
        String::new()
    }
}

// ---------------------------------------------------------------------------
// MemoryManagerMemory
// ---------------------------------------------------------------------------

/// Wraps `MemoryManager` (the structured long-term store in `memory.rs`).
///
/// `MemoryManager::extract_from_conversation` takes `&mut self`, but the
/// trait gives us only `&self`, so the manager lives behind a `Mutex`.
/// Cloning the wrapper shares the same `Arc` — both clones observe and
/// mutate the same underlying store.
pub struct MemoryManagerMemory {
    pub manager: Arc<Mutex<MemoryManager>>,
}

impl MemoryManagerMemory {
    /// Convenience constructor mirroring `MemoryManager::new`.
    pub fn new(project_root: &Path) -> Self {
        Self {
            manager: Arc::new(Mutex::new(MemoryManager::new(project_root))),
        }
    }
}

impl Clone for MemoryManagerMemory {
    fn clone(&self) -> Self {
        Self {
            manager: Arc::clone(&self.manager),
        }
    }
}

impl MbforgeConversationMemory for MemoryManagerMemory {
    fn inject_into_system_prompt<'a>(
        &'a self,
    ) -> Pin<Box<dyn Future<Output = String> + Send + 'a>> {
        Box::pin(async move {
            // `tokio::sync::Mutex::lock` is async and returns the guard
            // directly (no `Result` — tokio's mutex has no poison state).
            // The underlying `MemoryManager` accessors are sync.
            let guard = self.manager.lock().await;
            let user_profile = guard.get_user_profile_text();
            let agent_memory = guard.get_agent_memory_text();
            format!(
                "# Long-term Memory\n## User Profile\n{}\n## Agent Memory\n{}",
                user_profile, agent_memory
            )
        })
    }

    fn observe_turn<'a>(
        &'a self,
        _user_input: &'a str,
        assistant_output: &'a str,
    ) -> Pin<Box<dyn Future<Output = ()> + Send + 'a>> {
        Box::pin(async move {
            // The real `MemoryManager` API is `extract_from_conversation`,
            // which takes a `&[Message]` slice and a sidecar URL. The trait
            // hands us just the assistant text, so synthesize a minimal
            // 2-turn conversation: [user "", assistant <output>]. If the
            // assistant output is empty there is nothing to extract and
            // the call short-circuits inside `extract_from_conversation`.
            let messages = vec![Message::user(""), Message::assistant(assistant_output)];
            let url = sidecar_url();
            // Hold the lock across the await — the underlying
            // `extract_from_conversation` mutates the cache.
            let mut guard = self.manager.lock().await;
            guard.extract_from_conversation(&messages, &url).await;
        })
    }

    fn memory_summary(&self) -> String {
        // `memory_summary` is a sync trait method, so we cannot `.await`
        // the async `lock()`. `try_lock` returns immediately: if the
        // async extraction is mid-flight we just report 0 for this call.
        // `tokio::sync::TryLockError` has no `into_inner` (no poison), so
        // we map both busy and poisoned cases to 0.
        let count = self.manager.try_lock().map(|g| g.count()).unwrap_or(0);
        format!("memory items: {}", count)
    }
}

// ---------------------------------------------------------------------------
// SkillsManagerMemory
// ---------------------------------------------------------------------------

/// Wraps `SkillsManager` (the procedural-skills store in `skills.rs`).
///
/// `SkillsManager::auto_create_from_conversation` is `&self` and spawns
/// its own tokio task internally, so no `Mutex` is needed — plain `Arc`
/// is enough for shared ownership.
pub struct SkillsManagerMemory {
    pub manager: Arc<SkillsManager>,
}

impl SkillsManagerMemory {
    /// Convenience constructor mirroring `SkillsManager::new`.
    pub fn new(project_root: &Path) -> Self {
        Self {
            manager: Arc::new(SkillsManager::new(project_root)),
        }
    }
}

impl Clone for SkillsManagerMemory {
    fn clone(&self) -> Self {
        Self {
            manager: Arc::clone(&self.manager),
        }
    }
}

impl MbforgeConversationMemory for SkillsManagerMemory {
    fn inject_into_system_prompt<'a>(
        &'a self,
    ) -> Pin<Box<dyn Future<Output = String> + Send + 'a>> {
        Box::pin(async move {
            // Sync accessor; the future is essentially a no-op.
            let summary = self.manager.get_all_summary();
            format!("# Procedural Skills\n{}", summary)
        })
    }

    fn observe_turn<'a>(
        &'a self,
        user_input: &'a str,
        assistant_output: &'a str,
    ) -> Pin<Box<dyn Future<Output = ()> + Send + 'a>> {
        Box::pin(async move {
            // The real API is `auto_create_from_conversation(user, asst, url)`.
            // It is sync and self-spawns; if the heuristic doesn't see
            // procedural keywords in the conversation it returns
            // immediately without contacting the sidecar. Errors are
            // swallowed inside the spawned task, so this is fire-and-forget.
            let url = sidecar_url();
            self.manager
                .auto_create_from_conversation(user_input, assistant_output, &url);
        })
    }

    fn memory_summary(&self) -> String {
        let count = self.manager.list().len();
        format!("skills items: {}", count)
    }
}

// ---------------------------------------------------------------------------
// CompositeMemory
// ---------------------------------------------------------------------------

/// Holds both halves of the memory stack and delegates to whichever is
/// present. `memory` and `skills` are both optional so callers can build
/// a `CompositeMemory` with just one side wired up.
pub struct CompositeMemory {
    pub memory: Option<MemoryManagerMemory>,
    pub skills: Option<SkillsManagerMemory>,
}

impl Clone for CompositeMemory {
    fn clone(&self) -> Self {
        Self {
            memory: self.memory.clone(),
            skills: self.skills.clone(),
        }
    }
}

impl MbforgeConversationMemory for CompositeMemory {
    fn inject_into_system_prompt<'a>(
        &'a self,
    ) -> Pin<Box<dyn Future<Output = String> + Send + 'a>> {
        Box::pin(async move {
            // Await both halves sequentially. An `Option` short-circuits
            // when the corresponding field is `None`.
            let mut parts: Vec<String> = Vec::new();
            if let Some(mem) = &self.memory {
                parts.push(mem.inject_into_system_prompt().await);
            }
            if let Some(skl) = &self.skills {
                parts.push(skl.inject_into_system_prompt().await);
            }
            // `Vec::join` adds the separator only between elements, so
            // we don't get trailing whitespace when exactly one half is
            // present.
            parts.join("\n")
        })
    }

    fn observe_turn<'a>(
        &'a self,
        user_input: &'a str,
        assistant_output: &'a str,
    ) -> Pin<Box<dyn Future<Output = ()> + Send + 'a>> {
        Box::pin(async move {
            if let Some(mem) = &self.memory {
                mem.observe_turn(user_input, assistant_output).await;
            }
            if let Some(skl) = &self.skills {
                skl.observe_turn(user_input, assistant_output).await;
            }
        })
    }

    fn memory_summary(&self) -> String {
        let mut parts: Vec<String> = Vec::new();
        if let Some(mem) = &self.memory {
            parts.push(mem.memory_summary());
        }
        if let Some(skl) = &self.skills {
            parts.push(skl.memory_summary());
        }
        parts.join(" | ")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_memory_manager_memory_inject() {
        let dir = tempfile::tempdir().unwrap();
        let m = MemoryManagerMemory::new(dir.path());
        let text = futures::executor::block_on(m.inject_into_system_prompt());
        // Fresh store: both halves are empty strings but the section
        // headers are still present, so the result is non-empty.
        assert!(
            !text.is_empty(),
            "inject_into_system_prompt should return non-empty scaffold"
        );
        assert!(text.contains("# Long-term Memory"));
        assert!(text.contains("## User Profile"));
        assert!(text.contains("## Agent Memory"));
    }

    #[test]
    fn test_skills_manager_memory_inject() {
        let dir = tempfile::tempdir().unwrap();
        let s = SkillsManagerMemory::new(dir.path());
        let text = futures::executor::block_on(s.inject_into_system_prompt());
        assert!(
            !text.is_empty(),
            "inject_into_system_prompt should return non-empty scaffold"
        );
        assert!(text.contains("# Procedural Skills"));
    }

    #[test]
    fn test_composite_memory_concat() {
        let dir = tempfile::tempdir().unwrap();
        let composite = CompositeMemory {
            memory: Some(MemoryManagerMemory::new(dir.path())),
            skills: Some(SkillsManagerMemory::new(dir.path())),
        };
        let text = futures::executor::block_on(composite.inject_into_system_prompt());
        // Both halves present: the result must contain both scaffolds.
        assert!(text.contains("# Long-term Memory"));
        assert!(text.contains("# Procedural Skills"));
    }
}
