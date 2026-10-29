"""M8-T536: ``--check`` promises the floor; a clean checkout collected it without
ever computing it.

``scripts/impacted_tests.py`` documents its own contract at the top: *"Exit code 0
means the impact set was computed (and, with ``--check``, that the floor holds)."*
The floor block sat behind an early return that fires whenever the worktree is
clean - which is every CI checkout, because ``actions/checkout`` leaves nothing
uncommitted. So the ``claims`` job's step

    - name: Every module has an audience that can notice its change
      run: python scripts/impacted_tests.py --check

answered "no changes to measure" and exited 0 without evaluating the floor.
Measured on a clean export of this repository with a *committed*
``minicc/__no_audience__.py``: ``--check`` exits 0, while the same tree's floor,
evaluated by hand, is exactly that module.

The door that was supposed to watch this - ``test_the_impact_floor_is_wired_into_ci`` -
asks whether the command string appears in ``ci.yml``. It does. That question and
"does the command, run the way CI runs it, do the work" are not the same question,
and only the second one is a gate.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "impacted_tests.py"
SCRIPT_BYTES = SCRIPT.read_bytes()

ATTENDED = '"""A module one test reaches."""\n\n\ndef attended() -> int:\n    return 1\n'
ORPHAN = '"""A module nothing reaches."""\n\n\ndef orphan() -> int:\n    return 2\n'
INIT = '"""The package."""\n'
TEST_FILE = (
    '"""The only test in the synthetic repository."""\n'
    "import minicc\n"
    "import minicc.attended\n"
    "\n\n"
    "def test_attended() -> None:\n"
    "    assert minicc.attended.attended() == 1\n"
)
WORKFLOW = (
    "name: claims\n"
    "on: [push]\n"
    "jobs:\n"
    "  claims:\n"
    "    runs-on: ubuntu-latest\n"
    "    steps:\n"
    "      - uses: actions/checkout@v4\n"
    "      - name: Every module has an audience that can notice its change\n"
    "        run: python scripts/impacted_tests.py --check\n"
)


def _git(root: Path, *args: str) -> str:
    if shutil.which("git") is None:
        pytest.fail(
            "git is not on PATH, so this leg cannot establish the clean-checkout condition "
            "it is about - which is a finding about the leg, not a verdict about the floor"
        )
    result = subprocess.run(("git", "-C", str(root), *args), capture_output=True, text=True,
                            errors="replace", check=False)
    assert result.returncode == 0, (args, result.stdout, result.stderr)
    return result.stdout


def _synthetic(tmp_path: Path, *, orphans: int, git_clean: bool) -> Path:
    """A repository shaped like a CI checkout: the modules exist, nothing is uncommitted."""
    root = tmp_path / "repo"
    (root / "minicc").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "scripts").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "minicc" / "__init__.py").write_text(INIT, encoding="utf-8")
    (root / "minicc" / "attended.py").write_text(ATTENDED, encoding="utf-8")
    for index in range(orphans):
        (root / "minicc" / f"orphan{index}.py").write_text(ORPHAN, encoding="utf-8")
    (root / "tests" / "test_attends.py").write_text(TEST_FILE, encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text(WORKFLOW, encoding="utf-8")
    (root / "scripts" / "impacted_tests.py").write_bytes(SCRIPT_BYTES)
    if git_clean:
        # ``--no-verify`` keeps the leg about its own condition: a machine-wide commit
        # hook is not part of what "the worktree is clean" means.
        _git(root, "init", "-q")
        _git(root, "add", "-A")
        _git(root, "-c", "user.name=gate", "-c", "user.email=gate@example.invalid",
             "commit", "-q", "--no-verify", "-m", "one commit, clean worktree")
    return root


def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run((sys.executable, str(root / "scripts" / "impacted_tests.py"), *args),
                          capture_output=True, text=True, errors="replace",
                          cwd=str(root), check=False)


def _load(root: Path):
    spec = importlib.util.spec_from_file_location(
        "impacted_tests_under_test", root / "scripts" / "impacted_tests.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_clean_checkout_with_an_unattended_module_still_gates_the_floor(tmp_path) -> None:
    """The CI condition, and the verdict CI should get from it."""
    root = _synthetic(tmp_path, orphans=1, git_clean=True)
    assert _git(root, "diff", "--name-only", "HEAD") == "", "this leg lost the condition it is about"
    assert _git(root, "ls-files", "--others", "--exclude-standard") == ""

    result = _run(root, "--check")
    assert result.returncode == 1, (
        f"--check exited {result.returncode} on a clean checkout holding a module nothing "
        f"reaches (stderr: {result.stderr.strip()!r}). The floor is a property of the tree; "
        "an empty diff is not an answer to it."
    )
    assert "minicc.orphan0" in result.stderr, result.stderr


def test_a_clean_checkout_with_every_module_attended_is_green(tmp_path) -> None:
    """The control: the leg above must not be red because the floor always says no."""
    root = _synthetic(tmp_path, orphans=0, git_clean=True)
    result = _run(root, "--check")
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "modules no test reaches" not in result.stderr, result.stderr


def test_the_floor_does_not_answer_for_a_run_that_did_not_ask_for_it(tmp_path) -> None:
    """Plain invocations stay diff-only, or every ``--run`` would become a floor run."""
    root = _synthetic(tmp_path, orphans=1, git_clean=True)
    result = _run(root)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "no changes to measure" in result.stderr, result.stderr


def test_the_impact_half_still_names_a_changed_module_the_floor_excused(tmp_path, capsys) -> None:
    """The floor excuses an ``EXEMPT`` module; the diff half must not.

    Moving the floor ahead of the early return means it answers first, and for a
    changed module that is simply unattended the two reports say the same thing. They
    disagree for a module somebody excused by hand: the floor lets it go, and a change
    that touches it is still a change no test can see.
    """
    root = _synthetic(tmp_path, orphans=1, git_clean=False)
    script = _load(root)
    script.EXEMPT = {"minicc.orphan0": "excused by this leg"}
    code = script.main(["minicc/orphan0.py", "--check"])
    captured = capsys.readouterr()
    assert code == 1, captured.err
    assert "changed module(s) no test can notice" in captured.err, captured.err
    assert "modules no test reaches" not in captured.err, (
        "the exemption was decorated over, so the floor is now wider than the list it "
        f"replaced: {captured.err!r}"
    )


def test_the_facade_exemption_is_derived_once_not_once_per_candidate(tmp_path) -> None:
    """Two floor candidates must not mean two package walks.

    ``verified_facades()`` sat inside the comprehension's condition, so the answer - a
    set that cannot change while the loop runs - was recomputed for every module that
    had lost its audience. With the floor now evaluated on the CI path, that cost is
    no longer behind an unreachable branch.
    """
    root = _synthetic(tmp_path, orphans=2, git_clean=False)
    script = _load(root)
    calls: list[int] = []
    real = script.verified_facades

    def counting(modules=None, **kwargs):
        calls.append(1)
        return real(modules, **kwargs)

    script.verified_facades = counting
    try:
        code = script.main(["minicc/attended.py", "--check"])
    finally:
        script.verified_facades = real
    assert code == 1
    assert len(calls) == 1, (
        f"the floor re-derived the facade exemption {len(calls)} times for 2 candidates; "
        "it is one answer about one tree"
    )


def test_the_synthetic_census_sees_the_modules_it_is_asking_about(tmp_path) -> None:
    """Anti-vacuity: the legs above must not pass because nothing was found."""
    root = _synthetic(tmp_path, orphans=1, git_clean=False)
    script = _load(root)
    audience, _references, all_tests = script.build()
    assert audience, "the synthetic repository produced no modules at all"
    assert "minicc.attended" in audience, sorted(audience)
    assert audience["minicc.attended"], "the control module has no audience either"
    assert audience["minicc.orphan0"] == set()
    assert all_tests == {"test_attends.py"}, all_tests
