"""Gates for M8-T541: one source, one parse, one decoding per checker run.

``impacted_tests.py --check`` asks two questions of every ``tests/*.py`` file -
what does it reference (the import graph), and which repo roots does it walk (the
census gate). Through M8-T540 the two halves each owned a ``read_text`` +
``ast.parse`` pair, so one run parsed the same test files twice and three facade
``__init__`` files three times: 467 of 1013 parses re-read a source the same run
already had. ``route_coverage.py`` parsed the one dispatcher text four times the
same way.

The duplicate reads also disagreed about decoding. The graph read test files with
``errors="replace"``; the census demanded UTF-8 and raised ``UnicodeDecodeError``
straight past the ``except (OSError, SyntaxError)`` written to keep one broken
file from taking the tool down. On an undecodable file the two halves therefore
answered differently - one judged it, the other died - and nothing in any output
said so, because on the shipped corpus both parses succeed and both numbers print.

So the legs below count parses on the shipped tree, and plant one undecodable file
to make the split visible. A wall-clock reading that moves with the machine, or a
run that prints the same numbers either way, cannot keep this claim honest.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: A census gate is a test file that walks a repo root and names it in a string.
#: One of the two synthetic files is this; the other cannot be decoded at all.
_GATE_TEXT = (
    "from pathlib import Path\n"
    "\n"
    "\n"
    "def test_walks_the_tree() -> None:\n"
    "    for path in Path('minicc').rglob('*.py'):\n"
    "        assert path\n"
)


def _load(name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; @dataclass(slots=True) resolves annotations via
    # sys.modules, so register the module before executing it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _count(calls: list[str]):
    """Wrap ast.parse, recording one digest per distinct source text it is handed."""
    real = ast.parse

    def parse(source, filename="<unknown>", mode="exec", *args, **kwargs):
        if isinstance(source, str):
            calls.append(hashlib.sha1(source.encode("utf-8", "replace")).hexdigest())
        return real(source, filename, mode, *args, **kwargs)

    return real, parse


def _synthetic(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_walks_the_tree.py").write_text(_GATE_TEXT, encoding="utf-8")
    (root / "tests" / "test_bytes.py").write_bytes(b"# \xff\xfe not utf-8\nx = 1\n")
    return root


# --------------------------------------------------------------------------- #
# 1. One run, one parse per source - counted, not timed.
# --------------------------------------------------------------------------- #


def test_the_impact_check_parses_every_source_once() -> None:
    script = _load("minicc_impacted_parse_once_t541", "scripts/impacted_tests.py")
    calls: list[str] = []
    real, counting = _count(calls)
    ast.parse = counting
    try:
        code = script.main(["README.md", "--check"])
    finally:
        ast.parse = real
    assert code == 0, code
    distinct = len(set(calls))
    test_files = sorted((REPO_ROOT / "tests").glob("*.py"))
    assert distinct >= len(test_files), (
        f"the run parsed {distinct} distinct sources while tests/ alone holds {len(test_files)} - "
        "the snapshot did not reach the readers"
    )
    assert len(calls) == distinct, (
        f"{len(calls) - distinct} of {len(calls)} parses re-read a source this run already parsed: "
        "the second read is the first read's answer"
    )


def test_the_dispatcher_text_is_parsed_once_per_run() -> None:
    route = _load("minicc_route_parse_once_t541", "scripts/route_coverage.py")
    source = (REPO_ROOT / "minicc" / "webserver.py").read_text(encoding="utf-8")
    calls: list[str] = []
    real, counting = _count(calls)
    ast.parse = counting
    try:
        sites = route.dispatch_sites(source)
        blind = sorted(set(route.text_predicates(source)) - set(route.ast_predicates(source)))
        unresolved = route.unresolved_route_anchors(source)
    finally:
        ast.parse = real
    assert len(calls) == 1, (
        f"the dispatcher's own text was parsed {len(calls)} times in one run; its four readers "
        "all want the same tree"
    )
    assert sites, "the dispatcher reader found no dispatch site - this leg measured nothing"
    assert blind == [] and unresolved == [], (blind, unresolved)


# --------------------------------------------------------------------------- #
# 2. One decoding, and the swallow covers the read it actually performs.
# --------------------------------------------------------------------------- #


def test_an_undecodable_test_file_is_dropped_not_raised_through_the_census(
    tmp_path: Path, monkeypatch,
) -> None:
    script = _load("minicc_impacted_census_bytes_t541", "scripts/impacted_tests.py")
    monkeypatch.setattr(script, "REPO_ROOT", _synthetic(tmp_path))
    try:
        gates = script.census_gates()
    except BaseException as exc:  # noqa: BLE001 - the point is to report it
        raise AssertionError(
            f"an undecodable test file killed the census with {type(exc).__name__}: {exc}"
        ) from exc
    assert "test_walks_the_tree.py" in gates, gates
    assert "test_bytes.py" not in gates, gates


def test_an_undecodable_test_file_is_named_not_answered_around(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    script = _load("minicc_impacted_main_bytes_t541", "scripts/impacted_tests.py")
    monkeypatch.setattr(script, "REPO_ROOT", _synthetic(tmp_path))
    try:
        code = script.main(["README.md", "--check"])
    except BaseException as exc:  # noqa: BLE001 - the point is to report it
        raise AssertionError(
            f"an undecodable test file killed --check with {type(exc).__name__}: {exc}"
        ) from exc
    captured = capsys.readouterr()
    assert code == 1, (code, captured.out, captured.err)
    assert "test_bytes.py" in captured.err, (
        f"the run exited 1 without naming the file it could not read: {captured.err!r}"
    )
    assert "no changes to measure" not in captured.err, (
        f"a tree with a file this run could not read was answered as an ordinary diff: "
        f"{captured.err!r}"
    )
