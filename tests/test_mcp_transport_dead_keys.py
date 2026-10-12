"""M8-T242: a key the server's own transport never consults must say so at load time.

Measured on the main tree at ``32c0fd7`` (2026-10-13) before this batch landed, by
loading real ``.minicc/mcp.json`` files and capturing every record the
``minicc.mcp`` logger emitted:

    {"command": "echo", "headers": {"X-A": "1"}}        -> 0 warnings, card keeps headers
    {"url": U, "command": "echo", "args": ["-x"], "env": {"K": "V"}} -> 0 warnings
    {"command": "echo", "url": U}                      -> 0 warnings, transport="http"
    {"command": "echo", "commnd": "echo"}              -> WARNING 「键 'commnd' 不会被读取」

The last line is M8-T145's report, and it works. The first three are the hole it
left: ``RECOGNIZED_KEYS`` asks only *whether a key exists*, never *which transport
reads it*, so keys the other transport alone consults were stored on the card,
read by nobody, and announced as nothing. ``minicc/mcp.py`` class bodies confirm
the split - ``McpStdioClient`` reads ``command``/``args``/``env``,
``McpHttpClient`` reads ``url``/``headers`` - so an operator who wrote an
``Authorization`` header onto a stdio server believed the request carried it, and
an operator who left ``command`` beside a ``url`` believed a subprocess started.

This batch makes one table (``TRANSPORT_HANDLERS``) the single owner of both the
dispatch and the report, and the census below is what keeps the table honest: a
declared read-set that disagrees with what the class body actually reads goes red
even when every behaviour case stays green.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import logging
from pathlib import Path

from minicc import mcp as mcp_module
from minicc.mcp import McpServerConfig, load_mcp_config

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_MODULE = REPO_ROOT / "minicc" / "mcp.py"

#: The URL is only ever a claim here - nothing connects during loading.
HTTP_URL = "http://mcp.invalid.:1/mcp"
PRIVATE_ENV = "MINICC_ALLOW_PRIVATE_MCP"


def _workspace(tmp_path: Path, name: str, entry: dict[str, object]) -> Path:
    workspace = tmp_path / name
    (workspace / ".minicc").mkdir(parents=True, exist_ok=True)
    (workspace / ".minicc" / "mcp.json").write_text(
        json.dumps({"servers": {name: entry}}, ensure_ascii=False), encoding="utf-8"
    )
    return workspace


def _dead_key_warnings(tmp_path: Path, entry: dict[str, object], monkeypatch) -> list[str]:
    """Load one server entry and return the transport-dead-key warnings it drew."""
    monkeypatch.setenv(PRIVATE_ENV, "1")
    captured: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.name == "minicc.mcp" and "传输下不会被读取" in record.getMessage():
                captured.append(record.getMessage())

    log = logging.getLogger("minicc.mcp")
    handler = Capture()
    previous_level = log.level
    log.addHandler(handler)
    log.setLevel(logging.WARNING)
    try:
        load_mcp_config(_workspace(tmp_path, "srv", entry))
    finally:
        log.removeHandler(handler)
        log.setLevel(previous_level)
    return captured


def _all_records(tmp_path: Path, entry: dict[str, object], monkeypatch) -> list[str]:
    monkeypatch.setenv(PRIVATE_ENV, "1")
    captured: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.name == "minicc.mcp":
                captured.append(record.getMessage())

    log = logging.getLogger("minicc.mcp")
    handler = Capture()
    previous_level = log.level
    log.addHandler(handler)
    log.setLevel(logging.WARNING)
    try:
        load_mcp_config(_workspace(tmp_path, "srv", entry))
    finally:
        log.removeHandler(handler)
        log.setLevel(previous_level)
    return captured


def test_a_stdio_entry_that_writes_headers_names_the_header_as_not_read(tmp_path: Path, monkeypatch) -> None:
    """D1: ``headers`` on a stdio server is stored and never sent - it must not be silent."""
    warnings = _dead_key_warnings(tmp_path, {"command": "echo", "headers": {"Authorization": "Bearer x"}}, monkeypatch)
    assert warnings == ["MCP server 'srv' 的键 'headers' 在 stdio 传输下不会被读取（只有 http 传输会读它）"], (
        f"a stdio entry carrying headers drew {warnings}; it must draw exactly one warning naming headers"
    )


def test_an_http_entry_that_writes_command_args_env_names_all_three(tmp_path: Path, monkeypatch) -> None:
    """D2: an HTTP server's stdio keys are the same hole mirrored - one line per key."""
    warnings = _dead_key_warnings(
        tmp_path,
        {"url": HTTP_URL, "command": "echo", "args": ["-x"], "env": {"K": "V"}},
        monkeypatch,
    )
    keys = [w.split("的键 '")[1].split("'")[0] for w in warnings]
    assert keys == ["args", "command", "env"], (
        f"an http entry carrying command/args/env drew {warnings}; expected one line per dead key, sorted"
    )
    assert all("在 http 传输下不会被读取" in w for w in warnings), f"warnings must name the transport in force: {warnings}"


