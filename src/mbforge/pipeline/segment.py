"""Document segmentation — heading extraction, section building, tree construction.

Ported from Rust `mbforge-pipeline/src/pipeline/stages/segment.rs`.
Splits document text into sections at Markdown heading boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..utils.logger import get_logger

logger = get_logger("mbforge.pipeline.segment")

# Markdown heading pattern: # through ######
_MD_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class Heading:
    level: int  # 1-6
    title: str
    line_num: int  # 0-based


@dataclass
class SectionChunk:
    title: str
    path: str  # "Heading1 > Heading2 > Heading3"
    text: str
    page_start: int | None = None
    page_end: int | None = None
    line_start: int = 0
    line_end: int = 0


@dataclass
class TreeNode:
    title: str
    node_id: str
    line_num: int = 0
    nodes: list[TreeNode] = field(default_factory=list)


@dataclass
class SegmentedDocument:
    sections: list[SectionChunk]
    document_tree: list[TreeNode]
    headings: list[Heading]


def extract_headings(text: str) -> list[Heading]:
    """Extract Markdown headings from text."""
    headings: list[Heading] = []
    for i, line in enumerate(text.split("\n")):
        m = _MD_RE.match(line.strip())
        if m:
            headings.append(Heading(
                level=len(m.group(1)),
                title=m.group(2).strip(),
                line_num=i,
            ))
    return headings


def build_sections(
    text: str,
    headings: list[Heading],
    page_texts: list[str] | None = None,
    max_chars: int = 8000,
) -> list[SectionChunk]:
    """Build sections from text and headings.

    If no headings are found, falls back to semantic chunking.
    Long sections are split into parts.
    """
    if not headings:
        return _build_semantic_sections(text, page_texts, max_chars)

    lines = text.split("\n")
    total_lines = len(lines)
    sections: list[SectionChunk] = []
    path_stack: list[str] = []

    for i, heading in enumerate(headings):
        start_line = heading.line_num
        end_line = headings[i + 1].line_num if i + 1 < len(headings) else total_lines

        if start_line >= end_line:
            continue

        section_text = "\n".join(lines[start_line:end_line])
        _update_path_stack(path_stack, heading)

        page_start = _line_to_page(start_line)
        page_end = _line_to_page(end_line - 1)

        if len(section_text) > max_chars:
            parts = _split_long_section(section_text, max_chars)
            for j, part in enumerate(parts):
                part_title = f"{heading.title} (part {j + 1})" if len(parts) > 1 else heading.title
                part_path = f"{' > '.join(path_stack)} (part {j + 1})" if len(parts) > 1 else " > ".join(path_stack)
                sections.append(SectionChunk(
                    title=part_title,
                    path=part_path,
                    text=part,
                    page_start=page_start,
                    page_end=page_end,
                    line_start=start_line,
                    line_end=end_line,
                ))
        else:
            sections.append(SectionChunk(
                title=heading.title,
                path=" > ".join(path_stack),
                text=section_text,
                page_start=page_start,
                page_end=page_end,
                line_start=start_line,
                line_end=end_line,
            ))

    return sections


def build_tree(sections: list[SectionChunk]) -> list[TreeNode]:
    """Build a hierarchical tree from flat section list."""
    root_nodes: list[TreeNode] = []
    stack: list[tuple[int, TreeNode]] = []  # (level, node)

    for i, section in enumerate(sections):
        level = section.path.count(" > ") + 1
        node = TreeNode(
            title=section.title,
            node_id=f"node_{i}",
            line_num=section.line_start,
        )

        # Pop nodes at same or deeper level
        while stack and stack[-1][0] >= level:
            _, completed = stack.pop()
            if stack:
                stack[-1][1].nodes.append(completed)
            else:
                root_nodes.append(completed)

        stack.append((level, node))

    # Pop remaining
    while stack:
        _, completed = stack.pop()
        if stack:
            stack[-1][1].nodes.append(completed)
        else:
            root_nodes.append(completed)

    return root_nodes


def segment_document(text: str, max_chars: int = 8000) -> SegmentedDocument:
    """Full segmentation: extract headings → build sections → build tree."""
    if not text or not text.strip():
        return SegmentedDocument(sections=[], document_tree=[], headings=[])

    headings = extract_headings(text)
    sections = build_sections(text, headings, max_chars=max_chars)
    tree = build_tree(sections)

    logger.info("Segmented: %d headings, %d sections", len(headings), len(sections))
    return SegmentedDocument(sections=sections, document_tree=tree, headings=headings)


def _update_path_stack(stack: list[str], heading: Heading) -> None:
    """Update the heading path stack based on heading level."""
    if heading.level <= len(stack):
        del stack[heading.level - 1:]
    stack.append(heading.title)


def _line_to_page(line_num: int) -> int:
    """Estimate page number from line number (rough: 50 lines per page)."""
    return line_num // 50 + 1


def _split_long_section(text: str, max_chars: int) -> list[str]:
    """Split a long section into chunks respecting max_chars.

    Strategy: split on paragraph boundaries first, then sentence boundaries.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""

    # Split on double newlines (paragraphs)
    paragraphs = text.split("\n\n")
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            current = ""
        if len(para) > max_chars:
            # Paragraph itself is too long — split on sentences
            if current:
                chunks.append(current.strip())
                current = ""
            sentences = _split_sentences(para)
            for sent in sentences:
                if len(current) + len(sent) + 1 > max_chars and current:
                    chunks.append(current.strip())
                    current = ""
                current += sent + " "
        else:
            current += para + "\n\n"

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences (Chinese + English)."""
    # Split on sentence-ending punctuation
    parts = re.split(r"(?<=[。！？.!?])\s*", text)
    return [p.strip() for p in parts if p.strip()]


def _build_semantic_sections(
    text: str,
    page_texts: list[str] | None,
    max_chars: int,
) -> list[SectionChunk]:
    """Fallback: split text into semantic sections when no headings are found."""
    chunks = _split_long_section(text, max_chars)
    sections: list[SectionChunk] = []
    offset = 0
    for i, chunk in enumerate(chunks):
        line_start = text[:offset].count("\n")
        line_end = line_start + chunk.count("\n")
        sections.append(SectionChunk(
            title=f"Section {i + 1}",
            path=f"Section {i + 1}",
            text=chunk,
            page_start=_line_to_page(line_start),
            page_end=_line_to_page(line_end),
            line_start=line_start,
            line_end=line_end,
        ))
        offset += len(chunk) + 1
    return sections
