"""M8-T512 — task not found 判词三个家：404 的机器码有了家，人话没有

「没有这个任务」这条拒绝由三处路由发出：任务读取（GET）、事件流
（`_stream_task`）、POST 兜底。三处的调用形状逐字相同——`_fail(404,
"task not found", code=CODE_TASK_NOT_FOUND)`。机器码 `CODE_TASK_NOT_FOUND`
早有家（M8-T5 的错误码词表），但跟着它一起发的人话句子是三份手拼：码和
句子哪天漂移，按消息匹配的客户端就会在一半路由上认不出这个拒绝。

家安在 `minicc/webserver.py` 常量区，`CODE_TASK_NOT_FOUND` 的隔壁——
同一条拒绝的两半住在一起。
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from minicc.webserver import CODE_TASK_NOT_FOUND, TASK_NOT_FOUND_MESSAGE

REPO = Path(__file__).resolve().parents[1]
HOME = "minicc/webserver.py"


def test_the_home_pins_the_sentence() -> None:
    assert TASK_NOT_FOUND_MESSAGE == "task not found"
    # The two halves of one refusal live next to each other.
    assert CODE_TASK_NOT_FOUND == "task_not_found"


def test_the_sentence_is_spelled_exactly_once() -> None:
    hits: list[tuple[str, int]] = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == TASK_NOT_FOUND_MESSAGE:
                hits.append((path.relative_to(REPO).as_posix(), node.lineno))
    assert len(hits) == 1 and hits[0][0] == HOME, hits


def _handler(tasks: SimpleNamespace, *, real_stream: bool = False) -> tuple[object, list[tuple]]:
    from minicc import webserver

    handler = webserver.MiniccRequestHandler.__new__(webserver.MiniccRequestHandler)
    handler.headers = {}
    handler.server = SimpleNamespace(service=SimpleNamespace(tasks=tasks))
    seen: list[tuple] = []

    handler._authorized = lambda query=None: True
    handler._origin_allowed_for_state_change = lambda: True
    handler._json = lambda payload, status=200: seen.append(("json", payload, status))
    handler._fail = lambda status, message, code=None, exc=None: seen.append(
        ("fail", status, message, code)
    )
    if not real_stream:
        # The stream route test drives the real _stream_task instead, so its
        # own KeyError branch - one of the three homes - actually runs.
        handler._stream_task = lambda task_id, *, after=0: seen.append(
            ("stream", task_id, after)
        )
    return handler, seen


def _missing(task_id: str):
    raise KeyError(task_id)


def test_the_task_read_route_asks_the_home() -> None:
    handler, seen = _handler(SimpleNamespace(get=_missing))
    handler.path = "/api/tasks/t1"
    handler.do_GET()
    assert seen == [("fail", 404, "task not found", "task_not_found")], seen


def test_the_event_stream_route_asks_the_home() -> None:
    handler, seen = _handler(SimpleNamespace(get=_missing), real_stream=True)
    handler.path = "/api/tasks/t1/events"
    handler.do_GET()
    assert seen == [("fail", 404, "task not found", "task_not_found")], seen


def test_the_post_catch_all_asks_the_home() -> None:
    handler, seen = _handler(SimpleNamespace(resume=_missing))
    handler.path = "/api/tasks/t1/resume"
    handler.headers = {"Content-Length": "2"}
    handler.rfile = SimpleNamespace(read=lambda size: b"{}")
    handler.do_POST()
    assert seen == [("fail", 404, "task not found", "task_not_found")], seen
