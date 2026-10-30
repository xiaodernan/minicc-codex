"""One refresh asks `"is this path denied"` from two reads of the rules, and one pass can answer both ways.

``LocalEvidenceIndex._refresh`` asks ``audit.tool_denied_by_rule`` once per
candidate, and that function asked ``permissions.load_permission_rules``
*and then* ``permissions.match_permission_rule`` - each of which loads the
file on its own.  Same shape for ``audit.authorize_tool``: the readability
check and the deny check were two loads.

Measured on this machine before the change (``scratch/probe_537a.py``,
``probe_537c.py``, ``probe_537d.py``):

* a cold build of 20 files stats the rules file **40** times (2.000 per file);
* rewriting ``permissions.json`` after the third record is built splits one
  pass into **3 indexed / 7 denied** - one refresh, two answers about one
  policy, which is the M8-T526 hazard one level down;
* one ``tool_denied_by_rule`` call and one ``authorize_tool`` call each stat
  the file **twice**.

The fix has one shape: a question reads the rules once.  A single call loads
once (``match_rules`` judges rules already in hand), and a pass over many
paths asks ``audit.path_deny_predicate``, which reads once and answers from
that snapshot for every candidate.

These legs pin the count and the uniformity, not the wall clock: the point is
that one question has one answer.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import pytest

from minicc import audit
from minicc.agent import retrieval
from minicc.agent.retrieval import LocalEvidenceIndex

FILES = 6


@contextmanager
def rules_loads():
    """Count ``Path.stat`` calls made *inside* ``load_permission_rules``."""
    counts: Counter = Counter()
    original = Path.stat

    def counted(self, **kwargs):
        counts[sys._getframe(1).f_code.co_name] += 1
        return original(self, **kwargs)

    Path.stat = counted  # type: ignore[method-assign]
    try:
        yield counts
    finally:
        Path.stat = original  # type: ignore[method-assign]
        assert Path.stat is original, "the counter leaked a patch"


def _workspace(root: Path, *, count: int = FILES, deny: list[str] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (root / f"mod_{i}.py").write_text(f"def handler_{i}(payload):\n    return payload\n", encoding="utf-8")
    if deny is not None:
        (root / ".minicc").mkdir(exist_ok=True)
        (root / ".minicc" / "permissions.json").write_text(
            json.dumps({"deny": {"paths": deny}}), encoding="utf-8"
        )
    return root


def test_the_refresh_reads_the_rules_once(tmp_path: Path) -> None:
    """N candidates, one policy: the file is read once, not twice per file."""
    workspace = _workspace(tmp_path / "ws", deny=["secrets/*"])
    with rules_loads() as counts:
        index = LocalEvidenceIndex(workspace, max_files=100)
        census = index.stats()
    assert int(census["files_indexed"]) == FILES, census
    assert counts["load_permission_rules"] == 1, (
        f"the rules file was read {counts['load_permission_rules']} times for {FILES} "
        "candidates; a pass has one policy, so one read is the denominator - zero "
        "means the refresh never asked and the gate is green because nothing was "
        "judged, more than one means the per-file question is still there"
    )


def test_one_question_reads_the_rules_once(tmp_path: Path) -> None:
    """``tool_denied_by_rule`` answered its two sub-questions from two loads."""
    workspace = _workspace(tmp_path / "ws", count=1, deny=["secrets/*"])
    with rules_loads() as counts:
        verdict = audit.tool_denied_by_rule(workspace, "read_file", {"path": "mod_0.py"})
    assert verdict is False, "the rule names secrets/*, so mod_0.py must not be denied"
    assert counts["load_permission_rules"] == 1, (
        f"one deny question loaded the rules {counts['load_permission_rules']} times; "
        "the readability answer and the deny answer are the same read"
    )


def test_the_authorization_decision_reads_the_rules_once(tmp_path: Path) -> None:
    """The enforcement path asked twice as well - the same fix, one load."""
    workspace = _workspace(tmp_path / "ws", count=1, deny=["secrets/*"])
    with rules_loads() as counts:
        decision = audit.authorize_tool(
            "read_file",
            "readonly",
            {"path": "mod_0.py"},
            allow_changes=False,
            allow_network=False,
            workspace=workspace,
        )
    assert decision.allowed is True, decision.reason
    assert counts["load_permission_rules"] == 1, (
        f"one authorization decision loaded the rules {counts['load_permission_rules']} "
        "times; between two loads the file can become unreadable, and the old shape "
        "then matched the empty rules - a veto that fell back to an allow"
    )


def test_the_refresh_judges_every_candidate_by_one_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rules file edited mid-pass must not split one refresh into two answers."""
    workspace = _workspace(tmp_path / "ws", deny=["nothing-here/*"])
    rules_path = workspace / ".minicc" / "permissions.json"

    def write_rules(patterns: list[str]) -> None:
        rules_path.write_text(json.dumps({"deny": {"paths": patterns}}), encoding="utf-8")

    real = LocalEvidenceIndex._build_record
    built = {"n": 0}

    def flipping(self, path, rel, stat):
        record = real(self, path, rel, stat)
        built["n"] += 1
        if built["n"] == 3:
            write_rules(["mod_*.py"])
        return record

    monkeypatch.setattr(LocalEvidenceIndex, "_build_record", flipping)
    index = LocalEvidenceIndex(workspace, max_files=100)
    census = index.stats()
    indexed, denied = int(census["files_indexed"]), int(census["files_denied"])
    assert built["n"] >= 3, built
    assert indexed + denied == FILES, (indexed, denied, census)
    assert (indexed, denied) in {(FILES, 0), (0, FILES)}, (
        f"one refresh answered {indexed} indexed / {denied} denied for the same "
        f"{FILES} candidates; the policy is a property of the pass, so every "
        "candidate in it is judged by the same snapshot"
    )


