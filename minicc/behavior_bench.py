"""Small isolated coding tasks with behavior graders kept outside the workspace.

The fixture suite is intentionally inspectable and versioned. Grading code is
never placed in the agent's task directory; it is run only after execution.
Passing this suite measures these cases, not general coding capability.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def grade_behavior(task: dict[str, Any], workspace: Path, answer: str = "") -> dict[str, Any]:
    grader = task.get("grader") or {}
    if grader.get("type") == "answer_rubric":
        folded = answer.casefold()
        groups = grader.get("required_any", [])
        passed = bool(groups) and all(any(str(term).casefold() in folded for term in group) for group in groups)
        return {"passed": passed, "grader_type": "answer_rubric", "case_count": len(groups)}
    if grader.get("type") != "python_behavior":
        return {"passed": None, "grader_type": "ungraded"}
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", _GRADER, str(workspace.resolve())],
            input=json.dumps(grader), capture_output=True, text=True,
            cwd=workspace, timeout=20,
        )
        count = len(grader.get("cases", [])) + len(grader.get("raises", []))
        marker = f"MINICC_BEHAVIOR_COMPLETE:{count}"
        return {"passed": result.returncode == 0 and marker in result.stdout.splitlines(), "grader_type": "python_behavior", "case_count": count, "exit_code": result.returncode}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"passed": False, "grader_type": "python_behavior", "error": type(exc).__name__}


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
