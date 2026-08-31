"""Deterministic, structured context compaction for long agent runs.

A coding agent needs more than the last assistant sentence after compaction:
objectives, file paths, digests, verification commands, and failures are
continuation-critical facts.  This module keeps those facts in a bounded JSON
checkpoint while leaving the recent conversation untouched.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from typing import Any

from ..tools.registry import redact_text

COMPACTION_MARKER = "[CONTEXT COMPACTED]"
CHECKPOINT_VERSION = 2
_MAX_ITEMS = 24
_MAX_TEXT = 900
_MAX_OBJECTIVE = 1800
_IMAGE_CONTEXT_CHARS = 1024
_VISUAL_PART_TYPES = frozenset({"image_url", "input_image"})
_DIGEST_RE = re.compile(r"(?i)(?:digest|sha256|hash)[^a-f0-9]{0,20}([a-f0-9]{12,64})")


def _msg_chars(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        for key in ("content", "tool_calls", "name", "tool_call_id"):
            value = message.get(key)
            if isinstance(value, str):
                total += len(value)
            elif isinstance(value, list):
                # A data URL contains the whole image in base64. Counting it
                # as prompt text makes one screenshot trigger compaction on
                # every turn, even though the model receives it as an image.
                total += _content_chars(value) if key == "content" else len(str(value))
    return total


def _content_chars(value: Any) -> int:
    """Estimate text-equivalent size without counting image base64 payloads."""
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(_content_chars(item) for item in value)
    if isinstance(value, dict):
        if str(value.get("type") or "").lower() in _VISUAL_PART_TYPES:
            return _IMAGE_CONTEXT_CHARS
        return sum(len(str(key)) + _content_chars(item) for key, item in value.items())
    return len(str(value)) if value is not None else 0


def message_chars(messages: list[dict[str, Any]]) -> int:
    """Return the approximate wire size used by the compaction guard."""
    return _msg_chars(messages)


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate tokens for gateways that omit usage in streamed responses."""
    chars = _msg_chars(messages)
    return math.ceil(chars / 4) if chars else 0


def _hash_messages(messages: list[dict[str, Any]]) -> str:
    raw = str([(m.get("role"), m.get("content", "")[:80]) for m in messages])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(
            str(item.get("text") or item.get("content") or "")
            for item in value
            if isinstance(item, dict) and item.get("type") in {"text", "input_text"}
        )
    return ""


def _visual_parts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value
        if isinstance(item, dict) and str(item.get("type") or "").lower() in _VISUAL_PART_TYPES
    ]


def has_visual_content(messages: list[dict[str, Any]]) -> bool:
    """Return whether a message history still contains an image part."""
    return any(_visual_parts(message.get("content")) for message in messages)


def _visual_attachment_facts(value: Any) -> list[dict[str, Any]]:
    """Keep stable visual references in checkpoints, never the image bytes."""
    facts: list[dict[str, Any]] = []
    for part in _visual_parts(value):
        part_type = str(part.get("type") or "image_url")
        image = part.get("image_url")
        url = image.get("url") if isinstance(image, dict) else image
        if not url:
            continue
        raw_url = str(url)
        if raw_url.startswith("data:"):
            mime_type = raw_url[5:].split(";", 1)[0].lower() or "image/unknown"
            source = "data_url"
        else:
            mime_type = ""
            source = "url"
        fact: dict[str, Any] = {
            "type": part_type,
            "source": source,
            "fingerprint": hashlib.sha256(raw_url.encode("utf-8", "replace")).hexdigest()[:16],
        }
        if mime_type:
            fact["mime_type"] = mime_type
        if isinstance(image, dict) and image.get("detail"):
            fact["detail"] = str(image["detail"])[:32]
        if fact not in facts:
            facts.append(fact)
    return facts


def _safe(value: Any, limit: int = _MAX_TEXT) -> str:
    text, _ = redact_text(str(value or "").strip())
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _add_unique(items: list[Any], value: Any, *, limit: int = _MAX_ITEMS, text_limit: int = _MAX_TEXT) -> None:
    item = _safe(value, text_limit) if not isinstance(value, dict) else value
    if item and item not in items and len(items) < limit:
        items.append(item)


def _walk_values(value: Any, key: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for child_key, child in value.items():
            found.extend(_walk_values(child, str(child_key).lower()))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_values(child, key))
    elif isinstance(value, str):
        found.append((key, value))
    return found


