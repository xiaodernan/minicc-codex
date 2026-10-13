"""M8-T244: the stored record must keep the tail its own truncation marker promises.

Measured on the main tree before this batch (read-only probes, in-process + AST walks):

    composed render() width, budget-full MCP result: 6049 chars ("MCP srv/big")
    minicc/main.py:109 stored render()[:6000]        -> 49 tail bytes dropped
    len(ToolResult.output) for a 500k-char answer:   0  (the flattener never writes it)
    channel-length bounds in tests/ written as digits: 4

Three coupled failures, all of them a number copied instead of read:

1. ``tests/test_mcp_stdio.py:140`` asserted ``len(result.output) <= 6000`` on the one
   field ``_content_to_tool_result`` (``minicc/mcp.py:67``) never fills, so it was true
   for a server answer of any length; ``:141``/``:142`` and
   ``tests/test_background_shell.py:373`` bounded the same budget with hand-typed
   2000/4000/7000, and ``HEAD_CHARS``/``TAIL_CHARS`` had no mention anywhere in
   ``tests/``.
2. ``minicc/main.py:109`` clipped that composition to 6000 - below the width
   ``render()`` itself produces - and ``/expand`` (``minicc/main.py:154``) prints
   exactly the stored string. What the operator reads still said
   「保留头 2000 + 尾 4000 字符」 while holding 3951 of those tail characters.
3. ``minicc/web.py:1498``/``:1988`` clip at 8000, which only stays honest while the
   summary is under ~1962 chars. The MCP summary is ``f"MCP {server}/{tool}"`` and the
   tool name comes from the server's own ``tools/list``: ``_unique_tool_name`` caps the
   *registry* name at ``minicc/mcp.py:730``, the summary at ``minicc/mcp.py:69`` never
   passes through it.

The fix is ``ToolResult.record_text(ceiling)``: the ceiling governs the raw ``output``
channel, which carries no budget of its own, while a body that came through
``split_output`` is returned whole - re-cutting it would delete bytes the marker
advertises.  No truncation figure and no session-size figure changed.

C1/C2 drive real records, C6 drives a real spawned MCP server; C3/C4/C5/C7 reconcile the
copies against the shipped code, each with a floor so an empty read cannot pose as clean.
"""

from __future__ import annotations

import ast
import sys
from collections import Counter, namedtuple
from pathlib import Path

import pytest

import minicc
import minicc.tools.schemas as schemas_module
from minicc.mcp import McpServerConfig, McpStdioClient
from minicc.main import CliView
from minicc.session import SessionStore
from minicc.tools.schemas import HEAD_CHARS, TAIL_CHARS, TRUNCATION_MARKER, ToolCall, ToolResult

REPO_ROOT = Path(__file__).resolve().parents[1]
MINICC = REPO_ROOT / "minicc"
TESTS = REPO_ROOT / "tests"
MCP_MODULE = MINICC / "mcp.py"
SCHEMAS_MODULE = MINICC / "tools" / "schemas.py"

#: The channels a ToolResult body can be stored through.
CHANNEL_FIELDS = ("head", "tail", "output")

#: A digit this large standing where ``HEAD_CHARS``/``TAIL_CHARS`` should be read is a
#: copy of the shipped budget; smaller numbers are emptiness checks and stay uncharged.
BUDGET_DIGIT_FLOOR = HEAD_CHARS

#: Floors for the four censuses, each far below the population measured in this
#: repository, so a floor only fires when its own census went blind - and the message
#: says which one.
MIN_MCP_CHANNEL_BOUNDS = 1
MIN_CHANNEL_BOUNDS = 4
MIN_STORED_TEXT_CLIPS = 3
MIN_RECORD_OUTPUT_ENTRIES = 1

Bound = namedtuple("Bound", "file lineno hand_typed fields")
Clip = namedtuple("Clip", "file lineno kept kind")
RecordEntry = namedtuple("RecordEntry", "file lineno through_record_text")


