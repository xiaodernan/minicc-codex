"""M8-T151: static serving must stay inside its root for every hostile spelling.

The boundary lives in ``minicc/static_assets.py`` (``asset_response``): the
requested name is joined onto the root, ``resolve()``d (following links), and
refused unless it lands inside the root. ``webserver._serve_static`` feeds it
``unquote(path.lstrip('/'))`` — decode happens *after* the strip, so encoded
dot-dot bytes reach ``asset_response`` only after being turned into real
traversal text there.

Two independently load-bearing halves, each with its own witness arm (record:
第一百五十一批):

- lexical escapes (``..``, interleaved ``./../``, manifest alias pointing up)
  are refused by the containment check itself;
- link escapes (a junction *inside* the root pointing outside) are refused
  because ``resolve()`` follows the link before the check — a purely lexical
  ``normpath`` would serve them, so the junction case is not decorative.

The manifest alias rows come in pairs: the escape row only means something
next to a control row proving the manifest was actually parsed (a malformed
manifest is silently ignored, which would make the escape row green for the
wrong reason).

Windows-first spellings (backslash, drive letter) carry a comment naming what
holds them on POSIX, where they are ordinary names rather than separators.
"""

from __future__ import annotations

import http.client
import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc import webserver
from minicc.static_assets import asset_response

OUTSIDE_MARKER = "OUTSIDE-MARKER-8801"
INSIDE_ETC_MARKER = "INSIDE-ETC-7002"
ALIAS_MARKER = "ALIAS-CONTROL-5503"
JUNCTION_MARKER = "JUNCTION-SECRET-4407"


def _root(tmp_path: Path) -> Path:
    """Static root with a sibling outside file, manifest, and a junction."""
    root = tmp_path / "webroot"
    root.mkdir()
    (root / "index.html").write_text("<html>inside-index</html>", encoding="utf-8")
    (tmp_path / "outside.txt").write_text(OUTSIDE_MARKER, encoding="utf-8")
    # A hostile absolute spelling must be forced root-relative: seed the
    # in-root twin so the row can assert *which* file gets served.
    (root / "etc").mkdir()
    (root / "etc" / "passwd").write_text(INSIDE_ETC_MARKER, encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "alias.js").write_text(f"// {ALIAS_MARKER}\n", encoding="utf-8")
    (root / "asset-manifest.json").write_text(
        json.dumps({
            "/escape.js": "/../outside.txt",
            "/alias.js": "/assets/alias.js",
        }),
        encoding="utf-8",
    )
    return root


def _make_dir_link(link: Path, target: Path) -> bool:
    """Directory junction on Windows, symlink on POSIX (same as M2-T6 helper)."""
    if os.name == "nt":
        try:
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
            return True
        except (OSError, ImportError, AttributeError):
            return False
    try:
        link.symlink_to(target, target_is_directory=True)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# asset_response direct layer: spelling table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        # Windows: backslash is a separator, so this is the same escape as ../.
        # POSIX: an ordinary name that does not exist — refused either way.
        pytest.param("..\\outside.txt", id="windows-backslash"),
        pytest.param("../outside.txt", id="literal-dotdot"),
        pytest.param("./.././outside.txt", id="interleaved-dotdot"),
        pytest.param("....//outside.txt", id="quad-dot-has-no-escape"),
        # Windows: drive-absolute joins as an absolute path and leaves the
        # root; POSIX: ordinary name. Refusal must hold without the path
        # existing, so this does not depend on the host having win.ini.
        pytest.param("C:/Windows/win.ini", id="windows-drive-absolute"),
        pytest.param("escape.js", id="manifest-alias-escape"),
    ],
)
def test_hostile_spellings_are_refused(tmp_path: Path, relative: str) -> None:
    root = _root(tmp_path)
    with pytest.raises(FileNotFoundError):
        asset_response(root, relative)


def test_nul_byte_is_a_refusal_not_a_crash(tmp_path: Path) -> None:
    root = _root(tmp_path)
    # Measured FileNotFoundError on this plane; ValueError is the other
    # documented outcome family (os.stat on the embedded-NUL path). The HTTP
    # layer catches both; the contract is "refused", not a specific type.
    with pytest.raises((OSError, ValueError)):
        asset_response(root, "a\x00b")


def test_absolute_posix_spelling_is_forced_root_relative(tmp_path: Path) -> None:
    """`/etc/passwd` must map to root/etc/passwd, never to the filesystem's."""
    root = _root(tmp_path)
    body, _ = asset_response(root, "/etc/passwd")
    assert INSIDE_ETC_MARKER.encode() in body
    assert OUTSIDE_MARKER.encode() not in body


