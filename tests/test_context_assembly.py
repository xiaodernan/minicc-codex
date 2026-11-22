# -*- coding: utf-8 -*-
"""M8-T1294 — large-context assembly must be bounded, stable and auditable."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import minicc.context_assembly as ca
import minicc.rag as rag


def _index():
    # Use the same lazy singleton the HTTP/RAG path uses. Rebuilding a fresh
    # BM25Index per test re-tokenizes the whole ledger and takes ~5s each.
    return rag._LazyIndex.get()


def test_budget_is_bounded_and_coerced():
    assert ca.clamp_budget("nope") == ca.DEFAULT_BUDGET_TOKENS
    assert ca.clamp_budget(-50) == ca.MIN_BUDGET_TOKENS
    assert ca.clamp_budget(999999) == ca.MAX_BUDGET_TOKENS
    assert ca.clamp_budget(4096) == 4096


def test_empty_query_yields_empty_pack_with_stable_fingerprint():
    pack = ca.build_context_pack("   ", index=_index())
    assert pack["chunks"] == []
    assert pack["estimated_tokens"] == 0
    assert pack["query_variants"] == []
    assert pack["prefix_fingerprint"] == ca._prefix_fingerprint([])
    assert pack["truncated"] is False


def test_pack_respects_budget_and_marks_truncation():
    small = ca.build_context_pack("缓存 命中率 优化", budget_tokens=600, index=_index())
    large = ca.build_context_pack("缓存 命中率 优化", budget_tokens=24000, index=_index())
    assert small["estimated_tokens"] <= 600
    assert large["estimated_tokens"] <= 24000
    assert len(large["chunks"]) >= len(small["chunks"])
    assert large["candidates"] > 0
    assert sum(c["tokens"] for c in small["chunks"]) == small["estimated_tokens"]


def test_assembly_is_deterministic_down_to_chunk_order():
    a = ca.build_context_pack("StateGraph 状态流转 缓存", budget_tokens=9000, index=_index())
    b = ca.build_context_pack("StateGraph 状态流转 缓存", budget_tokens=9000, index=_index())
    assert a["prefix_fingerprint"] == b["prefix_fingerprint"]
    assert [c["source"] for c in a["chunks"]] == [c["source"] for c in b["chunks"]]
    assert [c["start_line"] for c in a["chunks"]] == [c["start_line"] for c in b["chunks"]]
    assert ca.render_context(a) == ca.render_context(b)


def test_larger_budget_never_reorders_the_head_of_the_prompt():
    head = ca.build_context_pack("访客行为 分析 优化措施", budget_tokens=1200, index=_index())
    full = ca.build_context_pack("访客行为 分析 优化措施", budget_tokens=30000, index=_index())
    assert head["chunks"], "the small pack must have something to compare"
    assert len(full["chunks"]) > len(head["chunks"])
    # The head is identical: a growing budget appends, never reshuffles.
    assert full["prefix_fingerprint"] == head["prefix_fingerprint"]
    for left, right in zip(head["chunks"], full["chunks"]):
        assert (left["source"], left["start_line"], left["score"]) == \
               (right["source"], right["start_line"], right["score"])


def test_chunks_are_deduplicated_by_real_line_identity():
    pack = ca.build_context_pack("缓存 命中率 前缀 会话", budget_tokens=20000, index=_index())
    identities = [(c["source"], c["start_line"], c["end_line"]) for c in pack["chunks"]]
    assert len(identities) == len(set(identities)), "a chunk must not appear twice"


def test_each_chunk_carries_a_real_file_and_line_anchor():
    pack = ca.build_context_pack("管理员 行为分析", budget_tokens=4000, index=_index())
    assert pack["chunks"]
    for chunk in pack["chunks"]:
        assert chunk["source"].endswith(".md")
        assert isinstance(chunk["start_line"], int) and chunk["start_line"] >= 1
        assert chunk["end_line"] >= chunk["start_line"]
        assert chunk["tokens"] >= 1
    rendered = ca.render_context(pack)
    assert "file: " in rendered and "L1" in rendered
    assert rendered.count("[") >= len(pack["chunks"])


def test_fanout_expands_recall_over_a_single_query():
    query = "缓存 命中率 低 并行 会话"
    single = _index().search(query, limit=5)
    variants = ca.query_variants(query)
    assert variants[0] == query
    assert len(variants) > 1
    merged = ca.build_context_pack(query, budget_tokens=20000, index=_index())
    assert merged["candidates"] >= len(single)


def test_render_uses_numbered_evidence_matching_sources():
    pack = ca.build_context_pack("状态流转", budget_tokens=1600, index=_index())
    rendered = ca.render_context(pack)
    for position, chunk in enumerate(pack["chunks"], 1):
        assert f"[{position}] file: {chunk['source']}:L{chunk['start_line']}-L{chunk['end_line']}" in rendered


class _Client:
    def __init__(self, *args, **kwargs):
        pass

    class chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                class _Msg:
                    content = "evidenced [1]."

                class _Usage:
                    prompt_tokens = 400
                    completion_tokens = 5
                    total_tokens = 405
                    prompt_tokens_details = None

                class _Choice:
                    message = _Msg()

                class _Resp:
                    pass

                resp = _Resp()
                resp.choices = [_Choice()]
                resp.usage = _Usage()
                return resp


def test_answer_default_path_unchanged_without_budget(monkeypatch):
    captured = {}

    class Client(_Client):
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured["prompt"] = kwargs["messages"][0]["content"]
                    return _Client.chat.completions.create(**kwargs)

    monkeypatch.setattr("openai.OpenAI", Client)
    out = rag.answer("routing", limit=2,
                     config=SimpleNamespace(model="m", base_url="https://example.invalid/v1",
                                            api_key="sk-test", prompt_cache_key=""),
                     max_output_tokens=16)
    assert "context" not in out
    assert "\nL" not in captured["prompt"]


def test_answer_budget_path_reports_context_and_line_anchors(monkeypatch):
    captured = {}

    class Client(_Client):
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured["prompt"] = kwargs["messages"][0]["content"]
                    return _Client.chat.completions.create(**kwargs)

    monkeypatch.setattr("openai.OpenAI", Client)
    out = rag.answer("缓存 命中率 低", limit=2,
                     config=SimpleNamespace(model="m", base_url="https://example.invalid/v1",
                                            api_key="sk-test", prompt_cache_key=""),
                     max_output_tokens=16, budget_tokens=3000)
    assert "context" in out
    assert out["context"]["estimated_tokens"] <= 3000
    assert out["context"]["chunks"] == len(out["sources"])
    assert "file: " in captured["prompt"] and ":L" in captured["prompt"]
    assert out["citation"]["valid"] == [1]


def test_answer_budget_path_survives_provider_error(monkeypatch):
    class Broken:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("quota dry")

    monkeypatch.setattr("openai.OpenAI", Broken)
    out = rag.answer("缓存", config=SimpleNamespace(
        model="m", base_url="https://example.invalid/v1", api_key="sk-test", prompt_cache_key=""),
        budget_tokens=1200)
    assert out["answer"] == ""
    assert "quota dry" in out["error"]
    assert out["context"]["chunks"] > 0
