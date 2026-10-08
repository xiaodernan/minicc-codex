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

import ast
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

__all__ = [
    "SUITE_VERSION",
    "LEGACY_SUITE_VERSION",
    "SUITE_VERSIONS",
    "GRADER_TYPES",
    "DEFAULT_TASKS_V2",
    "resolve_grader_dir",
    "v2_tasks",
    "validate_task",
    "require_prompt",
    "require_objective_shape",
    "spec_blockers",
    "GRADER_SCRIPTS",
    "grade_file_contract",
    "grade_command_contract",
    "grade_v2",
]

SUITE_VERSION = "v2-1"
# The vocabulary of suite identities a result may carry. A task file that names
# anything outside this table is refused instead of reporting a suite nobody
# produced - and a task that names nothing gets SUITE_VERSION stamped on it
# here, so the value in benchmarks/tasks.v2.json can never be the only source.
LEGACY_SUITE_VERSION = "legacy-1"
SUITE_VERSIONS = frozenset({SUITE_VERSION, LEGACY_SUITE_VERSION})
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
    for task in tasks:
        if isinstance(task, dict) and "suite_version" not in task:
            task["suite_version"] = SUITE_VERSION
    return tasks


def require_prompt(task: dict[str, Any]) -> None:
    """Every suite's task must actually ask something - one owner for that rule.

    The runner turns a missing prompt into an empty message and still pays for the
    agent turn, so "no question" cannot be allowed to reach a run from either loader.
    """
    task_id = task.get("id") if isinstance(task, dict) else None
    prompt = task.get("prompt") if isinstance(task, dict) else None
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"任务 {task_id!r} prompt 不能为空")


def require_objective_shape(task: dict[str, Any]) -> None:
    """A task may not carry a field the report or the shell would have to invent.

    Two silent coercions this refuses: a missing or blank ``category`` becomes the report
    word ``uncategorized``, and a truthy non-string ``verify_command`` becomes
    ``str(...)`` - a nonsense command line that fails and is charged to the agent. A null
    or absent command is fine; that is how prompt-only tasks are written.
    """
    task_id = task.get("id") if isinstance(task, dict) else None
    category = task.get("category") if isinstance(task, dict) else None
    if not isinstance(category, str) or not category.strip():
        raise ValueError(f"任务 {task_id!r} category 必须是非空字符串（报告不应替任务编一个）")
    command = task.get("verify_command") if isinstance(task, dict) else None
    if command is not None and (not isinstance(command, str) or not command.strip()):
        raise ValueError(
            f"任务 {task_id!r} verify_command 必须是非空字符串或 null，收到 {type(command).__name__}"
        )


