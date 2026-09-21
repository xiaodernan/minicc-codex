"""M8-T2 session fork tests (message-level event tree + branching).

Acceptance (docs/ROADMAP_TO_PRODUCT.md M8-T2):
- 一个 10 条消息的会话在第 5 条 fork，两个会话文件独立；
- fork 出的会话追加消息不影响原会话；
- CLI --resume（经 --list-sessions 列出）能恢复 fork。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minicc.main import _print_sessions
from minicc.session import (
    SessionError,
    SessionStore,
    _unsatisfied_tool_calls,
    list_sessions,
)


def _conversation(count: int) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": "SYS"}]
    roles = ["user", "assistant"]
    for index in range(count - 1):
        role = roles[index % 2]
        messages.append({"role": role, "content": f"{role} turn {index + 1}"})
    return messages


def _raw(store: SessionStore) -> dict:
    return json.loads(store.path.read_text(encoding="utf-8"))


# --- message-level ids --------------------------------------------------------


def test_save_stamps_ids_and_load_strips_them(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "ids")
    store.save(_conversation(4))
    stored = _raw(store)["messages"]
    assert all(isinstance(item.get("id"), str) and item["id"].startswith("m-") for item in stored)
    loaded = store.load("SYS")
    assert all("id" not in message for message in loaded)
    assert [message["content"] for message in loaded] == [item["content"] for item in stored]


def test_ids_are_stable_across_appends(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "stable")
    base = _conversation(3)
    store.save(base)
    first_ids = [item["id"] for item in _raw(store)["messages"]]
    store.save(base + [{"role": "assistant", "content": "appended"}])
    second = _raw(store)["messages"]
    assert [item["id"] for item in second[:3]] == first_ids
    assert second[3]["id"] not in first_ids


def test_duplicate_content_messages_get_distinct_ids(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "dups")
    store.save(
        [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "same"},
            {"role": "user", "content": "same"},
        ]
    )
    ids = [item["id"] for item in _raw(store)["messages"]]
    assert len(set(ids)) == 3


# --- fork ---------------------------------------------------------------------


def test_fork_at_fifth_message_is_independent(tmp_path: Path) -> None:
    source = SessionStore(tmp_path, "main")
    source.save(_conversation(10))
    branch = source.fork(5, new_session_id="branch5")

    assert branch.path.is_file() and branch.path != source.path
    assert [item["role"] for item in _raw(branch)["messages"]] == [
        item["role"] for item in _raw(source)["messages"][:5]
    ]
    lineage = _raw(branch)["forked_from"]
    assert lineage == {
        "session": "main",
        "from_message_id": _raw(source)["messages"][4]["id"],
        "keep_messages": 5,
        "at": lineage["at"],
    }

    # Appending to the fork must not touch the source file.
    fork_messages = branch.load("SYS")
    fork_messages.append({"role": "user", "content": "different plan"})
    branch.save(fork_messages)
    assert len(_raw(source)["messages"]) == 10
    assert len(_raw(branch)["messages"]) == 6
    assert _raw(branch)["forked_from"]["session"] == "main"  # lineage survives save


def test_fork_by_message_id_matches_fork_by_count(tmp_path: Path) -> None:
    source = SessionStore(tmp_path, "byid")
    source.save(_conversation(10))
    fifth_id = _raw(source)["messages"][4]["id"]
    by_id = source.fork(fifth_id, new_session_id="id-branch")
    by_count = source.fork(5, new_session_id="count-branch")
    assert [m["id"] for m in _raw(by_id)["messages"]] == [m["id"] for m in _raw(by_count)["messages"]]


def test_two_forks_diverge_without_cross_talk(tmp_path: Path) -> None:
    source = SessionStore(tmp_path, "tree")
    source.save(_conversation(10))
    plan_a = source.fork(5, new_session_id="plan-a")
    plan_b = source.fork(5, new_session_id="plan-b")
    for store, word in ((plan_a, "postgres"), (plan_b, "sqlite")):
        messages = store.load("SYS")
        messages.append({"role": "user", "content": f"use {word}"})
        store.save(messages)
    assert len(_raw(source)["messages"]) == 10
    assert "postgres" in json.dumps(_raw(plan_a), ensure_ascii=False)
    assert "sqlite" not in json.dumps(_raw(plan_a), ensure_ascii=False)
    assert "postgres" not in json.dumps(_raw(plan_b), ensure_ascii=False)


@pytest.mark.parametrize("point", [0, -3, 11, "m-nope", "", 999])
def test_fork_rejects_invalid_points(tmp_path: Path, point: object) -> None:
    source = SessionStore(tmp_path, "reject")
    source.save(_conversation(10))
    with pytest.raises(SessionError):
        source.fork(point)  # type: ignore[arg-type]


def test_fork_target_collision_and_auto_name(tmp_path: Path) -> None:
    source = SessionStore(tmp_path, "auto")
    source.save(_conversation(6))
    source.fork(3, new_session_id="taken")
    with pytest.raises(SessionError, match="已存在"):
        source.fork(3, new_session_id="taken")
    auto = source.fork(3)
    assert auto.session_id.startswith("auto-fork-")
    assert auto.session_id != source.fork(3).session_id  # second fork: new name
    # Auto names stay inside the session-id grammar.
    assert SessionStore(tmp_path, auto.session_id).path == auto.path


def test_fork_from_missing_session_raises(tmp_path: Path) -> None:
    with pytest.raises(SessionError, match="不存在"):
        SessionStore(tmp_path, "ghost").fork(2)


# --- listing / CLI --------------------------------------------------------------


def test_list_sessions_forest_skips_backups_and_bad_files(tmp_path: Path) -> None:
    source = SessionStore(tmp_path, "listed")
    source.save(_conversation(10))
    source.fork(5, new_session_id="listed-child")
    # A rewind backup sidecar must never be listed as a session.
    source.rewind(4)
    assert source.path.with_name("listed.pre-rewind.json").is_file()
    broken = source.path.parent / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    entries = {item["session_id"]: item for item in list_sessions(tmp_path)}
    assert set(entries) == {"listed", "listed-child", "broken"}
    assert entries["listed"]["messages"] == 4  # after rewind
    assert entries["listed"]["forked_from"] is None
    assert entries["listed-child"]["forked_from"]["session"] == "listed"
    assert entries["listed-child"]["messages"] == 5
    assert entries["listed-child"]["title"].startswith("user turn")
    assert entries["broken"]["error"] == "无法读取"


def test_cli_list_sessions_output_includes_fork(tmp_path: Path, capsys) -> None:
    source = SessionStore(tmp_path, "clifork")
    source.save(_conversation(10))
    source.fork(5, new_session_id="clifork-branch")
    _print_sessions(tmp_path)
    out = capsys.readouterr().out
    assert "clifork " in out or "clifork  " in out
    assert "clifork-branch" in out
    assert "fork of clifork" in out
    assert "10" in out and "5" in out


def test_forked_session_restores_like_any_resume(tmp_path: Path) -> None:
    # --resume path: SessionStore(workspace, name).load() on the fork name.
    source = SessionStore(tmp_path, "resume-me")
    source.save(_conversation(10))
    branch = source.fork(5, new_session_id="resume-me-fork")
    reopened = SessionStore(tmp_path, branch.session_id)
    messages = reopened.load("FRESH-SYSTEM")
    assert messages[0]["content"] == "FRESH-SYSTEM"
    assert len(messages) == 5


# --- a cut must not orphan a tool call --------------------------------------
# Found by forking a real conversation at its first assistant turn: the branch
# ended with ``assistant.tool_calls`` and no ``tool`` result, i.e. a history
# the model API rejects, so the branch could not answer its first question.


def _tool_round() -> list[dict[str, object]]:
    return [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "读一下 CODEBOOK.md"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"CODEBOOK.md"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "代号：KX91"},
        {"role": "assistant", "content": "代号是 KX91"},
    ]


def _stored(store: SessionStore) -> list[dict[str, object]]:
    return _raw(store)["messages"]


def test_forking_at_a_tool_call_carries_its_result(tmp_path: Path) -> None:
    source = SessionStore(tmp_path, "toolfork")
    source.save(_tool_round())
    called = next(item for item in _stored(source) if item.get("tool_calls"))
    branch = source.fork(str(called["id"]), new_session_id="toolfork-branch")

    kept = _stored(branch)
    assert [item["role"] for item in kept] == ["system", "user", "assistant", "tool"]
    assert _unsatisfied_tool_calls(kept) == set(), "branch ends in an unanswered tool call"
    # Lineage still names the message the user actually picked.
    assert branch.load("SYS")[-1]["role"] == "tool"


def test_rewinding_into_a_tool_round_carries_its_result(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "toolrewind")
    store.save(_tool_round())
    result = store.rewind(3)
    assert result["kept"] == 4, "cutting at the call without its result is not a rewind"
    assert _unsatisfied_tool_calls(_stored(store)) == set()


def test_a_cut_at_a_complete_turn_is_not_extended(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "clean")
    store.save(_tool_round())
    assert store.rewind(2)["kept"] == 2
    assert len(_stored(SessionStore(tmp_path, "clean"))) == 2


def test_an_unrepairable_history_does_not_chase_forever(tmp_path: Path) -> None:
    """The result is simply missing: extend stops, nothing hangs or raises."""
    broken = _tool_round()[:3]
    rewound = SessionStore(tmp_path, "broken-r")
    rewound.save(broken)
    assert rewound.rewind(2)["kept"] == 2

    source = SessionStore(tmp_path, "broken-f")
    source.save(broken)
    branch = source.fork(3, new_session_id="broken-f-branch")
    assert len(_stored(branch)) == 3


# --- a dropped one-shot task must announce itself ---------------------------


def test_cli_fork_with_task_text_says_it_did_not_run(tmp_path: Path, capsys) -> None:
    from minicc.main import main

    store = SessionStore(tmp_path, "cliforktask")
    store.save(_conversation(6))
    code = main(
        [
            "--workspace", str(tmp_path), "--session-id", "cliforktask",
            "--fork-from", "3", "--new-session-id", "cliforktask-b", "顺便把测试跑一遍",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "已 fork" in out
    assert "没有执行" in out, "exit 0 with a silently dropped task reads as success"
    # The text is reported by length only; the terminal never re-echoes it.
    assert "顺便把测试跑一遍" not in out
    assert len(_stored(SessionStore(tmp_path, "cliforktask-b"))) == 3


def test_cli_fork_without_task_text_stays_quiet(tmp_path: Path, capsys) -> None:
    from minicc.main import main

    SessionStore(tmp_path, "cliforkplain").save(_conversation(6))
    assert main(
        ["--workspace", str(tmp_path), "--session-id", "cliforkplain", "--fork-from", "3"]
    ) == 0
    assert "没有执行" not in capsys.readouterr().out
