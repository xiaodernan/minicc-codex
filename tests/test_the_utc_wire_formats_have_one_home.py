"""M8-T485 — UTC 时刻的线上格式三个家：九处手拼，三种拼法

「现在几点」渲染到线上，仓库里有三种拼法、九个现场：

* ``%Y-%m-%dT%H:%M:%SZ``（Z 后缀、整秒）——task_worker 的快照 created_at、
  tools/memory 的记忆条目、tools/todo 的待办文件；
* ``datetime.now(UTC).isoformat(timespec="seconds")``（偏移后缀、整秒）
  ——session 的四处记录加 tools/editor 的默认时钟；
* ``datetime.fromtimestamp(ts, timezone.utc).isoformat()``（微秒精度）
  ——task_manager 的 `_iso`，被 task_manager 自己七处加 web 两处使用。

一种拼法在一个现场忘了跟着改，就是一根没人能比对的时间戳；一个 ``gmtime``
悄悄变成 ``localtime``，就是一份创建时间差着宿主时区的快照。本批把三种拼法
收进一个家 `minicc/clock.py`：每种拼法全场只准出现一次，且只能出现在家里。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/clock.py"


def test_the_home_owns_the_three_spellings() -> None:
    from minicc.clock import UTC_STAMP_FORMAT, utc_iso, utc_now_iso, utc_stamp

    assert UTC_STAMP_FORMAT == "%Y-%m-%dT%H:%M:%SZ"
    assert utc_stamp(0) == "1970-01-01T00:00:00Z"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", utc_stamp())
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", utc_now_iso())
    assert utc_iso(None) is None
    assert utc_iso(0) == "1970-01-01T00:00:00+00:00"


def test_utc_stamp_renders_the_moment_it_is_given() -> None:
    """The epoch parameter is honored, not silently replaced by now."""
    from minicc.clock import utc_stamp

    assert utc_stamp(1_700_000_000) == "2023-11-14T22:13:20Z"


def test_each_spelling_is_written_exactly_once_and_it_is_the_home() -> None:
    """Census: each of the three mechanisms appears once, in clock.py only."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "%Y-%m-%dT%H:%M:%SZ":
                offenders.append(f"{relative}:{node.lineno} format")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "gmtime":
                    offenders.append(f"{relative}:{node.lineno} gmtime")
                elif node.func.attr == "fromtimestamp":
                    offenders.append(f"{relative}:{node.lineno} fromtimestamp")
                elif node.func.attr == "isoformat" and any(
                    kw.arg == "timespec" for kw in node.keywords
                ):
                    offenders.append(f"{relative}:{node.lineno} isoformat-timespec")
                elif node.func.attr == "now" and any(
                    isinstance(arg, ast.Name) and arg.id == "UTC" for arg in node.args
                ):
                    offenders.append(f"{relative}:{node.lineno} now-UTC")
    assert len(offenders) == 5 and all(item.startswith(HOME) for item in offenders), (
        "a UTC wire spelling is written outside its one home: " + ", ".join(offenders)
    )


def test_every_consumer_asks_the_home() -> None:
    """All nine former call sites consume the home's builders."""
    from minicc import clock, session, task_manager, task_worker, web
    from minicc.tools import editor, memory, todo

    assert session.utc_now_iso is clock.utc_now_iso
    assert editor.utc_now_iso is clock.utc_now_iso
    assert task_worker.utc_stamp is clock.utc_stamp
    assert memory.utc_stamp is clock.utc_stamp
    assert todo.utc_stamp is clock.utc_stamp
    assert task_manager.utc_iso is clock.utc_iso
    assert web.utc_iso is clock.utc_iso


def test_a_session_record_still_carries_the_offset_spelling(tmp_path: Path) -> None:
    """The session writer's bytes are unchanged by the move."""
    import json

    from minicc.session import SessionStore

    store = SessionStore(tmp_path, "s-1")
    store.save([{"role": "user", "content": "hi"}])
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", payload["updated_at"])


def test_a_task_record_still_carries_the_microsecond_spelling() -> None:
    """The task manager's rendering is unchanged by the move."""
    from minicc.clock import utc_iso
    from minicc.task_manager import TaskRecord

    record = TaskRecord(
        task_id="t-1", session_id="s-1", message="hello",
        allow_changes=True, allow_network=True,
        permission_mode="acceptEdits", reasoning_effort="low", model="",
    )
    payload = record.snapshot()
    assert payload["created_at"] == utc_iso(record.created_at)
    assert payload["finished_at"] is None
