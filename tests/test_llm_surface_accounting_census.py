"""M8-T188: every LLM call face must name the surface that accounts its spend.

Arc closure for M8-T162/T163/T164/T165 -- four same-family holes (DAG nodes,
task subagents, the planner, the batch merge): each face spent through
``chat_with_cancellation`` while the surface that governs the run did not see
the money. The four were found one at a time; nothing structural prevented a
fifth. This census derives the population from the tree (AST walk of
``minicc/`` for calls to ``chat_with_cancellation``) and pins, per site, the
accounting statement in its named carrier. An aliased import would blind the
walk, so aliases are refused explicitly rather than silently missed.

Registry -- (file, enclosing def chain) -> where that face's spend is accounted:

1. ``loop.run_agent``            -> the run budget: ``record_usage`` +
    ``record_cost`` inside ``run_agent``; a trip is the named agent stop.
2. ``web.AgentService._chat_locked/execute/prepare_planner``
    -> the run budget: ``record_usage`` + ``record_cost`` priced on the
    planning route (M8-T164).
3. ``completion.judge_completion`` -> usage returned in the decision; charged
    by the caller ``web.AgentService._chat_locked/execute/record_review_usage``
    (review route; the caller that invokes it is also pinned -- a charge
    statement nobody calls is dead code).
4. ``web.AgentService.merge_batch/execute`` -> two surfaces, both pinned here:
    the batch parent's run budget (``record_usage`` + ``record_cost``, M8-T165),
    which the caller ``task_manager.TaskManager._watch_batch`` must arm by
    passing ``budget=``/``cost_estimator=`` built from
    ``AgentService.batch_merge_budget``; and the task usage row
    (``on_usage`` -> ``_watch_batch/on_merge_usage`` -> ``parent.update_usage``).
    A fold whose builder the caller never looks up, or a lookup naming a method
    that no longer exists, leaves the face silently un-armed -- both are caught.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "minicc"

CALL = "chat_with_cancellation"

REGISTRY = {
    ("minicc/agent/loop.py", ("run_agent",)),
    ("minicc/web.py", ("AgentService", "_chat_locked", "execute", "prepare_planner")),
    ("minicc/agent/completion.py", ("judge_completion",)),
    ("minicc/web.py", ("AgentService", "merge_batch", "execute")),
}

MERGE_BUILDER = "batch_merge_budget"

_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _files() -> list[Path]:
    return sorted(PKG.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))


def _enclosing_chain(node: ast.AST, lineno: int) -> tuple[str, ...]:
    """Names of the defs/classes containing ``lineno``, outermost first."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _DEFS):
            if child.lineno <= lineno <= (child.end_lineno or child.lineno):
                return (child.name,) + _enclosing_chain(child, lineno)
            continue
        found = _enclosing_chain(child, lineno)
        if found:
            return found
    return ()


def _call_sites() -> dict[tuple[str, tuple[str, ...]], int]:
    sites: dict[tuple[str, tuple[str, ...]], int] = {}
    for path in _files():
        tree = _parse(path)
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name == CALL:
                key = (rel, _enclosing_chain(tree, node.lineno))
                sites[key] = sites.get(key, 0) + 1
    return sites


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _aliased_imports() -> list[str]:
    out: list[str] = []
    for path in _files():
        tree = _parse(path)
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == CALL and alias.asname:
                        out.append(f"{rel}:{node.lineno} imports {CALL} as {alias.asname}")
    return out


def _subtree(tree: ast.Module, chain: tuple[str, ...]) -> ast.AST:
    """The def/class node whose full enclosing chain equals ``chain``."""

    def find(node: ast.AST, names: tuple[str, ...]) -> ast.AST | None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _DEFS):
                if names + (child.name,) == chain:
                    return child
                found = find(child, names + (child.name,))
                if found is not None:
                    return found
            else:
                found = find(child, names)
                if found is not None:
                    return found
        return None

    node = find(tree, ())
    assert node is not None, f"no definition chain {'/'.join(chain)} found"
    return node


def _calls_spelled(node: ast.AST, name: str) -> int:
    """Calls to ``name`` under ``node``, in either spelling (``x.name(...)`` or ``name(...)``).

    Learned from the preflight: ``on_usage`` is forwarded as a bare ``Name`` call
    inside ``merge_batch/execute``, so an Attribute-only counter read it as absent.
    """
    return sum(1 for child in ast.walk(node) if isinstance(child, ast.Call) and _call_name(child) == name)


def _calls_with_keyword(node: ast.AST, callee: str, keyword: str) -> int:
    """Calls to ``callee`` under ``node`` that pass ``keyword`` as a keyword argument."""
    return sum(
        1
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and _call_name(child) == callee
        and any(k.arg == keyword for k in child.keywords)
    )


