"""M8-T540 — the mention path loads the deny policy once per message.

M8-T317 gave @-mention injection the deny veto the agent's own reads obey, and
M8-T290 re-checked it on the CJK-converged path.  Both checkpoints asked
``audit.tool_denied_by_rule``, which loads ``.minicc/permissions.json`` twice
per call (once to see whether it is readable, once to match) and stats the
file on every load: a message with N mentions plus one denied path paid
``4N + 2`` stats.  Measured on the shipped code:

  1 mention  -> 6 stats      2 mentions -> 10 stats      8 mentions -> 34 stats
  plain path under an exact rule                -> 2 stats
  the same path with a CJK tail glued on       -> 4 stats (both checkpoints ran)

``audit.denied_by_rule_matcher`` already exists for this shape (M8-T533: load
once, keep asking) and the evidence index and the snapshot copy use it.  The
mention path now does too, so the second checkpoint is free.

What must **not** be lost by the move: the question stays asked (a workspace
with no rules file still consults the path), the converged checkpoint still
catches the glued token the exact rule cannot see, and a policy that cannot be
read still refuses (M8-T526).  Those three are the behavioural legs; the cost
leg is the constancy between two message sizes.
"""

from __future__ import annotations

import json
from pathlib import Path

from minicc.mentions import build_mention_context

RULES_NAME = "permissions.json"
GLOB_RULES = json.dumps({"deny": {"paths": ["secrets/*"], "tools": [], "commands": []}})
EXACT_RULES = json.dumps({"deny": {"paths": ["secrets/k.txt"], "tools": [], "commands": []}})


def _workspace(tmp_path: Path, name: str, mentions: int, *, body: str | None) -> Path:
    root = tmp_path / name
    (root / "secrets").mkdir(parents=True)
    (root / "secrets" / "k.txt").write_text("TOP-SECRET\n", encoding="utf-8")
    for number in range(mentions):
        (root / f"f{number}.txt").write_text("body\n", encoding="utf-8")
    if body is not None:
        (root / ".minicc").mkdir()
        (root / ".minicc" / RULES_NAME).write_text(body, encoding="utf-8")
    return root


def _mentions(count: int) -> str:
    return " ".join(f"@f{number}.txt" for number in range(count))


def _ask(workspace: Path, message: str) -> tuple[int, str, list[dict]]:
    """Run the injection while counting stats of the rules file by name."""
    seen = {"stat": 0}
    original = Path.stat

    def counted(self, *args, **kwargs):
        if self.name == RULES_NAME:
            seen["stat"] += 1
        return original(self, *args, **kwargs)

    Path.stat = counted  # type: ignore[method-assign]
    try:
        block, records = build_mention_context(message, workspace)
    finally:
        Path.stat = original  # type: ignore[method-assign]
        assert Path.stat is original, "the counter leaked a patch"
    return seen["stat"], block, records


def _statuses(records: list[dict]) -> dict[str, str]:
    return {item["token"]: item["status"] for item in records}


def test_the_deny_question_does_not_grow_with_the_mention_count(tmp_path: Path) -> None:
    small = _workspace(tmp_path, "small", 2, body=GLOB_RULES)
    big = _workspace(tmp_path, "big", 8, body=GLOB_RULES)
    message = "@secrets/k.txt 请看 "

    small_stats, small_block, small_records = _ask(small, message + _mentions(2))
    big_stats, big_block, big_records = _ask(big, message + _mentions(8))

    assert _statuses(small_records) == {
        "secrets/k.txt": "rejected",
        "f0.txt": "injected",
        "f1.txt": "injected",
    }, small_records
    assert [item["path"] for item in big_records if item["status"] == "injected"] == [
        f"f{number}.txt" for number in range(8)
    ]
    assert "TOP-SECRET" not in small_block and "TOP-SECRET" not in big_block
    assert small_stats >= 1, "the rules file was never consulted (vacuous gate)"
    assert big_stats == small_stats, (
        f"the deny question is asked per mention: {small_stats} stats for 2 mentions, "
        f"{big_stats} for 8"
    )


def test_the_two_checkpoints_share_one_policy_load(tmp_path: Path) -> None:
    """The CJK re-check (M8-T290) runs on the matcher the message already loaded.

    ``@secrets/k.txt是什么`` is the shape the exact rule cannot see at the raw
    token: the walk converges onto ``secrets/k.txt``, and the second checkpoint
    is what refuses it.  Under the one-shot call that checkpoint cost two more
    policy loads even when nothing else had changed; here the whole message -
    one plain mention and one glued one - pays a single load pair.
    """
    workspace = _workspace(tmp_path, "glued", 1, body=EXACT_RULES)
    stats, block, records = _ask(workspace, "@f0.txt @secrets/k.txt是什么")

    assert _statuses(records) == {
        "f0.txt": "injected",
        "secrets/k.txt是什么": "rejected",
    }, records
    assert "TOP-SECRET" not in block
    assert "deny 规则不允许注入" in block
    # The matcher already loads once per question (M8-T659/T658); both
    # checkpoints in one message therefore pay a single load for the whole
    # message, not two.  Assert exactly that, and assert single-load by the
    # one-and-only count the refresh test pins.
    assert stats == 1, f"the policy was loaded {stats} times for one message (expected 1)"


def test_a_glob_rule_still_refuses_the_path_it_names(tmp_path: Path) -> None:
    """The control on the verdict itself: the denial is the rule's, not a miss."""
    workspace = _workspace(tmp_path, "one", 1, body=GLOB_RULES)
    _stats, block, records = _ask(workspace, "@f0.txt @secrets/k.txt 请看")
    assert _statuses(records) == {"f0.txt": "injected", "secrets/k.txt": "rejected"}, records
    assert "body" in block and "TOP-SECRET" not in block


def test_a_missing_policy_is_still_consulted_and_still_allows(tmp_path: Path) -> None:
    """No rules file is the normal case: the path is looked for, nothing refused."""
    workspace = _workspace(tmp_path, "missing", 1, body=None)
    stats, block, records = _ask(workspace, "@f0.txt @secrets/k.txt 请看")
    assert stats >= 1, "a missing policy still has to be looked for"
    assert [item["status"] for item in records] == ["injected", "injected"], records
    assert "TOP-SECRET" in block


def test_a_malformed_policy_refuses_every_mention(tmp_path: Path) -> None:
    """Fail-closed (M8-T526) survives the move to the one-shot matcher."""
    workspace = _workspace(tmp_path, "broken", 2, body="{not json")
    _stats, block, records = _ask(workspace, _mentions(2) + " @secrets/k.txt")
    assert all(item["status"] == "rejected" for item in records), records
    assert "TOP-SECRET" not in block
    assert "body" not in block
