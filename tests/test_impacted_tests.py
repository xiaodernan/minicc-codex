"""M8-T179: a change has an audience, and the audience is computable.

第 206 批 measured what "we do not run the full suite" costs: an assertion sat
red for sixty batches because it contradicted a deliberate change made in
another file, and nothing was watching. The answer is not to run everything -
that is the twelve-minute wall clock the project deliberately avoids - but to
know, mechanically, which test files can see a given change.

``scripts/impacted_tests.py`` inverts the import graph for that. This file keeps
the inversion honest, because an impact tool nobody gates is just another
comment:

1. every module under ``minicc/`` imports cleanly. That census is what found
   ``minicc/repl`` - a package whose only file imported ``.repl``, a module that
   has never existed in this repository's history, referenced by nothing,
   unimportable since the first commit;
2. every module is reachable from at least one test file, or is a re-export
   facade this file has itself verified (a facade has no behaviour to notice, so
   the only thing it can get wrong is the names it promises);
3. every name a facade promises in ``__all__`` is a name it actually binds;
4. the impact set sees through the import chain, so a change in ``bench_tasks``
   reaches a test that only ever names ``benchmarks``.
"""
from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "impacted_tests.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("impacted_tests_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _production_modules() -> dict[str, Path]:
    script = _load_script()
    return script._modules()


def test_every_module_in_the_package_imports() -> None:
    """The census that found ``minicc/repl``.

    A module that cannot be imported cannot be tested, cannot be shipped, and
    cannot be noticed - and the only thing standing between it and production is
    that nothing imports it either. The floor is what makes that arrangement
    visible instead of harmless-looking.
    """
    modules = _production_modules()
    assert len(modules) >= 50, f"only {len(modules)} modules scanned - the census saw nothing"
    failures = []
    for name in sorted(modules):
        try:
            importlib.import_module(name)
        except BaseException as exc:  # noqa: BLE001 - the point is to report it
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert failures == [], failures


def test_every_module_is_reachable_from_a_test_or_is_a_verified_facade() -> None:
    """A module no test can notice is a module whose regressions have no audience."""
    script = _load_script()
    tests_per_module, _tests, _all_tests = script.build()
    facades = script.verified_facades()
    unreachable = sorted(
        name for name, tests in tests_per_module.items()
        if not tests and name not in script.EXEMPT and name not in facades
    )
    assert unreachable == [], unreachable
    # The exemption is earned by verification, so it has to actually earn something:
    # a rule that exempts nothing would make this gate a restatement of the floor.
    assert facades, "no facade was verified - the exemption rule is decorative"


def test_every_name_a_facade_promises_is_one_it_binds() -> None:
    """``__all__`` is a promise; a promise about a name that is not there is a lie.

    ``minicc/repl`` promised ``Repl`` from a module that never existed. The same
    shape, one level quieter, is an ``__all__`` entry whose import was deleted
    while the list stayed.
    """
    script = _load_script()
    for name, path in sorted(_production_modules().items()):
        promised = script._promised_names(path)
        if promised is None:
            continue
        bound = script._bound_names(path)
        missing = sorted(promised - bound)
        assert missing == [], f"{name} promises names it does not bind: {missing}"


def test_every_script_has_an_audience_too() -> None:
    """``scripts/`` joined the floor in the same batch that wired it into CI.

    ``reliability_probe.py`` has no test that runs it - and must not need one:
    CI runs it on every push (an M1 exit criterion). Its audience is ``ci.yml``,
    which is why the audience set is "tests plus workflows" and not "tests".
    """
    script = _load_script()
    audience, _references, _tests = script.build()
    for name in script._script_modules():
        assert audience[name], f"{name} has no audience: no test reaches it and no workflow runs it"
    assert "ci.yml" in audience["scripts.reliability_probe"], (
        "reliability_probe lost its CI runner - the M1 exit criterion is now unmeasured"
    )


