use serde::{Deserialize, Serialize};

use super::config::ModelConfig;
use super::constants::PROVIDER_ANTHROPIC;
use super::context::Message;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmResponse {
    pub content: String,
    pub tool_calls: Vec<ToolCall>,
    pub finish_reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    pub id: String,
    pub name: String,
    pub arguments: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamChunk {
    pub delta: String,
    pub finish_reason: Option<String>,
}

pub struct LlmClient {
    config: ModelConfig,
    http_client: reqwest::Client,
}

impl LlmClient {
    pub fn new(config: &ModelConfig) -> Self {
        let http_client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(120))
            .build()
            .expect("Failed to create HTTP client");
        Self {
            config: config.clone(),
            http_client,
        }
    }

    fn is_anthropic(&self) -> bool {
        self.config.provider.to_lowercase() == PROVIDER_ANTHROPIC
    }

    pub async fn chat(
        &self,
        messages: &[Message],
        tools: Option<&[serde_json::Value]>,
    ) -> Result<LlmResponse, String> {
        if self.is_anthropic() {
            self.chat_anthropic(messages, tools).await
        } else {
            self.chat_openai(messages, tools).await
        }
    }

    async fn chat_openai(
        &self,
        messages: &[Message],
        tools: Option<&[serde_json::Value]>,
    ) -> Result<LlmResponse, String> {
        let url = format!(
            "{}/chat/completions",
            self.config.base_url.trim_end_matches('/')
        );
        let mut body = serde_json::json!({
            "model": self.config.model_name,
            "messages": messages_to_openai(messages),
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
        });
        if let Some(tools) = tools {
            body["tools"] = serde_json::json!(tools);
        }
        let resp = self
            .http_client
            .post(&url)
            .header("Content-Type", "application/json")
            .header("Authorization", format!("Bearer {}", self.config.api_key))
            .json(&body)
            .send()
            .await
            .map_err(|e| format!("HTTP error: {}", e))?;
        let text = resp
            .text()
            .await
            .map_err(|e| format!("Read error: {}", e))?;
        parse_openai_response(&text)
    }

    async fn chat_anthropic(
        &self,
        messages: &[Message],
        tools: Option<&[serde_json::Value]>,
    ) -> Result<LlmResponse, String> {
        let url = format!("{}/v1/messages", self.config.base_url.trim_end_matches('/'));
        let (system, msgs) = messages_to_anthropic(messages);
        let mut body = serde_json::json!({
            "model": self.config.model_name,
            "messages": msgs,
            "max_tokens": self.config.max_tokens,
        });
        if !system.is_empty() {
            body["system"] = serde_json::json!(system);
        }
        if self.config.temperature > 0.0 {
            body["temperature"] = serde_json::json!(self.config.temperature);
        }
        if let Some(tools) = tools {
            body["tools"] = serde_json::json!(tools_to_anthropic(tools));
        }
        let resp = self
            .http_client
            .post(&url)
            .header("Content-Type", "application/json")
            .header("x-api-key", &self.config.api_key)
            .header("anthropic-version", "2023-06-01")
            .json(&body)
            .send()
            .await
            .map_err(|e| format!("HTTP error: {}", e))?;
        let text = resp
            .text()
            .await
            .map_err(|e| format!("Read error: {}", e))?;
        parse_anthropic_response(&text)
    }

    pub async fn chat_stream(
        &self,
        messages: &[Message],
        tools: Option<&[serde_json::Value]>,
    ) -> Result<tokio::sync::mpsc::Receiver<StreamChunk>, String> {
        let (tx, rx) = tokio::sync::mpsc::channel(64);
        if self.is_anthropic() {
            self.stream_anthropic(messages, tools, tx).await?;
        } else {
            self.stream_openai(messages, tools, tx).await?;
        }
        Ok(rx)
    }

    async fn stream_openai(
        &self,
        messages: &[Message],
        tools: Option<&[serde_json::Value]>,
        tx: tokio::sync::mpsc::Sender<StreamChunk>,
    ) -> Result<(), String> {
        let url = format!(
            "{}/chat/completions",
            self.config.base_url.trim_end_matches('/')
        );
        let mut body = serde_json::json!({
            "model": self.config.model_name,
            "messages": messages_to_openai(messages),
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "stream": true,
        });
        if let Some(tools) = tools {
            body["tools"] = serde_json::json!(tools);
        }
        let resp = self
            .http_client
            .post(&url)
            .header("Content-Type", "application/json")
            .header("Authorization", format!("Bearer {}", self.config.api_key))
            .json(&body)
            .send()
            .await
            .map_err(|e| format!("HTTP error: {}", e))?;
        let mut stream = resp.bytes_stream();
        use futures::StreamExt;
        let mut buffer = String::new();
        while let Some(chunk) = stream.next().await {
            let bytes = chunk.map_err(|e| format!("Stream error: {}", e))?;
            buffer.push_str(&String::from_utf8_lossy(&bytes));
            while let Some(line_end) = buffer.find('\n') {
                let line = buffer[..line_end].trim().to_string();
                buffer = buffer[line_end + 1..].to_string();
                if line.is_empty() || !line.starts_with("data: ") {
                    continue;
                }
                let data = &line[6..];
                if data == "[DONE]" {
                    let _ = tx
                        .send(StreamChunk {
                            delta: String::new(),
                            finish_reason: Some("stop".into()),
                        })
                        .await;
                    return Ok(());
                }
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(data) {
                    let delta = val["choices"][0]["delta"]["content"]
                        .as_str()
                        .unwrap_or("")
                        .to_string();
                    let finish = val["choices"][0]["finish_reason"]
                        .as_str()
                        .map(|s| s.to_string());
                    if !delta.is_empty() || finish.is_some() {
                        let _ = tx
                            .send(StreamChunk {
                                delta,
                                finish_reason: finish,
                            })
                            .await;
                    }
                }
            }
        }
        Ok(())
    }

    async fn stream_anthropic(
        &self,
        messages: &[Message],
        tools: Option<&[serde_json::Value]>,
        tx: tokio::sync::mpsc::Sender<StreamChunk>,
    ) -> Result<(), String> {
        let url = format!("{}/v1/messages", self.config.base_url.trim_end_matches('/'));
        let (system, msgs) = messages_to_anthropic(messages);
        let mut body = serde_json::json!({
            "model": self.config.model_name,
            "messages": msgs,
            "max_tokens": self.config.max_tokens,
            "stream": true,
        });
        if !system.is_empty() {
            body["system"] = serde_json::json!(system);
        }
        if let Some(tools) = tools {
            body["tools"] = serde_json::json!(tools_to_anthropic(tools));
        }
        let resp = self
            .http_client
            .post(&url)
            .header("Content-Type", "application/json")
            .header("x-api-key", &self.config.api_key)
            .header("anthropic-version", "2023-06-01")
            .json(&body)
            .send()
            .await
            .map_err(|e| format!("HTTP error: {}", e))?;
        let mut stream = resp.bytes_stream();
        use futures::StreamExt;
        let mut buffer = String::new();
        while let Some(chunk) = stream.next().await {
            let bytes = chunk.map_err(|e| format!("Stream error: {}", e))?;
            buffer.push_str(&String::from_utf8_lossy(&bytes));
            while let Some(line_end) = buffer.find('\n') {
                let line = buffer[..line_end].trim().to_string();
                buffer = buffer[line_end + 1..].to_string();
                if line.starts_with("data: ") {
                    let data = &line[6..];
                    if let Ok(val) = serde_json::from_str::<serde_json::Value>(data) {
                        let event_type = val["type"].as_str().unwrap_or("");
                        match event_type {
                            "content_block_delta" => {
                                if val["delta"]["type"].as_str() == Some("text_delta") {
                                    let text =
                                        val["delta"]["text"].as_str().unwrap_or("").to_string();
                                    if !text.is_empty() {
                                        let _ = tx
                                            .send(StreamChunk {
                                                delta: text,
                                                finish_reason: None,
                                            })
                                            .await;
                                    }
                                }
                            }
                            "message_delta" => {
                                let stop =
                                    val["delta"]["stop_reason"].as_str().map(|s| s.to_string());
                                let _ = tx
                                    .send(StreamChunk {
                                        delta: String::new(),
                                        finish_reason: stop,
                                    })
                                    .await;
                            }
                            _ => {}
                        }
                    }
                }
            }
        }
        Ok(())
    }
}

