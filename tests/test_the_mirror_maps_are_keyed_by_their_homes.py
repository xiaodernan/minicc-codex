"""M8-T581 — dict mirrors of gated vocabularies stay inside them.

Two vocabularies already have one home each and a gate that pins the
home's members: the reasoning efforts (``minicc/config.py``,
``REASONING_EFFORTS``) and the verification statuses
(``minicc/agent/verifier.py``, ``VERIFICATION_STATUSES``).  But the dicts
that carry those same keys as data - the machine translation of the
vocabulary onto wire values, fallbacks, summary sentences, repair hints -
were hand-maintained next to the homes, and a key added to a home would
silently never appear in the mirror, or worse, a misspelled key would go
unnoticed.

The rule this gate pins, per file, by shape:

* every ``Dict`` literal anywhere in ``minicc/`` with three or more keys
  drawn from a gated set is keyed **inside** that set (no stray members);
* the designated mirrors are held to the strict form - the module-scope
  ``REASONING_WIRE_VALUES`` and ``REASONING_FALLBACKS`` dicts in
  ``minicc/llm/openai_provider.py``, the inline effort-label map in
  ``minicc/agent/loop.py`` (``effort_label``), and every status-keyed dict
  in ``minicc/agent/verifier.py`` (the two ``to_event()`` maps) - each must
  be keyed by **exactly** the gated set, because the wire face of the home
  is meaningless with a hole in it.

Deliberate subsets stay legal where the question is different - e.g.
``minicc/agent/completion.py``'s repair-instruction table is intentionally a
subset (only the failure-shaped statuses have repair guidance) and is held
to the subset rule, not the strict one.
"""

from __future__ import annotations

import ast
from pathlib import Path

from minicc.agent.verifier import VERIFICATION_STATUSES
from minicc.config import REASONING_EFFORTS

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"

EFFORTS = set(REASONING_EFFORTS)
STATUSES = set(VERIFICATION_STATUSES)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _dict_literals(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            yield node


def _string_keys(node: ast.Dict) -> list[str]:
    return [
        key.value
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    ]


def test_every_effort_keyed_dict_stays_inside_the_home() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        tree = _parse(path)
        for node in _dict_literals(tree):
            keys = _string_keys(node)
            overlap = EFFORTS & set(keys)
            if len(overlap) >= 3 and not set(keys) <= EFFORTS:
                offenders.append(f"{relative}:{node.lineno}: {sorted(set(keys) - EFFORTS)} outside")
    assert offenders == [], (
        "these dicts carry effort names outside the home "
        f"(REASONING_EFFORTS): {offenders}"
    )


def test_every_status_keyed_dict_stays_inside_the_home() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        tree = _parse(path)
        for node in _dict_literals(tree):
            keys = _string_keys(node)
            overlap = STATUSES & set(keys)
            if len(overlap) >= 3 and not set(keys) <= STATUSES:
                offenders.append(f"{relative}:{node.lineno}: {sorted(set(keys) - STATUSES)} outside")
    assert offenders == [], (
        "these dicts carry verification statuses outside the home "
        f"(VERIFICATION_STATUSES): {offenders}"
    )


def _assigns_named(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name and isinstance(node.value, ast.Dict):
                yield node


def test_the_provider_wire_and_fallback_maps_are_the_whole_home() -> None:
    source = PACKAGE / "llm" / "openai_provider.py"
    tree = _parse(source)
    checked: dict[str, set[str]] = {}
    for name in ("REASONING_WIRE_VALUES", "REASONING_FALLBACKS"):
        for node in _assigns_named(tree, name):
            checked[name] = set(_string_keys(node.value))
    assert checked.get("REASONING_WIRE_VALUES") == EFFORTS, (
        f"REASONING_WIRE_VALUES must be keyed by exactly {sorted(EFFORTS)}, got {checked.get('REASONING_WIRE_VALUES')}"
    )
    assert checked.get("REASONING_FALLBACKS") == EFFORTS, (
        f"REASONING_FALLBACKS must be keyed by exactly {sorted(EFFORTS)}, got {checked.get('REASONING_FALLBACKS')}"
    )


def test_the_inline_effort_label_map_is_the_whole_home() -> None:
    # The inline map sits inside a `{...}.get(requested, requested)` call, so
    # find it by shape: any dict in loop.py carrying three or more effort
    # names is the label map, and it must be the whole home.
    source = PACKAGE / "agent" / "loop.py"
    tree = _parse(source)
    found: list[set[str]] = []
    for node in _dict_literals(tree):
        keys = set(_string_keys(node))
        if len(keys & EFFORTS) >= 3:
            found.append(keys)
    assert found, "the inline effort_label map in minicc/agent/loop.py was not found"
    for keys in found:
        assert keys == EFFORTS, f"the inline effort_label map must be keyed by exactly {sorted(EFFORTS)}, got {sorted(keys)}"


def test_the_verifier_event_maps_are_the_whole_home() -> None:
    source = PACKAGE / "agent" / "verifier.py"
    tree = _parse(source)
    maps = [
        set(_string_keys(node))
        for node in _dict_literals(tree)
        if len(STATUSES & set(_string_keys(node))) >= 3
    ]
    assert len(maps) == 2, f"expected the two to_event() status maps, found {len(maps)}"
    for keys in maps:
        assert keys == STATUSES, f"a verifier event map must be keyed by exactly {sorted(STATUSES)}, got {sorted(keys)}"
