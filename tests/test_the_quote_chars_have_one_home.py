"""M8-T516 — QUOTE_CHARS 一个键六个家：check_commands/bash/config"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"

QUOTE_CHARS = frozenset({'"', "'"})


def test_the_quote_chars_exist_in_shell_lexing() -> None:
    """QUOTE_CHARS exists in shell_lexing.py."""
    from minicc.shell_lexing import QUOTE_CHARS as HomeQuoteChars
    assert HomeQuoteChars == QUOTE_CHARS


def test_check_commands_imports_from_shell_lexing() -> None:
    """check_commands.py imports QUOTE_CHARS from shell_lexing."""
    from minicc.agent.check_commands import QUOTE_CHARS as CheckCommandsQuoteChars
    assert CheckCommandsQuoteChars == QUOTE_CHARS


def test_bash_imports_from_shell_lexing() -> None:
    """bash.py imports QUOTE_CHARS from shell_lexing."""
    from minicc.tools.bash import QUOTE_CHARS as BashQuoteChars
    assert BashQuoteChars == QUOTE_CHARS


def test_config_imports_from_shell_lexing() -> None:
    """config.py imports QUOTE_CHARS from shell_lexing."""
    from minicc.config import QUOTE_CHARS as ConfigQuoteChars
    assert ConfigQuoteChars == QUOTE_CHARS


def test_no_module_has_inline_quote_chars() -> None:
    """No module hard-codes {'"', "'"} inline (outside shell_lexing)."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if elements == QUOTE_CHARS and len(node.elts) == 2:
                relative = path.relative_to(REPO).as_posix()
                if relative != "minicc/shell_lexing.py":
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "Inline quote character sets found outside "
        "their one home (minicc/shell_lexing.py): "
        + ", ".join(offenders)
    )


def test_the_home_is_in_shell_lexing_py() -> None:
    """The home is in shell_lexing.py and is exported."""
    import minicc.shell_lexing as sl

    assert hasattr(sl, "QUOTE_CHARS"), "shell_lexing must export QUOTE_CHARS"
    assert sl.QUOTE_CHARS == frozenset({'"', "'"})