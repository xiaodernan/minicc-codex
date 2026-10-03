"""M6-T1 补线（M11 系列后的 debt 收账）：可写委派的旋钮真到两面 task 注册处。

路线图 M6-T1 行声称「main.py 新增 ``--subagent-writable`` 并向下传递
``permission_mode``/``allow_network``；``web.py`` 从 config 读取档位参数接线」，
但 ``git log -S`` 里那两处接线从未存在：``subagent_writable`` /
``subagent_max_depth`` 只活在 config.py（describe() 甚至会打印
``subagent=delegated``），两面注册处都不传 ``writable=``——旋钮开了，
子代理也永远是 readonly。这些门钉住补线后的契约：

- 旋钮/旗标开 + 会话 acceptEdits → ``spec.risk == "write"``（yolo 同理出
  exec 档，风险标注同为 "write"）；
- 旋钮开但会话是 default/plan → 注册层诚实失效，仍 readonly（tier 机器的
  既有契约 ``resolve_subagent_tier`` 现在真的参与裁决）；
- 旋钮关 → 逐字节旧形状，readonly；
- ``subagent_max_depth`` 从 config 到达注册处，缺省回落 DEFAULT_MAX_DEPTH；
- ``subagent_max_tokens`` 从 config 到达注册处（M6-T1 补线之二）：设置 →
  数值直通 ``_child_budget`` 的硬 token 上限；未设 → ``None``（旧版无硬上限）。
- yolo 会话 + 旋钮 → ``spec`` 背后 runner 的真实档位是 ``exec``（126 批 §5
  欠账：docstring 声称「yolo 同理出 exec 档」但两面接线处从未单列过门——
  ``risk`` 把 write/exec 都标成 "write"，只有 runner.tier 能分辨）。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from minicc.agent.subagent import DEFAULT_MAX_DEPTH
from minicc.llm.base import LLMResponse


# -- CLI 面 ---------------------------------------------------------------------


@pytest.fixture()
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated MINICC_HOME + workspace（与 test_cli_stage_routing 同形）。"""
    home = tmp_path / "home"
    workspace = tmp_path / "ws"
    home.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "sk-deploy-key")
    monkeypatch.setenv("MINICC_BASE_URL", "https://deploy-gateway.test/v1")
    monkeypatch.setenv("MINICC_MODEL", "terra-main")
    monkeypatch.setenv("MINICC_TIMEOUT", "180")
    keep = {
        "MINICC_HOME",
        "MINICC_API_KEY",
        "MINICC_BASE_URL",
        "MINICC_MODEL",
        "MINICC_TIMEOUT",
    }
    for key in [k for k in os.environ if k.startswith("MINICC_") and k not in keep]:
        monkeypatch.delenv(key)
    return workspace


class _CliSentinel:
    """Deployment provider stand-in; run_agent is stubbed so chat never runs."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = dict(kwargs)

    @classmethod
    def is_transient_failure(cls, error: object) -> bool:
        return False

    def protocol(self) -> str:
        return "chat_completions"

    def protocol_status(self) -> dict[str, str]:
        return {"requested": "chat_completions", "active": "chat_completions"}

    async def chat(self, messages: object, tools: object, on_delta=None):  # noqa: ANN001, ANN201
        return LLMResponse(content="cli-ok")

    async def close(self) -> None:
        return None


@pytest.fixture()
def cli_capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch the provider, ``build_task_tool_spec`` and ``run_agent`` on main.

    The recorder delegates to the real builder so the registry keeps a genuine
    task tool (and the gate can assert the returned spec's risk), while
    capturing the exact registration kwargs the CLI face passes.
    """
    import minicc.main as cli

    monkeypatch.setattr(cli, "OpenAICompatibleProvider", _CliSentinel)
    real_build = cli.build_task_tool_spec
    captured: dict[str, Any] = {}

    def _recording_build(**kwargs: Any):
        captured.update(kwargs)
        spec = real_build(**kwargs)
        captured["risk"] = spec.risk
        # risk collapses write/exec into "write"; the runner carries the real
        # tier, which is the only way a gate can tell the exec face apart.
        captured["tier"] = spec.handler.__self__.tier
        return spec

    monkeypatch.setattr(cli, "build_task_tool_spec", _recording_build)

    async def _stub_run_agent(provider, registry, messages, **kwargs):  # noqa: ANN001, ANN202
        from minicc.agent.loop import TurnResult

        return TurnResult(answer="cli-ok")

    monkeypatch.setattr(cli, "run_agent", _stub_run_agent)
    return captured


