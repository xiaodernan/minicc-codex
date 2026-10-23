"""M8-T382 — sandbox mode 一个词表三个家：config.py / sandbox.py / main.py 的 CLI choices"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"

SANDBOX_MODES = frozenset({"host", "docker", "auto"})


def test_the_sandbox_modes_exist_in_config() -> None:
    """SANDBOX_MODES exists in config.py."""
    from minicc.config import SANDBOX_MODES as ConfigModes
    assert ConfigModes == SANDBOX_MODES


def test_sandbox_imports_from_config() -> None:
    """sandbox.py imports SANDBOX_MODES from config."""
    from minicc.sandbox import SANDBOX_MODES as SandboxModes
    assert SandboxModes == SANDBOX_MODES


def test_no_module_has_inline_sandbox_modes() -> None:
    """No module hard-codes {"host", "docker", "auto"} inline (set or tuple)."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if elements == SANDBOX_MODES and len(node.elts) == 3:
                relative = path.relative_to(REPO).as_posix()
                if relative != "minicc/config.py":
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "Inline sandbox mode literals found outside "
        "their one home (minicc/config.py): "
        + ", ".join(offenders)
    )


def test_the_home_is_in_config_py() -> None:
    """The home is in config.py and is exported."""
    import minicc.config as cfg

    assert hasattr(cfg, "SANDBOX_MODES"), "config must export SANDBOX_MODES"
    assert cfg.SANDBOX_MODES == frozenset({"host", "docker", "auto"})


def test_cli_choices_derive_from_the_one_home() -> None:
    """main.py's --sandbox choices are derived from SANDBOX_MODES, not hand-written."""
    from minicc.config import SANDBOX_MODES as Modes
    from minicc.main import _parser

    parser = _parser()
    action = next(
        action for action in parser._actions if "--sandbox" in action.option_strings
    )
    assert action.choices is not None
    assert set(action.choices) == set(Modes)