def _grading_this_plane() -> None:
    """The censuses read files off disk; they must be the files this run imported."""
    for module, expected in ((minicc.tools.schemas, SCHEMAS_MODULE), (sys.modules["minicc.mcp"], MCP_MODULE)):
        resolved = Path(module.__file__).resolve()
        assert resolved == expected, (
            f"this file grades {expected} but the import resolved to {resolved} - the census would "
            "clear a copy that is not the one in use"
        )


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _minicc_trees() -> list[tuple[Path, ast.Module]]:
    trees = [(path, _tree(path)) for path in sorted(MINICC.rglob("*.py"))]
    assert len(trees) >= 20, f"walking {MINICC} found only {len(trees)} modules - the census read too little"
    return trees


def _func(tree: ast.Module, name: str) -> ast.FunctionDef:
    found = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(found) == 1, f"expected exactly one def {name}(), found {len(found)}"
    return found[0]


def _calls(tree_or_body, attr: str) -> list[ast.Call]:
    """Calls whose callable ends in ``attr`` - either ``x.record_text(...)`` or ``f(...)``."""
    found = []
    for node in ast.walk(tree_or_body):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == attr:
            found.append(node)
        elif isinstance(node.func, ast.Name) and node.func.id == attr:
            found.append(node)
    return found


def _toolresult_fields() -> list[str]:
    tree = _tree(SCHEMAS_MODULE)
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "ToolResult")
    fields = [stmt.target.id for stmt in cls.body if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)]
    assert len(fields) >= len(CHANNEL_FIELDS), f"{SCHEMAS_MODULE} declared only {fields} - the class shape changed"
    return fields


def _flattener_fields() -> set[str]:
    """Which ToolResult fields the MCP flattener actually passes."""
    tree = _tree(MCP_MODULE)
    calls = _calls(_func(tree, "_content_to_tool_result"), "ToolResult")
    assert len(calls) == 1, f"_content_to_tool_result builds {len(calls)} ToolResult objects, expected 1"
    return {keyword.arg for keyword in calls[0].keywords if keyword.arg}


def _is_len_of_channel(node: ast.expr) -> tuple[bool, frozenset[str]]:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len"):
        return False, frozenset()
    fields = frozenset(
        sub.attr
        for arg in node.args
        for sub in ast.walk(arg)
        if isinstance(sub, ast.Attribute) and (sub.attr in CHANNEL_FIELDS or sub.attr == "render")
    )
    return bool(fields), fields


def _channel_bounds(pattern: str) -> list[Bound]:
    """Every test assertion that bounds a ToolResult body channel by length."""
    found: list[Bound] = []
    files = sorted(TESTS.glob(pattern))
    assert files, f"no test file matched {pattern} in {TESTS} - the census read nothing"
    for path in files:
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
                continue
            operands = [node.test.left, *node.test.comparators]
            fields: set[str] = set()
            for operand in operands:
                ok, seen = _is_len_of_channel(operand)
                if ok:
                    fields |= seen
            if not fields:
                continue
            literals = [op.value for op in operands if isinstance(op, ast.Constant) and isinstance(op.value, int)]
            hand = any(abs(value) >= BUDGET_DIGIT_FLOOR for value in literals)
            found.append(Bound(str(path.relative_to(REPO_ROOT)), node.lineno, hand, frozenset(fields)))
    return found


def _composed_minimum() -> int:
    """The width ``render()`` gives a budget-full body with an empty summary."""
    probe = ToolResult(status="ok", summary="", head="h" * HEAD_CHARS, tail="t" * TAIL_CHARS, truncated=True)
    width = len(probe.render())
    assert HEAD_CHARS + TAIL_CHARS < width, f"the probe composition is {width} chars - it does not hold the budget"
    return width


def _reads_render(node: ast.AST) -> bool:
    return any(
        isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "render"
        for call in ast.walk(node)
    )


def _record_text_calls(scope: ast.AST) -> list[ast.Call]:
    return [
        call
        for call in _calls(scope, "record_text")
        if isinstance(call.func, ast.Attribute)
    ]


