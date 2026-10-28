"""M8-T365 — 网络闸门必须看得见远程 MCP 工具

MCP 有两种传输 ✓：**stdio**（本地进程 ✓）与 **http**（远程服务器 ✓）。http 那次
调用**本身就跨网络** ✓——请求从这台机器发出去 ✓。

而桥接注册 MCP 工具时**没有声明任何 capability** ✓（`ToolSpec(..., (), ...)` ✓）
→ `is_network_tool` 看不见它 ✓ → 网络闸门**根本没问** ✓ → 一个**没有联网授权**的
任务 ✓，照样能把请求发到远程 MCP 服务器 ✓（而任务卡上还写着"联网不可用" ✓ ✗）。

被钉住的契约 ✓：**够到网络需要另一份授权** ✓（Web 的任务契约 ✓ + CLI 的
`--allow-network` ✓ + M8-T353 ✓）——远程 MCP 工具也是"够到网络" ✓，它只是没说
✓。

本门钉住：远程（http）服务器的工具**是网络工具** ✓（没有联网授权时被网络闸门拒
掉 ✓）；控制组——本地（stdio）服务器的工具**不是**网络工具 ✓（行为不变 ✓）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from minicc.audit import authorize_tool, is_network_tool
from minicc.mcp import McpManager


class _FakeClient:
    """A server that answers the discovery call and nothing else."""

    dead = False

    def tools_listing(self) -> tuple[list[dict[str, Any]], list[str]]:
        # The read M8-T530 put behind the bridge: the items, and what the reader
        # had to leave out.  This gate's server answers cleanly, so nothing was.
        return [{
            "name": "echo",
            "description": "echo back",
            "inputSchema": {"type": "object", "properties": {}},
        }], []

    def list_tools(self) -> list[dict[str, Any]]:
        return self.tools_listing()[0]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        return "{}"


def _write(tmp_path: Path, servers: dict[str, Any]) -> McpManager:
    config_dir = tmp_path / ".minicc"
    config_dir.mkdir()
    (config_dir / "mcp.json").write_text(
        json.dumps({"servers": servers}), encoding="utf-8"
    )
    manager = McpManager(tmp_path)
    # The discovery seam is replaced: this gate is about what the bridge
    # **declares**, not about speaking the MCP protocol over a socket.
    manager._client = lambda config: _FakeClient()  # type: ignore[method-assign]
    return manager


def test_a_remote_mcp_tool_is_a_network_tool(tmp_path: Path, monkeypatch) -> None:
    # The shipped override the suite already uses to point an MCP server at
    # a loopback address (the SSRF guard is not what this gate is about).
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_MCP", "1")
    manager = _write(tmp_path, {
        "remote": {"url": "http://127.0.0.1:9/mcp", "read_only": True},
    })
    try:
        specs = manager.tool_specs()
    finally:
        manager.close()

    assert len(specs) == 1, specs
    spec = specs[0]
    assert spec.name.startswith("mcp__remote__"), spec.name
    assert is_network_tool(spec.name, spec.capabilities), spec.capabilities

    # And the gate asks: without the network grant the call is refused.
    decision = authorize_tool(
        spec.name,
        spec.risk,
        {},
        allow_changes=False,
        allow_network=False,
        permission_mode="default",
        capabilities=spec.capabilities,
    )
    assert decision.allowed is False, decision
    assert decision.authorization == "missing_task_network", decision


def test_a_local_stdio_mcp_tool_is_not_a_network_tool(tmp_path: Path) -> None:
    """The control: a local server is the operator's own process."""
    manager = _write(tmp_path, {
        "local": {"command": "echo", "args": ["hi"], "read_only": True},
    })
    try:
        specs = manager.tool_specs()
    finally:
        manager.close()

    assert len(specs) == 1, specs
    spec = specs[0]
    assert not is_network_tool(spec.name, spec.capabilities), spec.capabilities
