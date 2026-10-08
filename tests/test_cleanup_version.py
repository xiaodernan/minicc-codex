"""M4-T9: cleanup and version single-source guards.

Pin the durability fixes so they cannot silently regress: the version lives in
exactly one place (minicc.__version__) and every consumer derives from it; the
retired web/app.min.js stays gone and is no longer generated; web/assets holds
only the bundles the manifest references; the repo root carries no repro/log
artifacts; and the README no longer points at a non-existent npm script.
"""

from __future__ import annotations

import ast
import importlib.metadata as importlib_metadata
import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)
#: One installed record: (the version it states, where that record lives).
VersionRecord = tuple[str, str]


def _visible_version_records(name: str = "minicc") -> list[VersionRecord]:
    """Every installed record for *name* this interpreter can see.

    ``importlib_metadata.version()`` answers with the first record ``sys.path``
    yields and stays silent about the rest, and ``python -m pytest`` puts the run
    directory first.  The packaging tests leave a ``minicc.egg-info`` rebuilt from
    the current source in that directory, so on a tree that has been run once the
    artifact can state the single source while the editable record that installed
    this tree states something else - a green that certifies nothing about the
    install it claims to check.  Measured on 3118bbd: with the run directory first
    the census holds ``0.2.0`` (egg-info) and ``0.1.0`` (dist-info) and the old
    call answers 0.2.0, while on a worktree plane without the artifact the same
    repo bytes answer 0.1.0.  One file, two verdicts, neither about the repo.
    """
    rows: list[VersionRecord] = []
    for dist in importlib_metadata.distributions():
        try:
            metadata_name = dist.metadata["Name"]
        except Exception:  # unreadable METADATA is still a visible record
            metadata_name = None
        if (metadata_name or "").strip().lower().replace("_", "-") != name:
            continue
        rows.append((dist.version, str(getattr(dist, "_path", "<unknown>"))))
    return rows


def _version_disagreements(
    records: list[VersionRecord], canonical: str, *, label: str = "minicc"
) -> list[str]:
    """Every way *records* fail to state *canonical*, one problem per record.

    Three clauses, each with its own burden: the floor (reading nothing is not
    agreement), the per-record comparison (a stale record sitting behind an
    agreeing one still bites), and the record path inside every sentence (the
    reader has to be able to tell which artifact answered).
    """
    if not records:
        return [
            f"no installed record for {label} is visible to this interpreter - an "
            "import is not an install, so the single source was never compared "
            "with anything"
        ]
    problems: list[str] = []
    for version, path in records:
        if version != canonical:
            problems.append(
                f"{label} record at {path} states {version!r} while the single "
                f"source minicc.__version__ states {canonical!r}; one of the two "
                "is stale - `python -m pip install -e .` refreshes the record, "
                "editing minicc/__init__.py refreshes the source"
            )
    return problems



# --- version single source of truth ---------------------------------------


def test_version_is_dynamic_in_pyproject():
    project = _pyproject()["project"]
    assert "version" not in project, "pyproject must not pin a static version"
    assert "version" in project.get("dynamic", [])
    dynamic = _pyproject()["tool"]["setuptools"]["dynamic"]
    assert dynamic["version"] == {"attr": "minicc.__version__"}


def test_all_version_consumers_agree():
    import minicc
    import minicc.mcp as mcp

    canonical = minicc.__version__
    assert mcp.__version__ == canonical
    # mcp.py must build clientInfo from __version__, never a hardcoded literal.
    mcp_src = (REPO_ROOT / "minicc" / "mcp.py").read_text(encoding="utf-8")
    assert '"version": __version__' in mcp_src
    assert '"version": "0.' not in mcp_src
