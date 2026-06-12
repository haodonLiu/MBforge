//! Agent tool implementations for the rig-core agent stack.
//!
//! Defines 16 of the 25 tools the MBForge agent uses, all wired with the
//! `#[derive(Deserialize, JsonSchema)]` + `impl Tool` pattern so rig-core can
//! introspect JSON Schema for LLM tool selection. The 9 literature tools
//! (`arxiv_*` / `pmc_*`) live next door in `arxiv_rig.rs` and are assembled
//! together with these 16 by `rig_adapter::assemble_rig_tool_vec`.
//!
//! rustc's dead_code analysis can't see through the macro expansion in
//! `assemble_rig_tool_vec!`, so cross-module tool structs report "never
//! constructed" even though they ARE registered at runtime. Suppress at the
//! module level and document the call site.
//!
//! Categories covered here:
//! - File system  (grep_search, list_files, read_file, get_project_info, glob_search)
//! - Knowledge base  (search_knowledge_base, get_document_structure, get_document_pages)
//! - Document access  (read_document_abstract / overview / detail, list_documents,
//!   get_document_summary, find_documents)
//! - Molecule  (check_markush_overlap, molecule_analysis)
//!
//! Each tool follows the same shape:
//!   - A struct `<Name>Tool { project_root: String }` (or unit struct for
//!     stateless tools like `CheckMarkushTool`)
//!   - An `<Name>Args` struct with `#[derive(Deserialize, JsonSchema)]` for
//!     LLM-friendly JSON Schema generation
//!   - An `impl Tool for <Name>Tool` block that dispatches to a function
//!     in `core::document::*` / `core::molecule::*` / `core::chem::markush` /
//!     `core::agent::arxiv`
//!
//! To add a new tool: declare the struct + Args + impl, then push one
//! `Box::new(...)` line in `rig_adapter::assemble_rig_tool_vec`. No other
//! wiring is needed — the agent picks it up automatically.

// Tool structs / new() / Args are constructed by the
// `assemble_rig_tool_vec!` macro in `rig_adapter.rs`; rustc's dead_code
// analysis can't follow macro_rules! expansion across modules, so we
// suppress the false-positive "never constructed" / "never used" warnings
// at module level. The wiring is real — see rig_adapter::assemble_rig_tool_vec.
#![allow(dead_code)]

use rig_core::completion::ToolDefinition;
use rig_core::schemars::JsonSchema;
use rig_core::tool::{Tool, ToolError};
use serde::Deserialize;
use super::document as document_src;
use super::fs as fs_src;
use super::kb as kb_src;
use super::molecule as molecule_src;
// ============================================================================
// File-system tools (grep / list / read / project info / glob)
// ============================================================================

/// `grep_search` — ripgrep-level regex search across the project.
#[derive(Deserialize, JsonSchema)]
pub struct GrepSearchArgs {
    /// regex pattern to search for
    pub pattern: String,
    /// subdirectory relative to project root; empty = whole project
    #[serde(default)]
    pub path: String,
    /// max results to return (default 20)
    #[serde(default)]
    pub max_results: Option<u64>,
}

#[derive(Clone)]
pub struct GrepSearchTool {
    pub project_root: String,
}

impl GrepSearchTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for GrepSearchTool {
    const NAME: &'static str = "grep_search";
    type Error = ToolError;
    type Args = GrepSearchArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(GrepSearchArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "在项目文件中正则搜索内容（ripgrep 级性能）".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        let max_results = args.max_results.unwrap_or(20) as usize;
        Ok(fs_src::native_grep_search(
            &self.project_root,
            &args.pattern,
            &args.path,
            max_results,
        ))
    }
}

/// `list_files` — list project files (respects .gitignore).
#[derive(Deserialize, JsonSchema)]
pub struct ListFilesArgs {
    /// glob pattern (e.g. "**/*.rs"); empty = all files
    #[serde(default)]
    pub pattern: String,
    /// max results (default 50)
    #[serde(default)]
    pub max_results: Option<u64>,
}

#[derive(Clone)]
pub struct ListFilesTool {
    pub project_root: String,
}

impl ListFilesTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for ListFilesTool {
    const NAME: &'static str = "list_files";
    type Error = ToolError;
    type Args = ListFilesArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(ListFilesArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "列出项目中的文件（遵循 .gitignore）".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        let max_results = args.max_results.unwrap_or(50) as usize;
        Ok(fs_src::native_list_files(
            &self.project_root,
            &args.pattern,
            max_results,
        ))
    }
}

