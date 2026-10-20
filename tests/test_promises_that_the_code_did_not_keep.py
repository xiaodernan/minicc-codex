"""M8-T275 / T276 / T277 / T278 / T279 — 一批「说了什么」和「做了什么」对不上的地方

这一批的六个缺陷分属三个模块，但形状相同：**一句承诺写在注释或文档里，代码做的是另一件事**。

| 编号 | 承诺 | 实际 |
| --- | --- | --- |
| M8-T275 | 显式参数 > 环境变量 > .env > 项目层 > 用户层 | 配置里的 ``yolo`` **无条件改写**了显式的 ``--permission-mode plan``；Web 面保留 plan，CLI 面变成全放行 |
| M8-T276 | 层的优先级高于拼写 | 两种拼法分两轮扫全部层，**拼写**决定了哪一层赢 |
| M8-T277 | 坏文件按各模块自己的契约处理 | ``UnicodeDecodeError`` 既不是 ``OSError`` 也不是 ``json.JSONDecodeError``，四个模块的契约同时被打破 |
| M8-T278 | 32 KB 读取上限 | ``read_bytes()[:32KB]`` —— 整个文件先进内存，再切片 |
| M8-T279 | 只有真的跑了检查才算验证证据 | 后台启动的 bash 返回 ``status="ok"``（一行测试都没跑），被算成"改完之后已验证" |

外加一条是**本批次自己引入又当场修掉的**：CLI 的工具级授权分支被 ``.lower()``
折进了小写分支，提示里写着的 ``A`` 永远走不到。

This door pins every one of them.
"""

from __future__ import annotations

import json
import types
from pathlib import Path
from typing import Any

import pytest

from minicc.agent.tool_policy import is_verification_evidence
from minicc.config import ConfigError, load_config
from minicc.main import _apply_cli_overrides
from minicc.mentions import MENTION_READ_BYTES, apply_mentions
from minicc.snapshots import SnapshotError
from minicc.snapshots import _load as load_snapshot
from minicc.workspaces import WorkspaceCatalog


# --- M8-T275: an explicit --permission-mode plan must survive a yolo config ---


def _args(**overrides: Any) -> types.SimpleNamespace:
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
    return types.SimpleNamespace(**base)


def _config(**overrides: Any) -> Any:
    from minicc.config import Config

    base: dict[str, Any] = {
        "base_url": "https://example.test/v1",
        "api_key": "test-key",
        "model": "m",
    }
    base.update(overrides)
    return Config(**base)


def test_an_explicit_plan_mode_is_not_overridden_by_a_yolo_config() -> None:
    """The safe direction wins over the configuration layer."""
    config = _config(yolo=True)
    updated = _apply_cli_overrides(config, _args(permission_mode="plan"))
    assert updated.yolo is False, "the configured yolo silently overrode the explicit plan mode"


def test_a_yolo_config_still_applies_without_an_explicit_plan() -> None:
    """The control: the configuration layer keeps its meaning."""
    config = _config(yolo=True)
    updated = _apply_cli_overrides(config, _args(permission_mode="default"))
    assert updated.yolo is True


def test_a_plan_mode_without_a_yolo_config_is_unchanged() -> None:
    config = _config(yolo=False)
    updated = _apply_cli_overrides(config, _args(permission_mode="plan"))
    assert updated.yolo is False


# --- M8-T276: the layer decides, not the spelling ---


def _write_layers(tmp_path: Path, *, user: dict[str, Any], project: dict[str, Any]) -> tuple[Path, Path]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps(user), encoding="utf-8")
    workspace = tmp_path / "ws"
    (workspace / ".minicc").mkdir(parents=True, exist_ok=True)
    (workspace / ".minicc" / "config.json").write_text(json.dumps(project), encoding="utf-8")
    return home, workspace


def _load_with_key(monkeypatch: pytest.MonkeyPatch, workspace: Path) -> Any:
    """``load_config`` refuses to answer without a key; give it one."""
    monkeypatch.setenv("MINICC_API_KEY", "test-key")
    monkeypatch.setenv("MINICC_BASE_URL", "https://example.test/v1")
    return load_config(workspace=workspace)