def _stored_text_clips() -> list[Clip]:
    """Every bound minicc/ puts on a text it composes from the shipped head/tail budget."""
    clips: list[Clip] = []
    for path, tree in _minicc_trees():
        relative = str(path.relative_to(REPO_ROOT))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "record_text":
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, int):
                    clips.append(Clip(relative, node.lineno, int(node.args[0].value), "record_text"))
            elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice) and _reads_render(node.value):
                upper, lower = node.slice.upper, node.slice.lower
                if isinstance(upper, ast.Constant) and isinstance(upper.value, int):
                    clips.append(Clip(relative, node.lineno, int(upper.value), "render slice"))
                elif isinstance(lower, ast.Constant) and isinstance(lower.value, int) and lower.value < 0:
                    clips.append(Clip(relative, node.lineno, -int(lower.value), "render slice"))
    return clips


def _record_output_entries() -> list[RecordEntry]:
    """The dict entries that persist a ToolResult body under the key ``"output"``."""
    entries: list[RecordEntry] = []
    for path, tree in _minicc_trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and key.value == "output"):
                    continue
                routed = _record_text_calls(value)
                if not routed and not _reads_render(value):
                    continue
                entries.append(
                    RecordEntry(str(path.relative_to(REPO_ROOT)), getattr(value, "lineno", node.lineno), bool(routed))
                )
    return entries


def _record_ceilings() -> list[int]:
    return sorted({clip.kept for clip in _stored_text_clips() if clip.kind == "record_text"})


def _budget_full(summary: str = "MCP srv/big") -> ToolResult:
    return ToolResult(status="ok", summary=summary, head="H" * HEAD_CHARS, tail="T" * TAIL_CHARS, truncated=True)


def _stored_cli_record(tmp_path: Path, call: ToolCall, result: ToolResult, name: str) -> tuple[str, str]:
    """Drive the real CLI record path and return (stored output, what /expand prints)."""
    view = CliView(SessionStore(tmp_path, name))
    view.record_tool(call, result)
    stored = CliView(SessionStore(tmp_path, name), announce_resume=True)
    dumped = stored.tool_history[-1]["output"]
    return dumped, stored


# --- C1: the record a user can reopen must hold the bytes its marker advertises -------


