"""The worker argv contract must have exactly one home."""

from __future__ import annotations

import ast
import pathlib
from types import SimpleNamespace

from minicc import task_contract as tc
from minicc.task_manager import TaskManager, TaskRecord
from minicc.task_worker import build_parser

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = "minicc/task_contract.py"
SIDES = ("minicc/task_worker.py", "minicc/task_manager.py")


def _vocabulary() -> dict[str, str]:
    tree = ast.parse((REPO / HOME).read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id.endswith("_FLAG")
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            found[node.targets[0].id] = node.value.value
    return found


def test_every_flag_constant_is_defined_once_in_the_home():
    vocab = _vocabulary()
    assert len(vocab) >= 15, vocab
    for path in sorted((REPO / "minicc").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id.endswith("_FLAG")
            ):
                rel = path.relative_to(REPO).as_posix()
                assert rel == HOME, (rel, node.lineno, node.targets[0].id)


def test_no_side_spells_a_flag_by_hand():
    """The two sides of the contract live in different processes."""
    for rel in SIDES:
        tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        inline = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("--")
        ]
        assert inline == [], (rel, inline)


def test_the_parser_declares_the_vocabulary_and_nothing_else():
    tree = ast.parse((REPO / "minicc" / "task_worker.py").read_text(encoding="utf-8"))
    declared = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "attr", "") == "add_argument"
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            declared.add(node.args[0].id)
    assert declared == set(_vocabulary()), declared ^ set(_vocabulary())


def _stub_service() -> SimpleNamespace:
    return SimpleNamespace(config=SimpleNamespace(model="stub-model"))


def _task() -> TaskRecord:
    return TaskRecord(
        task_id="t-1",
        session_id="s-1",
        message="hello",
        allow_changes=True,
        allow_network=True,
        permission_mode="acceptEdits",
        reasoning_effort="low",
        model="",
    )


def _parse(command: list[str]):
    return build_parser().parse_args(command[command.index(tc.WORKSPACE_FLAG):])


def test_the_launcher_and_the_parser_agree_at_runtime():
    """The whole point: build the argv, then read it back with the parser."""
    manager = TaskManager(_stub_service(), max_workers=1)
    try:
        command = manager._worker_command(
            _task(), pathlib.Path("."), pathlib.Path("store.sqlite3"),
            pathlib.Path("cancel.flag"), False,
        )
    finally:
        manager.shutdown()
    args = _parse(command)
    assert args.workspace == "."
    assert args.task_id == "t-1"
    assert args.session_id == "s-1"
    assert args.message == "hello"
    assert args.store_path == "store.sqlite3"
    assert args.cancel_file == "cancel.flag"
    assert args.permission_mode == "acceptEdits"
    assert args.reasoning_effort == "low"
    assert args.model == "stub-model"
    assert args.allow_changes is True
    assert args.allow_network is True
    assert args.config_stdin is False
    assert args.fake_provider is False


def test_the_optional_flags_the_launcher_can_add_are_declared():
    manager = TaskManager(_stub_service(), max_workers=1)
    try:
        command = manager._worker_command(
            _task(), pathlib.Path("."), pathlib.Path("s"), pathlib.Path("c"), True,
        )
        command.extend([tc.REQUEST_FILE_FLAG, "req.json", tc.LEASE_OWNER_FLAG, "owner-1"])
    finally:
        manager.shutdown()
    args = _parse(command)
    assert args.config_stdin is True
    assert args.request_file == "req.json"
    assert args.lease_owner == "owner-1"


def test_the_home_is_reachable_from_both_sides():
    for rel in SIDES:
        source = (REPO / rel).read_text(encoding="utf-8")
        assert "from .task_contract import" in source, rel
