use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Tool parameter schema (JSON Schema properties).
pub type ParameterSchema = HashMap<String, serde_json::Value>;

/// Registered tool information.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolInfo {
    pub name: String,
    pub description: String,
    pub parameters: ParameterSchema,
}

impl ToolInfo {
    pub fn new(name: &str, description: &str, parameters: ParameterSchema) -> Self {
        Self {
            name: name.to_string(),
            description: description.to_string(),
            parameters,
        }
    }

    /// Export as OpenAI function-calling schema.
    pub fn to_openai_schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                }
            }
        })
    }
}

/// Tool registry with name-based lookup and native function dispatch.
#[derive(Debug)]
pub struct ToolRegistry {
    tools: HashMap<String, ToolInfo>,
    native_funcs: HashMap<String, Box<dyn Fn(&serde_json::Value) -> String>>,
}

impl Default for ToolRegistry {
    fn default() -> Self {
        Self {
            tools: HashMap::new(),
            native_funcs: HashMap::new(),
        }
    }
}

impl ToolRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn register(&mut self, info: ToolInfo) {
        self.tools.insert(info.name.clone(), info);
    }

    /// Register a tool with a native Rust function (no sidecar needed).
    pub fn register_with_fn(&mut self, info: ToolInfo, func: Box<dyn Fn(&serde_json::Value) -> String>) {
        let name = info.name.clone();
        self.tools.insert(name.clone(), info);
        self.native_funcs.insert(name, func);
    }

    pub fn get(&self, name: &str) -> Option<&ToolInfo> {
        self.tools.get(name)
    }

    /// Get native function for a tool (returns None if it's a sidecar tool).
    pub fn get_native(&self, name: &str) -> Option<&Box<dyn Fn(&serde_json::Value) -> String>> {
        self.native_funcs.get(name)
    }

    pub fn list(&self) -> Vec<&ToolInfo> {
        self.tools.values().collect()
    }

    pub fn to_openai_schemas(&self) -> Vec<serde_json::Value> {
        self.tools.values().map(|t| t.to_openai_schema()).collect()
    }

    pub fn names(&self) -> Vec<&str> {
        self.tools.keys().map(|s| s.as_str()).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_registry() {
        let mut reg = ToolRegistry::new();
        reg.register(ToolInfo::new("search", "Search KB", HashMap::new()));
        assert!(reg.get("search").is_some());
        assert_eq!(reg.list().len(), 1);
    }

    #[test]
    fn test_native_registry() {
        let mut reg = ToolRegistry::new();
        reg.register_with_fn(
            ToolInfo::new("echo", "Echo input", HashMap::new()),
            Box::new(|args| args["text"].as_str().unwrap_or("empty").to_string()),
        );
        assert!(reg.get_native("echo").is_some());
        let func = reg.get_native("echo").unwrap();
        let result = func(&serde_json::json!({"text": "hello"}));
        assert_eq!(result, "hello");
    }

    #[test]
    fn test_openai_schema() {
        let tool = ToolInfo::new("test", "Test tool", HashMap::new());
        let schema = tool.to_openai_schema();
        assert_eq!(schema["type"], "function");
        assert_eq!(schema["function"]["name"], "test");
    }
}
