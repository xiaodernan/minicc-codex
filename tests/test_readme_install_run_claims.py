"""README install/run examples must name real, runnable artifacts.

Batch 225 gates the *capability list* vocabulary (env vars, flags, endpoints,
workspace files) by checking each name is read somewhere in the source. This
file gates the *install/run examples* - the things the README tells a reader to
actually execute:

  * ``python -m minicc.X``       -> the module file exists with a ``__main__`` guard
  * ``scripts/foo.py`` / ``.ps1``-> the file exists in the repo
  * ``npm run <script>``         -> declared in the root ``package.json`` ``scripts``
  * ``minicc`` / ``minicc-web``  -> declared as console-script entry points in
    ``pyproject.toml``

These are the artifacts that rot silently: delete or rename a script, drop an npm
script, or stop declaring a console script, and the README keeps telling readers
to run something that no longer exists. Nothing checked this before.

This is *existence, not behaviour*: a module that imports but crashes on run, an
npm script whose command is broken, or a console script whose target raises on
import would all still pass here. That limit is deliberate and matches batch
225's own "names, not behaviour" boundary - the behaviour of each runnable thing
belongs to its own gate (the packaging gate runs the real console scripts, the
web smoke runs ``npm run test:web``). Behavioural claims in the install/run
section (``minicc --version`` prints a number, ``npm run check:web`` is green)
are explicitly out of scope of this file.

Explicit non-goals (do not widen this file to cover them):

  * CLI flag recognition in install/run examples (``--host`` / ``--port`` /
    ``--version``). Batch 225 already owns flag checking for the capability
    list; the install/run-only flags are few and are a future batch that
    widens flag scope, not this one.
  * ``Invoke-RestMethod`` / curl HTTP examples (``/api/tasks/batch``,
    ``/api/audit``). Those endpoints are already covered by batch 225's
    whole-README endpoint gate.
  * External tool usages (``pip install -e .``, ``python -m venv``,
    ``python -m pip wheel``). They are not project artifacts.

Floors are asserted so an empty or unparsed section cannot pass by finding
nothing.

Mutation note: the first cut of batch 225 used substring matching and its own
mutation arm showed why that is fake - renaming ``MINICC_WORKSPACE_ROOTS`` to
``...RENAMED`` kept the gate green because the old name is a prefix of the new
one. This file reuses word-boundary matching and ships its own mutation arm in
``test_the_gate_catches_*`` so a future refactor cannot silently turn it into a
vacuous check again.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
README = REPO / "README.md"
PACKAGE_JSON = REPO / "package.json"
PYPROJECT = REPO / "pyproject.toml"

#: Anti-vacuity floors. The README's install/run examples referenced 2 ``-m``
#: modules, 3 ``scripts/`` paths, 4 ``npm run`` scripts and 2 console scripts
#: when this gate was written; the floors sit below that so ordinary edits pass
#: and an empty or unparsed section cannot.
MIN_MODULES = 1
MIN_SCRIPT_PATHS = 2
MIN_NPM_SCRIPTS = 3
MIN_CONSOLE_SCRIPTS = 2


def _mentions(source: str, name: str) -> bool:
    """Is ``name`` present as a whole token, not as a prefix of something longer?

    Word boundaries make a rename a rename - see the module docstring.
    """
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", source) is not None


def _readme_text() -> str:
    return README.read_text(encoding="utf-8")


def _python_modules(text: str) -> list[str]:
    """``python -m minicc.X`` -> ``minicc.X`` (only our own ``minicc.*`` modules)."""
    return sorted(set(re.findall(r"python -m (minicc\.[A-Za-z0-9_.]+)", text)))


def _script_paths(text: str) -> list[str]:
    """``scripts\\foo.ps1`` / ``scripts/bar.py`` -> normalized ``scripts/foo.ps1``."""
    raw = re.findall(r"scripts[\\/][A-Za-z0-9_./-]+\.[A-Za-z0-9]+", text)
    return sorted(set(p.replace("\\", "/") for p in raw))


def _npm_scripts(text: str) -> list[str]:
    """``npm run <script>`` -> ``<script>``."""
    return sorted(set(re.findall(r"npm run ([A-Za-z0-9_:]+)", text)))


def _console_scripts(text: str) -> list[str]:
    """``minicc.exe`` / ``minicc-web.exe`` -> ``minicc`` / ``minicc-web``."""
    return sorted(set(re.findall(r"\b(minicc-web|minicc)\.exe", text)))


def _check_modules(text: str) -> None:
    modules = _python_modules(text)
    assert len(modules) >= MIN_MODULES, modules
    for mod in modules:
        rel = mod.replace(".", "/") + ".py"
        path = REPO / rel
        assert path.is_file(), (
            f"the README runs `python -m {mod}` but {rel} does not exist"
        )
        body = path.read_text(encoding="utf-8")
        assert re.search(r'if __name__ == [\'"]__main__[\'"]', body), (
            f"{rel} is run via `python -m {mod}` but has no `if __name__ == '__main__'` guard"
        )


def _check_script_paths(text: str) -> None:
    paths = _script_paths(text)
    assert len(paths) >= MIN_SCRIPT_PATHS, paths
    missing = [p for p in paths if not (REPO / p).is_file()]
    assert not missing, f"the README references script paths that do not exist: {missing}"


def _check_npm_scripts(text: str) -> None:
    scripts = _npm_scripts(text)
    assert len(scripts) >= MIN_NPM_SCRIPTS, scripts
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    declared = set(pkg.get("scripts", {}))
    missing = [s for s in scripts if s not in declared]
    assert not missing, (
        f"the README runs `npm run {missing}` but package.json declares no such script"
    )


def _check_console_scripts(text: str) -> None:
    names = _console_scripts(text)
    assert len(names) >= MIN_CONSOLE_SCRIPTS, names
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    missing = [
        n
        for n in names
        if not re.search(rf"^\s*{re.escape(n)}\s*=\s*[\"']", pyproject, re.M)
    ]
    assert not missing, (
        f"the README uses `{missing}.exe` but pyproject.toml declares no matching console script"
    )


def test_the_extraction_finds_a_list_of_real_size() -> None:
    text = _readme_text()
    assert len(_python_modules(text)) >= MIN_MODULES
    assert len(_script_paths(text)) >= MIN_SCRIPT_PATHS
    assert len(_npm_scripts(text)) >= MIN_NPM_SCRIPTS
    assert len(_console_scripts(text)) >= MIN_CONSOLE_SCRIPTS


def test_readme_python_minus_m_modules_are_runnable() -> None:
    _check_modules(_readme_text())


def test_readme_script_paths_exist() -> None:
    _check_script_paths(_readme_text())


def test_readme_npm_scripts_are_declared() -> None:
    _check_npm_scripts(_readme_text())


def test_readme_console_scripts_are_entry_points() -> None:
    _check_console_scripts(_readme_text())


# --- Mutation arms: prove the gate is not vacuous (batch 225 v1 was). ----------


def test_the_gate_catches_a_renamed_module() -> None:
    original = "python -m minicc.benchmarks"
    renamed = "python -m minicc.legacy_benchmarks"
    readme = _readme_text()
    assert original in readme, "anchor: original claim must be present"
    tampered = readme.replace(original, renamed)
    assert original not in tampered and renamed in tampered, (
        "anchor: the rename must have actually been applied and must not keep the old name as a prefix"
    )
    with pytest.raises(AssertionError):
        _check_modules(tampered)


def test_the_gate_catches_a_removed_script_path() -> None:
    original = "scripts/route_coverage.py"
    renamed = "scripts/legacy_route_coverage.py"
    readme = _readme_text()
    assert original in readme, "anchor: original claim must be present"
    tampered = readme.replace(original, renamed)
    assert original not in tampered and renamed in tampered, (
        "anchor: the rename must have actually been applied and must not keep the old name as a prefix"
    )
    with pytest.raises(AssertionError):
        _check_script_paths(tampered)


def test_the_gate_catches_a_dropped_npm_script() -> None:
    original = "npm run check:web"
    renamed = "npm run legacy_check_web"
    readme = _readme_text()
    assert original in readme, "anchor: original claim must be present"
    tampered = readme.replace(original, renamed)
    assert original not in tampered and renamed in tampered, (
        "anchor: the rename must have actually been applied and must not keep the old name as a prefix"
    )
    with pytest.raises(AssertionError):
        _check_npm_scripts(tampered)


def test_the_gate_catches_a_removed_console_script() -> None:
    original = "minicc-web.exe"
    renamed = "minicc-legacy-web.exe"
    readme = _readme_text()
    assert original in readme, "anchor: original claim must be present"
    tampered = readme.replace(original, renamed)
    assert original not in tampered and renamed in tampered, (
        "anchor: the rename must have actually been applied and must not keep the old name as a prefix"
    )
    with pytest.raises(AssertionError):
        _check_console_scripts(tampered)
