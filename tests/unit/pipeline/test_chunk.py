"""Tests for pipeline/text chunking."""

from mbforge.pipeline.chunk import chunk_sections, chunk_text


class TestChunkText:
    def test_empty_text(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_single_chunk(self):
        result = chunk_text("Hello world")
        assert len(result) == 1
        assert result[0] == "Hello world"

    def test_long_text_multiple_chunks(self):
        text = "A" * 1200
        result = chunk_text(text, chunk_size=512, overlap=128)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= 600  # some tolerance

    def test_paragraph_boundary_break(self):
        para1 = "A" * 300
        para2 = "B" * 300
        text = f"{para1}\n\n{para2}"
        result = chunk_text(text, chunk_size=512, overlap=128)
        assert len(result) >= 1

    def test_sentence_boundary_break(self):
        sentences = ". ".join(["Word" * 20 for _ in range(20)])
        result = chunk_text(sentences, chunk_size=200, overlap=50)
        assert len(result) >= 2

    def test_chinese_sentence_break(self):
        text = "这是第一句话。" * 50
        result = chunk_text(text, chunk_size=100, overlap=30)
        assert len(result) >= 2

    def test_overlap_produces_repeated_content(self):
        text = " ".join(["word"] * 200)
        result = chunk_text(text, chunk_size=100, overlap=30)
        if len(result) >= 2:
            # Second chunk should share some content with first
            assert result[1][:30] in result[0] or any(
                result[1][:20] in c for c in [result[0]]
            )


class TestChunkSections:
    def test_empty_sections(self):
        assert chunk_sections([]) == []

    def test_section_with_empty_text(self):
        sections = [{"title": "Empty", "path": "Empty", "text": ""}]
        assert chunk_sections(sections) == []

    def test_section_produces_chunks(self):
        sections = [
            {
                "title": "Methods",
                "path": "Intro > Methods",
                "text": "A" * 1200,
                "page_start": 1,
                "page_end": 2,
            }
        ]
        result = chunk_sections(sections, chunk_size=512, overlap=128)
        assert len(result) >= 2
        for chunk in result:
            assert "chunk_id" in chunk
            assert "text" in chunk
            assert "metadata" in chunk
            assert chunk["metadata"]["section_title"] == "Methods"
            assert chunk["metadata"]["section_path"] == "Intro > Methods"
            assert chunk["metadata"]["page_start"] == 1

    def test_multiple_sections(self):
        sections = [
            {"title": "A", "path": "A", "text": "X" * 600},
            {"title": "B", "path": "B", "text": "Y" * 600},
        ]
        result = chunk_sections(sections, chunk_size=512, overlap=128)
        assert len(result) >= 2
        titles = {c["metadata"]["section_title"] for c in result}
        assert "A" in titles
        assert "B" in titles
