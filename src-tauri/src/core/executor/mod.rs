//! Agent tool executor — orchestrates native and sidecar execution.
//!
//! Tool registrations are split across focused submodules:
//! - [`fs`]        file system search / read / list
//! - [`kb`]        knowledge base search / structure / pages
//! - [`document`]  document abstracts / overviews / listing
//! - [`molecule`]  molecule analysis + Markush overlap
//! - [`literature`]  arXiv / PMC paper access
//!
//! The orchestrator below wires them all into a single [`ToolRegistry`]
//! and exposes the [`ToolExecutor`] facade that the Agent uses.

use super::document::document_tree::DocumentTreeIndex;
use super::document::knowledge_base::KnowledgeBase;
use super::document::summary::SummaryManager;
use super::tools::{ToolInfo, ToolRegistry};

pub mod arxiv;
pub mod document;
pub mod fs;
pub mod kb;
pub mod literature;
pub mod molecule;

pub struct ToolExecutor {
    pub sidecar_url: String,
    pub project_root: String,
    pub registry: ToolRegistry,
    // 可选依赖（Agent 工具 Native 化后注入）
    pub kb: Option<KnowledgeBase>,
    pub tree_index: Option<DocumentTreeIndex>,
    pub summary: Option<SummaryManager>,
}

impl ToolExecutor {
    /// 原有构造函数（保持向后兼容，Agent::new() 调用这个）
    pub fn new(sidecar_url: &str, project_root: &str) -> Self {
        let mut registry = ToolRegistry::new();
        register_native_tools(&mut registry, project_root);
        Self {
            sidecar_url: sidecar_url.to_string(),
            project_root: project_root.to_string(),
            registry,
            kb: None,
            tree_index: None,
            summary: None,
        }
    }

    /// 带完整依赖的构造函数（index_project_rust 调用这个）
    pub fn new_with_deps(
        sidecar_url: &str,
        project_root: &str,
        kb: KnowledgeBase,
        tree_index: DocumentTreeIndex,
        summary: SummaryManager,
    ) -> Self {
        let mut executor = Self::new(sidecar_url, project_root);
        executor.kb = Some(kb);
        executor.tree_index = Some(tree_index);
        executor.summary = Some(summary);
        executor
    }

    /// 注入依赖（Agent 初始化后调用）
    pub fn set_kb(&mut self, kb: KnowledgeBase) {
        self.kb = Some(kb);
    }
    pub fn set_tree_index(&mut self, tree: DocumentTreeIndex) {
        self.tree_index = Some(tree);
    }
    pub fn set_summary(&mut self, summary: SummaryManager) {
        self.summary = Some(summary);
    }

    pub async fn execute(&self, name: &str, args: &serde_json::Value) -> String {
        // 先查 native 工具
        if let Some(func) = self.registry.get_native(name) {
            return func(args);
        }
        // 走 sidecar
        self.execute_sidecar(name, args).await
    }

    async fn execute_sidecar(&self, name: &str, args: &serde_json::Value) -> String {
        let url = format!(
            "{}/api/v1/tools/call",
            self.sidecar_url.trim_end_matches('/')
        );
        let body = serde_json::json!({
            "tool": name,
            "args": args,
            "project_root": self.project_root,
        });
        let client = crate::core::http::client_30s();
        let resp = match client
            .post(&url)
            .header("Content-Type", "application/json")
            .json(&body)
            .send()
            .await
        {
            Ok(r) => r,
            Err(e) => return format!("Sidecar unavailable: {}", e),
        };
        let text = match resp.text().await {
            Ok(t) => t,
            Err(e) => return format!("Read error: {}", e),
        };
        match serde_json::from_str::<serde_json::Value>(&text) {
            Ok(val) => {
                if val["success"].as_bool().unwrap_or(false) {
                    val["result"].as_str().unwrap_or("").to_string()
                } else {
                    val["error"]
                        .as_str()
                        .unwrap_or("Tool execution failed")
                        .to_string()
                }
            }
            Err(_) => text,
        }
    }
}

/// Wire up all native tool registrations across submodules.
fn register_native_tools(registry: &mut ToolRegistry, project_root: &str) {
    fs::register(registry, project_root);
    kb::register(registry, project_root);
    document::register(registry, project_root);
    molecule::register(registry, project_root);
    literature::register(registry, project_root);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tool_registration() {
        let executor = ToolExecutor::new("http://localhost:18792", "/tmp/test");
        // native + sidecar
        let tools = executor.registry.list();
        assert!(tools.len() >= 15);
        assert!(executor.registry.get("grep_search").is_some());
        assert!(executor.registry.get("search_knowledge_base").is_some());
    }

    #[test]
    fn test_tool_executor_defaults() {
        let executor = ToolExecutor::new("http://localhost:18792", "/tmp/test");
        assert!(executor.kb.is_none());
        assert!(executor.tree_index.is_none());
        assert!(executor.summary.is_none());
    }
}