def _run_cli(workspace: Path, *extra: str) -> None:
    from minicc.main import main

    exit_code = main(["--workspace", str(workspace), "--no-stream", *extra, "你好"])
    assert exit_code == 0


def test_the_writable_knob_reaches_the_cli_task_spec(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch, cli_capture: dict[str, Any]
) -> None:
    monkeypatch.setenv("MINICC_SUBAGENT_WRITABLE", "1")
    _run_cli(cli_env, "--permission-mode", "acceptEdits")
    assert cli_capture["writable"] is True
    assert cli_capture["permission_mode"] == "acceptEdits"
    assert cli_capture["risk"] == "write", (
        "an authorized session with the knob on must resolve the write tier"
    )


def test_without_the_knob_the_cli_task_spec_stays_readonly(
    cli_env: Path, cli_capture: dict[str, Any]
) -> None:
    _run_cli(cli_env)
    assert cli_capture["writable"] is False
    assert cli_capture["risk"] == "readonly"
    assert cli_capture["max_depth"] == DEFAULT_MAX_DEPTH, (
        "the depth knob falls back to the structural default"
    )


def test_writable_without_an_auto_accepting_mode_stays_readonly(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch, cli_capture: dict[str, Any]
) -> None:
    monkeypatch.setenv("MINICC_SUBAGENT_WRITABLE", "1")
    _run_cli(cli_env)
    assert cli_capture["writable"] is True
    assert cli_capture["permission_mode"] == "default"
    assert cli_capture["risk"] == "readonly", (
        "the knob alone must not unlock delegation - the session mode decides"
    )


def test_the_flag_alone_unlocks_writable_on_the_cli(
    cli_env: Path, cli_capture: dict[str, Any]
) -> None:
    _run_cli(cli_env, "--subagent-writable", "--permission-mode", "acceptEdits")
    assert cli_capture["writable"] is True
    assert cli_capture["risk"] == "write"


def test_the_depth_knob_reaches_the_cli_task_spec(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch, cli_capture: dict[str, Any]
) -> None:
    monkeypatch.setenv("MINICC_SUBAGENT_WRITABLE", "1")
    monkeypatch.setenv("MINICC_SUBAGENT_MAX_DEPTH", "1")
    _run_cli(cli_env, "--permission-mode", "acceptEdits")
    assert cli_capture["max_depth"] == 1


def test_the_token_cap_knob_reaches_the_cli_task_spec(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch, cli_capture: dict[str, Any]
) -> None:
    monkeypatch.setenv("MINICC_SUBAGENT_MAX_TOKENS", "5000")
    _run_cli(cli_env)
    assert cli_capture["max_tokens"] == 5000, (
        "the M6-T1 token knob must finally reach the child budget"
    )


def test_without_the_token_knob_the_cli_child_budget_stays_uncapped(
    cli_env: Path, cli_capture: dict[str, Any]
) -> None:
    _run_cli(cli_env)
    assert cli_capture["max_tokens"] is None, (
        "knob unset keeps the legacy uncapped child budget (None, not 0)"
    )


def test_a_yolo_session_with_the_knob_gets_the_exec_tier_on_the_cli(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch, cli_capture: dict[str, Any]
) -> None:
    monkeypatch.setenv("MINICC_SUBAGENT_WRITABLE", "1")
    _run_cli(cli_env, "--permission-mode", "yolo")
    assert cli_capture["permission_mode"] == "yolo"
    assert cli_capture["risk"] == "write", (
        "exec tier still declares the write risk label - the tool policy level"
    )
    assert cli_capture["tier"] == "exec", (
        "a yolo session with the knob on must resolve the exec tier (bash), "
        "not just the write tier - the docstring has claimed this all along"
    )


# -- web 面 ---------------------------------------------------------------------


def _service(tmp_path: Path, **extra: object):
    from minicc.web import AgentService

    return AgentService(
        tmp_path,
        SimpleNamespace(
            yolo=False,
            max_concurrent_tasks=2,
            sandbox_mode="host",
            sandbox_image="python:3.11-slim",
            base_url="https://example.test/v1",
            api_key="test-key",
            model="primary",
            timeout=10,
            tool_mode="auto",
            reasoning_effort="high",
            max_turns=4,
            compact_threshold=300_000,
            context_window_tokens=300_000,
            fallback_models=(),
            stage_routing=None,
            **extra,
        ),
    )


