"""Configuration loading: .env in cwd → environment → project → user config.

Precedence (highest wins): explicit constructor args > environment variables >
.env file in the current directory > project config
(`<workspace>/.minicc/config.json`) > user config (`~/.minicc/config.json`) >
defaults. Values are plain strings/ints/bools — no schema machinery, but
nothing silently defaults when the user explicitly set something invalid: a
malformed .env line or a non-object config.json is reported as ConfigError.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
DEFAULT_SANDBOX_MODE = "auto"
DEFAULT_SANDBOX_IMAGE = "python:3.11-slim"
DEFAULT_CONTEXT_WINDOW_TOKENS = 300_000
DEFAULT_MAX_CONCURRENT_TASKS = 8
DEFAULT_REASONING_EFFORT = "high"
REASONING_EFFORTS = frozenset({"low", "mid", "high", "xhigh", "max", "ultra"})
_MODEL_NAME_RE = re.compile(r"^[^\x00-\x20\x7f\"'\\]{1,200}$")
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
# M6-T1: a writable subagent may nest one more level; the depth-2 grandchild
# is structurally denied the ``task`` tool, so depth 3 is impossible.
DEFAULT_SUBAGENT_MAX_DEPTH = 2

TRUTHY = frozenset({"1", "true", "yes", "on"})


class ConfigError(RuntimeError):
    """Configuration is missing or malformed."""


def normalize_reasoning_effort(value: str | None, *, default: str = DEFAULT_REASONING_EFFORT) -> str:
    """Normalize UI/env aliases to the supported provider effort levels."""
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
        raise ValueError(f"reasoning effort 非法: {value!r} (low|mid|high|xhigh|max|ultra)")
    return normalized


def normalize_model_name(value: object | None, *, default: str | None = None) -> str:
    """Validate a provider model id before it enters a task or provider call.

    Model ids are gateway-defined, so this intentionally accepts names beyond
    the built-in StepFun list (for example custom deployments and aliases),
    while rejecting whitespace/control characters and oversized values.
    """
    # An empty/blank value falls back to the default, mirroring
    # normalize_reasoning_effort. A resumed task whose record predates an
    # explicit model must inherit the configured default rather than crash.
    raw = str((value or default) or "").strip()
    if not raw:
        raise ValueError("模型名不能为空")
    if not _MODEL_NAME_RE.fullmatch(raw):
        raise ValueError("模型名格式非法：不能包含空白、控制字符、引号或反斜杠，长度需为 1-200")
    return raw


def home_dir() -> Path:
    """Resolve the config root (``~/.minicc`` or ``MINICC_HOME``) read-only.

    M7-T4: this getter never creates directories — callers that write under
    the root mkdir their own target path. A ``MINICC_HOME`` that points at an
    existing non-directory is a user typo and must surface as ConfigError,
    not silently relocate (or crash later with FileExistsError).
    """
    override = os.getenv("MINICC_HOME")
    if not override:
        return Path.home() / ".minicc"
    root = Path(override)
    if root.exists() and not root.is_dir():
        raise ConfigError(f"MINICC_HOME 指向的路径不是目录: {root}")
    return root


def _read_config_json(path: Path) -> dict[str, Any]:
    """Load one config.json layer; a non-object top level is a ConfigError."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError(f"无法读取 {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(
            f"{path}: 顶层必须是 JSON 对象，实际是 {type(data).__name__}"
        )
    return data


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
        # M2-T8: accept shell-style `export KEY=VALUE`.
        if line.startswith("export ") or line.startswith("export\t"):
            line = line[len("export"):].strip()
        if "=" not in line:
            raise ConfigError(f"{path}:{line_no}: expected KEY=VALUE, got {line!r}")
        key, _, value = line.partition("=")
        value = value.strip()
        quote = value[:1]
        if quote in {'"', "'"} and len(value) >= 2 and value.endswith(quote):
            value = value[1:-1]
        else:
            # M2-T8: strip inline comments from unquoted values — a `#` after
            # whitespace starts a comment (dotenv convention). Previously the
            # comment text was sent to the gateway as part of the value.
            for marker in (" #", "\t#"):
                index = value.find(marker)
                if index != -1:
                    value = value[:index]
            value = value.rstrip().strip('"').strip("'")
        values[key.strip()] = value
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
    # openai | anthropic | auto (auto infers from base_url/model name)
    provider_type: str = "openai"
    # Ordered fallback models tried on repeated provider failures (may be empty).
    fallback_models: tuple[str, ...] = ()
    # Re-queue interrupted tasks automatically when the web service starts.
    auto_resume_on_start: bool = False
    # thread (default, in-process) | process (detached task_worker subprocess)
    task_executor: str = "thread"
    # Empty tuple keeps the historical "any local directory" behavior; when
    # set, /api/workspace/select may only switch to one of these roots or a
    # subdirectory of them.
    workspace_roots: tuple[Path, ...] = ()
    # Optional wrap-up-then-stop budgets. None keeps the historical
    # "no task-level token/duration cap" behavior.
    soft_max_tokens: int | None = None
    soft_max_duration_seconds: float | None = None
    # M6-T1 bounded writable delegation. Off by default: subagents stay
    # readonly reconnaissance even in acceptEdits/yolo sessions. When on, a
    # subagent's tool tier still follows the session's permission_mode
    # (acceptEdits -> write, yolo -> exec) so writes never happen without an
    # explicitly authorized session. subagent_max_depth caps nesting (>=1).
    subagent_writable: bool = False
    subagent_max_tokens: int | None = None
    subagent_max_depth: int = DEFAULT_SUBAGENT_MAX_DEPTH

    def describe(self) -> str:
        # M7-T4: never echo any fragment of the api key — even head+tail
        # leaked enough to correlate logs with a specific credential.
        key_state = "set" if self.api_key else "unset"
        delegation = (
            f"subagent=delegated(depth<={self.subagent_max_depth})"
            if self.subagent_writable else "subagent=readonly"
        )
        return (
            f"model={self.model} endpoint={self.base_url} "
            f"tool_mode={self.tool_mode} protocol={self.llm_protocol} "
            f"reasoning={self.reasoning_effort} key={key_state} {delegation}"
        )


def load_config(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    tool_mode: str | None = None,
    yolo: bool | None = None,
    workspace: Path | None = None,
) -> Config:
    """Resolve config: args > env vars > .env > project > user > defaults.

    M7-T4: when ``workspace`` is given, ``<workspace>/.minicc/config.json``
    forms a project-level layer that overrides the user-level
    ``~/.minicc/config.json`` key by key (still below `.env` and the
    environment, per the documented precedence).
    """
    user_values = _read_config_json(home_dir() / "config.json")
    project_values: dict[str, Any] = {}
    if workspace is not None:
        project_values = _read_config_json(
            Path(workspace) / ".minicc" / "config.json"
        )
    # Project keys win over user keys; both stay below env/.env in pick().
    file_values: dict[str, Any] = {**user_values, **project_values}

    env_values = _parse_env_file(Path(".env"))

    def _stringify(value: object) -> str:
        # M2-T8 (audit P2-5e): a JSON list in config.json used to become its
        # Python repr ("['C:/a', 'C:/b']"), which downstream parsers split
        # into garbage paths. Join lists so comma/sep splitting still works.
        if isinstance(value, (list, tuple)):
            return ",".join(_stringify(item) for item in value)
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)

    def _present(value: object) -> bool:
        # M7-T4: `if value:` discarded an explicit JSON 0/false, so a user
        # could not turn a knob off via config.json. Only None and empty
        # strings (or empty collections) mean "not configured" here.
        if value is None:
            return False
        if isinstance(value, str):
            return value != ""
        if isinstance(value, (list, tuple, dict)):
            return len(value) > 0
        return True

    def pick(arg: str | None, env_name: str, file_key: str, default: str) -> str:
        if arg is not None:
            return arg
        # M2-T8: only look up `env_name` (the exact MINICC_* spelling) in
        # os.environ. The old code also probed os.environ with the lowercase
        # file_key, and on Windows the mapping is case-insensitive — so any
        # stray `MODEL=` / `API_KEY=` in the environment hijacked the config
        # and silently overrode `.env` and config.json.
        for source in (os.environ, env_values, file_values):
            value = source.get(env_name)
            if _present(value):
                return _stringify(value)
        # config.json and .env use lowercase keys without the prefix;
        # os.environ must never be probed with the bare key.
        for source in (env_values, file_values):
            value = source.get(file_key)
            if _present(value):
                return _stringify(value)
        return default

    # M2-T8: export `.env` values into os.environ so subprocesses (task
    # worker, Docker sandbox, MCP children via their explicit env) and the
    # MINICC_* toggles M2/M3 rely on actually take effect from `.env`.
    for key, value in env_values.items():
        if key.startswith("MINICC_") or key in {
            "MINICC_ALLOW_PRIVATE_FETCH", "MINICC_ALLOW_PRIVATE_MCP",
        }:
            os.environ.setdefault(key, value)

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

    # Hard task-level execution budgets remain unlimited.  Keep these legacy
    # fields for snapshot and API compatibility, but ignore old environment
    # variables so stale configuration cannot truncate a task. Optional *soft*
    # caps (wrap-up then stop) are opt-in via MINICC_SOFT_MAX_*.
    max_turns = None
    max_duration_seconds = None
    max_tool_calls = None

    def _optional_positive_int(env_name: str, file_key: str) -> int | None:
        raw = pick(None, env_name, file_key, "").strip()
        if not raw or raw.lower() in {"0", "none", "off", "unlimited"}:
            return None
        try:
            value = int(raw)
        except ValueError as exc:
            raise ConfigError(f"{env_name} 不是整数: {raw!r}") from exc
        if value <= 0:
            return None
        return value

    def _optional_positive_float(env_name: str, file_key: str) -> float | None:
        raw = pick(None, env_name, file_key, "").strip()
        if not raw or raw.lower() in {"0", "none", "off", "unlimited"}:
            return None
        try:
            value = float(raw)
        except ValueError as exc:
            raise ConfigError(f"{env_name} 不是数字: {raw!r}") from exc
        if not math.isfinite(value) or value <= 0:
            return None
        return value

    soft_max_tokens = _optional_positive_int("MINICC_SOFT_MAX_TOKENS", "soft_max_tokens")
    soft_max_duration_seconds = _optional_positive_float(
        "MINICC_SOFT_MAX_DURATION_SECONDS", "soft_max_duration_seconds"
    )
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

    raw_roots = pick(None, "MINICC_WORKSPACE_ROOTS", "workspace_roots", "")
    workspace_roots: list[Path] = []
    for raw_root in raw_roots.replace(",", os.pathsep).split(os.pathsep):
        part = raw_root.strip().strip('"')
        if not part:
            continue
        workspace_roots.append(Path(part).expanduser().resolve())

    raw_provider_type = pick(None, "MINICC_PROVIDER_TYPE", "provider_type", "auto").strip().lower()
    if raw_provider_type not in {"auto", "openai", "anthropic"}:
        raise ConfigError(f"MINICC_PROVIDER_TYPE 非法: {raw_provider_type!r} (auto|openai|anthropic)")
    if raw_provider_type == "auto":
        haystack = f"{resolved_url} {resolved_model}".lower()
        provider_type = "anthropic" if ("anthropic" in haystack or resolved_model.startswith("claude")) else "openai"
    else:
        provider_type = raw_provider_type

    raw_auto_resume = pick(None, "MINICC_AUTO_RESUME_ON_START", "auto_resume_on_start", "0")
    auto_resume_on_start = raw_auto_resume.strip().lower() in TRUTHY

    # M6-T1: writable subagent delegation is opt-in and defaults to off.
    subagent_writable = pick(None, "MINICC_SUBAGENT_WRITABLE", "subagent_writable", "0").strip().lower() in TRUTHY
    subagent_max_tokens = _optional_positive_int("MINICC_SUBAGENT_MAX_TOKENS", "subagent_max_tokens")
    raw_subagent_depth = pick(None, "MINICC_SUBAGENT_MAX_DEPTH", "subagent_max_depth", str(DEFAULT_SUBAGENT_MAX_DEPTH))
    try:
        subagent_max_depth = max(1, min(2, int(raw_subagent_depth)))
    except ValueError:
        raise ConfigError(f"MINICC_SUBAGENT_MAX_DEPTH 不是整数: {raw_subagent_depth!r}") from None

    task_executor = pick(None, "MINICC_TASK_EXECUTOR", "task_executor", "thread").strip().lower()
    if task_executor not in {"thread", "process"}:
        raise ConfigError(f"MINICC_TASK_EXECUTOR 非法: {task_executor!r} (thread|process)")

    raw_fallbacks = pick(None, "MINICC_FALLBACK_MODELS", "fallback_models", "")
    fallback_models: list[str] = []
    for raw_model in raw_fallbacks.replace(";", ",").split(","):
        name = raw_model.strip()
        if name and name != resolved_model and name not in fallback_models:
            fallback_models.append(name)

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
        workspace_roots=tuple(workspace_roots),
        provider_type=provider_type,
        fallback_models=tuple(fallback_models),
        auto_resume_on_start=auto_resume_on_start,
        task_executor=task_executor,
        soft_max_tokens=soft_max_tokens,
        soft_max_duration_seconds=soft_max_duration_seconds,
        subagent_writable=subagent_writable,
        subagent_max_tokens=subagent_max_tokens,
        subagent_max_depth=subagent_max_depth,
    )
