"""M4-T5: writable edit fixtures with hidden graders for the ``v2`` suite.

The legacy ``benchmarks/tasks.json`` suite is read-only: none of its 30 tasks
carry a ``fixture``, so ``allow_changes`` resolves to False and the agent runs
against the minicc repo itself — coding ability is never measured and write
permission can never be safely enabled. The ``behavior`` suite does isolate
fixtures but only grades pure-function behavior.

This module adds the missing piece: small synthetic repositories (declared
inline in ``benchmarks/tasks.v2.json``) that the agent edits inside an isolated
temporary workspace with ``allow_changes=True``, graded by two oracle types:

  * ``file_contract``  — assert produced files exist / contain / equal / parse
    to a required shape.
  * ``command_contract`` — run a command (usually the repo's own tests) inside
    the workspace and require a specific exit code / stdout marker.

Grader *driver* scripts are materialized into a ``.graders`` directory that
lives **outside** the repository (``MINICC_EVAL_GRADER_DIR`` / ``--grader-dir``)
and is unreadable to the agent's file tools (see ``tools/fs.py``). The expected
values themselves stay in ``tasks.v2.json``, which is never inside the agent's
isolated workspace, so the oracle is hidden from the run under test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

__all__ = [
    "SUITE_VERSION",
    "GRADER_TYPES",
    "DEFAULT_TASKS_V2",
    "resolve_grader_dir",
    "v2_tasks",
    "validate_task",
    "grade_file_contract",
    "grade_command_contract",
    "grade_v2",
]

SUITE_VERSION = "v2-1"
GRADER_TYPES = frozenset({"file_contract", "command_contract"})
DEFAULT_TASKS_V2 = Path(__file__).resolve().parent.parent / "benchmarks" / "tasks.v2.json"
GRADER_DIR_NAME = ".graders"
_REQUIRED_KEYS = ("id", "category", "prompt", "fixture", "grader")


def resolve_grader_dir(explicit: object | None = None) -> Path:
    """Where grader driver scripts live — always outside the agent workspace.

    Priority: explicit argument → ``MINICC_EVAL_GRADER_DIR`` → a ``.graders``
    directory beside (not inside) the repository. Keeping it outside the repo
    means a benchmark run whose workspace is the repo cannot stumble onto it,
    and the ``.graders`` name is blocked at the tool layer regardless.
    """
    raw = str(explicit or os.getenv("MINICC_EVAL_GRADER_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    repo_root = Path(__file__).resolve().parent.parent
    return (repo_root.parent / GRADER_DIR_NAME).resolve()


def v2_tasks(path: Path | str = DEFAULT_TASKS_V2) -> list[dict[str, Any]]:
    tasks = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        raise ValueError("tasks.v2.json 必须是任务数组")
    return tasks


def validate_task(task: dict[str, Any]) -> None:
    """Schema gate used by tests and by ``--suite v2`` loading.

    Raises ``ValueError`` on the first violation so a malformed fixture can
    never silently degrade into an ungraded or escape-prone task.
    """
    if not isinstance(task, dict):
        raise ValueError("任务必须是对象")
    for key in _REQUIRED_KEYS:
        if key not in task:
            raise ValueError(f"任务缺少字段: {key}")
    if not isinstance(task["id"], str) or not task["id"].strip():
        raise ValueError("任务 id 必须是非空字符串")
    if not isinstance(task["prompt"], str) or not task["prompt"].strip():
        raise ValueError(f"任务 {task['id']} prompt 不能为空")
    fixture = task["fixture"]
    if not isinstance(fixture, dict) or not fixture:
        raise ValueError(f"任务 {task['id']} fixture 必须是非空对象")
    for relative in fixture:
        rel = str(relative).replace("\\", "/")
        if rel.startswith("/") or ".." in rel.split("/"):
            raise ValueError(f"任务 {task['id']} fixture 路径逃逸: {relative}")
    grader = task["grader"]
    if not isinstance(grader, dict) or grader.get("type") not in GRADER_TYPES:
        raise ValueError(f"任务 {task['id']} grader 类型非法: {grader.get('type') if isinstance(grader, dict) else grader}")
    minutes = task.get("max_minutes")
    if not isinstance(minutes, (int, float)) or isinstance(minutes, bool) or minutes <= 0:
        raise ValueError(f"任务 {task['id']} max_minutes 必须为正数")


_FILE_CONTRACT_GRADER = '''import json, re, sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
spec = json.loads(sys.stdin.read())
checks = 0
for item in spec.get("files", []):
    rel = str(item["path"]).replace("\\\\", "/")
    target = (root / rel).resolve()
    if not target.is_relative_to(root):
        print("contract path escapes workspace", file=sys.stderr)
        raise SystemExit(2)
    checks += 1
    exists = target.is_file()
    if "exists" in item and bool(item["exists"]) != exists:
        print(f"existence mismatch: {rel}", file=sys.stderr)
        raise SystemExit(1)
    content_keys = ("contains", "not_contains", "equals", "regex", "json_equals")
    if not exists:
        if any(key in item for key in content_keys):
            print(f"missing file: {rel}", file=sys.stderr)
            raise SystemExit(1)
        continue
    text = target.read_text(encoding="utf-8", errors="replace")
    if "contains" in item and str(item["contains"]) not in text:
        print(f"missing substring in {rel}", file=sys.stderr)
        raise SystemExit(1)
    if "not_contains" in item and str(item["not_contains"]) in text:
        print(f"forbidden substring in {rel}", file=sys.stderr)
        raise SystemExit(1)
    if "equals" in item and text != item["equals"]:
        print(f"content mismatch: {rel}", file=sys.stderr)
        raise SystemExit(1)
    if "regex" in item and not re.search(item["regex"], text):
        print(f"regex mismatch: {rel}", file=sys.stderr)
        raise SystemExit(1)
    if "json_equals" in item:
        try:
            parsed = json.loads(text)
        except Exception:
            print(f"invalid json: {rel}", file=sys.stderr)
            raise SystemExit(1)
        if parsed != item["json_equals"]:
            print(f"json mismatch: {rel}", file=sys.stderr)
            raise SystemExit(1)
print("MINICC_FILE_CONTRACT_COMPLETE:" + str(checks))
'''

_COMMAND_CONTRACT_GRADER = '''import json, os, subprocess, sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
spec = json.loads(sys.stdin.read())
command = spec["command"]
if "{python}" in command:
    # Rendering belongs to the host (see render_python_command): an unquoted
    # interpreter path is split by shell=True, which graded correct workspaces
    # as failures. Fail loudly instead of quietly repeating that bug.
    print("command still carries an unrendered {python} placeholder", file=sys.stderr)
    raise SystemExit(2)
expect = int(spec.get("expect_exit", 0))
timeout = float(spec.get("timeout", 180))
marker = spec.get("stdout_contains")
# Never write .pyc: a stale bytecode file from an earlier import of the buggy
# source can shadow the agent's fix on same-mtime filesystems (Windows).
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
try:
    proc = subprocess.run(
        command, shell=True, cwd=str(root), env=env,
        capture_output=True, text=True, timeout=timeout,
    )
except subprocess.TimeoutExpired:
    print("MINICC_COMMAND_CONTRACT_COMPLETE:0")
    print("command timed out", file=sys.stderr)
    raise SystemExit(1)
ok = proc.returncode == expect
if marker is not None and marker not in (proc.stdout or ""):
    ok = False
print("MINICC_COMMAND_CONTRACT_COMPLETE:" + ("1" if ok else "0"))
if not ok:
    print((proc.stdout or "")[-2000:], file=sys.stderr)
    print((proc.stderr or "")[-2000:], file=sys.stderr)
raise SystemExit(0 if ok else 1)
'''


def _materialize(grader_dir: Path, name: str, source: str) -> Path:
    grader_dir.mkdir(parents=True, exist_ok=True)
    script = grader_dir / name
    try:
        current = script.read_text(encoding="utf-8") if script.is_file() else None
    except OSError:
        current = None
    if current != source:
        script.write_text(source, encoding="utf-8")
    return script


def _run_grader(
    script_name: str,
    source: str,
    grader_dir: Path,
    workspace: Path,
    spec: dict[str, Any],
    *,
    isolated: bool,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    script = _materialize(Path(grader_dir), script_name, source)
    workspace = Path(workspace).resolve()
    argv = [sys.executable]
    if isolated:
        argv.append("-I")
    argv += [str(script), str(workspace)]
    return subprocess.run(
        argv, input=json.dumps(spec), capture_output=True, text=True,
        cwd=str(workspace), timeout=timeout,
    )


def grade_file_contract(
    task: dict[str, Any], workspace: Path, *, grader_dir: Path | None = None
) -> dict[str, Any]:
    spec = task.get("grader") or {}
    files = spec.get("files") or []
    try:
        result = _run_grader(
            "file_contract.py", _FILE_CONTRACT_GRADER,
            grader_dir or resolve_grader_dir(), workspace, spec,
            isolated=True, timeout=float(spec.get("timeout", 60)),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"passed": False, "grader_type": "file_contract", "error": type(exc).__name__}
    marker = f"MINICC_FILE_CONTRACT_COMPLETE:{len(files)}"
    passed = result.returncode == 0 and marker in result.stdout.splitlines()
    return {
        "passed": passed, "grader_type": "file_contract",
        "case_count": len(files), "exit_code": result.returncode,
    }


def render_python_command(command: str, python_executable: str) -> str:
    """Substitute ``{python}`` with an interpreter path that survives a shell.

    The command contract runs through ``shell=True``, where an unquoted path is
    split at its first space - and Windows installs Python under
    ``C:\\Program Files\\`` by default, so the default install turned into
    ``'C:\\Program' 不是内部或外部命令`` and graded a correct workspace as failed.
    Quoting lives here, in-process and once, so the embedded grader carries no
    substitution logic of its own.
    """
    return command.replace("{python}", subprocess.list2cmdline([python_executable]))


def grade_command_contract(
    task: dict[str, Any],
    workspace: Path,
    *,
    grader_dir: Path | None = None,
    python_executable: str | None = None,
) -> dict[str, Any]:
    """Grade a shell command; ``python_executable`` is what ``{python}`` becomes.

    Defaults to ``sys.executable``. The keyword is the seam a test uses to pin
    an interpreter path containing a space - the one shape the default Windows
    install has, and the one ``shell=True`` splits.
    """
    spec = task.get("grader") or {}
    command = spec.get("command")
    if isinstance(command, str):
        # Render here, in-process and once. The embedded grader used to do this
        # itself, unquoted, which is how a correct workspace came back failed on
        # a default Windows install: ``C:\Program Files\...\python.exe`` was
        # split at the space and cmd.exe reported "C:\Program 不是内部或外部命令".
        spec = {
            **spec,
            "command": render_python_command(command, python_executable or sys.executable),
        }
    try:
        result = _run_grader(
            "command_contract.py", _COMMAND_CONTRACT_GRADER,
            grader_dir or resolve_grader_dir(), workspace, spec,
            isolated=False, timeout=float(spec.get("timeout", 200)) + 30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"passed": False, "grader_type": "command_contract", "error": type(exc).__name__}
    passed = result.returncode == 0 and "MINICC_COMMAND_CONTRACT_COMPLETE:1" in result.stdout.splitlines()
    return {"passed": passed, "grader_type": "command_contract", "exit_code": result.returncode}


def grade_v2(
    task: dict[str, Any], workspace: Path, answer: str = "", *, grader_dir: Path | None = None
) -> dict[str, Any]:
    """Dispatch a v2 task to its grader; signature mirrors ``grade_behavior``."""
    grader = task.get("grader") or {}
    kind = grader.get("type")
    if kind == "file_contract":
        return grade_file_contract(task, workspace, grader_dir=grader_dir)
    if kind == "command_contract":
        return grade_command_contract(task, workspace, grader_dir=grader_dir)
    return {"passed": None, "grader_type": "ungraded"}
