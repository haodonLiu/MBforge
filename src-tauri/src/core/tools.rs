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

/// Tool registry with name-based lookup.
#[derive(Debug, Default)]
pub struct ToolRegistry {
    tools: HashMap<String, ToolInfo>,
}

impl ToolRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn register(&mut self, info: ToolInfo) {
        self.tools.insert(info.name.clone(), info);
    }

    pub fn get(&self, name: &str) -> Option<&ToolInfo> {
        self.tools.get(name)
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
    fn test_openai_schema() {
        let tool = ToolInfo::new("test", "Test tool", HashMap::new());
        let schema = tool.to_openai_schema();
        assert_eq!(schema["type"], "function");
        assert_eq!(schema["function"]["name"], "test");
    }
}
