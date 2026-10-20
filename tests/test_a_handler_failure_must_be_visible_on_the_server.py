"""M8-T301 — handler 里的真 bug，不该在两边都看不见

JSON-RPC 的传输边界是"该停住的地方"——但它以前也是**唯一**看见这个异常的
地方：客户端拿到 "Server error"，服务端**什么都没留**。

于是 handler 里的一个真实 bug（一个拼错的属性、一个空指针）在两边都不可观测：
客户端只看到"服务端出错了"，运维看日志什么也没有。

本门禁钉住：异常在服务端**被记下来**（带 traceback），而客户端拿到的答案
**不变**（不泄漏内部细节）。
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from minicc.agent.rpc import RpcDispatcher, RpcProtocolError


def _dispatcher() -> RpcDispatcher:
    def boom(_params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("handler 里出了事")

    return RpcDispatcher({"boom": boom})


def test_a_handler_failure_is_logged_with_its_traceback(caplog: Any) -> None:
    """The server side has to see it."""
    dispatcher = _dispatcher()
    with caplog.at_level(logging.ERROR, logger="minicc.rpc"):
        response = dispatcher.dispatch({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "boom",
            "params": {},
        })

    assert isinstance(response, dict)
    assert response.get("error", {}).get("code") == -32000
    records = [record for record in caplog.records if record.name == "minicc.rpc"]
    assert records, "the handler's exception was not logged anywhere"
    assert any(record.exc_info for record in records), (
        "the log line carries no traceback"
    )


def test_the_client_answer_does_not_leak_the_traceback(caplog: Any) -> None:
    """The control: the answer is still the stable one.

    The client's answer carries the exception's type and message - that is
    this face's long-standing contract and it is useful to the caller.
    What must not leave the server is the **traceback**: it is logged
    here, and the answer stays as it was.
    """
    dispatcher = _dispatcher()
    with caplog.at_level(logging.ERROR, logger="minicc.rpc"):
        response = dispatcher.dispatch({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "boom",
            "params": {},
        })

    assert isinstance(response, dict)
    error = response.get("error", {})
    assert error.get("code") == -32000
    assert error.get("message") == "Server error"
    assert "Traceback" not in str(error), (
        "the traceback was handed to the client"
    )


def test_a_protocol_error_is_still_a_protocol_error() -> None:
    """The control: the ordinary path is unchanged."""
    dispatcher = RpcDispatcher({"boom": lambda _params: {"ok": True}})
    response = dispatcher.dispatch({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "missing",
        "params": {},
    })
    assert isinstance(response, dict)
    assert response.get("error", {}).get("code") == -32601
