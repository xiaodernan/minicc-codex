"""M7-T4: project-level config layer + config.py defect regressions + CLI flags."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from minicc.config import (
    DEFAULT_COMPACT_THRESHOLD,
    Config,
    ConfigError,
    home_dir,
    load_config,
)
from minicc.main import _load, _parser


@pytest.fixture()
def config_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    """Isolated cwd + MINICC_HOME + workspace; MINICC_* never leaks out."""
    cwd = tmp_path / "cwd"
    home = tmp_path / "home"
    workspace = tmp_path / "ws"
    for directory in (cwd, home, workspace):
        directory.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "sk-test-key")
    monkeypatch.chdir(cwd)
    for key in [
        k for k in os.environ
        if k.startswith("MINICC_") and k not in {"MINICC_HOME", "MINICC_API_KEY"}
    ]:
        monkeypatch.delenv(key)
    yield cwd, home, workspace
    for key in [k for k in os.environ if k.startswith("MINICC_")]:
        os.environ.pop(key, None)


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_project_layer_overrides_user_layer(config_env) -> None:
    _cwd, home, workspace = config_env
    _write(home / "config.json", {"model": "user-model", "reasoning_effort": "low"})
    _write(workspace / ".minicc" / "config.json", {"model": "project-model"})
    config = load_config(workspace=workspace)
    assert config.model == "project-model"
    # Keys the project layer does not set still fall through to the user layer.
    assert config.reasoning_effort == "low"


def test_documented_precedence_env_and_dotenv_beat_project(config_env) -> None:
    _cwd, home, workspace = config_env
    _write(home / "config.json", {"model": "user-model"})
    _write(workspace / ".minicc" / "config.json", {"model": "project-model"})
    (_cwd / ".env").write_text("MINICC_MODEL=dotenv-model\n", encoding="utf-8")
    assert load_config(workspace=workspace).model == "dotenv-model"
    os.environ["MINICC_MODEL"] = "env-model"
    try:
        assert load_config(workspace=workspace).model == "env-model"
        # Explicit args win over everything.
        assert load_config(model="arg-model", workspace=workspace).model == "arg-model"
    finally:
        os.environ.pop("MINICC_MODEL", None)


def test_non_object_config_json_raises_config_error(config_env) -> None:
    _cwd, home, workspace = config_env
    for payload in ("[]", "null", '"hello"', "42"):
        user_file = home / "config.json"
        user_file.write_text(payload, encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config()
        user_file.unlink()
        _write(workspace / ".minicc" / "config.json", json.loads(payload))
        with pytest.raises(ConfigError):
            load_config(workspace=workspace)
        (workspace / ".minicc" / "config.json").unlink()


def test_explicit_zero_and_false_are_preserved(config_env) -> None:
    _cwd, home, _workspace = config_env
    _write(home / "config.json", {
        "provider_retries": 0,
        "max_repair_attempts": 0,
        "subagent_writable": False,
    })
    config = load_config()
    # Old `if value:` dropped JSON 0/False and silently fell back to the
    # defaults (4 and 2).
    assert config.provider_retries == 0
    assert config.max_repair_attempts == 0
    assert config.subagent_writable is False


def test_minicc_home_pointing_at_file_raises_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("MINICC_HOME", str(blocker))
    with pytest.raises(ConfigError):
        home_dir()
    with pytest.raises(ConfigError):
        load_config()


def test_home_dir_has_no_mkdir_side_effect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "fresh-home"
    monkeypatch.setenv("MINICC_HOME", str(root))
    assert home_dir() == root
    assert not root.exists()


def test_describe_never_leaks_api_key(config_env) -> None:
    _cwd, _home, _workspace = config_env
    long_key = "sk-" + "a" * 24 + "9876"
    config = load_config(api_key=long_key)
    described = config.describe()
    assert long_key not in described
    assert "sk-" not in described
    assert "9876" not in described
    assert "key=set" in described
    bare = Config(base_url="https://example.invalid/v1", api_key="", model="m")
    assert "key=unset" in bare.describe()


def test_project_layer_malformed_json_is_reported(config_env) -> None:
    _cwd, _home, workspace = config_env
    project = workspace / ".minicc" / "config.json"
    project.parent.mkdir(parents=True, exist_ok=True)
    project.write_text("{oops", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(workspace=workspace)


# --- CLI flags ------------------------------------------------------------


def _args(argv: list[str]) -> object:
    return _parser().parse_args(argv)


def test_new_cli_flags_appear_in_help() -> None:
    help_text = _parser().format_help()
    for flag in (
        "--max-turns", "--timeout", "--context-window", "--soft-max-tokens",
        "--max-concurrent-tasks", "--sandbox", "--provider-type",
        "--fallback-models", "--task-executor", "--auto-resume",
    ):
        assert flag in help_text


def test_cli_flags_take_effect(config_env) -> None:
    _cwd, _home, workspace = config_env
    config = _load(_args([
        "--max-turns", "7",
        "--timeout", "33.5",
        "--context-window", "123456",
        "--soft-max-tokens", "999999",
        "--max-concurrent-tasks", "3",
        "--sandbox", "docker",
        "--provider-type", "anthropic",
        "--task-executor", "process",
        "--fallback-models", "beta,alpha,beta,,gpt-5.6-terra",
        "--auto-resume",
        "--model", "gpt-5.6-terra",
    ]), workspace)
    assert config.max_turns == 7
    assert config.timeout == 33.5
    assert config.context_window_tokens == 123456
    assert config.soft_max_tokens == 999999
    assert config.max_concurrent_tasks == 3
    assert config.sandbox_mode == "docker"
    assert config.provider_type == "anthropic"
    assert config.task_executor == "process"
    assert config.fallback_models == ("beta", "alpha")
    assert config.auto_resume_on_start is True


def test_cli_invalid_values_raise_config_error(config_env) -> None:
    _cwd, _home, workspace = config_env
    with pytest.raises(ConfigError):
        _load(_args(["--max-turns", "0"]), workspace)
    with pytest.raises(ConfigError):
        _load(_args(["--timeout", "-1"]), workspace)
    with pytest.raises(ConfigError):
        _load(_args(["--max-concurrent-tasks", "65"]), workspace)
    with pytest.raises(ConfigError):
        _load(_args(["--fallback-models", 'bad"model']), workspace)


def test_cli_flag_beats_project_layer(config_env) -> None:
    _cwd, _home, workspace = config_env
    _write(workspace / ".minicc" / "config.json", {"model": "project-model"})
    config = _load(_args(["--model", "cli-model"]), workspace)
    assert config.model == "cli-model"


def test_completion_continue_ceiling_is_reachable(config_env) -> None:
    """The web loop read this through ``getattr(config, ..., 3)`` while ``Config``
    declared no such field, so no layer could move it - every release capped the
    reviewer at 3 re-runs regardless of what the user wrote."""
    _cwd, home, workspace = config_env
    assert load_config(workspace=workspace).max_completion_continues == 3
    _write(home / "config.json", {"max_completion_continues": 1})
    assert load_config(workspace=workspace).max_completion_continues == 1
    os.environ["MINICC_MAX_COMPLETION_CONTINUES"] = "5"
    try:
        assert load_config(workspace=workspace).max_completion_continues == 5
    finally:
        os.environ.pop("MINICC_MAX_COMPLETION_CONTINUES", None)


@pytest.mark.parametrize("raw,expected", [("0", 1), ("-4", 1), ("99", 8)])
def test_the_ceiling_stays_bounded_when_someone_types_it_wrong(config_env, raw, expected) -> None:
    """Unbounded would mean a typo costs tens of thousands of tokens per round."""
    os.environ["MINICC_MAX_COMPLETION_CONTINUES"] = raw
    try:
        assert load_config().max_completion_continues == expected
    finally:
        os.environ.pop("MINICC_MAX_COMPLETION_CONTINUES", None)


def test_a_non_integer_ceiling_is_a_config_error(config_env) -> None:
    os.environ["MINICC_MAX_COMPLETION_CONTINUES"] = "several"
    try:
        with pytest.raises(ConfigError):
            load_config()
    finally:
        os.environ.pop("MINICC_MAX_COMPLETION_CONTINUES", None)


def test_the_anthropic_endpoint_can_differ_from_the_openai_one(config_env) -> None:
    """Both construction sites read ``anthropic_base_url`` with a default, and no
    config layer could set it, so an Anthropic gateway on its own host was
    unreachable - it always inherited ``base_url``."""
    _cwd, _home, _workspace = config_env
    assert load_config().anthropic_base_url == ""
    os.environ["MINICC_ANTHROPIC_BASE_URL"] = "https://claude.internal/v1/"
    try:
        assert load_config().anthropic_base_url == "https://claude.internal/v1"
    finally:
        os.environ.pop("MINICC_ANTHROPIC_BASE_URL", None)


def test_the_provider_timeout_is_reachable_from_every_layer(config_env) -> None:
    """``Config.timeout`` was passed to the HTTP client in five places but no
    config layer ever resolved it, so it sat at the compiled-in 180s for the Web
    service and every task worker it spawned; only the CLI could move it."""
    _cwd, home, workspace = config_env
    assert load_config().timeout == 180.0
    _write(home / "config.json", {"timeout": 45})
    assert load_config().timeout == 45.0
    os.environ["MINICC_TIMEOUT"] = "60"
    try:
        assert load_config().timeout == 60.0
    finally:
        os.environ.pop("MINICC_TIMEOUT", None)
    _write(workspace / ".minicc" / "config.json", {"timeout": 90})
    assert load_config(workspace=workspace).timeout == 90.0


@pytest.mark.parametrize("raw", ["several", "0", "-5", "inf", "nan"])
def test_a_timeout_that_cannot_be_honored_is_a_config_error(config_env, raw: str) -> None:
    _cwd, _home, _workspace = config_env
    os.environ["MINICC_TIMEOUT"] = raw
    try:
        with pytest.raises(ConfigError):
            load_config()
    finally:
        os.environ.pop("MINICC_TIMEOUT", None)


def test_an_absurd_timeout_is_clamped_instead_of_hanging_forever(config_env) -> None:
    _cwd, _home, _workspace = config_env
    os.environ["MINICC_TIMEOUT"] = "999999"
    try:
        assert load_config().timeout == 3600.0
    finally:
        os.environ.pop("MINICC_TIMEOUT", None)


def test_a_stray_key_in_the_user_layer_is_reported_not_silently_dropped(
    config_env, caplog: pytest.LogCaptureFixture
) -> None:
    """A key nothing reads used to load a clean, unrelated config in silence.

    ``config.py``'s own docstring promises "nothing silently defaults when the
    user explicitly set something" - that held for bad *values* but not for bad
    *names*, which is the half a typo lands in.
    """
    _cwd, home, _workspace = config_env
    _write(home / "config.json", {"compact_threshhold": 1000})
    config = load_config()
    assert config.compact_threshold == DEFAULT_COMPACT_THRESHOLD
    assert config.unrecognized_config_keys == ("compact_threshhold",)
    assert any("compact_threshhold" in line and "compact_threshold" in line for line in caplog.messages)


def test_a_retired_budget_key_explains_itself(config_env, caplog: pytest.LogCaptureFixture) -> None:
    _cwd, home, _workspace = config_env
    _write(home / "config.json", {"max_turns": 40})
    config = load_config()
    assert config.max_turns is None
    assert config.unrecognized_config_keys == ("max_turns",)
    reasons = [line for line in caplog.messages if "max_turns" in line]
    assert any("已废弃" in line and "SOFT_MAX" in line for line in reasons)
    # A retired name gets a reason, not a guess at what the user meant.
    assert not any("是否想写" in line for line in reasons)


def test_the_project_layer_reports_its_own_stray_keys(
    config_env, caplog: pytest.LogCaptureFixture
) -> None:
    _cwd, _home, workspace = config_env
    _write(workspace / ".minicc" / "config.json", {"provider_typer": "openai"})
    config = load_config(workspace=workspace)
    assert config.unrecognized_config_keys == ("provider_typer",)
    line = next(entry for entry in caplog.messages if "provider_typer" in entry)
    assert "项目配置" in line
    assert "用户配置" not in line
    assert "是否想写 'provider_type'" in line


@pytest.mark.parametrize("spelling", ["sandbox", "sandbox_mode"])
def test_sandbox_mode_is_reachable_under_both_spellings(config_env, spelling: str) -> None:
    """``MINICC_SANDBOX`` is the one documented name that does not strip onto its
    field, so the file accepts both the env-derived and the field-derived key."""
    _cwd, home, _workspace = config_env
    _write(home / "config.json", {spelling: "host"})
    config = load_config()
    assert config.sandbox_mode == "host"
    assert config.unrecognized_config_keys == ()


def test_a_dotenv_file_is_not_audited_for_stray_keys(config_env) -> None:
    _cwd, _home, _workspace = config_env
    (_cwd / ".env").write_text(
        "PATH=/usr/local/bin\nSOME_UNRELATED_TOOL=1\nMINICC_MODEL=dotenv-model\n",
        encoding="utf-8",
    )
    config = load_config()
    assert config.model == "dotenv-model"
    assert config.unrecognized_config_keys == ()


def test_the_stray_key_report_is_visible_in_print_config(config_env) -> None:
    _cwd, home, _workspace = config_env
    _write(home / "config.json", {"max_concurrent_task": 4})
    assert "ignored_keys=max_concurrent_task" in load_config().describe()