// --- Message format conversion ---

pub fn messages_to_openai(messages: &[Message]) -> Vec<serde_json::Value> {
    messages
        .iter()
        .map(|m| {
            let mut obj = serde_json::json!({
                "role": m.role,
                "content": m.content,
            });
            if let Some(ref tool_calls) = m.tool_calls {
                obj["tool_calls"] = serde_json::json!(tool_calls);
            }
            if let Some(ref name) = m.name {
                obj["name"] = serde_json::json!(name);
            }
            if let Some(ref tc_id) = m.tool_call_id {
                obj["tool_call_id"] = serde_json::json!(tc_id);
            }
            obj
        })
        .collect()
}

pub fn messages_to_anthropic(messages: &[Message]) -> (String, Vec<serde_json::Value>) {
    let mut system_parts = Vec::new();
    let mut anthropic_msgs = Vec::new();

    for m in messages {
        match m.role.as_str() {
            "system" => system_parts.push(m.content.clone()),
            "tool" => {
                let tool_result = serde_json::json!({
                    "type": "tool_result",
                    "tool_use_id": m.tool_call_id.as_deref().unwrap_or(""),
                    "content": m.content,
                });
                anthropic_msgs.push(serde_json::json!({
                    "role": "user",
                    "content": [tool_result],
                }));
            }
            "assistant" => {
                if let Some(ref tool_calls) = m.tool_calls {
                    let mut content = Vec::new();
                    if !m.content.is_empty() {
                        content.push(serde_json::json!({"type": "text", "text": m.content}));
                    }
                    for tc in tool_calls {
                        content.push(serde_json::json!({
                            "type": "tool_use",
                            "id": tc["id"].as_str().unwrap_or(""),
                            "name": tc["function"]["name"].as_str().unwrap_or(""),
                            "input": tc["function"]["arguments"],
                        }));
                    }
                    anthropic_msgs.push(serde_json::json!({
                        "role": "assistant",
                        "content": content,
                    }));
                } else {
                    anthropic_msgs.push(serde_json::json!({
                        "role": "assistant",
                        "content": [{"type": "text", "text": m.content}],
                    }));
                }
            }
            _ => {
                anthropic_msgs.push(serde_json::json!({
                    "role": m.role,
                    "content": [{"type": "text", "text": m.content}],
                }));
            }
        }
    }

    (system_parts.join("\n"), anthropic_msgs)
}

