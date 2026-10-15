"""Reverse-control and agreement cells for the third silence gate (M8-T260).

``test_broad_silent_handlers_state_a_reason.py`` is the third gate that decides whether
a broad handler may swallow silently. The other two share ``_silence_reason_shared``,
whose module docstring says the gates "must agree on (a) how ``minicc/`` is walked and
(b) what counts as 'a stated reason', so that logic lives here once instead of being
copied into each gate".

This gate copies all three predicates instead - ``_is_broad``, ``_is_silent`` and
``_states_a_reason`` - and walks ``scripts/`` as well as ``minicc/``. Measured on the
shipped tree the two answers happen to agree: the population is exactly the union of
the two shared families (17 = 14 pass + 3 return), and the reason verdicts agree 17 of
17. Fed seven synthetic shapes through both detectors, 0 diverged.

So there is no active divergence - and that is precisely the problem. The agreement is
coincidental, not structural, and nothing in CI would notice the day it stopped being
true. This file makes it load-bearing: the agreement cells pin the private detectors to
the shared ones on a fixture corpus, and the reverse-control cells prove each private
predicate still reacts when blinded.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _silence_reason_shared import census_silent, stated_reason  # noqa: E402
from test_broad_except_return_swallows_state_reason import (  # noqa: E402
    _is_return_swallow,
)
from test_broad_silent_handlers_state_a_reason import (  # noqa: E402
    REPO_ROOT as THIRD_ROOT,
    _audit,
    _is_broad,
    _is_silent,
    _states_a_reason,
)
from test_silence_must_state_its_reason import _is_silent_broad  # noqa: E402

#: A fixture corpus covering every shape the two detectors could plausibly read
#: differently: the noqa spellings, the comment placements, and the silent-statement
#: trailing-comment case. Each value is (label, source).
AGREEMENT_CORPUS: tuple[tuple[str, str], ...] = (
    ("noqa BLE001 with dash on the handler line",
     "try:\n    run()\nexcept Exception:  # noqa: BLE001 - teardown is best-effort\n    pass\n"),
    ("plain noqa with no BLE001 tag",
     "try:\n    run()\nexcept Exception:  # noqa - teardown is best-effort\n    pass\n"),
    ("noqa BLE001 with no dash after the tag",
     "try:\n    run()\nexcept Exception:  # noqa: BLE001\n    pass\n"),
    ("comment between the handler line and its body",
     "try:\n    run()\nexcept Exception:\n    # teardown is best-effort\n    pass\n"),
    ("trailing comment on the silent statement",
     "try:\n    run()\nexcept Exception:\n    pass  # teardown is best-effort\n"),
    ("trailing comment on a bare return",
     "try:\n    run()\nexcept Exception:\n    return  # teardown is best-effort\n"),
    ("no reason at all",
     "try:\n    run()\nexcept Exception:\n    pass\n"),
    ("narrow handler, out of scope for both",
     "try:\n    run()\nexcept OSError:\n    pass\n"),
    ("multi-statement silent body",
     "try:\n    run()\nexcept Exception:\n    pass\n    pass\n"),
)

BARE_SILENT = '''"""A fixture module with a silence nobody explained."""


def probe():
    try:
        run()
    except Exception:
        pass
'''

NARROW = '''"""A narrow handler is a named decision, not a silent broad one."""


def probe():
    try:
        run()
    except OSError:
        pass
'''

MULTI_SILENT = '''"""Two silent statements: the third gate's rule asks for exactly one."""


def probe():
    try:
        run()
    except Exception:
        pass
        pass
