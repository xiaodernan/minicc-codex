"""Small, explicit Git worktree orchestration for local agent sessions."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class WorktreeError(RuntimeError):
    """A worktree operation could not be completed safely."""


class WorktreeManager:
    """Keep managed worktrees in a sibling directory and never use a shell."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.root = self.workspace.parent / f".{self.workspace.name}-worktrees"

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except OSError as exc:
            raise WorktreeError(f"无法执行 git: {exc}") from exc

    def list(self) -> list[dict[str, Any]]:
        result = self._run(["worktree", "list", "--porcelain"])
        if result.returncode != 0:
            raise WorktreeError((result.stderr or result.stdout).strip() or "git worktree list 失败")
        records: list[dict[str, Any]] = []
        current: dict[str, Any] = {}
        for line in result.stdout.splitlines():
            if not line.strip():
                if current:
                    records.append(self._decorate(current))
                    current = {}
                continue
            key, _, value = line.partition(" ")
            if key == "worktree":
                current["path"] = value
            elif key == "HEAD":
                current["head"] = value
            elif key == "branch":
                current["branch"] = value.removeprefix("refs/heads/")
            elif key == "detached":
                current["branch"] = "(detached)"
            elif key == "locked":
                current["locked"] = True
        if current:
            records.append(self._decorate(current))
        return records

    def _decorate(self, record: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(record.get("path", ""))).resolve()
        return {
            "path": path.as_posix(),
            "name": path.name,
            "head": record.get("head", ""),
            "branch": record.get("branch", "(unknown)"),
            "locked": bool(record.get("locked", False)),
            "managed": path.parent == self.root.resolve(),
        }

    @staticmethod
    def _validate_name(name: str) -> str:
        if not _NAME.fullmatch(name):
            raise WorktreeError("worktree 名称只能包含字母、数字、点、下划线和短横线")
        return name

    def create(self, name: str, branch: str | None = None) -> dict[str, Any]:
        name = self._validate_name(name)
        target = (self.root / name).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise WorktreeError("worktree 路径越界")
        if target.exists():
            raise WorktreeError(f"worktree 已存在: {name}")
        self.root.mkdir(parents=True, exist_ok=True)
        args = ["worktree", "add"]
        if branch:
            if branch.startswith("-") or ".." in branch or any(ch.isspace() for ch in branch):
                raise WorktreeError("branch 名称非法")
            args.extend(["-b", branch])
        args.extend([str(target), "HEAD"])
        result = self._run(args)
        if result.returncode != 0:
            raise WorktreeError((result.stderr or result.stdout).strip() or "git worktree add 失败")
        return next((item for item in self.list() if Path(item["path"]).resolve() == target), self._decorate({"path": str(target), "branch": branch or "(detached)"}))

    def remove(self, name: str, force: bool = False) -> dict[str, Any]:
        name = self._validate_name(name)
        target = (self.root / name).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise WorktreeError("worktree 路径越界")
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(target))
        result = self._run(args)
        if result.returncode != 0:
            raise WorktreeError((result.stderr or result.stdout).strip() or "git worktree remove 失败")
        return {"name": name, "path": target.as_posix(), "removed": True}
