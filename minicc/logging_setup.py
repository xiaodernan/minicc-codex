"""Central logging configuration and secret redaction (M8-T5).

Before this module ``minicc/`` contained zero ``logging`` usage and ~70
``print()`` calls, so a failed task left no trace beyond the terminal. Rules:

* The default level is ``WARNING`` and the stream is **stderr** — stdout is the
  CLI/REPL protocol channel (see :mod:`minicc.cli_io`) and must stay clean.
* ``MINICC_LOG_LEVEL`` raises or lowers that level; ``MINICC_LOG_FILE`` appends
  the same records to a UTF-8 file so an operator can capture ``DEBUG`` traces.
* Every handler passes records through :class:`SecretRedactionFilter`, which
  scrubs registered credentials (api key, web token) and anything that *looks*
  like a credential. Redaction runs on the formatted message, so it also covers
  secrets embedded in a third-party exception string.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .tools.registry import redact_text

ROOT_NAME = "minicc"
LEVEL_ENV = "MINICC_LOG_LEVEL"
FILE_ENV = "MINICC_LOG_FILE"
DEFAULT_LEVEL = "WARNING"
REDACTED = "[REDACTED:credential]"
#: Any already-rendered redaction marker (ours or ``redact_text``'s labelled
#: forms). Registered-value masking must never run inside one of these.
_MARKER_SPAN_RE = re.compile(r"\[REDACTED[^\]]*\]")
FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
#: Registered secrets shorter than this are ignored — a 3-char token would
#: redact half of an ordinary log line.
MIN_SECRET_LENGTH = 4

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_SECRET_KEY = (
    r"(?:api[_-]?key|apikey|authorization|access[_-]?token|refresh[_-]?token|"
    r"id[_-]?token|session[_-]?token|web[_-]?token|client[_-]?secret|secret|"
    r"password|passwd|cookie|token|key)"
)
# ``?token=abc`` / ``&api_key=abc`` in a URL.
_QUERY_RE = re.compile(rf"(?i)([?&]{_SECRET_KEY}=)([^\s&\"']+)")
# ``"api_key": "abc"`` / ``token: 'abc'``.
_KV_QUOTED_RE = re.compile(rf"(?i)([\"']?{_SECRET_KEY}[\"']?\s*[:=]\s*[\"'])([^\"']*)([\"'])")
# ``api_key=abc`` / ``MINICC_API_KEY: abc`` without quotes. ``[`` is excluded so
# an already-redacted value is never masked a second time.
_KV_BARE_RE = re.compile(rf"(?i)(?<![\w\"'-])({_SECRET_KEY}\s*[:=]\s*)([^\s,;}}\]\[]+)")
# Value shapes (``sk-…``, ``Bearer …``, JWTs, cloud keys) are owned by
# :func:`minicc.tools.registry.redact_text`, the codebase's single rule set;
# the patterns above only add the labelled-key forms that rules miss.
_lock = threading.RLock()
_secrets: set[str] = set()
_configured = False


def register_secret(value: object) -> None:
    """Remember one credential so no log line can echo it back.

    Call sites pass the *resolved* api key / web token; nothing here is ever
    logged, and the registry only exists to mask those exact substrings.
    """
    raw = str(value or "")
    if len(raw) < MIN_SECRET_LENGTH:
        return
    with _lock:
        _secrets.add(raw)


def _registered(text: str) -> str:
    """Replace registered credentials outside of any existing redaction marker.

    ``redact()`` is often handed text an upstream ``redact_text`` call already
    masked. Without the marker guard, a credential whose value happens to be an
    ordinary word (a test suite really did use ``api_key="secret"``) would be
    masked *inside* ``[REDACTED:secret]`` and every pass would grow the line.
    """
    with _lock:
        values = sorted(_secrets, key=len, reverse=True) if _secrets else []
    if not values:
        return text
    parts: list[str] = []
    cursor = 0
    for span in _MARKER_SPAN_RE.finditer(text):
        parts.append(text[cursor : span.start()])
        parts.append(span.group(0))
        cursor = span.end()
    parts.append(text[cursor:])
    # Even indices are unprotected text; odd indices are markers kept as-is.
    for index in range(0, len(parts), 2):
        segment = parts[index]
        for secret in values:
            if secret in segment:
                segment = segment.replace(secret, REDACTED)
        parts[index] = segment
    return "".join(parts)


def redact(text: object) -> str:
    """Return *text* with credentials replaced by ``REDACTED``."""
    rendered = str(text)
    if not rendered:
        return rendered
    rendered = _registered(rendered)
    # Value shapes first: masking ``Authorization:`` alone would leave the
    # bearer token that follows it visible.
    rendered = redact_text(rendered)[0]
    rendered = _QUERY_RE.sub(lambda m: m.group(1) + REDACTED, rendered)
    rendered = _KV_QUOTED_RE.sub(lambda m: m.group(1) + REDACTED + m.group(3), rendered)
    return _KV_BARE_RE.sub(lambda m: m.group(1) + REDACTED, rendered)


class SecretRedactionFilter(logging.Filter):
    """Rewrite the formatted message so secrets never reach a handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:  # noqa: BLE001 - logging must never fail the task
            pass
        return True


