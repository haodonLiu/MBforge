"""PDF type classification module."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PageClassification:
    """Classification result for a single page."""

    page_idx: int
    text_density: float
    is_scanned: bool
    has_molecular_patterns: bool
    context_from_neighbors: str = ""


@dataclass
class DocumentClassification:
    """Classification result for entire document."""

    text_density: float
    is_scanned: bool
    has_molecular_patterns: bool
    metadata_hints: dict[str, Any] = field(default_factory=dict)
    pages: list[PageClassification] = field(default_factory=list)
    needs_confirmation: bool = False


class PDFClassifier:
    """Classify PDF type and content."""

    # SMILES pattern: requires SMILES-specific structural features
    # (bonds =/#, ring closures letter+digit, chirality @, charges [+/-])
    SMILES_PATTERN = re.compile(
        r"(?=(?:.*[=#])|(?:.*[a-z][0-9])|(?:.*@)|(?:.*\[[\+\-]))"
        r"[A-Za-z0-9@\.\+\-\=\#\$\(\)\[\]\\\/\%\~]{4,}"
    )

    # Common chemical names
    CHEMICAL_NAMES = {
        "aspirin", "ibuprofen", "caffeine", "metformin", "paracetamol",
        "acetaminophen", "penicillin", "morphine", "codeine", "insulin",
        "glucose", "ethanol", "methanol", "acetone", "benzene",
        "toluene", "phenol", "aniline", "pyridine", "quinoline",
    }

    # Thresholds
    DOCUMENT_SCAN_THRESHOLD = 50.0
    PAGE_SCAN_THRESHOLD = 20.0

    def classify_page(
        self,
        page_text: str,
        page_idx: int,
    ) -> PageClassification:
        """Classify a single page."""
        text_density = len(page_text.strip())
        is_scanned = text_density < self.PAGE_SCAN_THRESHOLD
        has_molecular_patterns = self._detect_molecular_patterns(page_text)

        return PageClassification(
            page_idx=page_idx,
            text_density=text_density,
            is_scanned=is_scanned,
            has_molecular_patterns=has_molecular_patterns,
        )

    def classify_document_from_pages(
        self,
        pages: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> DocumentClassification:
        """Classify document from extracted page texts."""
        if not pages:
            return DocumentClassification(
                text_density=0,
                is_scanned=True,
                has_molecular_patterns=False,
            )

        # Calculate average text density
        total_chars = sum(len(p.strip()) for p in pages)
        avg_density = total_chars / len(pages)

        # Classify each page
        page_classifications = [
            self.classify_page(page_text, idx)
            for idx, page_text in enumerate(pages)
        ]

        # Check for molecular patterns across document
        has_molecules = any(p.has_molecular_patterns for p in page_classifications)

        # Metadata hints
        metadata_hints = self._analyze_metadata(metadata or {})

        return DocumentClassification(
            text_density=avg_density,
            is_scanned=avg_density < self.DOCUMENT_SCAN_THRESHOLD,
            has_molecular_patterns=has_molecules,
            metadata_hints=metadata_hints,
            pages=page_classifications,
            needs_confirmation=self._needs_confirmation(page_classifications),
        )

    def _detect_molecular_patterns(self, text: str) -> bool:
        """Detect SMILES or chemical names in text."""
        # Check for SMILES-like patterns
        if self.SMILES_PATTERN.search(text):
            return True

        # Check for chemical names
        text_lower = text.lower()
        for name in self.CHEMICAL_NAMES:
            if name in text_lower:
                return True

        return False

    def _analyze_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Analyze PDF metadata for hints."""
        hints = {}

        # Check filename
        filename = metadata.get("filename", "").lower()
        molecular_keywords = ["mol", "drug", "compound", "chemical", "pharma"]
        for keyword in molecular_keywords:
            if keyword in filename:
                hints["filename_hint"] = True
                break

        # Check title
        title = metadata.get("title", "").lower()
        if any(kw in title for kw in molecular_keywords):
            hints["title_hint"] = True

        return hints

    def _needs_confirmation(self, pages: list[PageClassification]) -> bool:
        """Determine if user confirmation is needed."""
        # Need confirmation if there are mixed page types
        scanned_count = sum(1 for p in pages if p.is_scanned)
        text_count = len(pages) - scanned_count

        # Mixed content needs confirmation
        if scanned_count > 0 and text_count > 0:
            return True

        # Low confidence molecular detection needs confirmation
        if any(p.has_molecular_patterns for p in pages):
            return True

        return False
