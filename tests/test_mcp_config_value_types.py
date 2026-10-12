"""M8-T238: every value ``load_mcp_config`` reads off mcp.json is checked as the type it is used as.

Measured on the main tree at ``ce6a7a2`` (2026-10-12) before this batch landed -
all three lines below are what the shipped loader actually answered:

    {"command": "server.py", "read_only": "false"}  -> ACCEPTED, .read_only=True
    {"command": "server.py", "url": ["http://x"]}   -> ACCEPTED, transport="http", url="['http://x']"
    {"command": ["server.py"]}                      -> REFUSED 「缺少 command 或 url」

``read_only`` was the only field the loader *coerced* rather than validated
(``bool(value.get("read_only", False))``), and it is the field that decides the
risk string every tool of that server is registered under:
``minicc/audit.py:259-260`` answers risk ``readonly`` with
``AuthorizationDecision(True, "readonly", "只读工具已允许", "default_readonly")``
without consulting ``allow_changes`` and without entering the session-allowlist
path. So a workspace file could write its own consent exemption:
``"read_only": "false"`` - a sentence meaning 「this server writes」 - is a
non-empty string, hence True, hence an unasked-for run.

``command`` and ``url`` decided *presence* with ``isinstance(..., str)`` and then
stored ``str(value.get(...))``, so a mis-typed value either took the missing-key
verdict (「写了但类型错」 and 「根本没写」 printed the same sentence) or reached
``McpServerConfig`` as its Python repr: a list url skipped the scheme check and
the SSRF gate - both of which only ever read strings - flipped ``transport`` to
``http``, and discarded the stdio command the operator actually wrote.

Nothing in this repo depends on that leniency: every shipped fake server writes
``read_only: true`` (a real bool) and ``README.md:179``/``README.md:184``
document the key as a JSON bool, so asking for the declared type changes the
verdict for no valid config.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import re
import sys
from pathlib import Path

import pytest

from minicc import mcp as mcp_module
from minicc.audit import authorize_tool
from minicc.mcp import McpError, McpManager, McpServerConfig, load_mcp_config
from minicc.tools import Editor, build_registry

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_MODULE = REPO_ROOT / "minicc" / "mcp.py"

#: One tool, whose handler writes a file into the workspace. The risk string the
#: loader produced is therefore the only thing between a workspace ``mcp.json``
#: and a write nobody was asked about.
SERVER_SRC = '''
import json
import pathlib
import sys


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "serverInfo": {"name": "fake", "version": "0"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": "write_note", "description": "write note.txt"}]}})
    elif method == "tools/call":
        target = pathlib.Path(sys.argv[2]) / "note.txt"
        target.write_text("written by the mcp server\\n", encoding="utf-8")
        send({"jsonrpc": "2.0", "id": mid,
              "result": {"content": [{"type": "text", "text": "ok"}]}})
'''

#: Wrong-type spellings for the field the loader must read as a boolean.
NOT_A_BOOL: list[object] = ["false", "no", "0", "yes", "true", 1, 0, [], [True], {"a": 1}]
#: Wrong-type spellings for a field the loader must read as a string.
NOT_A_TEXT: list[object] = [["server.py"], ["http://x"], 7, {"a": 1}, True]


def _entry_file(workspace: Path, entry: dict[str, object]) -> Path:
    """Write one server entry into a workspace, the way a user edits the file."""
    (workspace / ".minicc").mkdir(parents=True, exist_ok=True)
    (workspace / ".minicc" / "mcp.json").write_text(
        json.dumps({"servers": {"srv": entry}}, ensure_ascii=False), encoding="utf-8"
    )
    return workspace


def _verdict(workspace: Path, entry: dict[str, object]) -> tuple[str, str]:
    """('accepted', the config) or ('refused', the McpError text) - never a crash."""
    try:
        configs = load_mcp_config(_entry_file(workspace, entry))
    except McpError as exc:
        return "refused", str(exc)
    return "accepted", repr(configs[0])


def _stdio_server(workspace: Path, **declaration: object) -> Path:
    """A real child-process MCP server, declared however the caller asks."""
    workspace.mkdir(parents=True, exist_ok=True)
    script = workspace / "server.py"
    script.write_text(SERVER_SRC, encoding="utf-8")
    entry: dict[str, object] = {"command": sys.executable, "args": [str(script), str(workspace)]}
    entry.update(declaration)
    return _entry_file(workspace, entry)


def test_a_wrong_type_read_only_is_refused_by_its_own_name(tmp_path: Path) -> None:
    """``bool(x)`` is not a type check: every spelling below was ACCEPTED before this batch.

    Counted per row, because a table that only asserts 「at least one refused」
    stays green while nine of ten are still coerced.
    """
    refusals: list[str] = []
    for index, spelling in enumerate(NOT_A_BOOL):
        outcome, text = _verdict(
            tmp_path / f"ro{index}", {"command": "server.py", "read_only": spelling}
        )
        assert outcome == "refused", f"read_only={json.dumps(spelling)} was {outcome}: {text}"
        assert "read_only" in text, f"the refusal for read_only={json.dumps(spelling)} does not name the key: {text}"
        assert "非法" in text, f"the refusal for read_only={json.dumps(spelling)} does not call it illegal: {text}"
        refusals.append(text)
    assert len(refusals) == len(NOT_A_BOOL), (len(refusals), len(NOT_A_BOOL))

    # Absent and explicit null stay 「no declaration」, which is the default.
    for spelling in ({"command": "server.py"}, {"command": "server.py", "read_only": None}):
        configs = load_mcp_config(_entry_file(tmp_path / "flag-default", spelling))
        assert configs[0].read_only is False, (
            f"{json.dumps(spelling)} must default read_only to False, got {configs[0].read_only!r}"
        )


def test_the_declaration_decides_between_asking_and_never_asking(tmp_path: Path) -> None:
    """The declaration is load-bearing at the consent gate, in both directions.

    A real stdio server is spawned, its tool is registered through
    ``build_registry``, and the risk the *registry* reports is fed to
    ``authorize_tool`` with the arguments ``minicc/main.py:338`` feeds it. True
    must auto-allow (``default_readonly``), False must refuse and ask
    (``missing_task_exec``) - a server whose tools behaved identically under both
    declarations would make the refusal above meaningless. A string declaration
    now never reaches the registry at all.
    """
    for declaration, expected_risk, expected_allowed, expected_authorization in (
        (True, "readonly", True, "default_readonly"),
        (False, "exec", False, "missing_task_exec"),
    ):
        workspace = _stdio_server(tmp_path / f"gate-{declaration}", read_only=declaration)
        manager = McpManager(workspace)
        registry = build_registry(Editor(workspace), yolo=False, mcp_manager=manager)
        specs = manager.tool_specs()
        assert len(specs) == 1, f"the fake server registered {len(specs)} tools, expected 1"
        name = specs[0].name
        assert registry.risk_of(name) == expected_risk, (
            f"read_only={declaration} must register the tool under risk {expected_risk!r}, "
            f"the registry reports {registry.risk_of(name)!r} (spec.risk={specs[0].risk!r})"
        )
        decision = authorize_tool(
            name,
            registry.risk_of(name),
            {"path": "note.txt"},
            allow_changes=False,
            allow_network=False,
            permission_mode="default",
        )
        assert decision.allowed is expected_allowed, (
            f"read_only={declaration} -> risk {expected_risk!r} -> authorize_tool(allow_changes=False) "
            f"allowed={decision.allowed} ({decision.authorization}): {decision.reason}"
        )
        assert decision.authorization == expected_authorization, (
            f"read_only={declaration} was decided by {decision.authorization!r}, "
            f"expected {expected_authorization!r}: {decision.reason}"
        )

    # A writable server declared with a string is refused by the loader, so it
    # cannot be registered as readonly and run unasked.
    workspace = _stdio_server(tmp_path / "gate-string", read_only="false")
    with pytest.raises(McpError, match="read_only"):
        McpManager(workspace)


@pytest.mark.parametrize("spelling", NOT_A_TEXT)
def test_a_wrong_type_command_is_named_not_reported_as_missing(tmp_path: Path, spelling: object) -> None:
    """「写了但类型错」 must not borrow the sentence reserved for 「根本没写」.

    The load-bearing clause is the negative one: 「缺少 command 或 url」 is also
    the right answer for an entry that declares neither, so only forbidding that
    text keeps the two verdicts apart.
    """
    outcome, text = _verdict(tmp_path, {"command": spelling})
    assert outcome == "refused", f"command={json.dumps(spelling)} was {outcome}: {text}"
    assert "command" in text, f"the refusal does not name command: {text}"
    assert "缺少" not in text, f"a present-but-wrong-type command was reported as missing: {text}"


@pytest.mark.parametrize("spelling", NOT_A_TEXT)
def test_a_wrong_type_url_beside_a_good_command_does_not_become_http_transport(
    tmp_path: Path, spelling: object
) -> None:
    """A url that never passed a check must not decide the transport.

    Before this batch ``{"command": "server.py", "url": ["http://x"]}`` loaded:
    ``has_url`` was False so neither the scheme test nor ``assert_public_http_url``
    ran, then ``str(value.get("url") or "")`` stored the repr, so ``transport``
    read 「http」, ``McpManager._client`` built an ``McpHttpClient`` for
    「['http://x']」 and the command the operator wrote was dropped - the failure
    surfaced later as 「MCP HTTP server srv 不可达: <urlopen error unknown url
    type」.
    """
    outcome, text = _verdict(tmp_path, {"command": "server.py", "url": spelling})
    assert outcome == "refused", f"command + url={json.dumps(spelling)} was {outcome}: {text}"
    assert "url" in text, f"the refusal does not name url: {text}"
    assert "缺少" not in text, f"a present-but-wrong-type url was reported as missing: {text}"

    # The other direction stays exactly as it was: no url text means stdio.
    for absent in (None, ""):
        configs = load_mcp_config(
            _entry_file(tmp_path / "url-absent", {"command": "server.py", "url": absent})
        )
        assert configs[0].transport == "stdio", (
            f"url={absent!r} must not pick the http transport, picked {configs[0].transport}"
        )
        assert configs[0].url == "", f"url={absent!r} must store nothing, stored {configs[0].url!r}"

    # Both fields mis-typed: the entry has no usable transport either way, but
    # the sentence must still name the key that is wrong. This is the clause
    # that makes the *order* of the two checks load-bearing - a loader that
    # decides 「neither is a string」 first and validates second answers 「缺少」
    # here and leaves the operator to guess which key to fix.
    outcome, text = _verdict(tmp_path / "both-wrong", {"command": ["a"], "url": ["b"]})
    assert outcome == "refused" and "缺少" not in text and "command" in text, (
        f"an entry with two mis-typed transport fields answered {outcome}: {text}"
    )


def test_the_value_the_loader_checks_is_the_value_the_server_gets(tmp_path: Path) -> None:
    """Presence is decided on ``.strip()``; the config must carry that same text.

    ``{"command": "  <python>  "}`` loaded before this batch with
    ``command='  <python>  '``, and the client the loader had just blessed died
    with 「无法启动 MCP server srv: [WinError 2] 系统找不到指定的文件。」 - the
    whitespace-invisible spelling of the same executable. Both spellings now
    spawn the child and list the same one tool.
    """
    bare = sys.executable
    script = tmp_path / "server.py"
    script.write_text(SERVER_SRC, encoding="utf-8")

    for label, command in (("bare", bare), ("padded", f"   {bare}   ")):
        workspace = tmp_path / label
        _entry_file(workspace, {"command": command, "args": [str(script), str(workspace)], "read_only": True})
        configs = load_mcp_config(workspace)
        assert configs[0].command == bare, (
            f"{label}: the loader stored {configs[0].command!r}, not the {bare!r} its own check read"
        )
        specs = McpManager(workspace).tool_specs()
        assert len(specs) == 1, (
            f"{label}: the server the loader accepted listed {len(specs)} tools - it never started"
        )


def test_the_url_the_loader_blesses_is_the_url_the_gate_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same address, two verdicts, and the stored text is always the checked text.

    ``MINICC_ALLOW_PRIVATE_MCP`` is the shipped override the suite already uses
    (``tests/test_mcp_config_validation.py:132``). With the gate open the url is
    accepted and stored exactly as the gate read it; with the gate closed the
    same entry is refused by the SSRF protection rather than becoming a config -
    which is the invariant the repr-carrying url used to break.
    """
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_MCP", "1")
    accepted = load_mcp_config(_entry_file(tmp_path / "http-open", {"url": " http://127.0.0.1:3000/mcp "}))
    assert accepted[0].transport == "http", accepted[0].transport
    assert accepted[0].url == "http://127.0.0.1:3000/mcp", (
        f"the client would be handed {accepted[0].url!r} while the gate read the stripped text"
    )

    monkeypatch.delenv("MINICC_ALLOW_PRIVATE_MCP", raising=False)
    outcome, text = _verdict(tmp_path / "http-closed", {"url": "http://127.0.0.1:3000/mcp"})
    assert outcome == "refused", f"the closed gate let {text} through"
    assert "SSRF" in text, f"the closed gate answered something else: {text}"


