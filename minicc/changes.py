"""Workspace change inspection for the web workbench.

Git is the preferred baseline. A fresh interview repository often has no
commit yet, so untracked files fall back to an empty baseline and still get a
useful red/green diff in the UI.
"""

from __future__ import annotations

import difflib
import subprocess
from pathlib import Path
from typing import Any

from .tools.registry import redact_text


class ChangeError(RuntimeError):
    """A requested path cannot be inspected safely."""


_IGNORED_PREFIXES = (
    ".git/",
    ".minicc/",
    ".playwright-cli/",
    ".pytest_cache/",
    ".venv/",
    "__pycache__/",
    "minicc.egg-info/",
    "node_modules/",
    "output/",
)
_MAX_FILES = 120


def _ignored_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized in {".git", ".minicc"} or normalized.startswith(_IGNORED_PREFIXES)


class ChangeInspector:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()

    def _resolve(self, raw_path: str) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ChangeError("path 不能为空")
        candidate = Path(raw_path)
        if candidate.is_absolute():
            raise ChangeError("不允许绝对路径")
        resolved = (self.workspace / candidate).resolve()
        if not resolved.is_relative_to(self.workspace):
            raise ChangeError("路径超出工作区")
        return resolved

    def _git(self, args: list[str]) -> tuple[int, str, str]:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return 127, "", "git unavailable"
        return result.returncode, result.stdout, result.stderr

    def _status_lines(self) -> list[str]:
        code, stdout, _stderr = self._git(["status", "--porcelain=v1", "-uall"])
        return stdout.splitlines() if code == 0 else []

    @staticmethod
    def _parse_status(raw: str) -> tuple[str, str]:
        code = raw[:2]
        path = raw[3:].strip() if len(raw) > 3 else ""
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1]
        if code == "??" or "A" in code:
            status = "added"
        elif "D" in code:
            status = "deleted"
        elif "R" in code:
            status = "renamed"
        else:
            status = "modified"
        return status, path

    def _audit_paths(self) -> set[str]:
        audit = self.workspace / ".minicc" / "audit.jsonl"
        if not audit.is_file():
            return set()
        paths: set[str] = set()
        try:
            for line in audit.read_text(encoding="utf-8").splitlines()[-500:]:
                if '"path"' not in line:
                    continue
                import json

                item = json.loads(line)
                path = str(item.get("path") or "").replace("\\", "/")
                if path and not path.startswith(".") and not _ignored_path(path):
                    paths.add(path)
        except (OSError, ValueError, TypeError):
            return set()
        return paths

    def files(self) -> list[dict[str, Any]]:
        items: dict[str, dict[str, Any]] = {}
        for raw in self._status_lines():
            status, path = self._parse_status(raw)
            if not path or _ignored_path(path):
                continue
            items[path] = {"path": path, "status": status, "raw": raw}

        # Non-Git workspaces still expose files changed through the editor.
        for path in self._audit_paths():
            if path not in items and (self.workspace / path).is_file():
                items[path] = {"path": path, "status": "modified", "raw": "audit"}

        output: list[dict[str, Any]] = []
        for item in sorted(items.values(), key=lambda value: str(value["path"]).lower())[:_MAX_FILES]:
            try:
                path = str(item["path"])
                target = self._resolve(path)
                diff = self._diff_for_target(target, path, str(item["status"]))
            except ChangeError:
                diff = {"additions": 0, "deletions": 0}
            output.append({**item, "additions": diff["additions"], "deletions": diff["deletions"]})
        return sorted(output, key=lambda value: str(value["path"]).lower())

    def _baseline(self, path: str) -> str:
        code, stdout, _stderr = self._git(["show", f"HEAD:{path}"])
        return stdout if code == 0 else ""

    @staticmethod
    def _text(path: Path) -> str:
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ""
        except OSError as exc:
            raise ChangeError(f"读取文件失败: {exc}") from exc

    def diff(self, raw_path: str) -> dict[str, Any]:
        target = self._resolve(raw_path)
        path = target.relative_to(self.workspace).as_posix()
        status_map = {str(item["path"]): item for item in self.files_without_diff()}
        status = status_map.get(path, {"status": "clean"})["status"]
        return self._diff_for_target(target, path, status)

    def _diff_for_target(self, target: Path, path: str, status: str) -> dict[str, Any]:
        # Untracked files have no HEAD baseline; avoid a subprocess for each
        # one when the workspace is a fresh interview repository.
        before = "" if status == "added" else self._baseline(path)
        after = self._text(target)
        if not before and target.is_file() and status == "clean":
            before = after

        if not before and not after:
            patch = ""
        else:
            lines = difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
            patch = "\n".join(lines)
        patch, _ = redact_text(patch)
        additions = sum(1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))
        return {
            "path": path,
            "status": status,
            "patch": patch,
            "additions": additions,
            "deletions": deletions,
            "source": "git-or-empty-baseline",
        }

    def files_without_diff(self) -> list[dict[str, Any]]:
        """Return status records without recursively calculating every diff."""
        items: dict[str, dict[str, Any]] = {}
        for raw in self._status_lines():
            status, path = self._parse_status(raw)
            if path and not _ignored_path(path):
                items[path] = {"path": path, "status": status, "raw": raw}
        for path in self._audit_paths():
            if path not in items and (self.workspace / path).is_file():
                items[path] = {"path": path, "status": "modified", "raw": "audit"}
        return list(items.values())

    def summary(self) -> dict[str, Any]:
        files = self.files()
        return {
            "files": files,
            "total_files": len(files),
            "additions": sum(int(item.get("additions") or 0) for item in files),
            "deletions": sum(int(item.get("deletions") or 0) for item in files),
            "workspace": self.workspace.as_posix(),
        }


__all__ = ["ChangeError", "ChangeInspector"]