def test_the_record_census_walks_sys_path_not_a_hand_pick(tmp_path: Path) -> None:
    """The census must find *every* visible record, not the first one.

    A census truncated to the first hit still greens a clean plane, which has one
    record - so no other case in this file can see that hole.  This one puts two
    synthetic records on the real ``sys.path`` walk and asks for both back.
    """
    planted = {"0.9.1", "0.9.2"}
    for version in sorted(planted):
        record = tmp_path / ("minicc-%s.dist-info" % version)
        record.mkdir()
        (record / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: minicc\nVersion: %s\n\n" % version,
            encoding="utf-8",
        )
    sys.path.insert(0, str(tmp_path))
    try:
        rows = _visible_version_records()
    finally:
        sys.path.remove(str(tmp_path))
    found = {(version, path) for version, path in rows if version in planted}
    assert {version for version, _ in found} == planted, (
        "the census planted %s into %s and read back %s; anything short of both "
        "means it stops at one record, which is the property that let a build "
        "artifact answer for an installed one"
        % (sorted(planted), tmp_path, sorted({version for version, _ in rows}))
    )
    for version, path in sorted(found):
        assert str(tmp_path) in path, (version, path)
        assert "dist-info" in path, (version, path)


def test_the_installed_record_states_the_single_source() -> None:
    """M4-T9's claim, measured against every record the plane can answer with.

    ``importlib_metadata.version("minicc") == minicc.__version__`` was the whole
    check.  Batch 216's fence found it green in the warm tree and red, by exact
    value (``'0.1.0' == '0.2.0'``), on a pinned worktree plane - the disagreement
    was real (this machine's editable record said 0.1.0 while the source said
    0.2.0), the warm tree's green was not: the run directory held the
    ``minicc.egg-info`` the packaging tests rebuild, and it answers first.
    """
    import minicc

    records = _visible_version_records()
    problems = _version_disagreements(records, minicc.__version__)
    assert problems == [], (
        "%s states %r; visible records: %s || %s"
        % (
            minicc.__file__,
            minicc.__version__,
            "; ".join("%s at %s" % row for row in records),
            " || ".join(problems),
        )
    )


def test_records_that_disagree_are_each_named() -> None:
    """A stale record hidden behind an agreeing one must still be reported.

    ``[("0.2.0", artifact), ("0.1.0", install)]`` is the shape of the false-green
    plane; comparing only the first answer calls it healthy.
    """
    rows = [
        ("0.2.0", "D:/tree/minicc.egg-info"),
        ("0.1.0", "D:/tree/.venv/Lib/site-packages/minicc-0.1.0.dist-info"),
    ]
    problems = _version_disagreements(rows, "0.2.0")
    assert len(problems) == 1, problems
    assert "0.1.0" in problems[0], problems
    assert "0.2.0" in problems[0], problems
    assert "minicc-0.1.0.dist-info" in problems[0], problems
    assert "egg-info" not in problems[0], (
        "the record that agrees with the single source is not a fault and must "
        "not be dragged into the report: %s" % (problems,)
    )


def test_no_visible_record_is_refused_not_passed() -> None:
    """Zero records read is "nothing was installed", never agreement."""
    problems = _version_disagreements([], "0.2.0")
    assert len(problems) == 1, problems
    assert "no installed record" in problems[0], problems[0]


def test_a_single_stale_record_still_bites() -> None:
    """The plain stale install: one record, wrong number, named by path."""
    problems = _version_disagreements(
        [("0.1.0", "/x/site-packages/minicc-0.1.0.dist-info")], "0.2.0"
    )
    assert len(problems) == 1, problems
    assert "0.1.0" in problems[0] and "0.2.0" in problems[0], problems[0]
    assert "/x/site-packages/minicc-0.1.0.dist-info" in problems[0], problems[0]
    assert "pip install -e" in problems[0], (
        "the refusal has to say how to fix the machine it is refusing: %s" % problems[0]
    )


