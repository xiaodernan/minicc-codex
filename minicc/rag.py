"""Small in-memory BM25 index over the repository's own docs.

The workbench already carries a local sentence retriever (``LocalEvidenceIndex``)
but it is task-shaped: it answers "which file evidence supports this question
right now". This module is smaller, simpler, and symmetric to what a RAG
("/api/rag/search") caller needs: a ranked list of documentation chunks
relevant to a free-form query.

The implementation is deliberately textbook BM25 (k1=1.2, b=0.75) over its
chunks. No embeddings, no model, no network. It is honest about what it is:
a lexical retriever. It will find "缓存命中率 低" faster than semantic RAG can
ever hope to, because the project uses the exact phrase in the docs.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
_ROOT_FILES = (
    Path(__file__).resolve().parent.parent / "README.md",
    Path(__file__).resolve().parent.parent / "CONTRIBUTING.md",
)
_DOC_FILE = Path(__file__).resolve().parent.parent / "docs" / "ROADMAP_TO_PRODUCT.md"

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]{2,}")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _chunk_markdown(text: str, *, chunk_chars: int = 800) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if buf and len(buf) + len(p) + 2 > chunk_chars:
            chunks.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def _load_documents() -> list[tuple[str, str]]:
    docs: list[tuple[str, str]] = []
    for file in sorted(_DOCS_DIR.glob("*.md")):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for chunk in _chunk_markdown(text):
            if chunk.strip():
                docs.append((file.name, chunk))
    for file in _ROOT_FILES:
        if not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for chunk in _chunk_markdown(text):
            if chunk.strip():
                docs.append((file.name, chunk))
    return docs


class _LazyIndex:
    _instance: BM25Index | None = None

    @classmethod
    def get(cls) -> BM25Index:
        if cls._instance is None:
            cls._instance = BM25Index()
        return cls._instance


def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    return _LazyIndex.get().search(query, limit=limit)


def reload_index() -> int:
    """Invalidate the cached index (call after docs change)."""
    _LazyIndex._instance = None
    return len(_LazyIndex.get().docs)


class BM25Index:
    """Minimal Okapi BM25 over (source, chunk) pairs."""

    def __init__(self, docs: list[tuple[str, str]] | None = None) -> None:
        self.k1 = 1.2
        self.b = 0.75
        self.docs: list[tuple[str, str, list[str]]] = [(src, chunk, _tokens(chunk)) for src, chunk in (docs if docs is not None else _load_documents())]
        self.N = len(self.docs)
        df: dict[str, int] = {}
        for _, _, tokens in self.docs:
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1
        self.df = df
        self.avgdl = sum(len(t) for _, _, t in self.docs) / self.N if self.N else 1.0

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        q_tokens = _tokens(query)
        if not q_tokens:
            return []
        scores: list[tuple[float, int]] = []
        for idx, (src, chunk, tokens) in enumerate(self.docs):
            tf: dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            score = 0.0
            for qt in q_tokens:
                df = self.df.get(qt)
                if not df:
                    continue
                idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)
                f = tf.get(qt, 0)
                norm = f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(tokens) / self.avgdl))
                score += idf * norm
            if score > 0.0:
                scores.append((score, idx))
        scores.sort(key=lambda item: -item[0])
        results: list[dict[str, Any]] = []
        for score, idx in scores[:limit]:
            src, chunk, _tokens_list = self.docs[idx]
            snippet = chunk if len(chunk) <= 400 else chunk[:400] + "…"
            results.append({"source": src, "score": round(score, 4), "chunk": snippet})
        return results
