"""Safe file-editing core, adapted from specproof craft/editor.py.

- read_file: line-numbered reads, capped at 2000 lines per call;
  read_file_meta / file_digest additionally return the sha256 digest of the
  file's raw bytes (the freshness anchor for STALE_CONTEXT);
- write_file: whole-file atomic write (temp file + os.replace), existing
  content backed up to .minicc/backup/ first, line-ending convention
  preserved (LF stays LF, CRLF stays CRLF);
- apply_edit: precise substring replace — old must match exactly once; when
  the exact match misses, a whitespace-normalized line match (tabs collapsed
  to spaces, trailing spaces stripped) is tried as a fallback and, if unique,
  is applied against the REAL file text; zero or ambiguous normalized matches
  keep the explicit rejection and nothing touches the disk (drift guard);
- write_file / apply_edit accept an optional expected_digest: when the
  current file digest differs, a StaleContextError (STALE_CONTEXT) refuses
  the write — the user's concurrent edits are never overwritten;
- move/delete: backup first, then act;
- every operation appends an audit line (timestamp/action/path/detail/
  before_digest/after_digest), optionally persisted to an audit.jsonl.

All paths are relative to the workspace root; absolute paths and ".."
escapes are rejected.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

MAX_READ_LINES = 2000

# git status --porcelain: unmerged (conflict) status pairs — plain "D"
# deletions are NOT unmerged, only the documented pair set is.
_UNMERGED_PAIRS = frozenset({"DD", "AU", "UD", "UA", "DU", "AA", "UU"})
_PORCELAIN_LINE_RE = re.compile(r"^([MADRCU?! ]{2})\s+(.*)$")


class EditError(RuntimeError):
    """An edit could not be applied (and nothing was written)."""


class StaleContextError(EditError):
    """expected_digest mismatch: the file changed under the agent.

    STALE_CONTEXT (计划书 §8.2): the agent must re-read / re-plan / ask to
    merge — it may never force-overwrite the user's concurrent edits.
    """

    def __init__(self, path: str, expected: str, actual: str) -> None:
        super().__init__(
            f"STALE_CONTEXT: {path} 的 digest 不匹配 "
            f"(expected {expected[:12]}, actual {actual[:12]}); 拒绝写入, 未落盘"
        )
        self.expected_digest = expected
        self.actual_digest = actual


def sha256_digest(data: bytes) -> str:
    """Canonical content digest — sha256 over the file's raw bytes."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class FileRead:
    """Digest-addressed file read: the freshness anchor for stale checks."""

    path: str
    digest: str
    size: int
    lines: list[tuple[int, str]]


@dataclass(frozen=True)
class AuditEntry:
    timestamp: str
    action: str
    path: str
    detail: str = ""
    before_digest: str = ""
    after_digest: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "path": self.path,
            "detail": self.detail,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
        }


def _default_clock() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _normalize_ws_line(line: str) -> str:
    """Whitespace-normalized line for the relaxed apply_edit anchor (W113):
    every tab collapses to a single space, then trailing spaces are stripped.

    The normalization only decides WHERE the replacement lands — the edit is
    always applied against the real (un-normalized) file text.
    """
    return line.replace("\t", " ").rstrip(" ")


def _relaxed_ws_anchor(text: str, old: str) -> tuple[int, int, int] | None:
    """Relaxed anchor fallback for apply_edit (W113).

    When the exact substring match fails, the old-string may have drifted
    only in whitespace (trailing spaces / tabs), so the file text and old
    are compared line-by-line after _normalize_ws_line. Returns
    (start, end, occurrences): the real-text offsets of the single relaxed
    match plus how many normalized matches exist (an exact match never
    reaches this helper). None means no normalized match at all — the
    caller keeps the original explicit rejection.
    """
    file_text = text.replace("\r\n", "\n")
    file_lines = file_text.split("\n")
    old_text = old.replace("\r\n", "\n")
    old_lines = old_text.split("\n")
    if old_lines and old_lines[-1] == "":
        # A trailing newline in old anchors line CONTENT; the file's own
        # line terminator stays in place after the splice.
        old_lines.pop()
    if not old_lines:
        return None
    needle = [_normalize_ws_line(line) for line in old_lines]
    width = len(needle)
    occurrences = 0
    first_start = 0
    for start_index in range(len(file_lines) - width + 1):
        window = file_lines[start_index : start_index + width]
        if [_normalize_ws_line(line) for line in window] != needle:
            continue
        if occurrences == 0:
            first_start = start_index
        occurrences += 1
    if occurrences == 0:
        return None
    start_offset = len("\n".join(file_lines[:first_start]))
    if first_start > 0:
        start_offset += 1
    end_index = first_start + width
    # The span covers the matched lines' CONTENT only — each line's own
    # terminator stays in the file, exactly like the exact-match path
    # (old without a trailing newline never consumes the line's newline).
    end_offset = len("\n".join(file_lines[:end_index]))
    return start_offset, end_offset, occurrences


