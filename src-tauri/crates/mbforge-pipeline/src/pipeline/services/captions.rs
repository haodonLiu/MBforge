//! Image captioning service for the PDF processing pipeline.
//!
//! This service generates human-readable descriptions for document images
//! using a VLM-backed sidecar endpoint. Captions are cached on disk so that
//! repeated processing of the same document can avoid redundant model calls.
//! Images that are likely chemical structures are skipped because their
//! meaning is captured separately by the molecule extraction service.

use std::collections::HashMap;
use std::path::Path;

use crate::chem::vlm_chem::{
    describe_image_cached, is_likely_chemical_structure, ImageCaptionCache,
};
use crate::pipeline::error::{EnrichError, PipelineError};
use crate::pipeline::models::extracted::ImageRef;

/// Service that generates VLM captions for document images.
#[derive(Debug, Clone)]
pub struct ImageCaptionService {
    /// URL of the Python sidecar providing the VLM describe endpoint.
    pub sidecar_url: String,
}

impl ImageCaptionService {
    /// Creates a new [`ImageCaptionService`] pointing at the given sidecar URL.
    ///
    /// # Arguments
    /// - `sidecar_url`: Base URL of the Python sidecar (e.g. `http://127.0.0.1:18792`).
    pub fn new(sidecar_url: impl Into<String>) -> Self {
        Self {
            sidecar_url: sidecar_url.into(),
        }
    }

    /// Generates captions for the supplied images and mutates them in place.
    ///
    /// # Arguments
    /// - `images`: Mutable slice of image references. Successful captions are
    ///   written back to [`ImageRef::description`].
    /// - `project_root`: Project root directory used to resolve relative image
    ///   paths and persist the caption cache.
    ///
    /// # Returns
    /// A map from image filename to generated caption.
    pub async fn caption_images(
        &self,
        images: &mut [ImageRef],
        project_root: &Path,
    ) -> Result<HashMap<String, String>, PipelineError> {
        let mut cache = ImageCaptionCache::new(project_root);
        let prompt = "请详细描述这张科学文献图片的内容。如果是图表，请说明其中的关键数据和趋势；如果是分子结构图，请描述其骨架特征和官能团；如果是实验流程图，请概述主要步骤。用中文回答，不超过100字。";
        let mut result = HashMap::new();

        for img in images.iter_mut() {
            if is_likely_chemical_structure(&img.filename, img.region.as_deref()) {
                continue;
            }
            let Some(full_path) = Self::resolve_image_path(img, project_root) else {
                continue;
            };
            match describe_image_cached(&full_path, prompt, &self.sidecar_url, &mut cache).await {
                Ok(caption) => {
                    img.description = Some(caption.clone());
                    result.insert(img.filename.clone(), caption);
                }
                Err(e) => {
                    let err = PipelineError::Enrich(EnrichError::CaptionServiceFailed {
                        filename: img.filename.clone(),
                        detail: e,
                    });
                    if let Err(save_err) = cache.save() {
                        log::warn!("failed to save caption cache: {save_err}");
                    }
                    return Err(err);
                }
            }
        }

        cache.save().map_err(|e| {
            PipelineError::Enrich(EnrichError::CaptionServiceFailed {
                filename: "cache".into(),
                detail: e,
            })
        })?;

        Ok(result)
    }

    /// Resolves an image reference to an absolute file system path.
    ///
    /// Returns `None` if the image has no relative path, the resolved file
    /// does not exist, or the resolved path escapes `project_root`.
    fn resolve_image_path(img: &ImageRef, project_root: &Path) -> Option<String> {
        let rel = img.rel_path.as_ref()?;
        let full = project_root.join(rel);
        let full = mbforge_infra::helpers::assert_within_root_allow_missing(
            project_root.to_string_lossy().as_ref(),
            &full,
        )
        .ok()?;
        if full.exists() {
            Some(full.to_string_lossy().to_string())
        } else {
            None
        }
    }
}
