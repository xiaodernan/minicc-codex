"""M8-T264: a tool-discovery pass must not die with the first server that cannot start.

``McpManager.tool_specs()`` walked every configured server in one pass and, the moment one
of them refused to answer, re-raised — so ``build_registry`` (minicc/tools/__init__.py) had
no containment left and the session lost all of its builtin tools.  Worse, the pass's outer
handler reaped and negative-cached the *healthy* servers that had already answered, so a
retry named a healthy server in the error.  The sibling seam ``resources_context()`` already
promised the opposite 口径 ("dead or unspawnable servers are skipped rather than allowed to
stall discovery").

This door pins that 口径 for the tool bridge, per server:

* the failing server is skipped, its child reaped, its negative cache kept (M5-T3 stands);
* every other server keeps its tools, its client and its single spawn;
* the skip is disclosed on two channels — ``status()`` (which ``/api/mcp`` and the web state
  payload read) and a WARNING naming the server — and the healthy-only control proves the
  disclosure is not decoration.

Real stdio children (the venv interpreter), no mocking of ``subprocess``.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

from minicc.mcp import McpError, McpManager, McpServerConfig, McpStdioClient
from minicc.tools import Editor, build_registry

ECHO_SERVER_SRC = r'''
import json, sys

spec = json.load(open(sys.argv[1], encoding="utf-8"))
tools = spec.get("tools", [])

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    method = msg.get("method")
    mid = msg.get("id")
    reply = None
    if method == "initialize":
        reply = {"protocolVersion": "2024-11-05", "capabilities": {},
                 "serverInfo": {"name": "echo", "version": "0"}}
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        reply = {"tools": tools}
    if mid is None:
        continue
    out = {"jsonrpc": "2.0", "id": mid,
           "result": reply if reply is not None else {"tools": []}}
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()
'''

# The other failure shape: this one answers ``initialize`` (so its client is constructed and
# cached), then dies on ``tools/list`` with bytes the reader cannot parse.
GLITCH_SERVER_SRC = r'''
import json, sys

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    if msg.get("method") == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "serverInfo": {"name": "glitch", "version": "0"}}}) + "\n")
        sys.stdout.flush()
    elif msg.get("method") == "tools/list":
        sys.stdout.flush()
        sys.stdout.buffer.write(b"\xff\xfe\x00bad\n")
        sys.stdout.buffer.flush()
        sys.exit(0)
'''

BOOT_EXIT_ARGS = ["-c", "raise SystemExit(7)"]
HEALTHY_TOOL_NAME = "mcp__echo__healthy_tool"


def _servers(ws: Path) -> dict[str, dict]:
    echo = ws / "echo_server.py"
    glitch = ws / "glitch_server.py"
    spec = ws / "spec_one.json"
    return {
        # A child that exits at once: the client never finishes initializing.
        "dead": {"command": sys.executable, "args": BOOT_EXIT_ARGS},
        "dead2": {"command": sys.executable, "args": ["-c", "raise SystemExit(8)"]},
        "echo": {"command": sys.executable, "args": [str(echo), str(spec)], "read_only": True},
        # Answers initialize, dies on tools/list.
        "glitch": {"command": sys.executable, "args": [str(glitch)]},
        # Another transport hitting the same discovery seam, in-process.
        "ghost": {"url": "http://127.0.0.1:9/mcp"},
    }


def _workspace(tmp_path: Path, order: list[str], tag: str) -> Path:
    ws = tmp_path / f"ws_{tag}_{'_'.join(order)}"
    (ws / ".minicc").mkdir(parents=True, exist_ok=True)
    (ws / "echo_server.py").write_text(ECHO_SERVER_SRC, encoding="utf-8")
    (ws / "glitch_server.py").write_text(GLITCH_SERVER_SRC, encoding="utf-8")
    (ws / "spec_one.json").write_text(
        json.dumps({"tools": [{"name": "healthy_tool", "description": "ok"}]}), encoding="utf-8")
    servers = _servers(ws)
    (ws / ".minicc" / "mcp.json").write_text(
        json.dumps({"servers": {name: servers[name] for name in order}}), encoding="utf-8")
    return ws


def _manager(tmp_path: Path, order: list[str], tag: str) -> tuple[McpManager, Path]:
    ws = _workspace(tmp_path, order, tag)
    return McpManager(ws), ws


def _spawn_count(ws: Path, name: str) -> int:
    audit = ws / ".minicc" / "mcp_audit.jsonl"
    if not audit.is_file():
        return 0
    rows = [json.loads(line).get("name")
            for line in audit.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows.count(name)


def _disclosed(manager: McpManager, caplog: pytest.LogCaptureFixture) -> set[str]:
    """Servers the pass disclosed as skipped, on either shipped channel.

    ``status()`` and the WARNING are pinned *separately* by E5 and E6; here either channel
    counts, so a case whose claim is "the skip was disclosed" does not silently become a
    second reading of one channel.
    """
    names = set(manager.status().get("skipped") or {})
    for record in caplog.records:
        if record.levelno < logging.WARNING:
            continue
        text = record.getMessage()
        for config in manager.configs:
            if f"MCP server {config.name} " in text:
                names.add(config.name)
    return names


def _builtin_names(workspace: Path) -> set[str]:
    """The same build, on the same plane, with no bridge at all (the control denominator)."""
    plain = workspace / "no_bridge"
    plain.mkdir(parents=True, exist_ok=True)
    return set(build_registry(Editor(plain), mcp_manager=None).names())


def test_a_dead_server_does_not_abort_discovery_for_the_healthy_one(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="minicc.mcp")
    for order in (["dead", "echo"], ["echo", "dead"]):
        manager, ws = _manager(tmp_path, order, "e1")
        try:
            specs = manager.tool_specs()
        finally:
            manager.close()
        names = [spec.name for spec in specs]
        assert HEALTHY_TOOL_NAME in names, (
            f"order {order} in {ws}: discovery aborted and lost the server that answered; "
            f"got {names}"
        )


def test_the_shipped_build_registry_keeps_all_builtins_when_one_server_cannot_start(tmp_path: Path) -> None:
    manager, ws = _manager(tmp_path, ["dead", "echo"], "e2")
    base = _builtin_names(ws)
    assert base, "the bridge-less build produced no tools - the denominator is empty"
    try:
        names = set(build_registry(Editor(ws), mcp_manager=manager).names())
    finally:
        manager.close()
    missing = sorted(base - names)
    assert not missing, f"a server that cannot start cost these builtin tools: {missing}"
    assert HEALTHY_TOOL_NAME in names, f"the answering server lost its tool: {sorted(names)}"
    assert len(names) == len(base) + 1, f"expected {len(base) + 1} tools, got {len(names)}"


def test_the_server_that_answered_keeps_its_client_after_a_sibling_fails(tmp_path: Path) -> None:
    manager, ws = _manager(tmp_path, ["echo", "dead"], "e3")
    try:
        first = [spec.name for spec in manager.tool_specs()]
        spawned_after_first = _spawn_count(ws, "echo")
        assert HEALTHY_TOOL_NAME in first, f"first pass lost the answering server: {first}"
        second = [spec.name for spec in manager.tool_specs()]
        assert second == first, (
            f"the server that answered kept its tools for the caller but not for the retry: "
            f"first pass {first}, second pass {second} (a sibling's failure negative-cached it)"
        )
        spawned_after_second = _spawn_count(ws, "echo")
        assert spawned_after_second == spawned_after_first, (
            f"the healthy server was respawned after its sibling failed: "
            f"{spawned_after_first} -> {spawned_after_second} spawn records in mcp_audit.jsonl"
        )
    finally:
        manager.close()


def test_the_dead_server_is_spawned_once_across_three_passes(tmp_path: Path) -> None:
    manager, ws = _manager(tmp_path, ["dead", "echo"], "e4")
    try:
        for attempt in (1, 2, 3):
            specs = manager.tool_specs()
            assert specs is not None, f"pass {attempt} returned nothing at all"
        dead_spawns = _spawn_count(ws, "dead")
        echo_spawns = _spawn_count(ws, "echo")
    finally:
        manager.close()
    assert dead_spawns == 1, (
        f"the server that cannot start cost {dead_spawns} spawns across three passes; the "
        "negative cache (M5-T3) must survive the pass that skips it"
    )
    assert echo_spawns == 1, (
        f"the answering server was spawned {echo_spawns} times by three passes that all succeeded"
    )


def test_status_names_the_server_that_was_skipped_and_why(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="minicc.mcp")
    scratch = tmp_path / "derive_client"
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        McpStdioClient(McpServerConfig(name="dead", command=sys.executable,
                                       args=tuple(BOOT_EXIT_ARGS)), scratch)
    except McpError as exc:
        startup_sentence = str(exc)
    else:
        raise AssertionError(
            "the boot-exit fixture initialized successfully - it no longer fails the way this "
            "case claims, so the disclosure text below proves nothing"
        )
    assert startup_sentence.strip(), "the client raised an McpError whose text is empty"

    manager, ws = _manager(tmp_path, ["dead", "echo"], "e5")
    try:
        manager.tool_specs()  # exactly one pass: the record is last-write-wins
        skipped = manager.status().get("skipped")
    finally:
        manager.close()
    assert isinstance(skipped, dict), f"status() exposes no skip record: {skipped!r}"
    assert "dead" in skipped, f"status() does not name the server it skipped: {skipped}"
    reason = str(skipped["dead"])
    assert startup_sentence in reason, (
        f"the recorded reason does not carry the exception's own words; expected {startup_sentence!r} "
        f"inside {reason!r}"
    )


def test_the_warning_for_a_skipped_server_is_emitted_with_its_name(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="minicc.mcp")
    manager, ws = _manager(tmp_path, ["dead", "echo"], "e6")
    try:
        manager.tool_specs()
    finally:
        manager.close()
    warnings = [record.getMessage() for record in caplog.records
                if record.levelno >= logging.WARNING and record.name == "minicc.mcp"]
    named = [text for text in warnings if "MCP server dead " in text]
    assert named, (
        f"no WARNING from minicc.mcp names the skipped server; got {warnings}"
    )


def test_a_server_that_answers_but_cannot_list_tools_is_skipped_the_same_way(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="minicc.mcp")
    manager, ws = _manager(tmp_path, ["glitch", "echo"], "e7")
    try:
        names = [spec.name for spec in manager.tool_specs()]
        disclosed = _disclosed(manager, caplog)
    finally:
        manager.close()
    assert names == [HEALTHY_TOOL_NAME], (
        f"the server that dies on tools/list took the answering server with it: {names}"
    )
    assert "glitch" in disclosed, f"the tools/list failure was not disclosed: {disclosed}"


def test_every_server_dead_leaves_the_builtins_and_an_empty_mcp_toolset(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="minicc.mcp")
    manager, ws = _manager(tmp_path, ["dead", "dead2"], "e8")
    base = _builtin_names(ws)
    try:
        specs = manager.tool_specs()
        disclosed = _disclosed(manager, caplog)
        names = set(build_registry(Editor(ws), mcp_manager=manager).names())
    finally:
        manager.close()
    assert specs == [], f"with no server able to answer, the MCP toolset must be empty: {specs}"
    assert not [name for name in names if name.startswith("mcp__")], (
        f"an MCP tool survived a pass in which every server failed: {sorted(names)}"
    )
    assert base <= names, f"builtins lost with every server dead: {sorted(base - names)}"
    assert {"dead", "dead2"} <= disclosed, (
        f"both failing servers must be disclosed, got {sorted(disclosed)}"
    )


def test_the_http_transport_refuses_an_unreachable_server_the_same_way(tmp_path: Path, caplog,
                                                                       monkeypatch) -> None:
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_MCP", "1")
    caplog.set_level(logging.WARNING, logger="minicc.mcp")
    manager, ws = _manager(tmp_path, ["ghost"], "e9")
    try:
        specs = manager.tool_specs()
        disclosed = _disclosed(manager, caplog)
    finally:
        manager.close()
    assert specs == [], f"an unreachable http server must yield no specs, got {specs}"
    assert "ghost" in disclosed, (
        f"the http transport skipped the server without disclosing it: {sorted(disclosed)}"
    )


def test_a_healthy_only_config_gains_no_skip_records(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="minicc.mcp")
    manager, ws = _manager(tmp_path, ["echo"], "e10")
    try:
        names = [spec.name for spec in manager.tool_specs()]
        skipped = manager.status().get("skipped")
    finally:
        manager.close()
    warnings = [record.getMessage() for record in caplog.records
                if record.levelno >= logging.WARNING and record.name == "minicc.mcp"]
    assert names == [HEALTHY_TOOL_NAME], f"the healthy control did not yield its tool: {names}"
    # ``or {}`` on purpose: this case is the control the *old* code must also satisfy, so it
    # may only fail on "skips were recorded", never on "status() has no such key yet".
    assert not (skipped or {}), (
        f"a pass with no failure still recorded skips ({skipped}); the disclosure would then be "
        "decoration rather than evidence"
    )
    assert not warnings, f"a healthy pass emitted a failure WARNING: {warnings}"
