"""M8-T411 — 运行时 trace 事件记录只有一个家

M8-T532 — 这条门的前提在 M8-T482 之后腐烂了：anthropic 把自建的七键记录
交给了 ``usage.channel_switched_event``，``trace_event`` 的 import 也随字面量
一起删掉；本模块却仍按「每个 emitter 文件里出现 trace_event 这五个字母」判红。
产品是对的，门是旧的。现在门从 AST 派生：谁直接调用 ``trace_event`` 就是一家，
调用这些家的人也在家谱上；按名字撞上的陌生接收者（``session.execute``）不算。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/trace.py"
TRACE_HOME = ("minicc.trace", "trace_event")

#: Every module the T411 census found emitting a trace event; none of them
#: may go silent without someone deleting a line here.
EMITTERS = (
    "minicc/agent/loop.py",
    "minicc/agent/subagent.py",
    "minicc/llm/anthropic_provider.py",
    "minicc/llm/fake.py",
    "minicc/llm/openai_provider.py",
    "minicc/main.py",
    "minicc/task_manager.py",
    "minicc/web.py",
)

#: Domain homes the T396/T482 consolidations left behind. A name leaving this
#: set is a product change someone has to say out loud, not a refactor.
KNOWN_HOMES = frozenset({
    "trace_event", "channel_switched_event", "budget_exceeded_event",
})

#: Anti-vacuity floor for the package scan.
MODULE_FLOOR = 60

Facts = tuple[ast.Module, dict[str, str], dict[str, ast.AST]]


def _dotted(path: Path) -> str:
    parts = list(path.relative_to(REPO).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _facts_from_source(module: str, source: str, *, is_package: bool = False) -> Facts:
    tree = ast.parse(source)
    imports: dict[str, str] = {}
    base = module.split(".") if is_package else module.split(".")[:-1]

    def absolute(level: int, target: str | None) -> str:
        prefix = base
        trim = level - 1
        if trim > 0:
            prefix = prefix[:-trim] if trim <= len(prefix) else []
        return ".".join(prefix + ([target] if target else []))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            source_module = absolute(node.level, node.module)
            for alias in node.names:
                if alias.name == "*":
                    continue
                binding = alias.asname or alias.name
                imports[binding] = (
                    source_module if node.module
                    else f"{source_module}.{alias.name}"
                )
    defs = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    return tree, imports, defs


def _facts(path: Path) -> Facts:
    return _facts_from_source(
        _dotted(path),
        path.read_text(encoding="utf-8"),
        is_package=path.name == "__init__.py",
    )


def _call_target(
    func: ast.expr,
    imports: dict[str, str],
    own: str,
    local_defs: set[str],
) -> tuple[str, str] | None:
    """Where a call lands, as ``(dotted module, name)``; ``None`` if unknown.

    Only receivers we can bind are resolved: a module-level function, a name
    imported from a known module, or ``self.<method>``. A method called on a
    local variable (``session.execute()``) is deliberately unknown - guessing
    by bare name is how a census starts counting strangers.
    """
    if isinstance(func, ast.Name):
        if func.id in local_defs:
            return own, func.id
        if func.id in imports:
            return imports[func.id], func.id
        return None
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "self":
            return (own, func.attr) if func.attr in local_defs else None
        if func.value.id in imports:
            return imports[func.value.id], func.attr
    return None


def _calls_in(node: ast.AST) -> list[ast.Call]:
    return [child for child in ast.walk(node) if isinstance(child, ast.Call)]


def _home_functions(
    modules: dict[str, Facts], identity: tuple[str, str],
) -> set[tuple[str, str]]:
    """Functions that reach the constructor, directly or through another home."""
    edges: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for module, (tree, imports, defs) in modules.items():
        local = set(defs)
        for name, node in defs.items():
            targets = edges.setdefault((module, name), set())
            for call in _calls_in(node):
                target = _call_target(call.func, imports, module, local)
                if target is not None:
                    targets.add(target)

    reached: set[tuple[str, str]] = set()
    changed = True
    while changed:
        changed = False
        for caller, targets in edges.items():
            if caller not in reached and (identity in targets or targets & reached):
                reached.add(caller)
                changed = True
    return reached


def _reaching_modules(
    modules: dict[str, Facts],
    homes: set[tuple[str, str]],
    identity: tuple[str, str],
) -> set[str]:
    """Modules containing at least one call that lands on a home."""
    reached: set[str] = set()
    for module, (tree, imports, defs) in modules.items():
        if module == identity[0]:
            continue
        local = set(defs)
        for call in _calls_in(tree):
            target = _call_target(call.func, imports, module, local)
            if target == identity or target in homes:
                reached.add(module)
                break
    return reached


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


def test_the_reach_walk_follows_a_domain_home_and_ignores_a_stranger() -> None:
    """The derivation itself: one hop is followed, unknown receivers are not.

    ``plane.provider`` never names ``trace_event`` - it reaches the home only
    through ``usage.domain_home``. ``plane.store`` calls a method with the
    same name on a local variable, which must not count.
    """
    identity = ("plane.trace", "trace_event")
    plane = {
        "plane.trace": _facts_from_source(
            "plane.trace",
            "def trace_event(name):\n    return {'kind': 'trace', 'name': name}\n",
        ),
        "plane.usage": _facts_from_source(
            "plane.usage",
            "from .trace import trace_event\n\n"
            "def domain_home():\n    return trace_event('x')\n",
        ),
        "plane.provider": _facts_from_source(
            "plane.provider",
            "from .usage import domain_home\n\n"
            "def call_it():\n    return domain_home()\n",
        ),
        "plane.store": _facts_from_source(
            "plane.store",
            "def save(session):\n    return session.domain_home()\n",
        ),
    }

    homes = _home_functions(plane, identity) | {identity}
    assert ("plane.usage", "domain_home") in homes
    assert ("plane.provider", "call_it") in homes, (
        "a function calling a domain home is part of the family"
    )

    reached = _reaching_modules(plane, homes, identity)
    assert "plane.provider" in reached
    assert "plane.store" not in reached, (
        "a method called on an unknown receiver must not count as the home"
    )


def test_the_three_domain_homes_are_still_in_the_family() -> None:
    """The reach walk still recognises the homes the consolidations left.

    This is the census clause: a domain home disappearing means a product
    change someone has to say out loud.
    """
    modules = {_dotted(path): _facts(path) for path in sorted(PACKAGE.rglob("*.py"))}
    homes = _home_functions(modules, TRACE_HOME) | {TRACE_HOME}
    home_names = {name for _, name in homes}
    blind = sorted(KNOWN_HOMES - home_names)
    assert blind == [], (
        "the reach walk stopped seeing a domain home: " + ", ".join(blind)
    )


def test_every_emitter_asks_the_home() -> None:
    """The eight T411 emitters still reach the trace home.

    The literal ``trace_event`` is no longer required in every emitter file:
    M8-T482 moved anthropic's record into ``usage.channel_switched_event``.
    What must hold is that some call the module makes lands on the home,
    directly or through a domain home such as ``budget_exceeded_event``.
    """
    modules = {_dotted(path): _facts(path) for path in sorted(PACKAGE.rglob("*.py"))}
    assert len(modules) >= MODULE_FLOOR, (
        f"the scan found only {len(modules)} modules under minicc/ - "
        "the emitter check would pass without reading the package"
    )

    homes = _home_functions(modules, TRACE_HOME) | {TRACE_HOME}
    reached = _reaching_modules(modules, homes, TRACE_HOME)
    missing = [name for name in EMITTERS if _dotted(REPO / name) not in reached]
    assert missing == [], (
        "these modules no longer reach the trace home: " + ", ".join(missing)
    )


def _trace_dict_literals(path: Path) -> list[ast.Dict]:
    """Dict literals that spell ``"kind": "trace"`` - the record's signature."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
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


def test_the_record_is_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second shape.

    The count is exact (not "all inside the home") because the T396 lesson
    applies: the loop's own six-key builder sat in a *different* module from
    the forty-six seven-key literals, and both had to be caught.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        for node in _trace_dict_literals(path):
            offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the trace event record is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )
