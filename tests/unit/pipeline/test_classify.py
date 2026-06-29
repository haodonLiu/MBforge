"""Tests for pipeline/document classification."""

from mbforge.pipeline.classify import classify_document


class TestClassifyDocument:
    def test_empty_text_returns_unknown(self):
        result = classify_document("")
        assert result.doc_type == "unknown"
        assert result.confidence == 0.0

    def test_whitespace_only_returns_unknown(self):
        result = classify_document("   \n  \t  ")
        assert result.doc_type == "unknown"

    def test_patent_text_classified(self):
        text = """
        United States Patent No. 10,123,456

        Field of the Invention
        The present invention relates to ...

        Claims
        1. A method for comprising:
           a) providing a compound of formula I;
           b) contacting with a reagent.
        2. The method of claim 1, wherein ...
        """
        result = classify_document(text)
        assert result.doc_type == "patent"
        assert result.confidence > 0.3

    def test_paper_text_classified(self):
        text = """
        Abstract: We report a novel approach to ...

        Introduction: Recent advances in drug discovery
        have enabled ...

        Figure 1 shows the synthetic route.
        Table 1 summarizes the biological data.

        References:
        [1] Smith et al. Journal of Medicinal Chemistry, 2024.
        DOI: 10.1021/acs.jmedchem.2024.001

        Acknowledgments: This work was supported by ...
        Conflicts of interest: None declared.
        """
        result = classify_document(text)
        assert result.doc_type == "paper"
        assert result.confidence > 0.3

    def test_report_fallback(self):
        text = "This is a brief internal report with no special signals."
        result = classify_document(text)
        assert result.doc_type == "report"
        assert result.confidence <= 0.5

    def test_mixed_signals_picks_higher(self):
        text = """
        United States Patent
        Claims
        1. A compound of formula I.
        Abstract: A novel compound is disclosed.
        """
        result = classify_document(text)
        assert result.doc_type in ("patent", "paper")
        assert result.confidence > 0.0
