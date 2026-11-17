"""Small in-memory BM25 index over the repository's own docs.

The workbench already carries a local sentence retriever (``LocalEvidenceIndex``)
but it is task-shaped: it answers "which file evidence supports this question
right now". This module is smaller, simpler, and symmetric to what a RAG
("/api/rag/search" and "/api/rag/query") caller needs: a ranked list of
documentation chunks relevant to a free-form query.

Tokenization is bilingual by construction: latin/digit runs are kept whole,
CJK runs are emitted as bigrams (a Chinese sentence has no spaces; scoring
the run as one giant token matches nothing — M8-T975 measured exactly that
on the wkapi.pro lane and fixed it here). The implementation is
deliberately textbook BM25 (k1=1.2, b=0.75) over its chunks. No embeddings,
no model, no network. It will find "缓存命中率 低" faster than semantic RAG
can ever hope to, because the project uses the exact phrase in the docs.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any

_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
#: The corpus is docs/*.md (which already carries CONTRIBUTING.md) plus the
#: repository README; there is no second root-level CONTRIBUTING — pointing
#: at one would either double-count docs/CONTRIBUTING.md or fail silently.
_ROOT_FILES = (
    Path(__file__).resolve().parent.parent / "README.md",
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


def _chunk_markdown(text: str, *, chunk_chars: int = 800) -> list[tuple[str, int, int]]:
    # M8-T1195: chunks carry their real line ranges so a reader (or the jury
    # downstream) can check a fact against the owning file, not against a
    # filename with no anchor into it.
    lines = text.splitlines()
    paragraphs: list[tuple[int, int, str]] = []   # (start, end, text)
    current: list[str] = []
    current_start = 1
    for index, raw in enumerate(lines, 1):
        if raw.strip():
            if not current:
                current_start = index
            current.append(raw)
            continue
        if current:
            paragraphs.append((current_start, current_start + len(current) - 1, "\n".join(current).strip()))
            current = []
    if current:
        paragraphs.append((current_start, current_start + len(current) - 1, "\n".join(current).strip()))

    chunks: list[tuple[str, int, int]] = []
    buf: list[str] = []
    buf_spans: list[tuple[int, int]] = []
    buf_len = 0
    for start, end, paragraph in paragraphs:
        projected = buf_len + (2 if buf else 0) + len(paragraph)
        if buf and projected > chunk_chars:
            chunks.append(("\n\n".join(buf), buf_spans[0][0], buf_spans[-1][1]))
            buf, buf_spans, buf_len = [paragraph], [(start, end)], len(paragraph)
            continue
        buf.append(paragraph)
        buf_spans.append((start, end))
        buf_len = projected
    if buf:
        chunks.append(("\n\n".join(buf), buf_spans[0][0], buf_spans[-1][1]))
    return chunks


def _load_documents() -> list[tuple[str, str, int, int]]:
    docs: list[tuple[str, str, int, int]] = []
    for file in sorted(_DOCS_DIR.glob("*.md")):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for chunk, start, end in _chunk_markdown(text):
            if chunk.strip():
                docs.append((file.name, chunk, start, end))
    for file in _ROOT_FILES:
        if not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for chunk, start, end in _chunk_markdown(text):
            if chunk.strip():
                docs.append((file.name, chunk, start, end))
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


import re as _re

_CITATION_RE = _re.compile(r"\[(\d+)\]")

def citation_report(answer_text: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Cross-check the '[n]' references the model emitted against the retrieved sources.

    Honest verdicts only: ``ok`` is true only when every cited index exists in the
    retrieved set; `cited`/`invalid` list which ones, `coverage` is len(valid)/len(cited)
    (None when nothing was cited). Nothing about the model's truthfulness is claimed
    beyond that — we never judge whether a cited chunk supports a sentence.
    """
    cited = sorted({int(m.group(1)) for m in _CITATION_RE.finditer(answer_text)})
    invalid = [n for n in cited if n < 1 or n > len(sources)]
    valid = [n for n in cited if 1 <= n <= len(sources)]
    return {
        "ok": not invalid,
        "cited": cited,
        "valid": valid,
        "invalid": invalid,
        "coverage": round(len(valid) / len(cited), 3) if cited else None,
    }

def _prompt_cache_key(base_url: str, model: str, explicit: str = "") -> str:
    """Same affinity-key discipline as the provider: an explicit key wins,
    otherwise a salted hash of gateway+model — stable across processes."""
    explicit = (explicit or "").strip()[:64]
    if explicit:
        return explicit
    return f"minicc-{hashlib.sha256(f'{base_url}|{model}'.encode('utf-8')).hexdigest()[:16]}"


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
            # Boundary: the route answers with an honest error payload, never a
            # 500 - a missing or invalid environment is surfaced to the caller.
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
    explicit_key = str(getattr(config, "prompt_cache_key", "") or "")
    cache_key = _prompt_cache_key(base_url, model_name, explicit_key)

    prompt = (
        "You answer only from the documents below. Copy the language of the question.\n"
        "Answer briefly and cite the source numbers like [1], [2] for the facts you use.\n"
        "If and only if the documents do not cover the question, reply with one short sentence in the same language as the question saying the documents do not directly answer it — do not mix languages in that sentence.\n\n"
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
            prompt_cache_key=cache_key,
        )
        from .llm.usage import measured_usage, token_count

        text = (response.choices[0].message.content or "").strip()
        usage_obj = getattr(response, "usage", None)
        usage = measured_usage(
            token_count(getattr(usage_obj, "prompt_tokens", 0), 0) or 0,
            token_count(getattr(usage_obj, "completion_tokens", 0), 0) or 0,
            token_count(getattr(usage_obj, "total_tokens", None), None),
        )
        # Report cache visibility honestly when the gateway reports it.
        # Never fabricate: absent details → key absent.
        details = getattr(usage_obj, "prompt_tokens_details", None)
        cached = None
        if isinstance(details, dict):
            cached = details.get("cached_tokens")
        elif details is not None:
            cached = getattr(details, "cached_tokens", None)
        if isinstance(cached, (int, float)) and not isinstance(cached, bool):
            usage["prompt_cache_hit_tokens"] = int(cached)
        # Note: /usage does not carry cached_tokens on chat/completions; it is
        # intentionally honest about that — we do not fabricate a cache hit rate.
        return {
            "query": query,
            "answer": text,
            "model": model_name,
            "base_url": base_url,
            "usage": usage,
            "sources": sources,
            "citation": citation_report(text, sources),
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
    """Minimal Okapi BM25 over (source, chunk, start_line, end_line) tuples."""

    def __init__(self, docs: list[tuple[str, str, int, int]] | None = None) -> None:
        self.k1 = 1.2
        self.b = 0.75
        self.docs: list[tuple[str, str, list[str], int, int]] = [
            (src, chunk, _tokens(chunk), start, end)
            for src, chunk, start, end in (docs if docs is not None else _load_documents())
        ]
        self.N = len(self.docs)
        df: dict[str, int] = {}
        for _, _, tokens, _, _ in self.docs:
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1
        self.df = df
        self.avgdl = sum(len(t) for _, _, t, _, _ in self.docs) / self.N if self.N else 1.0

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        q_tokens = _tokens(query)
        if not q_tokens:
            return []
        scores: list[tuple[float, int]] = []
        for idx, (src, chunk, tokens, _start, _end) in enumerate(self.docs):
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
            src, chunk, _tokens_list, start, end = self.docs[idx]
            snippet = chunk if len(chunk) <= 400 else chunk[:400] + "…"
            results.append({"source": src, "score": round(score, 4),
                            "chunk": snippet, "start_line": start, "end_line": end})
        return results
