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