def _getattr_literals(tree: ast.Module) -> set[str]:
    """The string names looked up through ``getattr(obj, "name", ...)``."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and _call_name(node) == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            out.add(node.args[1].value)
    return out


def _defs_named(tree: ast.Module, name: str) -> int:
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def test_every_llm_call_site_is_registered() -> None:
    sites = _call_sites()
    problems: list[str] = []
    for key in sorted(sites):
        if key not in REGISTRY:
            problems.append(
                f"unregistered LLM call site: {key[0]}::{ '/'.join(key[1]) or '<module>' } "
                f"({sites[key]} call(s)) -- its spend reaches no named accounting surface"
            )
        elif sites[key] != 1:
            problems.append(
                f"registered site carries {sites[key]} calls, expected exactly 1: "
                f"{key[0]}::{ '/'.join(key[1]) }"
            )
    for key in sorted(REGISTRY):
        if key not in sites:
            problems.append(
                f"registered site vanished from the tree: {key[0]}::{ '/'.join(key[1]) } "
                "-- update the registry consciously, or restore the face"
            )
    for line in _aliased_imports():
        problems.append(f"aliased import would blind this census: {line}")
    assert not problems, (
        "LLM-surface census mismatch -- every chat_with_cancellation face must be "
        "registered with the surface that accounts its spend:\n- " + "\n- ".join(problems)
    )
    assert len(sites) == len(REGISTRY) == 4, (
        f"population floor: {len(sites)} sites found vs {len(REGISTRY)} registry rows"
    )


def test_census_walk_reaches_the_package() -> None:
    files = _files()
    assert len(files) >= 70, (
        f"the walk reached only {len(files)} files under minicc/ -- the census is "
        "reading a hole, not the package"
    )
    chat_defs: set[str] = set()
    for path in files:
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "chat":
                chat_defs.add(path.relative_to(REPO).as_posix())
    for required in (
        "minicc/llm/anthropic_provider.py",
        "minicc/llm/fake.py",
        "minicc/llm/openai_provider.py",
    ):
        assert required in chat_defs, (
            f"the walk did not see the provider chat surface in {required}; "
            f"saw {sorted(chat_defs)}"
        )


def test_registered_sites_carry_their_accounting_statement() -> None:
    problems: list[str] = []

    loop_tree = _parse(PKG / "agent" / "loop.py")
    run_agent = _subtree(loop_tree, ("run_agent",))
    for attr in ("record_usage", "record_cost"):
        if not _calls_spelled(run_agent, attr):
            problems.append(
                f"minicc/agent/loop.py::run_agent: no {attr} call -- the main turn's "
                "spend reaches no budget"
            )

    web_tree = _parse(PKG / "web.py")
    planner = _subtree(
        web_tree, ("AgentService", "_chat_locked", "execute", "prepare_planner")
    )
    for attr in ("record_usage", "record_cost"):
        if not _calls_spelled(planner, attr):
            problems.append(
                f"minicc/web.py::prepare_planner: no {attr} call -- the planner's "
                "spend reaches no budget (M8-T164)"
            )

    judge_carrier = _subtree(
        web_tree, ("AgentService", "_chat_locked", "execute", "record_review_usage")
    )
    for attr in ("record_usage", "record_cost"):
        if not _calls_spelled(judge_carrier, attr):
            problems.append(
                f"minicc/web.py::record_review_usage: no {attr} call -- the judge's "
                "returned usage is never charged"
            )
    if not _calls_spelled(web_tree, "record_review_usage"):
        problems.append(
            "minicc/web.py: no caller invokes record_review_usage -- the judge's "
            "charge statement is dead code"
        )

    completion_tree = _parse(PKG / "agent" / "completion.py")
    judge = _subtree(completion_tree, ("judge_completion",))
    usage_handoff = any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute) and target.attr == "usage"
            for target in node.targets
        )
        for node in ast.walk(judge)
    )
    if not usage_handoff:
        problems.append(
            "minicc/agent/completion.py::judge_completion: no assignment to "
            "decision.usage -- the caller has nothing to charge"
        )

    merge = _subtree(web_tree, ("AgentService", "merge_batch", "execute"))
    for attr in ("record_usage", "record_cost"):
        if not _calls_spelled(merge, attr):
            problems.append(
                f"minicc/web.py::merge_batch/execute: no {attr} call -- the merge's "
                "spend reaches no budget ceiling (M8-T165)"
            )
    if not _calls_spelled(merge, "on_usage"):
        problems.append(
            "minicc/web.py::merge_batch/execute: response.usage is not forwarded via "
            "on_usage -- the merge spend vanishes from the task's usage rows"
        )

    tm_tree = _parse(PKG / "task_manager.py")
    for keyword in ("budget", "cost_estimator"):
        if not _calls_with_keyword(tm_tree, "merge_batch", keyword):
            problems.append(
                f"minicc/task_manager.py: the merge_batch call does not pass {keyword}= "
                "-- the merge's fold statement exists but no ceiling is armed for it"
            )
    if MERGE_BUILDER not in _getattr_literals(tm_tree):
        problems.append(
            f"minicc/task_manager.py: nothing looks up {MERGE_BUILDER} via getattr -- "
            "the merge budget would silently stay None and the fold would never charge"
        )
    if not _defs_named(web_tree, MERGE_BUILDER):
        problems.append(
            f"minicc/web.py: no method named {MERGE_BUILDER} builds the merge ceiling -- "
            "the caller's lookup resolves to nothing and the face is un-armed"
        )

    on_merge = _subtree(tm_tree, ("TaskManager", "_watch_batch", "on_merge_usage"))
    if not _calls_spelled(on_merge, "update_usage"):
        problems.append(
            "minicc/task_manager.py::on_merge_usage: no parent.update_usage call -- "
            "the merge spend lands in no usage row"
        )

    assert not problems, (
        "LLM call faces with an unbound accounting statement:\n- " + "\n- ".join(problems)
    )
