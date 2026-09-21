"""M2 security-perimeter regressions (roadmap exit criterion: >=12 tests).

Every test here corresponds to a confirmed finding in docs/AUDIT_2026-09-20.md
(P1-1/P1-2/P1-5/P1-6/P1-13, P2-5, P2-6, P1-12 spawn env). They must fail on
the pre-M2 code and pass on the fixed code — no always-green assertions.
"""

from __future__ import annotations

import json
import os
import types
from pathlib import Path

import pytest

from minicc.config import load_config
from minicc.mcp import McpStdioClient, _emit_spawn_audit
from minicc.tools.editor import EditError, Editor
from minicc.tools.fs import FsTools
from minicc.tools.registry import ToolError
from minicc.workspaces import resolve_workspace_path

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fs(workspace: Path) -> FsTools:
    return FsTools(Editor(workspace))


def _make_dir_link(link: Path, target: Path) -> bool:
    """Create a directory junction (Windows) or symlink (POSIX)."""
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
# M2-T1: workspace_roots enforcement (P1-13)
# ---------------------------------------------------------------------------


def test_roots_reject_outside_path(tmp_path: Path) -> None:
    allowed = tmp_path / "a"
    outside = tmp_path / "b"
    allowed.mkdir()
    outside.mkdir()
    with pytest.raises(ValueError, match="越界|不在允许"):
        resolve_workspace_path(str(outside), roots=(allowed,))


def test_roots_allow_inside_subdirectory(tmp_path: Path) -> None:
    allowed = tmp_path / "a"
    inner = allowed / "project"
    inner.mkdir(parents=True)
    resolved = resolve_workspace_path(str(inner), roots=(allowed,))
    assert resolved == inner.resolve()


def test_all_four_entries_call_shared_resolver() -> None:
    """Structural: web.py (3 entries) + task_manager.py (1) share the gate."""
    import minicc.task_manager as task_manager_module
    import minicc.web as web_module
    import inspect

    call_sites = inspect.getsource(web_module).count("resolve_workspace_path(")
    call_sites += inspect.getsource(task_manager_module).count("resolve_workspace_path(")
    assert call_sites >= 4


# ---------------------------------------------------------------------------
# M2-T2: .minicc auth/credential files (P1-1, P1-2)
# ---------------------------------------------------------------------------


def test_write_file_denied_for_minicc_auth_files(tmp_path: Path) -> None:
    tools = _fs(tmp_path)
    for rel in (
        ".minicc/allowlist.json",
        ".minicc/web_token.json",
        ".minicc/mcp.json",
        ".minicc/audit.jsonl",
        ".minicc/worker/task-1.config.json",
    ):
        with pytest.raises(ToolError):
            tools.write_file({"path": rel, "content": '{"sessions":{}}'})


def test_read_file_denied_for_web_token_and_allowlist(tmp_path: Path) -> None:
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "web_token.json").write_text(
        json.dumps({"token": "T" * 64}), encoding="utf-8"
    )
    (tmp_path / ".minicc" / "allowlist.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".minicc" / "worker").mkdir()
    (tmp_path / ".minicc" / "worker" / "t.config.json").write_text(
        json.dumps({"api_key": "sk-secret"}), encoding="utf-8"
    )
    tools = _fs(tmp_path)
    for rel in (
        ".minicc/web_token.json",
        ".minicc/allowlist.json",
        ".minicc/worker/t.config.json",
    ):
        with pytest.raises(ToolError):
            tools.read_file({"path": rel})


def test_read_file_redacts_mcp_headers(tmp_path: Path) -> None:
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "mcp.json").write_text(
        json.dumps({
            "servers": {
                "remote": {
                    "url": "https://example.test/mcp",
                    "headers": {"Authorization": "Bearer sk-ant-secret"},
                }
            }
        }),
        encoding="utf-8",
    )
    result = _fs(tmp_path).read_file({"path": ".minicc/mcp.json"})
    body = (result.head or "") + (result.tail or "")
    assert "sk-ant-secret" not in body
    assert "REDACTED" in body


# ---------------------------------------------------------------------------
# M2-T6: junction / symlink escape (P2-6)
# ---------------------------------------------------------------------------


def _junction_workspace(tmp_path: Path) -> tuple[Path, Path] | None:
    workspace = tmp_path / "ws"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("TOPSECRET-abc123", encoding="utf-8")
    (workspace / "normal.txt").write_text("hello", encoding="utf-8")
    if not _make_dir_link(workspace / "out", outside):
        return None
    return workspace, outside


def test_junction_grep_does_not_leak(tmp_path: Path) -> None:
    made = _junction_workspace(tmp_path)
    if made is None:
        pytest.skip("cannot create directory junction/symlink here")
    workspace, _ = made
    result = _fs(workspace).grep({"pattern": "TOPSECRET"})
    body = (result.head or "") + (result.tail or "")
    assert "TOPSECRET" not in body
    assert "out/secret.txt" not in body


def test_junction_glob_and_tree_do_not_leak(tmp_path: Path) -> None:
    made = _junction_workspace(tmp_path)
    if made is None:
        pytest.skip("cannot create directory junction/symlink here")
    workspace, _ = made
    tools = _fs(workspace)
    glob_body = tools.glob({"pattern": "*.txt"}).head or ""
    assert "out/secret.txt" not in glob_body
    assert "normal.txt" in glob_body
    tree_body = tools.tree({}).head or ""
    assert "out" not in tree_body.split()
    assert "secret.txt" not in tree_body


