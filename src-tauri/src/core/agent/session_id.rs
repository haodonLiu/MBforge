//! `SessionId` — newtype around the per-conversation thread id.
//!
//! The MBForge Tauri `session_id` (a string minted by the frontend via
//! `crypto.randomUUID()` and threaded through every agent command) is
//! the same identifier rig uses as its `conversation_id` and the same
//! one we use as the SQLite primary-key column in `conversations.db`.
//! Wrapping it in a newtype gives us:
//!
//! * Discoverable intent at every call site — `&SessionId` is hard to
//!   confuse with `&str` user input.
//! * A single place to add invariants later (UUID-format check, length
//!   cap, …) without touching the call sites.
//! * `Clone + Send + Sync` trivially, matching what the rig
//!   `PromptRequest::conversation(impl Into<String>)` accepts.
//!
//! See `core/agent/managed_memory.rs` for the memory backend that
//! actually keys storage on this id.

use std::fmt;
use std::ops::Deref;

/// A per-conversation thread id. Cheap to clone; safe to share across
/// threads.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct SessionId(pub String);

impl SessionId {
    /// Wrap any string-ish input as a `SessionId`.
    pub fn new(s: impl Into<String>) -> Self {
        Self(s.into())
    }

    /// Borrow the underlying string slice.
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl Deref for SessionId {
    type Target = str;
    fn deref(&self) -> &str {
        &self.0
    }
}

impl From<String> for SessionId {
    fn from(s: String) -> Self {
        Self(s)
    }
}

impl From<&str> for SessionId {
    fn from(s: &str) -> Self {
        Self(s.to_string())
    }
}

impl From<&SessionId> for SessionId {
    fn from(s: &SessionId) -> Self {
        s.clone()
    }
}

impl fmt::Display for SessionId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(f)
    }
}

impl AsRef<str> for SessionId {
    fn as_ref(&self) -> &str {
        &self.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_from_string_and_str() {
        let a: SessionId = String::from("abc").into();
        let b: SessionId = "abc".into();
        assert_eq!(a, b);
    }

    #[test]
    fn test_deref_and_as_str() {
        let s: SessionId = SessionId::new("hello");
        assert_eq!(s.as_str(), "hello");
        // Deref to &str — enables `&cid.len()` style call sites.
        assert_eq!(s.len(), 5);
    }

    #[test]
    fn test_display() {
        let s: SessionId = SessionId::new("thread-1");
        assert_eq!(format!("{}", s), "thread-1");
    }
}
