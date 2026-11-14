"""Small in-memory BM25 index over the repository's own docs.

The workbench already carries a local sentence retriever (``LocalEvidenceIndex``)
but it is task-shaped: it answers "which file evidence supports this question
right now". This module is smaller, simpler, and symmetric to what a RAG
("/api/rag/search") caller needs: a ranked list of documentation chunks
relevant to a free-form query.

Tokenization is bilingual by construction: latin/digit runs are kept whole,
CJK runs are emitted as bigrams (a Chinese sentence has no spaces; scoring
the run as one giant token matches nothing — M8-T975 measured exactly that
on the wkapi.pro lane and fixed it here). The implementation is
deliberately textbook BM25 (k1=1.2, b=0.75) over its chunks. No embeddings,
no model, no network. It will find "缓存命中率 低" faster than semantic RAG
can ever hope to, because the project uses the exact phrase in the docs.
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

# Two token families. Latin/digit runs are kept whole (prefix_cache_key is
# one token — our readers write it that way). CJK runs are emitted as
# bigrams, because a Chinese sentence arrives without spaces: the run
# "为什么缓存命中率看起来很低" is one regex match, and scoring it as a
# single giant token matches nothing — which is why the askdocs panel
# used to come back empty for the primary language of this repo's docs.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]+")


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text.lower()):
        token = match.group()
        if token[0] >= "\u4e00":
            if len(token) <= 1:
                tokens.append(token)
            else:
                tokens.extend(token[i : i + 2] for i in range(len(token) - 1))
        else:
            tokens.append(token)
    return tokens


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


def answer(query: str, limit: int = 5, *, config: Any | None = None, max_output_tokens: int = 700) -> dict[str, Any]:
    """One-shot RAG over the repo docs: retrieve, then ask the configured model.

    Uses the same provider settings as the rest of minicc (MINICC_* env). Returns a
    dict with ``sources`` (the retrieved documents), ``answer`` (the model's text),
    and ``usage`` (token counters when the gateway provides them).
    Never leaks the api_key; the base_url in the result is the public host only.
    """
    sources = search(query, limit=limit)
    if not sources:
        return {"query": query, "answer": "", "sources": [], "model": None, "usage": None}

    from .config import load_config
    from openai import OpenAI

    if config is None:
        try:
            config = load_config(workspace=Path("."))
        except Exception as exc:
            return {
                "query": query,
                "answer": "",
                "sources": sources,
                "model": None,
                "usage": None,
                "error": f"config-unavailable: {type(exc).__name__}: {exc}",
            }
    # Headers carry the key as a constant; never insert it into the prompt.
    model_name = str(getattr(config, "model", "gpt-6-sol") or "gpt-6-sol")
    base_url = str(getattr(config, "base_url", "https://wkapi.pro/v1") or "https://wkapi.pro/v1")
    api_key = str(getattr(config, "api_key", "") or "")

    prompt = (
        "You answer only from the documents below. Copy the language of the query.\n"
        "If the docs do not answer the question, reply: 文档里没有直接答案 — I cannot find it in the docs.\n\n"
        + "\n\n".join(
            f"[{index + 1}] file: {item['source']}\n{item['chunk']}" for index, item in enumerate(sources)
        )
        + f"\n\nQuestion: {query}"
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=45, max_retries=0)
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=max_output_tokens,
            temperature=0,
        )
        text = (response.choices[0].message.content or "").strip()
        usage_obj = getattr(response, "usage", None)
        usage = {
            "prompt_tokens": int(getattr(usage_obj, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage_obj, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(usage_obj, "total_tokens", 0) or 0),
        }
        # Note: /usage does not carry cached_tokens on chat/completions; it is
        # intentionally honest about that — we do not fabricate a cache hit rate.
        return {
            "query": query,
            "answer": text,
            "model": model_name,
            "base_url": base_url,
            "usage": usage,
            "sources": sources,
        }
    except Exception as exc:  # noqa: BLE001 - surface the failure to the caller, not a stack trace
        return {
            "query": query,
            "answer": "",
            "model": model_name,
            "base_url": base_url,
            "usage": None,
            "sources": sources,
            "error": f"{type(exc).__name__}: {exc}",
        }


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