def _message_facts(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract bounded facts without retaining raw tool output."""
    objectives: list[str] = []
    requirements: list[str] = []
    files: list[str] = []
    digests: list[str] = []
    verification: list[str] = []
    failures: list[str] = []
    progress: list[str] = []
    visual_attachments: list[dict[str, Any]] = []
    tools: Counter[str] = Counter()

    for message in messages:
        role = str(message.get("role") or "")
        content = _text(message.get("content"))
        for visual_fact in _visual_attachment_facts(message.get("content")):
            _add_unique(visual_attachments, visual_fact)
        if COMPACTION_MARKER in content:
            continue
        if role == "user" and content:
            _add_unique(objectives, content, limit=3, text_limit=_MAX_OBJECTIVE)
            for line in content.splitlines():
                if re.search(r"验收|要求|必须|完成|accept|must|should|test", line, re.I):
                    _add_unique(requirements, line, limit=12, text_limit=400)
        if role == "assistant" and content:
            _add_unique(progress, content, limit=8, text_limit=400)

        values: list[tuple[str, str]] = [("message", content)]
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function") or {}
            name = str(function.get("name") or "?")
            tools[name] += 1
            raw_arguments = function.get("arguments") or ""
            parsed: Any = raw_arguments
            if isinstance(raw_arguments, str):
                try:
                    parsed = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    pass
            values.extend(_walk_values(parsed))
        if role == "tool":
            tools[str(message.get("name") or "tool")] += 1
        values.extend(_walk_values(message.get("data")))
        for key, value in values:
            key = key.lower()
            if key in {"path", "file", "file_path", "filename", "workspace_path"}:
                _add_unique(files, value)
            for digest in _DIGEST_RE.findall(value):
                _add_unique(digests, digest, text_limit=64)
            if re.search(r"pytest(?:\s+[^\s]+)*|(?:python\s+)?-m\s+pytest|ruff|mypy|pyright|compile|lint|typecheck", value, re.I):
                _add_unique(verification, value, text_limit=500)
            if re.search(
                r"失败|错误|error|failed|failure|exception|traceback|timed.?out|denied", value, re.I
            ):
                _add_unique(failures, value, limit=10, text_limit=500)

    return {
        "objectives": objectives,
        "requirements": requirements,
        "files": files,
        "digests": digests,
        "verification": verification,
        "failures": failures,
        "progress": progress[-6:],
        "visual_attachments": visual_attachments[:_MAX_ITEMS],
        "tools": [{"name": name, "count": count} for name, count in tools.most_common(12)],
    }


def _parse_checkpoint(message: dict[str, Any]) -> dict[str, Any] | None:
    content = _text(message.get("content"))
    if COMPACTION_MARKER not in content:
        return None
    try:
        value = json.loads(content.split(COMPACTION_MARKER, 1)[1].strip())
    except json.JSONDecodeError:
        return {"legacy_summary": _safe(content, 500)}
    return value if isinstance(value, dict) else {"legacy_summary": _safe(content, 500)}


def _merge_checkpoint(previous: list[dict[str, Any]], facts: dict[str, Any], middle: list[dict[str, Any]]) -> dict[str, Any]:
    old = [parsed for message in previous if (parsed := _parse_checkpoint(message))]

    def values(key: str, limit: int = _MAX_ITEMS) -> list[Any]:
        output: list[Any] = []
        sources = [item.get(key, []) for item in old] + [facts.get(key, [])]
        for source in sources:
            if not isinstance(source, list):
                continue
            for value in source:
                if value not in output and len(output) < limit:
                    output.append(value)
        return output

    checkpoint: dict[str, Any] = {"version": CHECKPOINT_VERSION}
    for key in (
        "objectives",
        "requirements",
        "files",
        "digests",
        "verification",
        "failures",
        "progress",
        "visual_attachments",
        "tools",
    ):
        checkpoint[key] = values(key)
    legacy = values("legacy_summary", limit=3)
    if legacy:
        checkpoint["legacy_summary"] = legacy
    checkpoint["archive"] = {
        "messages": sum(int(item.get("archive", {}).get("messages", 0) or 0) for item in old) + len(middle),
        "characters": sum(int(item.get("archive", {}).get("characters", 0) or 0) for item in old) + _msg_chars(middle),
        "hash": _hash_messages(middle),
    }
    checkpoint["loss_risk"] = [
        "完整工具输出和模型原文已归档，不再默认放入 prompt",
        "未被提取为路径、digest、验证或失败记录的细节可能丢失",
        "视觉附件只在检查点保存引用元数据，原始图片由调用方持久化并在后续请求重新注入",
        "需要精确原文时应重新读取工作区或查看任务 trace",
    ]
    return checkpoint


def _checkpoint_message(checkpoint: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "user",
        "content": COMPACTION_MARKER + "\n" + json.dumps(checkpoint, ensure_ascii=False, separators=(",", ":")),
    }


def compact_with_checkpoint(
    messages: list[dict[str, Any]],
    *,
    threshold: int = 300_000,
    keep_recent: int = 6,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Return compacted messages and a structured checkpoint, if triggered."""
    if _msg_chars(messages) <= threshold:
        return messages, None

    system_msgs: list[dict[str, Any]] = []
    non_system: list[dict[str, Any]] = []
    prior_checkpoints: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "system":
            system_msgs.append(message)
        elif _parse_checkpoint(message) is not None:
            prior_checkpoints.append(message)
        else:
            non_system.append(message)

    if len(non_system) <= keep_recent:
        return messages, None
    middle = non_system[:-keep_recent]
    tail = non_system[-keep_recent:]
    checkpoint = _merge_checkpoint(prior_checkpoints, _message_facts(middle), middle)
    return [*system_msgs, _checkpoint_message(checkpoint), *tail], checkpoint


def compact(messages: list[dict[str, Any]], *, threshold: int = 300_000, keep_recent: int = 6) -> list[dict[str, Any]]:
    """Backward-compatible wrapper returning only the compacted messages."""
    return compact_with_checkpoint(messages, threshold=threshold, keep_recent=keep_recent)[0]


__all__ = [
    "CHECKPOINT_VERSION",
    "COMPACTION_MARKER",
    "compact",
    "compact_with_checkpoint",
    "estimate_tokens",
    "has_visual_content",
    "message_chars",
]
