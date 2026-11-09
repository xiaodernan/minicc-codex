"""M8-T536 — one deny question per capture, not one per dirty file.

M8-T350 taught the snapshot to ask ``permissions.json`` about every dirty file
before copying it, through ``audit.tool_denied_by_rule``.  That one-shot home
loads the policy twice per call (once to see whether it is readable, once to
match), and ``load_permission_rules`` stats the rules file on every load - so a
capture paid two stats of ``.minicc/permissions.json`` **per dirty file**.
Measured before the fix on this batch's own probe: 10 stats for 5 dirty files,
100 for 50.

``capture`` now builds ``audit.denied_by_rule_matcher`` once and keeps asking
it; the evaluation error is read once too, which fixes the second clause here:
a policy that cannot be parsed used to be reported as a deny rule that covered
the path - a rule the user never wrote.  The skip reason now names the
unreadable policy.

Both cells are needed: the first proves the cost stops growing, the second
proves the refusal still happens (and says why) when the matcher refuses every
candidate.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from minicc.snapshots import capture

RULES_NAME = "permissions.json"


def _git(workspace: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(workspace), capture_output=True,
        encoding="utf-8", errors="replace",
    )


def _workspace(root: Path, files: int, policy: str) -> None:
    (root / ".minicc").mkdir(parents=True)
    (root / ".minicc" / RULES_NAME).write_text(policy, encoding="utf-8")
    for number in range(files):
        (root / f"m{number}.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "init")
    _git(root, "config", "user.email", "t@example.test")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "seed")
    # Every file is dirty now, so the capture has one question per file to ask.
    for number in range(files):
        (root / f"m{number}.py").write_text("x = 2\n", encoding="utf-8")


def _capture_stats(root: Path) -> tuple[int, int]:
    """Capture once over ``root``; return (rules-file stats, files copied)."""
    seen = {"stat": 0}
    original = Path.stat

    def counted(self, *args, **kwargs):
        if self.name == RULES_NAME:
            seen["stat"] += 1
        return original(self, *args, **kwargs)

    Path.stat = counted  # type: ignore[method-assign]
    try:
        result = capture(root, "t1")
    finally:
        Path.stat = original  # type: ignore[method-assign]
        assert Path.stat is original, "the counter leaked a patch"
    return seen["stat"], len(result.get("files") or [])


def test_the_deny_question_does_not_grow_with_the_file_count(tmp_path: Path) -> None:
    policy = json.dumps({"deny": {"paths": ["secrets/*"]}})
    small = tmp_path / "small"
    big = tmp_path / "big"
    _workspace(small, 5, policy)
    _workspace(big, 50, policy)

    small_stats, small_copied = _capture_stats(small)
    big_stats, big_copied = _capture_stats(big)

    assert (small_copied, big_copied) == (5, 50), (small_copied, big_copied)
    assert small_stats >= 1, "the rules file was never consulted (vacuous gate)"
    assert big_stats == small_stats, (
        f"the deny question is asked per file: {small_stats} stats for "
        f"{small_copied} files, {big_stats} for {big_copied}"
    )


def test_an_unreadable_policy_refuses_every_candidate_and_says_why(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    _workspace(workspace, 3, "{not json")

    result = capture(workspace, "t1")

    assert result.get("files") == [], result
    assert sorted(result.get("skipped") or []) == ["m0.py", "m1.py", "m2.py"], result
    reasons = result.get("skipped_reasons") or {}
    for rel in ("m0.py", "m1.py", "m2.py"):
        reason = str(reasons.get(rel) or "")
        assert "无法读取" in reason and RULES_NAME in reason, (rel, reason)
    copies = list((workspace / ".minicc" / "snapshots" / "t1" / "files").rglob("*"))
    assert copies == [], "a pre-image was written under an unreadable policy"
