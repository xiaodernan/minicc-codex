"""M8-T243: the environment names an MCP child may inherit must be names that exist.

Measured on the main tree before this batch (read-only probe, in-process):

    declared entries: 33 distinct: 27
    duplicates: [('LC_ALL', 3), ('SYSTEMDRIVE', 2), ('USERPROFILE', 2), ('WINDIR', 3)]
    inherited from the probe parent: {'LANG': True, 'LANGUAGE': False, 'LC_ALL': True,
                                      'LC_CTYPE': False, 'PYTHONIOENCODING': False, 'TMPDIR': True}

``INHERITED_ENV_KEYS`` carried the one entry 「LANGUANGE」 - a misspelling of
``LANGUAGE``, the variable gettext uses to pick the message language. The misspelled
name can match nothing in any real environment, while the name the operator wrote is
dropped silently. The shipped coverage only ever tested the *scrub* side
(``tests/test_security_perimeter.py:220`` asserts what must NOT arrive), so the
inherit side had no reader and the typo lived on. The same list shows how it happened:
six of its 33 entries are repeats, i.e. it was appended to by hand and never
reconciled against itself.

These cases reconcile it: what the promise carries must arrive (C1), what the promise
forbids must not (C2), the list must not list a name twice (C3), the shipped spawn must
actually route through the scrub (C4), no credential name the config layer knows may
join the list (C5, population derived from ``minicc/config.py``), and the fixed name
must arrive in a real child process rather than only in this test's interpreter (C6).
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

import pytest

from minicc.mcp import McpServerConfig, McpStdioClient

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_MODULE = REPO_ROOT / "minicc" / "mcp.py"
CONFIG_MODULE = REPO_ROOT / "minicc" / "config.py"

#: The message-locale variables a child needs to speak the user's language.
LOCALE_NAMES = ("LANG", "LANGUAGE", "LC_ALL")

#: Name endings that mark a credential in this repository's own vocabulary.
CREDENTIAL_ENDINGS = ("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD")

#: Floors for the two censuses, so a harvest that read *nothing* cannot be reported as
#: a list that has no problem. Both sit far below the population measured in this
#: repository (the inherit list has 28 entries, the config layer publishes
#: MINICC_API_KEY and MINICC_PLAN_API_KEY), so they only fire when the census itself is
#: blind - and the message says which census went blind.
MIN_INHERIT_ENTRIES = 20
MIN_CREDENTIAL_NAMES = 2


def _mcp_tree() -> ast.Module:
    from minicc import mcp as mcp_module

    assert Path(mcp_module.__file__).resolve() == MCP_MODULE, (
        f"this file grades {MCP_MODULE}, but the import resolved to {mcp_module.__file__}"
    )
    return ast.parse(MCP_MODULE.read_text(encoding="utf-8"))


def _declared_from_ast(tree: ast.Module) -> list[str]:
    """The names the source declares, read off the class body itself."""
    class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "McpStdioClient"), None)
    assert class_node is not None, f"no class McpStdioClient at module level in {MCP_MODULE}"
    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "INHERITED_ENV_KEYS" for target in stmt.targets
        ):
            assert isinstance(stmt.value, ast.Tuple), (
                f"INHERITED_ENV_KEYS is a {type(stmt.value).__name__}, not the tuple this census walks"
            )
            return [elt.value for elt in stmt.value.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
    raise AssertionError(f"{MCP_MODULE} declares no INHERITED_ENV_KEYS assignment")


def test_the_locale_the_list_claims_to_carry_reaches_the_child(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every locale name a parent sets must survive into the child environment.

    A name the list spells wrong is invisible to every other check: it is a legal
    entry, it matches nothing in ``os.environ``, and the scrub side stays green.
    """
    for name in LOCALE_NAMES:
        monkeypatch.setenv(name, f"probe-{name}")
    kept = {key.upper() for key in McpStdioClient.scrubbed_env(None)}
    missing = [name for name in LOCALE_NAMES if name not in kept]
    assert not missing, (
        f"the parent carries {LOCALE_NAMES} but the child loses {missing}; "
        f"INHERITED_ENV_KEYS as declared: {sorted(McpStdioClient.INHERITED_ENV_KEYS)}"
    )


