//! Molecule analysis + Markush overlap tools.

use std::collections::HashMap;

use super::super::markush;
use super::super::tools::{ToolInfo, ToolRegistry};

/// Register all molecule/markush native tools.
pub fn register(registry: &mut ToolRegistry, _project_root: &str) {
    // check_markush_overlap — E-SMILES Markush 专利范围检查
    registry.register_with_fn(
        ToolInfo::new("check_markush_overlap", "检查一个分子（SMILES）是否落在一个 Markush 专利通式（E-SMILES）的范围内", {
            let mut p: HashMap<String, serde_json::Value> = HashMap::new();
            p.insert("esmiles".into(), serde_json::json!({"type": "string", "description": "E-SMILES Markush pattern (e.g. *c1ccccc1<sep><a>0:R[1]</a>)"}));
            p.insert("query_smiles".into(), serde_json::json!({"type": "string", "description": "Query molecule SMILES (e.g. Fc1ccccc1)"}));
            p.insert("rgroup_text".into(), serde_json::json!({"type": "string", "description": "Optional patent text defining R-groups (e.g. R[1] is halogen)"}));
            p
        }),
        Box::new(|args| {
            let esmiles = args["esmiles"].as_str().unwrap_or("");
            let query = args["query_smiles"].as_str().unwrap_or("");
            let rtext = args.get("rgroup_text").and_then(|v| v.as_str());
            if esmiles.is_empty() || query.is_empty() {
                return serde_json::json!({"error": "esmiles and query_smiles are required"}).to_string();
            }
            let result = markush::analyze_markush_coverage(esmiles, query, rtext);
            serde_json::to_string(&result).unwrap_or_else(|e| format!("Serialization error: {}", e))
        }),
    );

    // molecule_analysis — 统一分子分析入口
    let root = _project_root.to_string();
    registry.register_with_fn(
        ToolInfo::new("molecule_analysis", "分子数据库统一分析入口：列表、搜索、SAR、Markush、聚类、去重等", {
            let mut p = HashMap::new();
            p.insert("action".into(), serde_json::json!({"type": "string", "description": "操作类型: list | search_by_smiles | search_text | get_stats | get_relation_stats | scaffold_profile | find_analogs | find_activity_cliffs | check_markush | list_clusters | dedup_batch"}));
            p.insert("params".into(), serde_json::json!({"type": "object", "description": "操作对应的参数对象"}));
            p
        }),
        Box::new(move |args| {
            let action = args["action"].as_str().unwrap_or("");
            let params = args["params"].clone();
            native_molecule_analysis(&root, action, params)
        }),
    );
}

fn native_molecule_analysis(
    root: &str,
    action: &str,
    params: serde_json::Value,
) -> String {
    let project_root = std::path::Path::new(root);
    if !project_root.join(".mbforge").join("molecules.db").exists() {
        return "No molecule database found".to_string();
    }
    match super::super::molecule::molecule_engine::MoleculeEngine::new(project_root) {
        Ok(engine) => match engine.analyze(action, params) {
            Ok(result) => serde_json::to_string(&result)
                .unwrap_or_else(|e| format!("Serialize error: {}", e)),
            Err(e) => format!("Analysis error: {}", e),
        },
        Err(e) => format!("Engine init error: {}", e),
    }
}
