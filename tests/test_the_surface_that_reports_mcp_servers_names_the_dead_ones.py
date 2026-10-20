"""M8-T267: the MCP payload the surfaces read must name the servers that are corpses.

``McpManager.status()`` is the only MCP shape with production readers: ``/api/mcp``
(minicc/webserver.py) and ``workspace_info()`` (minicc/web.py, which the workspace panel
renders as a bare "MCP 工具 N" count).  Until this unit it was a roster of *configs*, and
``skipped`` only ever records discovery-time failures — so a server whose child died
**after** it answered ``tools/list`` (crash, OOM, reaped by the supervisor) kept a
byte-identical status to a healthy one.  Measured at cd53a7a with a real stdio child:

    step2 alive  status()={"configured":1,"servers":[{...}],"skipped":{}}
    step3 corpse status()={"configured":1,"servers":[{...}],"skipped":{}}
    VERDICT status_bytes_identical_alive_vs_dead=True

The seam that does know the difference, ``health()`` (ok / dead / unspawned, documented as
"without spawning anything new", M5-T7), had exactly one reader in the tree and it was a
test.  This door gives it a production reader and pins what a human can see:

* every server row carries the ``state`` ``health()`` derived for that name — the 口径 lives
  in one place, so the payload cannot hand-copy a verdict of its own;
* ``states`` is counted from the rows the payload actually ships, so the tally can never
  disagree with the list printed beside it;
* reading the payload must never be the thing that spawns a child;
* both routes carry the state, not just the count.

Real stdio children (the venv interpreter running an inline JSON-RPC server), no mocking of
``subprocess``, and the real ``ThreadingHTTPServer`` for the two route legs.
"""

from __future__ import annotations

import json
import sys
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from minicc.mcp import _DEAD_CLIENT, McpManager, McpServerConfig
from minicc.task_store import TaskStore
from minicc.web import AgentService, MiniccHTTPServer
from tests.test_http_route_inventory import _wait_for_live_server

SERVER_SRC = r'''
import json, sys

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method, mid = msg.get("method"), msg.get("id")

    def send(result):
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
        sys.stdout.flush()

    if method == "initialize":
        send({"protocolVersion": "2024-11-05", "capabilities": {},
              "serverInfo": {"name": "fake", "version": "0"}})
    elif method == "tools/list":
        send({"tools": [{"name": "echo", "description": "echo", "inputSchema": {}}]})
    elif method in ("resources/list", "prompts/list"):
        send({("resources" if method.startswith("resources") else "prompts"): []})
'''


@pytest.fixture(scope="module")
def fake_server(tmp_path_factory: pytest.TempPathFactory) -> Path:
    script = tmp_path_factory.mktemp("mcpservers") / "fake_server.py"
    script.write_text(SERVER_SRC, encoding="utf-8")
    return script


def _manager(tmp_path: Path, names: tuple[str, ...], script: Path) -> McpManager:
    manager = McpManager(tmp_path)
    manager.configs = [
        McpServerConfig(name=name, command=sys.executable, args=(str(script),))
        for name in names
    ]
    return manager


def _row(status: dict, name: str) -> dict:
    matches = [item for item in status["servers"] if item["name"] == name]
    assert len(matches) == 1, f"server {name!r} appears {len(matches)}x in {status['servers']}"
    return matches[0]


def _spawn(manager: McpManager, name: str) -> None:
    """Build the real child for one named server, leaving the others unspawned.

    ``tool_specs()`` walks the whole fleet, so a mixed-state fixture has to spawn one
    server at a time through the manager's own client cache.
    """
    config = next(item for item in manager.configs if item.name == name)
    client = manager._client(config)
    assert client.process is not None and client.process.poll() is None, (
        f"fixture could not raise a live child for {name!r}"
    )


def _kill(manager: McpManager, name: str) -> int:
    """Kill the child of a server that already answered discovery, and prove it is gone."""
    client = manager.clients.get(name)
    assert client is not None and client is not _DEAD_CLIENT, (
        f"{name} has no live client to kill (state {client!r}); the corpse leg would be vacuous"
    )
    client.process.kill()
    client.process.wait(timeout=30)
    returncode = client.process.returncode
    assert returncode is not None, f"killed child {name} still reports a live pid"
    return returncode