class Editor:
    """Workspace-scoped editor with backups and an in-memory audit list."""

    def __init__(
        self,
        workspace: str | Path,
        backup_dir: str | Path | None = None,
        audit_path: str | Path | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.backup_dir = (
            Path(backup_dir) if backup_dir is not None else self.workspace / ".minicc" / "backup"
        )
        self.audit_path = Path(audit_path) if audit_path is not None else None
        self._clock = clock or _default_clock
        self.audit: list[AuditEntry] = []

    # -- internals -------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        raw = Path(path)
        if raw.is_absolute():
            raise EditError(f"路径越界: 不允许绝对路径 ({path})")
        target = (self.workspace / raw).resolve()
        if not target.is_relative_to(self.workspace):
            raise EditError(f"路径越界: {path} 超出 workspace 根")
        return target

    def _audit(
        self,
        action: str,
        path: str,
        detail: str = "",
        *,
        before_digest: str = "",
        after_digest: str = "",
    ) -> None:
        entry = AuditEntry(
            timestamp=self._clock(),
            action=action,
            path=path,
            detail=detail,
            before_digest=before_digest,
            after_digest=after_digest,
        )
        self.audit.append(entry)
        if self.audit_path is None:
            return
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            raise EditError(f"审计写入失败 ({self.audit_path}): {exc}") from exc

    def _backup(self, target: Path) -> None:
        if not target.is_file():
            return
        relative = target.relative_to(self.workspace).as_posix().replace("/", "__")
        stamp = self._clock().replace(":", "").replace("+", "Z").replace("-", "")
        name = f"{relative}.{stamp}.{secrets.token_hex(3)}"
        destination = self.backup_dir / name
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, destination)
        except OSError as exc:
            raise EditError(f"备份失败 ({target}): {exc}") from exc
        digest = self._digest_bytes(target)
        self._audit(
            "backup",
            str(target.relative_to(self.workspace)),
            f"→ {name}",
            before_digest=digest,
        )

    @staticmethod
    def _digest_bytes(target: Path) -> str:
        """sha256 of the file's raw bytes ("" when the file is absent)."""
        if not target.is_file():
            return ""
        try:
            return sha256_digest(target.read_bytes())
        except OSError as exc:
            raise EditError(f"digest 计算失败 ({target}): {exc}") from exc

    def file_digest(self, path: str) -> str:
        """Digest of a workspace-relative path ("" when the file is absent)."""
        return self._digest_bytes(self._resolve(path))

    @staticmethod
    def _detect_newline(target: Path) -> str:
        with target.open("rb") as handle:
            head = handle.read(64 * 1024)
        return "CRLF" if b"\r\n" in head else "LF"

    def _atomic_write(self, target: Path, content: str, style: str) -> None:
        tmp = target.parent / f".{target.name}.{secrets.token_hex(6)}.tmp"
        normalized = content.replace("\r\n", "\n")
        if style == "CRLF":
            normalized = normalized.replace("\n", "\r\n")
        try:
            with tmp.open("w", encoding="utf-8", newline="") as handle:
                handle.write(normalized)
            os.replace(tmp, target)
        except OSError as exc:
            with suppress(OSError):
                tmp.unlink()
            raise EditError(f"原子写失败 ({target}): {exc}") from exc

    # -- public toolset --------------------------------------------------

    def read_file_meta(
        self, path: str, offset: int = 1, limit: int = MAX_READ_LINES
    ) -> FileRead:
        """Line-numbered read PLUS digest/size of the file's raw bytes —
        the freshness anchor for STALE_CONTEXT checks (§8.1)."""
        target = self._resolve(path)
        if not target.is_file():
            raise EditError(f"文件不存在: {path}")
        lines = self.read_file(path, offset=offset, limit=limit)
        raw = target.read_bytes()
        return FileRead(path=path, digest=sha256_digest(raw), size=len(raw), lines=lines)

    def read_file(
        self, path: str, offset: int = 1, limit: int = MAX_READ_LINES
    ) -> list[tuple[int, str]]:
        """Line-numbered read; at most MAX_READ_LINES lines per call.

        Unchanged for backward compatibility — digest-addressed reads use
        read_file_meta()/file_digest().
        """
        if offset < 1:
            raise EditError(f"offset 必须 ≥ 1 (收到 {offset})")
        if limit > MAX_READ_LINES:
            raise EditError(f"limit={limit} 超过单次读取上限 {MAX_READ_LINES}")
        target = self._resolve(path)
        if not target.is_file():
            raise EditError(f"文件不存在: {path}")
        text = target.read_text(encoding="utf-8")
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        window = lines[offset - 1 : offset - 1 + limit]
        result = [(offset + index, line) for index, line in enumerate(window)]
        self._audit(
            "read",
            path,
            f"lines {offset}-{offset + len(window) - 1} ({len(window)} 行)",
            before_digest=self._digest_bytes(target),
        )
        return result

    def _check_expected_digest(
        self, action: str, path: str, target: Path, expected_digest: str | None
    ) -> str:
        """Return the current digest; raise StaleContextError on mismatch.

        expected_digest="" explicitly means "the file must not exist yet".
        A refusal is audited (before_digest only — nothing was written).
        """
        actual = self._digest_bytes(target)
        if expected_digest is not None and actual != expected_digest:
            self._audit(
                action,
                path,
                f"拒绝: STALE_CONTEXT (digest 不匹配: expected {expected_digest[:12]} "
                f"actual {actual[:12]})",
                before_digest=actual,
            )
            raise StaleContextError(path, expected_digest, actual)
        return actual

    def _apply_span(
        self,
        target: Path,
        path: str,
        before: str,
        text: str,
        start: int,
        end: int,
        new: str,
        *,
        detail: str,
    ) -> None:
        """Back up and atomically write text[:start] + new + text[end:].

        Shared by the exact and the whitespace-normalized apply_edit paths;
        the file's own line-ending style is preserved and one audit line is
        appended with the caller-supplied detail.
        """
        style = self._detect_newline(target)
        self._backup(target)
        replaced = text[:start] + new + text[end:]
        self._atomic_write(target, replaced, style)
        normalized = replaced.replace("\r\n", "\n")
        if style == "CRLF":
            normalized = normalized.replace("\n", "\r\n")
        self._audit(
            "edit",
            path,
            detail,
            before_digest=before,
            after_digest=sha256_digest(normalized.encode("utf-8")),
        )

    def write_file(
        self, path: str, content: str, *, expected_digest: str | None = None
    ) -> None:
        """Whole-file atomic write; existing files are backed up first.

        expected_digest (optional): when set and the current file digest
        differs, STALE_CONTEXT refuses the write — the user's concurrent
        edits are never overwritten (§8.2). Omitted -> legacy behavior.
        """
        target = self._resolve(path)
        before = self._check_expected_digest("write", path, target, expected_digest)
        if target.is_file():
            style = self._detect_newline(target)
            self._backup(target)
        else:
            style = "LF"
            target.parent.mkdir(parents=True, exist_ok=True)
        normalized = content.replace("\r\n", "\n")
        if style == "CRLF":
            normalized = normalized.replace("\n", "\r\n")
        self._atomic_write(target, content, style)
        after = sha256_digest(normalized.encode("utf-8"))
        self._audit(
            "write",
            path,
            f"{len(content)} chars",
            before_digest=before,
            after_digest=after,
        )

    def apply_edit(
        self, path: str, old: str, new: str, *, expected_digest: str | None = None
    ) -> None:
        """Precise edit: old must match exactly once or nothing is written.

        Relaxed fallback (W113): when the exact match misses, a
        whitespace-normalized line match (tabs collapsed, trailing spaces
        stripped) anchors the same replacement against the REAL file text;
        ambiguous normalized matches are rejected with the real reason.

        expected_digest (optional): freshness gate evaluated before the
        uniqueness check — a stale context refuses the write (§8.2).
        """
        if old == "":
            raise EditError("apply_edit 的 old 不能为空字符串")
        target = self._resolve(path)
        if not target.is_file():
            raise EditError(f"文件不存在: {path}")
        before = self._check_expected_digest("edit", path, target, expected_digest)
        text = target.read_text(encoding="utf-8")
        count = text.count(old)
        if count == 0:
            relaxed = _relaxed_ws_anchor(text, old)
            if relaxed is not None:
                start, end, relaxed_count = relaxed
                if relaxed_count != 1:
                    self._audit(
                        "edit",
                        path,
                        f"拒绝: old 空白归一化后命中 {relaxed_count} 处, 不唯一",
                        before_digest=before,
                    )
                    raise EditError(
                        f"apply_edit 拒绝: old 空白归一化后命中 {relaxed_count} 处不唯一, "
                        f"未落盘 ({path})"
                    )
                self._apply_span(
                    target,
                    path,
                    before,
                    text,
                    start,
                    end,
                    new,
                    detail=f"替换 1 处 (空白归一化匹配, {len(old)}→{len(new)} chars)",
                )
                return
            self._audit("edit", path, "拒绝: old 未命中任何位置", before_digest=before)
            raise EditError(f"apply_edit 拒绝: old 未命中 ({path})")
        if count > 1:
            self._audit(
                "edit", path, f"拒绝: old 命中 {count} 处, 不唯一", before_digest=before
            )
            raise EditError(f"apply_edit 拒绝: old 命中 {count} 处不唯一, 未落盘 ({path})")
        anchor = text.index(old)
        self._apply_span(
            target,
            path,
            before,
            text,
            anchor,
            anchor + len(old),
            new,
            detail=f"替换 1 处 ({len(old)}→{len(new)} chars)",
        )

    def move(self, src: str, dst: str) -> None:
        source = self._resolve(src)
        destination = self._resolve(dst)
        if not source.is_file():
            raise EditError(f"源文件不存在: {src}")
        if destination.exists():
            raise EditError(f"目标已存在: {dst}")
        before = self._digest_bytes(source)
        self._backup(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(source, destination)
        except OSError as exc:
            raise EditError(f"移动失败 ({src} → {dst}): {exc}") from exc
        self._audit("move", src, f"→ {dst}", before_digest=before)

    def delete(self, path: str) -> None:
        target = self._resolve(path)
        if not target.is_file():
            raise EditError(f"文件不存在: {path}")
        before = self._digest_bytes(target)
        self._backup(target)
        try:
            target.unlink()
        except OSError as exc:
            raise EditError(f"删除失败 ({path}): {exc}") from exc
        self._audit("delete", path, "", before_digest=before)

def classify_workspace_changes(
    status_output: str, *, agent_paths: Iterable[str] = ()
) -> dict[str, list[str]]:
    """Split 'git status --porcelain' output into the three §8.2 buckets.

    - agent_changes: paths the agent itself wrote (caller supplies the
      authoritative list, e.g. the editor audit trail);
    - user_changes: dirty paths the agent did not touch (pre-existing or
      concurrent user edits — the stale-digest guard protects them);
    - unknown: unmerged conflicts, renames, and untracked files that cannot
      be attributed — the caller MUST pause on a non-empty unknown bucket.

    Ignores '!!' (ignored) lines; renames match on the destination path.
    """
    agent = set(agent_paths)
    user_changes: list[str] = []
    agent_changes: list[str] = []
    unknown: list[str] = []
    for raw in status_output.replace("\r\n", "\n").replace("\r", "").split("\n"):
        line = raw.rstrip()
        if not line:
            continue
        match = _PORCELAIN_LINE_RE.match(line)
        if match is None:
            unknown.append(line)
            continue
        codes, rest = match.group(1), match.group(2).strip()
        if codes == "!!":
            continue
        path = rest if codes == "??" else rest.split(" -> ")[-1].strip()
        if path in agent:
            agent_changes.append(path)
            continue
        if codes == "??" or codes in _UNMERGED_PAIRS or " -> " in rest:
            unknown.append(path)
            continue
        user_changes.append(path)
    return {
        "user_changes": _dedupe_ordered(user_changes),
        "agent_changes": _dedupe_ordered(agent_changes),
        "unknown": _dedupe_ordered(unknown),
    }


def _dedupe_ordered(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result
