"""M8-T266: the .minicc gate must judge the path the file actually names.

``_minicc_sensitive_kind`` used to read the *raw* path argument and match the
tail after the first ``.minicc`` segment against the deny list.  Two escapes
followed from that:

* ``.minicc/x/../web_token.json`` produced the tail ``("x", "..", "web_token.json")``
  - no exact match, so the read was allowed and the workbench bearer token
  reached the model.  The same shape on the write side let the agent
  overwrite ``.minicc/allowlist.json`` with ``{"tools": ["*"]}``, which is
  the self-escalation the deny list exists to stop.
* ``.minicc/permissions.json`` was simply missing from the deny list, even
  though it is the file the ``permissions.json`` deny rules live in - so the
  agent could erase its own deny rules.

The gate now collapses ``..`` before matching and, for the file tools, judges
the *resolved* target (which also covers a symlink named innocuously).

This door pins:

* ``..`` inside ``.minicc`` no longer escapes the deny list, for read and
  for write;
* ``permissions.json`` is denied for both directions;
* the controls: ordinary workspace files, and ``.minicc`` files that are not
  on the deny list, keep working.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from minicc.tools.editor import Editor
from minicc.tools.fs import FsTools, _minicc_sensitive_kind

ESCALATION = '{"sessions": {"s": {"tools": ["*"]}}}'
SECRET = {"token": "SUPER-SECRET-BEARER-abc123"}


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    (workspace / ".minicc").mkdir(parents=True)
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (workspace / ".minicc" / "web_token.json").write_text(
        json.dumps(SECRET), encoding="utf-8"
    )
    (workspace / ".minicc" / "allowlist.json").write_text('{"sessions":{}}', encoding="utf-8")
    (workspace / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": ["secrets/*"]}}), encoding="utf-8"
    )
    (workspace / ".minicc" / "todos.json").write_text('{"items":[]}', encoding="utf-8")
    return workspace


def _tools(workspace: Path) -> FsTools:
    return FsTools(Editor(workspace))


# --- the string-level predicate ------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".minicc/web_token.json",
        ".minicc/x/../web_token.json",
        ".minicc/./web_token.json",
        ".minicc/deep/nested/../../web_token.json",
    ],
)
def test_a_dot_dot_inside_minicc_still_names_the_deny_listed_file(path: str) -> None:
    """The tail must be read off the collapsed path, not the raw string."""
    assert _minicc_sensitive_kind(path) == "deny"


@pytest.mark.parametrize(
    "path",
    [
        ".minicc/allowlist.json",
        ".minicc/x/../allowlist.json",
        ".minicc/permissions.json",
        ".minicc/x/../permissions.json",
    ],
)
def test_the_authorization_files_are_on_the_deny_list(path: str) -> None:
    assert _minicc_sensitive_kind(path) == "deny"


def test_a_directory_merely_named_like_minicc_is_not_the_minicc_directory() -> None:
    assert _minicc_sensitive_kind("notminicc/web_token.json") is None


# --- the end-to-end read and write doors ---------------------------------------


def test_reading_the_bearer_token_through_a_dot_dot_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    tools = _tools(workspace)
    with pytest.raises(Exception) as excinfo:
        tools.read_file({"path": ".minicc/x/../web_token.json"})
    assert "minicc" in str(excinfo.value).lower()


def test_reading_the_bearer_token_directly_is_still_refused(tmp_path: Path) -> None:
    """The control: the door was already closed here, and stays closed."""
    workspace = _workspace(tmp_path)
    tools = _tools(workspace)
    with pytest.raises(Exception):
        tools.read_file({"path": ".minicc/web_token.json"})


def test_writing_the_allowlist_through_a_dot_dot_is_refused(tmp_path: Path) -> None:
    """The self-escalation this door exists for."""
    workspace = _workspace(tmp_path)
    tools = _tools(workspace)
    with pytest.raises(Exception):
        tools.write_file({"path": ".minicc/x/../allowlist.json", "content": ESCALATION})
    stored = (workspace / ".minicc" / "allowlist.json").read_text(encoding="utf-8")
    assert stored == '{"sessions":{}}', "the allowlist was rewritten through a '..' path"


def test_writing_the_allowlist_directly_is_still_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    tools = _tools(workspace)
    with pytest.raises(Exception):
        tools.write_file({"path": ".minicc/allowlist.json", "content": ESCALATION})
    stored = (workspace / ".minicc" / "allowlist.json").read_text(encoding="utf-8")
    assert stored == '{"sessions":{}}'


def test_the_agent_cannot_erase_its_own_deny_rules(tmp_path: Path) -> None:
    """``permissions.json`` holds the deny rules; writing it is escalation."""
    workspace = _workspace(tmp_path)
    tools = _tools(workspace)
    with pytest.raises(Exception):
        tools.write_file({
            "path": ".minicc/permissions.json",
            "content": json.dumps({"deny": {"paths": [], "tools": [], "commands": []}}),
        })
    stored = json.loads((workspace / ".minicc" / "permissions.json").read_text(encoding="utf-8"))
    assert stored["deny"]["paths"] == ["secrets/*"], "the deny rules were erased"


def test_editing_the_deny_rules_through_a_dot_dot_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    tools = _tools(workspace)
    with pytest.raises(Exception):
        tools.edit_file({
            "path": ".minicc/x/../permissions.json",
            "old": "secrets/*",
            "new": "",
        })
    stored = (workspace / ".minicc" / "permissions.json").read_text(encoding="utf-8")
    assert "secrets/*" in stored


# --- the symlink shape ---------------------------------------------------------


def test_a_path_that_resolves_onto_the_token_is_judged_by_its_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate must ask where the path *lands*, not what it is called.

    A link named ``notes.txt`` that points at ``.minicc/web_token.json`` is
    still the token.  Windows refuses symlink creation without elevation, so
    the shape is staged by making ``resolve()`` report the target - the gate
    must not consult the raw name when the resolved name says otherwise.
    """
    workspace = _workspace(tmp_path)
    tools = _tools(workspace)
    token = workspace / ".minicc" / "web_token.json"
    real_resolve = Path.resolve

    def fake_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if self.name == "notes.txt":
            return token
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    assert tools._sensitive_kind(".minicc/notes.txt") == "deny"
    with pytest.raises(Exception):
        tools.read_file({"path": ".minicc/notes.txt"})


