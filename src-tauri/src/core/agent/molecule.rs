//! Molecule analysis + Markush overlap tools.

pub async fn native_molecule_analysis(
    root: &str,
    action: &str,
    params: serde_json::Value,
) -> String {
    let project_root = std::path::Path::new(root);
    if !project_root.join(".mbforge").join("molecules.db").exists() {
        return "No molecule database found".to_string();
    }
    match crate::core::molecule::molecule_engine::MoleculeEngine::new(project_root).await {
        Ok(engine) => match engine.analyze(action, params).await {
            Ok(result) => {
                serde_json::to_string(&result).unwrap_or_else(|e| format!("Serialize error: {}", e))
            }
            Err(e) => format!("Analysis error: {}", e),
        },
        Err(e) => format!("Engine init error: {}", e),
    }
}