/// `read_file` — read a project file (truncated to max_lines).
#[derive(Deserialize, JsonSchema)]
pub struct ReadFileArgs {
    /// file path relative to project root
    pub path: String,
    /// max lines to read (default 200)
    #[serde(default)]
    pub max_lines: Option<u64>,
}

#[derive(Clone)]
pub struct ReadFileTool {
    pub project_root: String,
}

impl ReadFileTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for ReadFileTool {
    const NAME: &'static str = "read_file";
    type Error = ToolError;
    type Args = ReadFileArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(ReadFileArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "读取项目中指定文件的内容".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        let max_lines = args.max_lines.unwrap_or(200) as usize;
        Ok(fs_src::native_read_file(
            &self.project_root,
            &args.path,
            max_lines,
        ))
    }
}

/// `get_project_info` — get basic project statistics.
#[derive(Deserialize, JsonSchema)]
pub struct GetProjectInfoArgs {}

#[derive(Clone)]
pub struct GetProjectInfoTool {
    pub project_root: String,
}

impl GetProjectInfoTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for GetProjectInfoTool {
    const NAME: &'static str = "get_project_info";
    type Error = ToolError;
    type Args = GetProjectInfoArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(GetProjectInfoArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "获取项目基本信息（文件数、目录结构等）".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, _args: Self::Args) -> Result<Self::Output, Self::Error> {
        Ok(fs_src::native_get_project_info(&self.project_root))
    }
}

/// `glob_search` — search filenames by glob pattern.
#[derive(Deserialize, JsonSchema)]
pub struct GlobSearchArgs {
    /// glob pattern (e.g. "**/*.rs")
    pub pattern: String,
    /// max results (default 50)
    #[serde(default)]
    pub max_results: Option<u64>,
}

#[derive(Clone)]
pub struct GlobSearchTool {
    pub project_root: String,
}

impl GlobSearchTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for GlobSearchTool {
    const NAME: &'static str = "glob_search";
    type Error = ToolError;
    type Args = GlobSearchArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(GlobSearchArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "按 glob 模式搜索文件名".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        let max_results = args.max_results.unwrap_or(50) as usize;
        Ok(fs_src::native_glob_search(
            &self.project_root,
            &args.pattern,
            max_results,
        ))
    }
}

// ============================================================================
// Knowledge-base tools (semantic search / structure / pages)
// ============================================================================

/// `search_knowledge_base` — semantic search across the project's KB cache.
#[derive(Deserialize, JsonSchema)]
pub struct SearchKbArgs {
    /// search query
    pub query: String,
    /// max results to return (default 5)
    #[serde(default)]
    pub top_k: Option<u64>,
}

#[derive(Clone)]
pub struct SearchKbTool {
    pub project_root: String,
}

impl SearchKbTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for SearchKbTool {
    const NAME: &'static str = "search_knowledge_base";
    type Error = ToolError;
    type Args = SearchKbArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(SearchKbArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "搜索项目知识库，基于语义相似度检索相关文档内容".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        let top_k = args.top_k.unwrap_or(5) as usize;
        match kb_src::native_search_knowledge_base(&self.project_root, &args.query, top_k).await {
            Ok(results) => Ok(serde_json::to_string(&results)
                .unwrap_or_else(|e| format!("Serialize error: {}", e))),
            Err(e) => Ok(format!("Search error: {}", e)),
        }
    }
}

/// `get_document_structure` — heading tree of a document.
#[derive(Deserialize, JsonSchema)]
pub struct GetDocumentStructureArgs {
    pub doc_id: String,
}

#[derive(Clone)]
pub struct GetDocumentStructureTool {
    pub project_root: String,
}

impl GetDocumentStructureTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for GetDocumentStructureTool {
    const NAME: &'static str = "get_document_structure";
    type Error = ToolError;
    type Args = GetDocumentStructureArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(GetDocumentStructureArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "获取文档的章节结构树（heading 层级）".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        match kb_src::native_get_document_structure(&self.project_root, &args.doc_id) {
            Ok(tree) => Ok(serde_json::to_string(&tree)
                .unwrap_or_else(|e| format!("Serialize error: {}", e))),
            Err(e) => Ok(format!("Structure error: {}", e)),
        }
    }
}

