"""M8-T153: /api/file preview endpoint — refusal envelope contract, five guard families.

``/api/file`` (``AgentService.file_preview`` → ``build_registry(Editor).execute(read_file)``)
had zero test coverage. Its contract differs from the sibling tree route in a way
worth pinning: every guard refusal comes back as **HTTP 200** with
``{"status": "error", "summary": "[TOOL_ERROR] …", "content": …, "path": <echo>}``
— never a raised error — while ``/api/files`` raises and yields 400
(that leg is already pinned in ``test_file_tree_api.py``). The ``path`` field
echoes the requested spelling verbatim, including after one level of query
decoding.

The refusal table covers the five guard families reachable through this route,
each with its exact user-visible sentence:

- workspace containment (``Editor._resolve``): ``路径越界: … 超出 workspace 根``
  and ``路径越界: 不允许绝对路径 (…)``;
- sensitive-name guard (``fs._reject_sensitive``): ``拒绝访问敏感文件: …``;
- hidden-grader guard (``fs._reject_graders``): ``拒绝访问评测隐藏目录 .graders``;
- ``.minicc`` auth-file guard (``fs._minicc_sensitive_kind == "deny"``):
  ``拒绝读取 .minicc 下的认证/授权文件: …``;
- plain missing-file misses (directory, empty spelling).

Windows-first spellings (backslash, drive letter) carry per-platform expected
sentences: on POSIX they are ordinary names, so the refusal still happens but
by the missing-file clause instead of the escape clause. ``/etc/passwd`` is the
mirror image (absolute on POSIX, root-relative on Windows).

Positive rows keep the table honest: an in-root ``..`` is served, an escape
spelling that *resolves* back inside is served (containment is judged on the
resolved target, not the spelling), ``.env.example`` is the documented
exception, and ``.minicc/mcp.json`` is served with every header value redacted.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from minicc.web import AgentService, MiniccHTTPServer
from minicc.webauth import WebAuth

OUTSIDE_MARKER = "OUTSIDE-MARK-8899"
NOTE_MARKER = "NOTE-CONTROL-1122"
CRED_MARKER = "CRED-MARK-5521"
SECRETS_MARKER = "SECRETS-MARK-9988"
KEY_MARKER = "KEY-MARK-3311"
PEM_MARKER = "PEM-MARK-4400"
ENV_MARKER = "ENV-MARK-6611"
ENV_LOCAL_MARKER = "ENV-LOCAL-3300"
ALLOW_MARKER = "ALLOW-MARK-7711"
AUDIT_MARKER = "AUDIT-MARK-8811"
HOOKS_MARKER = "HOOKS-MARK-9012"
TOK_MARKER = "TOK-MARK-4412"
WORKER_MARKER = "WORKER-MARK-9901"
GRADER_MARKER = "SEED-MARK-2200"
ENV_EXAMPLE_MARKER = "ENV-EXAMPLE-2200"
MCP_BEARER = "MCPKEY-7788"
MCP_APIKEY = "APIKEY-9911"

_WIN32 = sys.platform == "win32"

# Sentence families; ``{raw}`` is the spelling as the caller wrote it.
F_ESCAPE = "路径越界: {raw} 超出 workspace 根"
F_ABSOLUTE = "路径越界: 不允许绝对路径 ({raw})"
F_SENSITIVE = "拒绝访问敏感文件: {raw} (请由用户手动处理密钥)"
F_MINICC = "拒绝读取 .minicc 下的认证/授权文件: {raw} (请由用户在工作区外手动处理)"
F_GRADERS = "拒绝访问评测隐藏目录 .graders: {raw}"
F_MISSING = "文件不存在: {raw}"

ENVELOPE_KEYS = ["content", "path", "status", "summary"]


def _service(workspace: Path) -> AgentService:
    config = types.SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )
    return AgentService(workspace, config)


def _make_workspace(tmp_path: Path) -> Path:
    """Workspace rooted at ``tmp_path/ws`` with a sibling outside file.

    The nesting is load-bearing: it gives ``../ws/<name>`` a spelling that
    textually escapes and still resolves back inside.
    """
    root = tmp_path / "ws"
    root.mkdir()
    (tmp_path / "outside.txt").write_text(f"{OUTSIDE_MARKER}\n", encoding="utf-8")
    (root / "notes.txt").write_text(f"{NOTE_MARKER}\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "inside.txt").write_text("INNER-7733\n", encoding="utf-8")
    (root / "auth").mkdir()
    (root / "auth" / "credentials.json").write_text(
        f'{{"password": "{CRED_MARKER}"}}\n', encoding="utf-8"
    )
    (root / "auth" / "secrets.json").write_text(
        f'{{"k": "{SECRETS_MARKER}"}}\n', encoding="utf-8"
    )
    (root / "keys").mkdir()
    (root / "keys" / "id_rsa").write_text(f"{KEY_MARKER}\n", encoding="utf-8")
    (root / "certs").mkdir()
    (root / "certs" / "server.pem").write_text(f"{PEM_MARKER}\n", encoding="utf-8")
    (root / ".env").write_text(f"{ENV_MARKER}=1\n", encoding="utf-8")
    (root / ".env.example").write_text(f"{ENV_EXAMPLE_MARKER}=1\n", encoding="utf-8")
    (root / ".env.local").write_text(f"{ENV_LOCAL_MARKER}=1\n", encoding="utf-8")
    (root / ".minicc").mkdir()
    (root / ".minicc" / "web_token.json").write_text(
        f'{{"token": "{TOK_MARKER}"}}\n', encoding="utf-8"
    )
    (root / ".minicc" / "allowlist.json").write_text(
        f'{{"note": "{ALLOW_MARKER}"}}\n', encoding="utf-8"
    )
    (root / ".minicc" / "audit.jsonl").write_text(
        f'{{"action": "{AUDIT_MARKER}"}}\n', encoding="utf-8"
    )
    (root / ".minicc" / "hooks.json").write_text(
        f'{{"note": "{HOOKS_MARKER}"}}\n', encoding="utf-8"
    )
    (root / ".minicc" / "worker").mkdir()
    (root / ".minicc" / "worker" / "w1.config.json").write_text(
        f'{{"token": "{WORKER_MARKER}"}}\n', encoding="utf-8"
    )
    (root / ".minicc" / "mcp.json").write_text(
        json.dumps(
            {
                "servers": {
                    "remote": {
                        "url": "https://example.test/mcp",
                        "headers": {
                            "Authorization": f"Bearer {MCP_BEARER}",
                            "X-Api-Key": MCP_APIKEY,
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (root / ".graders").mkdir()
    (root / ".graders" / "seed.py").write_text(f"{GRADER_MARKER}\n", encoding="utf-8")
    return root


@pytest.fixture()
def service(tmp_path: Path) -> AgentService:
    root = _make_workspace(tmp_path)
    svc = _service(root)
    yield svc
    svc.shutdown()


def _expected_sentence(family, raw: str) -> str:
    if isinstance(family, dict):
        family = family["win32" if _WIN32 else "posix"]
    return "[TOOL_ERROR] " + family.format(raw=raw)


# (id, spelling, sentence family / per-platform families, leaked marker if served)
DENY_ROWS = [
    ("dotdot-escape", "../outside.txt", F_ESCAPE, OUTSIDE_MARKER),
    ("dotdot-interleaved", "sub/../../outside.txt", F_ESCAPE, OUTSIDE_MARKER),
    ("dotdot-bare", "..", F_ESCAPE, None),
    # Windows uses ``\`` as the separator, so this spelling escapes there; on
    # POSIX it is one ordinary (nonexistent) file name. Both refuse.
    ("backslash-escape", "..\\outside.txt", {"win32": F_ESCAPE, "posix": F_MISSING}, OUTSIDE_MARKER),
    # A drive-letter path is absolute on Windows; on POSIX it is a relative
    # name whose first component is literally ``C:``.
    ("drive-absolute", "C:/Windows/win.ini", {"win32": F_ABSOLUTE, "posix": F_MISSING}, None),
    ("drive-absolute-backslash", "C:\\Windows\\win.ini", {"win32": F_ABSOLUTE, "posix": F_MISSING}, None),
    # Mirror image: absolute on POSIX; a root-relative (drive-less) path on
    # Windows resolves to <drive>/etc/passwd, outside the workspace.
    ("posix-absolute", "/etc/passwd", {"win32": F_ESCAPE, "posix": F_ABSOLUTE}, None),
    ("sensitive-credentials", "auth/credentials.json", F_SENSITIVE, CRED_MARKER),
    ("sensitive-secrets", "auth/secrets.json", F_SENSITIVE, SECRETS_MARKER),
    ("sensitive-id-rsa", "keys/id_rsa", F_SENSITIVE, KEY_MARKER),
    ("sensitive-pem", "certs/server.pem", F_SENSITIVE, PEM_MARKER),
    ("sensitive-dotenv", ".env", F_SENSITIVE, ENV_MARKER),
    ("sensitive-dotenv-variant", ".env.local", F_SENSITIVE, ENV_LOCAL_MARKER),
    ("minicc-web-token", ".minicc/web_token.json", F_MINICC, TOK_MARKER),
    ("minicc-allowlist", ".minicc/allowlist.json", F_MINICC, ALLOW_MARKER),
    ("minicc-audit", ".minicc/audit.jsonl", F_MINICC, AUDIT_MARKER),
    ("minicc-hooks", ".minicc/hooks.json", F_MINICC, HOOKS_MARKER),
    ("minicc-worker-config", ".minicc/worker/w1.config.json", F_MINICC, WORKER_MARKER),
    ("graders-hidden-dir", ".graders/seed.py", F_GRADERS, GRADER_MARKER),
    ("directory-dot", ".", F_MISSING, None),
    ("empty-spelling", "", F_MISSING, None),
]


@pytest.mark.parametrize(
    "case_id, raw, family, marker",
    DENY_ROWS,
    ids=[row[0] for row in DENY_ROWS],
)
def test_refusal_envelope_per_spelling(
    service: AgentService, case_id: str, raw: str, family, marker: str | None
) -> None:
    out = service.file_preview(raw)
    assert sorted(out) == ENVELOPE_KEYS, f"envelope keys changed for {case_id}: {sorted(out)}"
    assert out["status"] == "error", f"{case_id!r} was not refused: {out['summary']!r}"
    expected = _expected_sentence(family, raw)
    assert out["summary"] == expected, f"{case_id!r} refusal sentence drifted"
    assert out["path"] == raw, f"{case_id!r} must echo the requested spelling verbatim"
    if marker is not None:
        leaked = marker in out["content"] or marker in out["summary"]
        assert not leaked, f"{case_id!r} served guarded content (marker {marker!r} leaked)"


ALLOW_ROWS = [
    ("plain-file", "notes.txt", NOTE_MARKER),
    # ``..`` inside the root is a normal name, not a refusal trigger.
    ("in-root-dotdot", "sub/../notes.txt", NOTE_MARKER),
    # Containment is judged on the *resolved* target: this spelling escapes
    # textually and lands back inside, so it is served.
    ("escape-spelling-that-lands-inside", "../ws/notes.txt", NOTE_MARKER),
    ("dotenv-example", ".env.example", ENV_EXAMPLE_MARKER),
]


@pytest.mark.parametrize(
    "case_id, raw, marker",
    ALLOW_ROWS,
    ids=[row[0] for row in ALLOW_ROWS],
)
def test_allowed_spellings_are_served(
    service: AgentService, case_id: str, raw: str, marker: str
) -> None:
    out = service.file_preview(raw)
    assert sorted(out) == ENVELOPE_KEYS, f"envelope keys changed for {case_id}: {sorted(out)}"
    assert out["status"] == "ok", f"{case_id!r} was refused: {out['summary']!r}"
    assert marker in out["content"], f"{case_id!r} did not serve the expected content"
    assert out["path"] == raw


def test_minicc_mcp_json_is_served_with_redacted_headers(service: AgentService) -> None:
    """The redact row proves the .minicc deny-list is not over-broad.

    ``mcp.json`` is the one .minicc file that stays readable; every header
    value is replaced before the model sees it. Pinning the count (= 2) keeps
    "only the first header was redacted" from passing.
    """
    out = service.file_preview(".minicc/mcp.json")
    assert out["status"] == "ok", out["summary"]
    content = out["content"]
    assert MCP_BEARER not in content and MCP_APIKEY not in content, (
        "raw credential values must not survive the redact path"
    )
    assert content.count("[REDACTED]") == 2, "both header values must be redacted"
    assert '"Authorization": "[REDACTED]"' in content
    assert '"X-Api-Key": "[REDACTED]"' in content


def _serve_thread(service: AgentService) -> tuple[MiniccHTTPServer, threading.Thread, str]:
    server = MiniccHTTPServer(("127.0.0.1", 0), service, auth=WebAuth("t", required=False))
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        daemon=True,
        name="minicc-t153-server",
    )
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    deadline = time.monotonic() + 10.0
    while True:
        if not thread.is_alive():
            raise AssertionError(
                f"the test HTTP server thread {thread.name!r} died before serving {url}"
            )
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=5) as probe:
                if probe.status == 200:
                    return server, thread, url
        except (urllib.error.HTTPError, OSError):
            pass
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"the test HTTP server thread {thread.name!r} never answered GET /api/health "
                f"with 200 within 10s at {url}"
            )
        time.sleep(0.02)


@pytest.fixture()
def live_server(tmp_path: Path):
    root = _make_workspace(tmp_path)
    service = _service(root)
    server, thread, url = _serve_thread(service)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), (
            f"the preview-route test HTTP server thread {thread.name!r} was still alive 5s "
            f"after shutdown() at {url}; its socket can still answer"
        )
        service.shutdown()


# (id, raw spelling, url encoding mode, expected status, expected summary family,
#  marker absent from body, expected path echo)
#   mode "quote": the client percent-encodes the whole spelling;
#   mode "verbatim": the string is placed in the query as-is (already encoded);
#   mode "none": no path parameter at all.
HTTP_ROWS = [
    # The control row asserts the served content positively; its "marker absent"
    # slot is None because the marker is exactly what must be *present* here.
    ("http-control", "notes.txt", "quote", "ok", None, None, "notes.txt"),
    ("http-dotdot-raw", "../outside.txt", "quote", "error", F_ESCAPE, OUTSIDE_MARKER, "../outside.txt"),
    # One level of decoding happens in parse_qs; the decoded spelling reaches
    # the guard and is echoed back decoded.
    ("http-encoded-single", "%2e%2e%2foutside.txt", "verbatim", "error", F_ESCAPE, OUTSIDE_MARKER, "../outside.txt"),
    # Double-encoded stays literal after one decode and misses as a file name.
    ("http-encoded-double", "%252e%252e%252foutside.txt", "verbatim", "error", F_MISSING, OUTSIDE_MARKER, "%2e%2e%2foutside.txt"),
    ("http-minicc-web-token", ".minicc/web_token.json", "quote", "error", F_MINICC, TOK_MARKER, ".minicc/web_token.json"),
    ("http-graders", ".graders/seed.py", "quote", "error", F_GRADERS, GRADER_MARKER, ".graders/seed.py"),
    ("http-absolute", "C:/Windows/win.ini", "quote", "error", {"win32": F_ABSOLUTE, "posix": F_MISSING}, None, "C:/Windows/win.ini"),
    ("http-missing-param", None, "none", "error", F_MISSING, None, ""),
]


@pytest.mark.parametrize(
    "case_id, raw, mode, wanted_status, family, marker, echo",
    HTTP_ROWS,
    ids=[row[0] for row in HTTP_ROWS],
)
def test_http_layer_never_raises_and_echoes(
    live_server: str,
    case_id: str,
    raw: str | None,
    mode: str,
    wanted_status: str,
    family,
    marker: str | None,
    echo: str,
) -> None:
    if mode == "none":
        query = ""
    elif mode == "verbatim":
        query = f"?path={raw}"
    else:
        query = "?path=" + urllib.parse.quote(raw, safe="")
    try:
        with urllib.request.urlopen(live_server + "/api/file" + query, timeout=10) as response:
            status_code = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # pragma: no cover - the contract is 200
        raise AssertionError(
            f"{case_id!r}: /api/file answered {exc.code} instead of the 200 envelope"
        ) from exc
    assert status_code == 200, f"{case_id!r}: expected the 200 envelope, got {status_code}"
    obj = json.loads(body)
    assert sorted(obj) == ENVELOPE_KEYS, f"{case_id!r}: envelope keys changed: {sorted(obj)}"
    assert obj["status"] == wanted_status, f"{case_id!r}: {obj['summary']!r}"
    if family is not None:
        assert obj["summary"] == _expected_sentence(family, echo), (
            f"{case_id!r}: refusal sentence drifted"
        )
    else:
        assert obj["summary"].startswith("读取 notes.txt"), obj["summary"]
        assert NOTE_MARKER in obj["content"]
    assert obj["path"] == echo, f"{case_id!r}: path must echo the (decoded) spelling"
    if marker is not None:
        assert marker not in body, f"{case_id!r}: guarded content leaked over HTTP"


def test_http_layer_redacts_mcp_headers(live_server: str) -> None:
    query = "?path=" + urllib.parse.quote(".minicc/mcp.json", safe="")
    with urllib.request.urlopen(live_server + "/api/file" + query, timeout=10) as response:
        assert response.status == 200
        body = response.read().decode("utf-8")
    obj = json.loads(body)
    assert obj["status"] == "ok", obj["summary"]
    assert MCP_BEARER not in body and MCP_APIKEY not in body
    assert obj["content"].count("[REDACTED]") == 2
    assert obj["path"] == ".minicc/mcp.json"
