"""Configuration loading: .env in cwd → environment → ~/.minicc/config.json.

Precedence (highest wins): explicit constructor args > environment variables >
.env file in the current directory > config file > defaults. Values are plain
strings/ints/bools — no schema machinery, but nothing silently defaults when
the user explicitly set something invalid: a malformed .env line is reported.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

# Default to the configured OpenAI-compatible gateway; callers can still
# override it through environment variables or explicit CLI arguments.
DEFAULT_MODEL = "gpt-5.6-terra"
DEFAULT_BASE_URL = "https://api.247kan.com/v1"
# Task execution has no wall-clock, turn, token, or tool-count budget. Keep
# these fields as ``None`` for backwards-compatible snapshots/config objects.
DEFAULT_MAX_TURNS: int | None = None
DEFAULT_TIMEOUT = 180.0
DEFAULT_LLM_PROTOCOL = "auto"
DEFAULT_PROVIDER_RETRIES = 4
DEFAULT_TASK_RECOVERY_RETRIES = 2
DEFAULT_MAX_DURATION_SECONDS: float | None = None
DEFAULT_MAX_TOOL_CALLS: int | None = None
DEFAULT_SANDBOX_MODE = "host"
DEFAULT_SANDBOX_IMAGE = "python:3.11-slim"
DEFAULT_CONTEXT_WINDOW_TOKENS = 300_000
DEFAULT_MAX_CONCURRENT_TASKS = 8
DEFAULT_REASONING_EFFORT = "high"
REASONING_EFFORTS = frozenset({"low", "mid", "high", "xhigh", "max"})
DEFAULT_MAX_REPAIR_ATTEMPTS = 2
DEFAULT_TASK_HISTORY_LIMIT = 24
DEFAULT_TASK_HISTORY_MAX_AGE_DAYS = 30
DEFAULT_TASK_EVENT_LIMIT = 768
DEFAULT_TASK_STREAM_LIMIT = 16_000
DEFAULT_TASK_USAGE_LIMIT = 64
DEFAULT_TASK_COMPACTION_LIMIT = 64
DEFAULT_TASK_QUEUE_LIMIT = 32
# Context compaction trigger, in characters (~chars/4 ≈ tokens).
DEFAULT_COMPACT_THRESHOLD = 300_000

TRUTHY = frozenset({"1", "true", "yes", "on"})


class ConfigError(RuntimeError):
    """Configuration is missing or malformed."""


def normalize_reasoning_effort(value: str | None, *, default: str = DEFAULT_REASONING_EFFORT) -> str:
    """Normalize UI/env aliases to the five provider effort levels."""
    raw = str(value or default).strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "standard": "mid",
        "medium": "mid",
        "very-high": "xhigh",
        "very high": "xhigh",
        "veryhigh": "xhigh",
        "maximum": "max",
        "高": "high",
        "极高": "xhigh",
        "最高": "max",
    }
    normalized = aliases.get(raw, raw)
    if normalized not in REASONING_EFFORTS:
        raise ValueError(f"reasoning effort 非法: {value!r} (low|mid|high|xhigh|max)")
    return normalized


def home_dir() -> Path:
    override = os.getenv("MINICC_HOME")
    root = Path(override) if override else Path.home() / ".minicc"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line_no, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"{path}:{line_no}: expected KEY=VALUE, got {line!r}")
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass
class Config:
    base_url: str
    api_key: str
    model: str
    reasoning_effort: str = DEFAULT_REASONING_EFFORT
    tool_mode: str = "auto"  # auto | native | envelope
    max_turns: int | None = DEFAULT_MAX_TURNS
    timeout: float = DEFAULT_TIMEOUT
    llm_protocol: str = DEFAULT_LLM_PROTOCOL  # auto | responses | chat_completions
    provider_retries: int = DEFAULT_PROVIDER_RETRIES
    task_recovery_retries: int = DEFAULT_TASK_RECOVERY_RETRIES
    max_duration_seconds: float | None = DEFAULT_MAX_DURATION_SECONDS
    max_tool_calls: int | None = DEFAULT_MAX_TOOL_CALLS
    yolo: bool = False
    compact_threshold: int = DEFAULT_COMPACT_THRESHOLD
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS
    max_concurrent_tasks: int = DEFAULT_MAX_CONCURRENT_TASKS
    max_repair_attempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS
    task_history_limit: int = DEFAULT_TASK_HISTORY_LIMIT
    task_history_max_age_days: int = DEFAULT_TASK_HISTORY_MAX_AGE_DAYS
    task_event_limit: int = DEFAULT_TASK_EVENT_LIMIT
    task_stream_limit: int = DEFAULT_TASK_STREAM_LIMIT
    task_usage_limit: int = DEFAULT_TASK_USAGE_LIMIT
    task_compaction_limit: int = DEFAULT_TASK_COMPACTION_LIMIT
    task_queue_limit: int = DEFAULT_TASK_QUEUE_LIMIT
    sandbox_mode: str = DEFAULT_SANDBOX_MODE
    sandbox_image: str = DEFAULT_SANDBOX_IMAGE

    def describe(self) -> str:
        key = self.api_key
        shown = key if len(key) <= 12 else key[:8] + "..." + key[-4:]
        return (
            f"model={self.model} endpoint={self.base_url} "
            f"tool_mode={self.tool_mode} protocol={self.llm_protocol} "
            f"reasoning={self.reasoning_effort} key={shown}"
        )


def load_config(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    tool_mode: str | None = None,
    yolo: bool | None = None,
) -> Config:
    """Resolve config from args > env (incl. .env) > config file > defaults."""
    file_values: dict[str, str] = {}
    config_file = home_dir() / "config.json"
    if config_file.is_file():
        try:
            file_values = json.loads(config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ConfigError(f"无法读取 {config_file}: {exc}") from exc

    env_values = _parse_env_file(Path(".env"))

    def pick(arg: str | None, env_name: str, file_key: str, default: str) -> str:
        if arg is not None:
            return arg
        for source in (os.environ, env_values, file_values):
            value = source.get(env_name)
            if value:
                return str(value)
            # config.json uses lowercase keys without the prefix
            value = source.get(file_key)
            if value:
                return str(value)
        return default

    resolved_url = pick(base_url, "MINICC_BASE_URL", "base_url", DEFAULT_BASE_URL)
    resolved_key = pick(api_key, "MINICC_API_KEY", "api_key", "")
    resolved_model = pick(model, "MINICC_MODEL", "model", DEFAULT_MODEL)
    raw_reasoning = pick(reasoning_effort, "MINICC_REASONING_EFFORT", "reasoning_effort", DEFAULT_REASONING_EFFORT)
    try:
        resolved_reasoning = normalize_reasoning_effort(raw_reasoning)
    except ValueError as exc:
        raise ConfigError(f"MINICC_REASONING_EFFORT 非法: {exc}") from None
    resolved_mode = pick(tool_mode, "MINICC_TOOL_MODE", "tool_mode", "auto")
    if resolved_mode not in ("auto", "native", "envelope"):
        raise ConfigError(f"MINICC_TOOL_MODE 非法: {resolved_mode!r} (auto|native|envelope)")

    # Task-level execution budgets remain unlimited.  Keep these legacy
    # fields for snapshot and API compatibility, but ignore old environment
    # variables so stale configuration cannot truncate a task.
    max_turns = None
    max_duration_seconds = None
    max_tool_calls = None
    resolved_protocol = pick(None, "MINICC_LLM_PROTOCOL", "llm_protocol", DEFAULT_LLM_PROTOCOL).strip().lower()
    aliases = {"chat": "chat_completions", "completions": "chat_completions", "response": "responses"}
    resolved_protocol = aliases.get(resolved_protocol, resolved_protocol)
    if resolved_protocol not in {"auto", "responses", "chat_completions"}:
        raise ConfigError(
            f"MINICC_LLM_PROTOCOL 非法: {resolved_protocol!r} (auto|responses|chat_completions)"
        )
    raw_provider_retries = pick(None, "MINICC_PROVIDER_RETRIES", "provider_retries", str(DEFAULT_PROVIDER_RETRIES))
    try:
        provider_retries = max(0, min(8, int(raw_provider_retries)))
    except ValueError:
        raise ConfigError(f"MINICC_PROVIDER_RETRIES 不是 0-8 的整数: {raw_provider_retries!r}") from None
    raw_task_retries = pick(None, "MINICC_TASK_RECOVERY_RETRIES", "task_recovery_retries", str(DEFAULT_TASK_RECOVERY_RETRIES))
    try:
        task_recovery_retries = max(0, min(4, int(raw_task_retries)))
    except ValueError:
        raise ConfigError(f"MINICC_TASK_RECOVERY_RETRIES 不是 0-4 的整数: {raw_task_retries!r}") from None

    raw_yolo = pick(None, "MINICC_YOLO", "yolo", "0")
    resolved_yolo = yolo if yolo is not None else raw_yolo.strip().lower() in TRUTHY
    sandbox_mode = pick(None, "MINICC_SANDBOX", "sandbox", DEFAULT_SANDBOX_MODE).strip().lower()
    if sandbox_mode not in {"host", "docker", "auto"}:
        raise ConfigError(f"MINICC_SANDBOX 非法: {sandbox_mode!r} (host|docker|auto)")
    sandbox_image = pick(None, "MINICC_SANDBOX_IMAGE", "sandbox_image", DEFAULT_SANDBOX_IMAGE)

    raw_context_window = pick(None, "MINICC_CONTEXT_WINDOW_TOKENS", "context_window_tokens", str(DEFAULT_CONTEXT_WINDOW_TOKENS))
    try:
        context_window_tokens = max(1, int(raw_context_window))
    except ValueError:
        raise ConfigError(f"MINICC_CONTEXT_WINDOW_TOKENS 不是整数: {raw_context_window!r}") from None
    raw_compact_threshold = pick(None, "MINICC_COMPACT_THRESHOLD", "compact_threshold", str(DEFAULT_COMPACT_THRESHOLD))
    try:
        compact_threshold = max(1, int(raw_compact_threshold))
    except ValueError:
        raise ConfigError(f"MINICC_COMPACT_THRESHOLD 不是整数: {raw_compact_threshold!r}") from None

    raw_max_concurrent = pick(None, "MINICC_MAX_CONCURRENT_TASKS", "max_concurrent_tasks", str(DEFAULT_MAX_CONCURRENT_TASKS))
    try:
        max_concurrent_tasks = max(1, min(64, int(raw_max_concurrent)))
    except ValueError:
        raise ConfigError(f"MINICC_MAX_CONCURRENT_TASKS 不是整数: {raw_max_concurrent!r}") from None

    raw_max_repairs = pick(None, "MINICC_MAX_REPAIR_ATTEMPTS", "max_repair_attempts", str(DEFAULT_MAX_REPAIR_ATTEMPTS))
    try:
        max_repair_attempts = max(0, min(8, int(raw_max_repairs)))
    except ValueError:
        raise ConfigError(f"MINICC_MAX_REPAIR_ATTEMPTS 不是整数: {raw_max_repairs!r}") from None

    raw_history_limit = pick(None, "MINICC_TASK_HISTORY_LIMIT", "task_history_limit", str(DEFAULT_TASK_HISTORY_LIMIT))
    try:
        task_history_limit = max(1, min(200, int(raw_history_limit)))
    except ValueError:
        raise ConfigError(f"MINICC_TASK_HISTORY_LIMIT 不是 1-200 的整数: {raw_history_limit!r}") from None
    raw_history_age = pick(None, "MINICC_TASK_HISTORY_MAX_AGE_DAYS", "task_history_max_age_days", str(DEFAULT_TASK_HISTORY_MAX_AGE_DAYS))
    try:
        task_history_max_age_days = max(1, min(3650, int(raw_history_age)))
    except ValueError:
        raise ConfigError(f"MINICC_TASK_HISTORY_MAX_AGE_DAYS 不是 1-3650 的整数: {raw_history_age!r}") from None
    raw_event_limit = pick(None, "MINICC_TASK_EVENT_LIMIT", "task_event_limit", str(DEFAULT_TASK_EVENT_LIMIT))
    try:
        task_event_limit = max(32, min(10_000, int(raw_event_limit)))
    except ValueError:
        raise ConfigError(f"MINICC_TASK_EVENT_LIMIT 不是 32-10000 的整数: {raw_event_limit!r}") from None
    raw_stream_limit = pick(None, "MINICC_TASK_STREAM_LIMIT", "task_stream_limit", str(DEFAULT_TASK_STREAM_LIMIT))
    try:
        task_stream_limit = max(512, min(100_000, int(raw_stream_limit)))
    except ValueError:
        raise ConfigError(f"MINICC_TASK_STREAM_LIMIT 不是 512-100000 的整数: {raw_stream_limit!r}") from None
    raw_usage_limit = pick(None, "MINICC_TASK_USAGE_LIMIT", "task_usage_limit", str(DEFAULT_TASK_USAGE_LIMIT))
    try:
        task_usage_limit = max(8, min(512, int(raw_usage_limit)))
    except ValueError:
        raise ConfigError(f"MINICC_TASK_USAGE_LIMIT 不是 8-512 的整数: {raw_usage_limit!r}") from None
    raw_compaction_limit = pick(None, "MINICC_TASK_COMPACTION_LIMIT", "task_compaction_limit", str(DEFAULT_TASK_COMPACTION_LIMIT))
    try:
        task_compaction_limit = max(8, min(512, int(raw_compaction_limit)))
    except ValueError:
        raise ConfigError(f"MINICC_TASK_COMPACTION_LIMIT 不是 8-512 的整数: {raw_compaction_limit!r}") from None
    raw_queue_limit = pick(None, "MINICC_TASK_QUEUE_LIMIT", "task_queue_limit", str(DEFAULT_TASK_QUEUE_LIMIT))
    try:
        task_queue_limit = max(1, min(256, int(raw_queue_limit)))
    except ValueError:
        raise ConfigError(f"MINICC_TASK_QUEUE_LIMIT 不是 1-256 的整数: {raw_queue_limit!r}") from None

    if not resolved_key or resolved_key == "sk-replace_me":
        raise ConfigError(
            "MINICC_API_KEY 未设置。复制 minicc.config.example 为 .env 并填入 key，"
            "或设置环境变量 MINICC_API_KEY / MINICC_BASE_URL / MINICC_MODEL。"
        )

    return Config(
        base_url=resolved_url.rstrip("/"),
        api_key=resolved_key,
        model=resolved_model,
        reasoning_effort=resolved_reasoning,
        tool_mode=resolved_mode,
        max_turns=max_turns,
        llm_protocol=resolved_protocol,
        provider_retries=provider_retries,
        task_recovery_retries=task_recovery_retries,
        yolo=resolved_yolo,
        compact_threshold=compact_threshold,
        context_window_tokens=context_window_tokens,
        max_concurrent_tasks=max_concurrent_tasks,
        max_repair_attempts=max_repair_attempts,
        task_history_limit=task_history_limit,
        task_history_max_age_days=task_history_max_age_days,
        task_event_limit=task_event_limit,
        task_stream_limit=task_stream_limit,
        task_usage_limit=task_usage_limit,
        task_compaction_limit=task_compaction_limit,
        task_queue_limit=task_queue_limit,
        sandbox_mode=sandbox_mode,
        sandbox_image=sandbox_image,
    )
