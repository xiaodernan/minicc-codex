"""M8-T141: config.json unknown/unused keys must be reported, not silently ignored.

The `load_config` function already tracks which keys it consults and reports
unrecognized ones via `unrecognized_config_keys`. This gate proves three
properties that used to have only partial coverage:

1. **Suggestion accuracy**: a typo like "modle" must suggest "model", not an
   unrelated key with a similar Levenshtein distance.
2. **Multi-layer isolation**: user-level and project-level stray keys are
   reported separately, each with the correct file path in the warning.
3. **Nested object keys are not false-positives**: a valid nested object (e.g.
   stage_routing) must not trigger unrecognized warnings for its internal keys.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from minicc.config import ConfigError, load_config


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture()
def config_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    """Isolated cwd + MINICC_HOME + workspace; MINICC_* never leaks out."""
    cwd = tmp_path / "cwd"
    home = tmp_path / "home"
    workspace = tmp_path / "ws"
    for directory in (cwd, home, workspace):
        directory.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "test-key-placeholder")
    monkeypatch.chdir(cwd)
    for key in [
        k for k in os.environ
        if k.startswith("MINICC_") and k not in {"MINICC_HOME", "MINICC_API_KEY"}
    ]:
        monkeypatch.delenv(key)
    yield cwd, home, workspace
    for key in [k for k in os.environ if k.startswith("MINICC_")]:
        os.environ.pop(key, None)


# --- Section 1: Suggestion accuracy ------------------------------------------

def test_typo_suggests_correct_key(config_env, caplog: pytest.LogCaptureFixture) -> None:
    """A one-char typo ('modle') must suggest 'model', not 'max_turns' or 'timeout'."""
    _cwd, home, _workspace = config_env
    _write(home / "config.json", {
        "api_key": "test-key-placeholder",
        "modle": "gpt-4",  # typo
    })
    config = load_config()
    assert config.unrecognized_config_keys == ("modle",)
    messages = [m for m in caplog.messages if "modle" in m]
    assert len(messages) == 1
    assert "model" in messages[0], f"suggestion should mention 'model': {messages[0]}"


def test_close_match_cutoff_prevents_bad_suggestions(config_env, caplog: pytest.LogCaptureFixture) -> None:
    """A key too different from any known key gets no suggestion (hint is None)."""
    _cwd, home, _workspace = config_env
    _write(home / "config.json", {
        "api_key": "test-key-placeholder",
        "xyzzy_nothing": "value",
    })
    config = load_config()
    assert config.unrecognized_config_keys == ("xyzzy_nothing",)
    messages = [m for m in caplog.messages if "xyzzy_nothing" in m]
    assert len(messages) == 1
    # No "是否想写" when cutoff is not met.
    assert "是否想写" not in messages[0]


# --- Section 2: Multi-layer isolation ----------------------------------------

def test_user_and_project_stray_keys_reported_separately(
    config_env, caplog: pytest.LogCaptureFixture
) -> None:
    """User-level and project-level stray keys appear in separate warnings."""
    _cwd, home, workspace = config_env
    _write(home / "config.json", {
        "api_key": "test-key-placeholder",
        "user_stray": "value",
    })
    _write(workspace / ".minicc" / "config.json", {
        "project_stray": "value",
    })
    config = load_config(workspace=workspace)
    assert set(config.unrecognized_config_keys) == {"user_stray", "project_stray"}
    user_msgs = [m for m in caplog.messages if "user_stray" in m and "用户配置" in m]
    proj_msgs = [m for m in caplog.messages if "project_stray" in m and "项目配置" in m]
    assert len(user_msgs) >= 1
    assert len(proj_msgs) >= 1


# --- Section 3: Nested objects are not false-positives -----------------------

def test_nested_stage_routing_keys_not_reported_as_stray(
    config_env, caplog: pytest.LogCaptureFixture
) -> None:
    """Valid nested objects (stage_routing) don't trigger unrecognized warnings."""
    _cwd, home, _workspace = config_env
    _write(home / "config.json", {
        "api_key": "test-key-placeholder",
        "stage_routing": {
            "enabled": True,
            "tiers": {
                "fast": ["gpt-4o-mini"],
            },
            "stage_map": {
                "planning": "fast",
            },
        },
    })
    config = load_config()
    # stage_routing is a recognized key; its internals are validated by
    # normalize_stage_routing, not reported as stray top-level keys.
    assert config.unrecognized_config_keys == ()
    stray_msgs = [m for m in caplog.messages if "是否想写" in m or "不会被读取" in m]
    assert len(stray_msgs) == 0, f"unexpected stray-key warnings: {stray_msgs}"


def test_invalid_nested_object_still_reports_top_level_key(
    config_env, caplog: pytest.LogCaptureFixture
) -> None:
    """An invalid top-level key that happens to hold an object is still stray."""
    _cwd, home, _workspace = config_env
    _write(home / "config.json", {
        "api_key": "test-key-placeholder",
        "not_a_real_feature": {
            "some": "nested",
            "data": True,
        },
    })
    config = load_config()
    assert config.unrecognized_config_keys == ("not_a_real_feature",)
    messages = [m for m in caplog.messages if "not_a_real_feature" in m]
    assert len(messages) == 1
