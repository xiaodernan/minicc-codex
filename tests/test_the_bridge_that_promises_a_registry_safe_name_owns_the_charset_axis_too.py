"""M8-T263: a bridge that promises a registry-safe name has to own the charset axis too.

Measured before this file was written (Temp/mc-t260/probe1_t263.py, in-process, no child):
``McpManager._unique_tool_name`` owned the *length* axis and nothing else, so 5 of 8 tool
names spelled the way real servers spell them (``read file``, ``tool/sub``, ``get:resource``,
``lookup#1``, ``工具查询``) and 4 of 6 server keys a user can type into ``.minicc/mcp.json``
(``我的服务``, ``my server``, ``srv:v1``, ``srv/sub``) reached ``ToolRegistry.register`` with
their illegal characters intact and were refused by ``_TOOL_NAME_RE``.  ``build_registry``
(minicc/tools/__init__.py:194-195) registers MCP specs with no containment, so the measured
blast radius of one refused name was the whole shipped toolset - 0 of 23 callable tools,
plus the two well-named MCP tools beside it.

These gates pin the fix (the bridge folds disallowed characters to ``_`` and keeps the RAW
name in the disambiguating digest) and pin the two axes that must not move: a name that was
already legal stays byte-identical, and the length/collision axis keeps behaving the way
M5-T4 left it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from minicc import mcp as mcp_module
from minicc.mcp import McpManager
from minicc.tools import Editor, build_registry
from minicc.tools.registry import (
    ToolRegistry,
    ToolSpec,
    validate_tool_spec,
)

# The shapes the probe fed the shipped helper. A space, a slash, a colon, a hash and a CJK
# name are things tool authors publish; none of them is a hypothetical.
PATHOLOGICAL_TOOL_NAMES = {
    "space": "read file",
    "slash": "tool/sub",
    "colon": "get:resource",
    "hash": "lookup#1",
    "cjk": "工具查询",
    "legal_body_chars": "ok.name-1_2~3",
    "leading_tilde": "~lead",
    "over_length": "x" * 200,
}

PATHOLOGICAL_SERVER_KEYS = {
    "ascii": "srv",
    "cjk": "我的服务",
    "space": "my server",
    "colon": "srv:v1",
    "slash": "srv/sub",
    "long_but_legal": "a" * 70,
}

# One character at a time, from everything a JSON string can carry. The control clause below
# proves each of these is really refused when it reaches the registry unfolded, so the sweep
# that uses them cannot pass by sweeping nothing interesting.
UNSAFE_CHARS = [
    " ", "/", ":", "#", "?", "!", "@", "%", "&", "*", "(", ")", "[", "]", "{", "}",
    "<", ">", "|", "\\", '"', "'", ",", ";", "=", "+", "$", "^", "`", "\n", "\t",
    "中", "é", "🔥",
]

PATHOLOGICAL = "查询 数据"


def _name_for_probe(tool: str, server: str = "srv") -> str:
    """Ask the shipped helper what it hands the registry - nothing else builds the name."""
    return McpManager._unique_tool_name(server, tool, set())


def _spec(name: str) -> ToolSpec:
    # ToolSpec.handler is a required field (registry.py:195); leaving it out would raise
    # TypeError before the name check this unit is about, and the arm would measure a crash.
    return ToolSpec(name, "probe description", "readonly", (), lambda args: None)


def _refusal(name: str) -> str:
    """The registry's own verdict on this name, as a string when it refuses."""
    try:
        validate_tool_spec(_spec(name))
    except ValueError as exc:  # ToolRegistrationError is a ValueError
        return str(exc)
    return ""


def _name_cap() -> int:
    """The longest name the registry takes, read out of its own verdicts.

    Derived rather than imported because the length ceiling is not a named thing in the
    version of the registry this unit's reverse control grades, and a door that cannot load
    on the bytes it is meant to refute measures nothing at all.  Every character here is a
    letter, so a refusal can only come from the length.
    """
    accepted = [length for length in range(1, 400) if _refusal("m" + "x" * (length - 1)) == ""]
    assert accepted, "the registry refused every all-letter name - the derivation read nothing"
    return max(accepted)


def test_the_shapes_a_real_server_names_its_tools_with_are_accepted():
    refused = []
    registry = ToolRegistry()
    registry.declare_builtin()
    for label, raw in PATHOLOGICAL_TOOL_NAMES.items():
        name = _name_for_probe(raw)
        message = _refusal(name)
        if message:
            refused.append(f"{label}: {raw!r} -> {name!r} {message}")
            continue
        registry.register(_spec(name))
    assert refused == [], (
        f"the bridge still hands the registry {len(refused)} of "
        f"{len(PATHOLOGICAL_TOOL_NAMES)} names it refuses:\n" + "\n".join(refused)
    )
    assert len(registry.names()) == len(PATHOLOGICAL_TOOL_NAMES), (
        f"only {len(registry.names())} of {len(PATHOLOGICAL_TOOL_NAMES)} probe shapes became "
        f"callable tools: {registry.names()}"
    )
    assert all(n.startswith("mcp__") for n in registry.names()), registry.names()


