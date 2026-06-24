//! MoleCode Tauri 命令

/// Tauri 命令：将 E-SMILES/SMILES 转换为 MoleCode (Mermaid graph text)
///
/// 用于前端渲染分子结构图，支持 Markush 缩写节点（{R1}、{Boc} 等）
#[tauri::command]
pub fn esmiles_to_molecode_cmd(esmiles: String, name: String) -> Result<String, String> {
    let result = mbforge_chem::molecode::esmiles_to_molecode(&esmiles, &name)?;
    Ok(result.mermaid)
}

/// Tauri 命令：计算分子理化性质描述符
///
/// 使用 chematic-chem 计算 MW、LogP、TPSA、HBA、HBD、可旋转键数、分子式
#[tauri::command]
pub fn chem_descriptors_cmd(
    smiles: String,
) -> Result<mbforge_chem::chem::ChemDescriptors, String> {
    mbforge_chem::chem::compute_descriptors(&smiles)
}
