"""M8-T508 — 任务 API 路由前缀八个家：四个路由各拼两遍

`/api/tasks/` 在 `webserver.py` 里有八个家：四个路由（events 流、任务读
取、resume、cancel）各自 `startswith` 匹配一遍、`removeprefix` 剥离一遍。
前缀改了匹配器忘了剥离器（或反之），路由就对一半流量 404——没有任何测试
会红。

家安在 `minicc/webserver.py` 模块层常量区：`TASKS_API_PREFIX`。同文件的
`"/api/tasks/batch"` 是另一条路由的精确匹配，不是这个事实，census 用精确
相等天然不误伤。
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/webserver.py"
PREFIX = "/api/tasks/"


def _prefix_sites() -> list[str]:
    sites: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == PREFIX:
                sites.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return sites


def test_the_home_pins_the_prefix() -> None:
    from minicc.webserver import TASKS_API_PREFIX

    assert TASKS_API_PREFIX == "/api/tasks/"


def test_the_prefix_is_spelled_exactly_once_in_the_package() -> None:
    offenders = _prefix_sites()
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the task API prefix is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_all_eight_sites_ask_the_home() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("TASKS_API_PREFIX") == 9, (
        "webserver.py references the prefix "
        f"{source.count('TASKS_API_PREFIX')} times, expected 9 "
        "(one definition, four matchers, four strippers)"
    )


def _handler(monkeypatch, tasks):
    from minicc import webserver

    handler = webserver.MiniccRequestHandler.__new__(webserver.MiniccRequestHandler)
    handler.headers = {}
    handler.server = SimpleNamespace(service=SimpleNamespace(tasks=tasks))
    seen: list[tuple] = []

    handler._authorized = lambda query=None: True
    handler._origin_allowed_for_state_change = lambda: True
    handler._json = lambda payload, status=200: seen.append(("json", payload, status))
    handler._fail = lambda status, message, code=None, exc=None: seen.append(
        ("fail", status, message)
    )
    handler._stream_task = lambda task_id, *, after=0: seen.append(
        ("stream", task_id, after)
    )
    return handler, seen


def test_the_events_route_asks_the_home(monkeypatch) -> None:
    handler, seen = _handler(monkeypatch, SimpleNamespace())
    handler.path = "/api/tasks/t1/events"
    handler.do_GET()
    assert seen == [("stream", "t1", 0)], seen


def test_the_task_read_route_asks_the_home(monkeypatch) -> None:
    handler, seen = _handler(
        monkeypatch, SimpleNamespace(get=lambda task_id: {"id": task_id})
    )
    handler.path = "/api/tasks/t1"
    handler.do_GET()
    assert seen == [("json", {"id": "t1"}, 200)], seen


def test_the_resume_route_asks_the_home(monkeypatch) -> None:
    handler, seen = _handler(
        monkeypatch,
        SimpleNamespace(resume=lambda task_id: {"id": task_id, "resumed": True}),
    )
    handler.path = "/api/tasks/t1/resume"
    handler.headers = {"Content-Length": "2"}
    handler.rfile = SimpleNamespace(read=lambda size: b"{}")
    handler.do_POST()
    assert seen == [("json", {"id": "t1", "resumed": True}, 202)], seen


def test_the_cancel_route_asks_the_home(monkeypatch) -> None:
    handler, seen = _handler(
        monkeypatch,
        SimpleNamespace(cancel=lambda task_id: {"id": task_id, "cancelled": True}),
    )
    handler.path = "/api/tasks/t1/cancel"
    handler.headers = {"Content-Length": "2"}
    handler.rfile = SimpleNamespace(read=lambda size: b"{}")
    handler.do_POST()
    assert seen == [("json", {"id": "t1", "cancelled": True}, 200)], seen
