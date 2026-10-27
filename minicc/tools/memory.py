"""M8-T1 long-term memory: MEMORY.md entry tools + prompt index injection.

Storage is plain, human-editable Markdown — one entry per line in
``~/.minicc/MEMORY.md`` (user scope) and ``<workspace>/.minicc/MEMORY.md``
(project scope)::

    - [mem-1a2b3c4d] (created=2026-09-22T10:00:00Z, source=model) content...

Lines that do not match the format (headers, comments, free-form user notes)
are ignored on read, so entries can be hand-edited or deleted and a
malformed line never breaks a run.

System prompts inject an INDEX ONLY (id + date + short excerpt; at >=200
entries the 50 most recent plus an omission note) to keep tokens bounded;
the model recalls full content through memory_read / memory_list. Content
is redacted with ``redact_text`` before it touches disk.

All three tools map to ``readonly`` risk on purpose (same rationale as
``todo_write``): they only ever append agent-internal state under
``.minicc/MEMORY.md``, never user code. The ``scope`` argument is an enum
(``user`` | ``project``), never a path — sensitive ``.minicc/`` credential
files and out-of-workspace absolute targets cannot be addressed through
this tool at all, and any attempt to pass one is rejected as
INVALID_ARGUMENTS.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..atomic_file import read_text_with_retry, replace_with_retry
from ..clock import utc_stamp
from ..config import ConfigError, home_dir
from ..sidecar_lock import hold_sidecar, sidecar_path_for
from .registry import ToolError, ToolParamError, ToolResult, redact_text
from .schemas import untrusted_tags

# M8-T527: the standard library logger, the way ``minicc/tools/editor.py``
# does it - ``minicc.logging_setup`` imports ``minicc.tools.registry``, so
# importing it from here closes a cycle (tools -> logging_setup -> tools).
LOG = logging.getLogger("minicc.memory")

MEMORY_FILE_NAME = "MEMORY.md"
MEMORY_SCOPES = ("user", "project")
MAX_MEMORY_CHARS = 500
MAX_SOURCE_CHARS = 40
INDEX_EXCERPT_CHARS = 100
INDEX_INJECT_ALL_BELOW = 200
INDEX_RECENT_CAP = 50
DEFAULT_LIST_LIMIT = 20

FILE_HEADER = (
    "# minicc 长期记忆（{scope}）\n"
    "# 一行一条：- [mem-id] (created=ISO时间, source=来源) 内容\n"
    "# 可直接删除整行或修改内容；不符合该格式的行会被忽略。\n"
)

ENTRY_RE = re.compile(
    r"^- \[(?P<id>mem-[0-9a-z]{4,16})\]"
    r" \(created=(?P<created>[A-Za-z0-9:T+.-]+)(?:, source=(?P<source>[^)]*))?\)"
    r" ?(?P<content>.*)$"
)

_APPEND_LOCK = threading.Lock()

# M8-T527: the sidecar lock's budget.  The memory file is small and the
# read-modify-write inside the lock is short, so the ceiling is the catalog's
# 40 x 50ms = 2s: long enough for a neighbour that is mid-append, short
# enough that a wedged one does not hang a tool call.
_LOCK_ATTEMPTS = 40
_LOCK_RETRY_DELAY = 0.05

# M8-T527: the read side rides out the same transient refusal with the
# repository's one answer for it (``minicc/atomic_file.py``).  A reader that
# is refused must not answer "there are no memories".
_READ_ATTEMPTS = 24
_READ_RETRY_DELAY = 0.05


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    content: str
    created: str
    source: str
    scope: str

    def to_line(self) -> str:
        return (
            f"- [{self.id}] (created={self.created}, source={self.source}) {self.content}"
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _collapse(text: object) -> str:
    """Flatten to a single whitespace-normalized line (entries are line-based)."""
    return " ".join(str(text if text is not None else "").split())


def parse_entries(text: str, scope: str) -> list[MemoryEntry]:
    entries: list[MemoryEntry] = []
    for line in text.splitlines():
        match = ENTRY_RE.match(line.strip())
        if not match:
            continue
        content = match.group("content").strip()
        if not content:
            continue
        entries.append(
            MemoryEntry(
                id=match.group("id"),
                content=content,
                created=match.group("created"),
                source=(match.group("source") or "model").strip() or "model",
                scope=scope,
            )
        )
    return entries


class MemoryTools:
    """Workspace- and home-scoped MEMORY.md storage with tool handlers."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)

    def path_for(self, scope: str) -> Path:
        if scope == "user":
            return home_dir() / MEMORY_FILE_NAME
        if scope == "project":
            return self.workspace / ".minicc" / MEMORY_FILE_NAME
        raise ToolParamError(f"scope 非法: {scope!r}（只允许 {'|'.join(MEMORY_SCOPES)}）")

    def _read_file(self, path: Path, scope: str) -> list[MemoryEntry]:
        """Read one scope's entries.

        M8-T527: this used to answer "there are no memories" to a read that
        was *refused* - a neighbouring process holding the file open on
        Windows made ``read_text`` raise, and the answer to that is "I could
        not read it", not "there is nothing there".  Measured on this plane
        with one process appending and one reading: 29 of 519 reads answered
        "no memories" while the file plainly had entries.  The refusal is
        now ridden out with the repository's one answer for a transient
        sharing violation (``minicc/atomic_file.py``); a refusal that
        survives the budget is still reported, because a memory list that
        silently says "none" is a wrong answer.
        """
        try:
            text = read_text_with_retry(path, attempts=_READ_ATTEMPTS, delay=_READ_RETRY_DELAY)
        except FileNotFoundError:
            # No file yet is not a failure: it is an empty memory file.
            return []
        except (OSError, UnicodeError) as exc:
            raise ToolError(
                f"无法读取记忆文件 ({path}): {exc}。"
                "请先修复该文件（编码或权限），再读取记忆。"
            ) from exc
        return parse_entries(text, scope)

    def load(self, scope: str | None = None) -> list[MemoryEntry]:
        """Entries in file order; scope=None merges user + project files."""
        scopes = MEMORY_SCOPES if scope is None else (scope,)
        entries: list[MemoryEntry] = []
        for entry_scope in scopes:
            try:
                path = self.path_for(entry_scope)
            except ToolParamError:
                continue
            entries.extend(self._read_file(path, entry_scope))
        return entries

    def append(self, entry: MemoryEntry) -> None:
        """Append one entry to the memory file, atomically against other processes.

        M8-T527: the read-modify-write below was guarded by ``_APPEND_LOCK``, a
        ``threading.Lock`` - which speaks to this process and to nobody else.
        ``~/.minicc/MEMORY.md`` (user scope) is one file for **every workspace
        on the machine**, and the project scope one is one file for every
        process in that workspace, so two processes that both succeeded still
        dropped each other's entries.  Measured on this plane, two
        barrier-synchronised children appending three entries each, six rounds:
        0 of 6 rounds kept all six entries, and every round kept exactly
        three - one child's worth.  With the sidecar lock around the same
        read-modify-write: 6 of 6 rounds kept all six.

        The lock is held across the read *and* the write, not around one of
        them: a lock around the write alone still lets two processes read the
        same old content and each write it back.

        A refusal is **not** downgraded to an unlocked write.  Losing a
        "recently opened folder" is cosmetic (M8-T265); losing a memory the
        model was told it had stored is not - the entry is gone and nothing
        says so.  So a neighbour that will not let go costs the ceiling and
        then the write is refused with a diagnosis, which is the answer the
        session checkpoint already gives.
        """
        path = self.path_for(entry.scope)
        with _APPEND_LOCK:
            with hold_sidecar(
                sidecar_path_for(path),
                attempts=_LOCK_ATTEMPTS,
                delay=_LOCK_RETRY_DELAY,
            ) as outcome:
                if not outcome.held:
                    raise ToolError(
                        f"记忆文件正被另一个进程占用，本次没有写入 ({path}): {outcome.refusal}。"
                        f"请稍后重试。"
                    )
                self._append_locked(path, entry)

    def _append_locked(
        self, path: Path, entry: MemoryEntry, *, existing: str | None = None
    ) -> None:
        """The read-modify-write itself.  The caller holds the sidecar lock."""
        if existing is None:
            existing = ""
            if path.is_file():
                try:
                    existing = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    # M8-T302: a read failure used to be treated as "the file
                    # is empty", and the write then replaced the whole file
                    # with a header and one new line - every earlier memory
                    # gone, with no error anywhere.  A file we cannot read
                    # is a file we must not overwrite.
                    raise ToolError(
                        f"无法读取记忆文件 ({path}): {exc}。"
                        "请先修复该文件（编码或权限），再写入记忆。"
                    ) from exc
        if not existing:
            existing = FILE_HEADER.format(scope=entry.scope) + "\n"
        if not existing.endswith("\n"):
            existing += "\n"
        payload = existing + entry.to_line() + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{time.time_ns()}.tmp")
        tmp.write_text(payload, encoding="utf-8")
        replace_with_retry(tmp, path, attempts=8, delay=0.005)

    # -- tool handlers -------------------------------------------------------

    def write(self, args: dict[str, Any]) -> ToolResult:
        content = _collapse(args.get("content"))
        if not content:
            raise ToolParamError("content 不能为空或纯空白")
        if len(content) > MAX_MEMORY_CHARS:
            raise ToolParamError(
                f"记忆内容超过 {MAX_MEMORY_CHARS} 字符（收到 {len(content)}）；请压缩成一句结论"
            )
        scope = _collapse(args.get("scope")) or "project"
        if scope not in MEMORY_SCOPES:
            raise ToolParamError(
                f"scope 必须是 {'|'.join(MEMORY_SCOPES)} 之一（收到 {scope!r}）；"
                "记忆只能写入 ~/.minicc/MEMORY.md 或 <工作区>/.minicc/MEMORY.md，"
                "本工具不接受任何路径参数（.minicc/ 敏感文件与工作区外绝对路径一律拒绝）"
            )
        source = _collapse(args.get("source")) or "model"
        source = source[:MAX_SOURCE_CHARS]
        tags = untrusted_tags()
        redacted_content, changed = redact_text(content)
        redacted_source, source_changed = redact_text(source)
        if changed or source_changed:
            tags.append("redacted")
        existing_ids = {entry.id for entry in self.load(scope)}
        entry_id = self._new_id(existing_ids)
        entry = MemoryEntry(
            id=entry_id,
            content=redacted_content,
            created=utc_stamp(),
            source=redacted_source,
            scope=scope,
        )
        self.append(entry)
        summary = f"已写入长期记忆 {entry.id}（scope={scope}）"
        if changed or source_changed:
            summary += "；检测到疑似密钥，已脱敏后落盘"
        return ToolResult(
            status="ok",
            summary=summary,
            output=entry.to_line(),
            data={"entry": entry.to_dict()},
            security_tags=tags,
        )

    def read(self, args: dict[str, Any]) -> ToolResult:
        memory_id = _collapse(args.get("id"))
        if not memory_id:
            raise ToolParamError("id 不能为空")
        scope = self._optional_scope(args.get("scope"))
        matches = [entry for entry in self.load(scope) if entry.id == memory_id]
        if not matches:
            raise ToolError(f"未找到记忆 {memory_id!r}（用 memory_list 查看现有条目）")
        return ToolResult(
            status="ok",
            summary=f"{len(matches)} 条记忆全文（id={memory_id}）",
            output="\n".join(entry.to_line() for entry in matches),
            data={"entries": [entry.to_dict() for entry in matches]},
            security_tags=untrusted_tags(),
        )

    def list_entries(self, args: dict[str, Any]) -> ToolResult:
        scope = self._optional_scope(args.get("scope"))
        query = str(args.get("query") or "")
        try:
            limit = int(args.get("limit") or DEFAULT_LIST_LIMIT)
        except (TypeError, ValueError):
            raise ToolParamError("limit 必须是整数") from None
        limit = max(1, min(100, limit))
        entries = self._recent_first(self.load(scope))
        reason = "recency"
        if query.strip():
            scored = self._score(entries, query)
            if scored is not None:
                entries, reason = scored
        entries = entries[:limit]
        lines = [
            f"- [{entry.scope}] {entry.id} ({entry.created}, source={entry.source}) {entry.content}"
            for entry in entries
        ]
        return ToolResult(
            status="ok",
            summary=(
                f"{len(entries)} 条长期记忆（scope={'all' if scope is None else scope}, "
                f"排序={reason}{', query=' + repr(query) if query.strip() else ''}）"
            ),
            output="\n".join(lines) or "（暂无记忆条目）",
            data={"entries": [entry.to_dict() for entry in entries], "sort": reason},
            security_tags=untrusted_tags(),
        )

    @staticmethod
    def _optional_scope(raw: object) -> str | None:
        scope = _collapse(raw)
        if not scope or scope == "all":
            return None
        if scope not in MEMORY_SCOPES:
            raise ToolParamError(
                f"scope 必须是 {'|'.join(MEMORY_SCOPES)}（或省略/\"all\" 表示两者）"
                f"（收到 {scope!r}）；本工具不接受路径"
            )
        return scope

    @staticmethod
    def _new_id(existing_ids: set[str]) -> str:
        for _ in range(10):
            candidate = f"mem-{secrets.token_hex(4)}"
            if candidate not in existing_ids:
                return candidate
        return f"mem-{secrets.token_hex(6)}"

    @staticmethod
    def _score(
        entries: list[MemoryEntry], query: str
    ) -> tuple[list[MemoryEntry], str] | None:
        """Deterministic keyword recall via retrieval.py's tokenizer.

        Returns ``(entries, "query-score")`` sorted by hit count then
        recency, or None when the query yields no usable terms (then the
        caller falls back to plain recency order).
        """
        from ..agent.retrieval import query_terms  # lazy: agent package imports tools

        terms = query_terms(query)
        if not terms:
            return None
        scored: list[tuple[int, MemoryEntry]] = []
        for entry in entries:
            folded = f"{entry.content} {entry.source} {entry.id}".casefold()
            hits = sum(1 for term in terms if term in folded)
            if hits:
                scored.append((hits, entry))
        # Two stable passes: recency desc first, then hit count desc so ties
        # inside one hit-count group keep the newest-first order.
        scored.sort(key=lambda item: item[1].created, reverse=True)
        ordered = [entry for _, entry in sorted(scored, key=lambda item: -item[0])]
        return ordered, "query-score"

    def _recent_first(self, entries: list[MemoryEntry]) -> list[MemoryEntry]:
        # Reversed file order is the newest-first base; the stable sort on
        # ``created`` keeps it for entries written inside the same second.
        return sorted(reversed(entries), key=lambda entry: entry.created, reverse=True)


