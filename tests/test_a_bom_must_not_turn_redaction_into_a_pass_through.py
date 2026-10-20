"""M8-T268: a BOM must not turn redaction into a pass-through.

``.minicc/mcp.json`` holds the MCP servers' ``headers`` - and an
``Authorization: Bearer …`` among them.  ``_redact_mcp_headers`` parsed the
file and, when the parse failed, returned the text **unchanged**.  A UTF-8
BOM made the parse fail, and a BOM is what PowerShell's ``Out-File`` and the
notepad default write.  So on a very ordinary Windows file the whole config,
credentials included, went into the model context.

The redaction now strips the BOM before parsing, and a file that still will
not parse is refused rather than passed through: a shape we cannot read is a
shape whose header values we cannot identify.

This door pins:

* a BOM-prefixed config is redacted, not leaked;
* an unparseable config is refused, not passed through;
* a config without a BOM keeps working (the control);
* ``load_mcp_config`` tolerates a BOM instead of failing to load.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minicc.mcp import McpError, load_mcp_config
from minicc.tools.editor import Editor
from minicc.tools.fs import FsTools

SECRET = "Bearer sk-mcp-test-token"
CONFIG = {
    "servers": {
        "docs": {
            "command": "node",
            "args": ["server.js"],
            "headers": {"Authorization": SECRET, "X-Api-Key": "another-secret"},
        }
    }
}


def _workspace(tmp_path: Path, *, bom: bool) -> Path:
    workspace = tmp_path / "ws"
    (workspace / ".minicc").mkdir(parents=True)
    body = json.dumps(CONFIG, ensure_ascii=False, indent=2)
    encoding = "utf-8-sig" if bom else "utf-8"
    (workspace / ".minicc" / "mcp.json").write_text(body, encoding=encoding)
    return workspace


def _read(workspace: Path) -> str:
    tools = FsTools(Editor(workspace))
    result = tools.read_file({"path": ".minicc/mcp.json"})
    return (result.head or "") + (result.tail or "")


def test_a_bom_prefixed_config_is_redacted_not_leaked(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, bom=True)
    body = _read(workspace)
    assert SECRET not in body, "the Authorization header reached the model context"
    assert "another-secret" not in body, "the api key reached the model context"
    assert "REDACTED" in body


def test_an_unparseable_config_is_refused_not_passed_through(tmp_path: Path) -> None:
    """The old fallback returned the text unchanged - the leak."""
    workspace = tmp_path / "ws"
    (workspace / ".minicc").mkdir(parents=True)
    (workspace / ".minicc" / "mcp.json").write_text(
        '{"servers": {"docs": {"headers": {"Authorization": "' + SECRET + '"}}}',
        encoding="utf-8",
    )
    tools = FsTools(Editor(workspace))
    with pytest.raises(Exception) as excinfo:
        tools.read_file({"path": ".minicc/mcp.json"})
    assert SECRET not in str(excinfo.value), "the refused content came back in the error"


def test_a_config_without_a_bom_still_works(tmp_path: Path) -> None:
    """The control: the ordinary file is unaffected."""
    workspace = _workspace(tmp_path, bom=False)
    body = _read(workspace)
    assert SECRET not in body
    assert "REDACTED" in body


def test_loading_the_config_tolerates_a_bom(tmp_path: Path) -> None:
    """The MCP bridge itself must still be able to read the file."""
    workspace = _workspace(tmp_path, bom=True)
    configs = load_mcp_config(workspace)
    assert len(configs) == 1
    assert configs[0].name == "docs"


def test_loading_a_config_without_a_bom_still_works(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, bom=False)
    configs = load_mcp_config(workspace)
    assert len(configs) == 1


def test_a_malformed_config_still_raises_an_mcp_error(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / ".minicc").mkdir(parents=True)
    (workspace / ".minicc" / "mcp.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(McpError):
        load_mcp_config(workspace)
