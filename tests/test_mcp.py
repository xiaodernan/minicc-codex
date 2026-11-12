"""M8-T819: minicc/mcp.py - MCP client tests.

Tests for pure functions and module-level constants:
- registry_safe: fold unsafe registry characters into '_'
- mcp_absent_status: status when no MCP manager exists
- _client_info: minicc identity as MCP client
- _initialize_params: MCP initialize handshake params
- _jsonrpc_request / _jsonrpc_notification: JSON-RPC envelopes
- _origin: origin extraction from URL
- McpServerConfig: config parsing, transport property
- load_mcp_config: config loading from .minicc/mcp.json
"""

from __future__ import annotations

import json

from pathlib import Path

import pytest

from minicc.mcp import (
    MCP_CONFIG_NAME,
    McpServerConfig,
    _client_info,
    _initialize_params,
    _jsonrpc_notification,
    _jsonrpc_request,
    _origin,
    mcp_absent_status,
    load_mcp_config,
    registry_safe,
)


# ============================================================================
# registry_safe
# ============================================================================

def test_registry_safe_simple() -> None:
    assert registry_safe("read_file") == "read_file"


def test_registry_safe_special_chars() -> None:
    result = registry_safe("tool-name with!spaces")
    assert " " not in result
    assert "!" not in result


def test_registry_safe_hyphen_preserved() -> None:
    assert registry_safe("tool-name") == "tool-name"


def test_registry_safe_idempotent() -> None:
    once = registry_safe("a b!c")
    twice = registry_safe(once)
    assert once == twice


# ============================================================================
# mcp_absent_status
# ============================================================================

def test_mcp_absent_status() -> None:
    result = mcp_absent_status("manager failed")
    assert result == {"configured": 0, "error": "manager failed"}


# ============================================================================
# _client_info
# ============================================================================

def test_client_info() -> None:
    result = _client_info()
    assert result["name"] == "minicc"
    assert "version" in result
    assert isinstance(result["version"], str)
    assert len(result["version"]) > 0


# ============================================================================
# _initialize_params
# ============================================================================

def test_initialize_params() -> None:
    result = _initialize_params("2024-11-05")
    assert result["protocolVersion"] == "2024-11-05"
    assert result["capabilities"] == {}
    assert "clientInfo" in result
    assert result["clientInfo"]["name"] == "minicc"


# ============================================================================
# _jsonrpc_request and _jsonrpc_notification
# ============================================================================

def test_jsonrpc_request() -> None:
    result = _jsonrpc_request(42, "tools/list", {})
    assert result["jsonrpc"] == "2.0"
    assert result["id"] == 42
    assert result["method"] == "tools/list"
    assert result["params"] == {}


def test_jsonrpc_notification() -> None:
    result = _jsonrpc_notification("notifications/initialized", {})
    assert result["jsonrpc"] == "2.0"
    assert result["method"] == "notifications/initialized"
    assert result["params"] == {}
    assert "id" not in result


# ============================================================================
# _origin
# ============================================================================

def test_origin() -> None:
    assert _origin("https://example.com/path?q=1") == "https//example.com"


def test_origin_with_port() -> None:
    assert _origin("http://localhost:8080/path") == "http//localhost:8080"


def test_origin_case_normalized() -> None:
    assert _origin("HTTPS://EXAMPLE.COM/path") == "https//example.com"


# ============================================================================
# McpServerConfig
# ============================================================================

def test_mcp_server_config_defaults() -> None:
    cfg = McpServerConfig(name="test")
    assert cfg.name == "test"
    assert cfg.command == ""
    assert cfg.args == ()
    assert cfg.env == {}
    assert cfg.read_only is False
    assert cfg.url == ""
    assert cfg.headers == {}


def test_mcp_server_config_transport_stdio() -> None:
    cfg = McpServerConfig(name="test", command="node server.js")
    assert cfg.transport == "stdio"


def test_mcp_server_config_transport_http() -> None:
    cfg = McpServerConfig(name="test", url="https://example.com/mcp")
    assert cfg.transport == "http"


# ============================================================================
# load_mcp_config
# ============================================================================

def test_load_mcp_config_no_file(tmp_path: Path) -> None:
    result = load_mcp_config(tmp_path)
    assert result == []


def test_load_mcp_config_valid(tmp_path: Path) -> None:
    mcp_dir = tmp_path / ".minicc"
    mcp_dir.mkdir()
    config_file = mcp_dir / MCP_CONFIG_NAME
    config_file.write_text(json.dumps({
        "servers": {
            "test-server": {"command": "python server.py"}
        }
    }), encoding="utf-8")
    result = load_mcp_config(tmp_path)
    assert len(result) == 1
    assert result[0].name == "test-server"


def test_load_mcp_config_invalid_json(tmp_path: Path) -> None:
    mcp_dir = tmp_path / ".minicc"
    mcp_dir.mkdir()
    config_file = mcp_dir / MCP_CONFIG_NAME
    config_file.write_text("not json at all", encoding="utf-8")
    with pytest.raises(Exception):
        load_mcp_config(tmp_path)


def test_load_mcp_config_bom_prefixed(tmp_path: Path) -> None:
    mcp_dir = tmp_path / ".minicc"
    mcp_dir.mkdir()
    config_file = mcp_dir / MCP_CONFIG_NAME
    config_file.write_bytes(b'\xef\xbb\xbf' + json.dumps({
        "servers": {
            "bom-server": {"command": "node server.js"}
        }
    }).encode("utf-8"))
    result = load_mcp_config(tmp_path)
    assert len(result) == 1
    assert result[0].name == "bom-server"


def test_load_mcp_config_missing_command_and_url(tmp_path: Path) -> None:
    mcp_dir = tmp_path / ".minicc"
    mcp_dir.mkdir()
    config_file = mcp_dir / MCP_CONFIG_NAME
    config_file.write_text(json.dumps({
        "servers": {
            "empty-server": {}
        }
    }), encoding="utf-8")
    with pytest.raises(Exception):
        load_mcp_config(tmp_path)


def test_load_mcp_config_non_dict_server_entry(tmp_path: Path) -> None:
    mcp_dir = tmp_path / ".minicc"
    mcp_dir.mkdir()
    config_file = mcp_dir / MCP_CONFIG_NAME
    config_file.write_text(json.dumps({
        "servers": {
            "bad-server": "just a string"
        }
    }), encoding="utf-8")
    with pytest.raises(Exception):
        load_mcp_config(tmp_path)