def test_a_symlink_named_innocuously_cannot_smuggle_the_token_out(tmp_path: Path) -> None:
    """The same shape with a real symlink, where the platform allows one."""
    workspace = _workspace(tmp_path)
    link = workspace / ".minicc" / "notes.txt"
    try:
        os.symlink(workspace / ".minicc" / "web_token.json", link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable on this platform: {exc}")
    tools = _tools(workspace)
    with pytest.raises(Exception):
        tools.read_file({"path": ".minicc/notes.txt"})


# --- the controls --------------------------------------------------------------


def test_ordinary_workspace_files_are_unaffected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    tools = _tools(workspace)
    assert tools.read_file({"path": "src/app.py"}).status == "ok"
    assert tools.write_file({"path": "src/new.py", "content": "x = 1\n"}).status == "ok"


def test_a_minicc_file_that_is_not_on_the_deny_list_still_reads(tmp_path: Path) -> None:
    """The gate is a list, not a blanket ban on the .minicc directory."""
    workspace = _workspace(tmp_path)
    tools = _tools(workspace)
    result = tools.read_file({"path": ".minicc/todos.json"})
    assert result.status == "ok"
    assert "items" in (result.head or "") + (result.tail or "")


def test_the_mcp_config_stays_readable_but_redacted(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / ".minicc" / "mcp.json").write_text(
        json.dumps({"servers": {"docs": {"headers": {"Authorization": "Bearer sk-secret"}}}}),
        encoding="utf-8",
    )
    tools = _tools(workspace)
    result = tools.read_file({"path": ".minicc/mcp.json"})
    body = (result.head or "") + (result.tail or "")
    assert "sk-secret" not in body
    assert "REDACTED" in body
