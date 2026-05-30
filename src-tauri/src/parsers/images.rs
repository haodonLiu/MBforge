use lopdf::{Document, Object, ObjectId};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// An image extracted from a PDF page.
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
    for (page_idx, (_, &page_id)) in pages.iter().enumerate() {
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

    let (resources_opt, _) = doc
        .get_page_resources(page_id)
        .map_err(|e| format!("Failed to get page resources: {}", e))?;

    let resources_dict = match resources_opt {
        Some(dict) => dict,
        None => return Ok(results),
    };

    let xobject_dict = match resolve_dict(resources_dict, b"XObject") {
        Some(dict) => dict,
        None => return Ok(results),
    };

    for (_name, obj_ref) in xobject_dict.iter() {
        let obj_id = match obj_ref {
            Object::Reference(id) => *id,
            _ => continue,
        };

        let obj_data = match doc.get_object(obj_id) {
            Ok(obj) => obj,
            Err(_) => continue,
        };

        let dict = match obj_data {
            Object::Stream(stream) => &stream.dict,
            _ => continue,
        };

        let subtype = dict.get(b"Subtype");
        match subtype {
            Ok(Object::Name(n)) if n == b"Image" => {}
            _ => continue,
        }

        let width = resolve_i64(dict, b"Width").unwrap_or(0) as u32;
        let height = resolve_i64(dict, b"Height").unwrap_or(0) as u32;

        results.push((obj_id, width, height));
    }

    Ok(results)
}

/// Extract raw image data and determine file extension.
fn extract_image_data(doc: &Document, obj_id: ObjectId) -> Option<(Vec<u8>, &'static str)> {
    let stream = doc.get_object(obj_id).ok()?.as_stream().ok()?.clone();
    let data = &stream.content;

    let filter_obj = match stream.dict.get(b"Filter") {
        Ok(obj) => obj,
        _ => return None,
    };

    let filter_name = match filter_obj {
        Object::Name(n) => Some(n.as_slice()),
        Object::Array(arr) => arr.first().and_then(|o| if let Object::Name(n) = o { Some(n.as_slice()) } else { None }),
        _ => None,
    };

    match filter_name {
        Some(b"DCTDecode") => Some((data.clone(), "jpg")),
        Some(b"FlateDecode") => Some((data.clone(), "raw")),
        Some(b"JPXDecode") => Some((data.clone(), "jp2")),
        Some(b"CCITTFaxDecode") => Some((data.clone(), "tiff")),
        _ => {
            if !data.is_empty() {
                Some((data.clone(), "bin"))
            } else {
                None
            }
        }
    }
}

fn resolve_dict<'a>(dict: &'a lopdf::Dictionary, key: &[u8]) -> Option<&'a lopdf::Dictionary> {
    match dict.get(key) {
        Ok(Object::Dictionary(d)) => Some(d),
        _ => None,
    }
}

fn resolve_i64(dict: &lopdf::Dictionary, key: &[u8]) -> Option<i64> {
    match dict.get(key) {
        Ok(Object::Integer(n)) => Some(*n),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn create_test_pdf(path: &Path) {
        use lopdf::*;

        let mut doc = Document::new();
        let page_id = doc.new_object_id();

        let content = Stream::new(Dictionary::new(), b"q 1 0 0 1 0 0 cm Q".to_vec());
        let content_id = doc.add_object(content);

        let resources = Object::Dictionary({
            let mut dict = Dictionary::new();
            dict.set("XObject", Object::Dictionary(Dictionary::new()));
            dict
        });

        let page = Object::Dictionary({
            let mut dict = Dictionary::new();
            dict.set("Type", Object::Name(b"Page".to_vec()));
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
            dict.set("Type", Object::Name(b"Pages".to_vec()));
            dict.set("Kids", Object::Array(vec![Object::Reference(page_id)]));
            dict.set("Count", Object::Integer(1));
            dict
        });
        doc.objects.insert(pages_id, pages);

        if let Some(obj) = doc.objects.get_mut(&page_id) {
            if let Object::Dictionary(ref mut dict) = obj {
                dict.set("Parent", Object::Reference(pages_id));
            }
        }

        let catalog_id = doc.new_object_id();
        let catalog = Object::Dictionary({
            let mut dict = Dictionary::new();
            dict.set("Type", Object::Name(b"Catalog".to_vec()));
            dict.set("Pages", Object::Reference(pages_id));
            dict
        });
        doc.objects.insert(catalog_id, catalog);

        doc.trailer.set("Root", Object::Reference(catalog_id));

        doc.save(path).unwrap();
    }

    #[test]
    fn test_extract_images_no_images() {
        let tmp = TempDir::new().unwrap();
        let pdf_path = tmp.path().join("test.pdf");
        create_test_pdf(&pdf_path);
        let out_dir = tmp.path().join("images");

        let images =
            extract_images_from_pdf(pdf_path.to_str().unwrap(), &out_dir, 10, 2).unwrap();
        assert!(images.is_empty(), "No images expected");
    }

    #[test]
    fn test_extract_images_nonexistent_pdf() {
        let tmp = TempDir::new().unwrap();
        let result = extract_images_from_pdf(
            tmp.path().join("nonexistent.pdf").to_str().unwrap(),
            tmp.path(),
            10,
            2,
        );
        assert!(result.is_err(), "Should fail on nonexistent PDF");
    }
}
