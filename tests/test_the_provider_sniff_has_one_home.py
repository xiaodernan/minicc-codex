"""M8-T509 — provider 嗅探规则两个家：auto 之下说哪家协议

``provider_type = auto`` 时，用 (base_url, model) 嗅探该说 Anthropic 还是
OpenAI 的 wire protocol。这条规则有两个家：``config.py`` 的配置解析和
``main.py`` 的 CLI 覆盖路径，逐字相同。规则在两边各自漂移的后果不是报错，
而是整个会话发错误的协议格式——没有任何测试会红。

家安在 ``minicc/config.py``：provider 词表 ``PROVIDER_TYPES`` 本就住在那
里，嗅探是同一张词表的读者。main 是配置层的上游调用方，引用它不成环。
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from minicc.config import Config, sniff_provider_type
from minicc.main import _apply_cli_overrides

REPO = Path(__file__).resolve().parents[1]
HOME = "minicc/config.py"


def test_the_home_sniffs_by_url_then_by_model() -> None:
    assert sniff_provider_type("https://api.anthropic.com/v1", "gpt-4o") == "anthropic"
    assert sniff_provider_type("https://gateway.test/v1", "claude-3.5-sonnet") == "anthropic"
    assert sniff_provider_type("https://gateway.test/v1", "gpt-4o") == "openai"
    # The haystack is casefolded ...
    assert sniff_provider_type("https://ANTHROPIC.internal/v1", "gpt-4o") == "anthropic"
    # ... and the model prefix is not. Pinned, because a future "cleanup" that
    # casefolds the model too is a behavior change, not a cleanup.
    assert sniff_provider_type("https://gateway.test/v1", "Claude-3") == "openai"


def test_the_sniff_is_spelled_exactly_once() -> None:
    """The literal and the call shape each appear exactly once, in the home."""
    literals: list[tuple[str, int]] = []
    calls: list[tuple[str, int]] = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "claude":
                literals.append((path.relative_to(REPO).as_posix(), node.lineno))
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "startswith" and node.args
                    and isinstance(node.args[0], ast.Constant) and node.args[0].value == "claude"):
                calls.append((path.relative_to(REPO).as_posix(), node.lineno))
    assert len(literals) == 1 and literals[0][0] == HOME, literals
    assert len(calls) == 1 and calls[0][0] == HOME, calls


@pytest.fixture()
def config_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated cwd + MINICC_HOME; MINICC_* never leaks in or out."""
    cwd = tmp_path / "cwd"
    home = tmp_path / "home"
    workspace = tmp_path / "ws"
    for directory in (cwd, home, workspace):
        directory.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "sk-test-key")
    monkeypatch.chdir(cwd)
    for key in [k for k in os.environ
                if k.startswith("MINICC_") and k not in {"MINICC_HOME", "MINICC_API_KEY"}]:
        monkeypatch.delenv(key)
    yield workspace
    for key in [k for k in os.environ if k.startswith("MINICC_")]:
        os.environ.pop(key, None)


def test_the_config_reader_asks_the_home(config_env, monkeypatch) -> None:
    from minicc.config import load_config

    monkeypatch.setenv("MINICC_PROVIDER_TYPE", "auto")
    monkeypatch.setenv("MINICC_BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("MINICC_MODEL", "claude-3.5-sonnet")
    assert load_config(workspace=config_env).provider_type == "anthropic"

    monkeypatch.setenv("MINICC_MODEL", "gpt-4o")
    assert load_config(workspace=config_env).provider_type == "openai"

    monkeypatch.setenv("MINICC_BASE_URL", "https://anthropic.internal/v1")
    assert load_config(workspace=config_env).provider_type == "anthropic"


def _args(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "compact_threshold": None,
        "max_turns": None,
        "timeout": None,
        "context_window": None,
        "soft_max_tokens": None,
        "output_style": None,
        "max_concurrent_tasks": None,
        "sandbox": None,
        "task_executor": None,
        "provider_type": None,
        "fallback_models": None,
        "auto_resume": False,
        "subagent_writable": False,
        "permission_mode": "default",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _config(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "base_url": "https://gateway.test/v1",
        "api_key": "test-key",
        "model": "gpt-4o",
    }
    base.update(overrides)
    return Config(**base)


def test_the_cli_reader_asks_the_home() -> None:
    claude = _apply_cli_overrides(
        _config(model="claude-3.5-sonnet"), _args(provider_type="auto")
    )
    assert claude.provider_type == "anthropic"

    plain = _apply_cli_overrides(_config(), _args(provider_type="auto"))
    assert plain.provider_type == "openai"

    by_url = _apply_cli_overrides(
        _config(base_url="https://anthropic.internal/v1"), _args(provider_type="auto")
    )
    assert by_url.provider_type == "anthropic"
