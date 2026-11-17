# -*- coding: utf-8 -*-
"""M8-T1195 — the citation-consistency check is a gate, not a decoration."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import minicc.rag as rag

SOURCES = [
    {"source": "README.md", "score": 9.5, "chunk": "para A", "start_line": 10, "end_line": 21},
    {"source": "CHANGELOG.md", "score": 8.5, "chunk": "para B", "start_line": 100, "end_line": 140},
]


def test_valid_single_citation_is_ok():
    out = rag.citation_report("minicc ships a routing engine [2].", SOURCES)
    assert out["ok"] is True
    assert out["cited"] == [2]
    assert out["valid"] == [2]
    assert out["invalid"] == []
    assert out["coverage"] == 1.0


def test_mixed_valid_and_phantom_refs_carry_their_own_verdicts():
    out = rag.citation_report("One shipped [1], plus an unsubstantiated claim [7], and maybe nothing [2].", SOURCES)
    assert out["ok"] is False
    assert out["cited"] == [1, 2, 7]
    assert out["valid"] == [1, 2]
    assert out["invalid"] == [7]
    assert out["coverage"] == pytest.approx(2 / 3, abs=0.01)


def test_nothing_cited_is_an_honest_blank():
    out = rag.citation_report("the gateway replied in Chinese.", SOURCES)
    assert out["ok"] is True
    assert out["cited"] == []
    assert out["coverage"] is None


def test_search_results_carry_real_line_anchors():
    idx = rag.BM25Index()
    results = idx.search("缓存", limit=2)
    assert results, "the bundled corpus resolves the common phrase"
    for item in results:
        assert isinstance(item["start_line"], int) and item["start_line"] >= 1
        assert isinstance(item["end_line"], int) and item["end_line"] >= item["start_line"]


def test_answer_payload_carries_a_citation_verdict(monkeypatch):
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    class _Msg:
                        content = "routing is handled in the engine [1][9]."

                    class _Usage:
                        prompt_tokens = 40
                        completion_tokens = 12
                        total_tokens = 52
                        prompt_tokens_details = SimpleNamespace(cached_tokens=24)

                    class _Choice:
                        message = _Msg()

                    class _Resp:
                        pass

                    resp = _Resp()
                    resp.choices = [_Choice()]
                    resp.usage = _Usage()
                    return resp

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = rag.answer("how does routing work?", limit=2,
                     config=SimpleNamespace(model="m", base_url="https://example.invalid/v1",
                                            api_key="sk-test", prompt_cache_key=""),
                     max_output_tokens=64)
    assert out["citation"]["ok"] is False           # [9] outranges the 2 retrieved
    assert out["citation"]["cited"] == [1, 9]
    assert out["citation"]["invalid"] == [9]
    assert out["usage"]["prompt_cache_hit_tokens"] == 24


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
