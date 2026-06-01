use std::path::Path;

use serde::{Deserialize, Serialize};

use super::helpers::estimate_tokens;

/// A single message in the conversation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: String,
    pub content: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_calls: Option<Vec<serde_json::Value>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_call_id: Option<String>,
}

impl Message {
    pub fn system(content: &str) -> Self {
        Self { role: "system".into(), content: content.to_string(), tool_calls: None, name: None, tool_call_id: None }
    }
    pub fn user(content: &str) -> Self {
        Self { role: "user".into(), content: content.to_string(), tool_calls: None, name: None, tool_call_id: None }
    }
    pub fn assistant(content: &str) -> Self {
        Self { role: "assistant".into(), content: content.to_string(), tool_calls: None, name: None, tool_call_id: None }
    }
    pub fn tool(name: &str, content: &str, call_id: &str) -> Self {
        Self { role: "tool".into(), content: content.to_string(), tool_calls: None, name: Some(name.to_string()), tool_call_id: Some(call_id.to_string()) }
    }
}

/// A layer in the layered context.
///
/// Ephemeral layers are automatically cleared after their content is consumed
/// by [`LayeredContext::build_messages`], ensuring temporary context (e.g.
/// retrieval trajectory, RAG injections) does not leak across conversation
/// turns.
#[derive(Debug, Clone, Default)]
struct ContextLayer {
    messages: Vec<Message>,
    ephemeral: bool,
}

impl ContextLayer {
    fn new(ephemeral: bool) -> Self {
        Self { messages: Vec::new(), ephemeral }
    }

    fn token_count(&self) -> usize {
        self.messages.iter().map(|m| estimate_tokens(&m.content)).sum()
    }

    fn clear(&mut self) {
        self.messages.clear();
    }

    fn is_ephemeral(&self) -> bool {
        self.ephemeral
    }
}

/// Layered conversation context (L0-L3).
///
/// - L0 system:   System prompt (permanent)
/// - L1 project:  Project context
/// - L2 tools:    Tool results (ephemeral)
/// - L3 history:  Conversation history (trimmable)
#[derive(Debug, Clone)]
pub struct LayeredContext {
    system: ContextLayer,
    project: ContextLayer,
    tools: ContextLayer,
    history: ContextLayer,
    max_history_rounds: usize,
    max_total_tokens: usize,
}

impl LayeredContext {
    pub fn new(system_prompt: &str, max_history_rounds: usize, max_total_tokens: usize) -> Self {
        let mut ctx = Self {
            system: ContextLayer::new(false),
            project: ContextLayer::new(false),
            tools: ContextLayer::new(true),
            history: ContextLayer::new(false),
            max_history_rounds,
            max_total_tokens,
        };
        if !system_prompt.is_empty() {
            ctx.set_system_prompt(system_prompt);
        }
        ctx
    }

    pub fn set_system_prompt(&mut self, prompt: &str) {
        self.system.messages = vec![Message::system(prompt)];
    }

    pub fn set_project_context(&mut self, context: &str) {
        self.project.messages = vec![Message::system(&format!("[项目上下文]\n{}", context))];
    }

    pub fn inject_memory(&mut self, memory_text: &str) {
        if !memory_text.is_empty() {
            self.project.messages.push(Message::system(&format!("[用户记忆]\n{}", memory_text)));
        }
    }

    pub fn inject_agent_memory(&mut self, memory_text: &str) {
        if !memory_text.is_empty() {
            self.project.messages.push(Message::system(&format!("[Agent 经验]\n{}", memory_text)));
        }
    }

    pub fn inject_retrieval_trajectory(&mut self, trajectory_text: &str) {
        if !trajectory_text.is_empty() {
            self.tools.messages.push(Message::system(&format!("[检索轨迹]\n{}", trajectory_text)));
        }
    }

    pub fn add_user_message(&mut self, content: &str) {
        self.history.messages.push(Message::user(content));
    }

    pub fn add_assistant_message(&mut self, content: &str) {
        self.history.messages.push(Message::assistant(content));
    }

    pub fn add_assistant_message_with_tool_calls(&mut self, content: &str, tool_calls: &[super::llm::ToolCall]) {
        let tc_values: Vec<serde_json::Value> = tool_calls.iter().map(|tc| {
            serde_json::json!({
                "id": tc.id,
                "function": {
                    "name": tc.name,
                    "arguments": tc.arguments.to_string(),
                }
            })
        }).collect();
        self.history.messages.push(Message {
            role: "assistant".into(),
            content: content.to_string(),
            tool_calls: Some(tc_values),
            name: None,
            tool_call_id: None,
        });
    }

    pub fn add_tool_result(&mut self, tool_name: &str, result: &str, tool_call_id: &str) {
        let truncated = if result.len() > 4000 { &result[..result.floor_char_boundary(4000)] } else { result };
        self.history.messages.push(Message::tool(tool_name, truncated, tool_call_id));
    }

    pub fn clear_tool_results(&mut self) {
        self.tools.clear();
    }

    /// Clear history and all ephemeral layers.
    pub fn clear_history(&mut self) {
        self.history.clear();
        self.tools.clear();
    }

    /// Trim history to fit token limits.
    pub fn trim_history(&mut self) {
        // Round-based trimming
        let max_msgs = self.max_history_rounds * 2;
        if self.history.messages.len() > max_msgs {
            let drain = self.history.messages.len() - max_msgs;
            self.history.messages.drain(..drain);
        }

        // Token-based trimming
        while self.total_token_count() > self.max_total_tokens && self.history.messages.len() > 2 {
            self.history.messages.remove(0);
            if self.history.messages.first().map_or(false, |m| m.role == "assistant") {
                self.history.messages.remove(0);
            }
        }
    }

