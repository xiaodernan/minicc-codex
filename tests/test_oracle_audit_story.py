"""M8-T1173 — the model reads this repository's own audit trail to tell its story.

The wire is the repository's own ``.minicc/audit.jsonl`` — real keystrokes the
agent made against the workspace.  The model never answers without an audit to
read; an empty window is zero-token "no-audit"; a model failure is honest
live=False; a healthy window produces a bilingual narrative that names the
window it read.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import minicc.oracle_audit_story as oas
from minicc.oracle_common import default_cache


def _config():
    return SimpleNamespace(model="test-model", base_url="https://example.test/v1",
                           api_key="test-key", prompt_cache_key="")


@pytest.fixture(autouse=True)
def _clear_cache():
    default_cache.set(oas._CACHE_KEY, None, ttl=0)
    yield
    default_cache.set(oas._CACHE_KEY, None, ttl=0)


def _write_audit(tmp_path: Path, lines: list[str]) -> Path:
    dst = tmp_path / ".minicc"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "audit.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


_SAMPLE = [
    json.dumps({"timestamp": "2026-11-17T00:00:00+00:00", "action": "read",
                "path": "README.md", "detail": "lines 1-53"}),
    json.dumps({"timestamp": "2026-11-17T00:00:01+00:00", "action": "read",
                "path": "README.md", "detail": "lines 1-53"}),
    json.dumps({"timestamp": "2026-11-17T00:00:02+00:00", "action": "write",
                "path": "web/index.html", "detail": "12 bytes inserted"}),
    json.dumps({"timestamp": "2026-11-17T00:00:03+00:00", "action": "read",
                "path": ".github/workflows/ci.yml", "detail": "lines 1-60"}),
]


def _fake_response(zh: str, en: str, prompt_tokens: int = 1300,
                   completion_tokens: int = 120, cached_tokens: int | None = None):
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
    details = None
    if cached_tokens is not None:
        class _Details:
            pass
        details = _Details()
        details.cached_tokens = cached_tokens
        usage.prompt_tokens_details = details
    resp.usage = usage
    return resp


def _install_client(monkeypatch, zh: str = "反复读 README.md。", en: str = "Read README.md again and again."):
    captured: dict = {}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)
                    return _fake_response(zh, en)

    monkeypatch.setattr("openai.OpenAI", _Client)
    return captured


def _forbid_model(monkeypatch) -> dict:
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


def test_story_carries_the_window_and_calls_the_model(monkeypatch, tmp_path: Path) -> None:
    root = _write_audit(tmp_path, _SAMPLE)
    captured = _install_client(monkeypatch)

    out = oas.build_audit_story(config=_config(), workspace=root, force_refresh=True)
    assert out["live"] is True
    assert out["verdict"] == "model-story"
    assert out["window_size"] == 4
    assert out["total_lines"] == 4
    assert out["zh"] == "反复读 README.md。"
    assert out["en"] == "Read README.md again and again."
    assert out["usage"].get("cached_tokens") is None  # nothing cached, not fabricated
    prompt = captured["messages"][0]["content"]
    assert "README.md" in prompt and "ci.yml" in prompt
    assert "纪律" in prompt and "不推测" in prompt      # anti-fabrication banned in prompt


def test_empty_audit_window_costs_zero_tokens(monkeypatch, tmp_path: Path) -> None:
    root = _write_audit(tmp_path, [])
    sentinel = _forbid_model(monkeypatch)

    out = oas.build_audit_story(config=_config(), workspace=root, force_refresh=True)
    assert out["live"] is True
    assert out["verdict"] == "no-audit"
    assert sentinel == {}
    assert out["zh"] and out["en"]


def test_missing_audit_file_costs_zero_tokens(monkeypatch, tmp_path: Path) -> None:
    sentinel = _forbid_model(monkeypatch)

    out = oas.build_audit_story(config=_config(), workspace=tmp_path, force_refresh=True)
    assert out["live"] is True
    assert out["verdict"] == "no-audit"
    assert sentinel == {}


def test_unparsable_line_stays_counted_not_dropped(monkeypatch, tmp_path: Path) -> None:
    root = _write_audit(tmp_path, _SAMPLE + ["not json at all"])
    _install_client(monkeypatch, zh="看不懂也会回这句。", en="Parsing failure is still counted.")

    out = oas.build_audit_story(config=_config(), workspace=root, force_refresh=True)
    assert out["live"] is True
    assert out["window_size"] == 5                 # the unparsable line is counted, not erased
    assert out["verdict"] == "model-story"


def test_second_call_rides_the_memo(monkeypatch, tmp_path: Path) -> None:
    root = _write_audit(tmp_path, _SAMPLE)
    calls = {"n": 0}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    calls["n"] += 1
                    return _fake_response("一", "one")

    monkeypatch.setattr("openai.OpenAI", _Client)
    first = oas.build_audit_story(config=_config(), workspace=root, force_refresh=True)
    second = oas.build_audit_story(config=_config(), workspace=root)
    assert calls["n"] == 1
    assert first["generated_at"] == second["generated_at"]


def test_model_failure_is_honest_not_raised(monkeypatch, tmp_path: Path) -> None:
    root = _write_audit(tmp_path, _SAMPLE)

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("provider exploded")

    monkeypatch.setattr("openai.OpenAI", _Client)
    out = oas.build_audit_story(config=_config(), workspace=root, force_refresh=True)
    assert out["live"] is False
    assert "RuntimeError" in out["error"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
