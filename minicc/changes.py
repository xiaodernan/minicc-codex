"""Workspace change inspection for the web workbench.

Git is the preferred baseline. A fresh interview repository often has no
commit yet, so untracked files fall back to an empty baseline and still get a
useful red/green diff in the UI.
"""

from __future__ import annotations

import difflib
import json
import subprocess
import threading
from collections import OrderedDict
from copy import deepcopy
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
_SUMMARY_CACHE: OrderedDict[str, tuple[object, list[dict[str, Any]]]] = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _ignored_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized in {".git", ".minicc"} or normalized.startswith(_IGNORED_PREFIXES)


class ChangeInspector:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        self._renames: dict[str, str] = {}

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
        code, stdout, _stderr = self._git(["status", "--porcelain=v1", "-z", "-uall"])
        if code != 0:
            return []
        # NUL records preserve spaces, Unicode and embedded newlines. A
        # rename/copy carries destination first and source as the next record.
        records = iter(stdout.split("\0"))
        output = []
        self._renames.clear()
        for raw in records:
            if not raw:
                continue
            if "R" in raw[:2] or "C" in raw[:2]:
                origin = next(records, "")
                self._renames[raw[3:]] = origin
            output.append(raw)
        return output

    @staticmethod
    def _parse_status(raw: str) -> tuple[str, str]:
        code = raw[:2]
        path = raw[3:] if len(raw) > 3 else ""
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
            # Read a bounded tail; audit histories can be many megabytes.
            with audit.open("rb") as stream:
                stream.seek(max(0, audit.stat().st_size - 256_000))
                tail = stream.read().decode("utf-8", errors="replace")
            for line in tail.splitlines()[-500:]:
                if '"path"' not in line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                path = str(item.get("path") or "").replace("\\", "/")
                if path and not path.startswith(".") and not _ignored_path(path):
                    paths.add(path)
        except (OSError, ValueError, TypeError):
            return set()
        return paths

    def files(self) -> list[dict[str, Any]]:
        items = sorted(self.files_without_diff(), key=lambda item: item["path"].casefold())[:_MAX_FILES]
        signature = []
        for item in items:
            try:
                stat = self._resolve(item["path"]).stat()
                signature.append((item["raw"], stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, self._renames.get(item["path"])))
            except (OSError, ChangeError):
                signature.append((item["raw"], None, None))
        # HEAD/index mutations invalidate even when the working file did not
        # change. rev-parse handles linked worktrees without assuming .git/.
        code, head, _ = self._git(["rev-parse", "HEAD"])
        key = str(self.workspace)
        fingerprint = (head if code == 0 else "", tuple(signature))
        with _CACHE_LOCK:
            cached = _SUMMARY_CACHE.get(key)
            if cached and cached[0] == fingerprint:
                _SUMMARY_CACHE.move_to_end(key)
                return deepcopy(cached[1])
        stats = self._numstat()
        output: list[dict[str, Any]] = []
        for item in items:
            counts = stats.get(item["path"], (0, 0))
            try:
                if item["raw"].startswith("??") or code != 0:
                    # Before the first commit HEAD is an empty baseline.
                    # Cached numstat sees only staged content; the worktree
                    # may contain additional edits or a staged-then-deleted file.
                    counts = (len(self._text(self._resolve(item["path"])).splitlines()), 0)
            except ChangeError:
                pass
            output.append({**item, "additions": counts[0], "deletions": counts[1]})
        with _CACHE_LOCK:
            _SUMMARY_CACHE[key] = (fingerprint, deepcopy(output))
            _SUMMARY_CACHE.move_to_end(key)
            while len(_SUMMARY_CACHE) > 16:
                _SUMMARY_CACHE.popitem(last=False)
        return output

    def _numstat(self) -> dict[str, tuple[int, int]]:
        code, stdout, _ = self._git(["diff", "--numstat", "-z", "--find-renames", "HEAD", "--"])
        if code != 0:
            # An unborn repository has no HEAD; staged additions still have
            # meaningful counts and untracked files are counted separately.
            code, stdout, _ = self._git(["diff", "--cached", "--numstat", "-z", "--find-renames", "--"])
        result = {}
        if code == 0:
            records = iter(stdout.split("\0"))
            for record in records:
                parts = record.split("\t", 2)
                if len(parts) == 3:
                    added, deleted, path = parts
                    if not path:
                        next(records, "")
                        path = next(records, "")
                    result[path] = (int(added) if added.isdigit() else 0, int(deleted) if deleted.isdigit() else 0)
        return result

    def _baseline(self, path: str) -> str:
        code, stdout, _stderr = self._git(["show", f"HEAD:{path}"])
        return stdout if code == 0 else ""

    @staticmethod
    def _text(path: Path) -> str:
        if not path.is_file():
            return ""
        try:
            text = path.read_text(encoding="utf-8")
            return "" if "\0" in text else text
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
        before = "" if status == "added" else self._baseline(self._renames.get(path, path))
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