def test_alias_control_row_proves_the_manifest_was_parsed(tmp_path: Path) -> None:
    """Companion to the alias-escape row: aliases do resolve when in-root.

    A malformed manifest is swallowed silently (``except (OSError, ValueError):
    pass``), which would make ``manifest-alias-escape`` green for the wrong
    reason. This control row pins that the fixture's manifest is live.
    """
    root = _root(tmp_path)
    body, headers = asset_response(root, "alias.js")
    assert ALIAS_MARKER.encode() in body
    # Aliases always revalidate; only content-addressed URLs are immutable.
    assert headers["Cache-Control"] == "no-cache"


def test_dotdot_that_stays_inside_is_allowed(tmp_path: Path) -> None:
    """`assets/../index.html` proves the refusal is containment, not `..`-phobia."""
    root = _root(tmp_path)
    body, _ = asset_response(root, "assets/../index.html")
    assert b"inside-index" in body


def test_junction_escape_is_refused(tmp_path: Path) -> None:
    root = _root(tmp_path)
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text(JUNCTION_MARKER, encoding="utf-8")
    if not _make_dir_link(root / "jn", outside_dir):
        pytest.skip("cannot create directory junction/symlink here")
    with pytest.raises(FileNotFoundError):
        asset_response(root, "jn/secret.txt")


# ---------------------------------------------------------------------------
# HTTP layer: the real server, request strings on the wire
# ---------------------------------------------------------------------------


def _start_server(root: Path) -> tuple[webserver.MiniccHTTPServer, threading.Thread, list[BaseException]]:
    server = webserver.MiniccHTTPServer(
        ("127.0.0.1", 0),
        SimpleNamespace(config=SimpleNamespace(max_concurrent_tasks=1)),
    )
    served: list[BaseException] = []

    def _serve() -> None:
        try:
            server.serve_forever(poll_interval=0.05)
        except BaseException as exc:
            served.append(exc)

    thread = threading.Thread(target=_serve, daemon=True, name="minicc-t151-server")
    thread.start()
    deadline = time.monotonic() + 15.0
    while True:
        if served or not thread.is_alive():
            raise AssertionError(
                f"the T151 test HTTP server thread {thread.name!r} died before "
                f"serving the readiness probe: {served!r}"
            )
        probe = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            probe.request("GET", "/index.html")
            status = probe.getresponse().status
        except OSError:
            status = -1
        finally:
            probe.close()
        if status == 200:
            return server, thread, served
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"the T151 test HTTP server thread {thread.name!r} never answered "
                f"GET /index.html with 200 within 15s (last status {status})"
            )
        time.sleep(0.02)


def test_http_layer_refuses_every_hostile_request_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path)
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text(JUNCTION_MARKER, encoding="utf-8")
    junction_made = _make_dir_link(root / "jn", outside_dir)
    monkeypatch.setattr(webserver, "STATIC_ROOT", root)
    server, thread, served = _start_server(root)
    url = f"http://127.0.0.1:{server.server_port}"
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        # Control first: a request nobody tampered with must be served with the
        # in-root body, or a 404 below could just be a dead server.
        connection.request("GET", "/index.html")
        response = connection.getresponse()
        control_status = response.status
        control_body = response.read()
        assert control_status == 200 and b"inside-index" in control_body, (
            f"control GET /index.html must serve the in-root page; got "
            f"{control_status} {control_body[:120]!r}"
        )

        targets = [
            # decode-after-strip turns these into real ../ text server-side
            ("/%2e%2e/outside.txt", "encoded dots"),
            ("/..%2foutside.txt", "encoded slash"),
            # Windows: %5c decodes to a separator. POSIX: an ordinary name.
            ("/%2e%2e%5coutside.txt", "encoded backslash"),
            ("/....//outside.txt", "quad-dot"),
            ("/a%00b", "encoded NUL"),
            ("/escape.js", "manifest alias escape"),
        ]
        if junction_made:
            targets.append(("/jn/secret.txt", "junction escape"))

        # Collect every row before asserting (a first-red-hides-the-rest loop
        # would report only one spelling per run).
        problems: list[str] = []
        for target, label in targets:
            connection.request("GET", target)
            response = connection.getresponse()
            body = response.read()
            if response.status != 404:
                problems.append(f"{label} {target!r}: status {response.status}, expected 404")
            for marker in (OUTSIDE_MARKER, JUNCTION_MARKER):
                if marker.encode() in body:
                    problems.append(f"{label} {target!r}: leaked {marker} in the body")
        assert not problems, (
            "hostile request targets must be refused with a bodyless verdict; "
            f"problems: {problems}"
        )
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(3)
        assert not thread.is_alive(), (
            f"the T151 test server thread {thread.name!r} at {url} was still alive "
            "3s after shutdown(); it could still answer, so the refusal rows above "
            "would hold for a server nobody stopped"
        )
