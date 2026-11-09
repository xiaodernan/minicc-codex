"""M8-T679 — the sandbox modes and the unavailable-backend word have one home.

``minicc/config.py`` owns the resolved-sandbox vocabulary:
``SANDBOX_MODE_HOST`` / ``SANDBOX_MODE_DOCKER`` / ``SANDBOX_MODE_AUTO``
(``SANDBOX_MODES`` as their frozenset) and ``SANDBOX_BACKEND_UNAVAILABLE``
(the one extra word the runtime is allowed to answer with).

Scope: the sandbox-fact modules only.  ``"host"`` / ``"docker"`` / ``"auto"``
also spell unrelated facts elsewhere in the product (config vocabularies,
orchestration_mode, PROVISION labels); this gate holds the sandbox modules to
constants and leaves the rest of the product alone.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPED = {
    REPO / "minicc" / "config.py",
    REPO / "minicc" / "sandbox.py",
    REPO / "minicc" / "tools" / "__init__.py",
    REPO / "minicc" / "web.py",
}
HOME = REPO / "minicc" / "config.py"
SANDBOX_WORDS = {"host", "docker", "unavailable"}
DEF_NAMES = {
    "SANDBOX_MODE_HOST": "host",
    "SANDBOX_MODE_DOCKER": "docker",
    "SANDBOX_MODE_AUTO": "auto",
    "SANDBOX_BACKEND_UNAVAILABLE": "unavailable",
}


def _prose_nodes(tree: ast.Module) -> set[int]:
    prose: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            for child in ast.walk(node):
                prose.add(id(child))
    return prose


def test_the_home_defines_the_sandbox_vocabulary() -> None:
    from minicc import config

    for name, value in DEF_NAMES.items():
        assert getattr(config, name) == value
    assert config.SANDBOX_MODES == frozenset({
        config.SANDBOX_MODE_HOST,
        config.SANDBOX_MODE_DOCKER,
        config.SANDBOX_MODE_AUTO,
    })
    assert config.DEFAULT_SANDBOX_MODE == config.SANDBOX_MODE_AUTO


def test_no_bare_sandbox_mode_literals_in_the_sandbox_fact_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        if path == HOME:
            continue
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        prose = _prose_nodes(tree)
        parents: dict[int, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[id(child)] = parent
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or node.value not in SANDBOX_WORDS:
                continue
            if id(node) in prose:
                continue
            parent = parents.get(id(node))
            if (
                isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Attribute)
                and parent.func.attr == "which"
                and node is parent.args[0]
            ):
                # shutil.which("docker") asks whether the docker binary
                # exists — a filesystem probe, not a sandbox-mode fact.
                continue
            relative = path.relative_to(REPO).as_posix()
            offenders.append(f"{relative}:{node.lineno}: {src.splitlines()[node.lineno-1].strip()[:170]}")
    assert offenders == [], (
        "bare sandbox literal - use SANDBOX_MODE_*/SANDBOX_BACKEND_UNAVAILABLE "
        "from minicc.config:\n" + "\n".join(offenders)
    )
