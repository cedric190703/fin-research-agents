"""Parent/child ("small-to-big") chunking.

Children (~512 tokens) are what we embed and search; parents (~2 000 tokens)
are what we hand to the model. Both carry character offsets into the section
so a citation can be resolved back to the filing.

Tokens are approximated as whitespace-delimited words × 1.3, which is close
enough for sizing and keeps ingestion free of a tokenizer dependency.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

_WORD = re.compile(r"\S+")
TOKENS_PER_WORD = 1.3


@dataclass(frozen=True)
class ChunkSpec:
    child_tokens: int = 512
    child_overlap: int = 64
    parent_tokens: int = 2000


@dataclass
class TextChunk:
    id: str
    level: str  # "parent" | "child"
    text: str
    char_start: int
    char_end: int
    parent_id: str | None = None
    children: list[str] = field(default_factory=list)


def estimate_tokens(text: str) -> int:
    return int(len(_WORD.findall(text)) * TOKENS_PER_WORD)


def _word_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _WORD.finditer(text)]


def _chunk_id(prefix: str, start: int, end: int) -> str:
    return hashlib.sha1(f"{prefix}:{start}:{end}".encode()).hexdigest()[:16]


def _windows(
    spans: list[tuple[int, int]], words_per_chunk: int, overlap_words: int
) -> list[tuple[int, int]]:
    """Return (char_start, char_end) windows over word spans."""
    if not spans:
        return []
    step = max(1, words_per_chunk - overlap_words)
    out: list[tuple[int, int]] = []
    i = 0
    while i < len(spans):
        j = min(len(spans), i + words_per_chunk)
        out.append((spans[i][0], spans[j - 1][1]))
        if j == len(spans):
            break
        i += step
    return out


def chunk_section(text: str, *, id_prefix: str, spec: ChunkSpec | None = None) -> list[TextChunk]:
    """Chunk one section into parents with their children. Offsets are relative to `text`."""
    spec = spec or ChunkSpec()
    spans = _word_spans(text)
    parent_words = max(1, int(spec.parent_tokens / TOKENS_PER_WORD))
    child_words = max(1, int(spec.child_tokens / TOKENS_PER_WORD))
    overlap_words = int(spec.child_overlap / TOKENS_PER_WORD)

    chunks: list[TextChunk] = []
    for p_start, p_end in _windows(spans, parent_words, 0):
        parent = TextChunk(
            id=_chunk_id(id_prefix, p_start, p_end),
            level="parent",
            text=text[p_start:p_end],
            char_start=p_start,
            char_end=p_end,
        )
        p_spans = [s for s in spans if s[0] >= p_start and s[1] <= p_end]
        for c_start, c_end in _windows(p_spans, child_words, overlap_words):
            child = TextChunk(
                id=_chunk_id(id_prefix, c_start, c_end),
                level="child",
                text=text[c_start:c_end],
                char_start=c_start,
                char_end=c_end,
                parent_id=parent.id,
            )
            parent.children.append(child.id)
            chunks.append(child)
        chunks.insert(len(chunks) - len(parent.children), parent)
    return chunks
