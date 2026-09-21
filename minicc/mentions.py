"""M7-T5: @-mention file references injected into the model's user message.

The Web composer's @-mention popover inserts plain ``@relative/path`` text.
By itself that only tells the model a name; tools would still have to fetch
it. This module turns those tokens into a bounded content block appended to
the user message so the model sees the head of each referenced file.

Security model (same gate as tools/fs.py and Editor._resolve):
- only workspace-relative references are read; absolute / ``~`` / drive paths
  are rejected, and ``resolve() + is_relative_to()`` catches junction escapes
  that name-based checks would miss (M2-T6);
- content is bounded per file and per message; anything beyond is cut at a
  line boundary and marked ``[truncated]``;
- rejected/missing/binary references are annotated but never read.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .tools.fs import _minicc_sensitive_kind
from .tools.registry import redact_text

# ``@`` tokens stop at whitespace *and* full-width punctuation (。、！？：);
# otherwise a hand-typed Chinese sentence would glue onto the path. The
# negative lookbehind keeps emails (``a@b``) out: an @ directly after an
# ASCII letter/digit is never a mention, while CJK/full-width prefix is.
MENTION_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])@([^\s@\u3000-\u303f\uff00-\uffef]+)")
MENTION_MAX_FILES = 10
MENTION_MAX_CHARS_PER_FILE = 6_000
MENTION_MAX_TOTAL_CHARS = 20_000
# Decoding stops being meaningful past this point; we only ever inject the
# first MENTION_MAX_CHARS_PER_FILE characters anyway.
MENTION_READ_BYTES = 32_768
_TRAILING_PUNCTUATION = ".,;:!?)]}>」』\"'”’、。，；：！？）】》"

__all__ = [
    "MENTION_MAX_CHARS_PER_FILE",
    "MENTION_MAX_FILES",
    "MENTION_MAX_TOTAL_CHARS",
    "apply_mentions",
    "build_mention_context",
    "extract_mention_tokens",
]


def extract_mention_tokens(message: str) -> list[str]:
    """Ordered, de-duplicated ``@path`` tokens (bounded by MENTION_MAX_FILES)."""
    tokens: list[str] = []
    seen: set[str] = set()
    for match in MENTION_TOKEN_RE.finditer(message or ""):
        token = match.group(1).rstrip(_TRAILING_PUNCTUATION)
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= MENTION_MAX_FILES:
            break
    return tokens


def _reject(token: str, reason: str) -> dict[str, Any]:
    return {"token": token, "path": token, "status": "rejected", "reason": reason, "truncated": False}


def _annotate(token: str, status: str, reason: str) -> dict[str, Any]:
    return {"token": token, "path": token, "status": status, "reason": reason, "truncated": False}


def build_mention_context(
    message: str,
    workspace: Path,
    *,
    max_chars_per_file: int = MENTION_MAX_CHARS_PER_FILE,
    max_total_chars: int = MENTION_MAX_TOTAL_CHARS,
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(block, records)`` for the @-mentions found in ``message``.

    ``block`` is the text to append to the user message (empty when nothing
    was mentioned); ``records`` describe every token's outcome for events.
    """
    tokens = extract_mention_tokens(message)
    records: list[dict[str, Any]] = []
    if not tokens:
        return "", records
    ws = workspace.resolve()
    chunks: list[str] = []
    used = 0
    omitted: list[str] = []
    for token in tokens:
        original = token
        raw = Path(token.replace("\\", "/"))
        # "C:/..." is only absolute on Windows; match drive letters explicitly
        # so the rejection is identical on every platform.
        if raw.is_absolute() or token.startswith("~") or re.match(r"^[A-Za-z]:", token):
            records.append(_reject(token, "绝对路径与主目录引用被拒绝"))
            continue
        # Same .minicc credential gate the file tools enforce (M2-T2).
        sensitive = _minicc_sensitive_kind(token)
        if sensitive == "deny":
            records.append(_reject(token, ".minicc 认证/授权文件不允许注入"))
            continue
        try:
            resolved = (ws / raw).resolve()
        except OSError:
            records.append(_reject(token, "路径无法解析"))
            continue
        if not resolved.is_relative_to(ws):
            records.append(_reject(token, "路径超出工作区范围"))
            continue
        # Hand-typed CJK text can glue onto the token (``@a.py是什么``); walk
        # the token back one character at a time to the longest prefix that
        # resolves to a real workspace file.
        while not resolved.is_file() and token:
            token = token[:-1]
            if not token:
                break
            try:
                resolved = (ws / Path(token.replace("\\", "/"))).resolve()
            except OSError:
                break
            if not resolved.is_relative_to(ws):
                break
        if not token or not resolved.is_file():
            records.append(_annotate(original, "missing", "工作区内没有这个文件"))
            continue
        rel = resolved.relative_to(ws).as_posix()
        remaining = min(max_chars_per_file, max_total_chars - used)
        if remaining <= 0:
            omitted.append(rel)
            records.append(_annotate(token, "omitted", "超出注入预算"))
            continue
        try:
            data = resolved.read_bytes()[:MENTION_READ_BYTES]
        except OSError:
            records.append(_annotate(token, "missing", "文件读取失败"))
            continue
        if b"\x00" in data:
            records.append(_annotate(token, "binary", "二进制文件不注入内容"))
            continue
        text = data.decode("utf-8", errors="ignore").replace("\r\n", "\n")
        if sensitive == "redact":
            text, _ = redact_text(text)
        truncated = False
        if len(data) >= MENTION_READ_BYTES or len(text) > remaining:
            truncated = True
            cut = text[:remaining].rfind("\n")
            text = text[:cut if cut > remaining // 2 else remaining]
            used += len(text)
            chunks.append(f'<file path="{rel}">\n{text}\n[truncated]</file>')
            records.append({"token": token, "path": rel, "status": "injected", "reason": "", "truncated": True})
            continue
        used += len(text)
        chunks.append(f'<file path="{rel}">\n{text}\n</file>')
        records.append({"token": token, "path": rel, "status": "injected", "reason": "", "truncated": False})
    injected = sum(1 for item in records if item["status"] == "injected")
    rejected = sum(1 for item in records if item["status"] == "rejected")
    if injected:
        header = (
            "[用户引用文件] 以下内容按 @-提及自动注入（路径相对工作区，超长部分已截断）；"
            "需要完整内容时请用 read_file 工具重新读取。"
        )
        parts = [header, *chunks]
        for item in records:
            if item["status"] == "rejected":
                parts.append(f'<file path="{item["path"]}" status="rejected">{item["reason"]}</file>')
            elif item["status"] in {"missing", "binary"}:
                parts.append(f'<file path="{item["path"]}" status="{item["status"]}">{item["reason"]}</file>')
        if omitted:
            parts.append(
                "[truncated] 以下引用超出注入预算，未包含内容，可用 read_file 读取：" + "、".join(omitted)
            )
        return "\n\n".join(parts), records
    if rejected or omitted:
        parts = ["[用户引用文件]"]
        parts.extend(
            f'<file path="{item["path"]}" status="rejected">{item["reason"]}</file>'
            for item in records
            if item["status"] == "rejected"
        )
        if omitted:
            parts.append("[truncated] 以下引用超出注入预算，未包含内容：" + "、".join(omitted))
        return "\n\n".join(parts), records
    return "", records


def apply_mentions(
    message: str,
    workspace: Path,
    *,
    max_chars_per_file: int = MENTION_MAX_CHARS_PER_FILE,
    max_total_chars: int = MENTION_MAX_TOTAL_CHARS,
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(message_for_model, records)`` with the mention block appended."""
    block, records = build_mention_context(
        message,
        workspace,
        max_chars_per_file=max_chars_per_file,
        max_total_chars=max_total_chars,
    )
    if not block:
        return message, records
    return f"{message}\n\n{block}", records
