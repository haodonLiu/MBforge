//! GESim Tauri commands — graph-based molecular similarity
//!
//! Exposes the Rust-native GESim implementation to the frontend via Tauri IPC.

use crate::core::chem::gesim;
use chematic_smiles::parse;

/// Tauri command: compute GESim similarity between two SMILES/E-SMILES strings.
///
/// Returns the **logistic-scaled** similarity (default, matching original Python).
/// Use [`gesim_similarity_raw_cmd`] if you need the raw `1 - QJS` value.
#[tauri::command]
pub fn gesim_similarity_cmd(smiles1: String, smiles2: String) -> Result<f64, String> {
    let mol1 = parse(&smiles1).map_err(|e| format!("SMILES parse failed (1): {:?}", e))?;
    let mol2 = parse(&smiles2).map_err(|e| format!("SMILES parse failed (2): {:?}", e))?;
    Ok(gesim::similarity(&mol1, &mol2))
}

/// Tauri command: compute raw GESim similarity (no logistic scaler).
#[tauri::command]
pub fn gesim_similarity_raw_cmd(smiles1: String, smiles2: String) -> Result<f64, String> {
    let mol1 = parse(&smiles1).map_err(|e| format!("SMILES parse failed (1): {:?}", e))?;
    let mol2 = parse(&smiles2).map_err(|e| format!("SMILES parse failed (2): {:?}", e))?;
    Ok(gesim::similarity_raw(&mol1, &mol2))
}

/// Tauri command: return the atom-level match mapping between two molecules.
///
/// Returns a JSON-friendly structure:
/// ```json
/// {
///   "mapping1": [0, 1, null, 2],
///   "mapping2": [0, 1, 2, null]
/// }
/// ```
/// where `mapping1[i] = j` means atom i in mol1 matches atom j in mol2.
#[tauri::command]
pub fn gesim_match_mapping_cmd(
    smiles1: String,
    smiles2: String,
) -> Result<GesimMappingResult, String> {
    let mol1 = parse(&smiles1).map_err(|e| format!("SMILES parse failed (1): {:?}", e))?;
    let mol2 = parse(&smiles2).map_err(|e| format!("SMILES parse failed (2): {:?}", e))?;
    let (m1, m2) = gesim::match_mapping(&mol1, &mol2);
    Ok(GesimMappingResult {
        mapping1: m1
            .into_iter()
            .map(|o| o.map(|v| v as i32).unwrap_or(-1))
            .collect::<Vec<i32>>(),
        mapping2: m2
            .into_iter()
            .map(|o| o.map(|v| v as i32).unwrap_or(-1))
            .collect::<Vec<i32>>(),
    })
}

/// Serializable result for [`gesim_match_mapping_cmd`].
#[derive(Debug, Clone, serde::Serialize)]
pub struct GesimMappingResult {
    pub mapping1: Vec<i32>,
    pub mapping2: Vec<i32>,
}
