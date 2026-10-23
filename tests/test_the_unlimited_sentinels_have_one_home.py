"""M8-T396 — 「无限制」哨兵词表两个家：soft cap 的 int/float 两个闭包各写一份"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/config.py"

SENTINELS = frozenset({"0", "none", "off", "unlimited"})


def test_the_home_exists_in_config() -> None:
    """config.py owns the no-limit spellings."""
    from minicc.config import UNLIMITED_SENTINELS

    assert UNLIMITED_SENTINELS == SENTINELS


def test_no_module_inlines_the_sentinels() -> None:
    """No module spells the sentinel set as a literal outside the one declaration."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple | ast.List):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) >= 2 and elements == SENTINELS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the no-limit sentinels are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


@pytest.fixture()
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated cwd + MINICC_HOME; MINICC_* never leaks out."""
    cwd = tmp_path / "cwd"
    home = tmp_path / "home"
    workspace = tmp_path / "ws"
    for directory in (cwd, home, workspace):
        directory.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "sk-test-key")
    monkeypatch.chdir(cwd)
    for key in [
        k for k in os.environ
        if k.startswith("MINICC_") and k not in {"MINICC_HOME", "MINICC_API_KEY"}
    ]:
        monkeypatch.delenv(key)
    return workspace


def test_both_soft_caps_still_read_the_sentinels(
    isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"off" and "none" mean no limit on both axes; a number still parses."""
    from minicc.config import load_config

    monkeypatch.setenv("MINICC_SOFT_MAX_TOKENS", "none")
    monkeypatch.setenv("MINICC_SOFT_MAX_DURATION_SECONDS", "off")
    config = load_config(workspace=isolated_config)
    assert config.soft_max_tokens is None
    assert config.soft_max_duration_seconds is None

    monkeypatch.setenv("MINICC_SOFT_MAX_TOKENS", "4321")
    monkeypatch.setenv("MINICC_SOFT_MAX_DURATION_SECONDS", "12.5")
    config = load_config(workspace=isolated_config)
    assert config.soft_max_tokens == 4321
    assert config.soft_max_duration_seconds == 12.5
