"""M8-T290: a deny rule must reach the preview and diff routes too.

``permissions.json``'s deny rules are documented as an absolute veto, and
the agent's own read of a denied path is refused.  The Web face's preview
and diff routes read the same files - through the registry, which never
asks the rules - so a denied path could be read from the browser panel
while the agent was refused it.

This door pins:

* the preview route refuses a denied path;
* the diff route refuses a denied path;
* a workspace-wide diff is refused whenever the deny side names a path
  (it would carry that path's content);
* the controls: a path with no rule still previews, and a workspace with
  no rules still diffs.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from minicc.web import AgentService


def _service(workspace: Path) -> AgentService:
    config = SimpleNamespace(
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
    return AgentService(workspace, config)


def _workspace(tmp_path: Path, *, deny_paths: list[str] | None) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "data").mkdir(parents=True)
    (workspace / "data" / "secret.txt").write_text("TOPSECRET\n", encoding="utf-8")
    (workspace / "public.txt").write_text("hello\n", encoding="utf-8")
    if deny_paths is not None:
        (workspace / ".minicc").mkdir()
        (workspace / ".minicc" / "permissions.json").write_text(
            json.dumps({"deny": {"paths": deny_paths}}), encoding="utf-8"
        )
    return workspace


def test_the_preview_refuses_a_denied_path(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=["data/*"])
    service = _service(workspace)
    try:
        result = service.file_preview("data/secret.txt")
        assert result["status"] == "error", (
            "the preview route served a path the agent would be refused"
        )
        assert "TOPSECRET" not in (result.get("content") or "")
    finally:
        service.shutdown()


def test_the_diff_refuses_a_denied_path(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=["data/*"])
    service = _service(workspace)
    try:
        result = service.changes("data/secret.txt")
        assert result.get("status") == "error", (
            "the diff route served a path the agent would be refused"
        )
    finally:
        service.shutdown()


def test_a_workspace_wide_diff_is_refused_when_a_path_is_denied(tmp_path: Path) -> None:
    """It would carry the denied path's content."""
    workspace = _workspace(tmp_path, deny_paths=["data/*"])
    service = _service(workspace)
    try:
        result = service.changes()
        assert result.get("status") == "error", (
            "the workspace-wide diff carried a denied path's content"
        )
    finally:
        service.shutdown()


def test_a_path_with_no_rule_still_previews(tmp_path: Path) -> None:
    """The control: the gate is a list, not a blanket ban."""
    workspace = _workspace(tmp_path, deny_paths=["data/*"])
    service = _service(workspace)
    try:
        result = service.file_preview("public.txt")
        assert result["status"] == "ok"
        assert "hello" in (result.get("content") or "")
    finally:
        service.shutdown()


def test_a_workspace_with_no_rules_still_diffs(tmp_path: Path) -> None:
    """The control: no rules, no refusal."""
    workspace = _workspace(tmp_path, deny_paths=None)
    service = _service(workspace)
    try:
        result = service.changes()
        assert result.get("status") != "error"
    finally:
        service.shutdown()
