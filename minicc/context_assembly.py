"""Bounded large-context assembly for RAG calls.

The original ``rag.answer`` hands the model five ~800-character chunks — about
one thousand tokens. The configured context window is 300,000. That gap is the
"input context is always too small" complaint: the gateway can take 50k–90k
tokens, but we only ever put ~1k in front of it.

This module closes the gap without spending a single model token. It fans the
question out into lexical variants (the original plus its distinct words and
adjacent word pairs), retrieves candidates for each, merges them by real
``(source, start_line, end_line)`` identity, then fills a token budget in a
*stable order*.

Two invariants matter more than raw size:

* **Determinism** — identical query + identical corpus yields byte-identical
  chunk order. Sorting is a total order ``(-score, source, start_line)``; no
  dict iteration order leaks into the prompt.
* **Prefix stability across budgets** — a larger budget only lets *more* chunks
  through the tail check. It never reorders the head. That is what keeps a
  prompt-cache prefix hit when a caller asks for more context mid-session.

Everything here is pure Python over the local BM25 index: no model, no network,
no repo writes.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

from . import rag

#: Default ask keeps the answer cheap; callers can ask for more explicitly.
DEFAULT_BUDGET_TOKENS = 8_000
MIN_BUDGET_TOKENS = 256
MAX_BUDGET_TOKENS = 60_000
DEFAULT_FANOUT = 12
DEFAULT_PER_VARIANT = 8
#: Extra retrieval variants are discounted so the literal question outranks a
#: single common word that happens to match a huge chunk.
VARIANT_WEIGHT = 0.6
PREFIX_CHUNKS_FOR_FINGERPRINT = 8


def clamp_budget(value: Any) -> int:
    """Coerce a caller-supplied budget into the safe, bounded range."""
    try:
        budget = int(value)
    except (TypeError, ValueError):
        return DEFAULT_BUDGET_TOKENS
    return max(MIN_BUDGET_TOKENS, min(MAX_BUDGET_TOKENS, budget))


def query_variants(query: str, *, max_variants: int = DEFAULT_FANOUT) -> list[str]:
    """Lexical fan-out with first-occurrence-wins deduplication.

    No model call: the original question plus its distinct content tokens and
    adjacent token pairs. Order is fixed, so the merged candidate order is too.
    """
    variants: list[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        normalized = " ".join(text.split()).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            variants.append(normalized)

    add(query)
    tokens = rag._tokens(query)
    for token in tokens:
        if len(variants) >= max_variants:
            break
        add(token)
    for index in range(len(tokens) - 1):
        if len(variants) >= max_variants:
            break
        add(f"{tokens[index]} {tokens[index + 1]}")
    return variants[:max_variants]


def estimate_chunk_tokens(text: str) -> int:
    """Same character/4 accounting the rest of minicc uses for gateways."""
    return max(1, math.ceil(len(text) / 4))


def _prefix_fingerprint(chunks: list[dict[str, Any]]) -> str:
    """Hash the first few chunk identities — the part of the prompt that must
    not move when the budget grows. Empty packs get a stable sentinel."""
    head = [
        [chunk["source"], chunk["start_line"], chunk["end_line"], chunk["score"]]
        for chunk in chunks[:PREFIX_CHUNKS_FOR_FINGERPRINT]
    ]
    raw = repr(head).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def build_context_pack(
    query: str,
    *,
    budget_tokens: Any = DEFAULT_BUDGET_TOKENS,
    max_variants: int = DEFAULT_FANOUT,
    per_variant: int = DEFAULT_PER_VARIANT,
    index: Any | None = None,
) -> dict[str, Any]:
    """Assemble a bounded, deterministic, line-anchored context pack.

    The returned dict is JSON-safe. ``chunks`` are ordered by score (ties by
    source and line), and ``truncated`` says whether the budget cut candidates
    off — an honest signal, not a silent undersupply.
    """
    budget = clamp_budget(budget_tokens)
    try:
        fanout = max(1, min(DEFAULT_FANOUT * 4, int(max_variants)))
    except (TypeError, ValueError):
        fanout = DEFAULT_FANOUT
    variants = query_variants(query, max_variants=fanout)
    per = max(1, min(20, int(per_variant)))
    if not variants:
        return {
            "query": query,
            "budget_tokens": budget,
            "estimated_tokens": 0,
            "chunks": [],
            "query_variants": [],
            "prefix_fingerprint": _prefix_fingerprint([]),
            "candidates": 0,
            "truncated": False,
        }

    idx = index if index is not None else rag._LazyIndex.get()
    best: dict[tuple[str, int, int], dict[str, Any]] = {}
    for position, variant in enumerate(variants):
        weight = 1.0 if position == 0 else VARIANT_WEIGHT
        for item in idx.search(variant, limit=per):
            identity = (item["source"], item["start_line"], item["end_line"])
            weighted = round(item["score"] * weight, 6)
            previous = best.get(identity)
            if previous is None or weighted > previous["_weighted"]:
                candidate = dict(item)
                candidate["score"] = weighted
                candidate["_weighted"] = weighted
                candidate["variant"] = variant
                best[identity] = candidate

    # Total order. Never sort by a dict alone: equal scores would then inherit
    # insertion order, which changes with fan-out and breaks the cache prefix.
    ranked = sorted(
        best.values(),
        key=lambda c: (-c["_weighted"], c["source"], c["start_line"]),
    )

    chunks: list[dict[str, Any]] = []
    used = 0
    truncated = False
    for candidate in ranked:
        tokens = estimate_chunk_tokens(candidate["chunk"])
        if used + tokens > budget:
            truncated = True
            break
        used += tokens
        chunks.append({
            "source": candidate["source"],
            "score": candidate["score"],
            "start_line": candidate["start_line"],
            "end_line": candidate["end_line"],
            "tokens": tokens,
            "variant": candidate["variant"],
            "chunk": candidate["chunk"],
        })

    return {
        "query": query,
        "budget_tokens": budget,
        "estimated_tokens": used,
        "chunks": chunks,
        "query_variants": variants,
        "prefix_fingerprint": _prefix_fingerprint(chunks),
        "candidates": len(ranked),
        "truncated": truncated,
    }


def render_context(pack: dict[str, Any]) -> str:
    """Render the numbered, line-anchored evidence block for a prompt."""
    return "\n\n".join(
        f"[{position}] file: {chunk['source']}:L{chunk['start_line']}-L{chunk['end_line']}\n{chunk['chunk']}"
        for position, chunk in enumerate(pack["chunks"], 1)
    )