def test_a_project_layer_wins_over_a_user_layer_across_spellings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The user layer wrote the prefixed spelling; the project layer the bare one."""
    home, workspace = _write_layers(
        tmp_path,
        user={"MINICC_MODEL": "user-model"},
        project={"model": "project-model"},
    )
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.delenv("MINICC_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    config = _load_with_key(monkeypatch, workspace)
    assert config.model == "project-model", (
        "the spelling decided which layer won; the layer decides"
    )


def test_a_project_layer_wins_over_a_user_layer_the_other_way_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, workspace = _write_layers(
        tmp_path,
        user={"model": "user-model"},
        project={"MINICC_MODEL": "project-model"},
    )
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.delenv("MINICC_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    config = _load_with_key(monkeypatch, workspace)
    assert config.model == "project-model"


def test_a_dotenv_value_wins_over_both_config_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, workspace = _write_layers(
        tmp_path,
        user={"model": "user-model"},
        project={"model": "project-model"},
    )
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.delenv("MINICC_MODEL", raising=False)
    (tmp_path / ".env").write_text("model=dotenv-model\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    config = _load_with_key(monkeypatch, workspace)
    assert config.model == "dotenv-model"


def test_the_environment_wins_over_the_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, workspace = _write_layers(
        tmp_path,
        user={"model": "user-model"},
        project={"model": "project-model"},
    )
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_MODEL", "env-model")
    (tmp_path / ".env").write_text("model=dotenv-model\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    config = _load_with_key(monkeypatch, workspace)
    assert config.model == "env-model"


# --- M8-T277: a file that is not UTF-8 must not break the module's own contract ---


def test_a_config_file_that_is_not_utf8_is_a_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_bytes(b'{"model": "\xff\xfe"}')
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        load_config(workspace=tmp_path)


def test_a_session_file_that_is_not_utf8_does_not_break_the_listing(
    tmp_path: Path,
) -> None:
    from minicc.session import list_sessions

    sessions_dir = tmp_path / ".minicc" / "sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "broken.json").write_bytes(b'{"messages": "\xff"}')
    listed = list_sessions(tmp_path)
    assert any(item.get("session_id") == "broken" for item in listed), (
        "one bad file took the whole listing down"
    )


def test_a_snapshot_manifest_that_is_not_utf8_is_a_snapshot_error(tmp_path: Path) -> None:
    dest = tmp_path / "snap"
    dest.mkdir()
    (dest / "manifest.json").write_bytes(b'{"files": "\xff"}')
    with pytest.raises(SnapshotError):
        load_snapshot(dest, tmp_path)


def test_a_workspace_catalog_that_is_not_utf8_degrades_to_empty(tmp_path: Path) -> None:
    catalog = WorkspaceCatalog(tmp_path / "workspaces.json")
    catalog.path.write_bytes(b'{"path": "\xff"}')
    assert catalog.list() == []


# --- M8-T278: the read ceiling has to be a ceiling ---


def test_a_large_mention_is_read_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole file must not reach the heap before the limit applies."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    big = workspace / "big.txt"
    big.write_text("x" * (MENTION_READ_BYTES * 4), encoding="utf-8")

    read_sizes: list[int] = []
    real_open = Path.open

    class _CountingFile:
        def __init__(self, handle: Any) -> None:
            self._handle = handle

        def read(self, size: int = -1) -> bytes:
            data = self._handle.read(size)
            read_sizes.append(len(data))
            return data

        def __enter__(self) -> "_CountingFile":
            self._handle.__enter__()
            return self

        def __exit__(self, *args: object) -> None:
            self._handle.__exit__(*args)

    def counting_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        return _CountingFile(real_open(self, *args, **kwargs))

    monkeypatch.setattr(Path, "open", counting_open)
    apply_mentions(f"@big.txt 请看这个文件", workspace)
    assert read_sizes, "the file was not read through a bounded handle"
    assert max(read_sizes) <= MENTION_READ_BYTES, (
        f"a mention read {max(read_sizes)} bytes, past the {MENTION_READ_BYTES} ceiling"
    )


# --- M8-T279: a backgrounded command is not verification ---


def test_a_backgrounded_command_is_not_verification_evidence() -> None:
    """Starting a shell runs nothing, so it proves nothing."""
    assert is_verification_evidence(
        "bash", {"command": "python -m pytest", "run_in_background": True}, "ok"
    ) is False


def test_the_same_command_in_the_foreground_is_verification_evidence() -> None:
    """The control: the foreground path is unchanged."""
    assert is_verification_evidence(
        "bash", {"command": "python -m pytest"}, "ok"
    ) is True


def test_a_failed_foreground_command_is_not_verification_evidence() -> None:
    assert is_verification_evidence(
        "bash", {"command": "python -m pytest"}, "error"
    ) is False


# --- the CLI's two "always" answers must be reachable and must mean different things ---


def _gate(monkeypatch: pytest.MonkeyPatch, answer: str, workspace: Path) -> tuple[bool, dict[str, list[str]]]:
    """Drive the CLI gate with one typed answer and report the rule it wrote."""
    from minicc.allowlist import session_rules
    from minicc.main import _permission_gate
    from minicc.tools import build_registry
    from minicc.tools.editor import Editor
    from minicc.tools.schemas import ToolCall

    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    registry = build_registry(Editor(workspace))
    gate = _permission_gate(
        _config(yolo=False),
        registry,
        "default",
        session_id="s1",
        workspace=workspace,
    )
    # A plain command, not one of the narrowly allowed read-only verifiers
    # (a bare ``pytest`` is auto-approved without asking).
    allowed = gate("bash", ToolCall(
        tool="bash",
        arguments={"command": "echo hello"},
        call_id="c1",
    ))
    return allowed, session_rules(workspace, "s1")


def test_the_uppercase_answer_writes_a_tool_wide_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``A`` is "always allow every use of this tool" - and it must be reachable.

    The answer used to be lowercased before the comparison, so the uppercase
    branch could never match and the tool-wide grant was unreachable.
    """
    allowed, rules = _gate(monkeypatch, "A", tmp_path)
    assert allowed is True
    assert rules["tools"] == ["bash"], "the tool-wide rule was not written"
    assert rules["commands"] == [], "the narrow rule was written instead"


def test_the_lowercase_answer_writes_a_narrow_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``a`` is "always allow this command" - not the whole tool."""
    allowed, rules = _gate(monkeypatch, "a", tmp_path)
    assert allowed is True
    assert rules["commands"], "the command rule was not written"
    assert rules["tools"] == [], "the tool-wide rule was written instead"


def test_a_plain_yes_writes_no_rule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: one-off approval leaves the allowlist alone."""
    allowed, rules = _gate(monkeypatch, "y", tmp_path)
    assert allowed is True
    assert rules["tools"] == [] and rules["commands"] == []
