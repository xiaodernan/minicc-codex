"""M8-T140: MCP server config validation must fail at startup, not runtime.

Every malformed mcp.json shape that used to crash mid-task (when the manager
first tries to spawn/connect) is now refused by load_mcp_config with a clear
McpError. The tests below prove each refusal happens before any child process
or HTTP connection is attempted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minicc.mcp import McpError, load_mcp_config


def _write_config(workspace: Path, content: str) -> None:
    """Helper: write raw JSON string to workspace/.minicc/mcp.json."""
    cfg_dir = workspace / ".minicc"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "mcp.json").write_text(content, encoding="utf-8")


# --- Section 1: Top-level structure refusals ---------------------------------

def test_mcp_config_rejects_non_dict_top_level(tmp_path: Path) -> None:
    """A bare array or string at the top level is not a valid config."""
    _write_config(tmp_path, '["not", "a", "config"]')
    with pytest.raises(McpError, match="servers"):
        load_mcp_config(tmp_path)


def test_mcp_config_rejects_server_entry_that_is_not_dict(tmp_path: Path) -> None:
    """Each server entry under 'servers' must be an object, not a string/array."""
    _write_config(tmp_path, '{"servers": {"bad": "just a string"}}')
    with pytest.raises(McpError, match="配置必须是对象"):
        load_mcp_config(tmp_path)


# --- Section 2: Missing transport refusals -----------------------------------

def test_mcp_config_rejects_server_with_neither_command_nor_url(tmp_path: Path) -> None:
    """A server entry must declare either command (stdio) or url (HTTP)."""
    _write_config(tmp_path, '{"servers": {"empty": {}}}')
    with pytest.raises(McpError, match="缺少 command 或 url"):
        load_mcp_config(tmp_path)


# --- Section 3: URL validation refusals --------------------------------------

def test_mcp_config_rejects_non_http_url(tmp_path: Path) -> None:
    """URL must start with http:// or https:// — no ftp/file/ws schemes."""
    _write_config(tmp_path, '{"servers": {"x": {"url": "ws://localhost/mcp"}}}')
    with pytest.raises(McpError, match="http/https"):
        load_mcp_config(tmp_path)


def test_mcp_config_rejects_loopback_url_without_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Loopback/private URLs are blocked unless MINICC_ALLOW_PRIVATE_MCP is set."""
    monkeypatch.delenv("MINICC_ALLOW_PRIVATE_MCP", raising=False)
    _write_config(tmp_path, '{"servers": {"local": {"url": "http://127.0.0.1:9999/mcp"}}}')
    with pytest.raises(McpError, match="SSRF"):
        load_mcp_config(tmp_path)


# --- Section 4: Type validation for arrays/dicts -----------------------------

def test_mcp_config_rejects_non_list_args(tmp_path: Path) -> None:
    """The args field must be a list of strings, not a single string or dict."""
    _write_config(tmp_path, '{"servers": {"srv": {"command": "node", "args": "bad"}}}')
    with pytest.raises(McpError, match="args 非法"):
        load_mcp_config(tmp_path)


def test_mcp_config_rejects_non_string_in_args_list(tmp_path: Path) -> None:
    """Each element in args must be a string — numbers/objects are rejected."""
    _write_config(tmp_path, '{"servers": {"srv": {"command": "node", "args": [123]}}}')
    with pytest.raises(McpError, match="args 非法"):
        load_mcp_config(tmp_path)


def test_mcp_config_rejects_non_dict_env(tmp_path: Path) -> None:
    """The env field must be a dict mapping strings to strings."""
    _write_config(tmp_path, '{"servers": {"srv": {"command": "node", "env": ["BAD"]}}}')
    with pytest.raises(McpError, match="env 非法"):
        load_mcp_config(tmp_path)


def test_mcp_config_rejects_non_string_env_value(tmp_path: Path) -> None:
    """Env values must be strings — numbers/booleans are rejected."""
    _write_config(tmp_path, '{"servers": {"srv": {"command": "node", "env": {"KEY": 123}}}}')
    with pytest.raises(McpError, match="env 非法"):
        load_mcp_config(tmp_path)


def test_mcp_config_rejects_non_dict_headers(tmp_path: Path) -> None:
    """The headers field must be a dict mapping strings to strings."""
    _write_config(tmp_path, '{"servers": {"srv": {"command": "node", "headers": "Bearer token"}}}')
    with pytest.raises(McpError, match="headers 非法"):
        load_mcp_config(tmp_path)


# --- Section 5: Valid configs pass -------------------------------------------

def test_mcp_config_accepts_valid_stdio_server(tmp_path: Path) -> None:
    """A well-formed stdio server loads without error."""
    _write_config(
        tmp_path,
        json.dumps({
            "servers": {
                "docs": {
                    "command": "node",
                    "args": ["server.js"],
                    "env": {"NODE_ENV": "production"},
                    "read_only": True,
                }
            }
        }),
    )
    configs = load_mcp_config(tmp_path)
    assert len(configs) == 1
    assert configs[0].name == "docs"
    assert configs[0].transport == "stdio"
    assert configs[0].read_only is True


def test_mcp_config_accepts_valid_http_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A well-formed HTTP server loads without error (DNS-resolvable host)."""
    # Use loopback to avoid DNS resolution failure in offline environments.
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_MCP", "1")
    _write_config(
        tmp_path,
        json.dumps({
            "servers": {
                "local": {
                    "url": "http://127.0.0.1:3000/mcp",
                    "headers": {"Authorization": "Bearer secret"},
                }
            }
        }),
    )
    configs = load_mcp_config(tmp_path)
    assert len(configs) == 1
    assert configs[0].name == "local"
    assert configs[0].transport == "http"
    assert configs[0].headers["Authorization"] == "Bearer secret"