def test_an_ambient_credential_never_arrives_by_inheritance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Widening the list to fix a typo must not turn the scrub inside out.

    This is the shipped promise in ``tests/test_security_perimeter.py`` seen from the
    other side: a credential-shaped name may reach the child only through the server
    entry's own ``env`` mapping.
    """
    monkeypatch.setenv("MINICC_API_KEY", "probe-api-key-value")
    monkeypatch.setenv("MINICC_PLAN_API_KEY", "probe-plan-key-value")
    env = McpStdioClient.scrubbed_env(None)
    leaked = sorted(key for key in env if key.upper().endswith(CREDENTIAL_ENDINGS))
    assert not leaked, f"credential-shaped names inherited from the ambient environment: {leaked}"
    for probe in ("probe-api-key-value", "probe-plan-key-value"):
        assert probe not in env.values(), f"{probe!r} reached the child environment"


def test_the_inherit_list_never_lists_a_name_twice() -> None:
    """Reconcile the hand-appended list against itself.

    The duplicates are not dangerous on their own - they are the evidence that nobody
    ever counted the list, which is exactly why the misspelling had no reader. The
    runtime tuple is checked against the source's own tuple so this case cannot pass
    by grading a different copy of the module.
    """
    declared = list(McpStdioClient.INHERITED_ENV_KEYS)
    from_source = _declared_from_ast(_mcp_tree())
    assert len(declared) >= MIN_INHERIT_ENTRIES, (
        f"the shipped inherit list carries {len(declared)} entries, below the floor {MIN_INHERIT_ENTRIES} - "
        "the census read too little to say anything about duplicates"
    )
    assert len(from_source) >= MIN_INHERIT_ENTRIES, (
        f"{MCP_MODULE} declares {len(from_source)} entries, below the floor {MIN_INHERIT_ENTRIES} - "
        "the AST walk found the assignment but not the names it claims"
    )
    assert len(declared) == len(from_source), (
        f"the shipped tuple has {len(declared)} entries but {MCP_MODULE} declares {len(from_source)} "
        "- the test and the module do not agree on which list is being graded"
    )
    counts = Counter(name.strip().upper() for name in declared)
    repeats = {name: count for name, count in counts.items() if count > 1}
    assert not repeats, (
        f"{len(declared)} entries carry only {len(counts)} distinct names; repeated: {sorted(repeats.items())} "
        f"- a list nobody reconciles is where 「LANGUANGE」 hid"
    )


def test_the_spawned_child_gets_the_scrubbed_environment() -> None:
    """The scrub must be wired into the spawn, not merely available next to it.

    ``_start`` builds ``env`` from ``scrubbed_env`` and hands it to ``Popen(env=...)``.
    If either half is dropped the child gets the whole ambient environment while every
    function-level test above still passes - so the claim is read off the call site.
    """
    tree = _mcp_tree()
    class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "McpStdioClient"), None)
    assert class_node is not None, f"no class McpStdioClient in {MCP_MODULE}"
    start = next((n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == "_start"), None)
    assert start is not None, f"McpStdioClient has no _start in {MCP_MODULE}"
    popen = next(
        (call for call in ast.walk(start) if isinstance(call, ast.Call) and ast.unparse(call.func) == "subprocess.Popen"),
        None,
    )
    assert popen is not None, f"no subprocess.Popen call inside _start - {MCP_MODULE} no longer spawns here"
    env_kw = next((kw for kw in popen.keywords if kw.arg == "env"), None)
    assert env_kw is not None, "Popen is called without env=, so the child inherits the whole ambient environment"

    def is_scrub_call(node: ast.expr) -> bool:
        return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "scrubbed_env"

    if is_scrub_call(env_kw.value):
        return
    assert isinstance(env_kw.value, ast.Name), (
        f"Popen's env= is a {type(env_kw.value).__name__}, not a scrubbed_env call or the name bound to one"
    )
    bound = env_kw.value.id
    producers = [
        stmt for stmt in ast.walk(start)
        if isinstance(stmt, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == bound for target in stmt.targets)
        and is_scrub_call(stmt.value)
    ]
    assert producers, (
        f"Popen takes env={bound}, but nothing in _start assigns the result of scrubbed_env to {bound} "
        "- the scrub is no longer on the spawn path"
    )


def test_no_credential_name_the_config_layer_knows_is_on_the_inherit_list() -> None:
    """The list's own purpose, checked against the names this repository treats as secrets.

    ``minicc/config.py`` is the owner of the ``MINICC_*`` environment vocabulary, so
    the credential population is read from it rather than hand-typed here. A floor
    keeps an empty harvest from passing as clean.
    """
    tree = ast.parse(CONFIG_MODULE.read_text(encoding="utf-8"))
    credentials = sorted({
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("MINICC_")
        and node.value.endswith(CREDENTIAL_ENDINGS)
    })
    assert len(credentials) >= MIN_CREDENTIAL_NAMES, (
        f"{CONFIG_MODULE} published only {len(credentials)} credential-shaped names {credentials}, below the "
        f"floor {MIN_CREDENTIAL_NAMES} - the census read too little to clear the inherit list"
    )
    listed = {name.strip().upper() for name in McpStdioClient.INHERITED_ENV_KEYS}
    both = sorted(set(credentials) & listed)
    assert not both, (
        f"{CONFIG_MODULE} treats {both} as a credential, yet McpStdioClient would hand it to every "
        f"MCP server child; the list reads: {sorted(McpStdioClient.INHERITED_ENV_KEYS)}"
    )


#: A fake MCP server that reports one of its own environment variables. It answers the
#: handshake ``McpStdioClient._start`` performs and nothing else, so the case cannot pass
#: by accident: no child, no answer.
ENV_PROBE_SRC = r'''
import json, os, sys

MISSING = "<env-name-not-inherited>"


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "serverInfo": {"name": "envprobe", "version": "0"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": "echo_env", "description": "report one environment variable"}]}})
    elif method == "tools/call":
        key = str(((msg.get("params") or {}).get("arguments") or {}).get("key", ""))
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": os.environ.get(key, MISSING)}],
            "isError": False}})
    elif mid is not None:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "unknown"}})
'''


def test_the_locale_a_parent_carries_arrives_in_a_real_child(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The shipped seam: a spawned MCP server, not this interpreter, must see the locale.

    ``_content_to_tool_result`` (mcp.py:52) fills ``head``/``tail`` and never ``output``,
    so this reads ``render()``; asserting on ``output`` here would be a permanently true
    claim (the shape M8-T244 registers).
    """
    probe = "probe-locale-value"
    monkeypatch.setenv("LANGUAGE", probe)
    server = tmp_path / "env_probe_server.py"
    server.write_text(ENV_PROBE_SRC, encoding="utf-8")
    config = McpServerConfig(name="envprobe", command=sys.executable, args=(str(server),))
    client = McpStdioClient(config, tmp_path)
    try:
        result = client.call_tool("echo_env", {"key": "LANGUAGE"})
    finally:
        client.close()
    seen = result.render()
    assert probe in seen, (
        f"the child answered {result.head!r} when asked for LANGUAGE while this process had {probe!r}; "
        "the inherit list dropped the name between scrubbed_env() and the real child"
    )
