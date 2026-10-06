"""M8-T144: hooks.json validation boundaries — systematic coverage of malformed configs.

HookRunner._parse validates hooks.json structure at load time and sets load_error
instead of crashing. This gate proves all common malformed inputs are caught with
clear HookConfigError messages rather than causing runtime issues or silent failures.

Coverage gaps this gate fills:
- Non-dict top-level structures
- Invalid event names
- Missing/empty command fields
- Invalid regex patterns in matcher
- Out-of-range timeout values
- Invalid on_failure values
- Non-dict env entries
- Mixed valid/invalid entries in same event
- Unknown top-level keys (currently allowed, documented)
- Unicode and special characters in commands/matchers
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from minicc.hooks import HookConfigError, HookRunner


def _write_hooks(workspace: Path, payload: object) -> None:
    """Write raw payload to .minicc/hooks.json without validation."""
    (workspace / ".minicc").mkdir(parents=True, exist_ok=True)
    (workspace / ".minicc" / "hooks.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


# ── Top-level structure validation ─────────────────────────────────────────


def test_non_dict_top_level_raises(tmp_path: Path) -> None:
    """Top-level array/string/number raises HookConfigError during file read."""
    _write_hooks(tmp_path, [{"hooks": {}}])
    # _read_config_file raises HookConfigError directly (not caught in __init__)
    with pytest.raises(HookConfigError, match="顶层必须是 JSON 对象"):
        HookRunner(tmp_path)


def test_missing_hooks_key_uses_root_as_hooks(tmp_path: Path) -> None:
    """If 'hooks' key missing, treats root dict as hooks config."""
    _write_hooks(tmp_path, {
        "PreToolUse": [
            {"command": "echo hello", "matcher": "bash"}
        ]
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    assert len(runner.specs) == 1
    assert runner.specs[0].event == "PreToolUse"


def test_hooks_value_is_not_dict_raises(tmp_path: Path) -> None:
    """hooks field must be a dict, not list/string."""
    _write_hooks(tmp_path, {"hooks": ["not-a-dict"]})
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    assert "hooks 字段必须是对象" in runner.load_error


# ── Event name validation ──────────────────────────────────────────────────


def test_unknown_event_name_raises(tmp_path: Path) -> None:
    """Event names not in HOOK_EVENTS raise HookConfigError."""
    _write_hooks(tmp_path, {
        "hooks": {
            "UnknownEvent": [
                {"command": "echo test"}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    assert "未知 hook 事件" in runner.load_error
    assert "PreToolUse" in runner.load_error or "PostToolUse" in runner.load_error


def test_valid_event_names_accepted(tmp_path: Path) -> None:
    """All four standard events are accepted."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [{"command": "echo pre"}],
            "PostToolUse": [{"command": "echo post"}],
            "UserPromptSubmit": [{"command": "echo prompt"}],
            "Stop": [{"command": "echo stop"}],
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    assert len(runner.specs) == 4
    events = {spec.event for spec in runner.specs}
    assert events == {"PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop"}


# ── Entry structure validation ─────────────────────────────────────────────


def test_entries_must_be_list_raises(tmp_path: Path) -> None:
    """Event entries must be a list, not dict/string."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": {"command": "echo test"}  # Should be list
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    assert "必须是数组" in runner.load_error


def test_entry_must_be_dict_raises(tmp_path: Path) -> None:
    """Individual entries must be dicts, not strings/numbers."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": ["not-a-dict", 123]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    assert "必须是对象" in runner.load_error


def test_empty_command_raises(tmp_path: Path) -> None:
    """Command field cannot be empty or whitespace-only."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": ""},
                {"command": "   "},
                {"command": None},
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    assert "command 不能为空" in runner.load_error


def test_missing_command_raises(tmp_path: Path) -> None:
    """Entries without command field raise HookConfigError."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"matcher": "bash"}  # No command
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    assert "command 不能为空" in runner.load_error


# ── Matcher regex validation ───────────────────────────────────────────────


def test_invalid_regex_in_matcher_raises(tmp_path: Path) -> None:
    """Invalid regex patterns in matcher raise HookConfigError."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test", "matcher": "[invalid("}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    assert "非法正则" in runner.load_error


def test_valid_regex_patterns_accepted(tmp_path: Path) -> None:
    """Valid regex patterns are compiled successfully."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test", "matcher": "bash|write_file"},
                {"command": "echo test2", "matcher": r"read_\w+"},
                {"command": "echo test3", "matcher": "(?:foo|bar)"},
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    assert len(runner.specs) == 3


def test_empty_matcher_matches_all_tools(tmp_path: Path) -> None:
    """Empty matcher string matches any tool name."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test", "matcher": ""}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    spec = runner.specs[0]
    assert spec.matches_tool("bash") is True
    assert spec.matches_tool("write_file") is True
    assert spec.matches_tool("anything") is True


# ── Timeout validation ─────────────────────────────────────────────────────


def test_timeout_out_of_range_raises(tmp_path: Path) -> None:
    """Timeout must be in (0, 60] seconds."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test", "timeout": 0},
                {"command": "echo test2", "timeout": -1},
                {"command": "echo test3", "timeout": 61},
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    assert "需在 (0, 60]" in runner.load_error


def test_timeout_non_numeric_raises(tmp_path: Path) -> None:
    """Non-numeric timeout values raise HookConfigError."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test", "timeout": "fast"}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    assert "必须是数字" in runner.load_error


def test_valid_timeout_values_accepted(tmp_path: Path) -> None:
    """Valid timeout values within range are accepted."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test", "timeout": 0.1},
                {"command": "echo test2", "timeout": 5.0},
                {"command": "echo test3", "timeout": 60},
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    assert len(runner.specs) == 3
    assert runner.specs[0].timeout == 0.1
    assert runner.specs[1].timeout == 5.0
    assert runner.specs[2].timeout == 60