class _WebSilentProvider:
    """Never meant to chat: the gates stop at registration-time assertions."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    @classmethod
    def is_transient_failure(cls, error: object) -> bool:
        return False

    def protocol(self) -> str:
        return "chat_completions"

    def protocol_status(self) -> dict[str, str]:
        return {"requested": "chat_completions", "active": "chat_completions"}

    async def chat(self, messages: object, tools: object, on_delta=None):  # noqa: ANN001, ANN201
        return LLMResponse(content="web-ok")

    async def close(self) -> None:
        return None


@pytest.fixture()
def web_capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch the provider + ``build_task_tool_spec`` on the web module."""
    import minicc.web as web_module

    monkeypatch.setattr(web_module, "OpenAICompatibleProvider", _WebSilentProvider)
    real_build = web_module.build_task_tool_spec
    captured: dict[str, Any] = {}

    def _recording_build(**kwargs: Any):
        captured.update(kwargs)
        spec = real_build(**kwargs)
        captured["risk"] = spec.risk
        # risk collapses write/exec into "write"; the runner carries the real
        # tier, which is the only way a gate can tell the exec face apart.
        captured["tier"] = spec.handler.__self__.tier
        return spec

    monkeypatch.setattr(web_module, "build_task_tool_spec", _recording_build)
    return captured


def _run_web_task(service: Any, tmp_path: Path, *, permission_mode: str) -> dict[str, Any]:
    try:
        return service._chat_locked(
            {
                "message": "zhi-du-jian-cha-ben-xiang-mu",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
                "permission_mode": permission_mode,
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()


def test_the_writable_knob_reaches_the_web_task_spec(
    tmp_path: Path, web_capture: dict[str, Any]
) -> None:
    service = _service(tmp_path, subagent_writable=True)
    result = _run_web_task(service, tmp_path, permission_mode="acceptEdits")
    assert result is not None
    assert web_capture["writable"] is True
    assert web_capture["permission_mode"] == "acceptEdits"
    assert web_capture["risk"] == "write", (
        "an acceptEdits session with the config knob on must resolve the write tier"
    )


def test_plan_mode_keeps_the_web_subagent_readonly(
    tmp_path: Path, web_capture: dict[str, Any]
) -> None:
    service = _service(tmp_path, subagent_writable=True)
    result = _run_web_task(service, tmp_path, permission_mode="plan")
    assert result is not None
    assert web_capture["writable"] is True
    assert web_capture["permission_mode"] == "plan"
    assert web_capture["risk"] == "readonly", (
        "plan mode is research-only: the subagent stays readonly regardless of the knob"
    )


def test_without_the_knob_the_web_task_spec_stays_readonly(
    tmp_path: Path, web_capture: dict[str, Any]
) -> None:
    service = _service(tmp_path)
    result = _run_web_task(service, tmp_path, permission_mode="acceptEdits")
    assert result is not None
    assert web_capture["writable"] is False
    assert web_capture["risk"] == "readonly"
    assert web_capture["max_depth"] == DEFAULT_MAX_DEPTH


def test_the_token_cap_knob_reaches_the_web_task_spec(
    tmp_path: Path, web_capture: dict[str, Any]
) -> None:
    service = _service(tmp_path, subagent_max_tokens=5000)
    result = _run_web_task(service, tmp_path, permission_mode="acceptEdits")
    assert result is not None
    assert web_capture["max_tokens"] == 5000, (
        "the M6-T1 token knob must finally reach the child budget on the web face"
    )


def test_without_the_token_knob_the_web_child_budget_stays_uncapped(
    tmp_path: Path, web_capture: dict[str, Any]
) -> None:
    service = _service(tmp_path)
    result = _run_web_task(service, tmp_path, permission_mode="acceptEdits")
    assert result is not None
    assert web_capture["max_tokens"] is None


def test_a_yolo_session_with_the_knob_gets_the_exec_tier_on_the_web(
    tmp_path: Path, web_capture: dict[str, Any]
) -> None:
    service = _service(tmp_path, subagent_writable=True)
    result = _run_web_task(service, tmp_path, permission_mode="yolo")
    assert result is not None
    assert web_capture["permission_mode"] == "yolo"
    assert web_capture["risk"] == "write", (
        "exec tier still declares the write risk label - the tool policy level"
    )
    assert web_capture["tier"] == "exec", (
        "a yolo task with the config knob on must resolve the exec tier (bash) "
        "on the web face too - the docstring has claimed this all along"
    )
