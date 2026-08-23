"""Configuration loading: .env in cwd → environment → ~/.minicc/config.json.

Precedence (highest wins): explicit constructor args > environment variables >
.env file in the current directory > config file > defaults. Values are plain
strings/ints/bools — no schema machinery, but nothing silently defaults when
the user explicitly set something invalid: a malformed .env line is reported.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

# The default is the interview gateway supplied for this project. The provider
# also accepts any other OpenAI-compatible root or path-qualified endpoint.
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_BASE_URL = "https://api.aizzz.xyz/v1"
DEFAULT_MAX_TURNS = 40
DEFAULT_TIMEOUT = 180.0
DEFAULT_SANDBOX_MODE = "host"
DEFAULT_SANDBOX_IMAGE = "python:3.11-slim"
DEFAULT_CONTEXT_WINDOW_TOKENS = 300_000
DEFAULT_MAX_CONCURRENT_TASKS = 8
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_MAX_REPAIR_ATTEMPTS = 2
# Context compaction trigger, in characters (~chars/4 ≈ tokens).
DEFAULT_COMPACT_THRESHOLD = 300_000

TRUTHY = frozenset({"1", "true", "yes", "on"})


class ConfigError(RuntimeError):
    """Configuration is missing or malformed."""


def normalize_reasoning_effort(value: str | None, *, default: str = DEFAULT_REASONING_EFFORT) -> str:
    """Normalize UI/env aliases to the three effort levels exposed by minicc."""
    raw = str(value or default).strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "low": "standard",
        "medium": "standard",
        "very-high": "max",
        "very high": "max",
        "veryhigh": "max",
        "xhigh": "max",
        "maximum": "max",
        "高": "high",
        "极高": "max",
        "最高": "max",
    }
    normalized = aliases.get(raw, raw)
    if normalized not in {"standard", "high", "max"}:
        raise ValueError(f"reasoning effort 非法: {value!r} (standard|high|max)")
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
    max_turns: int = DEFAULT_MAX_TURNS
    timeout: float = DEFAULT_TIMEOUT
    yolo: bool = False
    compact_threshold: int = DEFAULT_COMPACT_THRESHOLD
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS
    max_concurrent_tasks: int = DEFAULT_MAX_CONCURRENT_TASKS
    max_repair_attempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS
    sandbox_mode: str = DEFAULT_SANDBOX_MODE
    sandbox_image: str = DEFAULT_SANDBOX_IMAGE

    def describe(self) -> str:
        key = self.api_key
        shown = key if len(key) <= 12 else key[:8] + "..." + key[-4:]
        return (
            f"model={self.model} endpoint={self.base_url} "
            f"tool_mode={self.tool_mode} reasoning={self.reasoning_effort} key={shown}"
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

    raw_turns = pick(None, "MINICC_MAX_TURNS", "max_turns", str(DEFAULT_MAX_TURNS))
    try:
        max_turns = max(1, int(raw_turns))
    except ValueError:
        raise ConfigError(f"MINICC_MAX_TURNS 不是整数: {raw_turns!r}") from None

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
        yolo=resolved_yolo,
        compact_threshold=compact_threshold,
        context_window_tokens=context_window_tokens,
        max_concurrent_tasks=max_concurrent_tasks,
        max_repair_attempts=max_repair_attempts,
        sandbox_mode=sandbox_mode,
        sandbox_image=sandbox_image,
    )