def test_an_unreadable_policy_still_denies_the_whole_pass(tmp_path: Path) -> None:
    """M8-T526 kept: a policy nobody can read is not a policy that allows."""
    workspace = _workspace(tmp_path / "ws")
    (workspace / ".minicc").mkdir()
    (workspace / ".minicc" / "permissions.json").write_text("{not json", encoding="utf-8")
    index = LocalEvidenceIndex(workspace, max_files=100)
    census = index.stats()
    assert int(census["files_denied"]) == FILES, census
    assert int(census["files_indexed"]) == 0, census


def test_a_rules_file_the_stat_cannot_reach_is_not_no_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``OSError`` on the stat is not ``FileNotFoundError``.

    The old branch collapsed both into "no file, no rules, no error", so a
    policy the process was not allowed to look at silently stopped vetoing -
    the same fail-open M8-T526 closed for a malformed file, one syscall
    earlier.  ``policy_evaluation_error`` is the readout that tells the two
    apart, and the denial path has to inherit the refusal.
    """
    workspace = _workspace(tmp_path / "ws", count=1, deny=["secrets/*"])
    real = Path.stat

    def failing(self, **kwargs):
        if self.name == "permissions.json":
            raise PermissionError(13, "access denied", str(self))
        return real(self, **kwargs)

    monkeypatch.setattr(Path, "stat", failing)

    assert audit.policy_evaluation_error(workspace), "an unreadable policy is a reason"
    assert audit.tool_denied_by_rule(workspace, "read_file", {"path": "mod_0.py"}) is True
    assert audit.path_deny_predicate(workspace)("mod_0.py") is True


def test_no_rules_file_is_still_no_policy(tmp_path: Path) -> None:
    """Control: the missing-file branch keeps its contract."""
    workspace = _workspace(tmp_path / "ws", count=1)
    assert audit.policy_evaluation_error(workspace) == ""
    assert audit.tool_denied_by_rule(workspace, "read_file", {"path": "mod_0.py"}) is False


def test_the_predicate_keeps_the_verdicts_of_the_one_home(tmp_path: Path) -> None:
    """Deny wins over allow; an untouched path is not denied by either form."""
    workspace = _workspace(tmp_path / "ws", count=2, deny=["mod_0.py"])
    (workspace / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": ["mod_0.py"]}, "allow": {"paths": ["mod_0.py", "mod_1.py"]}}),
        encoding="utf-8",
    )
    predicate = audit.path_deny_predicate(workspace)
    assert predicate("mod_0.py") is True, "deny must win over allow"
    assert predicate("mod_1.py") is False, "allow alone is not a deny"
    assert predicate("mod_2.py") is False
    assert audit.tool_denied_by_rule(workspace, "read_file", {"path": "mod_0.py"}) is True
    assert audit.tool_denied_by_rule(workspace, "read_file", {"path": "mod_1.py"}) is False
    assert audit.path_deny_predicate(None)("anything") is False