/// `get_document_pages` — raw text of a document's pages.
#[derive(Deserialize, JsonSchema)]
pub struct GetDocumentPagesArgs {
    pub doc_id: String,
    /// 页码范围，如 "5-7,10"
    #[serde(default)]
    pub pages: String,
}

#[derive(Clone)]
pub struct GetDocumentPagesTool {
    pub project_root: String,
}

impl GetDocumentPagesTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for GetDocumentPagesTool {
    const NAME: &'static str = "get_document_pages";
    type Error = ToolError;
    type Args = GetDocumentPagesArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(GetDocumentPagesArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "按页码获取文档的原始文本内容".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        match kb_src::native_get_document_pages(&self.project_root, &args.doc_id, &args.pages) {
            Ok(p) => Ok(serde_json::to_string(&p)
                .unwrap_or_else(|e| format!("Serialize error: {}", e))),
            Err(e) => Ok(format!("Pages error: {}", e)),
        }
    }
}

// ============================================================================
// Molecule tools (Markush overlap / unified analysis)
// ============================================================================

/// `check_markush_overlap` — does a SMILES fall under a Markush patent's coverage?
#[derive(Deserialize, JsonSchema)]
pub struct CheckMarkushArgs {
    /// E-SMILES Markush pattern (e.g. *c1ccccc1<sep><a>0:R[1]</a>)
    pub esmiles: String,
    /// Query molecule SMILES (e.g. Fc1ccccc1)
    pub query_smiles: String,
    /// Optional patent text defining R-groups (e.g. R[1] is halogen)
    #[serde(default)]
    pub rgroup_text: Option<String>,
}

#[derive(Clone)]
pub struct CheckMarkushTool;

impl CheckMarkushTool {
    pub fn new() -> Self { Self }
}

impl Tool for CheckMarkushTool {
    const NAME: &'static str = "check_markush_overlap";
    type Error = ToolError;
    type Args = CheckMarkushArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(CheckMarkushArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "检查一个分子（SMILES）是否落在一个 Markush 专利通式（E-SMILES）的范围内".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        if args.esmiles.is_empty() || args.query_smiles.is_empty() {
            return Ok(serde_json::json!({"error": "esmiles and query_smiles are required"}).to_string());
        }
        let result = crate::core::chem::markush::analyze_markush_coverage(
            &args.esmiles, &args.query_smiles, args.rgroup_text.as_deref()
        );
        Ok(serde_json::to_string(&result)
            .unwrap_or_else(|e| format!("Serialization error: {}", e)))
    }
}

impl Default for CheckMarkushTool {
    fn default() -> Self { Self::new() }
}

/// `molecule_analysis` — unified molecule DB entry: list, search, SAR, Markush, cluster, dedup.
#[derive(Deserialize, JsonSchema)]
pub struct MoleculeAnalysisArgs {
    /// Operation: list | search_by_smiles | search_text | get_stats | get_relation_stats |
    ///             scaffold_profile | find_analogs | find_activity_cliffs | check_markush |
    ///             list_clusters | dedup_batch
    pub action: String,
    /// Params object (action-specific)
    pub params: serde_json::Value,
}

#[derive(Clone)]
pub struct MoleculeAnalysisTool {
    pub project_root: String,
}

impl MoleculeAnalysisTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for MoleculeAnalysisTool {
    const NAME: &'static str = "molecule_analysis";
    type Error = ToolError;
    type Args = MoleculeAnalysisArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(MoleculeAnalysisArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "分子数据库统一分析入口：列表、搜索、SAR、Markush、聚类、去重等".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        Ok(molecule_src::native_molecule_analysis(
            &self.project_root,
            &args.action,
            args.params,
        )
        .await)
    }
}

// ============================================================================
// Document access tools (L0/L1/L2 reads, list, summary, find)
// ============================================================================

/// `read_document_abstract` — read a document's L0 summary.
#[derive(Deserialize, JsonSchema)]
pub struct ReadDocumentAbstractArgs {
    pub doc_id: String,
}

#[derive(Clone)]
pub struct ReadDocumentAbstractTool {
    pub project_root: String,
}

