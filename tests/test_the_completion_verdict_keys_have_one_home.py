"""M8-T589 — the completion-verdict key contract has one home.

The completion judge's JSON object is a contract written in three places:

* ``minicc/agent/completion.py`` — ``CompletionDecision.to_dict`` is the
  rendering (the six base keys) and the ``required`` set (the subset the
  parser demands for status == "complete"), and
* ``minicc/llm/fake.py`` — the fake judge emits the same object.

A field added to ``to_dict`` without the fake also learning it (or the
``required`` set silently demanding more) would fail only at runtime.

This gate pins:

* fake.py's judge payload dict is keyed exactly the six-key home;
* completion.py's ``to_dict`` base literal is keyed exactly the same six;
* the ``required`` subset stays inside the six.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = {"status", "confidence", "rationale", "missing", "next_action", "evidence"}


def _dicts(node: ast.Module):
    for sub in ast.walk(node):
        if isinstance(sub, ast.Dict):
            yield sub


def _keys(node: ast.Dict) -> set[str]:
    return {
        key.value
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def _parse(rel: str) -> ast.Module:
    path = REPO / rel
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_the_fake_judge_emits_exactly_the_verdict_home() -> None:
    tree = _parse("minicc/llm/fake.py")
    matches = [d for d in _dicts(tree) if len(_keys(d) & HOME) >= 3]
    assert matches, "the fake judge's payload dict was not found"
    for dict_node in matches:
        assert _keys(dict_node) == HOME, (
            "the fake judge's payload keys drifted from the verdict home: "
            f"extra {_keys(dict_node) - HOME}, missing {HOME - _keys(dict_node)}"
        )


def test_to_dict_renders_the_six_base_keys() -> None:
    tree = _parse("minicc/agent/completion.py")
    matches = [d for d in _dicts(tree) if len(_keys(d) & HOME) == 6]
    assert matches, "to_dict's base literal was not found"
    for dict_node in matches:
        assert set(_keys(dict_node)) == HOME


def test_the_required_set_stays_inside_the_verdict_home() -> None:
    tree = _parse("minicc/agent/completion.py")
    matches: list[ast.Set] = []
    for sub in ast.walk(tree):
        if isinstance(sub, ast.Set):
            values = {elt.value for elt in sub.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)}
            if len(values & HOME) >= 3:
                matches.append(values)
    assert matches, "the parser's required set was not found"
    for values in matches:
        assert values <= HOME, (
            "the parser's required set reaches outside the verdict home: "
            f"{values - HOME}"
        )
