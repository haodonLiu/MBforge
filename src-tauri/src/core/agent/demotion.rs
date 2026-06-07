//! `EpisodicDemotionHook` — a `rig_core::memory::DemotionHook` impl that
//! writes evicted conversation messages into the `episodes` table of
//! `<project>/.mbforge/conversations.db`.
//!
//! # What we persist
//!
//! One row per evicted message. The `tags_json` column is a
//! rule-based keyword summary (top 8 tokens by frequency, after
//! dropping common Chinese + English stopwords). Full LLM-driven
//! semantic tagging is a v2 follow-up; keyword tags are sufficient
//! for the v1 contract (the test that proves multi-turn works) and
//! for any future `recall_episodes(query)` tool that searches by
//! keyword match.
//!
//! # `trace_id` correlation
//!
//! For v1 the `trace_id` we write equals the `session_id`. This is a
//! best-effort join key with the audit log + trajectory tracker
//! (which also mint one UUID per session). A real `session_id ↔
//! trace_id` mapping table is a v2 follow-up.

use std::sync::{Arc, Mutex};

use rusqlite::{params, Connection};

use rig_core::memory::{DemotionHook, MemoryError};
use rig_core::message::Message;
use rig_core::wasm_compat::WasmBoxedFuture;

use crate::core::helpers::now_rfc3339;

/// Common Chinese + English stopwords excluded from the keyword
/// extraction. Conservative — false positives are fine, false
/// negatives are not.
const STOPWORDS: &[&str] = &[
    // Chinese particles, pronouns, common verbs
    "的", "了", "是", "在", "我", "你", "他", "她", "它", "们", "和", "与", "或",
    "也", "都", "就", "要", "会", "能", "可以", "不", "没", "很", "也", "还",
    "把", "被", "对", "从", "到", "给", "让", "请", "问", "说", "答", "是",
    "那", "这", "什么", "怎么", "为什么", "吧", "呢", "吗", "啊", "哦", "嗯",
    // English
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "have",
    "has", "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "must", "shall", "can", "need", "dare", "ought", "used", "to", "of",
    "in", "on", "at", "by", "for", "with", "about", "against", "between", "into",
    "through", "during", "before", "after", "above", "below", "from", "up", "down",
    "out", "off", "over", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "any", "both", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "and", "but", "or", "if", "while",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us",
    "them", "my", "your", "his", "its", "our", "their", "this", "that", "these",
    "those",
];

/// Tag-extraction: take the text, split into CJK char n-grams (1-gram)
/// and ASCII words, drop stopwords, return the top 8 by frequency.
fn extract_tags(text: &str) -> Vec<String> {
    use std::collections::HashMap;
    let mut counts: HashMap<String, usize> = HashMap::new();
    let mut current_ascii = String::new();
    for ch in text.chars() {
        if ch.is_ascii_alphanumeric() {
            current_ascii.push(ch);
        } else {
            if !current_ascii.is_empty() {
                let w = current_ascii.to_lowercase();
                if w.len() >= 2 && !STOPWORDS.contains(&w.as_str()) {
                    *counts.entry(w).or_insert(0) += 1;
                }
                current_ascii.clear();
            }
            // CJK: treat each char as a 1-gram token.
            if (0x4E00..=0x9FFF).contains(&(ch as u32)) {
                let s = ch.to_string();
                if !STOPWORDS.contains(&s.as_str()) {
                    *counts.entry(s).or_insert(0) += 1;
                }
            }
        }
    }
    if !current_ascii.is_empty() {
        let w = current_ascii.to_lowercase();
        if w.len() >= 2 && !STOPWORDS.contains(&w.as_str()) {
            *counts.entry(w).or_insert(0) += 1;
        }
    }
    let mut v: Vec<(String, usize)> = counts.into_iter().collect();
    v.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    v.into_iter().take(8).map(|(s, _)| s).collect()
}

/// `DemotionHook` that persists evicted messages to a SQLite `episodes`
/// table. Cheap to clone.
#[derive(Clone)]
pub struct EpisodicDemotionHook {
    conn: Arc<Mutex<Connection>>,
    pub trace_id: String,
}

impl EpisodicDemotionHook {
    pub fn new(conn: Arc<Mutex<Connection>>, trace_id: impl Into<String>) -> Self {
        Self {
            conn,
            trace_id: trace_id.into(),
        }
    }
}

fn bootstrap_episodes_schema(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS episodes (
            episode_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id     TEXT NOT NULL,
            trace_id       TEXT,
            seq            INTEGER NOT NULL,
            user_text      TEXT,
            assistant_text TEXT,
            tags_json      TEXT,
            created_at     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_episodes_session
            ON episodes(session_id, seq);
        "#,
    )
    .map_err(|e| format!("bootstrap episodes schema: {e}"))
}

fn text_of_msg(m: &Message) -> String {
    match m {
        Message::System { content } => content.clone(),
        Message::User { content } => match content.first_ref() {
            rig_core::message::UserContent::Text(t) => t.text.clone(),
            _ => String::new(),
        },
        Message::Assistant { content, .. } => match content.first_ref() {
            rig_core::message::AssistantContent::Text(t) => t.text.clone(),
            _ => String::new(),
        },
    }
}