def test_the_persisted_record_keeps_the_tail_the_marker_promises(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _grading_this_plane()
    result = _budget_full()
    assert len(result.render()) > HEAD_CHARS + TAIL_CHARS, "the fixture must be wider than the budget it carries"
    stored, view = _stored_cli_record(tmp_path, ToolCall(tool="bash", arguments={"command": "echo big"}), result, "cli-view")
    kept = len(stored) - (len(result.render()) - len(result.tail))
    assert stored.endswith(result.tail), (
        f"the record stored {len(stored)} chars for a result whose body is head({HEAD_CHARS}) + tail({TAIL_CHARS}): "
        f"only {kept} of the {TAIL_CHARS} tail characters the stored text still promises survived the clip"
    )
    capsys.readouterr()  # drop the live print; /expand has to reprint from what is on disk
    view.expand()
    printed = capsys.readouterr().out
    assert TRUNCATION_MARKER in printed, f"/expand reprinted no truncation marker - where did the promise come from?\n{printed[:400]}"
    assert result.head in printed and result.tail in printed, (
        f"/expand prints {len(printed)} chars while the text itself says 「{TRUNCATION_MARKER}」"
    )


# --- C2: the ceiling must survive a name the *server* chose ---------------------------


def test_a_server_chosen_name_cannot_push_the_tail_past_the_clip() -> None:
    ceilings = _record_ceilings()
    assert ceilings, f"no ceiling is passed to record_text() anywhere under {MINICC} - the record surfaces never routed through it"
    ceiling = min(ceilings)
    # The summary is f"MCP {server}/{tool}" and the tool name is whatever the server's
    # tools/list returned; nothing caps its length (mcp.py:69 vs mcp.py:730).
    result = _budget_full("MCP srv/" + "n" * (ceiling - 600))
    composed = result.render()
    assert len(composed) > ceiling, f"fixture too short to test the shipped ceiling {ceiling} (composed {len(composed)})"
    stored = result.record_text(ceiling)
    assert stored.endswith(result.tail), (
        f"record_text({ceiling}) dropped tail bytes from a {len(composed)}-char composition whose marker "
        f"promises {TAIL_CHARS} of them"
    )
    assert TRUNCATION_MARKER in stored, f"record_text() lost the marker: {stored[:200]!r}"
    assert len(composed[:ceiling]) < len(stored), (
        f"the old hand clip [:ceiling] would keep {ceiling} chars; record_text kept {len(stored)} - "
        "the promise-preserving branch is not taking effect"
    )


# --- C3: no MCP test may bound a field the MCP path never writes ---------------------


def test_no_mcp_test_bounds_a_field_the_flattener_never_writes() -> None:
    _grading_this_plane()
    declared = _toolresult_fields()
    written = _flattener_fields()
    unwritten = [field for field in declared if field not in written and field in CHANNEL_FIELDS]
    assert "output" in unwritten, (
        f"_content_to_tool_result now passes output={sorted(written)} - M5-T1's rule is that MCP bodies stay in "
        "the budgeted head/tail channel; if that changed, the tests that bound `output` have to be re-derived"
    )
    bounds = _channel_bounds("test_mcp_*.py")
    assert len(bounds) >= MIN_MCP_CHANNEL_BOUNDS, (
        f"the walk over tests/test_mcp_*.py read {len(bounds)} channel-length bounds - below the floor "
        f"{MIN_MCP_CHANNEL_BOUNDS}, so its silence about {sorted(unwritten)} is not evidence"
    )
    charged = [b for b in bounds if b.fields & set(unwritten)]
    assert not charged, (
        "these assertions bound a ToolResult field the MCP flattener never writes, so they are true for any "
        f"server output: {[(b.file, b.lineno, sorted(b.fields)) for b in charged]}"
    )


# --- C4: the budget must be read from the shipped constants --------------------------


def test_a_truncation_bound_is_read_from_the_shipped_budget() -> None:
    _grading_this_plane()
    bounds = _channel_bounds("*.py")
    assert len(bounds) >= MIN_CHANNEL_BOUNDS, (
        f"the walk over {TESTS} read {len(bounds)} channel-length bounds, below the floor {MIN_CHANNEL_BOUNDS} "
        f"({sorted({b.file for b in bounds})}) - an empty census cannot be reported as a clean one"
    )
    hand = [b for b in bounds if b.hand_typed]
    assert not hand, (
        "these bound the shipped head/tail budget with a digit of their own instead of "
        f"HEAD_CHARS/TAIL_CHARS/TRUNCATION_MARKER: {[(b.file, b.lineno, sorted(b.fields)) for b in hand]}"
    )


# --- C5: no surface may re-clip the composition below its own promise ----------------


def test_no_render_clip_undercuts_the_composition_it_reprints() -> None:
    _grading_this_plane()
    minimum = _composed_minimum()
    clips = _stored_text_clips()
    assert len(clips) >= MIN_STORED_TEXT_CLIPS, (
        f"the walk over {MINICC} found {len(clips)} bounds on a stored/rendered ToolResult body, below the floor "
        f"{MIN_STORED_TEXT_CLIPS} - the census read too little to clear anything"
    )
    # A ceiling handed to record_text() bounds the raw channel and is the caller's own
    # number (C1/C2/C7 judge what it does); a slice cut into render()'s output is the
    # defect this clause charges, because the text it stores still carries the marker.
    too_thin = [clip for clip in clips if clip.kind == "render slice" and clip.kept < minimum]
    assert not too_thin, (
        f"a budget-full composition is {minimum} chars (head+tail+marker, summary not counted); these clips keep "
        f"less than that and still reprint 「{TRUNCATION_MARKER}」: "
        f"{[(clip.file, clip.lineno, clip.kept) for clip in too_thin]}"
    )
    entries = _record_output_entries()
    assert len(entries) >= MIN_RECORD_OUTPUT_ENTRIES, (
        f"the walk found {len(entries)} dict entries storing a ToolResult body under the key 'output', below the "
        f"floor {MIN_RECORD_OUTPUT_ENTRIES} - the wiring census read nothing"
    )
    raw = [entry for entry in entries if not entry.through_record_text]
    assert not raw, (
        f"these record entries clip render() by hand instead of routing through record_text: "
        f"{[(entry.file, entry.lineno) for entry in raw]}"
    )


# --- C6: the shipped seam, byte for byte (the fix must not break this) ---------------

#: Answers tools/call by echoing the text it was handed, so the payload stays owned by
#: this file - no second copy of the byte pattern inside the server.
ECHO_SERVER_SRC = r'''
import json, sys


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
            "serverInfo": {"name": "echopayload", "version": "0"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": "echo_text", "description": "answer with the text it was handed"}]}})
    elif method == "tools/call":
        text = str(((msg.get("params") or {}).get("arguments") or {}).get("text", ""))
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": text}], "isError": False}})
    elif mid is not None:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "unknown"}})
'''


def test_the_stdio_seam_keeps_exactly_the_budget_and_the_right_bytes(tmp_path: Path) -> None:
    _grading_this_plane()
    payload = ("mcp-t244-seed-" * 600)[: HEAD_CHARS + TAIL_CHARS + 137]
    assert len(payload) > HEAD_CHARS + TAIL_CHARS and not payload[-1].isspace()
    server = tmp_path / "echo_payload_server.py"
    server.write_text(ECHO_SERVER_SRC, encoding="utf-8")
    config = McpServerConfig(name="seam", command=sys.executable, args=(str(server),))
    client = McpStdioClient(config, tmp_path)
    try:
        result = client.call_tool("echo_text", {"text": payload})
    finally:
        client.close()
    assert result.truncated is True, f"a {len(payload)}-char answer came back untruncated"
    assert result.output == "", (
        f"the MCP flattener put {len(result.output)} chars into the raw output channel as well; render() prefers "
        "head/tail, so those bytes reach nothing and every bound on them is void"
    )
    assert result.head == payload[:HEAD_CHARS], "the head channel does not hold the first HEAD_CHARS bytes"
    assert result.tail == payload[-TAIL_CHARS:], (
        f"the tail channel holds {result.tail[:20]!r}…, expected {payload[-TAIL_CHARS:][:20]!r}… - not the last "
        f"TAIL_CHARS bytes of what the server answered"
    )
    assert result.render() == f"{result.summary}\n{result.head}\n\n{TRUNCATION_MARKER}\n\n{result.tail}", (
        "render() no longer composes summary + head + marker + tail, so the widths this file derives from it "
        "are measuring a different text"
    )


# --- C7: the ceiling still governs the channel that has no budget --------------------


def test_a_record_surface_gets_the_ceiling_it_passes(tmp_path: Path) -> None:
    _grading_this_plane()
    ceilings = _record_ceilings()
    assert ceilings, f"no literal ceiling reaches record_text() under {MINICC}; the record surfaces are unbounded"
    ceiling = min(ceilings)
    raw = ToolResult(status="ok", summary="raw", output="x" * (ceiling * 2 + 7))
    assert raw.head == "" and raw.truncated is False, "the raw-output channel is no longer the unbounded one"
    stored, _ = _stored_cli_record(tmp_path, ToolCall(tool="bash", arguments={"command": "echo raw"}), raw, "cli-view-raw")
    assert len(stored) == ceiling, (
        f"a body that came through no budget was stored as {len(stored)} chars while the shipped ceiling is "
        f"{ceiling} (ceilings in use: {ceilings})"
    )
    assert stored == raw.render()[:ceiling], "the clipped raw channel is not the prefix the ceiling describes"
