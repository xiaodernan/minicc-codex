"""工具层核心测试：editor/bash/grep/web、注册表与授权、sandbox/MCP/worktree/变更检视。

M8-T6 拆分说明：测试本体逐字搬迁，未改断言。"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
import pytest
import minicc.tools.web as web_tool
from minicc.audit import authorize_tool
from minicc.sandbox import SandboxRunner
from minicc.mcp import load_mcp_config
from minicc.tools.bash import decode_process_output, is_readonly_command, run_bash
from minicc.tools.editor import EditError, Editor, StaleContextError
from minicc.tools.schemas import ToolCall
from minicc.tools.web import parse_search_html
from minicc.tools import build_registry
from minicc.changes import ChangeInspector
from minicc.worktree import WorktreeError, WorktreeManager


def test_editor_rejects_escape_and_stale_write(tmp_path: Path) -> None:
    editor = Editor(tmp_path)
    with pytest.raises(EditError):
        editor.write_file("../outside.txt", "no")

    editor.write_file("note.txt", "one\n")
    digest = editor.file_digest("note.txt")
    (tmp_path / "note.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(StaleContextError):
        editor.write_file("note.txt", "agent overwrite\n", expected_digest=digest)


def test_editor_requires_unique_edit(tmp_path: Path) -> None:
    editor = Editor(tmp_path)
    editor.write_file("note.txt", "same\nsame\n")
    with pytest.raises(EditError, match="不唯一"):
        editor.apply_edit("note.txt", "same", "new")


def test_editor_prunes_old_backups_to_a_cap(tmp_path: Path) -> None:
    """P2-8（2026-09-25 复核）：per-edit 备份必须有保留上限，不能永久堆积。

    未修复代码上这里红：205 次编辑会留下 205 份备份，断言 ==200 失败。
    注意 _audit 与 _backup 共用同一个 clock，所以断言全部用观察到的文件名，
    不与时间戳格式耦合。
    """
    from datetime import datetime, timedelta

    base = datetime(2026, 9, 25, 12, 0, 0)
    counter = {"i": 0}

    def counting_clock() -> str:
        counter["i"] += 1
        return (base + timedelta(seconds=counter["i"])).isoformat()

    backup_dir = tmp_path / ".minicc" / "backup"
    editor = Editor(tmp_path, backup_dir=backup_dir, clock=counting_clock)
    editor.write_file("note.txt", "v0\n")  # 新建文件不产生备份（_backup 只备份已存在文件）
    editor.write_file("note.txt", "v1\n")  # 第一份备份（v0 的内容）
    first_backup = next(backup_dir.iterdir()).name  # 时间戳最小的一份
    for i in range(2, 11):
        editor.write_file("note.txt", f"v{i}\n")
    mid_backup = max(p.name for p in backup_dir.iterdir())  # 第 10 份备份，必然幸存
    for i in range(11, 207):
        editor.write_file("note.txt", f"v{i}\n")  # 备份总数 206 ⇒ 裁掉最旧 6 份

    backups = sorted(p.name for p in backup_dir.iterdir())
    assert len(backups) == 200, f"备份应被裁剪到 200 份，实际 {len(backups)}"
    # 时钟逐次递增 ⇒ 名字里的时间戳按生成次序单调：最旧的一份必不在，中间的必在。
    assert first_backup not in backups
    assert mid_backup in backups
    # 裁剪本身进审计。
    assert any(entry.action == "backup_prune" for entry in editor.audit)


def test_editor_prune_failure_never_breaks_the_edit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """裁剪是卫生工作：目录不可枚举时只降级，绝不能绊倒正在发生的编辑。"""
    import pathlib

    editor = Editor(tmp_path, backup_dir=tmp_path / ".minicc" / "backup")
    editor.write_file("note.txt", "v0\n")

    def broken_iterdir(self):
        raise OSError("locked")

    monkeypatch.setattr(pathlib.Path, "iterdir", broken_iterdir)
    editor.write_file("note.txt", "v1\n")  # 不得抛 EditError
    monkeypatch.undo()
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "v1\n"


def test_registry_contains_readonly_git_tools(tmp_path: Path) -> None:
    registry = build_registry(Editor(tmp_path))
    assert registry.risk_of("git_status") == "readonly"
    assert registry.risk_of("git_diff") == "readonly"
    assert registry.risk_of("web_search") == "readonly"


def test_authorization_policy_requires_explicit_network_and_write_permission() -> None:
    readonly = authorize_tool("read_file", "readonly", {}, allow_changes=False, allow_network=False)
    assert readonly.allowed is True
    assert authorize_tool("write_file", "write", {}, allow_changes=False, allow_network=False).allowed is False
    assert authorize_tool("bash", "exec", {"command": "python -m pytest -q"}, allow_changes=False, allow_network=False).allowed is True
    assert authorize_tool("web_search", "readonly", {"query": "documentation"}, allow_changes=True, allow_network=False).allowed is False
    assert authorize_tool("web_search", "readonly", {"query": "documentation"}, allow_changes=False, allow_network=True).allowed is True
    assert authorize_tool("bash", "exec", {"command": "curl https://example.test"}, allow_changes=True, allow_network=False).allowed is False


def test_bash_output_decodes_windows_code_pages_without_crashing() -> None:
    encoded = "中文输出".encode("gb18030")
    assert decode_process_output(encoded) == "中文输出"


def test_bash_cancellation_terminates_long_running_process(tmp_path: Path) -> None:
    cancel_event = threading.Event()
    command = subprocess.list2cmdline([
        sys.executable,
        "-c",
        'import time; print("started", flush=True); time.sleep(30)',
    ])
    result_box: dict[str, object] = {}

    def run() -> None:
        result_box["result"] = run_bash(
            command,
            tmp_path,
            timeout=30,
            cancel_event=cancel_event,
        )

    worker = threading.Thread(target=run)
    worker.start()
    try:
        time.sleep(0.25)
        cancel_event.set()
        worker.join(8)
        assert not worker.is_alive(), "cancelled bash must not leave the task thread blocked"
        result = result_box["result"]
        assert result.status == "cancelled"
        assert "终止进程树" in result.summary
    finally:
        cancel_event.set()
        worker.join(8)


@pytest.mark.parametrize("command", [
    "start /b python -m http.server 8765",
    "Start-Process python -ArgumentList '-m http.server 8765'",
    "nohup python -m http.server 8765",
])
def test_bash_blocks_processes_that_escape_tool_lifecycle(tmp_path: Path, command: str) -> None:
    result = run_bash(command, tmp_path, timeout=1)
    assert result.status == "error"
    assert result.data["code"] == "detached_process_blocked"
    assert result.data["retryable"] is True
    assert "未启动" in result.summary


def test_bash_does_not_wait_for_child_inherited_output_pipe(tmp_path: Path) -> None:
    """A grandchild holding the output pipe must not extend the tool call.

    The command exits immediately but leaves a grandchild that inherits
    stdout/stderr and sleeps far longer than any bound here. Two failure modes
    make this call take the grandchild's full lifetime instead of returning the
    parent's output:

    * reading the pipe to EOF instead of stopping at the shell's exit, and
    * closing the pipe from the main thread while a reader thread is parked in
      ``read1()`` (``BufferedReader.close()`` waits for that read on Windows).

    Measured before the fix: 22.4s for a 20s grandchild with the shell already
    exited at 3.7s. The bound is deliberately far from both outcomes so suite
    load cannot flip it, and the timeout is generous so the *status* stays
    deterministic (a 1s budget used to make this test pass or fail depending on
    pytest's capture mode, which is what made it flaky).
    """
    command = subprocess.list2cmdline([
        sys.executable,
        "-c",
        'import subprocess,sys,time; subprocess.Popen([sys.executable, "-c", "import time; time.sleep(45)"]); print("parent", flush=True)',
    ])
    started = time.monotonic()
    result = run_bash(command, tmp_path, timeout=30)
    elapsed = time.monotonic() - started
    assert result.status == "ok"
    assert "parent" in result.render()
    assert elapsed < 15, f"waited {elapsed:.1f}s for an inherited pipe"


def test_search_parser_supports_duckduckgo_lite_redirects() -> None:
    html = """
    <a class='result-link' href='//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs'>Docs</a>
    <td class='result-snippet'>A short result summary.</td>
    """
    results = parse_search_html(html, 3)
    assert results == [{
        "title": "Docs",
        "url": "https://example.com/docs",
        "snippet": "A short result summary.",
    }]


def test_search_parser_supports_bing_result_cards() -> None:
    html = """
    <li class="b_algo">
      <h2><a href="https://example.com/docs">A <strong>title</strong></a></h2>
      <div class="b_caption"><p class="b_lineclamp2">A short result summary.</p></div>
    </li>
    """
    assert parse_search_html(html, 3) == [{
        "title": "A title",
        "url": "https://example.com/docs",
        "snippet": "A short result summary.",
    }]


def test_web_search_caches_results_and_marks_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    web_tool._SEARCH_CACHE.clear()
    calls = 0

    def fake_fetch(_query: str) -> web_tool._SearchFetch:
        nonlocal calls
        calls += 1
        return web_tool._SearchFetch(
            source="test",
            results=[{"title": "Docs", "url": "https://example.com", "snippet": "summary"}],
            diagnostics=[],
        )

    monkeypatch.setattr(web_tool, "_fetch_search", fake_fetch)
    first = web_tool.web_search({"query": "cache me", "max_results": 1})
    second = web_tool.web_search({"query": "cache me", "max_results": 1})
    assert calls == 1
    assert first.data["cached"] is False
    assert second.data["cached"] is True


@pytest.mark.parametrize(
    "command",
    [
        "pytest -q -p no:cacheprovider",
        "python -m pytest tests/test_core.py",
        r".\\.venv\\Scripts\\python.exe -m pytest -q",
    ],
)
def test_safe_web_command_allows_readonly_pytest(command: str) -> None:
    assert is_readonly_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "python -c print('unsafe')",
        "pytest && del important.txt",
        "pytest > report.txt",
        "powershell -Command Get-ChildItem",
    ],
)
def test_safe_web_command_rejects_other_shell_commands(command: str) -> None:
    assert not is_readonly_command(command)


def test_sensitive_file_is_not_read(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("MINICC_API_KEY=sk-secret-value\n", encoding="utf-8")
    result = build_registry(Editor(tmp_path)).execute(
        ToolCall("read_file", {"path": ".env"})
    )
    assert result.status == "error"
    assert "拒绝访问敏感文件" in result.summary


def test_grep_accepts_single_file_and_read_window_errors_are_explicit(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    target.write_text("alpha = 1\nbeta = 2\n", encoding="utf-8")
    registry = build_registry(Editor(tmp_path))

    grep_result = registry.execute(ToolCall("grep", {"pattern": "beta", "path": "demo.py"}))
    assert grep_result.status == "ok"
    assert "demo.py:2: beta = 2" in grep_result.render()

    window_result = registry.execute(
        ToolCall("read_file", {"path": "demo.py", "offset": 99, "limit": 10})
    )
    assert window_result.status == "error"
    assert "读取窗口为空或越界" in window_result.summary


def test_tool_output_redacts_common_credentials(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text(
        "MINICC_API_KEY=sk-secret-value\n", encoding="utf-8"
    )
    result = build_registry(Editor(tmp_path)).execute(
        ToolCall("read_file", {"path": ".env.example"})
    )
    assert result.status == "ok"
    assert "sk-secret-value" not in result.render()
    assert "REDACTED" in result.render()


def test_sandbox_docker_mode_fails_closed_when_docker_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("minicc.sandbox.shutil.which", lambda _name: None)
    runner = SandboxRunner("docker")
    assert runner.status()["backend"] == "unavailable"
    assert runner.status()["isolated"] is False
    result = runner.run("echo should-not-run", tmp_path)
    assert result.status == "error"
    assert "SANDBOX_UNAVAILABLE" in result.summary


def test_mcp_config_loads_opt_in_servers(tmp_path: Path) -> None:
    config_dir = tmp_path / ".minicc"
    config_dir.mkdir()
    (config_dir / "mcp.json").write_text(
        json.dumps({"servers": {"docs": {"command": sys.executable, "args": ["server.py"], "read_only": True}}}),
        encoding="utf-8",
    )
    configs = load_mcp_config(tmp_path)
    assert len(configs) == 1
    assert configs[0].name == "docs"
    assert configs[0].read_only is True


def test_worktree_manager_creates_and_removes_managed_tree(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "minicc test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")

    manager = WorktreeManager(tmp_path)
    try:
        item = manager.create("feature-test", "feature-test")
        assert item["managed"] is True
        assert Path(item["path"]).is_dir()
        removed = manager.remove("feature-test")
        assert removed["removed"] is True
        with pytest.raises(WorktreeError):
            manager.create("../escape")
    finally:
        shutil.rmtree(manager.root, ignore_errors=True)


def test_change_inspector_shows_uncommitted_file_diff(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    target = tmp_path / "demo.txt"
    target.write_text("line one\nline two\n", encoding="utf-8")
    inspector = ChangeInspector(tmp_path)
    summary = inspector.summary()
    assert summary["files"][0]["path"] == "demo.txt"
    diff = inspector.diff("demo.txt")
    assert diff["status"] == "added"
    assert diff["additions"] == 2
    assert "+line one" in diff["patch"]
