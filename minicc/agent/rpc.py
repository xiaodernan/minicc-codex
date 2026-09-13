"""Small JSON-RPC 2.0 transport used by the local agent workbench.

This module intentionally implements the public protocol boundary only. It does
not copy a client implementation or own agent state; callers provide handlers
that delegate to the existing task/thread runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

JSONRPC_VERSION = "2.0"

_MISSING = object()


class RpcProtocolError(ValueError):
    """A JSON-RPC request or parameter error."""

    def __init__(self, code: int, message: str, data: Any = _MISSING) -> None:
        super().__init__(message)
        self.code = int(code)
        self.message = str(message)
        self.data = data


@dataclass(frozen=True)
class RpcRequest:
    """Validated JSON-RPC request; ``has_id`` distinguishes notifications."""

    request_id: Any
    has_id: bool
    method: str
    params: dict[str, Any]


def _response_error(request_id: Any, error: RpcProtocolError) -> dict[str, Any]:
    body: dict[str, Any] = {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": error.code, "message": error.message},
    }
    if error.data is not _MISSING:
        body["error"]["data"] = error.data
    return body


def _response_result(request_id: Any, result: Mapping[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": dict(result)}


def parse_request(payload: Any) -> RpcRequest:
    """Validate one JSON-RPC request without executing application code."""

    if not isinstance(payload, dict):
        raise RpcProtocolError(-32600, "Invalid Request")
    if payload.get("jsonrpc") != JSONRPC_VERSION:
        raise RpcProtocolError(-32600, "jsonrpc must be '2.0'")
    method = payload.get("method")
    if not isinstance(method, str) or not method.strip():
        raise RpcProtocolError(-32600, "method must be a non-empty string")
    request_id = payload.get("id")
    has_id = "id" in payload
    if has_id and (isinstance(request_id, bool) or not isinstance(request_id, (str, int, type(None)))):
        raise RpcProtocolError(-32600, "id must be a string, integer, or null")
    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise RpcProtocolError(-32602, "params must be an object")
    return RpcRequest(request_id, has_id, method.strip(), dict(params))


RpcHandler = Callable[[dict[str, Any]], Mapping[str, Any]]


class RpcDispatcher:
    """Dispatch JSON-RPC calls to application handlers.

    Handlers return JSON objects and are deliberately injected so the transport
    layer cannot bypass the existing permission, workspace, or task managers.
    """

    def __init__(self, handlers: Mapping[str, RpcHandler] | None = None, *, server_name: str = "minicc") -> None:
        self.handlers = dict(handlers or {})
        self.server_name = str(server_name or "minicc")

    def dispatch(self, payload: Any) -> dict[str, Any] | list[dict[str, Any]] | None:
        if isinstance(payload, list):
            if not payload:
                return _response_error(None, RpcProtocolError(-32600, "Invalid Request"))
            responses = [self._dispatch_one(item) for item in payload]
            visible = [item for item in responses if item is not None]
            return visible or None
        return self._dispatch_one(payload)

    def _dispatch_one(self, payload: Any) -> dict[str, Any] | None:
        try:
            request = parse_request(payload)
        except RpcProtocolError as exc:
            return _response_error(None, exc)
        try:
            if request.method == "initialize":
                result: Mapping[str, Any] = {
                    "protocolVersion": "minicc.rpc.v1",
                    "serverInfo": {"name": self.server_name, "version": "0.1.0"},
                    "capabilities": {
                        "threads": True,
                        "turns": True,
                        "replayableEvents": True,
                        "cancellation": True,
                    },
                }
            else:
                handler = self.handlers.get(request.method)
                if handler is None:
                    raise RpcProtocolError(-32601, f"Method not found: {request.method}")
                result = handler(request.params)
                if not isinstance(result, Mapping):
                    raise RpcProtocolError(-32000, "RPC handler must return an object")
        except RpcProtocolError as exc:
            return None if not request.has_id else _response_error(request.request_id, exc)
        except KeyError as exc:
            error = RpcProtocolError(-32004, "Not found", str(exc))
            return None if not request.has_id else _response_error(request.request_id, error)
        except ValueError as exc:
            error = RpcProtocolError(-32602, str(exc))
            return None if not request.has_id else _response_error(request.request_id, error)
        except Exception as exc:  # noqa: BLE001 - stable transport boundary
            error = RpcProtocolError(-32000, "Server error", f"{type(exc).__name__}: {exc}")
            return None if not request.has_id else _response_error(request.request_id, error)
        return None if not request.has_id else _response_result(request.request_id, result)


__all__ = [
    "JSONRPC_VERSION",
    "RpcDispatcher",
    "RpcProtocolError",
    "RpcRequest",
    "parse_request",
]
