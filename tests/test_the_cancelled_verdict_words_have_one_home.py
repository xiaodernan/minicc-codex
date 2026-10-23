"""The user-cancel verdict's words must have exactly one home.

A cancelled run carries the same three fields wherever it is cancelled from:
the flag, the short error, and the sentence the user reads.  Twenty-six sites
spelled those words out by hand - six in the agent loop, one in the worker,
three in the task manager, two on the web face - so the notice, the error and
the flag each had a dozen spellings across four modules.  A rename reached
only the sites somebody remembered: a cancelled task then answered one wording
on one face and the old wording on another, and nothing failed anywhere.

The words now live in :mod:`minicc.agent.protocol` with the rest of the answer
and error vocabulary, and the three-field stamp lives once beside ``TurnResult``.

The census needs one discriminator the earlier batches did not: ``任务已取消``
is the **prefix of a family** of longer sentences - ``任务已取消，已中止模型请
求``, ``任务已取消，未执行工具 X``, ``任务已取消，审批自动拒绝``,
``任务已取消，自动验证已停止。`` - and every one of them is a different fact
about a different moment.  A tree-wide "starts with" census would swallow them
all (M8-T472/T475).  The verdict is the one form that **stops**: it ends the
sentence instead of continuing it with ``，``.  So the rule is: a constant that
begins with the cancel word and does not continue into another sentence *is*
the verdict, and there is exactly one of each.
"""

from __future__ import annotations

import ast
import pathlib

from minicc.agent.loop import TurnResult, stamp_cancelled
from minicc.agent.protocol import TASK_CANCELLED_ANSWER, TASK_CANCELLED_ERROR
from minicc.task_manager import _cancelled_result

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = "minicc/agent/protocol.py"
STAMP_HOME = "minicc/agent/loop.py"
WEB = "minicc/web.py"
ERROR = TASK_CANCELLED_ERROR
ANSWER = TASK_CANCELLED_ANSWER
CONTINUES = "，"


def _trees():
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, ast.parse(path.read_bytes().decode("utf-8"))


def _is_dict_key(node: ast.AST, parents: dict[int, ast.AST]) -> bool:
    parent = parents.get(id(node))
    return isinstance(parent, ast.Dict) and node in parent.keys


def _value_constants() -> list[tuple[str, int, str]]:
    """Every string constant in a value position - f-string parts included."""
    found = []
    for path, tree in _trees():
        parents: dict[int, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[id(child)] = node
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _is_dict_key(node, parents):
                    continue
                found.append((path.relative_to(REPO).as_posix(), node.lineno, node.value))
    return found


def _call_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


# --- the words ----------------------------------------------------------------


def test_the_two_words_are_pinned():
    assert ERROR == "任务已取消"
    assert ANSWER == "任务已取消。"


def test_the_error_word_has_exactly_one_home():
    hits = [hit for hit in _value_constants() if hit[2] == ERROR]
    assert len(hits) == 1, hits
    assert hits[0][0] == HOME, hits


def test_the_answer_word_has_exactly_one_home():
    hits = [hit for hit in _value_constants() if hit[2] == ANSWER]
    assert len(hits) == 1, hits
    assert hits[0][0] == HOME, hits


def test_no_other_constant_begins_with_the_cancel_word():
    """A constant that begins with the verdict and stops is the verdict.

    The family members that continue with ``，`` are different facts about
    different moments and stay where they are; so does the batch notice, which
    does not even begin with the cancel word.
    """
    strays = []
    for rel, lineno, value in _value_constants():
        if not value.startswith(ERROR):
            continue
        if value in (ERROR, ANSWER):
            continue
        if CONTINUES in value:
            continue
        strays.append((rel, lineno, value[:60]))
    assert strays == [], strays


def test_the_batch_notice_is_still_a_different_fact():
    """A cancelled batch is not a cancelled task; the words must not merge."""
    hits = [hit for hit in _value_constants() if hit[2] == "批量任务已取消。"]
    assert hits, "the batch notice disappeared - it is its own fact"
    assert all(hit[2] != ANSWER for hit in hits), hits


# --- the stamp ----------------------------------------------------------------


def test_the_stamp_is_defined_exactly_once():
    definitions = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name == "stamp_cancelled":
                definitions.append(path.relative_to(REPO).as_posix())
    assert definitions == [STAMP_HOME], definitions


def test_the_stamp_is_called_from_every_cancelled_site():
    sites = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node.func) == "stamp_cancelled":
                sites.append(path.relative_to(REPO).as_posix())
    assert len(sites) == 7, sites
    assert sum(site == STAMP_HOME for site in sites) == 6, sites
    assert sum(site == WEB for site in sites) == 1, sites


def test_the_stamp_sets_the_three_fields_a_reader_uses():
    stamped = stamp_cancelled(TurnResult(answer="partial answer"))
    assert stamped.cancelled is True
    assert stamped.error == ERROR
    assert stamped.answer == ANSWER


def test_the_stamp_overwrites_what_the_run_produced():
    stamped = stamp_cancelled(TurnResult(answer="half a turn", turns=3, tool_calls_total=2))
    assert stamped.answer == ANSWER
    assert stamped.turns == 3, "the stamp is a verdict, not a reset"
    assert stamped.tool_calls_total == 2


def test_the_manager_dict_and_the_stamp_agree():
    """Two shapes of one verdict: the payload dict and the run object."""
    stamped = stamp_cancelled(TurnResult(answer=""))
    payload = _cancelled_result({})
    assert payload["answer"] == stamped.answer == ANSWER
    assert payload["error"] == stamped.error == ERROR
    assert payload["cancelled"] is stamped.cancelled is True
