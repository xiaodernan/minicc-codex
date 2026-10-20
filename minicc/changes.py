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

from .tools.editor import _MUTATING_ACTIONS
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
#: The audit actions that actually change a file.  ``read``, ``backup`` and
#: ``backup_prune`` touch the workspace but do not change it.  M8-T313: the
#: set is the editor's own - two copies of "did this change the workspace"
#: are two answers waiting to diverge.
_CHANGING_AUDIT_ACTIONS = _MUTATING_ACTIONS
#: M8-T312: how many audit lines the change panel looks at.  A busy audit
#: history pushes older entries out of the window, so the window is
#: disclosed rather than silently shrinking the change list.
_AUDIT_WINDOW_LINES = 500
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
        """Paths the editor **changed**, from the audit trail.

        M8-T300: the action was ignored, so a ``read`` landed in the same
        set as a ``write`` - and the fallback then reported every file the
        agent had merely *read* as "modified", with an empty patch.  The
        audit trail records ``read``/``backup``/``backup_prune`` alongside
        the actions that change a file; only the latter are changes.

        M8-T312: the window is the last 500 lines of the tail, and it is
        applied **after** the read - so a busy audit history (a few hundred
        reads) pushes the writes out of the window, and the change panel
        reports a clean workspace while ``/api/audit`` still shows the
        write.  The window is now disclosed.
        """
        audit = self.workspace / ".minicc" / "audit.jsonl"
        if not audit.is_file():
            return set()
        paths: set[str] = set()
        try:
            # Read a bounded tail; audit histories can be many megabytes.
            with audit.open("rb") as stream:
                stream.seek(max(0, audit.stat().st_size - 256_000))
                tail = stream.read().decode("utf-8", errors="replace")
            lines = tail.splitlines()
            self._audit_window_truncated = len(lines) > _AUDIT_WINDOW_LINES
            for line in lines[-_AUDIT_WINDOW_LINES:]:
                if '"path"' not in line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                action = str(item.get("action") or "").strip().lower()
                if action and action not in _CHANGING_AUDIT_ACTIONS:
                    continue
                path = str(item.get("path") or "").replace("\\", "/")
                if path and not path.startswith(".") and not _ignored_path(path):
                    paths.add(path)
        except (OSError, ValueError, TypeError):
            return set()
        return paths

    def _computed_files(self) -> list[dict[str, Any]]:
        """Every changed file, with its counts.  Not truncated."""
        complete = sorted(self.files_without_diff(), key=lambda item: item["path"].casefold())
        # M8-T306: the cache fingerprint was built from the **truncated**
        # list, so a change to a file past the cap did not invalidate it -
        # the summary kept serving the old additions/deletions.  The
        # signature now covers every file the inspector knows about.
        signature = []
        for item in complete:
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
        # M8-T307: the counts cover **every** file the inspector knows
        # about, not only the ones that fit in the cap.  The list is
        # truncated (and the truncation is disclosed); the totals are not.
        for item in complete:
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

    def files(self) -> list[dict[str, Any]]:
        """The changed files, capped at ``_MAX_FILES``.

        M8-T307: the cap applies to the **list**, not to the numbers.  The
        summary's totals are computed over every file, so a workspace with
        300 changes reports 300 (and the additions that go with them) while
        the list itself shows the first 120 - and the summary says so.
        """
        return self._computed_files()[:_MAX_FILES]

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
        # M8-T304: the status table is keyed by the **resolved** path.  It
        # used to be keyed by the raw spelling, so an audit entry recorded
        # as ``sub/../notes.md`` (or a path through a symlinked directory)
        # put the file under one key while ``diff("notes.md")`` looked it up
        # under another - and the lookup missed, falling back to "clean".
        # The panel said "modified" and the diff said "clean" for the same
        # file.
        status_map: dict[str, str] = {}
        for item in self.files_without_diff():
            key = self._resolved_relative(str(item["path"]))
            if not key:
                # M8-T291: a path that does not resolve inside the workspace
                # (git reports symlinks that point out of the tree) has no
                # key here - and letting ``_resolve`` raise would turn the
                # diff route into a 500.
                key = str(item["path"])
            status_map[key] = str(item.get("status") or "clean")
        status = status_map.get(path, "clean")
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
            # M8-T310: the audit records the **raw** argument the model
            # passed (``sub/../notes.md``), while git records the clean
            # relative path (``notes.md``).  Keying the audit fallback by
            # the raw spelling put the same file into the list twice - once
            # from git and once from the audit - with two different
            # statuses, and the counts were added twice.  Both sources are
            # keyed by the resolved relative path.
            key = self._resolved_relative(path)
            if key and key not in items and (self.workspace / key).is_file():
                items[key] = {"path": key, "status": "modified", "raw": "audit"}
        return list(items.values())

    def _resolved_relative(self, raw_path: str) -> str:
        """The workspace-relative path a raw path names, or "" when outside."""
        try:
            target = self._resolve(str(raw_path))
            return target.relative_to(self.workspace).as_posix()
        except (OSError, ValueError, ChangeError):
            return ""

    def summary(self) -> dict[str, Any]:
        # M8-T305 / T307: the totals cover every changed file; the list is
        # capped and the truncation is disclosed.  ``files()`` used to
        # truncate and the summary used to report the truncated length as
        # the total - so a workspace with 300 changes claimed 120, and the
        # additions/deletions covered only the first 120.
        complete = self._computed_files()
        files = complete[:_MAX_FILES]
        return {
            "files": files,
            "total_files": len(complete),
            "additions": sum(int(item.get("additions") or 0) for item in complete),
            "deletions": sum(int(item.get("deletions") or 0) for item in complete),
            "truncated": len(complete) > len(files),
            "shown_files": len(files),
            # M8-T312: the audit window is disclosed too - a change that
            # fell out of the window is missing, and the panel should say so
            # rather than report a clean workspace.
            "audit_window_truncated": bool(
                getattr(self, "_audit_window_truncated", False)
            ),
            "workspace": self.workspace.as_posix(),
        }


__all__ = ["ChangeError", "ChangeInspector"]