def require_writable_fixture(task: dict[str, Any]) -> None:
    """A fixture must be text the workspace can actually hold, and its keys must fit together.

    Three host faults turn into an agent's failure when they reach the write path: a
    non-string value is written as Python repr (``str({'a': 1})`` is not valid JSON, so the
    agent is handed a file no parser reads), a key that is not a string makes the runner's
    path join raise, and a key naming a directory (``""``, ``"."``, ``"dir/"``) makes
    ``write_text`` fail on that directory. Escaping keys are refused as before, now including
    a Windows drive absolute one, which the leading-slash test did not see.

    Keys are also checked against **each other**, which no earlier door did. Measured on the
    unmodified plane: ``"./a.txt"`` after ``"a.txt"`` silently overwrote the first file (the
    agent got one file where the author wrote two, and no error anywhere),
    ``"a.txt"`` together with ``"a.txt/b.txt"`` left a half-built workspace holding only
    ``a.txt``, and ``"d/x"`` together with ``"d"`` raised ``PermissionError``.

    Two keys are compared by the **location they name**, not by their spelling, because identity
    is the host's own property: measured on this plane (case-insensitive volume) ``"A.txt"`` with
    ``"a.txt"`` left a workspace holding one file whose content was the later value and raised
    nothing, and ``"p/q.txt"`` with ``"P/Q.txt"`` did the same, while ``"P"`` with ``"p/q.txt"``
    raised ``FileExistsError`` after writing ``P`` and ``"p/q.txt"`` with ``"P"`` raised
    ``PermissionError``. ``os.path.normcase`` is therefore asked per segment for the comparison
    only; the refusal still quotes the two spellings the author wrote.
    """
    task_id = task.get("id") if isinstance(task, dict) else None
    fixture = task.get("fixture") if isinstance(task, dict) else None
    if fixture is None:
        return
    if not isinstance(fixture, dict):
        raise ValueError(f"任务 {task_id!r} fixture 必须是非空对象")
    authored: list[tuple[str, str]] = []
    for relative, content in fixture.items():
        if not isinstance(relative, str):
            raise ValueError(
                f"任务 {task_id!r} fixture 的键 {relative!r} 必须是字符串，收到 {type(relative).__name__}"
            )
        rel = relative.replace("\\", "/")
        drive_absolute = len(rel) >= 2 and rel[0].isalpha() and rel[1] == ":"
        if rel.startswith("/") or drive_absolute or ".." in rel.split("/"):
            raise ValueError(f"任务 {task_id!r} fixture 路径逃逸: {relative}")
        if not rel.strip() or rel == "." or rel.endswith("/"):
            raise ValueError(
                f"任务 {task_id!r} fixture 键 {relative!r} 命名的是目录而不是文件，写不进工作区"
            )
        if not isinstance(content, str):
            raise ValueError(
                f"任务 {task_id!r} fixture {relative!r} 的内容必须是文本，"
                f"收到 {type(content).__name__}（写进工作区会变成 Python repr）"
            )
        segments = [segment for segment in rel.split("/") if segment and segment != "."]
        if not segments:
            raise ValueError(
                f"任务 {task_id!r} fixture 键 {relative!r} 归一化之后什么都不剩，写不出文件"
            )
        # The authored spelling is kept, not the normalised one: the pair checks below have to
        # be able to point at the two keys the author actually wrote in the task file.
        authored.append(("/".join(segments), relative))

    # Every pair, in both directions, over the whole set: dict order must never decide whether
    # a task loads, and one position may only be written once.
    #
    # `normcase` is applied per segment, never to the whole path: on a Windows volume it also
    # rewrites "/" to "\\", which would make the parent/child prefixes below stop matching.
    def location(path: str) -> tuple[str, ...]:
        return tuple(os.path.normcase(segment) for segment in path.split("/"))

    for position, (path, relative) in enumerate(authored):
        here = location(path)
        for other_path, other_relative in authored[position + 1:]:
            there = location(other_path)
            if here == there:
                raise ValueError(
                    f"任务 {task_id!r} fixture 键 {relative!r} 与 {other_relative!r} 在工作区里是同一个位置，"
                    "后写的会静默盖掉先写的"
                )
            if there[: len(here)] == here:
                raise ValueError(
                    f"任务 {task_id!r} fixture 键 {relative!r} 占用了 {other_relative!r} 的父目录，"
                    "两份内容写不进同一个工作区"
                )
            if here[: len(there)] == there:
                raise ValueError(
                    f"任务 {task_id!r} fixture 键 {other_relative!r} 占用了 {relative!r} 的父目录，"
                    "两份内容写不进同一个工作区"
                )

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
    declared = task.get("suite_version", SUITE_VERSION)
    if declared not in SUITE_VERSIONS:
        raise ValueError(
            f"任务 {task['id']} 的 suite_version 不认识: {declared!r}"
            f"（本版本只认 {sorted(SUITE_VERSIONS)}）"
        )
    require_prompt(task)
    require_objective_shape(task)
    fixture = task["fixture"]
    if not isinstance(fixture, dict) or not fixture:
        raise ValueError(f"任务 {task['id']} fixture 必须是非空对象")
    require_writable_fixture(task)
    grader = task["grader"]
    if not isinstance(grader, dict) or grader.get("type") not in GRADER_TYPES:
        raise ValueError(f"任务 {task['id']} grader 类型非法: {grader.get('type') if isinstance(grader, dict) else grader}")
    # Same rule the grader applies, applied before the agent is paid: a spec nobody can
    # execute is a broken task file, not a workspace that failed.
    blockers = spec_blockers(grader["type"], grader)
    if blockers:
        raise ValueError(f"任务 {task['id']} grader 规格无法判分: {'; '.join(blockers)}")
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
    raw = target.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        # A criterion evaluated over replacement characters measures nothing:
        # a non-utf-8 file makes a non-ascii `contains` fail while making the
        # same non-ascii `not_contains` pass with the text physically present.
        # Refuse the verdict instead of guessing it (exit 2 = cannot judge).
        print(
            f"cannot judge content of {rel}: not valid utf-8 at byte {exc.start}; "
            "refusing to match markers over replacement text",
            file=sys.stderr,
        )
        raise SystemExit(2)
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
#
# PYTHONIOENCODING pins the *graded command's* stdout codec to the decoder the
# line below names. Leaving it out is the defect M8-T58 measured: on a cp936
# host the same correct workspace that prints one Chinese line graded passed
# with no PYTHONIOENCODING in the environment and failed with
# PYTHONIOENCODING=utf-8 in it - the child switched to UTF-8, this read stayed
# cp936, and the marker came back as mojibake. A criterion whose verdict moves
# with an environment variable nobody is required to set measures the host,
# not the work.
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
try:
    proc = subprocess.run(
        command, shell=True, cwd=str(root), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
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
        # Double-check inside the write window: another writer may have
        # materialized identical bytes while we compared (the shared grader
        # dir sees cross-process runs); skip our own replace entirely if the
        # winner got there first, which removes almost all contention.
        try:
            fresh = script.read_text(encoding="utf-8") if script.is_file() else None
        except OSError:
            fresh = None
        if fresh == source:
            return script
        # Write-then-replace with a per-writer temp name (pid + thread id):
        # every grader of a type shares one script (file_contract.py /
        # command_contract.py), so cross-process evaluation runs race this
        # file, and a concurrent subprocess must never exec a half-written
        # script. Same race class as the token store (M8-T156).
        temporary = grader_dir / f".{name}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            temporary.write_text(source, encoding="utf-8")
            for attempt in range(8):
                try:
                    os.replace(temporary, script)
                    break
                except PermissionError:
                    if attempt == 7:
                        raise
                    time.sleep(0.01 * (attempt + 1))
        finally:
            temporary.unlink(missing_ok=True)
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
        argv, input=json.dumps(spec), capture_output=True, text=True, errors="replace",
        cwd=str(workspace), timeout=timeout,
    )