def test_the_impact_floor_is_wired_into_ci() -> None:
    """A floor nobody runs is the hand-copied list it replaced (M8-T36..T38).

    The census that found ``minicc/repl`` is only worth what its enforcement is
    worth. ``tests/test_ci_hygiene.py`` pins the other two claim checkers the
    same way.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python scripts/impacted_tests.py --check" in workflow, (
        "the impact floor is not run by CI, so a module losing its audience is "
        "only visible to whoever remembers to run the tool"
    )


def test_a_facade_that_promises_a_name_it_does_not_bind_earns_no_exemption(
    tmp_path: Path,
) -> None:
    """The exemption is earned by verification, not by having an ``__all__``.

    Arm G of this batch weakened ``verified_facades`` to "declares ``__all__``"
    and every other assertion stayed green - the floor exempted the facade, and
    only the promise gate above objected. That is one gate doing two jobs, so the
    rule is pinned here on its own, against a facade built for the purpose.
    """
    script = _load_script()
    broken = tmp_path / "minicc" / "llm" / "__init__.py"
    broken.parent.mkdir(parents=True)
    broken.write_text(
        "from .base import user_msg\n\n__all__ = [\"user_msg\", \"Repl\"]\n",
        encoding="utf-8",
    )
    assert script.verified_facades({"minicc.llm.__init__": broken}) == set()


def test_the_impact_set_sees_through_the_import_chain() -> None:
    """Direct references only would miss most of the graph.

    ``tests/test_benchmark_runner.py`` never names ``bench_tasks``; it imports
    ``benchmarks``, which imports ``bench_tasks``. A change to the grader
    vocabulary is exactly the kind of change that test must see.
    """
    script = _load_script()
    tests_per_module, _tests, _all_tests = script.build()
    assert "test_benchmark_runner.py" in tests_per_module["minicc.bench_tasks"], (
        "a change to bench_tasks does not reach the runner that grades with it"
    )
    assert "test_bench_tasks.py" in tests_per_module["minicc.bench_tasks"]


def test_the_tool_lists_the_reaching_tests_for_a_changed_module() -> None:
    """End to end, as an operator would run it."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "minicc/bench_tasks.py"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), check=False,
    )
    assert result.returncode == 0, result.stderr
    listed = result.stdout.split()
    assert "tests/test_bench_tasks.py" in listed
    assert "tests/test_benchmark_runner.py" in listed
    assert len(listed) >= 10, listed


def test_the_tool_reports_a_change_no_test_can_see() -> None:
    """Silence is the failure mode this whole batch exists to prevent.

    A changed module with an empty impact set used to print nothing and exit 0 -
    "no test file reaches the changed paths" reads like a clean result. It is the
    opposite: the change is invisible to the suite by construction.
    """
    script = _load_script()
    script.build = lambda: ({"minicc.orphan": set()}, {}, set())  # type: ignore[assignment]
    assert script.main(["minicc/orphan.py"]) == 1


def test_the_tool_reports_a_module_the_graph_has_never_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of "no audience": a module the graph does not know at all.

    The first version of this gate only fed ``main`` a module the graph already
    knew, so the branch handling an unknown module was never executed - arm E of
    this batch deleted that branch and every assertion stayed green. The branch
    is reachable when the tree and the graph disagree (a file written after the
    scan, a path the scanner skips), so it is pinned here with a graph that
    knows nothing and a module that does exist.
    """
    script = _load_script()
    monkeypatch.setattr(script, "build", lambda: ({}, {}, set()))
    assert script.main(["minicc/benchmarks.py"]) == 1


def test_a_module_that_no_longer_exists_is_not_a_finding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deleted path has nothing left to run; reporting it would be noise.

    Same branch, opposite answer, and the difference is one ``exists()`` - which
    is why the two cases are pinned next to each other instead of in prose.
    """
    script = _load_script()
    monkeypatch.setattr(script, "build", lambda: ({}, {}, set()))
    assert script.main(["minicc/gone_forever.py"]) == 0


def test_the_tool_ignores_paths_no_test_could_reach() -> None:
    """Docs and config are not production modules; the tool says so quietly."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "README.md"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", result.stdout