def resolve_level(value: object = None) -> int:
    raw = str(value or os.getenv(LEVEL_ENV) or DEFAULT_LEVEL).strip().upper()
    if raw in _LEVELS:
        return _LEVELS[raw]
    if raw.isdigit():
        return max(0, min(50, int(raw)))
    return _LEVELS[DEFAULT_LEVEL]


def configure_logging(
    *,
    level: object = None,
    log_file: object = None,
    force: bool = False,
) -> logging.Logger:
    """Attach the minicc handlers once; returns the ``minicc`` root logger.

    ``force`` re-binds the handlers (tests point ``MINICC_LOG_FILE`` at a
    temporary file) and closes the ones it replaces.
    """
    global _configured
    logger = logging.getLogger(ROOT_NAME)
    if _configured and not force:
        return logger
    resolved_level = resolve_level(level)
    path = str(log_file if log_file is not None else (os.getenv(FILE_ENV) or "")).strip()
    handlers: list[logging.Handler] = []
    file_error: Exception | None = None
    if path:
        try:
            target = Path(path).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(target, encoding="utf-8"))
        except OSError as exc:
            # A log file that cannot be opened must not take the service down;
            # keep the records on stderr and say so once the handlers exist.
            file_error = exc
            handlers.append(logging.StreamHandler(sys.stderr))
    else:
        handlers.append(logging.StreamHandler(sys.stderr))
    if force:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
    for handler in handlers:
        handler.setLevel(resolved_level)
        handler.addFilter(SecretRedactionFilter())
        if handler.formatter is None:
            handler.setFormatter(logging.Formatter(FORMAT))
        logger.addHandler(handler)
    logger.setLevel(resolved_level)
    # The root logger often has its own handlers (pytest, embedding apps);
    # propagate=False keeps minicc records out of them.
    logger.propagate = False
    _configured = True
    if file_error is not None:
        logger.warning(
            "无法写入日志文件 %s，已回退到 stderr: %s", path, file_error
        )
    return logger


#: A third-party transport whose response-body async generator does not stop on
#: ``athrow()`` (httpcore2's ``safe_async_iterate``) makes asyncio print a
#: multi-frame traceback while shutting the loop down - after an answer that was
#: perfectly correct, so the user reads it as a crash. The defect is upstream and
#: we cannot patch a dependency's teardown; the event still has to reach the log,
#: because stdout is the CLI protocol channel (M8-T5) and a stray traceback there
#: is indistinguishable from a failed run.
TEARDOWN_NOISE = "closing of asynchronous generator"


def quiet_loop_teardown() -> None:
    """Route loop-shutdown async-generator errors to the log instead of stderr.

    Call it from inside the coroutine passed to ``asyncio.run``; outside a running
    loop it does nothing, so a caller cannot accidentally install it on the
    wrong loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    previous = loop.get_exception_handler()

    def handler(running_loop: Any, context: Mapping[str, Any]) -> None:
        message = str(context.get("message") or "")
        if TEARDOWN_NOISE in message:
            exception = context.get("exception")
            get_logger("runtime").debug(
                "loop_teardown %s exception=%s",
                message,
                type(exception).__name__ if exception is not None else "-",
            )
            return
        if callable(previous):
            previous(running_loop, context)
        else:
            running_loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a module-scoped logger under the ``minicc`` namespace."""
    configure_logging()
    return logging.getLogger(f"{ROOT_NAME}.{name}" if name else ROOT_NAME)


def describe_event(event: Mapping[str, Any] | None) -> str:
    """Render one task event as stable ``key=value`` pairs for log grepping."""
    item = event if isinstance(event, Mapping) else {}
    detail = item.get("detail")
    fields: list[str] = [
        f"kind={item.get('kind') or 'unknown'}",
        f"code={item.get('code') or '-'}",
        f"name={item.get('name') or '-'}",
        f"status={item.get('status') or '-'}",
        f"phase={item.get('phase') or '-'}",
    ]
    if isinstance(detail, Mapping):
        for key in ("turn", "attempt", "retry", "tool_count", "risk", "authorization"):
            if key in detail:
                fields.append(f"{key}={detail.get(key)}")
    summary = str(item.get("summary") or item.get("observation") or "")
    if summary:
        fields.append(f"summary={summary[:200]!r}")
    return " ".join(fields)


def log_task_event(event: Mapping[str, Any] | None, *, task_id: str = "") -> None:
    """Log one task event; the funnel every executor shares (M8-T5)."""
    get_logger("task").debug(
        "task_event task_id=%s %s", task_id or "-", describe_event(event)
    )


def log_provider_event(event: Mapping[str, Any] | None, *, model: str = "") -> None:
    """Log one provider trace (retry / protocol fallback).

    INFO rather than DEBUG because a retry is operationally notable, and below
    the WARNING default so a flaky network never puts noise on stderr. The CLI
    has no task event funnel, so without this a provider retry would be
    unobservable there.
    """
    get_logger("provider").info(
        "provider_event model=%s %s", model or "-", describe_event(event)
    )


__all__ = [
    "TEARDOWN_NOISE",
    "quiet_loop_teardown",
    "DEFAULT_LEVEL",
    "FILE_ENV",
    "LEVEL_ENV",
    "REDACTED",
    "ROOT_NAME",
    "SecretRedactionFilter",
    "configure_logging",
    "describe_event",
    "get_logger",
    "log_provider_event",
    "log_task_event",
    "redact",
    "register_secret",
    "resolve_level",
]
