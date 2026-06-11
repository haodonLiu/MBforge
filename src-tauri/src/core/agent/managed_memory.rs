#![allow(dead_code)]
//! `MbforgeManagedMemory` — a `rig_core::memory::ConversationMemory`
//! wrapper that orchestrates the compactor + demotion hook on every
//! `load(cid)` call.
//!
//! # Why this exists
//!
//! Rig 0.38's `AgentBuilder` exposes only `.memory(...)` and
//! `.conversation_id(...)` — there is no `.compactor(...)` or
//! `.demotion_hook(...)` builder method. The `Compactor` and
//! `DemotionHook` traits therefore must be wired into a
//! `ConversationMemory` impl somewhere; this file is that wiring.
//! It is the in-tree equivalent of the `rig-memory` companion crate's
//! `DemotingPolicyMemory` adapter, written in ~150 LOC and with no
//! new crate dependency.
//!
//! # How it works
//!
//! On every `load(cid)`:
//! 1. Delegate to the inner backend (`SqliteConversationMemory` in
//!    production) to get the raw message list.
//! 2. If the list is over the configured `window_size`, partition
//!    the oldest N as `evicted` and the rest as `recent`.
//! 3. If a `DemotionHook` is configured, hand the evicted slice to
//!    `on_demote(cid, evicted)` (fire-and-forget: we still return
//!    `recent` even if the hook errors).
//! 4. If a `Compactor` is configured, call `compact(cid, evicted,
//!    carry_over)` to get a `SummaryArtifact`, convert it to a
//!    `Message`, and return `[summary, ...recent]`. Without a
//!    compactor, we return just `recent` (eviction becomes a hard
//!    truncate).
//!
//! `append` and `clear` are passthroughs to the inner backend.
//!
//! # Carry-over
//!
//! The rig compactor trait hands us a `carry_over: Option<&Artifact>` —
//! the previous summary, if any. For v1 we ignore it and produce a
//! fresh summary from the evicted slice alone. A recursive compactor
//! that folds carry-over in is a v2 follow-up (see the v2 list in the
//! plan).

use std::sync::Arc;

use rig_core::memory::{Compactor, ConversationMemory, DemotionHook, MemoryError};
use rig_core::message::Message;
use rig_core::wasm_compat::WasmBoxedFuture;

use crate::core::agent::compactor::SummaryArtifact;
use crate::core::agent::conversation_store::HistoryItem;

/// Wraps an inner `ConversationMemory` and orchestrates a compactor +
/// demotion hook on every `load(cid)`.
pub struct MbforgeManagedMemory {
    inner: Arc<dyn ConversationMemory>,
    /// Concrete handle to the `SqliteConversationMemory` inner, if
    /// the production path is in use. Lets `list_for_session` and
    /// other SQLite-specific methods (e.g. raw_count for tests) be
    /// called without an `Any` downcast on the trait object.
    sqlite: Option<Arc<crate::core::agent::conversation_store::SqliteConversationMemory>>,
    compactor: Option<Arc<dyn Compactor<Artifact = SummaryArtifact>>>,
    demotion: Option<Arc<dyn DemotionHook>>,
    window_size: usize,
}

impl MbforgeManagedMemory {
    /// Wrap an inner backend. Use the `with_*` builders to add the
    /// compactor and demotion hook. The `sqlite` field is `None`;
    /// use `new_with_sqlite` for the production path that needs
    /// `list_for_session` access.
    pub fn new(inner: Arc<dyn ConversationMemory>) -> Self {
        Self {
            inner,
            sqlite: None,
            compactor: None,
            demotion: None,
            window_size: 40,
        }
    }

    /// Production constructor: also remember the concrete SQLite
    /// handle so `list_for_session` can be served.
    pub fn new_with_sqlite(
        inner: Arc<dyn ConversationMemory>,
        sqlite: Arc<crate::core::agent::conversation_store::SqliteConversationMemory>,
    ) -> Self {
        Self {
            inner,
            sqlite: Some(sqlite),
            compactor: None,
            demotion: None,
            window_size: 40,
        }
    }

    pub fn with_compactor(
        mut self,
        c: Arc<dyn Compactor<Artifact = SummaryArtifact>>,
    ) -> Self {
        self.compactor = Some(c);
        self
    }

    pub fn with_demotion(mut self, d: Arc<dyn DemotionHook>) -> Self {
        self.demotion = Some(d);
        self
    }

    pub fn with_window_size(mut self, n: usize) -> Self {
        self.window_size = n;
        self
    }