def test_junction_file_tree_api_does_not_leak(tmp_path: Path) -> None:
    made = _junction_workspace(tmp_path)
    if made is None:
        pytest.skip("cannot create directory junction/symlink here")
    workspace, _ = made
    from minicc.web import AgentService

    config = types.SimpleNamespace(
        yolo=False, max_concurrent_tasks=2, sandbox_mode="host",
        sandbox_image="python:3.11-slim", base_url="https://example.test/v1",
        api_key="test-key", model="test-model", timeout=10, tool_mode="auto",
        reasoning_effort="high", max_turns=4, compact_threshold=300_000,
        context_window_tokens=300_000,
    )
    service = AgentService(workspace, config)
    try:
        tree = service.file_tree("", depth=3)
        names = {entry["name"] for entry in tree["entries"]}
        assert "out" not in names
        assert "normal.txt" in names
    finally:
        service.shutdown()


def test_editor_read_still_rejects_junction_escape(tmp_path: Path) -> None:
    made = _junction_workspace(tmp_path)
    if made is None:
        pytest.skip("cannot create directory junction/symlink here")
    workspace, _ = made
    with pytest.raises((EditError, ToolError)):
        _fs(workspace).read_file({"path": "out/secret.txt"})


# ---------------------------------------------------------------------------
# M2-T7: MCP spawn env scrubbing (P1-12)
# ---------------------------------------------------------------------------


def test_scrubbed_env_excludes_ambient_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_API_KEY", "sk-secret-value")
    monkeypatch.setenv("MINICC_WEB_TOKEN", "web-token-value")
    env = McpStdioClient.scrubbed_env(None)
    assert "MINICC_API_KEY" not in env
    assert "MINICC_WEB_TOKEN" not in env
    assert not any("sk-secret-value" in value for value in env.values())
    if os.name == "nt":
        assert any(key.upper() == "PATH" for key in env)


def test_scrubbed_env_keeps_explicit_entry_env(monkeypatch: pytest.MonkeyPatch) -> None:
    env = McpStdioClient.scrubbed_env({"MY_SERVER_KEY": "explicit"})
    assert env["MY_SERVER_KEY"] == "explicit"


def test_spawn_audit_is_redacted(tmp_path: Path) -> None:
    _emit_spawn_audit(
        tmp_path,
        name="remote",
        transport="stdio",
        command="node",
        env_keys=["MY_SERVER_KEY"],
    )
    audit_path = tmp_path / ".minicc" / "mcp_audit.jsonl"
    assert audit_path.is_file()
    entry = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert entry["kind"] == "mcp_spawn"
    assert entry["name"] == "remote"
    assert entry["env_keys"] == ["MY_SERVER_KEY"]
    assert "sk-" not in audit_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# M2-T8: config hijack / .env defects (P2-5 a,b,e,f)
# ---------------------------------------------------------------------------


@pytest.fixture()
def config_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated CWD + MINICC_HOME with all MINICC_* env cleared."""
    for key in [k for k in os.environ if k.startswith("MINICC_")]:
        monkeypatch.delenv(key, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "sk-test-key")
    monkeypatch.chdir(tmp_path)
    yield tmp_path, home
    # load_config exports .env values into os.environ; drop the additions so
    # later tests are not polluted (monkeypatch restores the originals).
    for key in [k for k in os.environ if k.startswith("MINICC_")]:
        os.environ.pop(key, None)


def test_stray_uppercase_env_does_not_hijack_config(config_env) -> None:
    tmp_path, home = config_env
    os.environ["MODEL"] = "stray-model"
    try:
        (home / "config.json").write_text(
            json.dumps({"model": "from-json"}), encoding="utf-8"
        )
        assert load_config().model == "from-json"
    finally:
        os.environ.pop("MODEL", None)


def test_env_file_exports_minicc_toggles(config_env) -> None:
    tmp_path, _home = config_env
    (tmp_path / ".env").write_text("MINICC_ALLOW_PRIVATE_FETCH=1\n", encoding="utf-8")
    load_config()
    assert os.environ.get("MINICC_ALLOW_PRIVATE_FETCH") == "1"


def test_env_file_strips_inline_comments(config_env) -> None:
    tmp_path, _home = config_env
    (tmp_path / ".env").write_text(
        "MINICC_MODEL=x # note\nMINICC_YOLO=1 # on\n", encoding="utf-8"
    )
    config = load_config()
    assert config.model == "x"
    assert config.yolo is True


def test_env_file_accepts_export_prefix(config_env) -> None:
    tmp_path, _home = config_env
    (tmp_path / ".env").write_text("export MINICC_MODEL=y\n", encoding="utf-8")
    assert load_config().model == "y"


def test_env_file_quoted_value_keeps_hash(config_env) -> None:
    tmp_path, _home = config_env
    (tmp_path / ".env").write_text('MINICC_MODEL="a #b"\n', encoding="utf-8")
    assert load_config().model == "a #b"


def test_config_json_list_workspace_roots_not_repr(config_env) -> None:
    tmp_path, home = config_env
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    root_a.mkdir()
    root_b.mkdir()
    (home / "config.json").write_text(
        json.dumps({"workspace_roots": [str(root_a), str(root_b)]}), encoding="utf-8"
    )
    config = load_config()
    assert set(config.workspace_roots) == {root_a.resolve(), root_b.resolve()}