def test_an_entry_with_both_command_and_url_reports_the_dropped_command(tmp_path: Path, monkeypatch) -> None:
    """D3: ``url`` still wins the transport - this batch only takes the silence away."""
    monkeypatch.setenv(PRIVATE_ENV, "1")
    workspace = _workspace(tmp_path, "both", {"command": "server.py", "url": HTTP_URL})
    captured: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.name == "minicc.mcp":
                captured.append(record.getMessage())

    log = logging.getLogger("minicc.mcp")
    handler = Capture()
    previous_level = log.level
    log.addHandler(handler)
    log.setLevel(logging.WARNING)
    try:
        configs = load_mcp_config(workspace)
    finally:
        log.removeHandler(handler)
        log.setLevel(previous_level)

    assert configs[0].transport == "http", f"the transport verdict changed: {configs[0].transport}"
    assert configs[0].command == "server.py", f"the card must still carry what was written: {configs[0]!r}"
    assert any("'command'" in m and "不会被读取" in m for m in captured), (
        f"command was dropped by the transport with no warning among {captured}"
    )


def test_a_clean_entry_for_each_transport_stays_silent(tmp_path: Path, monkeypatch) -> None:
    """Anti-vacuity: the report must speak about dead keys only.

    Three shapes an operator writes on purpose: a full stdio entry, a full HTTP
    entry, and stdio with an explicitly empty ``url`` (M8-T145 pins that empty URL
    means stdio mode). A report that also fired on these would prove nothing about
    the first three cases.
    """
    for name, entry in (
        ("stdio-full", {"command": "echo", "args": ["-m", "srv"], "env": {"K": "V"}, "read_only": True}),
        ("http-full", {"url": HTTP_URL, "headers": {"Authorization": "Bearer x"}}),
        ("stdio-empty-url", {"command": "echo", "url": "", "headers": {}}),
    ):
        records = _all_records(tmp_path / name, entry, monkeypatch)
        assert records == [], f"{name} is a live shape and must draw no warning, got {records}"


def test_the_m8_t145_typo_warning_still_fires(tmp_path: Path, monkeypatch) -> None:
    """The repair must not eat the report that already worked."""
    monkeypatch.setenv(PRIVATE_ENV, "1")
    records = _all_records(tmp_path / "typo", {"command": "echo", "commnd": "echo"}, monkeypatch)
    assert len(records) == 1, f"a misspelled command drew {len(records)} records, expected 1: {records}"
    assert "不会被读取" in records[0] and "是否想写 'command'" in records[0], records[0]


def _class_node(tree: ast.Module, name: str) -> ast.ClassDef:
    node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name), None)
    assert node is not None, f"no class {name} at module level in {MCP_MODULE}"
    return node


def _config_field_reads(class_node: ast.ClassDef, fields: set[str]) -> set[str]:
    """Attribute names read as ``self.config.X`` / ``config.X`` anywhere inside the class."""
    hits: set[str] = set()
    for node in ast.walk(class_node):
        if isinstance(node, ast.Attribute) and node.attr in fields:
            base_parts = ast.unparse(node.value).split(".")
            if base_parts[-1] == "config":
                hits.add(node.attr)
    return hits