def test_records_that_all_agree_with_the_source_are_accepted() -> None:
    """The gate must still accept a healthy plane, duplicates included.

    An editable install plus the packaging tests' rebuild of the same number is
    two visible records saying one thing; refusing that would move the claim from
    "is the version single-sourced" to "does this machine hold exactly one file".
    """
    rows = [
        ("0.2.0", "/tree/minicc.egg-info"),
        ("0.2.0", "/tree/.venv/Lib/site-packages/minicc-0.2.0.dist-info"),
    ]
    assert _version_disagreements(rows, "0.2.0") == [], (
        "two records that agree are a normal editable-install plane, not a fault"
    )



def test_no_production_dict_announces_a_version_literal() -> None:
    """Enumerate the consumers; do not hand-pick one and trust it.

    The check above reads ``mcp.py`` by name, which is how ``rpc.py`` was able to
    announce ``"serverInfo": {..., "version": "0.1.0"}`` for as long as the
    canonical version happened to be 0.1.0.  Any dict entry keyed ``version`` in
    production code must take a name or an expression, never a string literal.
    """
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "minicc").rglob("*.py")):
        if path.name == "__init__.py":
            continue  # the single source itself
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "version" and isinstance(
                    value, ast.Constant
                ) and isinstance(value.value, str):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT).as_posix()}:{value.lineno} "
                        f"announces {value.value!r}"
                    )
    assert offenders == [], (
        "these version claims are literals that will silently disagree with "
        f"minicc.__version__ at the next bump: {offenders}"
    )


def test_cli_version_action_derives_from_the_single_source() -> None:
    """Ask the parser's own action, not the CLI's output.

    ``--version`` used to carry the literal ``minicc 0.1.0``.  The equality test
    below still passed - for as long as the canonical version happened to be
    0.1.0 - so M4-T9's claim that every consumer *derives* from the single
    source was never measured here.  This half costs no time and no process.
    """
    import minicc
    from minicc.main import _parser

    action = next(
        item for item in _parser()._actions if "--version" in item.option_strings
    )
    assert action.version == f"minicc {minicc.__version__}", (
        f"the CLI offers {action.version!r} while the single source says "
        f"{minicc.__version__!r}; one of the two is not derived"
    )
    main_src = (REPO_ROOT / "minicc" / "main.py").read_text(encoding="utf-8")
    assert 'version="minicc 0.' not in main_src, (
        "a quoted literal version is back in minicc/main.py; it will go stale "
        "at the next bump without reddening the equality check"
    )


