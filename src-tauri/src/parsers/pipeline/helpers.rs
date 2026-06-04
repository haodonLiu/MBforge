use crate::core::helpers::{generate_uuid, sha256_text};
use crate::core::molecule_store::MoleculeRecord;
use crate::parsers::doc_types::{ActivityEntry, CompoundEntry, PhysicochemicalProperty};

/// CompoundEntry → MoleculeRecord 映射
pub fn compound_entry_to_record(
    compound: &CompoundEntry,
    source_doc: &str,
    source_type: &str,
) -> Option<MoleculeRecord> {
    let esmiles = compound.esmiles.as_ref()?;
    if esmiles.is_empty() {
        return None;
    }
    let mol_id = if compound.name.is_empty() {
        generate_uuid()
    } else {
        sha256_text(&format!("{}|{}", compound.name, esmiles))
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
    if let Some(ref vlm) = compound.vlm_verified_esmiles {
        notes.push_str(&format!(" VLM verified: {}.", vlm));
    }
    if let Some(ref reason) = compound.uncertainty_reason {
        notes.push_str(&format!(" Uncertainty: {}.", reason));
    }
    Some(MoleculeRecord {
        mol_id,
        smiles: esmiles.clone(),
        esmiles: Some(esmiles.clone()),
        semantic_tags: None,
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

/// 提取指定 section 的文本（基于 section name 尝试搜索）
pub fn extract_section_text(raw_text: &str, section_name: &str) -> String {
    // 简单启发式：在文本中搜索 section 标题附近的段落
    let markers = [
        &format!("{}", section_name),
        &format!("# {}", section_name),
        &format!("## {}", section_name),
        &format!("【{}】", section_name),
    ];

    for marker in &markers {
        if let Some(pos) = raw_text.find(marker.as_str()) {
            let start = pos.saturating_sub(50);
            let end = (pos + 10000).min(raw_text.len());
            return raw_text[start..end].to_string();
        }
    }

    // Fallback: 取全文（限制前 10000 字符）
    raw_text.chars().take(10000).collect()
}
