use serde::Serialize;

#[derive(Serialize)]
pub struct TextChunkResult {
    pub chunks: Vec<String>,
    pub total_chunks: usize,
}

/// Split text into overlapping chunks, preferring natural boundaries.
///
/// Port of `split_text_chunks()` from `src/mbforge/utils/helpers.py`.
#[tauri::command]
pub fn text_chunk(text: String, chunk_size: usize, overlap: usize) -> TextChunkResult {
    if text.is_empty() || chunk_size == 0 {
        return TextChunkResult {
            chunks: vec![],
            total_chunks: 0,
        };
    }

    let chars: Vec<char> = text.chars().collect();
    let len = chars.len();
    let mut chunks: Vec<String> = Vec::new();
    let mut start: usize = 0;

    while start < len {
        let mut end = std::cmp::min(start + chunk_size, len);

        if end < len {
            let half = start + chunk_size / 2;
            // Try newline boundary
            if let Some(pos) = find_rev(&chars, start, end, '\n') {
                if pos > half {
                    end = pos + 1;
                }
            } else if let Some(pos) = find_rev(&chars, start, end, '。') {
                // Try Chinese period
                if pos > half {
                    end = pos + 1;
                }
            } else if let Some(pos) = find_rev(&chars, start, end, ' ') {
                // Try space
                if pos > half {
                    end = pos + 1;
                }
            }
        }

        let chunk: String = chars[start..end].iter().collect();
        let trimmed = chunk.trim();
        if !trimmed.is_empty() {
            chunks.push(trimmed.to_string());
        }

        if end >= chunk_size {
            start = end - overlap;
        } else {
            start = end;
        }

        if end == len {
            break;
        }
        if start >= len || start >= end {
            break;
        }
    }

    let total = chunks.len();
    TextChunkResult {
        chunks,
        total_chunks: total,
    }
}

/// Find the last occurrence of `target` in chars[start..end].
fn find_rev(chars: &[char], start: usize, end: usize, target: char) -> Option<usize> {
    chars[start..end]
        .iter()
        .rposition(|&c| c == target)
        .map(|p| start + p)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_text_chunk_long_text() {
        let text = "a ".repeat(1000);
        let result = text_chunk(text, 512, 128);
        assert!(
            result.total_chunks > 1,
            "Expected multiple chunks, got {}",
            result.total_chunks
        );
        assert!(
            result.total_chunks < 100,
            "Too many chunks: {}",
            result.total_chunks
        );
    }

    #[test]
    fn test_text_chunk_boundary_respect() {
        let text = "First line\nSecond line\nThird line with more content\nFourth".to_string();
        let result = text_chunk(text, 30, 5);
        assert!(result.total_chunks > 0);
    }
}
