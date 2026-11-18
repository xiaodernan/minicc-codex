"""M8-T1218/M8-T1219: codex-style session (per-conversation) cache-affinity
keys and the two-level byte-stable workspace snapshot.

openai/codex routes each Responses session on its thread's session id so the
whole conversation sticks to one gateway affinity shard while parallel lanes
stop thrashing each other; these tests pin the three-tier precedence on both
the provider and the cache keeper (they must agree, or a warm lane is never
the lane the user rides), plus the snapshot's shape caps.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import minicc.cache_keeper as ck
from minicc.llm.openai_provider import OpenAICompatibleProvider
from minicc.prompt import _workspace_inventory


def _provider(session_id: str = "", prompt_cache_key: str = "") -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="https://example.test/v1",
        api_key="sk-test-not-a-real-key",
        model="gpt-test",
        session_id=session_id,
        prompt_cache_key=prompt_cache_key,
    )


def test_session_family_preferred_over_lane_hash() -> None:
    p = _provider(session_id="ws-abc123")
    lane = _provider(session_id="")
    assert p._effective_prompt_cache_key() != lane._effective_prompt_cache_key()
    assert p._effective_prompt_cache_key().startswith("minicc-")
    assert len(p._effective_prompt_cache_key()) == len("minicc-") + 16


def test_session_key_is_stable_per_family_and_distinct_across_families() -> None:
    a = _provider(session_id="ws-a")._effective_prompt_cache_key()
    b = _provider(session_id="ws-a")._effective_prompt_cache_key()
    c = _provider(session_id="ws-b")._effective_prompt_cache_key()
    assert a == b
    assert a != c


def test_explicit_constructor_key_wins_over_session_family() -> None:
    p = _provider(session_id="ws-a", prompt_cache_key="minicc-mine-explicit")
    assert p._effective_prompt_cache_key() == "minicc-mine-explicit"


def test_family_key_matches_sha_derivation() -> None:
    expected = "minicc-" + hashlib.sha256("ws-a".encode()).hexdigest()[:16]
    assert _provider(session_id="ws-a")._effective_prompt_cache_key() == expected


def test_keeper_derivation_mirrors_the_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINICC_PROMPT_CACHE_KEY", raising=False)
    a = ck.derive_family_cache_key("https://x/v1", "m", "ws-a")
    b = ck.derive_family_cache_key("https://x/v1", "m", "ws-a")
    assert a == b
    assert a == "minicc-" + hashlib.sha256("ws-a".encode()).hexdigest()[:16]
    lane = ck.derive_family_cache_key("https://x/v1", "m", "")
    assert lane == ck._derive_cache_key("https://x/v1", "m")


def test_keeper_explicit_env_key_wins_over_session_family(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_PROMPT_CACHE_KEY", "explicit-wins")
    assert ck.derive_family_cache_key("https://x/v1", "m", "ws-a") == "explicit-wins"


def test_inventory_is_two_levels_deep_and_bounded(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("print(1)\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text("# guide\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "pkg.js").write_text("x\n", encoding="utf-8")
    (root / ".minicc").mkdir()
    (root / ".minicc" / "audit.jsonl").write_text("{}\n", encoding="utf-8")
    text = _workspace_inventory(root)
    assert text.startswith("顶层结构：")
    assert "a.py" in text
    assert "guide.md" in text
    assert "pkg.js" not in text      # vendored tree is named, never descended
    assert "audit.jsonl" not in text  # agent state dir is named, never descended
    assert len(text.encode("utf-8")) <= 7_000


def test_inventory_survives_missing_workspace(tmp_path: Path) -> None:
    assert _workspace_inventory(tmp_path / "nope") == ""