def test_default_timeout_applied_when_missing(tmp_path: Path) -> None:
    """Missing timeout uses DEFAULT_HOOK_TIMEOUT (5.0s)."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test"}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    assert runner.specs[0].timeout == 5.0


# ── on_failure validation ──────────────────────────────────────────────────


def test_invalid_on_failure_raises(tmp_path: Path) -> None:
    """on_failure must be 'continue' or 'deny'."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test", "on_failure": "abort"}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    assert "on_failure 非法" in runner.load_error
    assert "continue|deny" in runner.load_error


def test_valid_on_failure_values_accepted(tmp_path: Path) -> None:
    """Both 'continue' and 'deny' are accepted."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test", "on_failure": "continue"},
                {"command": "echo test2", "on_failure": "deny"},
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    assert runner.specs[0].on_failure == "continue"
    assert runner.specs[1].on_failure == "deny"


def test_default_on_failure_is_continue(tmp_path: Path) -> None:
    """Missing on_failure defaults to 'continue'."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test"}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    assert runner.specs[0].on_failure == "continue"


# ── env validation ─────────────────────────────────────────────────────────


def test_env_must_be_dict_raises(tmp_path: Path) -> None:
    """env field must be a dict, not list/string."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test", "env": ["NOT_A_DICT"]}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    assert "env 必须是对象" in runner.load_error


def test_env_values_coerced_to_strings(tmp_path: Path) -> None:
    """Env values are coerced to strings."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test", "env": {"KEY": 123, "FLAG": True}}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    env = runner.specs[0].env
    assert env["KEY"] == "123"
    assert env["FLAG"] == "True"


def test_empty_env_defaults_to_empty_dict(tmp_path: Path) -> None:
    """Missing or null env becomes empty dict."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test"},
                {"command": "echo test2", "env": None},
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    assert runner.specs[0].env == {}
    assert runner.specs[1].env == {}


# ── Mixed valid/invalid entries ────────────────────────────────────────────


def test_first_invalid_entry_stops_parsing(tmp_path: Path) -> None:
    """Parsing stops at first invalid entry; previous valid ones may be kept."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo valid"},
                {"command": ""},  # Invalid
                {"command": "echo unreachable"},
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    # The error should mention the invalid entry
    assert "command 不能为空" in runner.load_error


def test_multiple_events_with_one_invalid(tmp_path: Path) -> None:
    """One invalid event makes entire config fail."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo valid"}
            ],
            "BadEvent": [
                {"command": "echo invalid"}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is not None
    assert "未知 hook 事件" in runner.load_error


# ── Edge cases and special characters ──────────────────────────────────────


def test_unicode_in_command_accepted(tmp_path: Path) -> None:
    """Unicode characters in commands are preserved."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo '测试中文' 🧪"}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    assert "测试中文" in runner.specs[0].command


def test_special_chars_in_matcher_accepted(tmp_path: Path) -> None:
    """Special regex characters in matcher are validated."""
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": "echo test", "matcher": r"bash|write_file|\d+"}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    spec = runner.specs[0]
    assert spec.matches_tool("bash") is True
    assert spec.matches_tool("write_file") is True
    assert spec.matches_tool("tool123") is True


def test_very_long_command_accepted(tmp_path: Path) -> None:
    """Very long commands are accepted (no truncation in validation)."""
    long_cmd = "echo " + "x" * 10000
    _write_hooks(tmp_path, {
        "hooks": {
            "PreToolUse": [
                {"command": long_cmd}
            ]
        }
    })
    runner = HookRunner(tmp_path)
    assert runner.load_error is None
    assert len(runner.specs[0].command) > 10000


# ── Config via constructor parameter ───────────────────────────────────────


def test_config_parameter_bypasses_file(tmp_path: Path) -> None:
    """Passing config directly bypasses file reading."""
    config = {
        "hooks": {
            "PreToolUse": [
                {"command": "echo from-param"}
            ]
        }
    }
    runner = HookRunner(tmp_path, config=config)
    assert runner.load_error is None
    assert len(runner.specs) == 1
    assert runner.specs[0].command == "echo from-param"


def test_invalid_config_parameter_sets_load_error(tmp_path: Path) -> None:
    """Invalid config passed to constructor still sets load_error."""
    config = {
        "hooks": {
            "PreToolUse": [
                {"command": ""}  # Empty command
            ]
        }
    }
    runner = HookRunner(tmp_path, config=config)
    assert runner.load_error is not None
    assert "command 不能为空" in runner.load_error


# ── Disabled hooks via environment ─────────────────────────────────────────


def test_hooks_disabled_via_env_ignores_config(tmp_path: Path) -> None:
    """MINICC_HOOKS=0 disables hooks regardless of config."""
    import os
    old_val = os.environ.get("MINICC_HOOKS")
    try:
        os.environ["MINICC_HOOKS"] = "0"
        _write_hooks(tmp_path, {
            "hooks": {
                "PreToolUse": [
                    {"command": "echo should-not-load"}
                ]
            }
        })
        runner = HookRunner(tmp_path)
        assert not runner.enabled
        assert len(runner.specs) == 0
    finally:
        if old_val is None:
            os.environ.pop("MINICC_HOOKS", None)
        else:
            os.environ["MINICC_HOOKS"] = old_val
