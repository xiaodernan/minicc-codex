"""Git tools for the coding-agent loop.

Read-only tools: status, diff, summary, merge_precheck.
Write tools (human-triggered only): stage, commit.
Push/PR are explicitly not provided (per roadmap non-goal).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .editor import resolve_in_workspace
from .registry import ToolError, exit_marker, split_output
from .schemas import TOOL_STATUS_OK, ToolResult, untrusted_tags


def _merge_probe(
    branch: str, clean: bool, conflicts: list[str], tree_oid: str
) -> dict[str, Any]:
    """The one shape of a merge-tree probe result.

    The clean branch and the conflicted branch of the probe hand-wrote
    this four-key record.  A key one copy forgets is a probe whose
    ``tree`` or ``conflicts`` the caller reads as missing - and the
    caller decides whether to attempt the merge from exactly these
    keys.
    """
    return {
        "branch": branch,
        "clean": clean,
        "conflicts": conflicts,
        "tree": tree_oid,
    }


def _safe_relative(workspace: Path, raw: str) -> str:
    resolve_in_workspace(workspace, raw)
    return Path(raw).as_posix()


def git_command_failed(exc: BaseException) -> str:
    """The one wording of the git-command failure verdict.

    Three runners spell this sentence by hand - ``GitTools._run``,
    ``merge_precheck`` and ``_capture`` - so a rename reached the runners
    somebody remembered and the model read a different wording depending on
    which git surface it walked through (M8-T496).
    """
    return f"git 命令失败: {exc}"


class GitTools:
    """Bound to one workspace and limited to non-mutating Git commands."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self._prefix: str | None = None

    def _run(self, args: list[str]) -> ToolResult:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError(git_command_failed(exc)) from exc

        output = (completed.stdout or "").strip()
        if completed.stderr.strip():
            output += ("\n" if output else "") + f"[stderr]\n{completed.stderr.strip()}"
        head, tail, truncated = split_output(output)
        if completed.returncode == 0:
            summary = f"git {' '.join(args)} (exit 0)"
            status = "ok"
        else:
            summary = f"{exit_marker(completed.returncode)} git {' '.join(args)}"
            status = "error"
        return ToolResult(
            status=status,
            summary=summary,
            head=head,
            tail=tail,
            truncated=truncated,
            exit_code=completed.returncode,
            security_tags=untrusted_tags(),
        )

    def _scope(self) -> list[str]:
        """Pathspec that keeps a read inside the workspace.

        Git finds a repository by walking up from the working directory, so a
        workspace that is a subdirectory of a larger checkout would otherwise
        report - and name - files the agent is not allowed to read. Real-run
        evidence: an inspection workspace under the repo listed
        ``../../_check_failures.py`` and friends. ``--show-prefix`` is empty
        exactly at the repository root, where there is nothing to narrow.
        """
        if self._prefix is None:
            self._prefix = self._capture(["rev-parse", "--show-prefix"]).strip()
        return ["--", "."] if self._prefix else []

    def status(self, _args: dict[str, object]) -> ToolResult:
        return self._run(["status", "--short", "--branch", *self._scope()])

    def diff(self, args: dict[str, object]) -> ToolResult:
        raw_path = str(args.get("path") or "")
        command = ["diff", "--no-ext-diff"]
        if raw_path:
            command.extend(["--", _safe_relative(self.workspace, raw_path)])
        else:
            command.extend(self._scope())
        return self._run(command)

    def summary(self, _args: dict[str, object]) -> ToolResult:
        """Branch + dirty-state + recent-commit digest for review surfaces."""
        branch = self._capture(["rev-parse", "--abbrev-ref", "HEAD"])
        upstream = self._capture(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        ahead_behind = ""
        if upstream:
            ahead, behind = self._capture_list(
                ["rev-list", "--left-right", "--count", f"{upstream}...HEAD"]
            )
            ahead_behind = f"behind {ahead}, ahead {behind}"
        dirty = self._capture(["status", "--porcelain", *self._scope()]).splitlines()
        last_commit = self._capture(["log", "-1", "--format=%h %s (%cr)"])
        lines = [
            f"branch: {branch or '(unknown)'}",
            f"upstream: {upstream or '(none)'}" + (f" [{ahead_behind}]" if ahead_behind else ""),
            f"dirty files: {len(dirty)}",
            f"last commit: {last_commit or '(none)'}",
        ]
        return ToolResult(
            status=TOOL_STATUS_OK,
            summary=f"Git 摘要: {branch or '?'}，{len(dirty)} 个未提交文件",
            output="\n".join(lines),
            data={
                "branch": branch,
                "upstream": upstream,
                "ahead_behind": ahead_behind,
                "dirty_count": len(dirty),
                "last_commit": last_commit,
            },
            security_tags=untrusted_tags(),
        )

    def merge_precheck(self, args: dict[str, object]) -> ToolResult:
        """Dry-run a merge with merge-tree; never touches the working tree.

        Returns the conflict count and conflicted paths for a candidate merge
        of ``branch`` into the current HEAD, so the review UI can warn before
        any real merge is attempted. Requires git >= 2.38 for --write-tree.
        """
        branch = str(args.get("branch") or "").strip()
        if not branch or any(ch.isspace() for ch in branch) or branch.startswith("-"):
            raise ToolError("branch 参数非法")
        try:
            completed = subprocess.run(
                ["git", "merge-tree", "--write-tree", "--name-only", "HEAD", branch],
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError(git_command_failed(exc)) from exc
        output = (completed.stdout or "").strip()
        lines = output.splitlines() if output else []
        # merge-tree --write-tree --name-only: line 1 is the tree oid; in the
        # conflict case the remaining lines are "CONFLICT <msg>" entries and
        # conflicted file paths (exit code 1).
        tree_oid = lines[0] if lines and not lines[0].startswith("CONFLICT") else ""
        conflicts = [line for line in lines[1:] if line.strip()]
        if completed.returncode == 0 and not conflicts:
            body = f"merge {branch} -> HEAD 可以干净合并。"
            data = _merge_probe(branch, True, [], tree_oid)
            summary = f"合并预检通过: {branch} 无冲突"
        else:
            body = "\n".join(conflicts) or (completed.stderr or "").strip() or "merge-tree 失败"
            data = _merge_probe(branch, False, conflicts[:50], tree_oid)
            summary = f"合并预检: {branch} 有 {len(conflicts)} 个冲突项"
        return ToolResult(
            status=TOOL_STATUS_OK,
            summary=summary,
            output=body,
            data=data,
            security_tags=untrusted_tags(),
        )

    def stage(self, args: dict[str, object]) -> ToolResult:
        """Stage files for commit (git add). Human-triggered only.

        Args:
            paths: List of file paths to stage. Empty list stages all changes.
        """
        paths = args.get("paths")
        if paths is None:
            paths = []
        if not isinstance(paths, list):
            raise ToolError("paths 必须是数组")
        validated: list[str] = []
        for raw in paths:
            if not isinstance(raw, str):
                raise ToolError("paths 元素必须是字符串")
            candidate = raw.strip()
            if not candidate:
                raise ToolError("paths 元素不能为空")
            validated.append(_safe_relative(self.workspace, candidate))
        command = ["add", "--"]
        if validated:
            command.extend(validated)
        else:
            command.append(".")
        return self._run(command)

    def commit(self, args: dict[str, object]) -> ToolResult:
        """Create a commit from staged changes (git commit). Human-triggered only.

        Hooks run exactly as they do for a human ``git commit``: ``--no-verify``
        is deliberately absent, because pre-commit is where a repository puts
        its secret scanner and conflict-marker gate, and a human approving the
        commit is not approving a bypass of that gate.
        """
        message = str(args.get("message") or "").strip()
        if not message:
            raise ToolError("message 不能为空")
        allow_empty = bool(args.get("allow_empty"))
        command = ["commit"]
        if allow_empty:
            command.append("--allow-empty")
        command.extend(["-m", message])
        return self._run(command)

    def _capture(self, args: list[str]) -> str:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError(git_command_failed(exc)) from exc
        return (completed.stdout or "").strip()

    def _capture_list(self, args: list[str]) -> tuple[int, int]:
        raw = self._capture(args)
        values: list[int] = []
        for part in raw.split():
            try:
                values.append(int(part))
            except ValueError:
                continue
        while len(values) < 2:
            values.append(0)
        return values[0], values[1]
