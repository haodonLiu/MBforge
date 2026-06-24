//! Image extraction and persistence service for the PDF processing pipeline.

use std::path::Path;

use tokio::task::spawn_blocking;

use mbforge_infra::config::constants::REPORTS_DIR;
use crate::pdf::images::{extract_images_from_pdf, ExtractedImage};
use crate::pipeline::error::{ExtractError, PipelineError};
use crate::pipeline::models::extracted::ImageRef;

/// Service responsible for extracting embedded images from PDFs and copying
/// them into the project's report output directory.
pub struct ImageService;

impl ImageService {
    /// Creates a new [`ImageService`].
    pub fn new() -> Self {
        Self
    }

    /// Extracts embedded images from a PDF source into `tmp_dir`.
    ///
    /// The actual extraction runs on Tokio's blocking thread pool because the
    /// underlying `lopdf` operations are synchronous and may perform heavy IO.
    ///
    /// `pdf_path` and `tmp_dir` are caller-provided operational paths (the
    /// source PDF and a temporary working directory). They are not
    /// user-controlled relative paths, so explicit `assert_within_root`
    /// validation is left to the caller rather than enforced here.
    ///
    /// # Errors
    ///
    /// Returns `PipelineError::Extract(ExtractError::ImagePersistFailed)` when
    /// the extraction task fails to complete or the underlying parser reports
    /// an error.
    pub async fn extract_embedded_images(
        &self,
        pdf_path: &Path,
        tmp_dir: &Path,
    ) -> Result<Vec<ExtractedImage>, PipelineError> {
        let filename = pdf_path
            .file_name()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_else(|| "unknown.pdf".to_string());
        let pdf_path = pdf_path.to_path_buf();
        let tmp_dir = tmp_dir.to_path_buf();

        spawn_blocking(move || {
            extract_images_from_pdf(pdf_path.to_string_lossy().as_ref(), &tmp_dir, 50, 5)
        })
        .await
        .map_err(|e| {
            PipelineError::Extract(ExtractError::ImagePersistFailed {
                filename: filename.clone(),
                detail: format!("extraction task join failed: {}", e),
            })
        })?
        .map_err(|e| {
            PipelineError::Extract(ExtractError::ImagePersistFailed {
                filename: filename.clone(),
                detail: e,
            })
        })
    }

    /// Copies images extracted from a PDF into the project's figures directory.
    ///
    /// Images are placed under `<project_root>/reports/figures/<doc_slug>/`.
    /// The returned [`ImageRef`]s have their `rel_path` set relative to
    /// `project_root`.
    ///
    /// Image filenames are sanitized before being joined to the media directory.
    /// Directory-creation or copy failures are logged and the affected image is
    /// skipped rather than failing the whole operation.
    pub fn persist_extracted_images(
        &self,
        source_path: &Path,
        project_root: &Path,
        extracted: &[ExtractedImage],
    ) -> Vec<ImageRef> {
        let doc_slug = source_path
            .file_stem()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_else(|| "unknown".to_string());
        let doc_slug = sanitize_slug(&doc_slug);
        let root_str = project_root.to_string_lossy().to_string();

        let media_dir = project_root
            .join(REPORTS_DIR)
            .join("figures")
            .join(&doc_slug);
        let media_dir =
            match mbforge_infra::helpers::assert_within_root_allow_missing(&root_str, &media_dir) {
                Ok(p) => p,
                Err(e) => {
                    log::warn!("image media_dir escapes project root: {}", e);
                    return Vec::new();
                }
            };

        if let Err(e) = std::fs::create_dir_all(&media_dir) {
            log::error!("failed to create figures directory: {}", e);
            return Vec::new();
        }

        extracted
            .iter()
            .filter_map(|img| {
                let filename = sanitize_filename(&img.filename);
                let dest = media_dir.join(&filename);
                let dest = match mbforge_infra::helpers::assert_within_root_allow_missing(
                    &root_str, &dest,
                ) {
                    Ok(p) => p,
                    Err(e) => {
                        log::warn!("image destination escapes project root: {}", e);
                        return None;
                    }
                };

                if let Err(e) = std::fs::copy(&img.path, &dest) {
                    log::warn!(
                        "failed to copy image {} to {}: {}",
                        img.path.display(),
                        dest.display(),
                        e
                    );
                    return None;
                }

                let rel_path = match dest.strip_prefix(project_root) {
                    Ok(p) => Some(p.to_string_lossy().to_string()),
                    Err(e) => {
                        log::warn!("failed to relativise image path {}: {}", dest.display(), e);
                        None
                    }
                };

                Some(ImageRef {
                    filename,
                    page: img.page,
                    region: None,
                    description: None,
                    esmiles: None,
                    rel_path,
                })
            })
            .collect()
    }

