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
    assert importlib_metadata.version("minicc") == canonical
    assert mcp.__version__ == canonical
    # mcp.py must build clientInfo from __version__, never a hardcoded literal.
    mcp_src = (REPO_ROOT / "minicc" / "mcp.py").read_text(encoding="utf-8")
    assert '"version": __version__' in mcp_src
    assert '"version": "0.' not in mcp_src


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


def _interpreter_startup_seconds() -> float:
    """What it costs to start one interpreter on this machine, right now."""
    started = time.perf_counter()
    probe = subprocess.run(
        [sys.executable, "-c", ""], capture_output=True, timeout=300,
    )
    elapsed = time.perf_counter() - started
    assert probe.returncode == 0, (
        f"the startup denominator could not be measured (exit {probe.returncode})"
    )
    return elapsed


def test_cli_version_flag_matches():
    """The real entry point, budgeted as a function of this machine's own speed.

    ``timeout=60`` was an absolute stopwatch doing two jobs at once: "does the
    process terminate" and "is this machine fast".  Under a loaded machine a
    ``--version`` run hit 60s and the red said nothing about the product.  The
    budget is now 40x the cost of starting an interpreter measured in this same
    run, so past the floor it answers the first question only.
    """
    import minicc

    startup = _interpreter_startup_seconds()
    budget = max(60.0, startup * 40)
    try:
        out = subprocess.run(
            [sys.executable, "-m", "minicc.main", "--version"],
            capture_output=True, text=True, errors="replace",
            cwd=str(REPO_ROOT), timeout=budget,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            f"`--version` did not terminate within {budget:.1f}s = 40x the "
            f"{startup:.2f}s it took to start an interpreter in this same run; "
            "beyond that ratio the claim is about termination, not about speed"
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
