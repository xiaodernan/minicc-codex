"""M8-T530 (second site): a redirect hop must give the socket it borrowed back.

``McpHttpClient._post`` reads the ``3xx`` as *data* (M8-T325 - the redirect must
not be followed by urllib's handler, because that handler copies the
``Authorization`` header to the new origin), and an ``HTTPError`` **is** the
response: it holds the connection.  Only the status and the headers were read
from it, and then it was dropped - once per hop, and once again on the final
non-3xx error.  The sockets went to the garbage collector, which closes them
whenever it feels like it, under whichever test is executing at that moment.

This is the shape the fence cannot see coming: with ``-W error`` a leaked handle
is not a warning at the leak site, it is a red on **someone else's** test.  The
chain was measured here with a scripted opener and real OS handles: three hops
then a success released **three** ``ResourceWarning``s, two hops then a ``500``
released three, and a plain ``404`` on the first try released one - all of them
raised at collection time, none of them at the leak site.

This door pins the release, per exit of the error branch:

* a followed hop closes the error it followed;
* a refused hop (non-3xx) closes the error it turned into an ``McpError``;
* an error that carries **no** connection at all (``fp=None`` - the shape
  ``urllib.error.HTTPError`` allows and the redirect-home gate builds) is
  still followed and still reported, and does not become a ``KeyError`` out of
  the stdlib's own half-initialized wrapper;
* the success path still closes through its ``with`` - the control that proves
  the two assertions above are about the error branch, not about the client
  never closing anything.

No network, no child process: the opener is replaced with a script, so the only
thing under test is whether the code closes what it caught.
"""

from __future__ import annotations

import io
import json
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from minicc import mcp as mcp_mod
from minicc.mcp import McpError, McpHttpClient, McpServerConfig


class _Response:
    """The success-path shape: readable, headered, and closeable by ``with``."""

    def __init__(self, body: bytes, headers: dict[str, str] | None = None, status: int = 200) -> None:
        self._body = body
        self.status = status
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value
        self.closed = False

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_exc: Any) -> bool:
        self.close()
        return False


class _Opener:
    """A scripted opener: each call pops one outcome, or answers a plain 200 result.

    The handshake is not what this gate is about - constructing the client sends
    ``initialize`` and ``notifications/initialized`` - so the script only carries
    the outcomes a test names, and everything else gets a well-formed empty
    result.  An outcome that is an exception is raised, which is how a 3xx
    arrives (the opener has no redirect handler, by M8-T325).
    """

    def __init__(self) -> None:
        self.script: list[Any] = []
        self.urls: list[str] = []

    def open(self, request: Any, timeout: Any = None) -> Any:
        self.urls.append(request.full_url)
        outcome = self.script.pop(0) if self.script else _Response(
            json.dumps({"jsonrpc": "2.0", "id": 0, "result": {}}).encode()
        )
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _error(
    url: str, code: int, headers: dict[str, str], fp: io.BytesIO | None
) -> Exception:
    import urllib.error

    message = Message()
    for key, value in headers.items():
        message[key] = value
    return urllib.error.HTTPError(url, code, f"status {code}", message, fp)


def _client(monkeypatch: pytest.MonkeyPatch) -> tuple[McpHttpClient, _Opener]:
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_MCP", "1")
    opener = _Opener()
    monkeypatch.setattr(mcp_mod, "_MCP_OPENER", opener)
    config = McpServerConfig(name="srv", url="http://127.0.0.1:2/mcp")
    client = McpHttpClient(config, Path.cwd())
    return client, opener


def _tools(body: dict[str, Any]) -> _Response:
    return _Response(json.dumps({"jsonrpc": "2.0", "id": 1, "result": body}).encode())


def test_a_followed_hop_closes_the_error_it_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    hop_one_fp = io.BytesIO(b"")
    client, opener = _client(monkeypatch)
    opener.script = [
        _error("http://127.0.0.1:2/mcp", 302, {"Location": "http://127.0.0.1:3/next"}, hop_one_fp),
        _tools({"tools": []}),
    ]
    assert client.list_tools() == []
    assert opener.urls[-2:] == ["http://127.0.0.1:2/mcp", "http://127.0.0.1:3/next"], (
        "the hop the assertion is about never happened: " + ", ".join(opener.urls)
    )
    assert hop_one_fp.closed, (
        "the 3xx was read for its Location and then dropped with its connection: "
        "one live socket per hop, released only when the collector chooses"
    )


def test_a_refused_hop_closes_the_error_it_turned_into_an_mcperror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final_fp = io.BytesIO(b"")
    client, opener = _client(monkeypatch)
    opener.script = [
        _error("http://127.0.0.1:2/mcp", 500, {}, final_fp),
    ]
    with pytest.raises(McpError, match="500"):
        client.list_tools()
    assert final_fp.closed, (
        "the non-3xx error became an McpError and its connection stayed open behind it"
    )


def test_the_success_path_still_closes_through_its_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Control: the assertions above are about the error branch, not the client."""
    ok = _tools({"tools": [{"name": "echo"}]})
    client, opener = _client(monkeypatch)
    opener.script = [ok]
    assert client.list_tools() == [{"name": "echo"}]
    assert ok.closed, "the with-block stopped being the closer"


def test_an_error_with_no_connection_has_nothing_to_give_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``fp=None`` is a shape ``HTTPError`` accepts, and ``close()`` walks it.

    The over-correction guard for the release above: a hop that carries no
    connection must still be followed and still answer.  The stdlib builds that
    error *without* initializing its file-wrapper base classes - so ``close()``
    on it raises ``KeyError: 'file'``, not an ``AttributeError``.  Both spellings
    are caught here and turned into this assertion, because letting one escape
    takes the session down instead of reporting one red: pytest formats the
    failure by walking the ``HTTPError`` in the exception chain, and that walk
    hits the same missing ``'file'`` key (``INTERNALERROR``).
    """
    client, opener = _client(monkeypatch)
    opener.script = [
        _error("http://127.0.0.1:2/mcp", 302, {"Location": "http://127.0.0.1:3/next"}, None),
        _tools({"tools": [{"name": "echo"}]}),
    ]
    try:
        tools = client.list_tools()
    except (AttributeError, KeyError) as exc:
        tools = f"RAISED {type(exc).__name__}: {exc}"
    assert tools == [{"name": "echo"}], (
        "a hop with no connection was billed one: " + str(tools)
    )
