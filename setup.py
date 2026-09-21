"""Build hooks for the wheel: the workbench and IDE assets live at the repo root.

``web/`` and ``ide/`` are plain asset trees, not Python packages, so the
``[tool.setuptools.packages.find] include = ["minicc*"]`` rule in
``pyproject.toml`` cannot reach them and ``[tool.setuptools.package-data]`` only
ships files that already live inside a package directory. Copying them into
``build/lib/minicc/{web_static,ide_static}`` right after ``build_py`` makes them
part of the installed package, which is what ``minicc/static_assets.py`` looks
for at runtime.

Doing the copy at build time (instead of symlinking or moving the real
directories) keeps the checkout layout that ``scripts/build-web.mjs``, the
frontend smoke tests and ``npm run check:web`` all assume.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

HERE = Path(__file__).resolve().parent
# source directory -> package-relative destination inside build/lib
STATIC_ASSETS = {
    "web": "minicc/web_static",
    "ide": "minicc/ide_static",
}
SKIP_DIRS = {"node_modules", "__pycache__", ".pytest_cache", ".playwright-cli"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".log"}


def _wanted(source: Path) -> bool:
    if any(part in SKIP_DIRS for part in source.parts):
        return False
    return source.suffix not in SKIP_SUFFIXES


def copy_static_assets(build_lib: Path) -> int:
    """Mirror the asset trees into *build_lib*; returns the number of files."""
    copied = 0
    for folder, target in STATIC_ASSETS.items():
        source = HERE / folder
        if not source.is_dir():
            raise SystemExit(f"build aborted: {folder}/ is missing from the source tree")
        destination_root = build_lib / target
        for path in sorted(source.rglob("*")):
            if not path.is_file() or not _wanted(path.relative_to(HERE)):
                continue
            target_path = destination_root / path.relative_to(source)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target_path)
            copied += 1
    return copied


class build_py_with_static(build_py):
    def run(self) -> None:
        super().run()
        # ``bdist_wheel`` collects payload by walking build/lib, so the copies
        # need no registration here (setuptools' ``outfiles`` is not writable
        # from subclasses since it became a lazy attribute).
        copy_static_assets(Path(self.build_lib))


if __name__ == "__main__":
    setup(cmdclass={"build_py": build_py_with_static})
