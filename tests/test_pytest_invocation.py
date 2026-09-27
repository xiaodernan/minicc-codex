"""The invocation shape is part of the measurement: every gate has to actually run.

M8-T72's first full-suite attempt was `python -W error -m pytest tests` - the flag on
the interpreter, which is how a CI file usually writes it.  It produced no test result
at all: pytest-asyncio raises its
`PytestDeprecationWarning("asyncio_default_fixture_loop_scope is unset")` inside
`pytest_configure`, an interpreter-level `-W error` turns that warning into an
exception, and pytest dies before collecting a single file (exit code 3).  The
recorded shape, `python -m pytest -W error`, is green on the same tree, so the suite
was silently unrunnable under a plausible invocation rather than failing.

That is the M8-T60 family - a gate that never runs - with a new cause: not a skipped
test, but a configuration option the plugin asks for and nobody answers.  These tests
pin both halves: the option is declared in `pyproject.toml`, and the two invocation
shapes produce the same collection result.  A planted defect (a rootdir whose config
omits the option) proves the interpreter-side probe can still see the failure, so the
green here is not the green of a probe that cannot go red.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYPROJECT = REPO / "pyproject.toml"

#: A real test file, cheap to collect, and one this repository owns.  The point of the
#: probe is `pytest_configure`, which happens before any file is read, so the target
#: only has to be something that must appear in the collected count.
TARGET = "tests/test_index_census.py"

OPTION = "asyncio_default_fixture_loop_scope"

_COLLECTED = re.compile(r"(\d+) tests? collected")


def _argv_interpreter(*extra: str) -> list[str]:
    """`python -W error -m pytest ...` - the flag the interpreter sees first."""

    return [sys.executable, "-W", "error", "-m", "pytest", "--collect-only", "-q",
            TARGET, "-p", "no:cacheprovider", *extra]


def _argv_pytest(*extra: str) -> list[str]:
    """`python -m pytest ... -W error` - the shape the batch records actually used."""

    return [sys.executable, "-m", "pytest", "--collect-only", "-q", TARGET,
            "-p", "no:cacheprovider", "-W", "error", *extra]


def _run(argv: list[str], cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _reached_collection(proc: subprocess.CompletedProcess[str]) -> tuple[bool, int]:
    """Did this invocation get as far as reporting a collection count?

    The count is the only witness that survives both a configure-time crash and a
    collection error: an INTERNALERROR prints a traceback and no count, a broken import
    prints `error` and no count, and a run that collected zero items prints a count of
    0, which is not evidence that anything was armed either.
    """

    out = (proc.stdout or "") + (proc.stderr or "")
    match = _COLLECTED.search(out)
    return "INTERNALERROR" not in out, int(match.group(1)) if match else -1


def test_the_recorded_invocation_shape_collects_the_suite():
    """The shape the docs record must keep working - this test is the control."""

    proc = _run(_argv_pytest())
    reached, collected = _reached_collection(proc)
    assert reached, f"the recorded shape died before collecting:\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}"
    assert collected > 0, f"the recorded shape collected nothing: {proc.stdout[-800:]}"
    assert proc.returncode == 0, f"exit {proc.returncode}: {proc.stdout[-800:]}"


def test_a_ci_invocation_shape_collects_the_same_suite():
    """`-W error` on the interpreter must reach the same collection as `-W error` on pytest.

    Before the option was declared this reported:

        INTERNALERROR> pytest.PytestDeprecationWarning: The configuration option
        "asyncio_default_fixture_loop_scope" is unset.

    with exit code 3 and not one test named - a whole suite that silently does not run
    depending on where the flag sits on the command line.
    """

    proc = _run(_argv_interpreter())
    out = (proc.stdout or "") + (proc.stderr or "")
    reached, collected = _reached_collection(proc)
    assert reached, (
        f"`python -W error -m pytest` never reached collection (exit {proc.returncode}); "
        f"a plugin warning raised at configure time is fatal under this shape, so no gate "
        f"in this repository runs.  Does [{OPTION}] get declared in pyproject.toml?\n"
        f"{out[-1500:]}"
    )
    assert collected > 0, f"the interpreter-first shape collected nothing: {out[-800:]}"
    assert proc.returncode == 0, f"exit {proc.returncode}: {out[-800:]}"


def test_both_shapes_agree_on_the_number_of_tests_they_saw():
    """Same tree, same target, same count - or one of the shapes is not running the suite.

    A shape that "works" by collecting a different number of items is not the same
    measurement, which is exactly how a CI run can look green while testing a subset.
    """

    recorded = _reached_collection(_run(_argv_pytest()))
    ci_shape = _reached_collection(_run(_argv_interpreter()))
    assert recorded == (True, ci_shape[1]) or ci_shape == (True, recorded[1]), (
        f"the two invocation shapes disagree: pytest-first saw {recorded}, "
        f"interpreter-first saw {ci_shape} (collected=-1 means one of them never "
        "reached collection at all)"
    )
    assert recorded[1] > 0 and ci_shape[1] > 0, (recorded, ci_shape)


def test_the_configured_value_is_the_one_the_plugin_offers():
    """The option is a real ini key with a closed vocabulary, so pin the value too.

    Reading the shipped config, not my memory of it: `pytest-asyncio>=0.23.0` is the
    declared floor and the installed plugin (1.4.0) is the one that warns.
    """

    configured = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))[
        "tool"]["pytest"]["ini_options"].get(OPTION)
    assert configured == "function", (
        f"[tool.pytest.ini_options].{OPTION} = {configured!r}; the plugin's own sentence "
        "names function/class/module/package/session as valid, and 'function' is what a "
        "test-local event loop wants"
    )


def test_the_probe_sees_the_defect_when_the_option_is_absent(tmp_path: Path) -> None:
    """A green interpreter-first run means nothing unless red is reachable.

    `tmp_path` gets a pyproject with no `[tool.pytest.ini_options]` option at all and one
    trivial test file; under the interpreter-first shape that rootdir must reproduce the
    configure-time death, on this machine, in this run.
    """

    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = [\".\"]\n", encoding="utf-8"
    )
    (tmp_path / "test_planted.py").write_text("def test_planted_ok() -> None:\n    assert True\n", encoding="utf-8")
    proc = _run([sys.executable, "-W", "error", "-m", "pytest", "--collect-only", "-q",
                 "test_planted.py", "-p", "no:cacheprovider"], cwd=tmp_path)
    out = (proc.stdout or "") + (proc.stderr or "")
    reached, collected = _reached_collection(proc)
    assert not reached, (
        "the planted rootdir, which declares no value for this option, stayed collectible "
        f"under the interpreter-first shape (exit {proc.returncode}, collected={collected}); "
        "that means the probe above cannot detect the defect it claims to guard, and its "
        f"green proves nothing\n{out[-1200:]}"
    )


def test_the_two_shapes_are_the_two_command_lines_their_names_claim() -> None:
    """The probes must differ where the claim says they differ, or agreement is vacuous.

    Nothing in a run's output says which end of the command line carried `-W error`, so a
    future edit that makes both helpers build the same argv would leave four green tests
    and one dead claim.  The argv is the only place the distinction exists.
    """

    interpreter_first = _argv_interpreter()
    pytest_first = _argv_pytest()
    assert interpreter_first[1:5] == ["-W", "error", "-m", "pytest"], (
        f"the CI-shape probe no longer puts the flag on the interpreter: {interpreter_first}"
    )
    assert pytest_first[1:3] == ["-m", "pytest"], (
        f"the recorded-shape probe no longer starts with `-m pytest`: {pytest_first}"
    )
    assert pytest_first.index("-W") > pytest_first.index("pytest"), (
        f"the recorded shape's `-W error` moved in front of `-m pytest`, which makes it "
        f"the other shape: {pytest_first}"
    )
    assert interpreter_first != pytest_first, (
        "both probes now build the same command line, so the agreement test compares one "
        "shape with itself"
    )