_GRADER_REFUSED = 2


def _no_result(grader_type: str, reason: str, *, case_count: int | None = None,
               exit_code: int | None = None) -> dict[str, Any]:
    """The one constructor for "nobody judged this workspace".

    A grader that exited 2 and a grader the host could not run are the same
    verdict, so they have to be built in one place: a second literal is where
    the two drift apart, and where one of them slides back to passed=False.
    """
    out: dict[str, Any] = {
        "passed": None, "grader_type": grader_type, "grading_refused": True,
        "refusal": reason[:300],
    }
    if exit_code is not None:
        out["exit_code"] = exit_code
    if case_count is not None:
        out["case_count"] = case_count
    return out


def _refused(
    result: "subprocess.CompletedProcess[str]", grader_type: str, case_count: int | None = None
) -> dict[str, Any]:
    """The grader exited 2: it declined to judge this workspace at all.

    That is neither a pass nor a fail. ``build_report`` keeps rows with
    ``passed is None`` out of ``gradable``, so a refusal must arrive as None -
    folding it into False charges the agent for the grader's own inability and
    inflates ``false_completion_rate`` with a claim nobody verified.
    """
    first = next((line for line in result.stderr.splitlines() if line.strip()), "")
    return _no_result(
        grader_type, first, case_count=case_count, exit_code=result.returncode)


def grader_unable(grader_type: str, exc: BaseException) -> dict[str, Any]:
    """The grader process could not be run, or hung past its own clock.

    M8-T80 gave the exit-2 refusal a NO-RESULT channel; this is the same
    verdict arriving as an exception in the host instead - interpreter gone,
    grader directory unwritable, workspace removed mid-grade. Nobody looked at
    the work, so it is not a failure either.
    """
    return _no_result(grader_type, f"{type(exc).__name__}: {exc}")


def workspace_unwritable(grader_type: str, exc: BaseException) -> dict[str, Any]:
    """The host could not write the workspace this task is judged in.

    Same verdict as ``grader_unable``, different account: there a workspace
    existed and the grader could not be run on it; here nothing was ever
    written, so no agent ran either. Folding this into ``passed=False`` charged
    the agent for the host's own disk - measured on the plane before the fix:
    an ``OSError`` out of ``prepare_fixture`` booked ``pass_at_1=0.0`` for a
    task no agent ever attempted, and the diagnostic grader then re-judged the
    empty directory (M8-T107).
    """
    return _no_result(grader_type, f"{type(exc).__name__}: {exc}")


