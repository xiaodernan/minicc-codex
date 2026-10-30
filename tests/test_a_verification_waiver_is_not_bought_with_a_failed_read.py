"""M8-T547: the no-check waiver may not be bought with a read that failed.

The loop asks git which files a bash write changed.  ``_git_changed_paths``
answered a bare list, and every failure branch answered ``[]`` — timeout, no
git, non-zero exit, and the >64 「cannot tell」 ceiling.  At finish time the
loop asks ``_plan_has_runnable_check(workspace, sorted(changed_paths))``
(measured: ``False`` for ``[]`` even in a workspace that has tests, because an
empty changed set matches no test — ``True`` for ``["app.py"]``).  So the
post-write inspection was accepted as verification and the trace said the
workspace had no runnable objective check, about a workspace whose pytest was
right there and whose ``app.py`` had just been written.

Measured on HEAD before the change: a bash write (names no path), one
``read_file``, then the model says it is done — with ``git status`` failing and
the workspace holding ``app.py`` + ``tests/test_app.py``, the run emitted
``verification_satisfied_by_inspection`` and finished with ``error=None``.

The fix separates 「the tree is clean」 from 「the tree could not be read」:
``_git_changed_paths`` returns ``(paths, reason)``, a workspace that is not a
repository still answers ``([], None)`` — no repository is a fact, not a failed
read, and M8-T58's fallback for checkless workspaces keeps working — and the
waiver requires the read to have succeeded.  The >64 ceiling becomes a reason
too: past it the honest answer is 「cannot tell」, and 「cannot tell」 may not
clear the guard.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.agent.loop import VERIFICATION_GUARD_ERROR, _git_changed_paths, _plan_has_runnable_check, run_agent
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor


class _BashThenInspectThenStop:
    """bash write (no path) -> read_file -> 「done」, and 「done」 after nudges."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, on_delta=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content=None,
                tool_calls=[{
                    "id": "call-0", "type": "function",
                    "function": {"name": "bash", "arguments": json.dumps({"command": "echo hi > app.py"})},
                }],
                finish_reason="tool_calls",
            )
        if self.calls == 2:
            return LLMResponse(
                content=None,
                tool_calls=[{
                    "id": "call-1", "type": "function",
                    "function": {"name": "read_file", "arguments": json.dumps({"path": "app.py"})},
                }],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="done", finish_reason="stop")


def _workspace(root: Path) -> Path:
    workspace = root / "ws"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (workspace / "tests" / "test_app.py").write_text("def test_app():\n    assert True\n", encoding="utf-8")
    return workspace


def _stub_git(monkeypatch: pytest.MonkeyPatch, status) -> None:
    """A repo whose ``rev-parse`` works and whose ``git status`` is ``status()``."""
    real_run = subprocess.run

    def run(argv, *args, **kwargs):
        if isinstance(argv, list) and argv[:2] == ["git", "status"]:
            return status()
        if isinstance(argv, list) and argv[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr("minicc.agent.loop.subprocess.run", run)


def _drive(workspace: Path) -> tuple[list[str], str | None]:
    traces: list[dict[str, object]] = []
    result = asyncio.run(run_agent(
        _BashThenInspectThenStop(),
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "改一下 app.py"}],
        on_trace=lambda event: traces.append(event),
        workspace=workspace,
    ))
    return [str(event.get("code") or "") for event in traces], result.error


def _refused_status():
    return SimpleNamespace(
        returncode=128, stdout="",
        stderr="fatal: detected dubious ownership in repository at '/ws'\n",
    )


def test_a_failed_changed_read_does_not_waive_the_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path)
    # The harm is not hypothetical: this workspace *has* a runnable check for
    # the file the bash write touched.  Only the changed-path read failed.
    assert _plan_has_runnable_check(workspace, ["app.py"]) is True

    _stub_git(monkeypatch, _refused_status)
    codes, error = _drive(workspace)

    assert "verification_satisfied_by_inspection" not in codes, (
        f"读不出改动清单，却把「没有可运行的检查」当成了答案：{codes}"
    )
    assert "verification_required_before_finish" in codes, codes
    assert error == VERIFICATION_GUARD_ERROR, (error, codes)


def test_a_read_that_succeeded_and_found_nothing_still_waives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: an empty list that was actually read keeps M8-T58 alive."""
    workspace = _workspace(tmp_path)

    def clean_tree():
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    _stub_git(monkeypatch, clean_tree)
    codes, error = _drive(workspace)

    assert "verification_satisfied_by_inspection" in codes, codes
    assert error is None, (error, codes)


def test_the_helper_reports_why_it_could_not_read_the_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path)
    _stub_git(monkeypatch, _refused_status)
    paths, reason = _git_changed_paths(workspace)
    assert paths == [] and isinstance(reason, str) and reason, (paths, reason)
    assert "128" in reason and "dubious ownership" in reason, reason


def test_more_changed_files_than_the_ceiling_is_also_a_failed_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M8-T295's 「cannot tell」 used to be spelled ``[]`` — the word for 「clean」.

    Past the ceiling the loop may not clear the guard: the list it has is a
    superset of the write, and an empty answer would say the write changed
    nothing.
    """
    workspace = _workspace(tmp_path)

    def too_busy():
        # ``git status --porcelain`` is one record per line, no ``-z``.
        return SimpleNamespace(
            returncode=0, stdout="".join(f"?? f-{i}.txt\n" for i in range(65)), stderr=""
        )

    _stub_git(monkeypatch, too_busy)
    paths, reason = _git_changed_paths(workspace)
    assert paths == [] and isinstance(reason, str) and reason, (paths, reason)
    assert "65" in reason or "64" in reason, reason


def test_a_workspace_that_is_not_a_repository_is_not_a_failed_read(tmp_path: Path) -> None:
    """No repository is a fact about the workspace, and M8-T58's fallback needs it.

    A checkless non-repo workspace (version.txt) finishes because the plan's
    verdict is empty; if 「not a repository」 raised the failure flag, every such
    task would end in the verification guard instead of finishing.
    """
    workspace = tmp_path / "plain"
    workspace.mkdir()
    paths, reason = _git_changed_paths(workspace)
    assert paths == [] and reason is None, (paths, reason)