def render_memory_index(workspace: Path, *, max_entry_chars: int = INDEX_EXCERPT_CHARS) -> str:
    """System-prompt memory index block ("" when there are no memories).

    Index-only injection keeps prompt tokens bounded; at
    ``INDEX_INJECT_ALL_BELOW`` entries or more only the
    ``INDEX_RECENT_CAP`` most recent lines are shown with an omission note.
    """
    try:
        entries = MemoryTools(workspace).load()
    except ConfigError:
        entries = []
    except ToolError as exc:
        # M8-T527: the tool surface reports a read failure (a model that asked
        # "what do you remember" must not be told "nothing"), but the prompt
        # surface may not die over it: a memory file the user hand-edited into
        # a broken encoding must not make the agent unable to start.  So the
        # prompt degrades - and says so in the log, the way the output-style
        # file does (``minicc/output_style.py``), instead of pretending the
        # workspace has no memories.
        LOG.warning("长期记忆索引读取失败（本次不注入索引）: %s", exc)
        entries = []
    if not entries:
        return ""
    chronological = sorted(entries, key=lambda entry: entry.created)
    omitted = 0
    if len(chronological) >= INDEX_INJECT_ALL_BELOW:
        omitted = len(chronological) - INDEX_RECENT_CAP
        chronological = chronological[-INDEX_RECENT_CAP:]
    lines: list[str] = []
    for entry in chronological:
        excerpt = entry.content
        if len(excerpt) > max_entry_chars:
            excerpt = excerpt[:max_entry_chars] + "…"
        date = entry.created[:10]
        lines.append(f"- [{entry.scope}] {entry.id} ({date}, 来源={entry.source}): {excerpt}")
    if omitted:
        lines.append(
            f"（共 {len(entries)} 条，按省略策略仅展示最近 {INDEX_RECENT_CAP} 条；"
            f"其余 {omitted} 条可用 memory_list(query=...) 检索）"
        )
    return (
        "\n\n长期记忆索引（历史任务沉淀的条目，每次运行从磁盘刷新；"
        "此处仅注入索引行，全文需显式召回）：\n"
        + "\n".join(lines)
        + "\n使用规则：需要全文用 memory_read(id=...)；关键词检索用 memory_list(query=...)"
        "（确定性打分，非语义相似度）；跨任务仍有价值的结论用 memory_write 追加一条。"
        "记忆文件是纯文本（~/.minicc/MEMORY.md 与 <工作区>/.minicc/MEMORY.md），"
        "用户可手工编辑或删除；不要把密钥、令牌或个人隐私写入记忆。\n"
    )


__all__ = [
    "MEMORY_FILE_NAME",
    "MEMORY_SCOPES",
    "MemoryEntry",
    "MemoryTools",
    "parse_entries",
    "render_memory_index",
]