def test_cli_version_flag_prints_the_derived_line_in_process(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The wiring end to end, without starting an interpreter."""
    import minicc
    from minicc.main import _parser

    with pytest.raises(SystemExit) as exit_info:
        _parser().parse_args(["--version"])
    assert exit_info.value.code == 0, exit_info.value
    printed = capsys.readouterr().out.strip()
    assert printed == f"minicc {minicc.__version__}", printed


def _plane_probe_seconds(args: list[str], timeout: float = 300) -> float:
    """What this plane costs, right now, to run one interpreter on ``args``."""
    started = time.perf_counter()
    probe = subprocess.run(
        [sys.executable, *args], capture_output=True, timeout=timeout,
        cwd=str(REPO_ROOT),
    )
    elapsed = time.perf_counter() - started
    assert probe.returncode == 0, (
        f"the budget denominator could not be measured ({' '.join(args)} "
        f"exited {probe.returncode})"
    )
    return elapsed


def _bare_interpreter_seconds() -> float:
    """``python -c ""`` - the denominator the old budget wrongly used.

    Kept for the failure text, not for the arithmetic: on this machine
    ``--version`` costs 20-39x a bare interpreter with no defect anywhere
    (measured paired in M8-T112), so a ratio against this number answers
    "how fast is the machine", never "does the process terminate".
    """
    return _plane_probe_seconds(["-c", ""])


def _module_import_seconds() -> float:
    """``python -c "import minicc.main"`` - the bulk of what ``--version`` pays.

    ``--version`` is this import plus argparse printing one line, so the two
    track each other under load (paired measurements: 0.91-1.22x) while both
    inflate together when the machine is busy.
    """
    return _plane_probe_seconds(["-c", "import minicc.main"])


#: The watchdog is a multiple of the same-plane import, not of a bare start.
#: Observed worst paired ver/import on this machine is 1.22x, so 8x keeps head
#: room over scheduling jitter while still bounding a true hang at 8x the work
#: the entry point actually does.
VERSION_BUDGET_RATIO = 8

#: Below this the arm would be measuring noise; it also keeps CI (where the
#: import is ~1-2s and the whole run is ~3s) on a familiar, generous stopwatch.
VERSION_BUDGET_FLOOR = 60.0


def _version_budget(bare: float, module_import: float) -> float:
    """The budget is anchored to the import, never to the bare interpreter."""
    return max(VERSION_BUDGET_FLOOR, module_import * VERSION_BUDGET_RATIO)


def _version_timeout_message(bare: float, module_import: float, budget: float) -> str:
    """The failure must carry the ratio a bare denominator would have divided by.

    The red's whole complaint (M8-T112) was that ``40x bare`` folds "is this
    machine fast" into "does it terminate".  Printing bare, the same-plane
    import, their ratio - this run's intrinsic import/bare number, the quantity
    that was 20-39x here - lets the reader see which arm of ``max`` decided and
    why the ratio against a bare interpreter could not have.  Which arm fired
    is spelled out too: on a quiet plane the floor binds and ``8x import``
    would be the smaller number, so claiming "= 8x the import" there would be
    arithmetic the reader can check and find false.
    """
    intrinsic = module_import / bare if bare > 0 else float("inf")
    if budget == module_import * VERSION_BUDGET_RATIO:
        arm = (
            f"{VERSION_BUDGET_RATIO}x the {module_import:.2f}s it took "
            f"`python -c \"import minicc.main\"` in this same run"
        )
    else:
        arm = (
            f"the {VERSION_BUDGET_FLOOR:.0f}s floor - {VERSION_BUDGET_RATIO}x the "
            f"{module_import:.2f}s same-plane import is only "
            f"{module_import * VERSION_BUDGET_RATIO:.1f}s"
        )
    return (
        f"`--version` did not terminate within {budget:.1f}s = {arm} "
        f"(bare interpreter {bare:.2f}s, so this run's import/bare ratio is "
        f"{intrinsic:.1f}x - the number a bare-interpreter denominator would "
        "have divided by); past that ratio the claim is about termination, "
        "not about speed"
    )


def test_the_version_budget_is_anchored_to_this_planes_import() -> None:
    """M8-T112's core: the denominator changes the budget, by construction.

    Expected values are literals, not a re-call of the implementation, so
    restoring ``max(floor, bare * 40)`` reddens this cell instead of moving
    both sides together.  ``bare * 40`` on the same inputs gives 60.0 - the
    floor - which is exactly the under-determined budget batch 95 measured.
    """
    assert _version_budget(0.15, 30.0) == 240.0, (
        "a 30s import no longer buys a 240s watchdog; if the arm is back to "
        "bare*40 this returns 60.0 and the gate answers machine speed again"
    )
    assert _version_budget(0.25, 1.0) == VERSION_BUDGET_FLOOR, (
        "the floor must still bind when the plane is fast, so CI keeps its "
        "generous stopwatch instead of a sub-second budget"
    )


def test_the_timeout_message_shows_the_ratio_a_bare_denominator_would_divide_by() -> None:
    """The failure text is part of the gate: it must name every measured arm.

    Red if any of bare / import / intrinsic ratio / budget goes missing - the
    reader then cannot tell which arm of ``max`` fired, which is how the old
    60s floor reds went unattributed for batches.  Both arms get pinned: a
    message that claims "= 8x the import" while the floor is what actually
    bound is arithmetic the reader can check and find false (found by the
    M8-T112 witness run, where a quiet plane bound the floor).
    """
    ratio_arm = _version_timeout_message(bare=0.20, module_import=6.4, budget=51.2)
    assert "0.20" in ratio_arm, ratio_arm            # bare
    assert "6.40" in ratio_arm, ratio_arm            # same-plane import
    assert "32.0x" in ratio_arm, ratio_arm           # intrinsic import/bare ratio
    assert "51.2" in ratio_arm, ratio_arm            # the budget that fired
    assert "8x the 6.40s" in ratio_arm, ratio_arm    # the arm: 8x the import
    assert "termination" in ratio_arm, ratio_arm     # what the claim becomes

    floor_arm = _version_timeout_message(bare=0.20, module_import=3.0, budget=60.0)
    assert "floor" in floor_arm, floor_arm           # the arm: the floor bound
    assert "24.0" in floor_arm, floor_arm            # what 8x import would have been
    assert "= 8x" not in floor_arm, floor_arm        # no false equality claim


def test_cli_version_flag_matches():
    """The real entry point, budgeted as a function of this plane's own import.

    ``timeout=60`` was an absolute stopwatch doing two jobs at once, and its
    successor ``40x`` a bare interpreter answered the wrong question too: batch
    95 measured this machine's intrinsic ``--version``/bare at 20-39x with no
    defect anywhere, so the 40x arm sat inside the noise and the 60s floor was
    what actually decided under load - a red that said "the machine is busy".
    The budget is now ``8x`` the cost of importing ``minicc.main`` in this same
    run (paired: ``--version`` is 0.91-1.22x that import), so both sides of the
    ratio move together under load and past the floor the claim is about
    termination.
    """
    import minicc

    bare = _bare_interpreter_seconds()
    module_import = _module_import_seconds()
    budget = _version_budget(bare, module_import)
    try:
        out = subprocess.run(
            [sys.executable, "-m", "minicc.main", "--version"],
            capture_output=True, text=True, errors="replace",
            cwd=str(REPO_ROOT), timeout=budget,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            _version_timeout_message(bare, module_import, budget)
        ) from exc
    assert out.returncode == 0
    assert out.stdout.strip() == f"minicc {minicc.__version__}"


# --- web asset hygiene -----------------------------------------------------


def test_app_min_js_retired():
    assert not (REPO_ROOT / "web" / "app.min.js").exists()
    build_src = (REPO_ROOT / "scripts" / "build-web.mjs").read_text(encoding="utf-8")
    assert "app.min.js" not in build_src


def test_web_assets_only_contains_manifest_referenced_bundles():
    manifest = json.loads((REPO_ROOT / "web" / "asset-manifest.json").read_text(encoding="utf-8"))
    referenced = {asset.split("/")[-1] for asset in manifest.values()}
    on_disk = {p.name for p in (REPO_ROOT / "web" / "assets").iterdir() if p.is_file()}
    assert on_disk == referenced, f"stale or missing bundles: {on_disk ^ referenced}"
    assert len(referenced) == 3  # app.js, game.js, styles.css


# --- repo-root cleanliness -------------------------------------------------


def test_no_repro_or_log_artifacts_in_repo_root():
    banned = [
        "repro_budget.py", "repro_id_collision.py", "prev_test.txt", "testlist.txt",
        "pytest_full.log", "pytest_full.err", "pytest_verify.log",
        ".t1.log", ".t1.err", ".t2.log", ".t2.err", "=0.5", "=0.99",
    ]
    present = [name for name in banned if (REPO_ROOT / name).exists()]
    assert not (REPO_ROOT / ".tmp_audit_repro").exists()
    assert present == [], f"stray artifacts in repo root: {present}"


def test_readme_has_no_dead_npm_script():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "npm run typecheck" not in readme
    scripts = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert "typecheck" not in scripts