def test_the_report_and_the_dispatch_read_one_table_the_ast_confirms() -> None:
    """D4/D5: the table is the single owner, and the AST audits every row of it.

    Every set here is derived: the field population from
    ``dataclasses.fields(McpServerConfig)``, the transport names from the literal
    returns of ``McpServerConfig.transport``, the reader population from the keys
    ``load_mcp_config`` actually takes off the JSON. A declaration that lies, a
    transport that gains a client nobody reports on, and a key the loader reads
    that no transport claims all go red here.
    """
    assert Path(mcp_module.__file__).resolve() == MCP_MODULE.resolve(), (
        f"this census reads {MCP_MODULE}, but the import resolved to {mcp_module.__file__}"
    )
    tree = ast.parse(MCP_MODULE.read_text(encoding="utf-8"))
    fields = {field.name for field in dataclasses.fields(McpServerConfig)}
    table = mcp_module.TRANSPORT_HANDLERS

    assert len(table) >= 2, f"the census over TRANSPORT_HANDLERS would be vacuous at {len(table)} rows"

    # (a) each declared read-set equals what that class body actually reads.
    for transport, (client, declared) in table.items():
        read = _config_field_reads(_class_node(tree, client.__name__), fields)
        assert read - {"name"} == set(declared), (
            f"{transport} declares it reads {sorted(declared)} but {client.__name__}'s body reads "
            f"{sorted(read)} (ignoring name, which is the entry's key, not a JSON field)"
        )
        assert declared, f"{transport} declared an empty read-set - the report would call every key dead"

    # ``name`` and ``read_only`` are deliberately outside the per-transport sets;
    # pin why, so the exclusions above are not hiding places.
    for transport, (client, _) in table.items():
        read = _config_field_reads(_class_node(tree, client.__name__), fields)
        assert "name" in read, f"{client.__name__} does not read config.name, so excluding it above was a guess"
    assert "read_only" not in set().union(*(set(keys) for _, keys in table.values())), (
        "read_only is the manager-level risk string, not a transport key - claiming it would make "
        "one transport report the other's decision as dead"
    )

    # (b) the table's rows are exactly what ``transport`` can answer.
    transport_property = _class_node(tree, "McpServerConfig")
    literals = {
        sub.value
        for node in ast.walk(transport_property)
        if isinstance(node, ast.Return)
        for sub in ast.walk(node)
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
    }
    assert literals == set(table), (
        f"McpServerConfig.transport can return {sorted(literals)} but TRANSPORT_HANDLERS covers "
        f"{sorted(table)} - a transport with no row dispatches to nothing and reports nothing"
    )

    # (c) every key the loader reads is owned by some transport (except read_only).
    loader = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "load_mcp_config"), None)
    assert loader is not None, f"no def load_mcp_config at module level in {MCP_MODULE}"
    reads: set[str] = set()
    for node in ast.walk(loader):
        if isinstance(node, ast.Call):
            base = ast.unparse(node.func)
            if base == "value.get" and node.args and isinstance(node.args[0], ast.Constant):
                reads.add(node.args[0].value)
            elif base.startswith("_config_"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        reads.add(arg.value)
    assert reads, f"the census of {MCP_MODULE} saw no JSON keys at all - it checked nothing"
    claimed = set().union(*(set(keys) for _, keys in table.values()))
    assert (reads - {"read_only"}) == claimed, (
        f"load_mcp_config reads {sorted(reads)}; the transports claim {sorted(claimed)} - "
        f"unowned {sorted(reads - claimed - {'read_only'})}, claimed-but-never-read {sorted(claimed - reads)}"
    )

    # (d) the dispatch and the report both consult the table, not their own copies.
    dispatch = next(n for n in ast.walk(_class_node(tree, "McpManager"))
                    if isinstance(n, ast.FunctionDef) and n.name == "_client")
    dispatch_source = ast.unparse(dispatch)
    assert "TRANSPORT_HANDLERS" in dispatch_source, "McpManager._client no longer dispatches through the table"
    hardcoded = [
        ast.unparse(node)
        for node in ast.walk(dispatch)
        if isinstance(node, ast.Compare)
        and any(isinstance(c, ast.Constant) and c.value in literals for c in [node.left, *node.comparators])
    ]
    assert not hardcoded, f"_client still branches on a transport literal instead of the table: {hardcoded}"
    reporter = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name == "_report_keys_this_transport_never_reads"), None)
    assert reporter is not None, "no module-level reporter function - the report has no owner"
    assert "TRANSPORT_HANDLERS" in ast.unparse(reporter), "the reporter does not read the table"
    called = [ast.unparse(node.func) for node in ast.walk(loader) if isinstance(node, ast.Call)]
    assert "_report_keys_this_transport_never_reads" in called, (
        f"load_mcp_config never calls the reporter, so the shipped path cannot produce the warning: {called}"
    )
