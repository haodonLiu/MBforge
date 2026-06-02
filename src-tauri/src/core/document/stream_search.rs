use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamingSearchConfig {
    pub enabled: bool,
    pub yield_first: usize,
}

impl Default for StreamingSearchConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            yield_first: 3,
        }
    }
}

/// A chunk of results yielded during streaming search.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamingResult {
    pub r#type: String,
    pub results: Vec<serde_json::Value>,
    pub count: usize,
    pub error: Option<String>,
}

/// Streaming knowledge base search wrapper.
///
/// Splits KB search results into two batches:
/// - First batch: first `yield_first` results (immediate)
/// - Remaining: yielded incrementally
pub struct StreamingSearch {
    config: StreamingSearchConfig,
}

impl StreamingSearch {
    pub fn new(config: StreamingSearchConfig) -> Self {
        Self { config }
    }

    /// Execute a search and return results in streaming chunks.
    ///
    /// Returns at most 3 chunks:
    /// 1. `"first"` — first `yield_first` results (if results exist)
    /// 2. `"incremental"` — remaining results (if any)
    /// 3. `"complete"` — summary with total count
    pub fn execute(
        &self,
        results: Vec<serde_json::Value>,
        top_k: usize,
    ) -> Vec<StreamingResult> {
        if !self.config.enabled {
            let count = results.len();
            return vec![StreamingResult {
                r#type: "complete".into(),
                results,
                count,
                error: None,
            }];
        }

        let yield_first = self.config.yield_first.min(top_k);

        if results.is_empty() {
            return vec![StreamingResult {
                r#type: "complete".into(),
                results: vec![],
                count: 0,
                error: None,
            }];
        }

        let mut chunks: Vec<StreamingResult> = Vec::new();

        let first_batch: Vec<serde_json::Value> = results.iter().take(yield_first).cloned().collect();
        if !first_batch.is_empty() {
            chunks.push(StreamingResult {
                r#type: "first".into(),
                results: first_batch,
                count: yield_first,
                error: None,
            });
        }

        let remaining: Vec<serde_json::Value> = results.iter().skip(yield_first).cloned().collect();
        for r in remaining {
            chunks.push(StreamingResult {
                r#type: "incremental".into(),
                results: vec![r],
                count: 1,
                error: None,
            });
        }

        chunks.push(StreamingResult {
            r#type: "complete".into(),
            results: vec![],
            count: results.len(),
            error: None,
        });

        chunks
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_result(id: usize) -> serde_json::Value {
        serde_json::json!({"id": id, "text": format!("result {}", id)})
    }

    #[test]
    fn test_disabled_streaming() {
        let ss = StreamingSearch::new(StreamingSearchConfig {
            enabled: false,
            yield_first: 3,
        });
        let results: Vec<serde_json::Value> = (0..5).map(make_result).collect();
        let chunks = ss.execute(results, 5);

        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].r#type, "complete");
        assert_eq!(chunks[0].count, 5);
    }

    #[test]
    fn test_enabled_streaming_with_results() {
        let ss = StreamingSearch::new(StreamingSearchConfig {
            enabled: true,
            yield_first: 2,
        });
        let results: Vec<serde_json::Value> = (0..5).map(make_result).collect();
        let chunks = ss.execute(results, 5);

        // first(2) + 3 incremental + complete(1) = 5 chunks
        assert_eq!(chunks.len(), 5);
        assert_eq!(chunks[0].r#type, "first");
        assert_eq!(chunks[0].results.len(), 2);
        assert_eq!(chunks[chunks.len() - 1].r#type, "complete");
        assert_eq!(chunks[chunks.len() - 1].count, 5);
    }

    #[test]
    fn test_empty_results() {
        let ss = StreamingSearch::new(StreamingSearchConfig::default());
        let chunks = ss.execute(vec![], 5);

        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].r#type, "complete");
        assert_eq!(chunks[0].count, 0);
    }

    #[test]
    fn test_yield_first_more_than_results() {
        let ss = StreamingSearch::new(StreamingSearchConfig {
            enabled: true,
            yield_first: 10,
        });
        let results: Vec<serde_json::Value> = (0..3).map(make_result).collect();
        let chunks = ss.execute(results, 10);

        assert_eq!(chunks.len(), 2); // first(3) + complete(1)
        assert_eq!(chunks[0].results.len(), 3);
    }

    #[test]
    fn test_yield_first_zero() {
        let ss = StreamingSearch::new(StreamingSearchConfig {
            enabled: true,
            yield_first: 0,
        });
        let results: Vec<serde_json::Value> = (0..3).map(make_result).collect();
        let chunks = ss.execute(results, 3);

        // no "first" chunk, just incremental(3) + complete
        assert_eq!(chunks.len(), 4);
        assert_eq!(chunks[0].r#type, "incremental");
    }
}
