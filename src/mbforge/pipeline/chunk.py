"""Text chunking for vector indexing.

Splits sections into fixed-size chunks with overlap for embedding.
"""

from __future__ import annotations

import hashlib


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 128,
) -> list[str]:
    """Split text into overlapping chunks, respecting sentence boundaries.

    Args:
        text: Input text
        chunk_size: Target chunk size in characters
        overlap: Overlap between consecutive chunks in characters

    Returns:
        List of text chunks
    """
    if not text or not text.strip():
        return []

    if len(text) <= chunk_size:
        return [text.strip()]

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        if end < text_len:
            # Try to break at paragraph boundary
            nl = text.rfind("\n\n", start, end)
            if nl > start + chunk_size // 3:
                end = nl + 2
            else:
                # Try sentence boundary
                for sep in ["。", ".", "！", "!", "？", "?"]:
                    period = text.rfind(sep, start, end)
                    if period > start + chunk_size // 3:
                        end = period + 1
                        break
                else:
                    # Try newline
                    nl = text.rfind("\n", start, end)
                    if nl > start + chunk_size // 3:
                        end = nl + 1
                    else:
                        # Try space
                        space = text.rfind(" ", start, end)
                        if space > start + chunk_size // 3:
                            end = space + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap
        if start < 0:
            start = 0
        if start >= end or start >= text_len:
            break

    return chunks


def chunk_sections(
    sections: list[dict],
    chunk_size: int = 512,
    overlap: int = 128,
) -> list[dict]:
    """Chunk a list of sections into indexed chunks.

    Args:
        sections: List of dicts with 'title', 'path', 'text', 'page_start', 'page_end'
        chunk_size: Target chunk size
        overlap: Overlap between chunks

    Returns:
        List of chunk dicts with 'chunk_id', 'text', 'metadata'
    """
    all_chunks: list[dict] = []

    for section in sections:
        text = section.get("text", "")
        if not text.strip():
            continue

        parts = chunk_text(text, chunk_size, overlap)

        for i, part in enumerate(parts):
            chunk_id = _make_chunk_id(section.get("title", ""), i, part)
            metadata = {
                "section_title": section.get("title", ""),
                "section_path": section.get("path", ""),
                "page_start": section.get("page_start"),
                "page_end": section.get("page_end"),
                "chunk_index": i,
                "total_chunks": len(parts),
            }
            all_chunks.append({
                "chunk_id": chunk_id,
                "text": part,
                "metadata": metadata,
            })

    return all_chunks


def _make_chunk_id(title: str, index: int, text: str) -> str:
    """Generate a deterministic chunk ID."""
    content = f"{title}:{index}:{text[:100]}"
    h = hashlib.sha256(content.encode()).hexdigest()[:12]
    return f"chunk_{h}"
