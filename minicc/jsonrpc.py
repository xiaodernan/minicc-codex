"""The JSON-RPC 2.0 vocabulary shared by the workbench server and the MCP client.

Two speakers in this repo talk JSON-RPC 2.0: ``agent/rpc.py`` serves the local
workbench and ``mcp.py`` is a stdio/HTTP client for MCP servers.  The version
string and the standard error codes belong to the protocol, not to either
speaker: a version one copy drifts on is two speakers that no longer agree on
what "2.0" means, and a method-not-found sentence spelled twice is a server
and a client that disagree about what an unknown method looks like.

The MCP client sits below the agent stack and may not import it, so the
vocabulary lives here, below both speakers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: The one JSON-RPC protocol version both speakers publish and accept.
JSONRPC_VERSION = "2.0"

#: The JSON-RPC 2.0 standard error code for "no handler for this method".
ERROR_METHOD_NOT_FOUND = -32601


def is_jsonrpc_2(payload: Any) -> bool:
    """Whether one wire object declares itself a JSON-RPC 2.0 message."""
    return isinstance(payload, Mapping) and payload.get("jsonrpc") == JSONRPC_VERSION


def method_not_found_message(method: str) -> str:
    """The one sentence both speakers use for an unknown method."""
    return f"Method not found: {method}"


__all__ = [
    "ERROR_METHOD_NOT_FOUND",
    "JSONRPC_VERSION",
    "is_jsonrpc_2",
    "method_not_found_message",
]
