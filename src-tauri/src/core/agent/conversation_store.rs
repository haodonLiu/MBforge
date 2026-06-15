#![allow(dead_code)]
//! `SqliteConversationMemory` — a `rig_core::memory::ConversationMemory`
//! implementation that persists the active conversation window to a
//! project-local SQLite file.
//!
//! # File layout
//!
//! One file per project: `<project_root>/.mbforge/conversations.db`.
//! Two tables live inside it:
//!
//! * `conversation_messages` — the verbatim message log keyed by
//!   `(cid, seq)`. `evicted=1` rows are tombstoned by the demotion
//!   hook; `is_summary=1` rows are spliced at the front of `load(cid)`
//!   by the compactor.
//! * `episodes` — written by `EpisodicDemotionHook` (see
//!   `core::agent::demotion`). Not queried by this file but lives
//!   in the same DB to keep the file count down.
//!
//! # Threading
//!
//! The connection is held behind a `std::sync::Mutex`. SQLite operations
//! are quick and we are not on the hot path of an LLM call; running
//! them inline avoids the round-trip cost of `tokio::sync::Mutex`.
//! The rig `ConversationMemory` trait still returns boxed futures, so
//! we wrap the sync body in `Box::pin(async move { ... })`.
//!
//! # What we store
//!
//! We currently store text-only messages. Rig's `Message` enum allows
//! tool calls, images, audio, etc. on user/assistant turns; we extract
//! the first text block via `text_of(&m)` and re-construct text-only
//! messages on load. This is sufficient for the v1 Chat UI (which
//! only ever calls `agent.prompt(text).await`) and for the
//! `SidecarCompactor` (which summarizes text). Tool-call messages
//! would need a richer schema (separate `tool_calls`/`tool_results`
//! columns) — flagged as a v2 follow-up.

use std::path::{Path, PathBuf};
use std::sync::Arc;

use rusqlite::{params, Connection};
use tokio::sync::Mutex;

use rig_core::memory::{ConversationMemory, MemoryError};
use rig_core::message::{AssistantContent, Message, UserContent};
use rig_core::wasm_compat::WasmBoxedFuture;

/// A row in `conversation_messages` returned to the frontend by
/// `agent_get_history` (replaces the dead `LayeredContext::get_history_messages`).
#[derive(Debug, Clone)]
pub struct HistoryItem {
    pub seq: i64,
    pub role: String,
    pub content: String,
    pub is_summary: bool,
    pub created_at: String,
}

/// A SQLite-backed `ConversationMemory`. Cheap to clone (Arc + Mutex).
#[derive(Clone)]
pub struct SqliteConversationMemory {
    conn: Arc<Mutex<Connection>>,
    #[allow(dead_code)] // for future per-project quota / cleanup
    project_root: PathBuf,
    #[allow(dead_code)]
    window_size: usize,
}

impl SqliteConversationMemory {
    /// Open (or create) `<project_root>/.mbforge/conversations.db` and
    /// run schema bootstrap. Idempotent.
    pub fn open(project_root: &Path) -> Result<Self, String> {
        let mbforge_dir = project_root.join(".mbforge");
        std::fs::create_dir_all(&mbforge_dir).map_err(|e| format!("create .mbforge dir: {e}"))?;
        let db_path = mbforge_dir.join("conversations.db");
        let conn = Connection::open(&db_path)
            .map_err(|e| format!("open conversations.db at {}: {e}", db_path.display()))?;
        // WAL mode is per-connection; enables concurrent reads while a
        // single writer holds the lock. We don't open multiple writers
        // in MBForge, but the Python sidecar may read this DB later.
        conn.pragma_update(None, "journal_mode", "WAL")
            .map_err(|e| format!("enable WAL: {e}"))?;
        Self::bootstrap_schema(&conn)?;
        Ok(Self {
            conn: Arc::new(Mutex::new(conn)),
            project_root: project_root.to_path_buf(),
            window_size: 40,
        })
    }