def run_interrupted(grader_type: str, exc: BaseException) -> dict[str, Any]:
    """The operator aborted the run while this task was on the bench.

    A third account, after "the host could not write the workspace" and "the
    grader could not be run": here the workspace and the grader are both fine and
    a person pressed Ctrl+C. The grading block is skipped for a row that never
    completed, so booking ``passed=False`` charged the agent for the operator,
    and re-running the diagnostic grader during an abort produced a reviewer
    false negative about a reviewer nobody asked (measured on ``9a9d55a``: an
    empty directory satisfied the contract, the oracle read ``passed: true`` with
    ``case_count: 1``, and ``reviewer_false_negative_count`` counted it; M8-T113).
    """
    detail = str(exc).strip()
    label = type(exc).__name__
    return _no_result(grader_type, f"{label}: {detail}" if detail else label)


def ungraded_verdict() -> dict[str, Any]:
    """The verdict for a task whose declared grader this host cannot run at all.

    Not a refusal, and the difference is load-bearing: a refusal says a grader
    existed and declined to look, so it carries ``grading_refused`` and the row is
    kept out of ``gradable``. This says nobody was ever going to look, so it
    carries no refusal flag - which is exactly why ``grading_refusal_count`` reads
    zero for it, and why ``no_grader_count`` reads zero too when the task *did*
    declare a grader (M8-T184 counts the tasks that declare none). The only trace
    such a row leaves is the denominator shrinking under ``grading_coverage``.

    Two modules hand-wrote this dict - ``grade_v2`` and ``grade_behavior`` - and
    on the shipped suites neither copy is reachable: every v2 task declares a type
    in ``GRADER_TYPES``, and every legacy task declares no grader at all, so the
    runner never calls ``grade_behavior`` for one. Two unreachable copies of the
    same verdict are not harmless: the day one of them gains a field, the other
    keeps the old shape and the report prints both identically, because
    ``markdown_report`` reads ``passed`` and ``grading_refused`` and nothing else.
    """
    return {"passed": None, "grader_type": "ungraded"}


#: Keys the host reads off a grader spec before the embedded script ever sees it.
#: The gate reconciles this against the shipped dispatch and producers by AST, so a
#: drift here is a red rather than a spec key that starts being silently rejected.
HOST_READ_KEYS = frozenset({"type", "timeout"})

_VOCAB_CACHE: dict[str, dict[str, frozenset[str]]] = {}