def test_no_key_is_read_off_the_json_except_through_something_that_names_it() -> None:
    """The census that would have caught all three fields, kept as a rule.

    Derived, not hand-typed: the population comes out of
    ``dataclasses.fields(McpServerConfig)``, so a new field whose JSON key nobody
    validates goes red, and a deleted read goes red too (the loader would then be
    ignoring a field the card still declares).
    """
    assert Path(mcp_module.__file__).resolve() == MCP_MODULE.resolve(), (
        f"this census reads {MCP_MODULE}, but the import resolved to {mcp_module.__file__}"
    )
    tree = ast.parse(MCP_MODULE.read_text(encoding="utf-8"))
    loader = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "load_mcp_config"),
        None,
    )
    assert loader is not None, f"no def load_mcp_config at module level in {MCP_MODULE}"

    reads: set[str] = set()
    validated: set[str] = set()
    for node in ast.walk(loader):
        if isinstance(node, ast.Call):
            base = ast.unparse(node.func)
            if base == "value.get" and node.args:
                if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    reads.add(node.args[0].value)
            elif base.startswith("_config_"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        reads.add(arg.value)
                        validated.add(arg.value)
        elif isinstance(node, ast.Subscript) and ast.unparse(node.value) == "value":
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                reads.add(node.slice.value)
    for node in ast.walk(loader):
        if isinstance(node, ast.Raise):
            validated.update(re.findall(r"的 ([A-Za-z_][A-Za-z0-9_]*) 非法", ast.unparse(node)))

    assert reads, f"the census of {MCP_MODULE} saw no JSON keys at all - it checked nothing"
    unvalidated = sorted(reads - validated)
    assert not unvalidated, (
        f"load_mcp_config reads {sorted(reads)} off the JSON; these have no validator that names them: {unvalidated}"
    )
    declared = {field.name for field in dataclasses.fields(McpServerConfig)} - {"name"}
    unread = sorted(declared - reads)
    assert not unread, (
        f"McpServerConfig declares {sorted(declared)} but the loader reads none of {unread} - "
        "a field the card carries with no JSON reader is the M8-T195 defect shape"
    )


def test_the_loader_still_refuses_an_entry_that_declares_neither(tmp_path: Path) -> None:
    """The repair must not eat M8-T140's verdict.

    「缺少 command 或 url」 is shipped text that other gates read
    (``tests/test_mcp_config_validation.py:47``, ``tests/test_mcp_http.py:134``);
    this batch only takes the *wrong-type* shapes off that sentence.
    """
    for index, entry in enumerate(({"args": []}, {}, {"command": "", "url": ""}, {"command": "   "}, {"url": None})):
        outcome, text = _verdict(tmp_path / f"missing-{index}", entry)
        assert outcome == "refused", f"{json.dumps(entry)} was {outcome}: {text}"
        assert "缺少 command 或 url" in text, f"{json.dumps(entry)} refused with something else: {text}"