    /// Borrow a clone of the connection Arc — used by
    /// `EpisodicDemotionHook` to share the same `.db` file.
    pub fn conn_clone(&self) -> Arc<Mutex<Connection>> {
        Arc::clone(&self.conn)
    }

    fn bootstrap_schema(conn: &Connection) -> Result<(), String> {
        conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS conversation_messages (
                cid        TEXT NOT NULL,
                seq        INTEGER NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                evicted    INTEGER NOT NULL DEFAULT 0,
                is_summary INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY (cid, seq)
            );
            CREATE INDEX IF NOT EXISTS idx_conv_active
                ON conversation_messages(cid, evicted, seq);
            "#,
        )
        .map_err(|e| format!("bootstrap schema: {e}"))
    }

    /// Load all non-evicted messages for `cid` in chronological order.
    /// Summary rows (spliced at the front by compaction) come back
    /// first. We use a sentinel `seq = -1` for summaries (the
    /// `replace_with_compaction` method) so the `ORDER BY seq ASC`
    /// puts them before any real message — no need for a secondary
    /// `is_summary` sort key. Real messages get non-negative seqs
    /// from `COALESCE(MAX(seq), -1) + 1` in `append()`.
    pub async fn load_active(&self, cid: &str) -> Result<Vec<Message>, String> {
        let conn = self.conn.lock().await;
        let mut stmt = conn
            .prepare(
                "SELECT seq, role, content, is_summary FROM conversation_messages \
                 WHERE cid = ?1 AND evicted = 0 \
                 ORDER BY seq ASC",
            )
            .map_err(|e| format!("prepare load_active: {e}"))?;
        let rows = stmt
            .query_map(params![cid], |row| {
                let seq: i64 = row.get(0)?;
                let role: String = row.get(1)?;
                let content: String = row.get(2)?;
                let is_summary: i64 = row.get(3)?;
                Ok((seq, role, content, is_summary))
            })
            .map_err(|e| format!("query load_active: {e}"))?;
        let mut out = Vec::new();
        for row in rows {
            let (_, role, content, is_summary) =
                row.map_err(|e| format!("row load_active: {e}"))?;
            if is_summary == 1 {
                // The compactor writes a single system message at the
                // front of the window. We surface it as a user role for
                // rig's load path — rig's `Message::user` is the
                // simplest variant that doesn't pollute the system
                // channel. The `[Earlier conversation summary]` prefix
                // signals its role to the LLM.
                out.push(Message::user(format!(
                    "[Earlier conversation summary]\n{}",
                    content
                )));
            } else {
                out.push(match role.as_str() {
                    "system" => Message::system(content),
                    "assistant" => Message::assistant(content),
                    _ => Message::user(content),
                });
            }
        }
        Ok(out)
    }

    /// Append `msgs` to the tail of `cid`'s log. Seq is assigned by
    /// `COALESCE((SELECT MAX(seq)+1 FROM ...), 0)`.
    pub async fn append(&self, cid: &str, msgs: &[Message]) -> Result<(), String> {
        if msgs.is_empty() {
            return Ok(());
        }
        let conn = self.conn.lock().await;
        let tx = conn
            .unchecked_transaction()
            .map_err(|e| format!("tx: {e}"))?;
        let now = crate::core::helpers::now_rfc3339();
        for m in msgs {
            let role = match m {
                Message::System { .. } => "system",
                Message::User { .. } => "user",
                Message::Assistant { .. } => "assistant",
            };
            let content = text_of(m);
            tx.execute(
                "INSERT INTO conversation_messages (cid, seq, role, content, evicted, is_summary, created_at) \
                 VALUES (?1, \
                         COALESCE((SELECT MAX(seq) FROM conversation_messages WHERE cid = ?1), -1) + 1, \
                         ?2, ?3, 0, 0, ?4)",
                params![cid, role, content, now],
            )
            .map_err(|e| format!("insert append: {e}"))?;
        }
        tx.commit().map_err(|e| format!("commit append: {e}"))?;
        Ok(())
    }

    /// Wipe all rows for `cid`. Used by `agent_clear`.
    pub async fn clear(&self, cid: &str) -> Result<(), String> {
        let conn = self.conn.lock().await;
        conn.execute(
            "DELETE FROM conversation_messages WHERE cid = ?1",
            params![cid],
        )
        .map_err(|e| format!("clear: {e}"))?;
        Ok(())
    }

    /// Frontend-facing history endpoint (replaces
    /// `LayeredContext::get_history_messages`).
    pub async fn list_for_session(&self, cid: &str) -> Result<Vec<HistoryItem>, String> {
        let conn = self.conn.lock().await;
        let mut stmt = conn
            .prepare(
                "SELECT seq, role, content, is_summary, created_at FROM conversation_messages \
                 WHERE cid = ?1 AND evicted = 0 \
                 ORDER BY is_summary DESC, seq ASC",
            )
            .map_err(|e| format!("prepare list: {e}"))?;
        let rows = stmt
            .query_map(params![cid], |row| {
                Ok(HistoryItem {
                    seq: row.get(0)?,
                    role: row.get(1)?,
                    content: row.get(2)?,
                    is_summary: row.get::<_, i64>(3)? != 0,
                    created_at: row.get(4)?,
                })
            })
            .map_err(|e| format!("query list: {e}"))?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r.map_err(|e| format!("row list: {e}"))?);
        }
        Ok(out)
    }

    /// Mark the `count` oldest non-evicted messages for `cid` as
    /// evicted and return their (role, content) pairs. We use
    /// `LIMIT ?` rather than `seq < threshold` so successive
    /// calls (when `count` is small) actually evict the next
    /// oldest *non-evicted* rows instead of re-evicting rows that
    /// were already evicted by an earlier call.
    pub async fn mark_evicted(&self, cid: &str, count: i64) -> Result<Vec<Message>, String> {
        let conn = self.conn.lock().await;
        // Snapshot before mutating — the demotion hook wants the
        // evicted messages as `Vec<Message>`.
        let mut stmt = conn
            .prepare(
                "SELECT role, content FROM conversation_messages \
                 WHERE cid = ?1 AND evicted = 0 \
                 ORDER BY seq ASC LIMIT ?2",
            )
            .map_err(|e| format!("prepare mark_evicted: {e}"))?;
        let rows: Vec<(String, String)> = stmt
            .query_map(params![cid, count], |row| Ok((row.get(0)?, row.get(1)?)))
            .map_err(|e| format!("query mark_evicted: {e}"))?
            .filter_map(|r| r.ok())
            .collect();
        // Now actually evict the same N rows by seq. We do it in a
        // second statement so the snapshot above is consistent.
        conn.execute(
            "UPDATE conversation_messages SET evicted = 1 \
             WHERE seq IN ( \
                 SELECT seq FROM conversation_messages \
                 WHERE cid = ?1 AND evicted = 0 \
                 ORDER BY seq ASC LIMIT ?2 \
             )",
            params![cid, count],
        )
        .map_err(|e| format!("update mark_evicted: {e}"))?;
        Ok(rows
            .into_iter()
            .map(|(_, content)| Message::user(content))
            .collect())
    }

    /// Insert a summary row and evict everything before
    /// `evict_before`. The summary is stored as a single user-role
    /// row with `is_summary=1` so `load_active` can splice it at the
    /// front of subsequent loads. The summary is stored with
    /// `seq = -1` (a sentinel that always sorts before any real
    /// message) and `is_summary = 1` so `load_active` can splice it
    /// at the front. If a previous summary already exists, it is
    /// deleted first — the active summary is always the most recent
    /// one.
    pub async fn replace_with_compaction(
        &self,
        cid: &str,
        summary: &str,
        evict_before: i64,
    ) -> Result<(), String> {
        let conn = self.conn.lock().await;
        let now = crate::core::helpers::now_rfc3339();
        // Evict old rows first (no-op if the compactor already marked
        // them via mark_evicted).
        conn.execute(
            "UPDATE conversation_messages SET evicted = 1 \
             WHERE cid = ?1 AND seq < ?2",
            params![cid, evict_before],
        )
        .map_err(|e| format!("evict for compaction: {e}"))?;
        // Delete any prior summary row — the new one replaces it.
        conn.execute(
            "DELETE FROM conversation_messages WHERE cid = ?1 AND is_summary = 1",
            params![cid],
        )
        .map_err(|e| format!("delete prior summary: {e}"))?;
        // Insert the new summary with `seq = -1` (sentinel that sorts
        // before any real message) and `is_summary = 1`.
        conn.execute(
            "INSERT INTO conversation_messages (cid, seq, role, content, evicted, is_summary, created_at) \
             VALUES (?1, -1, 'user', ?2, 0, 1, ?3)",
            params![cid, summary, now],
        )
        .map_err(|e| format!("insert summary: {e}"))?;
        Ok(())
    }

    /// Internal: for tests / debug.
    #[allow(dead_code)]
    pub async fn raw_count(&self, cid: &str) -> Result<i64, String> {
        let conn = self.conn.lock().await;
        conn.query_row(
            "SELECT COUNT(*) FROM conversation_messages WHERE cid = ?1",
            params![cid],
            |row| row.get(0),
        )
        .map_err(|e| format!("count: {e}"))
    }

    #[allow(dead_code)]
    pub async fn table_exists(&self) -> Result<bool, String> {
        let conn = self.conn.lock().await;
        conn.query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='conversation_messages'",
            [],
            |row| row.get::<_, i64>(0),
        )
        .map(|n| Ok(n > 0))
        .map_err(|e| format!("table_exists: {e}"))?
    }

    #[allow(dead_code)]
    pub fn db_path(&self) -> PathBuf {
        self.project_root.join(".mbforge").join("conversations.db")
    }
}