def test_no_name_the_bridge_can_build_is_refused_by_the_registry():
    swept = 0
    refused = []
    for char in UNSAFE_CHARS:
        for server, tool in ((f"a{char}b", "search"), ("srv", f"a{char}b")):
            swept += 1
            name = _name_for_probe(tool, server)
            message = _refusal(name)
            if message:
                refused.append(f"server={server!r} tool={tool!r} -> {name!r} {message}")
    assert swept == 2 * len(UNSAFE_CHARS), f"the sweep reached {swept} names, expected {2 * len(UNSAFE_CHARS)}"
    # Control: the same characters, placed into a name by hand, must be refused. If this
    # fails the sweep is measuring an empty set of interesting inputs and proves nothing.
    accepted_any = [c for c in UNSAFE_CHARS if not _refusal(f"mcp__srv__a{c}b")]
    assert accepted_any == [], (
        f"the sweep's characters are not all refused by the registry, so the control below "
        f"is not a control: {accepted_any}"
    )
    assert refused == [], f"{len(refused)} of {swept} swept names were refused:\n" + "\n".join(refused[:8])


def test_two_names_that_clean_to_the_same_spelling_stay_two_tools():
    taken: set[str] = set()
    first = McpManager._unique_tool_name("srv", "read file", taken)
    second = McpManager._unique_tool_name("srv", "read_file", taken)
    assert first != second, f"cleaning merged two published tools into {first!r}"
    assert _refusal(first) == "", f"{first!r} refused: {_refusal(first)}"
    assert _refusal(second) == "", f"{second!r} refused: {_refusal(second)}"
    assert max(len(first), len(second)) <= _name_cap(), (len(first), len(second))
    registry = ToolRegistry()
    registry.declare_builtin()
    registry.register(_spec(first))
    registry.register(_spec(second))
    assert len(registry.names()) == 2, registry.names()


def test_cleaning_never_renames_a_name_that_was_already_legal():
    churned = []
    for server in ("srv", "docs", "a-b", "a_b", "a.b", "a~b"):
        for tool in ("search", "read_file", "ok.name-1_2~3", "list2"):
            expected = f"mcp__{server}__{tool}"
            produced = _name_for_probe(tool, server)
            if produced != expected:
                churned.append(f"{server!r}/{tool!r}: {expected!r} -> {produced!r}")
    assert churned == [], f"the fix renamed {len(churned)} legal names:\n" + "\n".join(churned)


def test_the_server_half_of_the_name_is_cleaned_the_same_way():
    refused = []
    for label, server in PATHOLOGICAL_SERVER_KEYS.items():
        name = _name_for_probe("search", server)
        message = _refusal(name)
        if message:
            refused.append(f"{label}: {server!r} -> {name!r} {message}")
    assert refused == [], (
        f"the server half still carries illegal characters in {len(refused)} of "
        f"{len(PATHOLOGICAL_SERVER_KEYS)} keys:\n" + "\n".join(refused)
    )
    taken: set[str] = set()
    spaced = McpManager._unique_tool_name("my server", "search", taken)
    underscored = McpManager._unique_tool_name("my_server", "search", taken)
    assert spaced != underscored, f"two configured servers merged into {spaced!r}"
    assert _refusal(spaced) == "" and _refusal(underscored) == ""
    assert all(n.startswith("mcp__") for n in (spaced, underscored)), (spaced, underscored)


def test_the_length_axis_keeps_the_hash_disambiguation_it_already_owned():
    cap = _name_cap()
    # A ceiling only means something if the name one character past it is refused; without
    # this the derivation in _name_cap could be reading a registry that takes everything.
    assert _refusal("m" + "x" * cap) != "", f"a {cap + 1}-character all-letter name was accepted"
    shared_prefix = "y" * (cap - len("mcp__srv__"))
    taken: set[str] = set()
    alpha = McpManager._unique_tool_name("srv", shared_prefix + "_alpha", taken)
    beta = McpManager._unique_tool_name("srv", shared_prefix + "_beta", taken)
    assert alpha != beta, f"two long names collapsed onto {alpha!r}"
    assert max(len(alpha), len(beta)) <= cap, (len(alpha), len(beta))
    assert _refusal(alpha) == "" and _refusal(beta) == ""
    plain = McpManager._unique_tool_name("srv", "plain", set())
    assert plain == "mcp__srv__plain", f"a short legal name gained a suffix: {plain!r}"


