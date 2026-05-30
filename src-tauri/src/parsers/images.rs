use lopdf::{Document, Object, ObjectId};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// An image extracted from a PDF page.
///
/// Port of the image extraction portion from
/// `src/mbforge/parsers/pdf_parser.py` (`_extract_limited_images`).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractedImage {
    pub page: usize,
    pub filename: String,
    pub path: PathBuf,
    pub width: u32,
    pub height: u32,
}

/// Extract embedded images from a PDF.
///
/// Iterates through PDF pages, finds image XObjects, and saves them
/// to `output_dir`. Skips images exceeding `max_size_mb`.
///
/// Port of `PDFParserPipeline._extract_limited_images` from
/// `src/mbforge/parsers/pdf_parser.py`.
pub fn extract_images_from_pdf(
    pdf_path: &str,
    output_dir: &Path,
    max_images: usize,
    max_size_mb: usize,
) -> Result<Vec<ExtractedImage>, String> {
    std::fs::create_dir_all(output_dir)
        .map_err(|e| format!("Failed to create output dir: {}", e))?;

    let doc = Document::load(pdf_path)
        .map_err(|e| format!("Failed to load PDF: {}", e))?;

    let max_bytes = (max_size_mb as u64) * 1024 * 1024;
    let mut images = Vec::new();

    let pages = doc.get_pages();
    for (page_idx, &page_id) in pages.keys().enumerate() {
        if images.len() >= max_images {
            break;
        }

        let image_objects = match find_page_images(&doc, page_id) {
            Ok(objs) => objs,
            Err(_) => continue,
        };

        for (img_idx, (obj_id, width, height)) in image_objects.iter().enumerate() {
            if images.len() >= max_images {
                break;
            }

            let (data, ext) = match extract_image_data(&doc, *obj_id) {
                Some(result) => result,
                None => continue,
            };

            if data.len() as u64 > max_bytes {
                continue;
            }

            let filename = format!("page_{}_img_{}.{}", page_idx + 1, img_idx + 1, ext);
            let img_path = output_dir.join(&filename);

            std::fs::write(&img_path, &data)
                .map_err(|e| format!("Failed to write image {}: {}", filename, e))?;

            images.push(ExtractedImage {
                page: page_idx + 1,
                filename,
                path: img_path,
                width: *width,
                height: *height,
            });
        }
    }

    Ok(images)
}

/// Find image XObjects on a given page.
fn find_page_images(
    doc: &Document,
    page_id: ObjectId,
) -> Result<Vec<(ObjectId, u32, u32)>, String> {
    let mut results = Vec::new();

    let resources = doc
        .get_page_resources(page_id)
        .map_err(|e| format!("Failed to get page resources: {}", e))?;

    // Navigate: resources → XObject → find Image subtypes
    let xobjects = match resources.get(b"XObject") {
        Some(Object::Dictionary(dict)) => dict,
        _ => return Ok(results),
    };

    for (name, obj_ref) in xobjects.iter() {
        let obj_id = match obj_ref {
            Object::Reference(id) => *id,
            _ => continue,
        };

        // Resolve the object to check its type
        let obj_data = match doc.get_object(obj_id) {
            Ok(obj) => obj,
            Err(_) => continue,
        };

        let dict = match obj_data {
            Object::Stream(stream) => &stream.dict,
            _ => continue,
        };

        // Check subtype is Image
        let subtype = dict
            .get(b"Subtype")
            .and_then(|o| o.as_name())
            .unwrap_or(b"");
        if subtype != b"Image" {
            continue;
        }

        let width = dict.get(b"Width").and_then(|o| o.as_i64()).unwrap_or(0) as u32;
        let height = dict
            .get(b"Height")
            .and_then(|o| o.as_i64())
            .unwrap_or(0) as u32;

        results.push((obj_id, width, height));
    }

    Ok(results)
}