/// Extract the first text block from a rig `Message`. Falls back to
/// `"<non-text message>"` for tool calls / images / audio so we don't
/// lose the row.
fn text_of(m: &Message) -> String {
    match m {
        Message::System { content } => content.clone(),
        Message::User { content } => match content.first_ref() {
            UserContent::Text(t) => t.text.clone(),
            UserContent::ToolResult(tr) => {
                let text = match tr.content.first_ref() {
                    rig_core::message::ToolResultContent::Text(t) => t.text.clone(),
                    _ => String::new(),
                };
                format!("[tool_result:{}] {}", tr.id, text)
            }
            _ => "<non-text user content>".into(),
        },
        Message::Assistant { content, .. } => match content.first_ref() {
            AssistantContent::Text(t) => t.text.clone(),
            AssistantContent::ToolCall(tc) => {
                format!("[tool_call:{}] {}", tc.id, tc.function.name)
            }
            _ => "<non-text assistant content>".into(),
        },
    }
}

impl ConversationMemory for SqliteConversationMemory {
    fn load<'a>(
        &'a self,
        conversation_id: &'a str,
    ) -> WasmBoxedFuture<'a, Result<Vec<Message>, MemoryError>> {
        Box::pin(async move {
            self.load_active(conversation_id)
                .await
                .map_err(MemoryError::backend)
        })
    }

    fn append<'a>(
        &'a self,
        conversation_id: &'a str,
        messages: Vec<Message>,
    ) -> WasmBoxedFuture<'a, Result<(), MemoryError>> {
        Box::pin(async move {
            self.append(conversation_id, &messages)
                .await
                .map_err(MemoryError::backend)
        })
    }

    fn clear<'a>(
        &'a self,
        conversation_id: &'a str,
    ) -> WasmBoxedFuture<'a, Result<(), MemoryError>> {
        Box::pin(async move {
            self.clear(conversation_id)
                .await
                .map_err(MemoryError::backend)
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn open_test() -> (tempfile::TempDir, SqliteConversationMemory) {
        let dir = tempdir().unwrap();
        let m = SqliteConversationMemory::open(dir.path()).unwrap();
        (dir, m)
    }

    #[tokio::test]
    async fn test_round_trip() {
        let (_dir, m) = open_test();
        let cid = "thread-1";
        m.append(
            cid,
            &[
                Message::user("hi"),
                Message::assistant("hello"),
                Message::user("how are you?"),
            ],
        )
        .await
        .unwrap();
        let loaded = m.load_active(cid).await.unwrap();
        assert_eq!(loaded.len(), 3);
        // Round-trip loses structural rig types but text is preserved.
        let texts: Vec<String> = loaded.iter().map(text_of).collect();
        assert_eq!(texts, vec!["hi", "hello", "how are you?"]);
    }

    #[tokio::test]
    async fn test_clear() {
        let (_dir, m) = open_test();
        let cid = "thread-1";
        m.append(cid, &[Message::user("x"), Message::assistant("y")])
            .await
            .unwrap();
        assert_eq!(m.raw_count(cid).await.unwrap(), 2);
        m.clear(cid).await.unwrap();
        assert_eq!(m.raw_count(cid).await.unwrap(), 0);
        assert!(m.load_active(cid).await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn test_compaction_replaces_evicted() {
        let (_dir, m) = open_test();
        let cid = "thread-1";
        // Append 6 messages, then mark the first 2 as evicted and
        // splice in a summary.
        let msgs: Vec<Message> = (0..6)
            .map(|i| {
                if i % 2 == 0 {
                    Message::user(format!("u{i}"))
                } else {
                    Message::assistant(format!("a{i}"))
                }
            })
            .collect();
        m.append(cid, &msgs).await.unwrap();
        // Evict everything with seq < 2 (i.e. seq 0, 1).
        let _ = m.mark_evicted(cid, 2).await.unwrap();
        m.replace_with_compaction(cid, "earlier: u0 -> a1", 2)
            .await
            .unwrap();

        let loaded = m.load_active(cid).await.unwrap();
        // First loaded message should be the summary (is_summary=1),
        // then the 4 remaining (seq 2..5).
        assert_eq!(loaded.len(), 5, "summary + 4 active = 5");
        // The summary comes back as a user message; verify the prefix.
        let first_text = text_of(&loaded[0]);
        assert!(first_text.contains("Earlier conversation summary"));
        assert!(first_text.contains("earlier: u0 -> a1"));
    }

    #[tokio::test]
    async fn test_isolation_between_conversations() {
        let (_dir, m) = open_test();
        m.append("a", &[Message::user("hi a")]).await.unwrap();
        m.append("b", &[Message::user("hi b")]).await.unwrap();
        assert_eq!(m.load_active("a").await.unwrap().len(), 1);
        assert_eq!(m.load_active("b").await.unwrap().len(), 1);
    }

    #[tokio::test]
    async fn test_list_for_session() {
        let (_dir, m) = open_test();
        m.append(
            "thread-1",
            &[
                Message::user("u0"),
                Message::assistant("a1"),
                Message::user("u2"),
            ],
        )
        .await
        .unwrap();
        let list = m.list_for_session("thread-1").await.unwrap();
        assert_eq!(list.len(), 3);
        assert_eq!(list[0].role, "user");
        assert_eq!(list[0].content, "u0");
        assert!(!list[0].is_summary);
    }

    #[tokio::test]
    async fn test_open_idempotent() {
        let dir = tempdir().unwrap();
        let _ = SqliteConversationMemory::open(dir.path()).unwrap();
        // Second open on the same path: must succeed and share schema.
        let m = SqliteConversationMemory::open(dir.path()).unwrap();
        assert!(m.table_exists().await.unwrap());
        assert_eq!(m.db_path(), dir.path().join(".mbforge/conversations.db"));
    }

    #[tokio::test]
    async fn test_empty_append_is_noop() {
        let (_dir, m) = open_test();
        m.append("c", &[]).await.unwrap();
        assert_eq!(m.raw_count("c").await.unwrap(), 0);
    }
}
