//! Helpers for mapping pipeline extracted entries to molecule records.

use crate::core::helpers::{generate_uuid, sha256_text};
use crate::core::molecule::molecule_store::MoleculeRecord;
use crate::parsers::doc_types::{ActivityEntry, CompoundEntry};

/// CompoundEntry → MoleculeRecord 映射（三层分离）
///
/// 将 LLM 提取的 E-SMILES 分离为：
/// - `smiles`: 纯净 SMILES（Layer 1，事实来源）
/// - `esmiles`: 原始 E-SMILES（Layer 2，可选，仅当含标签时）
/// - `semantic_tags`: 标签元数据（Layer 2，JSON）
pub fn compound_entry_to_record(
    compound: &CompoundEntry,
    source_doc: &str,
    source_type: &str,
) -> Option<MoleculeRecord> {
    let raw_esmiles = compound.esmiles.as_ref()?;
    if raw_esmiles.is_empty() {
        return None;
    }

    // 三层分离
    let (clean_smiles, esmiles, semantic_tags) =
        crate::parsers::chem::chem_validate::separate_esmiles_layers(raw_esmiles);

    // 用纯净 SMILES 作为 mol_id 的一部分（保证相同分子不同标签产生相同 ID）
    let mol_id = if compound.name.is_empty() {
        generate_uuid()
    } else {
        sha256_text(&format!("{}|{}", compound.name, clean_smiles))
    };

    let status = match compound.confidence.as_str() {
        "high" => "confirmed".to_string(),
        _ => "pending".to_string(),
    };

    let mut labels = Vec::new();
    if let Some(ref cat) = compound.category {
        labels.push(cat.clone());
    }

    let mut properties = serde_json::json!({});
    if let Some(ref props) = compound.physicochemical_props {
        let mut map = serde_json::Map::new();
        for p in props {
            map.insert(
                p.property_type.clone(),
                serde_json::json!({
                    "value": p.value,
                    "unit": p.unit,
                    "source_quote": p.source_quote,
                    "confidence": p.confidence,
                }),
            );
        }
        properties = serde_json::Value::Object(map);
    }

    let mut notes = format!(
        "Auto-extracted from {}. Confidence: {}.",
        source_type, compound.confidence
    );
    if let Some(ref reason) = compound.uncertainty_reason {
        notes.push_str(&format!(" Uncertainty: {}.", reason));
    }

    let related_image_paths: Vec<String> = compound.related_images.clone().unwrap_or_default();
    let vlm_verified_esmiles = compound.vlm_verified_esmiles.clone();

    if vlm_verified_esmiles.is_some() {
        notes.push_str(" VLM verified.");
    }

    Some(MoleculeRecord {
        mol_id,
        smiles: clean_smiles, // Layer 1: 纯净 SMILES
        esmiles,              // Layer 2: 原始 E-SMILES（仅含标签时）
        semantic_tags,        // Layer 2: 语义标签 JSON
        name: compound.name.clone(),
        source_doc: source_doc.to_string(),
        activity: None,
        activity_type: String::new(),
        units: "nM".to_string(),
        source_type: source_type.to_string(),
        status: status.to_string(),
        properties,
        labels,
        notes,
        created_at: None,
        related_image_paths,
        vlm_verified_esmiles,
        vlm_confidence: 0.0,
    })
}

/// ActivityEntry → MoleculeRecord 映射
pub fn activity_entry_to_record(
    activity: &ActivityEntry,
    source_doc: &str,
    source_type: &str,
) -> MoleculeRecord {
    let mut record = MoleculeRecord::new(&generate_uuid(), "");
    record.name = activity.compound.clone();
    record.source_doc = source_doc.to_string();
    record.activity = Some(activity.value);
    record.activity_type = activity.activity_type.clone();
    record.units = activity.units.clone();
    record.source_type = format!("{}_activity", source_type);
    record.status = match activity.confidence.as_str() {
        "high" => "confirmed".to_string(),
        _ => "pending".to_string(),
    };
    record.notes = format!(
        "Activity: {} {} {}. Source ref: {}. Confidence: {}.",
        activity.activity_type,
        activity.value,
        activity.units,
        activity.source_ref,
        activity.confidence
    );
    record
}
