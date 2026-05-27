"""Extract text contexts mentioning molecules."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class MoleculeContext:
    """Context passage mentioning a molecule."""

    text: str
    context_type: str  # 'smiles_mention', 'name_mention', 'activity'
    page_idx: int = 0
    position_start: int = 0
    position_end: int = 0


class MoleculeContextExtractor:
    """Extract all text mentioning a specific molecule."""

    WINDOW_SIZE = 200

    def extract_contexts(
        self,
        full_text: str,
        smiles: str,
        name: str = "",
        activities: list[dict] | None = None,
    ) -> list[MoleculeContext]:
        """Find all passages discussing this molecule."""
        contexts = []

        # 1. Direct SMILES mention
        for match in re.finditer(re.escape(smiles), full_text):
            contexts.append(MoleculeContext(
                text=self._extract_window(full_text, match.start()),
                context_type="smiles_mention",
                position_start=max(0, match.start() - self.WINDOW_SIZE),
                position_end=min(len(full_text), match.end() + self.WINDOW_SIZE),
            ))

        # 2. Chemical name mention
        if name:
            for match in re.finditer(re.escape(name), full_text, re.I):
                contexts.append(MoleculeContext(
                    text=self._extract_window(full_text, match.start()),
                    context_type="name_mention",
                    position_start=max(0, match.start() - self.WINDOW_SIZE),
                    position_end=min(len(full_text), match.end() + self.WINDOW_SIZE),
                ))

        # 3. Activity data
        if activities:
            for activity in activities:
                pattern = f"{activity['type']}\\s*[=:]\\s*{activity['value']}"
                for match in re.finditer(pattern, full_text, re.I):
                    contexts.append(MoleculeContext(
                        text=self._extract_window(full_text, match.start()),
                        context_type="activity",
                        position_start=max(0, match.start() - self.WINDOW_SIZE),
                        position_end=min(len(full_text), match.end() + self.WINDOW_SIZE),
                    ))

        return self._deduplicate_contexts(contexts)

    def _extract_window(self, text: str, pos: int) -> str:
        """Extract text window around position."""
        start = max(0, pos - self.WINDOW_SIZE)
        end = min(len(text), pos + self.WINDOW_SIZE)
        return text[start:end]

    def _deduplicate_contexts(
        self,
        contexts: list[MoleculeContext],
    ) -> list[MoleculeContext]:
        """Remove overlapping contexts."""
        if not contexts:
            return contexts

        # Sort by position
        contexts.sort(key=lambda c: c.position_start)

        # Remove overlaps
        deduplicated = [contexts[0]]
        for ctx in contexts[1:]:
            if ctx.position_start >= deduplicated[-1].position_end:
                deduplicated.append(ctx)

        return deduplicated
