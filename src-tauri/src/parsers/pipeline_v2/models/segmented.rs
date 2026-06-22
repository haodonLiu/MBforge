//! Segmented document representation used for chunking and downstream analysis.

use serde::{Deserialize, Serialize};

/// A document after structural segmentation into sections, headings, and a tree.
///
/// This is the primary output of the segmentation stage. It keeps the flat list
/// of chunks alongside the hierarchical document tree and heading index so
/// downstream stages can choose the most convenient representation.
#[derive(Debug, Clone)]
pub struct SegmentedDocument {
    /// Flat, ordered list of text chunks produced by the segmentation stage.
    pub sections: Vec<SectionChunk>,

    /// Hierarchical view of the document built from headings.
    pub document_tree: Vec<TreeNode>,

    /// All headings discovered in the document, in reading order.
    pub headings: Vec<Heading>,
}

/// A contiguous text chunk produced by segmenting a document on headings.
///
/// Each chunk corresponds to a single section of the source document and
/// records both logical location (`path`, `title`) and source coordinates
/// (`page_start`, `page_end`, `line_start`, `line_end`).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SectionChunk {
    /// Human-readable title of the section.
    pub title: String,

    /// Hierarchical path of the section, e.g. "1/2/3".
    pub path: String,

    /// Plain text content of the section.
    pub text: String,

    /// One-based page number where the section begins, if known.
    pub page_start: Option<usize>,

    /// One-based page number where the section ends, if known.
    pub page_end: Option<usize>,

    /// Zero-based line number where the section begins in the raw text.
    pub line_start: usize,

    /// Zero-based line number where the section ends in the raw text.
    pub line_end: usize,
}

/// A heading discovered during document segmentation.
///
/// Headings capture the document outline and drive construction of both the
/// section chunks and the document tree.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Heading {
    /// Heading depth, where 1 is the top-level heading.
    pub level: usize,

    /// Normalized title text of the heading.
    pub title: String,

    /// Zero-based line number where the heading appears in the raw text.
    pub line_num: usize,
}

/// A node in the hierarchical document tree.
///
/// Tree nodes are built from headings and preserve nesting so that downstream
/// consumers can render a table of contents or navigate by section.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TreeNode {
    /// Display title for this tree node.
    pub title: String,

    /// Stable identifier for the node, typically derived from its path.
    pub node_id: String,

    /// Zero-based line number of the heading that produced this node.
    pub line_num: usize,

    /// Child nodes nested under this heading.
    pub nodes: Vec<TreeNode>,
}