def test_cleaning_a_cleaned_name_changes_nothing():
    unstable = []
    for label, value in list(PATHOLOGICAL_TOOL_NAMES.items()) + list(PATHOLOGICAL_SERVER_KEYS.items()):
        once = mcp_module.registry_safe(value)
        twice = mcp_module.registry_safe(once)
        if once != twice:
            unstable.append(f"registry_safe({label}={value!r}) is not a fixed point: {once!r} -> {twice!r}")
    assert unstable == [], "\n".join(unstable)
    # The fold has one reader: ``_unique_tool_name``.  Feeding that helper its own output
    # must name the same tool, or the clean name the model sees and the raw name the server
    # published would drift apart on a second pass through the bridge.
    shifted = []
    for label, raw in PATHOLOGICAL_TOOL_NAMES.items():
        once = _name_for_probe(raw)
        twice = _name_for_probe(mcp_module.registry_safe(raw))
        if once != twice:
            shifted.append(f"{label}: {raw!r} -> {once!r} -> {twice!r}")
    assert shifted == [], (
        f"the bridge renamed {len(shifted)} of {len(PATHOLOGICAL_TOOL_NAMES)} tools when fed "
        f"an already-folded name:\n" + "\n".join(shifted)
    )


ECHO_SERVER_SRC = r'''
import json, sys

spec = json.load(open(sys.argv[1], encoding="utf-8"))
tools = spec.get("tools", [])
known = {t.get("name") for t in tools}

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
    reply = None
    if method == "initialize":
        reply = {"protocolVersion": "2024-11-05", "capabilities": {},
                 "serverInfo": {"name": "fake", "version": "0"}}
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        reply = {"tools": tools}
    elif method == "tools/call":
        asked = (msg.get("params") or {}).get("name")
        text = asked if asked in known else "UNKNOWN:%s" % asked
        reply = {"content": [{"type": "text", "text": text}], "isError": False}
    if mid is None:
        continue
    if reply is None:
        out = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "unknown"}}
    else:
        out = {"jsonrpc": "2.0", "id": mid, "result": reply}
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()
'''


@pytest.fixture()
def mcp_workspace(tmp_path: Path) -> Path:
    server = tmp_path / "echo_mcp_server.py"
    server.write_text(ECHO_SERVER_SRC, encoding="utf-8")
    spec_path = tmp_path / "spec_echo.json"
    spec_path.write_text(
        json.dumps({"tools": [{"name": PATHOLOGICAL}, {"name": "plain_tool"}]},
                   ensure_ascii=True),
        encoding="utf-8",
    )
    (tmp_path / ".minicc").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".minicc" / "mcp.json").write_text(
        json.dumps({"servers": {"srv": {
            "command": sys.executable,
            "args": [str(server), str(spec_path)],
            "read_only": True,
        }}}),
        encoding="utf-8",
    )
    return tmp_path


def test_the_name_the_model_is_offered_is_the_name_the_registry_holds(mcp_workspace):
    manager = McpManager(mcp_workspace)
    try:
        specs = {s.name: s for s in manager.tool_specs()}
        target = next((n for n, s in specs.items() if s.description.endswith(PATHOLOGICAL)), None)
        assert target is not None, (
            f"the server published {PATHOLOGICAL!r} but no spec carries it: "
            f"{sorted(s.description for s in specs.values())}"
        )
        assert _refusal(target) == "", f"the seam still offers the registry {target!r}: {_refusal(target)}"
        assert target != PATHOLOGICAL and " " not in target, target
        offered = specs[target].openai_schema()["function"]["name"]
        assert offered == target, (
            f"the model is offered {offered!r} while the registry would hold {target!r}: a name "
            f"that exists only in one of the two views is a tool that cannot be called"
        )
        # The child has to still be alive for this to be a call, so the manager closes only
        # after the handler has run.
        result = specs[target].handler({})
    finally:
        manager.close()
    assert result.summary == f"MCP srv/{PATHOLOGICAL}", (
        f"the record says {result.summary!r} while the model called {target!r}: a cleaned "
        f"name must not retarget the call away from the server's own tool"
    )
    # The child echoes the name it RECEIVED, so the label alone is not the evidence.
    assert PATHOLOGICAL in result.render(), result.render()
    assert list(result.security_tags) == ["untrusted", "mcp"], result.security_tags


def test_the_shipped_build_registry_keeps_all_23_builtins_when_a_server_names_a_tool_with_a_space(mcp_workspace):
    reference = build_registry(Editor(mcp_workspace))
    expected = reference.names()
    assert expected, "a build with no bridge produced no tools; the comparison would be vacuous"
    manager = McpManager(mcp_workspace)
    try:
        registry = build_registry(Editor(mcp_workspace), mcp_manager=manager)
    except Exception as exc:
        raise AssertionError(
            f"one MCP tool name cost the session its whole toolset: build_registry raised "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    finally:
        manager.close()
    missing = [n for n in expected if n not in registry.names()]
    assert missing == [], (
        f"one MCP tool name cost the session {len(missing)} of {len(expected)} shipped "
        f"builtins: {missing}"
    )
    mcp_names = [n for n in registry.names() if n.startswith("mcp__")]
    assert len(mcp_names) == 2, (
        f"the server published 2 tools and the registry holds {mcp_names}: a name the "
        f"registry refuses is a tool that silently disappeared"
    )
    assert all(_refusal(n) == "" for n in mcp_names), mcp_names
    assert len(registry.names()) == len(expected) + 2, (len(expected), len(mcp_names))
