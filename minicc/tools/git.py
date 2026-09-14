"""Read-only Git inspection tools for the coding-agent loop."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .editor import EditError
from .registry import ToolError, split_output
from .schemas import ToolResult


def _safe_relative(workspace: Path, raw: str) -> str:
    path = Path(raw)
    if path.is_absolute():
        raise EditError(f"路径越界: 不允许绝对路径 ({raw})")
    resolved = (workspace / path).resolve()
    if not resolved.is_relative_to(workspace):
        raise EditError(f"路径越界: {raw} 超出 workspace 根")
    return path.as_posix()


class GitTools:
    """Bound to one workspace and limited to non-mutating Git commands."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

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
            raise ToolError(f"git 命令失败: {exc}") from exc

        output = (completed.stdout or "").strip()
        if completed.stderr.strip():
            output += ("\n" if output else "") + f"[stderr]\n{completed.stderr.strip()}"
        head, tail, truncated = split_output(output)
        if completed.returncode == 0:
            summary = f"git {' '.join(args)} (exit 0)"
            status = "ok"
        else:
            summary = f"[exit {completed.returncode}] git {' '.join(args)}"
            status = "error"
        return ToolResult(
            status=status,
            summary=summary,
            head=head,
            tail=tail,
            truncated=truncated,
            exit_code=completed.returncode,
            security_tags=["untrusted"],
        )

    def status(self, _args: dict[str, object]) -> ToolResult:
        return self._run(["status", "--short", "--branch"])

    def diff(self, args: dict[str, object]) -> ToolResult:
        raw_path = str(args.get("path") or "")
        command = ["diff", "--no-ext-diff"]
        if raw_path:
            command.extend(["--", _safe_relative(self.workspace, raw_path)])
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
        dirty = self._capture(["status", "--porcelain"]).splitlines()
        last_commit = self._capture(["log", "-1", "--format=%h %s (%cr)"])
        lines = [
            f"branch: {branch or '(unknown)'}",
            f"upstream: {upstream or '(none)'}" + (f" [{ahead_behind}]" if ahead_behind else ""),
            f"dirty files: {len(dirty)}",
            f"last commit: {last_commit or '(none)'}",
        ]
        return ToolResult(
            status="ok",
            summary=f"Git 摘要: {branch or '?'}，{len(dirty)} 个未提交文件",
            output="\n".join(lines),
            data={
                "branch": branch,
                "upstream": upstream,
                "ahead_behind": ahead_behind,
                "dirty_count": len(dirty),
                "last_commit": last_commit,
            },
            security_tags=["untrusted"],
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
        output = (completed.stdout or "").strip()
        lines = output.splitlines() if output else []
        # merge-tree --write-tree --name-only: line 1 is the tree oid; in the
        # conflict case the remaining lines are "CONFLICT <msg>" entries and
        # conflicted file paths (exit code 1).
        tree_oid = lines[0] if lines and not lines[0].startswith("CONFLICT") else ""
        conflicts = [line for line in lines[1:] if line.strip()]
        if completed.returncode == 0 and not conflicts:
            body = f"merge {branch} -> HEAD 可以干净合并。"
            data = {"branch": branch, "clean": True, "conflicts": [], "tree": tree_oid}
            summary = f"合并预检通过: {branch} 无冲突"
        else:
            body = "\n".join(conflicts) or (completed.stderr or "").strip() or "merge-tree 失败"
            data = {"branch": branch, "clean": False, "conflicts": conflicts[:50], "tree": tree_oid}
            summary = f"合并预检: {branch} 有 {len(conflicts)} 个冲突项"
        return ToolResult(
            status="ok",
            summary=summary,
            output=body,
            data=data,
            security_tags=["untrusted"],
        )

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
            raise ToolError(f"git 命令失败: {exc}") from exc
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
