"""M8-T483 — JSON-RPC 协议词汇表两个家：版本串与方法不存在判词各写两份

这个仓库里有两个 JSON-RPC 2.0 的说话者：``agent/rpc.py`` 是本地工作台的
服务端，``mcp.py`` 是面向 MCP server 的 stdio/HTTP 客户端。版本串和标准错
误码属于协议，不属于任何一个说话者——一份漂移了，就是两个说话者对
"2.0" 不再有一致的理解；方法不存在的判词拼两遍，就是服务端与客户端对
「未知方法长什么样」各说各话。

重构前：``JSONRPC_VERSION = "2.0"``（rpc.py）与 ``_JSONRPC_VERSION =
"2.0"``（mcp.py）各一份，``Method not found: `` 的判词在两个文件里各拼
一次。MCP 客户端位于 agent 栈下层、不能 import agent，所以家安在两者之下
的 ``minicc/jsonrpc.py``。

顺带修好一道本来就已经红着的门：``test_version_vocabulary.py`` 的普查表
从没登记过 mcp.py 的 ``_JSONRPC_VERSION``——第二个家立下之后，老门禁没有
学会认新形状（T473/T475/T480 的同款形状）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/jsonrpc.py"
VERSION = "2.0"
NOT_FOUND_PREFIX = "Method not found: "


def test_the_home_owns_the_version_and_the_error_code() -> None:
    """jsonrpc.py owns the protocol version and the method-not-found code."""
    from minicc.jsonrpc import ERROR_METHOD_NOT_FOUND, JSONRPC_VERSION

    assert JSONRPC_VERSION == VERSION
    assert ERROR_METHOD_NOT_FOUND == -32601


def test_the_home_builds_the_method_not_found_sentence() -> None:
    """One sentence builder, shared by server and client."""
    from minicc.jsonrpc import method_not_found_message

    assert method_not_found_message("threads/list") == "Method not found: threads/list"


def test_the_home_answers_whether_a_payload_is_2_0() -> None:
    """The version's reader lives with the version."""
    from minicc.jsonrpc import is_jsonrpc_2

    assert is_jsonrpc_2({"jsonrpc": "2.0", "id": 1}) is True
    assert is_jsonrpc_2({"jsonrpc": "1.0", "id": 1}) is False
    assert is_jsonrpc_2({}) is False
    assert is_jsonrpc_2("not-a-payload") is False


def test_no_other_module_spells_the_vocabulary_inline() -> None:
    """No module spells the version or the not-found sentence outside the home."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value == VERSION or NOT_FOUND_PREFIX in node.value:
                    offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 2 and all(item.startswith(HOME) for item in offenders), (
        "the JSON-RPC vocabulary is spelled inline outside its one home: "
        + ", ".join(offenders)
    )


def test_both_speakers_consume_the_same_home_objects() -> None:
    """Both speakers ask the home, not a copy of it."""
    from minicc import jsonrpc, mcp
    from minicc.agent import rpc

    assert rpc.JSONRPC_VERSION is jsonrpc.JSONRPC_VERSION
    assert mcp.JSONRPC_VERSION is jsonrpc.JSONRPC_VERSION
    assert rpc.method_not_found_message is jsonrpc.method_not_found_message
    assert mcp.method_not_found_message is jsonrpc.method_not_found_message
    assert rpc.ERROR_METHOD_NOT_FOUND == jsonrpc.ERROR_METHOD_NOT_FOUND
    assert mcp.ERROR_METHOD_NOT_FOUND == jsonrpc.ERROR_METHOD_NOT_FOUND


def test_the_workbench_server_emits_the_home_sentence() -> None:
    """An unknown method on the workbench server is answered with the home's words."""
    from minicc.agent.rpc import RpcDispatcher
    from minicc.jsonrpc import ERROR_METHOD_NOT_FOUND, method_not_found_message

    dispatcher = RpcDispatcher()
    response = dispatcher.dispatch({"jsonrpc": "2.0", "id": 7, "method": "no/such"})
    assert response["error"]["code"] == ERROR_METHOD_NOT_FOUND
    assert response["error"]["message"] == method_not_found_message("no/such")


def test_the_mcp_client_answers_with_the_home_sentence() -> None:
    """An unknown method on the MCP client is answered with the home's words."""
    from minicc import mcp
    from minicc.jsonrpc import ERROR_METHOD_NOT_FOUND, method_not_found_message

    captured: list[tuple[object, dict]] = []
    client = mcp.McpStdioClient.__new__(mcp.McpStdioClient)
    client._respond = lambda msg_id, *, result=None, error=None: captured.append((msg_id, error))
    client._handle_server_message({"method": "no/such", "id": 9})
    assert captured == [
        (9, {"code": ERROR_METHOD_NOT_FOUND, "message": method_not_found_message("no/such")})
    ]


def test_the_workbench_server_still_refuses_a_foreign_version() -> None:
    """The version check moved into the home; the refusal is unchanged."""
    from minicc.agent.rpc import RpcDispatcher, RpcProtocolError, parse_request

    with pytest.raises(RpcProtocolError) as excinfo:
        parse_request({"jsonrpc": "1.0", "id": 1, "method": "initialize"})
    assert excinfo.value.code == -32600
    assert excinfo.value.message == "jsonrpc must be '2.0'"

    response = RpcDispatcher().dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert response["result"]["serverInfo"]["name"] == "minicc"
