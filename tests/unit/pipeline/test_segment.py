"""Tests for pipeline/document segmentation."""

from mbforge.pipeline.segment import (
    build_sections,
    build_tree,
    extract_headings,
    segment_document,
)


class TestExtractHeadings:
    def test_no_headings(self):
        headings = extract_headings("just plain text\nno headings here")
        assert headings == []

    def test_single_h1(self):
        text = "# Introduction\nSome text here."
        headings = extract_headings(text)
        assert len(headings) == 1
        assert headings[0].level == 1
        assert headings[0].title == "Introduction"

    def test_nested_headings(self):
        text = """# Title
## Section 1
### Subsection 1.1
## Section 2
"""
        headings = extract_headings(text)
        assert len(headings) == 4
        assert [h.level for h in headings] == [1, 2, 3, 2]
        assert headings[2].title == "Subsection 1.1"

    def test_headings_with_extra_spaces(self):
        text = "#   Spaced Title\n##    Also Spaced"
        headings = extract_headings(text)
        assert len(headings) == 2
        assert headings[0].title == "Spaced Title"


class TestBuildSections:
    def test_empty_text_no_headings(self):
        sections = build_sections("", [], max_chars=1000)
        assert len(sections) == 0 or (len(sections) == 1 and not sections[0].text.strip())

    def test_with_headings(self):
        text = """# Intro
Welcome to the paper.

# Methods
We used PyMuPDF for extraction.

# Results
The results are shown in Figure 1.
"""
        headings = extract_headings(text)
        sections = build_sections(text, headings, max_chars=1000)
        assert len(sections) == 3
        assert sections[0].title == "Intro"
        assert "Welcome" in sections[0].text
        assert sections[1].title == "Methods"
        assert sections[2].title == "Results"

    def test_long_section_splits(self):
        paragraphs = "\n\n".join(["A" * 500 for _ in range(20)])
        text = f"# Big Section\n\n{paragraphs}"
        headings = extract_headings(text)
        sections = build_sections(text, headings, max_chars=1000)
        assert len(sections) > 1
        for s in sections:
            assert len(s.text) <= 1200  # some tolerance for boundary

    def test_no_headings_fallback(self):
        text = "A" * 2000 + "\n\n" + "B" * 2000
        sections = build_sections(text, [], max_chars=1000)
        assert len(sections) >= 2


class TestBuildTree:
    def test_flat_sections(self):
        sections = [
            type("S", (), {"title": "A", "path": "A", "line_start": 0})(),
            type("S", (), {"title": "B", "path": "B", "line_start": 10})(),
        ]
        tree = build_tree(sections)
        assert len(tree) == 2

    def test_nested_sections(self):
        from mbforge.pipeline.segment import SectionChunk
        sections = [
            SectionChunk(title="Title", path="Title", text="", line_start=0),
            SectionChunk(title="Methods", path="Title > Methods", text="", line_start=5),
            SectionChunk(title="Sub", path="Title > Methods > Sub", text="", line_start=8),
            SectionChunk(title="Results", path="Title > Results", text="", line_start=12),
        ]
        tree = build_tree(sections)
        assert len(tree) == 1  # Title is root
        assert tree[0].title == "Title"
        assert len(tree[0].nodes) == 2  # Methods, Results
        assert tree[0].nodes[0].title == "Methods"
        assert len(tree[0].nodes[0].nodes) == 1  # Sub under Methods


class TestSegmentDocument:
    def test_empty_text(self):
        result = segment_document("")
        assert result.sections == []
        assert result.document_tree == []
        assert result.headings == []

    def test_full_segmentation(self):
        text = """# Introduction
Background information.

# Methods
## Sample Preparation
We prepared samples.

## Analysis
Analysis details.

# Conclusion
Final thoughts.
"""
        result = segment_document(text)
        assert len(result.headings) == 5
        assert len(result.sections) == 5
        assert len(result.document_tree) == 3  # 3 h1 headings are siblings at root
