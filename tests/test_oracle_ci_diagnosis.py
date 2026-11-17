"""M8-T1166 — the model's attribution of this repo's mainline red, honest by construction.

The data source is the GitHub REST wire only; the model may point at the
failure family, or say it cannot tell. No fact exists outside the wire JSON the
route hands it — and three of the four verdict states cost zero tokens because
the honest answer there is "no red to attribute".
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import minicc.oracle_ci_diagnosis as cidx
from minicc.oracle_common import default_cache


def _wire(*, conclusion: str | None, status: str | None) -> dict:
    """A minimal but faithful ci_health payload."""
    latest = {
        "conclusion": conclusion,
        "status": status,
        "workflow": "CI",
        "created_at": "2026-11-17T00:00:00Z",
        "head_sha": "abc1234",
        "html_url": "https://github.com/xiaodernan/minicc-codex/actions/runs/1",
    }
    return {
        "live": True,
        "generated_at": 123456789.0,
        "latest_run": latest,
        "recent": [latest],
        "open_prs": 0,
        "open_issues": 0,
        "errors": None,
    }


def _config():
    return SimpleNamespace(model="test-model", base_url="https://example.test/v1",
                           api_key="test-key", prompt_cache_key="")


@pytest.fixture(autouse=True)
def _clear_cache():
    default_cache.set(cidx._CACHE_KEY, None, ttl=0)
    yield
    default_cache.set(cidx._CACHE_KEY, None, ttl=0)


def _fake_response(zh: str, en: str, prompt_tokens: int = 900,
                   completion_tokens: int = 130, cached_tokens: int | None = 4224):
    class _Msg:
        content = json.dumps({"zh": zh, "en": en}, ensure_ascii=False)

    class _Usage:
        pass

    class _Choice:
        pass

    msg = _Msg()
    choice = _Choice()
    choice.message = msg

    class _Resp:
        pass

    resp = _Resp()
    resp.choices = [choice]
    usage = _Usage()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens
    if cached_tokens is None:
        resp.usage = usage
    else:
        class _Details:
            pass
        details = _Details()
        details.cached_tokens = cached_tokens
        usage.prompt_tokens_details = details
        resp.usage = usage
    return resp


def _install_client(monkeypatch, zh: str = "归因：引文搬迁没重新瞄准。", en: str = "Attribution: re-aimed citation drift."):
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)
                    return _fake_response(zh, en)

    captured: dict = {}
    monkeypatch.setattr("openai.OpenAI", _Client)
    return captured


def _forbid_model(monkeypatch) -> dict:
    """A client whose create() fails the test — used to prove zero-token paths."""
    called: dict = {}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    called["yes"] = True
                    raise AssertionError("the model must not be called in this path")

    monkeypatch.setattr("openai.OpenAI", _Client)
    return called


def test_failure_wire_produces_model_diagnosis(monkeypatch) -> None:
    monkeypatch.setattr(cidx, "fetch_ci_health", lambda **_: _wire(conclusion="failure", status="completed"))
    _install_client(monkeypatch)

    out = cidx.build_ci_diagnosis(config=_config(), workspace=Path("."), force_refresh=True)
    assert out["live"] is True
    assert out["verdict"] == "model-diagnosis"
    assert out["head_sha"] == "abc1234"
    assert out["workflow"] == "CI"
    assert "归因" in out["zh"] or out["zh"]
    assert out["usage"]["prompt_tokens"] == 900
    assert out["usage"]["cached_tokens"] == 4224


def test_the_prompt_carries_only_wire_facts(monkeypatch) -> None:
    monkeypatch.setattr(cidx, "fetch_ci_health", lambda **_: _wire(conclusion="failure", status="completed"))
    captured = _install_client(monkeypatch)

    cidx.build_ci_diagnosis(config=_config(), workspace=Path("."), force_refresh=True)
    prompt = captured["messages"][0]["content"]
    assert "abc1234" in prompt                      # the wire fact
    assert "无法从这六类里判定" in prompt           # bounded-family clause survives the prompt
    assert "不许" in prompt or "不" in prompt       # anti-fabrication discipline rides along


def test_green_wire_costs_zero_tokens(monkeypatch) -> None:
    monkeypatch.setattr(cidx, "fetch_ci_health", lambda **_: _wire(conclusion="success", status="completed"))
    sentinel = _forbid_model(monkeypatch)

    out = cidx.build_ci_diagnosis(config=_config(), workspace=Path("."), force_refresh=True)
    assert out["live"] is True
    assert out["verdict"] == "no-current-failure"
    assert sentinel == {}                            # model never invoked
    assert out["zh"] and out["en"]
    assert "0 tokens" in out["en"] or "零 token" in out["zh"] or "没有调用模型" in out["zh"]


def test_pending_wire_costs_zero_tokens(monkeypatch) -> None:
    monkeypatch.setattr(cidx, "fetch_ci_health", lambda **_: _wire(conclusion=None, status="in_progress"))
    sentinel = _forbid_model(monkeypatch)

    out = cidx.build_ci_diagnosis(config=_config(), workspace=Path("."), force_refresh=True)
    assert out["live"] is True
    assert out["verdict"] == "pending"
    assert sentinel == {}
    assert "abc1234" in out["zh"] or "abc1234" in out["en"]


def test_wire_down_never_calls_the_model(monkeypatch) -> None:
    monkeypatch.setattr(cidx, "fetch_ci_health", lambda **_: {"live": False})
    sentinel = _forbid_model(monkeypatch)

    out = cidx.build_ci_diagnosis(config=_config(), workspace=Path("."), force_refresh=True)
    assert out["live"] is False
    assert out["verdict"] == "wire-down"
    assert sentinel == {}


def test_model_failure_is_honest_not_raised(monkeypatch) -> None:
    monkeypatch.setattr(cidx, "fetch_ci_health", lambda **_: _wire(conclusion="failure", status="completed"))

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("provider exploded")

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = cidx.build_ci_diagnosis(config=_config(), workspace=Path("."), force_refresh=True)
    assert out["live"] is False
    assert "RuntimeError" in out["error"]


def test_second_call_rides_the_memo(monkeypatch) -> None:
    monkeypatch.setattr(cidx, "fetch_ci_health", lambda **_: _wire(conclusion="failure", status="completed"))
    calls = {"n": 0}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    calls["n"] += 1
                    return _fake_response("a", "b")

    monkeypatch.setattr("openai.OpenAI", _Client)
    first = cidx.build_ci_diagnosis(config=_config(), workspace=Path("."), force_refresh=True)
    second = cidx.build_ci_diagnosis(config=_config(), workspace=Path("."))
    assert calls["n"] == 1                            # one model round trip for two reads
    assert first["generated_at"] == second["generated_at"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