def test_a_server_that_never_got_a_child_is_reported_unspawned(tmp_path: Path, fake_server: Path) -> None:
    manager = _manager(tmp_path, ("quiet",), fake_server)
    row = _row(manager.status(), "quiet")
    assert row["state"] == "unspawned", (
        f"a configured-but-never-contacted server must not read as healthy: {row}"
    )


def test_a_server_whose_child_answered_is_reported_ok(tmp_path: Path, fake_server: Path) -> None:
    manager = _manager(tmp_path, ("live",), fake_server)
    assert len(manager.tool_specs()) == 1
    row = _row(manager.status(), "live")
    assert row["state"] == "ok", f"a responsive server must read ok: {row}"
    manager.close()


def test_a_server_whose_child_died_after_discovery_is_reported_dead(
    tmp_path: Path, fake_server: Path
) -> None:
    manager = _manager(tmp_path, ("corpse",), fake_server)
    assert len(manager.tool_specs()) == 1, "the discovery leg must land before the death leg"
    exitcode = _kill(manager, "corpse")
    row = _row(manager.status(), "corpse")
    assert row["state"] == "dead", (
        f"child of 'corpse' exited {exitcode} yet the payload still reports {row['state']!r}"
    )
    assert "corpse" not in manager.status()["skipped"], (
        "skipped is the discovery-failure channel; a death after discovery must reach state"
    )
    manager.close()


def test_the_payload_does_not_keep_the_alive_bytes_after_the_child_dies(
    tmp_path: Path, fake_server: Path
) -> None:
    """The measured pre-fix invariant, inverted: status() used to be one payload forever.

    At cd53a7a the two readings below were byte-identical, which is exactly how a dead
    server came to be reported as 「已配置」 to a human.
    """
    manager = _manager(tmp_path, ("turns",), fake_server)
    manager.tool_specs()
    alive = json.dumps(manager.status(), sort_keys=True, ensure_ascii=False)
    _kill(manager, "turns")
    dead = json.dumps(manager.status(), sort_keys=True, ensure_ascii=False)
    assert alive != dead, (
        "the payload a surface reads is the same bytes before and after the server died:\n"
        f"  alive={alive}\n  dead ={dead}"
    )
    assert json.loads(dead)["states"].get("dead") == 1, dead
    assert json.loads(alive)["states"].get("dead") is None, alive
    manager.close()


def test_the_states_tally_is_counted_from_the_rows_the_payload_ships(
    tmp_path: Path, fake_server: Path
) -> None:
    manager = _manager(tmp_path, ("stay", "break"), fake_server)
    manager.tool_specs()
    _kill(manager, "break")
    status = manager.status()
    from_rows: dict[str, int] = {}
    for row in status["servers"]:
        from_rows[row["state"]] = from_rows.get(row["state"], 0) + 1
    assert status["states"] == from_rows, (
        f"the tally {status['states']} disagrees with the rows it publishes {from_rows}"
    )
    assert status["states"] == {"ok": 1, "dead": 1}, status
    manager.close()


def test_the_states_tally_sums_to_the_configured_count(
    tmp_path: Path, fake_server: Path
) -> None:
    manager = _manager(tmp_path, ("a", "b", "c"), fake_server)
    _spawn(manager, "a")
    _spawn(manager, "c")
    _kill(manager, "c")
    status = manager.status()
    assert sum(status["states"].values()) == status["configured"] == 3, status
    assert status["states"] == {"ok": 1, "unspawned": 1, "dead": 1}, (
        f"three servers in three states must not fold into one tally: {status['states']}"
    )
    manager.close()


def test_reading_the_status_payload_never_spawns_a_child(
    tmp_path: Path, fake_server: Path
) -> None:
    """Liveness is reported from what already exists: a status read is not a probe.

    ``health()`` promises "without spawning anything new"; folding it into the payload the
    surfaces poll would otherwise turn every settings render into a child spawn.
    """
    manager = _manager(tmp_path, ("untouched",), fake_server)
    for _ in range(3):
        status = manager.status()
        assert status["servers"][0]["state"] == "unspawned", status
    assert manager.clients == {}, (
        f"status() populated the client cache, so it spawned: {list(manager.clients)}"
    )
    for client in manager.clients.values():
        process = getattr(client, "process", None)
        assert process is None or process.poll() is not None, "a child was spawned by status()"


