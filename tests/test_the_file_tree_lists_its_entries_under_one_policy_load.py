"""M8-T542 — the file tree asks its deny rules once per listing, and refuses on an unreadable policy.

``minicc/web.py``'s file-tree route walks the workspace and asks
``audit.deny_rule_covers_path`` about **every entry** (up to `max_entries = 2000`).
That home called ``load_permission_rules`` on each question, so one listing paid
one stat of ``.minicc/permissions.json`` per entry on top of the route's own two
loads.  Measured on the shipped code:

  5 entries  -> 8 stats
  50 entries -> 53 stats        (slope: one load per entry, + 3 for the route)

The same family was fixed twice already - M8-T533 (evidence index) and M8-T536
(snapshot copy) both load the policy once and keep asking the matcher.  This is
the third reader of the same file.

The second defect is inside the home itself: it read the rules and **threw the
load error away**, so a malformed ``permissions.json`` answered "not covered"
for the very path the user had named, while ``tool_denied_by_rule`` answers True
for the same call (M8-T526's fail-closed never reached this door).  Through the
route the inconsistency is currently caught upstream - M8-T344 refuses the whole
view before the walk when the policy cannot be read - so this is defence in
depth, not a live leak, and the fix makes the home agree with the veto anyway.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from minicc.audit import deny_rule_covers_path
from minicc.web import AgentService

RULES_NAME = "permissions.json"
GLOB_RULES = json.dumps({"deny": {"paths": ["secrets/*"], "tools": [], "commands": []}})
BROKEN_RULES = "{not json"


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=1,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )


def _workspace(tmp_path: Path, name: str, entries: int, *, body: str | None) -> Path:
    root = tmp_path / name
    (root / "secrets").mkdir(parents=True)
    (root / "secrets" / "k.txt").write_text("TOP-SECRET\n", encoding="utf-8")
    for number in range(entries):
        (root / f"n{number}.txt").write_text("x\n", encoding="utf-8")
    if body is not None:
        (root / ".minicc").mkdir()
        (root / ".minicc" / RULES_NAME).write_text(body, encoding="utf-8")
    return root


def _listing(workspace: Path) -> tuple[int, dict]:
    """Call the tree route; return (stats of the rules file, the response)."""
    seen = {"stat": 0}
    original = Path.stat

    def counted(self, *args, **kwargs):
        if self.name == RULES_NAME:
            seen["stat"] += 1
        return original(self, *args, **kwargs)

    service = AgentService(workspace, _config())
    Path.stat = counted  # type: ignore[method-assign]
    try:
        result = service.file_tree()
    finally:
        Path.stat = original  # type: ignore[method-assign]
        assert Path.stat is original, "the counter leaked a patch"
        service.shutdown()
    return seen["stat"], result


def _paths(response: dict) -> list[str]:
    return [str(entry.get("path")) for entry in response.get("entries") or []]


def test_the_deny_question_does_not_grow_with_the_entry_count(tmp_path: Path) -> None:
    small_stats, small = _listing(_workspace(tmp_path, "small", 5, body=GLOB_RULES))
    big_stats, big = _listing(_workspace(tmp_path, "big", 50, body=GLOB_RULES))

    assert "secrets" not in _paths(small) and "secrets/k.txt" not in _paths(small)
    assert sorted(_paths(small)) == sorted(f"n{number}.txt" for number in range(5)), _paths(small)
    assert len(_paths(big)) == 50, len(_paths(big))
    assert small_stats >= 1, "the rules file was never consulted (vacuous gate)"
    assert big_stats == small_stats, (
        f"the deny question is asked per entry: {small_stats} stats for 5 entries, "
        f"{big_stats} for 50"
    )


def test_an_unreadable_policy_covers_every_path_at_the_home(tmp_path: Path) -> None:
    """The home agrees with the veto: rules we cannot read cover what they may name."""
    workspace = _workspace(tmp_path, "broken", 1, body=BROKEN_RULES)
    assert deny_rule_covers_path(workspace, "secrets/k.txt") is True
    assert deny_rule_covers_path(workspace, "n0.txt") is True


def test_an_unreadable_policy_refuses_the_paths_it_is_named_and_no_others(tmp_path: Path) -> None:
    """The boundary of the fail-closed clause: a **named** path, never the root.

    The matcher is asked per path, so the refusal has a shape: everything the
    caller names may be covered (the rules are unknown), while the workspace
    root - which no rule pattern can name - is not. An unconditional ``True``
    here would read as "the whole view is denied", which is a different claim
    than the one the route acts on.
    """
    from minicc.audit import deny_rule_covers_path_matcher

    workspace = _workspace(tmp_path, "broken_named", 1, body=BROKEN_RULES)
    covers = deny_rule_covers_path_matcher(workspace)
    assert covers("n0.txt") is True
    assert covers("") is False
    assert deny_rule_covers_path(workspace, "") is False


def test_a_valid_policy_still_covers_only_what_it_named(tmp_path: Path) -> None:
    """Control on the verdict: the rule still draws its own line."""
    workspace = _workspace(tmp_path, "valid", 1, body=GLOB_RULES)
    assert deny_rule_covers_path(workspace, "secrets/k.txt") is True
    assert deny_rule_covers_path(workspace, "secrets") is True
    assert deny_rule_covers_path(workspace, "n0.txt") is False


def test_a_missing_policy_still_lists_the_workspace(tmp_path: Path) -> None:
    """No rules file is the normal case: the path is looked for, nothing hidden."""
    workspace = _workspace(tmp_path, "missing", 3, body=None)
    stats, response = _listing(workspace)
    assert response.get("status") != "error", response
    assert sorted(_paths(response)) == [
        "n0.txt",
        "n1.txt",
        "n2.txt",
        "secrets",
        "secrets/k.txt",
    ], _paths(response)
    assert stats >= 1, "a missing policy still has to be looked for"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
