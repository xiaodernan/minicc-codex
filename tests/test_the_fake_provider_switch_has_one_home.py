"""M8-T484 — 假 provider 开关的四个家，和一个没有恢复路径的进程全局写入

「这一跑用确定性假 provider」是一个事实，但它有四个家：环境变量名
``MINICC_FAKE_PROVIDER`` 在 task_worker（写）、task_manager（launcher 读）、
web（provider 工厂读）、benchmarks（元数据读）里各拼一遍；argv  flag 住在
task_contract（那一个是好的）。更糟的是写入侧没有恢复路径：
``_install_fake_provider()`` 把进程全局环境变量一设到底，而在进程内跑过一次
worker 之后（本仓自己的往返测试就这么干），这个开关就留在宿主进程里——之后
每个 launcher 都会给奔着真网关去的命令追加 ``--fake-provider``。

T468 的 argv 契约门禁就是这么被染红的：它单独跑全绿，跟在 window 测试后面跑
就红。本批把开关收成一个家（``minicc/llm/fake.py``：变量名 + 判问 + 作用域
安装），并把那道门禁救活。
"""

from __future__ import annotations

import ast
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/llm/fake.py"
ENV = "MINICC_FAKE_PROVIDER"


def test_the_home_owns_the_switch_name_and_the_question() -> None:
    from minicc.llm.fake import FAKE_PROVIDER_ENV, fake_provider_active

    assert FAKE_PROVIDER_ENV == ENV
    os.environ.pop(ENV, None)
    try:
        assert fake_provider_active() is False
        os.environ[ENV] = "1"
        assert fake_provider_active() is True
        os.environ[ENV] = "TRUE"
        assert fake_provider_active() is True
        os.environ[ENV] = "0"
        assert fake_provider_active() is False
    finally:
        os.environ.pop(ENV, None)


def test_no_other_module_spells_the_switch_name() -> None:
    """No module spells the env var name outside the one declaration."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == ENV:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME), (
        "the fake-provider switch name is spelled inline outside its one home: "
        + ", ".join(offenders)
    )


def test_every_reader_asks_the_home() -> None:
    """The factory, the launcher and the metadata all consume the home object."""
    from minicc import benchmarks, task_manager, web
    from minicc.llm import fake

    assert web.fake_provider_active is fake.fake_provider_active
    assert task_manager.fake_provider_active is fake.fake_provider_active
    assert benchmarks.fake_provider_active is fake.fake_provider_active


def test_the_switch_is_scoped_to_the_worker_run() -> None:
    """The install restores what was there before - including "there was nothing"."""
    from minicc.task_worker import _fake_provider_env

    os.environ.pop(ENV, None)
    try:
        with _fake_provider_env():
            assert os.environ[ENV] == "1"
        assert ENV not in os.environ, "an absent switch stayed absent"
        os.environ[ENV] = "0"
        with _fake_provider_env():
            assert os.environ[ENV] == "1"
        assert os.environ[ENV] == "0", "a pre-existing value was clobbered, not restored"
    finally:
        os.environ.pop(ENV, None)


def test_an_in_process_worker_run_does_not_poison_later_launchers(tmp_path: Path) -> None:
    """The exact regression: a fake worker run must not flip later launchers."""
    from minicc.task_contract import FAKE_PROVIDER_FLAG
    from minicc.task_manager import TaskManager, TaskRecord
    from minicc.task_store import TaskStore
    from minicc.task_worker import build_parser, run_worker

    os.environ.pop(ENV, None)
    store_path = tmp_path / "tasks.sqlite3"
    store = TaskStore(store_path)
    store.upsert({
        "task_id": "t-fake", "prompt": "hi", "status": "queued",
        "created_at_epoch": time.time(), "session_id": "s",
    })
    config = {
        "yolo": True, "max_concurrent_tasks": 2, "sandbox_mode": "host",
        "sandbox_image": "python:3.11-slim", "base_url": "https://example.test/v1",
        "api_key": "k", "model": "m", "timeout": 10, "tool_mode": "auto",
        "reasoning_effort": "high", "max_turns": 2, "compact_threshold": 300000,
        "context_window_tokens": 300000, "task_event_limit": 32, "task_stream_limit": 512,
    }
    args = build_parser().parse_args([
        "--workspace", str(tmp_path),
        "--task-id", "t-fake",
        "--session-id", "s",
        "--message", "hi",
        "--store-path", str(store_path),
        "--config-json", json.dumps(config),
        "--fake-provider",
    ])
    try:
        assert run_worker(args) == 0, "the fake-provider worker run must reach a terminal state"
        assert ENV not in os.environ, "the in-process worker run leaked the switch into the host process"

        manager = TaskManager(SimpleNamespace(config=SimpleNamespace(model="m")), max_workers=1)
        try:
            command = manager._worker_command(
                TaskRecord(
                    task_id="t-1", session_id="s-1", message="hello",
                    allow_changes=True, allow_network=True,
                    permission_mode="acceptEdits", reasoning_effort="low", model="",
                ),
                tmp_path, tmp_path / "store.sqlite3", tmp_path / "cancel.flag", False,
            )
        finally:
            manager.shutdown()
        assert FAKE_PROVIDER_FLAG not in command, (
            "a launcher built after an in-process fake run handed the real gateway "
            "a --fake-provider command"
        )
    finally:
        os.environ.pop(ENV, None)