    pub fn inner(&self) -> Arc<dyn ConversationMemory> {
        Arc::clone(&self.inner)
    }

    pub fn window_size(&self) -> usize {
        self.window_size
    }

    pub fn compactor_kind(&self) -> Option<&'static str> {
        if self.compactor.is_some() {
            Some("sidecar")
        } else {
            None
        }
    }

    pub fn has_demotion(&self) -> bool {
        self.demotion.is_some()
    }

    /// Frontend-facing history endpoint (replaces the dead
    /// `LayeredContext::get_history_messages`). Delegates to the
    /// concrete SQLite backend if one was wired at construction;
    /// returns an empty list otherwise (the InMemoryConversationMemory
    /// fallback path used by the one-shot literature review in
    /// `pipeline.rs` / `lit_review.rs` doesn't persist history).
    pub fn list_for_session(&self, cid: &str) -> Result<Vec<HistoryItem>, String> {
        if let Some(sqlite) = &self.sqlite {
            sqlite.list_for_session(cid)
        } else {
            Ok(Vec::new())
        }
    }

    /// Downcast + delegate to `SqliteConversationMemory::mark_evicted`.
    /// No-op (returns Ok) if the inner backend is not SQLite
    /// (e.g. `InMemoryConversationMemory` in the one-shot fallback).
    /// The `count` argument is the number of oldest non-evicted
    /// messages to mark evicted (not a seq threshold — see
    /// `SqliteConversationMemory::mark_evicted`).
    async fn mark_evicted_inner(
        &self,
        cid: &str,
        count: i64,
    ) -> Result<(), String> {
        if let Some(sqlite) = &self.sqlite {
            let _ = sqlite
                .mark_evicted(cid, count)
                .map_err(|e| format!("mark_evicted: {e}"))?;
        }
        Ok(())
    }

    /// Downcast + delegate to `SqliteConversationMemory::replace_with_compaction`.
    async fn replace_with_compaction_inner(
        &self,
        cid: &str,
        summary_text: &str,
        evict_before: i64,
    ) -> Result<(), String> {
        if let Some(sqlite) = &self.sqlite {
            sqlite
                .replace_with_compaction(cid, summary_text, evict_before)
                .map_err(|e| format!("replace_with_compaction: {e}"))?;
        }
        Ok(())
    }
}

impl ConversationMemory for MbforgeManagedMemory {
    fn load<'a>(
        &'a self,
        conversation_id: &'a str,
    ) -> WasmBoxedFuture<'a, Result<Vec<Message>, MemoryError>> {
        Box::pin(async move {
            let mut msgs = self.inner.load(conversation_id).await?;
            if msgs.len() <= self.window_size || self.compactor.is_none() && self.demotion.is_none() {
                return Ok(msgs);
            }
            // Over the window. Split: oldest N are evicted, the rest
            // are recent. Compactor and DemotionHook each get the
            // full evicted slice; we return `recent` (or
            // `[summary, ...recent]` if a compactor is wired).
            //
            // IMPORTANT: the eviction is persisted to the inner SQLite
            // backend via `mark_evicted` + `replace_with_compaction`,
            // NOT just held in the in-memory `Vec<Message>`. Without
            // this, every `load` would re-evict the same N messages and
            // the compactor would re-summarise them, growing the
            // prompt unboundedly. With it, the next `load` filters by
            // `evicted = 0` and sees the post-compaction state.
            let split = msgs.len().saturating_sub(self.window_size);
            let evicted = msgs.drain(..split).collect::<Vec<_>>();
            let recent = msgs;
            // `mark_evicted` takes a count, not a seq threshold. We
            // pass `split` — the N oldest non-evicted messages will be
            // marked evicted. On the next load, those rows are filtered
            // out by `load_active` and the compactor is asked to
            // summarise only the NEW split.
            let evict_count = split as i64;

            if let Some(d) = &self.demotion {
                // Fire-and-forget per rig's contract: a slow hook
                // delays the load, so we propagate errors but a
                // production caller may choose to swallow them.
                if let Err(e) = d.on_demote(conversation_id, evicted.clone()).await {
                    log::warn!(
                        "DemotionHook on_demote failed for cid={}: {e}",
                        conversation_id
                    );
                }
            }

            if let Some(c) = &self.compactor {
                // Try to compact. On failure, fall back to hard
                // truncate (`recent`) — same demotion best-effort
                // policy, no user-visible abort on compactor errors.
                let summary_result = c.compact(conversation_id, &evicted, None).await;
                match summary_result {
                    Ok(summary) => {
                        // Persist the eviction + splice the summary.
                        if let Err(e) = self.mark_evicted_inner(conversation_id, evict_count).await
                        {
                            log::warn!(
                                "managed_memory: mark_evicted failed for cid={}: {e}",
                                conversation_id
                            );
                        }
                        if let Err(e) = self
                            .replace_with_compaction_inner(
                                conversation_id,
                                &summary.text,
                                evict_count,
                            )
                            .await
                        {
                            log::warn!(
                                "managed_memory: replace_with_compaction failed for cid={}: {e}",
                                conversation_id
                            );
                        }
                        let mut out: Vec<Message> = vec![summary.into()];
                        out.extend(recent);
                        Ok(out)
                    }
                    Err(e) => {
                        log::warn!(
                            "Compactor failed for cid={}: {e}; falling back to hard truncate",
                            conversation_id
                        );
                        // Still mark evicted so the next load is
                        // stable (no re-summarisation of the same
                        // rows).
                        if let Err(e) = self.mark_evicted_inner(conversation_id, evict_count).await
                        {
                            log::warn!(
                                "managed_memory: mark_evicted failed for cid={}: {e}",
                                conversation_id
                            );
                        }
                        Ok(recent)
                    }
                }
            } else {
                // No compactor: just persist the eviction, hard truncate.
                if let Err(e) = self.mark_evicted_inner(conversation_id, evict_count).await {
                    log::warn!(
                        "managed_memory: mark_evicted failed for cid={}: {e}",
                        conversation_id
                    );
                }
                Ok(recent)
            }
        })
    }

    fn append<'a>(
        &'a self,
        conversation_id: &'a str,
        messages: Vec<Message>,
    ) -> WasmBoxedFuture<'a, Result<(), MemoryError>> {
        self.inner.append(conversation_id, messages)
    }

    fn clear<'a>(
        &'a self,
        conversation_id: &'a str,
    ) -> WasmBoxedFuture<'a, Result<(), MemoryError>> {
        self.inner.clear(conversation_id)
    }
}

