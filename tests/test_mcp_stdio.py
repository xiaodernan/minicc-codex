"""M5 MCP stdio/HTTP bridge hardening tests (table-driven, fake servers).

Every stdio case spawns a real child process (the venv interpreter running an
inline JSON-RPC server) so the reader thread, pipe framing, supervision and
reaping are exercised end to end — no mocking of ``subprocess``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from minicc.mcp import (
    McpError,
    McpManager,
    McpServerConfig,
    McpStdioClient,
)
from minicc.tools import Editor, build_registry

SERVER_SRC = r'''
import json, sys

spec = json.load(open(sys.argv[1], encoding="utf-8"))


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def rid(req):
    return str(req["id"]) if spec.get("string_id") else req["id"]


def die_garbage():
    sys.stdout.flush()
    sys.stdout.buffer.write(b"\xff\xfe\x00bad\n")
    sys.stdout.buffer.flush()
    sys.exit(0)


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
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": rid(msg), "result": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "serverInfo": {"name": "fake", "version": "0"}}})
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        if spec.get("garbage_on_list"):
            die_garbage()
        send({"jsonrpc": "2.0", "id": rid(msg), "result": {"tools": spec.get("tools", [])}})
    elif method == "resources/list":
        send({"jsonrpc": "2.0", "id": rid(msg), "result": {"resources": spec.get("resources", [])}})
    elif method == "prompts/list":
        send({"jsonrpc": "2.0", "id": rid(msg), "result": {"prompts": spec.get("prompts", [])}})
    elif method == "tools/call":
        if spec.get("ping_on_call"):
            send({"jsonrpc": "2.0", "id": "srv-ping", "method": "ping", "params": {}})
            got = None
            for rline in sys.stdin:
                r = rline.strip()
                if not r:
                    continue
                try:
                    rm = json.loads(r)
                except json.JSONDecodeError:
                    continue
                if rm.get("id") == "srv-ping":
                    got = rm
                    break
            text = "pong" if (got and "result" in got) else "no-response"
            send({"jsonrpc": "2.0", "id": rid(msg), "result": {
                "content": [{"type": "text", "text": text}], "isError": False}})
            continue
        repeat = spec.get("call_repeat")
        text = ("A" * int(repeat)) if repeat else spec.get("call_text", "ok")
        send({"jsonrpc": "2.0", "id": rid(msg), "result": {
            "content": [{"type": "text", "text": text}],
            "isError": bool(spec.get("call_error"))}})
    elif mid is not None:
        send({"jsonrpc": "2.0", "id": rid(msg), "error": {"code": -32601, "message": "unknown"}})
'''


def _spawn(tmp_path: Path, spec: dict, *, name: str = "fake") -> tuple[McpServerConfig, Path]:
    """Materialize the fake server + its spec; return a stdio config."""
    server = tmp_path / "fake_mcp_server.py"
    if not server.exists():
        server.write_text(SERVER_SRC, encoding="utf-8")
    spec_path = tmp_path / f"spec_{name}.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    config = McpServerConfig(
        name=name,
        command=sys.executable,
        args=(str(server), str(spec_path)),
    )
    return config, spec_path


def _client(tmp_path: Path, spec: dict, *, name: str = "fake") -> McpStdioClient:
    config, _ = _spawn(tmp_path, spec, name=name)
    return McpStdioClient(config, tmp_path)


def _write_mcp_json(workspace: Path, name: str, spec_path: Path) -> None:
    server = workspace / "fake_mcp_server.py"
    server.write_text(SERVER_SRC, encoding="utf-8")
    (workspace / ".minicc").mkdir(parents=True, exist_ok=True)
    (workspace / ".minicc" / "mcp.json").write_text(
        json.dumps({"servers": {name: {"command": sys.executable, "args": [str(server), str(spec_path)]}}}),
        encoding="utf-8",
    )


# --- M5-T1: 500k-char output is truncated to the 6000-char budget ------------

def test_half_million_char_output_is_truncated(tmp_path):
    client = _client(tmp_path, {"tools": [{"name": "big"}], "call_repeat": 500_000})
    try:
        result = client.call_tool("big", {})
    finally:
        client.close()
    assert result.truncated is True
    assert len(result.output) <= 6000
    assert len(result.head) <= 2000
    assert len(result.tail) <= 4000
    rendered = result.render()
    assert "输出已截断" in rendered
    assert len(rendered) < 7000


def test_small_output_not_truncated(tmp_path):
    client = _client(tmp_path, {"tools": [{"name": "small"}], "call_text": "hello world"})
    try:
        result = client.call_tool("small", {})
    finally:
        client.close()
    assert result.truncated is False
    assert "hello world" in result.render()


# --- M5-T2: string ids round-trip; server-initiated ping is answered ---------

def test_string_id_response_is_matched(tmp_path):
    client = _client(tmp_path, {"string_id": True, "tools": [{"name": "echo"}], "call_text": "pong-str"})
    try:
        result = client.call_tool("echo", {})
    finally:
        client.close()
    assert result.status == "ok"
    assert "pong-str" in result.render()


def test_server_initiated_ping_is_answered(tmp_path):
    client = _client(tmp_path, {"ping_on_call": True, "tools": [{"name": "probe"}]})
    try:
        result = client.call_tool("probe", {})
    finally:
        client.close()
    # The fake server only emits "pong" if the client answered its ping.
    assert "pong" in result.render()
    assert "no-response" not in result.render()


# --- M5-T3: undecodable stdout marks the client dead and fails fast ----------

def test_undecodable_stdout_fails_fast_not_30s(tmp_path):
    client = _client(tmp_path, {"garbage_on_list": True, "tools": [{"name": "x"}]})
    try:
        started = time.monotonic()
        with pytest.raises(McpError):
            client.list_tools()
        first = time.monotonic() - started
        assert first < 5.0, f"first call should fast-fail, took {first:.2f}s"
        assert client.dead is True
        started = time.monotonic()
        with pytest.raises(McpError):
            client.list_tools()
        second = time.monotonic() - started
        assert second < 1.0, f"second call should be <1s, took {second:.2f}s"
    finally:
        client.close()


def test_manager_negative_cache_does_not_respawn(tmp_path):
    workspace = tmp_path
    (workspace / ".minicc").mkdir(parents=True, exist_ok=True)
    (workspace / ".minicc" / "mcp.json").write_text(
        json.dumps({"servers": {"ghost": {"command": sys.executable, "args": ["-c", "raise SystemExit(3)"]}}}),
        encoding="utf-8",
    )
    manager = McpManager(workspace)
    try:
        with pytest.raises(McpError):
            manager.tool_specs()
        with pytest.raises(McpError):
            manager.tool_specs()
        audit = workspace / ".minicc" / "mcp_audit.jsonl"
        lines = audit.read_text(encoding="utf-8").strip().splitlines() if audit.exists() else []
        # First attempt spawns (and audits) once; the negative cache must stop
        # the second tool_specs() from spawning again.
        assert len(lines) == 1
    finally:
        manager.close()


# --- M5-T4: 128-char truncation collisions get hash-suffixed, not ValueError --

def test_long_tool_name_collision_is_disambiguated(tmp_path):
    shared = "x" * 128
    tools = [
        {"name": shared + "_alpha"},
        {"name": shared + "_beta"},
    ]
    workspace = tmp_path
    spec_path = workspace / "spec_collide.json"
    spec_path.write_text(json.dumps({"tools": tools}), encoding="utf-8")
    _write_mcp_json(workspace, "srv", spec_path)
    manager = McpManager(workspace)
    try:
        specs = manager.tool_specs()
    finally:
        manager.close()
    names = [s.name for s in specs]
    assert len(names) == 2
    assert len(set(names)) == 2, f"collision not resolved: {names}"
    assert all(len(n) <= 128 for n in names)
    # Registering both must not raise the duplicate-name ValueError.
    registry = build_registry(Editor(workspace), mcp_manager=None)
    for spec in specs:
        registry.register(spec)


# --- M5-T5: close() reaps the child ------------------------------------------

def test_close_reaps_child_process(tmp_path):
    client = _client(tmp_path, {"tools": [{"name": "x"}]})
    assert client.process is not None
    assert client.process.poll() is None  # alive
    client.close()
    assert client.process.poll() is not None  # reaped, no zombie


# --- M5-T7: resources/prompts become bounded read-only context ---------------

def test_resources_context_is_bounded_and_injected(tmp_path):
    spec = {
        "tools": [{"name": "t"}],
        "resources": [{"uri": "file:///big", "description": "D" * 7000}],
        "prompts": [{"name": "summarize", "description": "summarize the repo"}],
    }
    workspace = tmp_path
    spec_path = workspace / "spec_res.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    _write_mcp_json(workspace, "srv", spec_path)
    manager = McpManager(workspace)
    try:
        context = manager.resources_context(max_chars=6000)
    finally:
        manager.close()
    assert "file:///big" in context
    assert "summarize" in context
    for line in context.splitlines():
        assert len(line) <= 6000


def test_dead_server_marked_in_health(tmp_path):
    workspace = tmp_path
    spec_path = workspace / "spec_dead.json"
    spec_path.write_text(json.dumps({"garbage_on_list": True, "tools": [{"name": "x"}]}), encoding="utf-8")
    _write_mcp_json(workspace, "srv", spec_path)
    manager = McpManager(workspace)
    try:
        with pytest.raises(McpError):
            manager.tool_specs()
        health = {row["name"]: row["state"] for row in manager.health()}
        assert health["srv"] == "dead"
        # A dead server is negatively cached: the next call fails immediately.
        started = time.monotonic()
        with pytest.raises(McpError):
            manager.tool_specs()
        assert time.monotonic() - started < 1.0
    finally:
        manager.close()


# --- M5-T6: registry surfaces mcp__ tools when a manager is wired ------------

def test_build_registry_lists_mcp_tools(tmp_path):
    workspace = tmp_path
    spec_path = workspace / "spec_cli.json"
    spec_path.write_text(json.dumps({"tools": [{"name": "search", "description": "search things"}]}), encoding="utf-8")
    _write_mcp_json(workspace, "srv", spec_path)
    manager = McpManager(workspace)
    try:
        registry = build_registry(Editor(workspace), mcp_manager=manager)
    finally:
        manager.close()
    assert any(n.startswith("mcp__srv__") for n in registry.names())