/// Extract raw image data and determine file extension.
fn extract_image_data(doc: &Document, obj_id: ObjectId) -> Option<(Vec<u8>, &'static str)> {
    let stream = doc.get_object(obj_id).ok()?.as_stream().ok()?.clone();
    let data = &stream.content;

    let filters = stream.dict.get(b"Filter");
    let filter_name = filters.and_then(|f| match f {
        Object::Name(n) => Some(n.as_slice()),
        Object::Array(arr) => arr.first().and_then(|o| o.as_name()),
        _ => None,
    });

    match filter_name {
        Some(b"DCTDecode") => {
            // JPEG encoding
            Some((data.clone(), "jpg"))
        }
        Some(b"FlateDecode") => {
            // PNG-like (PNG header needs to be reconstructed) or raw
            // For simplicity, save as raw pixel data
            Some((data.clone(), "raw"))
        }
        Some(b"JPXDecode") => {
            // JPEG2000
            Some((data.clone(), "jp2"))
        }
        Some(b"CCITTFaxDecode") => {
            // CCITT fax encoding (TIFF)
            Some((data.clone(), "tiff"))
        }
        _ => {
            // No filter or unknown — try to save raw
            if !data.is_empty() {
                Some((data.clone(), "bin"))
            } else {
                None
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    /// Helper: create a minimal valid PDF with one embedded image.
    /// This creates a PDF with a minimal empty stream that has no actual
    /// image data, just to test the extraction flow won't crash.
    fn create_test_pdf(path: &Path) {
        use lopdf::*;

        let mut doc = Document::new();
        let page_id = doc.new_object_id();

        // Minimal content stream
        let content = Stream::new(Dictionary::new(), b"q 1 0 0 1 0 0 cm Q");
        let content_id = doc.add_object(content);

        let resources = Object::Dictionary({
            let mut dict = Dictionary::new();
            dict.set("XObject", Object::Dictionary(Dictionary::new()));
            dict
        });

        let page = Object::Dictionary({
            let mut dict = Dictionary::new();
            dict.set("Type", Object::Name(b"Page"));
            dict.set("MediaBox", Object::Array(vec![
                Object::Integer(0),
                Object::Integer(0),
                Object::Integer(612),
                Object::Integer(792),
            ]));
            dict.set("Contents", Object::Reference(content_id));
            dict.set("Resources", resources);
            dict
        });

        doc.objects.insert(page_id, page);

        let pages_id = doc.new_object_id();
        let pages = Object::Dictionary({
            let mut dict = Dictionary::new();
            dict.set("Type", Object::Name(b"Pages"));
            dict.set("Kids", Object::Array(vec![Object::Reference(page_id)]));
            dict.set("Count", Object::Integer(1));
            dict
        });
        doc.objects.insert(pages_id, pages);

        // Update page parent
        if let Some(obj) = doc.objects.get_mut(&page_id) {
            if let Object::Dictionary(ref mut dict) = obj {
                dict.set("Parent", Object::Reference(pages_id));
            }
        }

        // Root catalog
        let catalog_id = doc.new_object_id();
        let catalog = Object::Dictionary({
            let mut dict = Dictionary::new();
            dict.set("Type", Object::Name(b"Catalog"));
            dict.set("Pages", Object::Reference(pages_id));
            dict
        });
        doc.objects.insert(catalog_id, catalog);

        // Set trailer
        doc.trailer.set("Root", Object::Reference(catalog_id));

        doc.save(path).unwrap();
    }

    #[test]
    fn test_extract_images_no_images() {
        let tmp = TempDir::new().unwrap();
        let pdf_path = tmp.join("test.pdf");
        create_test_pdf(&pdf_path);
        let out_dir = tmp.join("images");

        let images =
            extract_images_from_pdf(pdf_path.to_str().unwrap(), &out_dir, 10, 2).unwrap();
        assert!(images.is_empty(), "No images expected");
    }

    #[test]
    fn test_extract_images_nonexistent_pdf() {
        let tmp = TempDir::new().unwrap();
        let result = extract_images_from_pdf(
            tmp.join("nonexistent.pdf").to_str().unwrap(),
            tmp.path(),
            10,
            2,
        );
        assert!(result.is_err(), "Should fail on nonexistent PDF");
    }
}
