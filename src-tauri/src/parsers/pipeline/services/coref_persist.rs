//! Coref 持久化 service
//!
//! 调用 sidecar `/api/v1/moldet/coref` 检测图内分子 + label，
//! 写入 `knowledge_base.db` 的 `figure_labels` 和 `coref_predictions` 表。
//!
//! 决策依据 (coref 增强设计 12 决策):
//! - 6C: figure_labels + coref_predictions 表已建
//! - 7A: 先存原始 + 几何兜底 (source='geometric')，人工可改 (P2: LLM 精炼)
//! - 8C: conf > 0.3 才存
//! - 12A: 几何配对兜底 (即使 LLM 失败也有数据)

use std::path::Path;

use crate::core::config::constants::sidecar_url;
use crate::core::document::knowledge_base::{CorefPrediction, FigureLabel, KnowledgeBase};
use crate::core::error::{AppError, AppResult, ErrorCode};
use crate::parsers::chem::vlm_chem;

/// Coref 持久化结果（单页）
#[derive(Debug, Clone, Default)]
pub struct CorefPersistResult {
    pub page: i64,
    pub labels_written: usize,
    pub predictions_written: usize,
    pub error: Option<String>,
}

/// 持久化 service — 写入 KB
pub struct CorefPersistService {
    sidecar_url: String,
}

impl CorefPersistService {
    pub fn new() -> Self {
        Self {
            sidecar_url: sidecar_url(),
        }
    }

    pub fn with_sidecar_url(sidecar_url: String) -> Self {
        Self { sidecar_url }
    }

    /// 对单张图跑 coref 检测并写入 KB
    ///
    /// 流程:
    /// 1. HTTP GET sidecar `/api/v1/moldet/coref` 拿 CorefResult
    /// 2. 解析为 FigureLabel + CorefPrediction
    /// 3. 调 `kb.insert_figure_labels` + `kb.upsert_coref_predictions`
    pub async fn persist_for_image(
        &self,
        kb: &KnowledgeBase,
        doc_id: &str,
        page: i64,
        image_path: &Path,
        use_molscribe: bool,
        use_ocr: bool,
    ) -> AppResult<CorefPersistResult> {
        let path_str = image_path.to_string_lossy().to_string();

        // 1. 调 sidecar
        let coref = vlm_chem::detect_coref(
            &path_str,
            &self.sidecar_url,
            use_molscribe,
            use_ocr,
        )
        .await
        .map_err(|e| AppError {
            code: ErrorCode::Unknown,
            message: format!("coref sidecar call failed: {e}"),
            path: Some(path_str.clone()),
            suggestion: None,
        })?;

        // 2. 解析 → records
        let labels: Vec<FigureLabel> = coref
            .bboxes
            .iter()
            .filter(|b| b.category_id == 3 && b.ocr_conf_or_default() > 0.3)
            .map(|b| FigureLabel {
                id: 0, // auto-increment
                doc_id: doc_id.to_string(),
                page,
                label_bbox: b.bbox.to_vec(),
                label_text: b.text.clone().unwrap_or_default(),
                ocr_conf: b.ocr_conf_or_default(),
                image_path: Some(path_str.clone()),
            })
            .collect();

        let predictions: Vec<CorefPrediction> = coref
            .corefs
            .iter()
            .filter_map(|&(mol_idx, idt_idx)| {
                let mol_bbox = coref.bboxes.get(mol_idx)?;
                let idt_bbox = coref.bboxes.get(idt_idx)?;
                if mol_bbox.category_id != 1 {
                    return None;
                }
                Some(CorefPrediction {
                    id: 0,
                    doc_id: doc_id.to_string(),
                    page,
                    mol_smiles: mol_bbox.smiles.clone(),
                    mol_bbox: Some(mol_bbox.bbox.to_vec()),
                    mol_conf: Some(mol_bbox.score),
                    label_id: None,
                    label_text: idt_bbox.text.clone(),
                    label_bbox: Some(idt_bbox.bbox.to_vec()),
                    confidence: (mol_bbox.score + idt_bbox.ocr_conf_or_default()) / 2.0,
                    source: "geometric".to_string(),
                    is_confirmed: false,
                })
            })
            .collect();

        // 3. 写 KB
        let label_tuples: Vec<(Vec<f64>, String, f64, Option<String>)> = labels
            .iter()
            .map(|l| (l.label_bbox.clone(), l.label_text.clone(), l.ocr_conf, l.image_path.clone()))
            .collect();
        let labels_written = kb.insert_figure_labels(doc_id, page, &label_tuples)?;

        // 用 page 局部 labels 找 id 对应 label_id
        let mut predictions_with_label_id = Vec::new();
        let stored_labels = kb.get_figure_labels(doc_id, page)?;
        for mut p in predictions.into_iter() {
            if let Some(label_text) = &p.label_text {
                if let Some(label_bbox) = &p.label_bbox {
                    if let Some(stored) = stored_labels.iter().find(|l| {
                        &l.label_text == label_text
                            && l.label_bbox.len() == label_bbox.len()
                            && l
                                .label_bbox
                                .iter()
                                .zip(label_bbox.iter())
                                .all(|(a, b)| (a - b).abs() < 1e-3)
                    }) {
                        p.label_id = Some(stored.id);
                    }
                }
            }
            predictions_with_label_id.push(p);
        }
        let predictions_written =
            kb.upsert_coref_predictions(doc_id, page, &predictions_with_label_id)?;

        Ok(CorefPersistResult {
            page,
            labels_written,
            predictions_written,
            error: None,
        })
    }
}

impl Default for CorefPersistService {
    fn default() -> Self {
        Self::new()
    }
}

// ─── CorefBbox 扩展：兼容可能的字段名变化 ───────────────────────

trait CorefBboxExt {
    fn ocr_conf_or_default(&self) -> f64;
}

impl CorefBboxExt for vlm_chem::CorefBbox {
    fn ocr_conf_or_default(&self) -> f64 {
        // 优先 score（MDetv2 输出），若无则 0
        self.score
    }
}