def _keys_read(tree: "ast.AST", base: str) -> set[str]:
    """Every key this code reads off ``base`` - subscript, ``.get``, or ``"k" in base``."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == base and node.args \
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            out.add(node.args[0].value)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
                and node.value.id == base and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            out.add(node.slice.value)
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.In) \
                and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str) \
                and isinstance(node.comparators[0], ast.Name) and node.comparators[0].id == base:
            out.add(node.left.value)
    return out


def grader_vocabulary(grader_type: str, script: str) -> dict[str, frozenset[str]]:
    """What a contract spec may contain, read out of the grader that will consume it.

    Handing a spec key nobody reads back as a pass is how a mistyped ``contains``
    silently deletes a check: the contract reports success having verified one fewer
    thing than the task author wrote.
    """
    cached = _VOCAB_CACHE.get(grader_type)
    if cached is None:
        tree = ast.parse(script)
        cached = {
            # The embedded scripts call their stdin payload "spec" or "data"; both are
            # the spec-level dictionary, so the walk must know either name.
            "spec": frozenset(_keys_read(tree, "spec") | _keys_read(tree, "data")
                               | HOST_READ_KEYS),
            "item": frozenset(_keys_read(tree, "item")),
        }
        _VOCAB_CACHE[grader_type] = cached
    return cached


def unverifiable_spec_keys(grader_type: str, script: str, spec: dict[str, Any]) -> list[str]:
    """Spec and per-item keys that neither the host nor the embedded grader reads."""
    vocab = grader_vocabulary(grader_type, script)
    unknown = sorted(set(spec) - vocab["spec"])
    for item in spec.get("files") or []:
        if isinstance(item, dict):
            unknown += [f"files[].{key}" for key in sorted(set(item) - vocab["item"])]
    return sorted(set(unknown))


def grade_file_contract(
    task: dict[str, Any], workspace: Path, *, grader_dir: Path | None = None
) -> dict[str, Any]:
    spec = task.get("grader") or {}
    files = spec.get("files") or []
    blockers = spec_blockers("file_contract", spec)
    if blockers:
        return _no_result("file_contract", "; ".join(blockers))
    try:
        result = _run_grader(
            "file_contract.py", _FILE_CONTRACT_GRADER,
            grader_dir or resolve_grader_dir(), workspace, spec,
            isolated=True, timeout=float(spec.get("timeout", 60)),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return grader_unable("file_contract", exc)
    if result.returncode == _GRADER_REFUSED:
        return _refused(result, "file_contract", len(files))
    marker = f"MINICC_FILE_CONTRACT_COMPLETE:{len(files)}"
    passed = result.returncode == 0 and marker in result.stdout.splitlines()
    return {
        "passed": passed, "grader_type": "file_contract",
        "case_count": len(files), "exit_code": result.returncode,
    }


#: Which embedded script consumes which shipped grader type. The gate reconciles its
#: keys against GRADER_TYPES, so a new contract type cannot be added without a script.
GRADER_SCRIPTS = {
    "file_contract": "_FILE_CONTRACT_GRADER",
    "command_contract": "_COMMAND_CONTRACT_GRADER",
}


def spec_blockers(grader_type: str, spec: dict[str, Any]) -> list[str]:
    """Why this spec cannot be judged at all - one answer for both enforcement doors.

    The loader raises and the grader refuses NO-RESULT from the same list, so neither can
    grow a private idea of "unusable" (which is how a malformed task ended up costing a
    full agent run before anything complained).
    """
    blockers: list[str] = []
    if grader_type == "file_contract":
        files = spec.get("files") or []
        if not files:
            blockers.append("file_contract lists no files: nothing was checked")
        elif not all(isinstance(item, dict) and isinstance(item.get("path"), str)
                     and item["path"].strip() for item in files):
            blockers.append("file_contract items need a non-empty string path")
    elif grader_type == "command_contract":
        command = spec.get("command")
        if not isinstance(command, str) or not command.strip():
            blockers.append("command_contract has no command to run")
    script = globals().get(GRADER_SCRIPTS.get(grader_type, ""), None)
    if isinstance(script, str):
        dead = unverifiable_spec_keys(grader_type, script, spec)
        if dead:
            blockers.append(f"{grader_type} spec has keys nobody reads: {dead}")
    return blockers


def spec_verifies_nothing(grader_type: str, reason: str) -> dict[str, Any]:
    """The spec named nothing to check, so nobody judged this workspace.

    Same verdict as a grader that could not run, reached through the one constructor:
    an empty contract, an unreadable one and a host-side refusal are three roads to "no
    look was taken", and none of them is the agent claiming work it did not do.
    """
    return _no_result(grader_type, reason)


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
    blockers = spec_blockers("command_contract", spec)
    if blockers:
        # ``cmd /c ""`` exits 0 and prints the marker, so an empty command used to
        # grade an untouched workspace as correct work.
        return _no_result("command_contract", "; ".join(blockers))
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
        return grader_unable("command_contract", exc)
    if result.returncode == _GRADER_REFUSED:
        return _refused(result, "command_contract")
    passed = result.returncode == 0 and "MINICC_COMMAND_CONTRACT_COMPLETE:1" in result.stdout.splitlines()
    return {"passed": passed, "grader_type": "command_contract", "exit_code": result.returncode}


def grade_v2(
    task: dict[str, Any], workspace: Path, answer: str = "", *, grader_dir: Path | None = None
) -> dict[str, Any]:
    """Dispatch a v2 task to its grader; signature mirrors ``grade_behavior``.

    The fallback is a safety net, not a path: ``run_benchmark`` only calls this for
    a type in ``GRADER_TYPES``, so today it cannot be reached from a run. The door
    in ``tests/test_every_declared_grader_type_reaches_a_grader.py`` holds that
    list against what this function actually dispatches, because the failure mode
    of a type added to ``GRADER_TYPES`` without a branch here is that every task
    of that type is accepted by ``validate_task``, graded as ``ungraded``, and
    counted by no metric at all.
    """
    grader = task.get("grader") or {}
    kind = grader.get("type")
    if kind == "file_contract":
        return grade_file_contract(task, workspace, grader_dir=grader_dir)
    if kind == "command_contract":
        return grade_command_contract(task, workspace, grader_dir=grader_dir)
    return ungraded_verdict()
