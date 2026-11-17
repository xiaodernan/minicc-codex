"""M8-T1123: live code review — the model reads the real HEAD~1..HEAD diff.

Facts pinned into the prompt; nothing inferred; outage honest.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import minicc.oracle_review as orev
from minicc.oracle_common import default_cache


class _Client:
    captured: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    class chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                _Client.captured = kwargs

                class _Msg:
                    content = json.dumps({"zh": "中文评审", "en": "english review"}, ensure_ascii=False)

                class _Choice:
                    message = _Msg()

                class _Usage:
                    prompt_tokens = 700
                    completion_tokens = 160
                    total_tokens = 860

                    class prompt_tokens_details:
                        cached_tokens = 512

                class _Resp:
                    pass

                resp = _Resp()
                resp.choices = [_Choice()]
                resp.usage = _Usage()
                return resp


@pytest.fixture(autouse=True)
def _clear_cache():
    default_cache.set(orev._CACHE_KEY, None, ttl=0)
    yield
    default_cache.set(orev._CACHE_KEY, None, ttl=0)


@pytest.fixture
def git_workspace(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    (repo / "a.py").write_text("x = 2\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "bump"], cwd=repo, check=True)
    return repo


def test_snapshot_reads_the_real_diff(git_workspace) -> None:
    from minicc import oracle_review as orev_mod

    snap = orev_mod._snapshot(git_workspace)
    assert len(snap["head_short"]) >= 7
    assert snap["branch"] != ""
    assert "a.py" in snap["stat"]
    assert "x = 2" in snap["diff"]
    assert snap["diff_truncated"] is False


def test_live_review_returns_bilingual_with_usage(monkeypatch, git_workspace) -> None:
    _Client.captured = {}
    monkeypatch.setattr("openai.OpenAI", _Client)
    monkeypatch.setenv("MINICC_API_KEY", "test-key")
    monkeypatch.setenv("MINICC_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("MINICC_MODEL", "test-model")

    out = orev.build_workspace_review(workspace=git_workspace)
    assert out["live"] is True
    assert out["zh"] == "中文评审"
    assert out["en"] == "english review"
    assert out["usage"]["cached_tokens"] == 512
    assert out["model"] == "test-model"
    prompt = _Client.captured["messages"][0]["content"]
    assert "diff" in prompt
    assert "x = 2" in prompt
    assert "x = 1" in prompt


def test_broken_wire_returns_live_false(monkeypatch, git_workspace) -> None:
    class _Broken:
        def __init__(self, *a, **k):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("connection refused")

    monkeypatch.setattr("openai.OpenAI", _Broken)
    out = orev.build_workspace_review(workspace=git_workspace)
    assert out["live"] is False
    assert "connection refused" in out["detail"]
    assert out["zh"] == ""
