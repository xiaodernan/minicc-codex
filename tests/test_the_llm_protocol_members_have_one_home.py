"""M8-T586 — the two named LLM protocol wire spellings have one home.

``LLM_PROTOCOLS`` (minicc/config.py) pins the membership of the switch
vocabulary - ``auto`` / ``responses`` / ``chat_completions`` - and every
reader imports it.  But the *members* were also re-spelled as raw string
literals wherever logic was pinned to one wire: the provider's negotiation
(constructor default, fallback flips, mid-stream break, trace detail), and
web.py's recovery path.  Each spelling was a tiny copy of a home member -
nothing would fail if one drifted.

The home now also names the two non-``auto`` members (``auto`` is shared by
unrelated vocabularies and stays unnamed; see the gate note).  This gate pins:

* the named constants exist, carry the documented values, and are members of
  the home set; and
* no file under ``minicc/`` other than ``minicc/config.py`` spells the two
  members as string constants (docstrings excepted - documentation may quote
  the wires freely).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "config.py"

MEMBERS = {"responses", "chat_completions"}


def test_the_named_constants_live_in_the_home_and_match_it() -> None:
    from minicc.config import (
        LLM_PROTOCOLS,
        LLM_PROTOCOL_CHAT_COMPLETIONS,
        LLM_PROTOCOL_RESPONSES,
    )

    assert LLM_PROTOCOL_RESPONSES == "responses"
    assert LLM_PROTOCOL_CHAT_COMPLETIONS == "chat_completions"
    assert LLM_PROTOCOL_RESPONSES in LLM_PROTOCOLS
    assert LLM_PROTOCOL_CHAT_COMPLETIONS in LLM_PROTOCOLS


def _docstring_constant_ids(tree: ast.Module) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            ids.add(id(node.body[0].value))
    return ids


def test_no_module_spells_the_protocol_members_outside_the_home() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        if path.resolve() == HOME.resolve():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = _docstring_constant_ids(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            if id(node) in docstrings:
                continue
            if isinstance(node.value, str) and node.value in MEMBERS:
                offenders.append(f"{relative}:{node.lineno}: {node.value}")
    assert offenders == [], (
        "these string constants re-spell an LLM protocol member (import "
        "LLM_PROTOCOL_RESPONSES / LLM_PROTOCOL_CHAT_COMPLETIONS from "
        f"minicc/config.py instead): {offenders}"
    )