'''


def _handlers_of(source: str) -> list[tuple[ast.ExceptHandler, list[str]]]:
    lines = source.splitlines()
    return [(node, lines) for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ExceptHandler)]


def _verdicts(source: str) -> list[tuple[str, bool, bool]]:
    """``(label, third gate verdict, shared verdict)`` for every handler in a fixture."""
    out = []
    for node, lines in _handlers_of(source):
        out.append((f"line {node.lineno}",
                    _states_a_reason(node, lines),
                    bool(stated_reason(lines, node))))
    return out


def _tree(tmp_path: Path, source: str) -> Path:
    root = tmp_path / "fixture_tree"
    root.mkdir(parents=True, exist_ok=True)
    (root / "probe_mod.py").write_text(source, encoding="utf-8")
    return root


# --- the load-bearing new thing: the private detectors must not drift ----


def test_the_private_and_shared_reason_detectors_agree_on_every_fixture() -> None:
    """Pin ``_states_a_reason`` to ``stated_reason`` on shapes that could split them.

    Measured before this file existed: 0 of 7 synthetic shapes diverged. That reading
    is only true until someone edits either detector - which is why it is asserted
    here rather than left as a one-off measurement.
    """
    for label, source in AGREEMENT_CORPUS:
        for where, third, shared in _verdicts(source):
            assert third == shared, (
                f"fixture {label!r} handler {where}: the third gate's private "
                f"_states_a_reason said {third} while the shared stated_reason said "
                f"{shared}. The two gates now disagree about what a stated reason is, "
                "which is the drift _silence_reason_shared exists to prevent"
            )


def test_the_third_gate_covers_exactly_the_two_shared_families() -> None:
    """Population agreement: its census is the union of the pass and return families.

    Measured on the shipped tree: 17 = 14 + 3, with nothing in either side's set that
    the other lacks. If a multi-statement silent handler ever appears, the pass family
    will count it and this gate will not, and this cell is what says so.
    """
    seen, _offenders = _audit()
    pass_family = {site for site, _ in census_silent(_is_silent_broad)}
    return_family = {site for site, _ in census_silent(_is_return_swallow)}
    shared_union = pass_family | return_family
    third_set = set(seen)
    assert third_set == shared_union, (
        "the third gate and the two shared families no longer cover the same handlers "
        f"- only in the third gate: {sorted(third_set - shared_union)}; "
        f"only in the shared families: {sorted(shared_union - third_set)}"
    )


# --- reverse control: each private predicate still reacts when blinded ----


def test_a_bare_silence_is_flagged_by_the_private_reason_detector(tmp_path: Path) -> None:
    """Blind ``_states_a_reason`` to always claim a reason and this must notice."""
    tree = _tree(tmp_path, BARE_SILENT)
    for path in tree.rglob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        for node in ast.walk(ast.parse("\n".join(lines))):
            if isinstance(node, ast.ExceptHandler):
                assert not _states_a_reason(node, lines), (
                    "a handler that never says why was reported as stating a reason - "
                    "the private reason detector has gone blind in the permissive "
                    "direction, which is exactly what the shared detector's own "
                    "reverse-control cell watches for"
                )


def test_a_narrow_handler_is_out_of_scope(tmp_path: Path) -> None:
    """Blind ``_is_broad`` to always claim broad and the scope cell must notice."""
    for node, _lines in _handlers_of(NARROW):
        assert not _is_broad(node), (
            "a handler naming OSError was classified as broad, so the gate would "
            "start policing named exceptions"
        )


def test_a_multi_statement_silent_body_is_out_of_scope(tmp_path: Path) -> None:
    """Blind ``_is_silent`` to always claim silent and this must notice.

    The rule is deliberately "a single silent statement"; two silent statements are a
    different shape that the pass-family gate already covers on its own.
    """
    for node, _lines in _handlers_of(MULTI_SILENT):
        assert not _is_silent(node), (
            "a two-statement body was classified as the single-statement silent shape"
        )


def test_the_shipped_tree_still_meets_its_floor() -> None:
    """A walker that stops finding handlers reports a pass - the floor is the check."""
    seen, _offenders = _audit()
    assert len(seen) >= 16, (
        f"only {len(seen)} broad silent handlers found; the gate's own floor is 16, "
        "so the walk has gone blind"
    )
    assert len(set(seen)) == len(seen), "duplicate sites in the census"


# --- the detectors are imported, not copied ------------------------------


def test_this_file_carries_no_private_copy_of_the_predicates() -> None:
    """Read by AST, not by substring: this file's docstring names what it borrows."""
    import tests.test_broad_silent_handlers_state_a_reason_mutation as self_module

    tree = ast.parse(Path(self_module.__file__).read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(tree)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for borrowed in ("_is_broad", "_is_silent", "_states_a_reason",
                     "stated_reason", "census_silent", "_audit"):
        assert borrowed not in defined, (
            f"{borrowed} is defined here instead of being imported - this file would "
            "keep passing while the gate it names is broken"
        )
    assert stated_reason is not None and _is_broad is not None


def test_the_predicates_here_are_the_gate_s_objects() -> None:
    """Identity check, so a future private re-export cannot slip in beside the import."""
    from test_broad_silent_handlers_state_a_reason import (
        _is_broad as broad,
        _is_silent as silent,
        _states_a_reason as reason,
    )

    assert _is_broad is broad and _is_silent is silent and _states_a_reason is reason
    assert THIRD_ROOT is not None