impl ReadDocumentAbstractTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for ReadDocumentAbstractTool {
    const NAME: &'static str = "read_document_abstract";
    type Error = ToolError;
    type Args = ReadDocumentAbstractArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(ReadDocumentAbstractArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "读取文档的一句话摘要（L0）".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        Ok(document_src::native_read_document_abstract(&self.project_root, &args.doc_id))
    }
}

/// `read_document_overview` — read a document's L1 structured overview.
#[derive(Deserialize, JsonSchema)]
pub struct ReadDocumentOverviewArgs {
    pub doc_id: String,
}

#[derive(Clone)]
pub struct ReadDocumentOverviewTool {
    pub project_root: String,
}

impl ReadDocumentOverviewTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for ReadDocumentOverviewTool {
    const NAME: &'static str = "read_document_overview";
    type Error = ToolError;
    type Args = ReadDocumentOverviewArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(ReadDocumentOverviewArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "读取文档的结构化概览（L1）".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        Ok(document_src::native_read_document_overview(&self.project_root, &args.doc_id))
    }
}

/// `list_documents` — list all documents in the project.
#[derive(Deserialize, JsonSchema)]
pub struct ListDocumentsArgs {
    /// Optional document type filter
    #[serde(default)]
    pub doc_type: String,
}

#[derive(Clone)]
pub struct ListDocumentsTool {
    pub project_root: String,
}

impl ListDocumentsTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for ListDocumentsTool {
    const NAME: &'static str = "list_documents";
    type Error = ToolError;
    type Args = ListDocumentsArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(ListDocumentsArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "列出项目中的所有文档".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        Ok(document_src::native_list_documents(&self.project_root, &args.doc_type))
    }
}

/// `get_document_summary` — get a document's metadata summary.
#[derive(Deserialize, JsonSchema)]
pub struct GetDocumentSummaryArgs {
    pub doc_id: String,
}

#[derive(Clone)]
pub struct GetDocumentSummaryTool {
    pub project_root: String,
}

impl GetDocumentSummaryTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for GetDocumentSummaryTool {
    const NAME: &'static str = "get_document_summary";
    type Error = ToolError;
    type Args = GetDocumentSummaryArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(GetDocumentSummaryArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "获取文档的元数据摘要".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        Ok(document_src::native_get_document_summary(&self.project_root, &args.doc_id))
    }
}

/// `read_document_detail` — read a document's full L2 content.
#[derive(Deserialize, JsonSchema)]
pub struct ReadDocumentDetailArgs {
    pub doc_id: String,
    /// max characters to return (default 8000)
    #[serde(default)]
    pub max_chars: Option<u64>,
}

#[derive(Clone)]
pub struct ReadDocumentDetailTool {
    pub project_root: String,
}

impl ReadDocumentDetailTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for ReadDocumentDetailTool {
    const NAME: &'static str = "read_document_detail";
    type Error = ToolError;
    type Args = ReadDocumentDetailArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(ReadDocumentDetailArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "读取文档的完整内容块（L2）".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        let max_chars = args.max_chars.unwrap_or(8000) as usize;
        Ok(document_src::native_read_document_detail(&self.project_root, &args.doc_id, max_chars))
    }
}

/// `find_documents` — search documents by keyword.
#[derive(Deserialize, JsonSchema)]
pub struct FindDocumentsArgs {
    pub keyword: String,
    /// Optional document type filter
    #[serde(default)]
    pub doc_type: String,
    /// Max results (default 10)
    #[serde(default)]
    pub top_k: Option<u64>,
}

#[derive(Clone)]
pub struct FindDocumentsTool {
    pub project_root: String,
}

impl FindDocumentsTool {
    pub fn new(project_root: impl Into<String>) -> Self {
        Self { project_root: project_root.into() }
    }
}

impl Tool for FindDocumentsTool {
    const NAME: &'static str = "find_documents";
    type Error = ToolError;
    type Args = FindDocumentsArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(rig_core::schemars::schema_for!(FindDocumentsArgs))
            .expect("schema serialization");
        ToolDefinition {
            name: Self::NAME.to_string(),
            description: "按关键词查找文档（支持 L0 摘要过滤）".to_string(),
            parameters: schema,
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        let top_k = args.top_k.unwrap_or(10) as usize;
        Ok(document_src::native_find_documents(&self.project_root, &args.keyword, &args.doc_type, top_k))
    }
}