    /// Copies backend-produced images into a backend-specific subdirectory.
    ///
    /// Images are placed under
    /// `<project_root>/reports/figures/<doc_slug>/<backend_name>/` and their
    /// `rel_path` values are updated to point to the new location.
    ///
    /// Image filenames are sanitized before being joined to the media directory.
    /// Both the resolved source path and the destination path are validated to
    /// stay within `project_root`; failures are logged and the affected image is
    /// skipped.
    pub fn persist_backend_images(
        &self,
        project_root: &Path,
        images: &[ImageRef],
        backend_name: &str,
        doc_slug: &str,
    ) -> Vec<ImageRef> {
        let doc_slug = sanitize_slug(doc_slug);
        let backend_name = sanitize_slug(backend_name);
        let root_str = project_root.to_string_lossy().to_string();

        let media_dir = project_root
            .join(REPORTS_DIR)
            .join("figures")
            .join(&doc_slug)
            .join(&backend_name);
        let media_dir =
            match mbforge_infra::helpers::assert_within_root_allow_missing(&root_str, &media_dir) {
                Ok(p) => p,
                Err(e) => {
                    log::warn!("image media_dir escapes project root: {}", e);
                    return Vec::new();
                }
            };

        if let Err(e) = std::fs::create_dir_all(&media_dir) {
            log::error!("failed to create backend figures directory: {}", e);
            return Vec::new();
        }

        images
            .iter()
            .filter_map(|img| {
                let filename = sanitize_filename(&img.filename);
                let source = match img.rel_path.as_ref() {
                    Some(rel) => {
                        let full = project_root.join(rel);
                        match mbforge_infra::helpers::assert_within_root_allow_missing(
                            &root_str, &full,
                        ) {
                            Ok(p) => p,
                            Err(e) => {
                                log::warn!("image rel_path escapes project root: {}", e);
                                return None;
                            }
                        }
                    }
                    None => {
                        let full = project_root
                            .join(REPORTS_DIR)
                            .join("figures")
                            .join(&doc_slug)
                            .join(&filename);
                        match mbforge_infra::helpers::assert_within_root_allow_missing(
                            &root_str, &full,
                        ) {
                            Ok(p) => p,
                            Err(e) => {
                                log::warn!("image source path escapes project root: {}", e);
                                return None;
                            }
                        }
                    }
                };

                let dest = media_dir.join(&filename);
                let dest = match mbforge_infra::helpers::assert_within_root_allow_missing(
                    &root_str, &dest,
                ) {
                    Ok(p) => p,
                    Err(e) => {
                        log::warn!("image destination escapes project root: {}", e);
                        return None;
                    }
                };

                if let Err(e) = std::fs::copy(&source, &dest) {
                    log::warn!(
                        "failed to copy backend image {} to {}: {}",
                        source.display(),
                        dest.display(),
                        e
                    );
                    return None;
                }

                let rel_path = match dest.strip_prefix(project_root) {
                    Ok(p) => Some(p.to_string_lossy().to_string()),
                    Err(e) => {
                        log::warn!("failed to relativise image path {}: {}", dest.display(), e);
                        None
                    }
                };

                Some(ImageRef {
                    filename,
                    page: img.page,
                    region: img.region.clone(),
                    description: img.description.clone(),
                    esmiles: img.esmiles.clone(),
                    rel_path,
                })
            })
            .collect()
    }
}

impl Default for ImageService {
    fn default() -> Self {
        Self::new()
    }
}

/// Sanitizes a path slug so it cannot contain directory separators or parent
/// directory references.
fn sanitize_slug(value: &str) -> String {
    value.replace(['/', '\\'], "_").replace("..", "_")
}

/// Sanitizes a filename so it cannot contain directory separators or parent
/// directory references.
fn sanitize_filename(name: &str) -> String {
    name.replace(['/', '\\'], "_").replace("..", "_")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitize_slug_replaces_separators_and_parent_refs() {
        assert_eq!(sanitize_slug("foo/bar"), "foo_bar");
        assert_eq!(sanitize_slug("foo\\bar"), "foo_bar");
        assert_eq!(sanitize_slug("../foo"), "__foo");
        assert_eq!(sanitize_slug("foo..bar"), "foo_bar");
    }
}
