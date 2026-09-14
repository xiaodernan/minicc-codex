"""Task history global search tests: TaskStore.search + HTTP route."""

from __future__ import annotations

import json
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path

from minicc.task_store import TaskStore
from minicc.web import AgentService, MiniccHTTPServer, TaskStore as _TS  # noqa: F401
from minicc.webauth import WebAuth


def _snapshot(task_id: str, *, prompt: str, stream: str = "", answer: str = "", workspace: str = "") -> dict:
    return {
        "task_id": task_id,
        "created_at_epoch": 1720000000.0,
        "created_at": "2026-09-13T00:00:00Z",
        "workspace_path": workspace,
        "status": "completed",
        "prompt": prompt,
        "preview": prompt[:120],
        "stream_text": stream,
        "result": {"answer": answer} if answer else None,
        "error": "",
    }


# ---------------------------------------------------------------------------
# TaskStore.search
# ---------------------------------------------------------------------------


def test_search_matches_prompt_stream_and_answer(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.upsert(_snapshot("task-1", prompt="检查 pytest 覆盖率"))
    store.upsert(_snapshot("task-2", prompt="别的任务", stream="日志里出现 needle-token"))
    store.upsert(_snapshot("task-3", prompt="第三项", answer="答案包含 SECRET-WORD"))

    hits = store.search("pytest")
    assert len(hits) == 1
    assert hits[0]["task_id"] == "task-1"
    assert "pytest" in hits[0]["snippet"]
    assert hits[0]["match_count"] == 1

    hits = store.search("needle-token")
    assert [hit["task_id"] for hit in hits] == ["task-2"]

    hits = store.search("secret-word")  # case-insensitive
    assert [hit["task_id"] for hit in hits] == ["task-3"]


def test_search_empty_query_and_limit_clamp(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    for index in range(8):
        store.upsert(_snapshot(f"task-{index}", prompt=f"重复关键词 alpha-{index} alpha"))
    assert store.search("   ") == []
    assert store.search("nonexistent") == []
    hits = store.search("alpha", limit=3)
    assert len(hits) == 3
    # limit values beyond the cap are clamped, not rejected
    assert len(store.search("alpha", limit=9999)) == 8


def test_search_workspace_filter(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.upsert(_snapshot("task-a", prompt="搜索目标词", workspace="D:/w1"))
    store.upsert(_snapshot("task-b", prompt="搜索目标词", workspace="D:/w2"))
    hits = store.search("搜索目标词", workspace_path="D:/w1")
    assert [hit["task_id"] for hit in hits] == ["task-a"]


def test_search_snippet_context_window(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    filler = "x" * 300
    store.upsert(_snapshot("task-1", prompt=f"{filler}关键词{filler}"))
    hits = store.search("关键词")
    snippet = hits[0]["snippet"]
    assert snippet.startswith("…") and snippet.endswith("…")
    assert "关键词" in snippet
    assert len(snippet) < 300 + 20  # context window keeps the snippet bounded


def test_search_tolerates_malformed_rows(tmp_path: Path) -> None:
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    store.upsert(_snapshot("task-1", prompt="可搜索的好任务"))
    import sqlite3

    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO tasks(task_id, created_at, workspace_path, payload) VALUES (?, ?, ?, ?)",
            ("task-bad", 0.0, "", "{not json"),
        )
    hits = store.search("可搜索")
    assert [hit["task_id"] for hit in hits] == ["task-1"]


# ---------------------------------------------------------------------------
# HTTP route
# ---------------------------------------------------------------------------


def _service_stub(tmp_path: Path) -> types.SimpleNamespace:
    store = TaskStore(tmp_path / "http-tasks.sqlite3")
    store.upsert(_snapshot("task-http-1", prompt="HTTP 层搜索验证", workspace="/tmp/ws"))

    def search_history(query: str, limit: int = 50, workspace_path: str | None = None) -> dict:
        return {
            "query": str(query or "").strip(),
            "results": store.search(query, limit=limit, workspace_path=workspace_path),
        }

    return types.SimpleNamespace(
        config=types.SimpleNamespace(max_concurrent_tasks=1),
        workspace_info=lambda: {"name": "stub", "path": "/tmp"},
        search_history=search_history,
    )


class _Server:
    def __init__(self, service: types.SimpleNamespace) -> None:
        self.server = MiniccHTTPServer(("127.0.0.1", 0), service, auth=WebAuth("t", required=False))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def test_history_search_route(tmp_path: Path) -> None:
    server = _Server(_service_stub(tmp_path))
    try:
        request = urllib.request.Request(f"{server.url}/api/history/search?q=HTTP")
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
        assert payload["query"] == "HTTP"
        assert len(payload["results"]) == 1
        assert payload["results"][0]["task_id"] == "task-http-1"

        # Missing query -> 400, matching the API error style.
        request = urllib.request.Request(f"{server.url}/api/history/search")
        try:
            urllib.request.urlopen(request, timeout=5)
            raise AssertionError("expected 400")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
    finally:
        server.shutdown()


def test_agent_service_search_history(tmp_path: Path) -> None:
    service = AgentService(
        tmp_path,
        types.SimpleNamespace(
            yolo=False,
            max_concurrent_tasks=2,
            sandbox_mode="host",
            sandbox_image="python:3.11-slim",
            base_url="https://example.test/v1",
            api_key="test-key",
            model="test-model",
            timeout=10,
            tool_mode="auto",
            reasoning_effort="high",
            max_turns=4,
            compact_threshold=300_000,
            context_window_tokens=300_000,
        ),
    )
    try:
        payload = service.search_history("anything")
        assert payload == {"query": "anything", "results": []}
    finally:
        service.shutdown()
