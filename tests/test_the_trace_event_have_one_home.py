"""M8-T411 / M8-T532 - the trace event has one home; the gate now asks *reach*.

Batch 411 landed ``minicc/trace.py:trace_event`` as the only place that spells the
record, and pinned it with ``assert "trace_event" in source`` over eight hand-copied
module names. That question is about *names*, and names move: ``1c12ec5`` (batch 482)
moved the anthropic provider's channel-switch record behind
``minicc/llm/usage.py:channel_switched_event`` - a same-package factory that asks the
home - and the gate has been red for 59 commits over a reason that is not a defect.
A permanently red gate teaches the next reader to skip the red.

Measured on the shipped bytes (batch 514 §2, working tree and clean HEAD plane read
the same): **ten** modules reach the home, the list declared **eight**, and the two
the list could not see are exactly the two factories (``minicc/agent/protocol.py``,
``minicc/llm/usage.py``). So the set is now *derived* and compared against the
*declared* tuple: the number stays visible (a shrinking list is still a red) while
spelling stops being the evidence.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME_FILE = "minicc/trace.py"
HOME_FUNCTION = "trace_event"

#: Every module that emits a trace event. Declared on purpose: the gate derives the
#: same set independently and refuses to let the two drift.
EMITTERS = (
    "minicc/agent/loop.py",
    "minicc/agent/protocol.py",
    "minicc/agent/subagent.py",
    "minicc/llm/anthropic_provider.py",
    "minicc/llm/fake.py",
    "minicc/llm/openai_provider.py",
    "minicc/llm/usage.py",
    "minicc/main.py",
    "minicc/task_manager.py",
    "minicc/web.py",
)

#: A floor, not a measurement: if the walk goes blind the derived set is empty, and
#: comparing two empty sets is trivially satisfiable.
_MIN_REACHING_MODULES = 5


def _trace_dict_literals(path: Path) -> list[ast.Dict]:
    """Dict literals that spell ``"kind": "trace"`` - the record's signature."""
    tree = ast.parse(path.read_bytes().decode("utf-8"))
    found: list[ast.Dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant) and key.value == "kind"
                and isinstance(value, ast.Constant) and value.value == "trace"
            ):
                found.append(node)
                break
    return found


def _callee_name(fn: ast.expr) -> str | None:
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        base = _callee_name(fn.value)
        return f"{base}.{fn.attr}" if base else None
    return None