// ============================================================================
// Mocks for unit tests — these satisfy the rig traits without standing up
// SQLite or a real LLM. They live here (not in a separate test-support
// crate) because they are only used by `managed_memory`'s own tests.
// ============================================================================

#[cfg(test)]
pub(crate) mod test_support {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    /// A `ConversationMemory` that returns a fixed Vec<Message> from
    /// `load(cid)` and records every `append` / `clear`. Used to
    /// drive the wrapper's partitioning + demote+compact logic
    /// without SQLite.
    pub struct MockMemory {
        pub messages: std::sync::Mutex<Vec<Message>>,
        pub append_count: AtomicUsize,
        pub clear_count: AtomicUsize,
    }

    impl MockMemory {
        pub fn new(messages: Vec<Message>) -> Self {
            Self {
                messages: std::sync::Mutex::new(messages),
                append_count: AtomicUsize::new(0),
                clear_count: AtomicUsize::new(0),
            }
        }
    }

    impl ConversationMemory for MockMemory {
        fn load<'a>(
            &'a self,
            _cid: &'a str,
        ) -> WasmBoxedFuture<'a, Result<Vec<Message>, MemoryError>> {
            Box::pin(async move {
                Ok(self.messages.lock().unwrap().clone())
            })
        }
        fn append<'a>(
            &'a self,
            _cid: &'a str,
            _msgs: Vec<Message>,
        ) -> WasmBoxedFuture<'a, Result<(), MemoryError>> {
            self.append_count.fetch_add(1, Ordering::SeqCst);
            Box::pin(async move { Ok(()) })
        }
        fn clear<'a>(
            &'a self,
            _cid: &'a str,
        ) -> WasmBoxedFuture<'a, Result<(), MemoryError>> {
            self.clear_count.fetch_add(1, Ordering::SeqCst);
            Box::pin(async move { Ok(()) })
        }
    }

    /// A `Compactor` that returns a fixed summary regardless of input.
    pub struct MockCompactor {
        pub summary_text: String,
    }

    impl Compactor for MockCompactor {
        type Artifact = SummaryArtifact;
        fn compact<'a>(
            &'a self,
            _cid: &'a str,
            _evicted: &'a [Message],
            _carry: Option<&'a SummaryArtifact>,
        ) -> WasmBoxedFuture<'a, Result<SummaryArtifact, MemoryError>> {
            Box::pin(async move {
                Ok(SummaryArtifact {
                    text: self.summary_text.clone(),
                })
            })
        }
    }

    /// A `DemotionHook` that records the count of evicted messages.
    pub struct MockDemotion {
        pub evicted_count: AtomicUsize,
        pub last_session: std::sync::Mutex<Option<String>>,
    }

    impl MockDemotion {
        pub fn new() -> Self {
            Self {
                evicted_count: AtomicUsize::new(0),
                last_session: std::sync::Mutex::new(None),
            }
        }
    }

    impl DemotionHook for MockDemotion {
        fn on_demote<'a>(
            &'a self,
            cid: &'a str,
            evicted: Vec<Message>,
        ) -> WasmBoxedFuture<'a, Result<(), MemoryError>> {
            self.evicted_count
                .fetch_add(evicted.len(), Ordering::SeqCst);
            *self.last_session.lock().unwrap() = Some(cid.to_string());
            Box::pin(async move { Ok(()) })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::test_support::{MockCompactor, MockDemotion, MockMemory};
    use super::*;
    use std::sync::atomic::Ordering;

    fn user(s: &str) -> Message {
        Message::user(s)
    }
    fn asst(s: &str) -> Message {
        Message::assistant(s)
    }

    #[test]
    fn test_load_under_window_returns_unchanged() {
        let inner = Arc::new(MockMemory::new(vec![user("a"), asst("b"), user("c")]));
        let mgr = MbforgeManagedMemory::new(inner).with_window_size(10);
        let out = futures::executor::block_on(mgr.load("cid-1")).unwrap();
        assert_eq!(out.len(), 3);
    }

    #[test]
    fn test_load_over_window_with_compactor_splices_summary() {
        // 6 messages, window 4 → 2 evicted, 4 recent + 1 summary.
        let msgs: Vec<Message> = (0..6)
            .map(|i| if i % 2 == 0 { user(&format!("u{i}")) } else { asst(&format!("a{i}")) })
            .collect();
        let inner = Arc::new(MockMemory::new(msgs));
        let compactor = Arc::new(MockCompactor {
            summary_text: "earlier: u0 -> a5".into(),
        });
        let demotion = Arc::new(MockDemotion::new());
        let mgr = MbforgeManagedMemory::new(inner.clone())
            .with_window_size(4)
            .with_compactor(compactor)
            .with_demotion(demotion.clone());

        let out = futures::executor::block_on(mgr.load("cid-1")).unwrap();
        // 1 summary + 4 recent = 5
        assert_eq!(out.len(), 5);
        // Demotion got the 2 evicted.
        assert_eq!(demotion.evicted_count.load(Ordering::SeqCst), 2);
        assert_eq!(
            demotion.last_session.lock().unwrap().as_deref(),
            Some("cid-1")
        );
    }

    #[test]
    fn test_load_over_window_without_compactor_hard_truncates() {
        let msgs: Vec<Message> = (0..6).map(|i| user(&format!("u{i}"))).collect();
        let inner = Arc::new(MockMemory::new(msgs));
        let demotion = Arc::new(MockDemotion::new());
        let mgr = MbforgeManagedMemory::new(inner)
            .with_window_size(4)
            .with_demotion(demotion.clone());

        let out = futures::executor::block_on(mgr.load("cid-1")).unwrap();
        assert_eq!(out.len(), 4, "no compactor → hard truncate to window");
        assert_eq!(demotion.evicted_count.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn test_load_exact_window_no_eviction() {
        let msgs: Vec<Message> = (0..4).map(|i| user(&format!("u{i}"))).collect();
        let inner = Arc::new(MockMemory::new(msgs));
        let mgr = MbforgeManagedMemory::new(inner).with_window_size(4);
        let out = futures::executor::block_on(mgr.load("cid-1")).unwrap();
        assert_eq!(out.len(), 4);
    }

    #[test]
    fn test_append_and_clear_passthrough() {
        let inner = Arc::new(MockMemory::new(vec![]));
        let mgr = MbforgeManagedMemory::new(inner.clone());
        futures::executor::block_on(mgr.append("cid-1", vec![user("hi")])).unwrap();
        futures::executor::block_on(mgr.append("cid-1", vec![asst("hello")])).unwrap();
        futures::executor::block_on(mgr.clear("cid-1")).unwrap();
        assert_eq!(inner.append_count.load(Ordering::SeqCst), 2);
        assert_eq!(inner.clear_count.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn test_with_compactor_kind() {
        let inner = Arc::new(MockMemory::new(vec![]));
        let mgr = MbforgeManagedMemory::new(inner)
            .with_compactor(Arc::new(MockCompactor { summary_text: "s".into() }));
        assert_eq!(mgr.compactor_kind(), Some("sidecar"));
    }
}
