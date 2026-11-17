"""M8-T537: the deny policy is asked once per refresh, not once per file.

The deny side of ``permissions.json`` does not depend on which candidate is
being asked about.  The evidence index nevertheless asked it **twice per
file**: ``audit.tool_denied_by_rule`` first asked "is the policy readable?"
(``policy_evaluation_error``) and then asked "does it deny this path?"
(``match_permission_rule``), and each of those loaded the rules file.  A
1000-file tree therefore cost 2,000 ``stat`` calls on one rules file - the
2.000/file the M8-T533 record attributed to this module.

The second cost is the sharper one.  Two observations per decision means a
rules file that is rewritten (or momentarily unreadable) between them answers
the first half of the tree and the second half differently: the deny side
gives itself two answers to one question.  M8-T526's promise - a policy that
cannot be read is not a policy that allows - holds only for the observation
that noticed the breakage; the second observation still answered "the rules
say nothing" and the call proceeded.

There is one question - "does this snapshot of the policy deny this path?" -
so one refresh takes one snapshot and every file in it is answered from that
snapshot.  The gates below measure the asks (one per refresh, whatever the
file count), the consequence (the deny is applied to every matching file, not
just half of them), and the unreadable-stat branch that used to answer "no
rules, no error".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minicc.agent.retrieval import LocalEvidenceIndex
from minicc.allowlist import empty_rule_side
from minicc.audit import policy_evaluation_error, tool_denied_by_rule


def _rules(*, deny_paths: list[str] | None = None) -> dict[str, dict[str, list[str]]]:
    rules = {"allow": empty_rule_side(), "deny": empty_rule_side()}
    if deny_paths:
        rules["deny"]["paths"] = list(deny_paths)
    return rules


def _package_tree(root: Path, packages: int) -> None:
    for package in range(packages):
        directory = root / f"pkg{package:03d}"
        directory.mkdir(parents=True, exist_ok=True)
        for number in range(10):
            (directory / f"mod_{number}.py").write_text(
                f"def handler_{package}_{number}(payload):\n    return payload\n",
                encoding="utf-8",
            )


def _write_rules(root: Path, body: dict[str, object] | str) -> None:
    directory = root / ".minicc"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "permissions.json").write_text(
        body if isinstance(body, str) else json.dumps(body), encoding="utf-8"
    )


def _rule_file_stats(run) -> int:
    """Count the ``stat`` calls that land on ``permissions.json``.

    This is the syscall the M8-T533 census attributed 2.000/file to, not a
    count of some internal helper - a fix that replaced the helper but still
    stat'ed the rules file once per candidate would stay red.
    """
    counted = 0
    real = Path.stat

    def counting(self, *args, **kwargs):
        nonlocal counted
        if self.name == "permissions.json":
            counted += 1
        return real(self, *args, **kwargs)

    Path.stat = counting  # type: ignore[method-assign]
    try:
        run()
    finally:
        Path.stat = real  # type: ignore[method-assign]
    return counted


def _cold_build(root: Path) -> dict[str, object]:
    return LocalEvidenceIndex(root, max_files=1500).stats()


def test_one_refresh_asks_the_rules_file_once_at_every_scale(tmp_path: Path) -> None:
    """One snapshot per refresh: 100 files and 400 files cost the same one ask.

    Both trees carry a deny rule, so a build that simply stopped asking would
    also stop denying - the two readouts have to agree.
    """
    small = tmp_path / "small"
    _package_tree(small, 10)
    _write_rules(small, _rules(deny_paths=["pkg000/*"]))
    big = tmp_path / "big"
    _package_tree(big, 40)
    _write_rules(big, _rules(deny_paths=["pkg000/*"]))

    small_stats: dict[str, object] = {}

    def build_small() -> None:
        small_stats.update(_cold_build(small))

    small_asks = _rule_file_stats(build_small)
    big_asks = _rule_file_stats(lambda: _cold_build(big))

    assert small_asks == 1, small_asks
    assert big_asks == 1, big_asks
    # The one ask was used: ten files of pkg000 were refused by the rule.
    assert small_stats["files_denied"] == 10, small_stats
    assert small_stats["files_indexed"] == 90, small_stats


def test_one_decision_asks_the_rules_file_once(tmp_path: Path) -> None:
    """The other half of 2.000/file: the decision asked twice by itself.

    A cache hit is not free - the stamp is checked before the cache is read,
    so every ask is a ``stat`` even when the parsed rules are reused.
    """
    _write_rules(tmp_path, _rules(deny_paths=["pkg000/*"]))

    asks = _rule_file_stats(
        lambda: tool_denied_by_rule(tmp_path, "read_file", {"path": "pkg000/mod_0.py"})
    )

    assert asks == 1, asks


def test_a_rules_file_that_breaks_mid_refresh_answers_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One refresh, one answer: an alternating file must not split the tree.

    The standalone stubs stand in for a rules file rewritten between two
    observations.  Before the fix every file asked twice: the first ask was
    fine and the second saw the broken policy, whose empty rules say "nothing
    is denied" - so the whole tree was indexed and the veto vanished.  With
    one snapshot the whole refresh is answered by the first observation.
    """
    _package_tree(tmp_path, 10)
    _write_rules(tmp_path, _rules(deny_paths=["pkg000/*"]))

    valid = (_rules(deny_paths=["pkg000/*"]), "")
    broken = ({"allow": empty_rule_side(), "deny": empty_rule_side()}, "permissions.json 非法: 坏掉了")
    calls = {"n": 0}

    def alternating(_workspace: Path):
        calls["n"] += 1
        return valid if calls["n"] % 2 == 1 else broken

    monkeypatch.setattr("minicc.audit.load_permission_rules", alternating)
    monkeypatch.setattr("minicc.permissions.load_permission_rules", alternating)

    stats = _cold_build(tmp_path)

    assert calls["n"] == 1, calls["n"]
    assert stats["files_denied"] == 10, stats
    assert stats["files_indexed"] == 90, stats


def test_a_rules_file_the_stat_cannot_reach_is_not_no_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``OError`` on the stat is not ``FileNotFoundError``.

    The old branch collapsed both into "no file, no rules, no error", so a
    policy the process was not allowed to look at silently stopped vetoing -
    the same fail-open M8-T526 closed for a malformed file, one syscall
    earlier.
    """
    _write_rules(tmp_path, _rules(deny_paths=["pkg000/*"]))
    real = Path.stat

    def failing(self, *args, **kwargs):
        if self.name == "permissions.json":
            raise PermissionError(13, "access denied", str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", failing)

    assert policy_evaluation_error(tmp_path), "an unreadable policy is a reason"
    assert tool_denied_by_rule(tmp_path, "read_file", {"path": "pkg000/mod_0.py"}) is True


def test_no_rules_file_is_still_no_policy(tmp_path: Path) -> None:
    """Control: the missing-file branch keeps its contract."""
    assert policy_evaluation_error(tmp_path) == ""
    assert tool_denied_by_rule(tmp_path, "read_file", {"path": "pkg000/mod_0.py"}) is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
