use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::LazyLock;

/// Result of keyword and entity extraction.
///
/// Port of keyword/entity logic from
/// `src/mbforge/core/summarizer.py` (`DocumentSummarizer._extract_keywords`).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KeywordExtraction {
    pub keywords: Vec<String>,
    pub entity_tags: Vec<String>,
}

/// Regex for extracting 3-10 character English words.
static WORD_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"[a-zA-Z]{3,10}").expect("valid word regex"));
static COMPOUND_NAME_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)Compound\s+\d+[a-zA-Z]?").expect("valid compound name regex")
});
static ENTITY_CANDIDATE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\b[A-Z][A-Za-z0-9]{2,9}\b").expect("valid entity regex"));

/// Default stoplist — ported from `summarizer.py`.
fn default_stoplist() -> std::collections::HashSet<&'static str> {
    [
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "had",
        "her",
        "was",
        "one",
        "our",
        "out",
        "day",
        "get",
        "has",
        "him",
        "his",
        "how",
        "man",
        "new",
        "now",
        "old",
        "see",
        "two",
        "way",
        "who",
        "boy",
        "did",
        "its",
        "let",
        "put",
        "say",
        "she",
        "too",
        "use",
        "with",
        "that",
        "this",
        "from",
        "they",
        "have",
        "been",
        "were",
        "said",
        "each",
        "which",
        "their",
        "time",
        "will",
        "about",
        "would",
        "there",
        "could",
        "other",
        "after",
        "first",
        "these",
        "them",
        "some",
        "what",
        "when",
        "where",
        "than",
        "then",
        "more",
        "into",
        "over",
        "also",
        "only",
        "know",
        "take",
        "year",
        "good",
        "come",
        "make",
        "well",
        "work",
        "life",
        "even",
        "here",
        "look",
        "down",
        "most",
        "long",
        "last",
        "find",
        "give",
        "does",
        "made",
        "part",
        "such",
        "keep",
        "call",
        "came",
        "back",
        "much",
        "before",
        "right",
        "through",
        "during",
        "should",
        "between",
        "being",
        "both",
        "under",
        "never",
        "really",
        "still",
        "those",
        "while",
        "group",
        "high",
        "every",
        "great",
        "another",
        "study",
        "using",
        "used",
        "based",
        "shown",
        "showed",
        "results",
        "method",
        "activity",
        "compound",
        "molecular",
        "cell",
        "protein",
        "analysis",
        "data",
        "fig",
        "table",
        "et",
        "al",
        "vs",
    ]
    .into_iter()
    .collect()
}

/// Extract keywords from text using frequency-based approach.
///
/// Returns top 10 keywords after filtering stopwords.
pub fn extract_keywords(text: &str) -> Vec<String> {
    let stop = default_stoplist();
    let mut freq: HashMap<String, usize> = HashMap::new();

    for m in WORD_RE.find_iter(text) {
        let word = m.as_str().to_lowercase();
        if word.len() <= 3 || stop.contains(word.as_str()) {
            continue;
        }
        *freq.entry(word).or_insert(0) += 1;
    }

    let mut words: Vec<(usize, String)> = freq.into_iter().map(|(w, c)| (c, w)).collect();
    words.sort_by(|a, b| b.0.cmp(&a.0));
    words.into_iter().take(10).map(|(_, w)| w).collect()
}

/// Extract entity tags from text.
///
/// Looks for compound names (Compound N) and capitalized multi-character
/// tokens that are likely protein/gene names.
pub fn extract_entities(text: &str) -> Vec<String> {
    let mut entities = Vec::new();
    let mut seen = std::collections::HashSet::new();

    // Compound names
    for m in COMPOUND_NAME_RE.find_iter(text) {
        let name = m.as_str().to_string();
        if seen.insert(name.clone()) {
            entities.push(name);
        }
    }

    // Capitalized candidate entities (likely protein/gene names)
    let stop = default_stoplist();
    for m in ENTITY_CANDIDATE_RE.find_iter(text) {
        let candidate = m.as_str().to_string();
        let lower = candidate.to_lowercase();
        if lower.len() <= 3 || stop.contains(lower.as_str()) || seen.contains(&candidate) {
            continue;
        }
        // Skip sentence-starting words that are common English
        if matches!(
            lower.as_str(),
            "this"
                | "that"
                | "these"
                | "those"
                | "with"
                | "from"
                | "they"
                | "were"
                | "have"
                | "been"
                | "will"
                | "would"
                | "could"
                | "should"
                | "also"
                | "only"
                | "into"
                | "over"
                | "some"
                | "more"
                | "than"
                | "then"
                | "each"
                | "both"
        ) {
            continue;
        }
        seen.insert(candidate.clone());
        entities.push(candidate);
    }

    entities
}

/// Convenience function: extract both keywords and entities at once.
pub fn extract_keywords_and_entities(text: &str) -> KeywordExtraction {
    KeywordExtraction {
        keywords: extract_keywords(text),
        entity_tags: extract_entities(text),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_keywords_basic() {
        let text = "The compound showed excellent activity against EGFR kinase with IC50 of 5.2 nM. Molecular docking studies revealed strong binding affinity.";
        let kw = extract_keywords(text);
        assert!(kw.len() <= 10);
        // "compound" is in stoplist, "excellent" and "activity" should appear
        assert!(kw.contains(&"excellent".to_string()));
        assert!(kw.contains(&"docking".to_string()));
    }

    #[test]
    fn test_extract_keywords_empty_returns_empty() {
        let kw = extract_keywords("");
        assert!(kw.is_empty());
    }

    #[test]
    fn test_extract_entities_compound() {
        let entities = extract_entities("Compound 1 and Compound 2 were tested");
        assert!(entities.contains(&"Compound 1".to_string()));
        assert!(entities.contains(&"Compound 2".to_string()));
    }

    #[test]
    fn test_extract_entities_uppercase() {
        let entities = extract_entities("EGFR and VEGFR2 kinases were inhibited");
        // Should capture EGFR and VEGFR2
        assert!(entities.contains(&"EGFR".to_string()));
        assert!(entities.contains(&"VEGFR2".to_string()));
    }

    #[test]
    fn test_extract_entities_dedup() {
        let entities = extract_entities("EGFR and EGFR kinases");
        let count = entities.iter().filter(|e| *e == "EGFR").count();
        assert_eq!(count, 1);
    }

    #[test]
    fn test_extract_keywords_and_entities_integration() {
        let text = "Compound 1 showed activity against EGFR kinase with excellent potency.";
        let result = extract_keywords_and_entities(text);
        assert!(!result.keywords.is_empty());
        assert!(!result.entity_tags.is_empty());
        assert!(result.entity_tags.contains(&"Compound 1".to_string()));
    }
}