    pub fn total_token_count(&self) -> usize {
        self.system.token_count() + self.project.token_count() + self.history.token_count()
    }

    /// Get history messages without mutating state (read-only).
    pub fn get_history_messages(&self) -> Vec<Message> {
        self.history.messages.clone()
    }

    /// Build message list for LLM call.
    ///
    /// Ephemeral layers (e.g. `tools`) are included when requested and then
    /// automatically cleared so their content does not persist to the next
    /// turn.
    pub fn build_messages(&mut self, include_tools: bool, include_history: bool) -> Vec<Message> {
        let mut result = Vec::new();
        result.extend(self.system.messages.clone());
        result.extend(self.project.messages.clone());
        if include_tools {
            result.extend(self.tools.messages.clone());
            if self.tools.is_ephemeral() {
                self.tools.clear();
            }
        }
        if include_history {
            self.trim_history();
            result.extend(self.history.messages.clone());
        }
        result
    }

    /// Serialize to JSON-compatible map.
    ///
    /// Note: ephemeral layers are intentionally excluded from serialization
    /// as they are transient per-turn context.
    pub fn to_dict(&self) -> serde_json::Value {
        serde_json::json!({
            "system": self.system.messages,
            "project": self.project.messages,
            "history": self.history.messages,
            "max_history_rounds": self.max_history_rounds,
            "max_total_tokens": self.max_total_tokens,
        })
    }

    /// Deserialize from JSON.
    pub fn from_dict(data: &serde_json::Value) -> Self {
        let mut ctx = Self::new(
            "",
            data["max_history_rounds"].as_u64().unwrap_or(20) as usize,
            data["max_total_tokens"].as_u64().unwrap_or(32000) as usize,
        );
        if let Some(sys) = data["system"].as_array() {
            ctx.system.messages = serde_json::from_value(serde_json::Value::Array(sys.clone())).unwrap_or_default();
        }
        if let Some(proj) = data["project"].as_array() {
            ctx.project.messages = serde_json::from_value(serde_json::Value::Array(proj.clone())).unwrap_or_default();
        }
        if let Some(hist) = data["history"].as_array() {
            ctx.history.messages = serde_json::from_value(serde_json::Value::Array(hist.clone())).unwrap_or_default();
        }
        ctx
    }

    /// Save context to file (excludes ephemeral layers).
    pub fn save_to_file(&self, path: &Path) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let data = self.to_dict();
        let json = serde_json::to_string_pretty(&data)?;
        std::fs::write(path, json)?;
        Ok(())
    }

    /// Load context from file.
    pub fn load_from_file(path: &Path) -> Option<Self> {
        let text = std::fs::read_to_string(path).ok()?;
        let data: serde_json::Value = serde_json::from_str(&text).ok()?;
        Some(Self::from_dict(&data))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_message_roles() {
        let m = Message::system("hello");
        assert_eq!(m.role, "system");
        let m = Message::tool("search", "result", "123");
        assert_eq!(m.role, "tool");
        assert_eq!(m.name, Some("search".into()));
    }

    #[test]
    fn test_layered_context() {
        let mut ctx = LayeredContext::new("You are a helper.", 5, 1000);
        ctx.add_user_message("hi");
        ctx.add_assistant_message("hello");
        let msgs = ctx.build_messages(true, true);
        assert!(msgs.len() >= 3); // system + user + assistant
    }

    #[test]
    fn test_token_estimate() {
        let mut ctx = LayeredContext::new("", 5, 1000);
        ctx.add_user_message("Hello world test message");
        assert!(ctx.total_token_count() > 0);
    }

    #[test]
    fn test_ephemeral_layer_auto_clear() {
        let mut ctx = LayeredContext::new("You are a helper.", 5, 1000);
        ctx.inject_retrieval_trajectory("临时检索结果 A");
        assert_eq!(ctx.tools.messages.len(), 1);

        // First build includes ephemeral content, then auto-clears it.
        let msgs = ctx.build_messages(true, true);
        assert!(msgs.iter().any(|m| m.content.contains("临时检索结果 A")));
        assert_eq!(ctx.tools.messages.len(), 0);

        // Second build no longer contains the cleared ephemeral content.
        let msgs2 = ctx.build_messages(true, false);
        assert!(!msgs2.iter().any(|m| m.content.contains("临时检索结果 A")));
    }

    #[test]
    fn test_ephemeral_skipped_when_include_tools_false() {
        let mut ctx = LayeredContext::new("System.", 5, 1000);
        ctx.inject_retrieval_trajectory("RAG context");
        assert_eq!(ctx.tools.messages.len(), 1);

        // When include_tools is false, ephemeral layer is NOT consumed/cleared.
        let msgs = ctx.build_messages(false, true);
        assert!(!msgs.iter().any(|m| m.content.contains("RAG context")));
        assert_eq!(ctx.tools.messages.len(), 1); // still preserved

        // It is still available for a subsequent build with include_tools=true.
        let msgs2 = ctx.build_messages(true, false);
        assert!(msgs2.iter().any(|m| m.content.contains("RAG context")));
        assert_eq!(ctx.tools.messages.len(), 0); // now cleared
    }
}
