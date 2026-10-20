"""M8-T306 — 第二次复核抓到的六条：修了一半的判据、够不着的规则

这一批做完之后做了**第二次独立复核**（专门盯"新引入的统一判据是否真的统一了
所有消费方"）。六条全部属实——三条"修了一半"、两条"新判据只接到了一个
消费方"、一条"死代码与理由写错"。

本门禁钉住其中可观察的部分：

* 一次调用**只携带一个风险**（授权事件、工具事件、hook 载荷、反馈一致）；
* 引号规则对**每条**命令都成立（包括短路分支）；
* 部分摘要也带着**被测文件**（大工作区里变化闸门才不是瞎的）；
* `files_rebuilt` 报的是**实际发生**的次数；
* 通用词集合里没有**永远进不来的**词。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minicc.agent.repair import _GENERIC_TEST_TOKENS, repair_scope
from minicc.agent.tool_policy import is_workspace_write
from minicc.agent.verification_plan import (
    _fold_changed_and_commands,
    safe_verification_command,
    verification_state,
)
from minicc.audit import effective_risk


# --- M8-T306a: one call, one risk --------------------------------------------


def test_the_effective_risk_is_what_the_gate_judged() -> None:
    """The declared risk cannot see the target; the effective one can."""
    arguments = {"scope": "user"}
    assert effective_risk("memory_write", "readonly", arguments) == "write"
    # The declared risk is still what the tool says - the two are different
    # questions, and the gate must ask the second one.
    assert effective_risk("memory_write", "readonly", {"scope": "project"}) == "readonly"


def test_a_write_is_not_a_read_just_because_the_tool_says_so() -> None:
    """The canonical write predicate and the effective risk must agree."""
    arguments = {"scope": "user"}
    assert is_workspace_write("memory_write", arguments, "ok") is False
    assert effective_risk("memory_write", "readonly", arguments) == "write"


# --- M8-T306b: the quote rule reaches every command ---------------------------


def test_a_misparsed_quote_is_refused_for_every_checker() -> None:
    """The rule used to sit behind a short-circuit that the plan's own
    commands went through.

    Two shapes: an **unclosed** quote (the parser refuses it outright) and
    a **balanced** one whose argument still carries a quote (``"we\\"ird.py"``)
    - the second is the one only this rule catches.
    """
    assert safe_verification_command('pytest "we"ird.py"') is False
    assert safe_verification_command('python -m pytest -q "we"ird.py"') is False
    assert safe_verification_command('pytest "we\\"ird.py"') is False, (
        "a balanced command whose argument carries a quote was accepted"
    )


def test_the_ordinary_quoted_command_is_still_accepted() -> None:
    """The control: the quoting mechanism is how every generated command looks."""
    assert safe_verification_command('node --check "app.js"') is True
    assert safe_verification_command('python -m pytest -q "src/app.py"') is True


# --- M8-T306c: the partial digest still carries the files under test ----------


def test_the_partial_digest_carries_the_changed_files(tmp_path: Path) -> None:
    """A scan that stopped early must still see the files under test move."""
    import hashlib

    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "app.py"
    target.write_text("x = 1\n", encoding="utf-8")

    commands = []
    before = hashlib.sha256()
    _fold_changed_and_commands(before, workspace, ["app.py"], commands)
    target.write_text("x = 2\n", encoding="utf-8")
    after = hashlib.sha256()
    _fold_changed_and_commands(after, workspace, ["app.py"], commands)

    assert before.hexdigest() != after.hexdigest(), (
        "the changed file is not in the digest, so the change gate is blind "
        "in the large workspaces where it matters"
    )


def test_the_commands_are_in_the_digest_too(tmp_path: Path) -> None:
    """The control: a different command is a different identity."""
    import hashlib

    from minicc.agent.verification_plan import VerificationCommand

    workspace = tmp_path / "ws"
    workspace.mkdir()
    first = hashlib.sha256()
    _fold_changed_and_commands(first, workspace, [], [VerificationCommand("pytest -q", "pytest")])
    second = hashlib.sha256()
    _fold_changed_and_commands(second, workspace, [], [VerificationCommand("pytest -x", "pytest")])
    assert first.hexdigest() != second.hexdigest()


# --- M8-T306d: the metric reports what happened -----------------------------


def test_the_rebuilt_count_is_not_erased(tmp_path: Path) -> None:
    """The one signal that shows a re-read must survive the early return.

    The count is read from ``refresh()``'s own return value: ``stats()``
    asks the index to make sure it is fresh, and with a zero refresh
    interval that is **another** refresh - which rebuilds nothing and
    would report 0.
    """
    from minicc.agent.retrieval import LocalEvidenceIndex

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.py").write_text("x = 1\n", encoding="utf-8")

    index = LocalEvidenceIndex(workspace, refresh_interval=3600.0)
    index.refresh()
    index._record_built = {
        key: value - 3600 for key, value in index._record_built.items()
    }
    stats = index.refresh()
    assert stats["files_rebuilt"] >= 1, (
        f"the tree was re-read but the metric says otherwise: {stats}"
    )


# --- M8-T306f: the generic words are the ones that can arrive ---------------


def test_the_generic_word_set_has_no_unreachable_member() -> None:
    """A two-character fragment can never reach the token set."""
    assert "py" not in _GENERIC_TEST_TOKENS, (
        "the set advertises a word the token filter can never produce"
    )


def test_the_generic_words_still_do_not_match_a_target() -> None:
    """The control: the false hits are still gone."""
    scope = repair_scope(
        [
            {"write": True, "path": "src/attestation.py"},
            {"write": True, "path": "src/latest/parser.py"},
        ],
        {"failed_tests": ["tests/test_ledger.py::test_sum"]},
    )
    assert scope["reason"] == "changed_file_evidence", scope
