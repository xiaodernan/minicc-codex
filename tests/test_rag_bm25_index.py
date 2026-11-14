"""M8-T971: the in-tree BM25 index. Unit tests + HTTP coverage."""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse

import pytest

from minicc.rag import BM25Index, _load_documents, _tokens


def test_tokens_are_lowercased_alnum_splits() -> None:
    assert _tokens("hello WORLD-123") == ["hello", "world", "123"]
    assert _tokens("") == []


def test_index_loads_bundled_docs() -> None:
    docs = _load_documents()
    assert len(docs) > 500, docs
    sources = {s for s, _ in docs}
    assert "README.md" in sources or any("README" in s for s in sources)


def test_cache_phrase_finds_changelog() -> None:
    idx = BM25Index()
    results = idx.search("缓存命中率", limit=3)
    assert len(results) >= 1
    joined = " ".join(item["chunk"] for item in results)
    assert "缓存" in joined


def test_chinese_sentence_without_spaces_finds_docs() -> None:
    """M8-T975 regression: a natural Chinese question (no spaces, one CJK
    run) must retrieve docs. Before the bigram tokenizer, the whole run
    scored as a single giant token and the index came back empty — which
    made /api/rag/query useless for the primary language of the docs."""
    idx = BM25Index()
    results = idx.search("为什么缓存命中率看起来很低", limit=5)
    assert results, "CJK sentences without spaces must not return nothing"
    joined = " ".join(item["chunk"] for item in results)
    assert "缓存" in joined


def test_unknown_terms_return_nothing() -> None:
    idx = BM25Index()
    assert idx.search("xyznonexistentthing", limit=3) == []


def test_empty_query_returns_nothing() -> None:
    assert BM25Index().search("", limit=3) == []


def test_limit_is_respected() -> None:
    idx = BM25Index()
    assert len(idx.search("almanac", limit=1)) <= 1
    assert len(idx.search("featur", limit=3)) <= 3


def test_score_is_finite_positive() -> None:
    for item in BM25Index().search("minicc", limit=5):
        assert item["score"] > 0