def _call_scopes() -> tuple[
    dict[str, dict[str, str]],
    dict[tuple[str, str], set[str]],
    dict[str, set[str]],
]:
    """Per file: imported-name bindings, per-scope call targets, per-file scope names.

    Three details carry this batch's claim:

    - relative imports resolve against the **declaring file's package**, so
      ``from ..trace import trace_event`` in ``minicc/agent/loop.py`` reads as
      ``minicc.trace`` and ``from .usage import channel_switched_event`` in
      ``minicc/llm/`` reads as ``minicc.llm.usage``. That is what makes a factory
      visible;
    - calls at **module level** count like calls inside a function. A walker that
      only descends into functions reports ``minicc/llm/fake.py`` as never asking the
      home, because it builds its fixtures with ``measured_usage(…)`` at import time
      (measured in batch 514 - that was the probe's bug, not the product's);
    - edges are keyed by **symbol**, not by file. The file-granularity shortcut was
      tried and is wrong by three: ``minicc/agent/completion.py:23`` imports
      ``classify_provider_failure``, ``minicc/benchmarks.py:31`` imports
      ``fake_provider_active`` and ``minicc/task_worker.py:35`` imports two
      *constants* from ``agent.protocol`` - all three sit in files that reach the
      home, and none of the three asks it.
    """
    binds: dict[str, dict[str, str]] = {}
    scopes: dict[tuple[str, str], set[str]] = {}
    names_by_file: dict[str, set[str]] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        try:
            tree = ast.parse(path.read_bytes().decode("utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        package_parts = relative[: -len(".py")].replace("/", ".").split(".")[:-1]
        own: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    own[alias.asname or alias.name.split(".")[0]] = alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = ".".join(package_parts[: len(package_parts) - (node.level - 1)])
                    prefix = f"{base}.{node.module}" if base and node.module else (base or node.module or "")
                else:
                    prefix = node.module or ""
                for alias in node.names:
                    own[alias.asname or alias.name] = (
                        f"{prefix}.{alias.name}" if prefix else alias.name
                    )
        binds[relative] = own
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        names_by_file[relative] = names

        def walk(owner: str, node: ast.AST) -> None:
            bucket = scopes.setdefault((relative, owner), set())
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    walk(f"{owner}.{child.name}" if owner else child.name, child)
                    continue
                if isinstance(child, ast.ClassDef):
                    walk(f"{owner}.{child.name}" if owner else child.name, child)
                    continue
                if isinstance(child, ast.Call):
                    name = _callee_name(child.func)
                    if name:
                        bucket.add(name)
                walk(owner, child)

        for top in tree.body:
            if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(top.name, top)
            elif isinstance(top, ast.ClassDef):
                for member in top.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        walk(f"{top.name}.{member.name}", member)
            else:
                walk("", top)
    return binds, scopes, names_by_file


def _dotted_to_file(dotted: str, files: set[str]) -> tuple[str, str] | None:
    """``minicc.llm.usage.channel_switched_event`` -> ``('minicc/llm/usage.py', ...)``."""
    module, _, symbol = dotted.rpartition(".")
    if not module or not symbol:
        return None
    candidate = f"{module.replace('.', '/')}.py"
    return (candidate, symbol) if candidate in files else None


def _resolve(
    binds: dict[str, dict[str, str]],
    names_by_file: dict[str, set[str]],
    scopes_by_file: dict[str, set[str]],
    relative: str,
    name: str,
) -> tuple[str, str] | None:
    head = name.split(".")[0]
    if head in binds[relative]:
        return _dotted_to_file(binds[relative][head] + name[len(head):], set(binds))
    if name.startswith("self."):
        return None
    if name in names_by_file[relative]:
        return (relative, name)
    suffix = "." + name
    for scoped in scopes_by_file.get(relative, set()):
        if scoped.endswith(suffix):
            return (relative, scoped)
    return None


def _nodes_asking_the_home() -> set[tuple[str, str]]:
    binds, scopes, names_by_file = _call_scopes()
    scopes_by_file: dict[str, set[str]] = {}
    for (relative, owner) in scopes:
        if owner:
            scopes_by_file.setdefault(relative, set()).add(owner)
    home = (HOME_FILE, HOME_FUNCTION)
    asking = {home}
    changed = True
    while changed:
        changed = False
        for (relative, owner), targets in scopes.items():
            if not owner:
                continue
            node = (relative, owner)
            if node in asking:
                continue
            for name in targets:
                got = _resolve(binds, names_by_file, scopes_by_file, relative, name)
                if got and got in asking:
                    asking.add(node)
                    changed = True
                    break
    return asking


def _modules_asking_the_home() -> set[str]:
    return {file for (file, _owner) in _nodes_asking_the_home()} - {HOME_FILE}


def test_the_home_builds_the_record() -> None:
    """The constructor owns the seven keys and their order."""
    from minicc.trace import trace_event

    event = trace_event(
        name="planner", status="error", phase="planning",
        code="planner_fixed_fallback", summary="回退固定模板",
        detail={"reason": "unsafe"},
    )
    assert list(event) == [
        "kind", "name", "status", "phase", "code", "summary", "detail",
    ]
    assert event["kind"] == "trace"
    assert event["detail"] == {"reason": "unsafe"}


def test_a_milestone_without_a_payload_omits_detail() -> None:
    """The loop's old shape: six keys, no ``detail`` key at all."""
    from minicc.trace import trace_event

    event = trace_event("agent", "ok", "answering", "milestone", "开始回答")
    assert "detail" not in event
    assert list(event) == ["kind", "name", "status", "phase", "code", "summary"]


def test_every_emitter_asks_the_home() -> None:
    """Reach, not spelling.

    The name stays: eleven shipped citations point at it, and the question it
    asks never changed - only what counts as an answer.

    The shipped gate printed ``minicc/llm/anthropic_provider.py must ask the one
    home`` for 59 commits while that module asked it through
    ``llm/usage.channel_switched_event``: the record was the home's, the *name* was
    not in the file.
    """
    reached = _modules_asking_the_home()
    missing = sorted(set(EMITTERS) - reached)
    assert not missing, (
        "declared emitters with no call path to the trace home - either the module "
        "stopped emitting, or it now goes through something the walk cannot follow: "
        + ", ".join(missing)
    )


def test_the_declared_list_is_the_set_that_reaches_the_home() -> None:
    """Neither direction of drift passes quietly.

    Blind (reaches, undeclared) was the measured state on shipped bytes: ten modules
    reach the home, eight were declared, and the two invisible ones are the two
    factories - so a *third* factory would never be asked at all.
    """
    reached = _modules_asking_the_home()
    declared = set(EMITTERS)
    blind = sorted(reached - declared)
    stale = sorted(declared - reached)
    assert not blind and not stale, (
        "the emitter list and the call graph disagree | "
        f"reaches but undeclared: {', '.join(blind) or '(none)'} | "
        f"declared but no longer reaches: {', '.join(stale) or '(none)'}"
    )


def test_the_walk_is_not_read_from_an_empty_graph() -> None:
    """Anti-vacuity, in two halves: the *reach* set and the walk under it."""
    binds, scopes, names_by_file = _call_scopes()
    reached = _modules_asking_the_home()
    assert len(reached) >= _MIN_REACHING_MODULES, (
        f"only {len(reached)} modules reach the trace home; the walk is probably "
        "blind (no scopes recorded, or the home moved) and an empty derived set "
        "would make the list comparison green by accident"
    )
    assert len(binds) >= 50, (
        f"the walk parsed {len(binds)} files out of minicc/; that is not a package "
        "reading, that is a walk that stopped seeing"
    )
    assert sum(len(targets) for targets in scopes.values()) > 1000, (
        "the walk recorded too few call targets to be the same measurement"
    )


def test_the_record_is_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second shape.

    The count is exact (not "all inside the home") because the T396 lesson applies:
    the loop's own six-key builder sat in a *different* module from the forty-six
    seven-key literals, and both had to be caught.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        for node in _trace_dict_literals(path):
            offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME_FILE + ":"), (
        "the trace event record is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )
