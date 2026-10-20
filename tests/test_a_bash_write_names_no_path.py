"""M8-T281: a bash write names no path, and the changed set must not stay empty.

The loop collected the changed paths from each write's ``path`` argument.
A bash write has no such argument, so the set stayed empty - and the
satisfiability probe, which asks "does this workspace have a runnable check
for these changed files", answered *no*.  The repository's own pytest was
right there; the model was told the workspace had no objective check, and
the mandatory post-write verification was quietly downgraded.

Which files changed is a fact about the workspace, so the loop asks git.

This door pins:

* a bash write contributes the files git reports as changed;
* the control: a write that names a path still contributes that path;
* the probe now answers "yes" for a workspace that does have a check.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from minicc.agent.loop import _git_changed_paths, _plan_has_runnable_check


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(workspace),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def test_a_bash_write_contributes_the_files_git_reports(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "t@example.test")
    _git(workspace, "config", "user.name", "t")
    (workspace / "app.py").write_text("print('hi')\n", encoding="utf-8")
    _git(workspace, "add", "app.py")
    _git(workspace, "commit", "-m", "init")
    (workspace / "app.py").write_text("print('bye')\n", encoding="utf-8")

    changed = _git_changed_paths(workspace)
    assert "app.py" in changed, f"git's changed files were not reported: {changed}"


def test_the_probe_answers_yes_for_a_workspace_that_has_a_check(tmp_path: Path) -> None:
    """The point of the fix: the probe's answer changes."""
    workspace = tmp_path / "ws"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (workspace / "tests" / "test_app.py").write_text(
        "def test_app():\n    assert True\n", encoding="utf-8"
    )
    # An empty changed set has nothing to map onto a test.
    assert _plan_has_runnable_check(workspace, []) is False
    # The file that actually changed does.
    assert _plan_has_runnable_check(workspace, ["app.py"]) is True


def test_a_non_git_workspace_reports_nothing(tmp_path: Path) -> None:
    """The control: no repository, no answer - and no exception."""
    assert _git_changed_paths(tmp_path) == []


def test_a_missing_workspace_reports_nothing() -> None:
    assert _git_changed_paths(None) == []
    assert _git_changed_paths("") == []


def test_the_loop_asks_git_after_a_bash_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wiring: the loop has to reach for git, not just offer the helper.

    The helper being correct is not the point - the loop has to *call* it
    when a bash write names no path, and the changed set it produces is
    what the satisfiability probe later reads.
    """
    import asyncio

    from minicc.agent.loop import run_agent
    from minicc.llm.base import LLMResponse
    from minicc.tools import build_registry
    from minicc.tools.editor import Editor

    asked: list[object] = []

    def fake_git_changed(workspace: object) -> list[str]:
        asked.append(workspace)
        return ["app.py"]

    monkeypatch.setattr("minicc.agent.loop._git_changed_paths", fake_git_changed)

    class _BashThenStop:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools=None, on_delta=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content=None,
                    tool_calls=[{
                        "id": "call-0",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": json.dumps({"command": "echo hi > app.py"}),
                        },
                    }],
                    finish_reason="tool_calls",
                )
            return LLMResponse(content="done", finish_reason="stop")

    workspace = tmp_path / "ws"
    workspace.mkdir()
    traces: list[dict[str, object]] = []

    asyncio.run(run_agent(
        _BashThenStop(),
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "改一下 app.py"}],
        on_trace=lambda event: traces.append(event),
        workspace=workspace,
    ))

    assert asked, "the loop never asked git which files the bash write changed"
