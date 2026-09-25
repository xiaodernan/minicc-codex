"""M4-T9: cleanup and version single-source guards.

Pin the durability fixes so they cannot silently regress: the version lives in
exactly one place (minicc.__version__) and every consumer derives from it; the
retired web/app.min.js stays gone and is no longer generated; web/assets holds
only the bundles the manifest references; the repo root carries no repro/log
artifacts; and the README no longer points at a non-existent npm script.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
import subprocess
import sys
import tomllib
from pathlib import Path

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


def test_cli_version_flag_matches():
    import minicc

    out = subprocess.run(
        [sys.executable, "-m", "minicc.main", "--version"],
        capture_output=True, text=True, errors="replace", cwd=str(REPO_ROOT), timeout=60,
    )
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
