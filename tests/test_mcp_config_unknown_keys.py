"""M8-T145: MCP server config must report unrecognized/unused keys, not silently ignore them.

Just like config.json reports typos (M8-T141), mcp.json should warn when a server entry
contains keys beyond the recognized set: command, url, args, env, headers, read_only.

This prevents users from silently misspelling field names or using deprecated options
that no longer have any effect.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from minicc.mcp import load_mcp_config


def _write_mcp(workspace: Path, payload: object) -> None:
    """Write raw payload to .minicc/mcp.json without validation."""
    (workspace / ".minicc").mkdir(parents=True, exist_ok=True)
    (workspace / ".minicc" / "mcp.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_typo_in_server_entry_is_reported(tmp_path: Path, caplog: logging.Logger) -> None:
    """A typo like 'comand' instead of 'command' is reported with suggestion."""
    _write_mcp(tmp_path, {
        "servers": {
            "my-server": {
                "command": "python",  # Valid command
                "comand": "python",  # Typo: extra field
                "args": ["-m", "mcp_server"],
            }
        }
    })
    with caplog.at_level(logging.WARNING):
        configs = load_mcp_config(tmp_path)
    
    # Should still load (unknown keys don't block loading)
    assert len(configs) == 1
    
    # But should warn about the unknown key
    assert len(caplog.records) >= 1
    messages = [r.message for r in caplog.records]
    warning_found = any("my-server" in msg and "comand" in msg for msg in messages)
    assert warning_found, f"Expected warning about 'comand' in server 'my-server', got: {messages}"


def test_close_match_suggests_correct_key(tmp_path: Path, caplog: logging.Logger) -> None:
    """Suggestions use difflib.get_close_matches to propose the right field name."""
    _write_mcp(tmp_path, {
        "servers": {
            "test": {
                "command": "echo",  # Valid command
                "commnd": "echo",  # Close to 'command' - typo
            }
        }
    })
    with caplog.at_level(logging.WARNING):
        load_mcp_config(tmp_path)
    
    messages = [r.message for r in caplog.records]
    # Should suggest 'command' as a close match
    suggestion_found = any("command" in msg for msg in messages)
    assert suggestion_found, f"Expected suggestion for 'command', got: {messages}"


def test_multiple_unknown_keys_all_reported(tmp_path: Path, caplog: logging.Logger) -> None:
    """Multiple unknown keys in one server entry are all reported."""
    _write_mcp(tmp_path, {
        "servers": {
            "srv": {
                "command": "node",  # Valid command
                "typo1": "value1",
                "typo2": "value2",
                "deprecated_option": True,
            }
        }
    })
    with caplog.at_level(logging.WARNING):
        load_mcp_config(tmp_path)
    
    messages = [r.message for r in caplog.records]
    # All three unknown keys should be mentioned
    assert any("typo1" in msg for msg in messages), f"Missing typo1 warning: {messages}"
    assert any("typo2" in msg for msg in messages), f"Missing typo2 warning: {messages}"
    assert any("deprecated_option" in msg for msg in messages), f"Missing deprecated_option warning: {messages}"


def test_recognized_keys_do_not_trigger_warning(tmp_path: Path, caplog: logging.Logger) -> None:
    """Valid server entries with only recognized keys produce no warnings."""
    _write_mcp(tmp_path, {
        "servers": {
            "valid-server": {
                "command": "python",
                "args": ["-m", "server"],
                "env": {"KEY": "value"},
                "headers": {"X-Custom": "header"},
                "read_only": True,
                "url": "",  # Empty URL means stdio mode
            }
        }
    })
    with caplog.at_level(logging.WARNING):
        configs = load_mcp_config(tmp_path)
    
    assert len(configs) == 1
    # No warnings for valid configuration
    assert len(caplog.records) == 0


def test_http_mode_keys_accepted(tmp_path: Path, caplog: logging.Logger) -> None:
    """HTTP-mode servers with url + headers are valid."""
    _write_mcp(tmp_path, {
        "servers": {
            "http-server": {
                "url": "http://127.0.0.1:8080/mcp",
                "headers": {"Authorization": "Bearer token"},
            }
        }
    })
    import os
    old = os.environ.get("MINICC_ALLOW_PRIVATE_MCP")
    try:
        os.environ["MINICC_ALLOW_PRIVATE_MCP"] = "1"
        with caplog.at_level(logging.WARNING):
            configs = load_mcp_config(tmp_path)
        
        assert len(configs) == 1
        assert len(caplog.records) == 0
    finally:
        if old is None:
            os.environ.pop("MINICC_ALLOW_PRIVATE_MCP", None)
        else:
            os.environ["MINICC_ALLOW_PRIVATE_MCP"] = old


def test_unknown_keys_in_multiple_servers_reported_separately(tmp_path: Path, caplog: logging.Logger) -> None:
    """Unknown keys in different servers are reported with their server names."""
    _write_mcp(tmp_path, {
        "servers": {
            "server-a": {
                "command": "echo",
                "bad-key-a": "value",
            },
            "server-b": {
                "command": "ls",
                "bad-key-b": "value",
            }
        }
    })
    with caplog.at_level(logging.WARNING):
        load_mcp_config(tmp_path)
    
    messages = [r.message for r in caplog.records]
    # Each server's unknown key should be mentioned with its name
    assert any("server-a" in msg and "bad-key-a" in msg for msg in messages)
    assert any("server-b" in msg and "bad-key-b" in msg for msg in messages)


def test_empty_string_values_still_reported_as_unknown(tmp_path: Path, caplog: logging.Logger) -> None:
    """Even empty string values for unknown keys are reported."""
    _write_mcp(tmp_path, {
        "servers": {
            "test": {
                "command": "echo",
                "unknown_field": "",
            }
        }
    })
    with caplog.at_level(logging.WARNING):
        load_mcp_config(tmp_path)
    
    messages = [r.message for r in caplog.records]
    assert any("unknown_field" in msg for msg in messages)


def test_null_values_for_unknown_keys_reported(tmp_path: Path, caplog: logging.Logger) -> None:
    """Null values for unknown keys are still reported as unrecognized."""
    _write_mcp(tmp_path, {
        "servers": {
            "test": {
                "command": "echo",
                "legacy_option": None,
            }
        }
    })
    with caplog.at_level(logging.WARNING):
        load_mcp_config(tmp_path)
    
    messages = [r.message for r in caplog.records]
    assert any("legacy_option" in msg for msg in messages)


def test_boolean_and_numeric_unknown_values_reported(tmp_path: Path, caplog: logging.Logger) -> None:
    """Non-string values (bool/number) for unknown keys are also reported."""
    _write_mcp(tmp_path, {
        "servers": {
            "test": {
                "command": "echo",
                "flag": True,
                "count": 42,
            }
        }
    })
    with caplog.at_level(logging.WARNING):
        load_mcp_config(tmp_path)
    
    messages = [r.message for r in caplog.records]
    assert any("flag" in msg for msg in messages)
    assert any("count" in msg for msg in messages)


def test_root_level_unknown_keys_ignored_when_using_servers_wrapper(tmp_path: Path, caplog: logging.Logger) -> None:
    """When using 'servers' wrapper, root-level unknown keys are ignored (backward compat)."""
    _write_mcp(tmp_path, {
        "servers": {
            "test": {
                "command": "echo",
            }
        },
        "version": 1,  # Root-level metadata, ignored
        "comment": "This is a comment"
    })
    with caplog.at_level(logging.WARNING):
        configs = load_mcp_config(tmp_path)
    
    assert len(configs) == 1
    # Root-level keys outside 'servers' are not validated (backward compatibility)
    assert len(caplog.records) == 0


def test_flat_format_unknown_keys_reported(tmp_path: Path, caplog: logging.Logger) -> None:
    """Flat format (no 'servers' wrapper) also reports unknown keys per server."""
    _write_mcp(tmp_path, {
        "server1": {
            "command": "echo",
            "typo": "value",
        },
        "server2": {
            "url": "http://localhost:3000",
        }
    })
    import os
    old = os.environ.get("MINICC_ALLOW_PRIVATE_MCP")
    try:
        os.environ["MINICC_ALLOW_PRIVATE_MCP"] = "1"
        with caplog.at_level(logging.WARNING):
            configs = load_mcp_config(tmp_path)
        
        assert len(configs) == 2
        messages = [r.message for r in caplog.records]
        assert any("server1" in msg and "typo" in msg for msg in messages)
    finally:
        if old is None:
            os.environ.pop("MINICC_ALLOW_PRIVATE_MCP", None)
        else:
            os.environ["MINICC_ALLOW_PRIVATE_MCP"] = old
