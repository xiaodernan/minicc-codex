"""Small isolated coding tasks with behavior graders kept outside the workspace.

The fixture suite is intentionally inspectable and versioned. Grading code is
never placed in the agent's task directory; it is run only after execution.
Passing this suite measures these cases, not general coding capability.
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import bench_tasks

SUITE_VERSION = "behavior-1"

# Each task specifies user-visible starter code and independent input/output
# cases. Additional edge cases prevent merely matching the happy-path prompt.
_CASES = [
    ("clamp", "将数值限制到闭区间 [lower, upper]，上下界颠倒时抛 ValueError。", "def clamp(value, lower, upper):\n    return max(value, upper)\n", [[[-3, 0, 10], 0], [[15, 0, 10], 10], [[5, 0, 10], 5], [[0, 0, 0], 0]], [[[0, 3, 1], "ValueError"]]),
    ("chunks", "按正整数 size 分块，保留最后不足一块的数据，空输入返回空列表；size<=0 抛 ValueError。", "def chunks(items, size):\n    return [items[:size]]\n", [[[[1, 2, 3, 4, 5], 2], [[1, 2], [3, 4], [5]]], [[[], 3], []], [[[1, 2], 4], [[1, 2]]]], [[[[1], 0], "ValueError"], [[[1], -1], "ValueError"]]),
    ("dedupe", "保持输入顺序去重，支持相等的列表元素（不能要求元素可哈希）。", "def dedupe(items):\n    return sorted(set(items))\n", [[[[3, 1, 3, 2, 1]], [3, 1, 2]], [[[]], []], [[[[1], [2], [1]]], [[1], [2]]]], []),
    ("median", "返回排序后的中位数，偶数项取中间两项均值；不修改原输入；空输入抛 ValueError。", "def median(items):\n    return items[len(items)//2]\n", [[[[9, 1, 4]], 4], [[[4, 1, 3, 2]], 2.5], [[[-4, -2]], -3]], [[[[]], "ValueError"]]),
    ("slugify", "生成 URL slug：转小写，连续非 ASCII 字母数字替换为一个横线，去掉首尾横线。", "def slugify(text):\n    return text.lower().replace(' ', '-')\n", [[["  Hello, World!  "], "hello-world"], [["A___B"], "a-b"], [["***"], ""], [["One 2 THREE"], "one-2-three"]], []),
    ("merge_counts", "合并多个字典的计数，同键相加；不修改传入字典；空列表返回空字典。", "def merge_counts(items):\n    result = {}\n    for item in items:\n        result.update(item)\n    return result\n", [[[[{"a": 2}, {"a": 3, "b": 1}]], {"a": 5, "b": 1}], [[[]], {}], [[[{"x": -2}, {"x": 1}]], {"x": -1}]], []),
    ("parse_bool", "解析布尔字符串，忽略首尾空白及大小写；true/1/yes 为真，false/0/no 为假；其他值抛 ValueError。", "def parse_bool(text):\n    return bool(text)\n", [[["false"], False], [[" TRUE "], True], [["0"], False], [["Yes"], True], [[" no "], False]], [[["maybe"], "ValueError"], [[""], "ValueError"]]),
    ("paginate", "页码从 1 起，size 必须为正数；返回指定页，超出范围返回空列表；page<1 或 size<1 抛 ValueError。", "def paginate(items, page, size):\n    return items[page*size:(page+1)*size]\n", [[[[1, 2, 3, 4, 5], 1, 2], [1, 2]], [[[1, 2, 3, 4, 5], 3, 2], [5]], [[[1], 9, 2], []]], [[[[1], 0, 2], "ValueError"], [[[1], 1, 0], "ValueError"]]),
    ("interval_overlap", "计算两个半开区间 [start,end) 的重叠长度；不重叠或相接返回 0；任一区间 end<start 抛 ValueError。", "def interval_overlap(a, b):\n    return min(a[1], b[1]) - max(a[0], b[0])\n", [[[[0, 5], [3, 7]], 2], [[[0, 1], [2, 4]], 0], [[[0, 3], [3, 6]], 0], [[[-4, 4], [-1, 1]], 2]], [[[[4, 1], [0, 3]], "ValueError"]]),
    ("moving_average", "返回每个完整窗口的算术平均值，窗口不足返回空列表，窗口大小<=0 抛 ValueError；不改变输入。", "def moving_average(items, window):\n    return [sum(items)/len(items)]\n", [[[[1, 2, 3, 4], 2], [1.5, 2.5, 3.5]], [[[1], 2], []], [[[], 1], []], [[[-2, 2], 1], [-2, 2]]], [[[[1], 0], "ValueError"]]),
    ("flatten_once", "只展开一层列表；非列表元素原样保留，字符串不能拆开；空列表返回空列表。", "def flatten_once(items):\n    return [value for item in items for value in item]\n", [[[[1, [2, 3], "ab", [], [[4]]]], [1, 2, 3, "ab", [4]]], [[[]], []], [[[None, False]], [None, False]]], []),
    ("safe_divide", "除数为 0 时返回调用者给出的 default（默认 None）；其他情况正常除法，不吞掉类型错误。", "def safe_divide(a, b, default=None):\n    return a / b\n", [[[6, 3], 2], [[6, 0], None], [[6, 0, "n/a"], "n/a"], [[-3, 2], -1.5]], [[["bad", 2], "TypeError"]]),
]


def behavior_tasks() -> list[dict[str, Any]]:
    return [
        {
            "id": f"behavior-{name}", "category": "edit", "suite_version": SUITE_VERSION,
            "prompt": f"修复 solution.py 中的 {name}。要求：{description} 请添加有针对性的本地测试，保持函数签名。",
            "fixture": {"solution.py": code, "README.md": description + "\n"},
            "grader": {"type": "python_behavior", "function": name, "cases": cases, "raises": raises, "preserve_inputs": True},
        }
        for name, description, code, cases, raises in _CASES
    ]


def fixture_digest(task: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(task, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


_GRADER = '''import copy, importlib.util, json, sys
from pathlib import Path

def matches(actual, expected):
    # Python considers True == 1 and False == 0. A boolean parser returning
    # integers must not pass a boolean contract (or vice versa).
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(matches(a, e) for a, e in zip(actual, expected))
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(matches(actual[key], value) for key, value in expected.items())
    return actual == expected

root = Path(sys.argv[1]).resolve()
data = json.loads(sys.stdin.read())
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("evaluated_solution", root / "solution.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
function = getattr(module, data["function"])
for args, expected in data["cases"]:
    inputs = copy.deepcopy(args)
    actual = function(*inputs)
    assert matches(actual, expected), "behavior mismatch"
    if data.get("preserve_inputs"):
        assert matches(inputs, args), "input mutated"
for args, expected_type in data.get("raises", []):
    inputs = copy.deepcopy(args)
    try:
        function(*inputs)
    except Exception as exc:
        assert type(exc).__name__ == expected_type, "incorrect exception"
    else:
        raise AssertionError("required exception not raised")
    if data.get("preserve_inputs"):
        assert matches(inputs, args), "input mutated on exception"
# The grader runs as a standalone subprocess script, so it writes its marker to
# stdout directly instead of importing minicc.cli_io.
sys.stdout.write("MINICC_BEHAVIOR_COMPLETE:" + str(len(data["cases"]) + len(data.get("raises", []))) + "\\n")
'''


#: Keys the answer-rubric grader reads for itself. ``HOST_READ_KEYS`` covers what the
#: dispatcher reads off the same dict. Reconciled against this function's own AST by
#: tests/test_rubric_vocabulary_is_branch_scoped.py - a declaration nobody checks is how
#: the merged list started out.
RUBRIC_SPEC_KEYS = frozenset({"required_any"})


#: Grader types this module's script understands. Reconciled by the gate against the types
#: ``grade_behavior`` actually dispatches on, so the list cannot be hand-kept.
BEHAVIOR_GRADER_TYPES = frozenset({"python_behavior", "answer_rubric"})


def _json_roundtrips(value: object) -> bool:
    """Whether a value survives the ``json.dumps`` that hands the spec to the grader.

    That encode happens in the host and ``grade_behavior`` catches only ``OSError`` and
    ``TimeoutExpired``, so a non-serialisable arg would raise out of the grader call - one
    malformed task could abort an entire run instead of yielding a row.
    """
    try:
        json.loads(json.dumps(value))
    except (TypeError, ValueError):
        return False
    return True


def spec_blockers(task: dict[str, Any]) -> list[str]:
    """Why a behaviour grader spec can judge nothing - the single owner for both doors.

    Contracts keep their equivalent in ``bench_tasks``: that module cannot import this one
    without a cycle, so ownership is per domain and the gate checks each domain keeps one
    copy of its own wording.
    """
    grader = task.get("grader") or {}
    kind = grader.get("type")
    blockers: list[str] = []
    if kind == "answer_rubric":
        unknown = sorted(set(grader) - RUBRIC_SPEC_KEYS - bench_tasks.HOST_READ_KEYS)
        if unknown:
            blockers.append(f"answer_rubric spec has keys nobody reads: {unknown}")
        groups = grader.get("required_any") or []
        if not groups:
            blockers.append("answer_rubric lists no required_any groups: nothing was checked")
        for index, group in enumerate(groups):
            if not isinstance(group, list) or not group:
                blockers.append(
                    f"answer_rubric required_any[{index}] 必须是非空 list，收到 {group!r}")
                continue
            for term in group:
                if not isinstance(term, str) or not term.strip():
                    blockers.append(
                        f"answer_rubric required_any[{index}] 每一项必须是非空字符串，收到 {term!r}")
                    break
    elif kind == "python_behavior":
        dead = bench_tasks.unverifiable_spec_keys("python_behavior", _GRADER, grader)
        if dead:
            blockers.append(f"python_behavior spec has keys nobody reads: {dead}")
        if not (grader.get("cases") or []) and not (grader.get("raises") or []):
            blockers.append("python_behavior spec has no cases or raises: nothing was checked")
    return blockers


def defined_names(code: str) -> set[str]:
    """Names a module binds at top level: defs, classes and plain assignments."""
    names: set[str] = set()
    for node in ast.parse(code).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def fixture_blockers(task: dict[str, Any]) -> list[str]:
    """Why this behaviour task can never be graded as written - read from its own fixture.

    The grader imports ``solution.py`` and looks up ``grader.function``. If the shipped fixture
    never binds that name, no agent action can make the task scoreable, so the refusal belongs at
    load time - while an agent that deletes the function from *its* workspace has really failed
    and must still get a verdict.
    """
    grader = task.get("grader") or {}
    if grader.get("type") != "python_behavior":
        return []
    function = grader.get("function")
    code = (task.get("fixture") or {}).get("solution.py")
    if not isinstance(code, str):
        return [f"python_behavior 任务缺少 fixture solution.py，无法校验被评函数 {function!r}"]
    try:
        names = defined_names(code)
    except SyntaxError as exc:
        return [f"python_behavior 任务 fixture solution.py 无法解析: {exc.msg}"]
    if not isinstance(function, str) or function not in names:
        return [f"python_behavior 任务的 fixture 未定义被评函数 {function!r}，任何智能体都无从通过"]
    blockers: list[str] = []
    for index, case in enumerate(grader.get("cases") or []):
        if not (isinstance(case, list) and len(case) == 2 and isinstance(case[0], list)):
            blockers.append(
                f"python_behavior cases[{index}] 必须是 [args, expected] 且 args 为 list，收到 {case!r}"
            )
        elif not _json_roundtrips(case[0]):
            blockers.append(
                f"python_behavior cases[{index}] 的 args 必须能通过 JSON 传递，收到 {case[0]!r}"
            )
    for index, case in enumerate(grader.get("raises") or []):
        if not (isinstance(case, list) and len(case) == 2 and isinstance(case[0], list)
                and isinstance(case[1], str)):
            blockers.append(
                f"python_behavior raises[{index}] 必须是 [args, 异常名] 且 args 为 list，收到 {case!r}"
            )
    return blockers


def validate_behavior_task(task: dict[str, Any]) -> None:
    """Load-time door: an unscoreable behaviour task must not reach the agent."""
    grader = task.get("grader") or {}
    kind = grader.get("type")
    if kind not in BEHAVIOR_GRADER_TYPES:
        raise ValueError(f"任务 {task.get('id')} grader 类型非法: {kind}")
    blockers = spec_blockers(task) + fixture_blockers(task)
    if blockers:
        raise ValueError(f"任务 {task.get('id')} grader 规格无法判分: {'; '.join(blockers)}")


def grade_answer_rubric(task: dict[str, Any], answer: str = "") -> dict[str, Any]:
    """Grade a text answer against required-any groups; the only reader of the rubric spec.

    Split out of ``grade_behavior`` so its vocabulary has a branch-sized subject: while
    both graders shared one function, the only list derivable from it was the union of
    their keys, which silently accepted ``cases`` in a rubric and ``required_any`` in a
    behaviour spec.
    """
    grader = task.get("grader") or {}
    blockers = spec_blockers(task)
    if blockers:
        # An empty rubric used to answer passed=False, charging the agent for the
        # grader's own blank spec.
        return bench_tasks.spec_verifies_nothing("answer_rubric", "; ".join(blockers))
    folded = answer.casefold()
    groups = grader.get("required_any") or []
    passed = all(any(str(term).casefold() in folded for term in group) for group in groups)
    return {"passed": passed, "grader_type": "answer_rubric", "case_count": len(groups)}


def grade_behavior(task: dict[str, Any], workspace: Path, answer: str = "") -> dict[str, Any]:
    grader = task.get("grader") or {}
    if grader.get("type") == "answer_rubric":
        return grade_answer_rubric(task, answer)
    if grader.get("type") != "python_behavior":
        return {"passed": None, "grader_type": "ungraded"}
    blockers = spec_blockers(task)
    if blockers:
        # Zero cases still prints the completion marker for zero, which used to grade
        # an untouched workspace as correct work.
        return bench_tasks.spec_verifies_nothing("python_behavior", "; ".join(blockers))
    count = len(grader.get("cases") or []) + len(grader.get("raises") or [])
    try:
        payload = json.dumps(grader)
    except (TypeError, ValueError) as exc:
        # The spec is encoded here, in the host. If that fails, nobody looked at the
        # workspace at all, so there is no verdict to give - and the alternative is a
        # TypeError travelling up through run_benchmark and taking the whole suite down.
        return bench_tasks.spec_verifies_nothing(
            "python_behavior", f"python_behavior 规格无法编码送进评分器: {type(exc).__name__}: {exc}")
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", _GRADER, str(workspace.resolve())],
            input=payload, capture_output=True, text=True, errors="replace",
            cwd=workspace, timeout=20,
        )
        marker = f"MINICC_BEHAVIOR_COMPLETE:{count}"
        return {"passed": result.returncode == 0 and marker in result.stdout.splitlines(), "grader_type": "python_behavior", "case_count": count, "exit_code": result.returncode}
    except (OSError, subprocess.TimeoutExpired) as exc:
        # The grader subprocess could not be started or hung: nobody looked at
        # the workspace, so this row has no verdict. M8-T83 removed the
        # passed=False + error shape from the contract graders for the same
        # reason - "error" also shadowed the agent's own diagnosis.
        return bench_tasks.grader_unable("python_behavior", exc)


def prepare_fixture(task: dict[str, Any], workspace: Path, *, initialize_git: bool = False) -> None:
    for relative, content in task.get("fixture", {}).items():
        target = (workspace / relative).resolve()
        if not target.is_relative_to(workspace.resolve()):
            raise ValueError("fixture path escapes workspace")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
    if initialize_git:
        # A baseline lets the agent inspect its actual diff without unrelated
        # failures from git tools. No global Git identity/config is changed.
        # The baseline commit is internal bookkeeping, so it must never run the
        # user's hooks: on a machine whose global `core.hooksPath` points at a
        # real hook directory, a single `git commit` took 20.8s and every
        # fixture task died with `TimeoutExpired` at the old 15s budget.
        # `core.hooksPath=` (empty) disables the hook lookup and `--no-verify`
        # skips pre-commit/commit-msg; the timeout now tolerates a slow
        # filesystem instead of assuming a fast one.
        for args in (
            ["init", "-q"],
            ["add", "--", "."],
            [
                "-c", "core.hooksPath=",
                "-c", "user.name=MiniCC Benchmark",
                "-c", "user.email=benchmark@example.invalid",
                "-c", "commit.gpgsign=false",
                "commit", "-qm", "Behavior fixture baseline", "--no-verify",
            ],
        ):
            subprocess.run(["git", *args], cwd=workspace, check=True, capture_output=True, timeout=60)