impl DemotionHook for EpisodicDemotionHook {
    fn on_demote<'a>(
        &'a self,
        conversation_id: &'a str,
        evicted: Vec<Message>,
    ) -> WasmBoxedFuture<'a, Result<(), MemoryError>> {
        Box::pin(async move {
            // Always bootstrap the schema, not just when we have rows
            // to insert — the empty-input path is also tested and
            // there's no reason to skip a no-op `CREATE IF NOT EXISTS`.
            let mut conn = self.conn.lock().map_err(|e| MemoryError::backend(format!("lock: {e}")))?;
            bootstrap_episodes_schema(&conn).map_err(MemoryError::backend)?;
            if evicted.is_empty() {
                return Ok(());
            }
            let now = now_rfc3339();
            // Pair user + assistant in the same row so a recall tool
            // can reconstruct turns; unpaired messages get NULL on the
            // other side.
            let mut i = 0;
            let mut seq_counter: i64 = 0;
            while i < evicted.len() {
                let m = &evicted[i];
                let (role_a, text_a) = match m {
                    Message::User { .. } => ("user", text_of_msg(m)),
                    Message::Assistant { .. } => ("assistant", text_of_msg(m)),
                    Message::System { content } => ("system", content.clone()),
                };
                let (user_text, assistant_text) = if role_a == "user" {
                    // Look ahead for the matching assistant turn.
                    let next_is_assistant = evicted
                        .get(i + 1)
                        .map(|n| matches!(n, Message::Assistant { .. }))
                        .unwrap_or(false);
                    if next_is_assistant {
                        let asst_text = text_of_msg(&evicted[i + 1]);
                        i += 2;
                        (Some(text_a), Some(asst_text))
                    } else {
                        i += 1;
                        (Some(text_a), None)
                    }
                } else if role_a == "assistant" {
                    // Leading assistant without a preceding user.
                    i += 1;
                    (None, Some(text_a))
                } else {
                    i += 1;
                    (Some(text_a), None)
                };

                // Tag extraction: take the union of the row's text
                // tokens (cap at 2000 chars for tag perf).
                let tag_source = format!(
                    "{} {}",
                    user_text.clone().unwrap_or_default(),
                    assistant_text.clone().unwrap_or_default()
                );
                let tag_source: String = tag_source.chars().take(2000).collect();
                let tags = extract_tags(&tag_source);
                let tags_json = serde_json::to_string(&tags).unwrap_or_else(|_| "[]".into());

                conn.execute(
                    "INSERT INTO episodes (session_id, trace_id, seq, user_text, assistant_text, tags_json, created_at) \
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
                    params![
                        conversation_id,
                        self.trace_id,
                        seq_counter,
                        user_text,
                        assistant_text,
                        tags_json,
                        now
                    ],
                )
                .map_err(|e| MemoryError::backend(format!("insert episode: {e}")))?;
                seq_counter += 1;
            }
            Ok(())
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn open_test_conn() -> (tempfile::TempDir, Arc<Mutex<Connection>>) {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test.db");
        let conn = Connection::open(&path).unwrap();
        (dir, Arc::new(Mutex::new(conn)))
    }

    #[test]
    fn test_extract_tags_drops_stopwords() {
        let tags = extract_tags("洗车店离家50米，开车还是走过去？我要去洗车。");
        assert!(tags.contains(&"洗".to_string()) || tags.contains(&"车".to_string()));
        assert!(!tags.contains(&"我".to_string()));
        assert!(!tags.contains(&"的".to_string()));
    }

    #[test]
    fn test_extract_tags_top_n() {
        let s = "alpha beta alpha gamma alpha delta";
        let tags = extract_tags(s);
        // alpha appears 3 times; should be first.
        assert_eq!(tags.first().map(|s| s.as_str()), Some("alpha"));
    }

    #[test]
    fn test_on_demote_writes_episode_rows() {
        let (_dir, conn) = open_test_conn();
        let hook = EpisodicDemotionHook::new(conn.clone(), "trace-abc");
        let evicted = vec![
            Message::user("洗车店离家50米"),
            Message::assistant("建议步行过去"),
            Message::user("那要带什么吗"),
            Message::assistant("带车钥匙"),
        ];
        // Run the future synchronously via a small tokio block_on.
        let fut = hook.on_demote("session-1", evicted);
        let result = futures::executor::block_on(fut);
        result.unwrap();

        let guard = conn.lock().unwrap();
        let count: i64 = guard
            .query_row("SELECT COUNT(*) FROM episodes", [], |row| row.get(0))
            .unwrap();
        // 4 evicted messages → 2 user+assistant pairs → 2 rows.
        assert_eq!(count, 2);
        let (user_text, assistant_text, trace_id): (String, String, String) = guard
            .query_row(
                "SELECT user_text, assistant_text, trace_id FROM episodes WHERE seq = 0",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!(user_text, "洗车店离家50米");
        assert_eq!(assistant_text, "建议步行过去");
        assert_eq!(trace_id, "trace-abc");
    }

    #[test]
    fn test_on_demote_empty_is_noop() {
        let (_dir, conn) = open_test_conn();
        let hook = EpisodicDemotionHook::new(conn.clone(), "trace");
        let fut = hook.on_demote("s", vec![]);
        futures::executor::block_on(fut).unwrap();
        let guard = conn.lock().unwrap();
        let count: i64 = guard
            .query_row("SELECT COUNT(*) FROM episodes", [], |row| row.get(0))
            .unwrap();
        assert_eq!(count, 0);
    }
}
