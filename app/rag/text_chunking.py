from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Chunk:
    """
    A single chunk of text taken from one specific page.
    """
    page: int           # 1-based page number (for citations)
    chunk_index: int    # chunk number on that page (0, 1, 2...)
    text: str           # actual chunk text


def normalize_whitespace(text: str) -> str:
    """
    Make whitespace consistent so chunking is stable across runs.

    Why:
    - PDFs can contain weird spacing and lots of newlines.
    - Normalizing helps produce deterministic chunk boundaries.
    """
    text = text.replace("\u00a0", " ")          # non-breaking space -> normal space
    text = re.sub(r"[ \t]+", " ", text)         # collapse repeated spaces/tabs
    text = re.sub(r"\n{3,}", "\n\n", text)      # collapse huge newline runs
    return text.strip()


def chunk_page_text(
    page_num: int,
    text: str,
    max_chars: int = 1200,
    overlap_chars: int = 200,
) -> List[Chunk]:
    """
    Deterministically chunk a page into overlapping windows.

    Strategy (simple + stable):
    - Normalize whitespace
    - Sliding window: max_chars per chunk, with overlap_chars overlap

    Overlap is important because policies often split rules across boundaries.
    """
    text = normalize_whitespace(text)

    if not text:
        return []

    chunks: List[Chunk] = []

    start = 0
    chunk_idx = 0
    n = len(text)

    while start < n:
        end = min(start + max_chars, n)
        chunk_text = text[start:end].strip()

        if chunk_text:
            chunks.append(
                Chunk(page=page_num, chunk_index=chunk_idx, text=chunk_text)
            )
            chunk_idx += 1

        # If we reached the end, stop
        if end >= n:
            break

        # Move start forward, keeping overlap
        start = max(0, end - overlap_chars)

    return chunks