def test_a_negative_cached_server_is_dead_not_absent(tmp_path: Path, fake_server: Path) -> None:
    """A server whose client could never be built is a corpse too, not a missing row."""
    manager = _manager(tmp_path, ("poisoned",), fake_server)
    manager.clients["poisoned"] = _DEAD_CLIENT
    row = _row(manager.status(), "poisoned")
    assert row["state"] == "dead", f"the negative-cache sentinel must read dead: {row}"
    assert manager.status()["states"] == {"dead": 1}, manager.status()


def test_a_mixed_fleet_reports_every_state_from_the_same_source(
    tmp_path: Path, fake_server: Path
) -> None:
    """status() and health() must not be two verdicts about one server."""
    manager = _manager(tmp_path, ("wait", "answer", "die"), fake_server)
    _spawn(manager, "answer")
    _spawn(manager, "die")
    _kill(manager, "die")
    from_health = {row["name"]: row["state"] for row in manager.health()}
    from_status = {row["name"]: row["state"] for row in manager.status()["servers"]}
    assert from_status == from_health, f"payload {from_status} vs health() {from_health}"
    assert from_health == {"wait": "unspawned", "answer": "ok", "die": "dead"}, from_health
    manager.close()


# ---------------------------------------------------------------------------
# the two production channels, over the real HTTP stack
# ---------------------------------------------------------------------------


def _config(tmp_path: Path) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=4,
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
    )


class _LiveSurface:
    """A real AgentService + MiniccHTTPServer whose mcp manager is a fake stdio fleet."""

    def __init__(self, tmp_path: Path, manager: McpManager) -> None:
        self.service = AgentService(
            tmp_path, _config(tmp_path), task_store=TaskStore(tmp_path / "tasks.sqlite3")
        )
        self.service.mcp = manager
        self.server = MiniccHTTPServer(("127.0.0.1", 0), self.service, auth=None)
        self.error: BaseException | None = None
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(
            target=self._serve, kwargs={"poll_interval": 0.05}, daemon=True,
            name="minicc-t267-server",
        )
        self.thread.start()

        def _probe_health(probe_timeout_s: float) -> int:
            request = urllib.request.Request(f"{self.url}/api/health", method="GET")
            try:
                with urllib.request.urlopen(request, timeout=probe_timeout_s) as response:
                    return response.status
            except urllib.error.HTTPError as exc:
                return exc.code

        _wait_for_live_server(
            origin=self.url, thread=self.thread, thread_error=lambda: self.error,
            http_get_status=_probe_health,
        )

    def _serve(self, **kwargs) -> None:
        try:
            self.server.serve_forever(**kwargs)
        except BaseException as exc:  # noqa: BLE001 - reported by the constructor leg
            self.error = exc

    def get_json(self, path: str) -> dict:
        with urllib.request.urlopen(f"{self.url}{path}", timeout=20) as response:
            assert response.status == 200, f"{path} answered {response.status}"
            return json.loads(response.read())

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        assert not self.thread.is_alive(), (
            f"the M8-T267 surface server thread {self.thread.name!r} was still alive 5s "
            f"after shutdown() at {self.url}"
        )
        self.service.shutdown()


@pytest.fixture
def surface(tmp_path: Path, fake_server: Path):
    manager = _manager(tmp_path, ("panel",), fake_server)
    live = _LiveSurface(tmp_path, manager)
    try:
        yield live, manager
    finally:
        live.shutdown()
        manager.close()


def test_the_mcp_route_carries_the_state_to_the_human(surface) -> None:
    live, manager = surface
    assert live.get_json("/api/mcp")["servers"][0]["state"] == "unspawned"
    manager.tool_specs()
    _kill(manager, "panel")
    payload = live.get_json("/api/mcp")
    assert _row(payload, "panel")["state"] == "dead", (
        f"/api/mcp still answers a corpse as a configured server: {payload}"
    )


def test_the_workspace_route_carries_the_state_to_the_human(surface) -> None:
    """``workspace_info()["mcp"]`` is what the workspace panel renders as 「MCP 工具 N」."""
    live, manager = surface
    manager.tool_specs()
    _kill(manager, "panel")
    payload = live.get_json("/api/workspace")["mcp"]
    assert payload["states"] == {"dead": 1}, (
        f"the panel's own payload reports {payload['states']} for a killed child; "
        f"configured={payload['configured']}"
    )
    assert _row(payload, "panel")["state"] == "dead", payload