pub fn tools_to_anthropic(tools: &[serde_json::Value]) -> Vec<serde_json::Value> {
    tools
        .iter()
        .filter_map(|t| {
            let func = &t["function"];
            Some(serde_json::json!({
                "name": func["name"].as_str()?,
                "description": func["description"].as_str().unwrap_or(""),
                "input_schema": func["parameters"],
            }))
        })
        .collect()
}

// --- Response parsing ---

pub fn parse_openai_response(text: &str) -> Result<LlmResponse, String> {
    let val: serde_json::Value =
        serde_json::from_str(text).map_err(|e| format!("JSON parse error: {}", e))?;
    let content = val["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or("")
        .to_string();
    let finish_reason = val["choices"][0]["finish_reason"]
        .as_str()
        .unwrap_or("")
        .to_string();
    let tool_calls = val["choices"][0]["message"]["tool_calls"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .map(|tc| ToolCall {
                    id: tc["id"].as_str().unwrap_or("").to_string(),
                    name: tc["function"]["name"].as_str().unwrap_or("").to_string(),
                    arguments: serde_json::from_str(
                        tc["function"]["arguments"].as_str().unwrap_or("{}"),
                    )
                    .unwrap_or(serde_json::json!({})),
                })
                .collect()
        })
        .unwrap_or_default();
    Ok(LlmResponse {
        content,
        tool_calls,
        finish_reason,
    })
}

pub fn parse_anthropic_response(text: &str) -> Result<LlmResponse, String> {
    let val: serde_json::Value =
        serde_json::from_str(text).map_err(|e| format!("JSON parse error: {}", e))?;
    let finish_reason = val["stop_reason"].as_str().unwrap_or("").to_string();
    let mut content = String::new();
    let mut tool_calls = Vec::new();
    if let Some(blocks) = val["content"].as_array() {
        for block in blocks {
            match block["type"].as_str() {
                Some("text") => {
                    if let Some(t) = block["text"].as_str() {
                        content.push_str(t);
                    }
                }
                Some("tool_use") => {
                    tool_calls.push(ToolCall {
                        id: block["id"].as_str().unwrap_or("").to_string(),
                        name: block["name"].as_str().unwrap_or("").to_string(),
                        arguments: block["input"].clone(),
                    });
                }
                _ => {}
            }
        }
    }
    Ok(LlmResponse {
        content,
        tool_calls,
        finish_reason,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_messages_to_openai() {
        let msgs = vec![Message::system("You are helpful"), Message::user("Hello")];
        let result = messages_to_openai(&msgs);
        assert_eq!(result.len(), 2);
        assert_eq!(result[0]["role"], "system");
        assert_eq!(result[1]["role"], "user");
    }

    #[test]
    fn test_messages_to_anthropic_system_extraction() {
        let msgs = vec![Message::system("System prompt"), Message::user("Hello")];
        let (system, anthropic_msgs) = messages_to_anthropic(&msgs);
        assert_eq!(system, "System prompt");
        assert_eq!(anthropic_msgs.len(), 1);
        assert_eq!(anthropic_msgs[0]["role"], "user");
    }

    #[test]
    fn test_parse_openai_response() {
        let json = r#"{"choices":[{"message":{"content":"Hello","tool_calls":null},"finish_reason":"stop"}]}"#;
        let resp = parse_openai_response(json).unwrap();
        assert_eq!(resp.content, "Hello");
        assert!(resp.tool_calls.is_empty());
    }

    #[test]
    fn test_parse_anthropic_response() {
        let json = r#"{"content":[{"type":"text","text":"Hello"}],"stop_reason":"end_turn"}"#;
        let resp = parse_anthropic_response(json).unwrap();
        assert_eq!(resp.content, "Hello");
        assert!(resp.tool_calls.is_empty());
    }

    #[test]
    fn test_parse_anthropic_with_tool_calls() {
        let json = r#"{"content":[{"type":"tool_use","id":"tc1","name":"search","input":{"query":"test"}}],"stop_reason":"tool_use"}"#;
        let resp = parse_anthropic_response(json).unwrap();
        assert!(resp.content.is_empty());
        assert_eq!(resp.tool_calls.len(), 1);
        assert_eq!(resp.tool_calls[0].name, "search");
    }

    #[test]
    fn test_tools_to_anthropic() {
        let tools = vec![serde_json::json!({
            "type": "function",
            "function": {"name": "search", "description": "Search", "parameters": {"type": "object", "properties": {}}}
        })];
        let result = tools_to_anthropic(&tools);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0]["name"], "search");
    }
}
