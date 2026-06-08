use crate::core::helpers::{generate_uuid, sha256_text};
use crate::core::molecule::molecule_store::MoleculeRecord;
use crate::parsers::doc_types::{ActivityEntry, CompoundEntry, PhysicochemicalProperty};

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
        smiles: clean_smiles,      // Layer 1: 纯净 SMILES
        esmiles,                    // Layer 2: 原始 E-SMILES（仅含标签时）
        semantic_tags,              // Layer 2: 语义标签 JSON
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

/// 将分子实体信息嵌入到结构化文本中。
///
/// **占位接口**：当前仅返回原始文本。你需要实现此函数，将
/// `MoleculeRecord` 中的 `related_image_paths`、`vlm_verified_esmiles`、
/// 将分子信息以 MoleCode 格式嵌入到文本中。
///
/// 对每个分子记录，使用 E-SMILES（如有）或 SMILES 生成 MoleCode（Mermaid 图），
/// 追加到文本末尾。
///
/// # Arguments
/// * `text` - 原始结构化文本（Markdown）
/// * `records` - 提取到的分子实体列表
///
/// # Returns
/// 插入 MoleCode 后的文本。
pub fn embed_molecules_into_text(text: &str, records: &[MoleculeRecord]) -> String {
    if records.is_empty() {
        return text.to_string();
    }

    let mut result = String::with_capacity(text.len() + records.len() * 500);
    result.push_str(text);

    for rec in records {
        // 优先使用 E-SMILES（含语义标签），否则用 SMILES
        let smiles_input = rec.esmiles.as_deref().unwrap_or(&rec.smiles);
        if smiles_input.is_empty() {
            continue;
        }

        let name = if rec.name.is_empty() {
            "Molecule"
        } else {
            &rec.name
        };

        match crate::core::chem::molecode::esmiles_to_molecode(smiles_input, name) {
            Ok(mc) => {
                result.push_str("\n\n<!-- MoleCode: ");
                result.push_str(name);
                result.push_str(" -->\n```mermaid\n");
                result.push_str(&mc.mermaid);
                result.push_str("\n```\n");
            }
            Err(e) => {
                log::debug!(
                    "[embed_molecules] MoleCode generation failed for {}: {}",
                    name, e
                );
            }
        }
    }

    result
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
