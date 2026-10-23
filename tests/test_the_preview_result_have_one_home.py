"""M8-T431 — 文件预览结果四键两个家：deny 拒绝与正常读取各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/web.py"

FIELDS = {"content", "path", "status", "summary"}


def test_the_home_builds_the_preview() -> None:
    """The constructor owns the four keys."""
    from minicc.web import _preview_result

    assert _preview_result("ok", "12 行", "x = 1", "a.py") == {
        "status": "ok",
        "summary": "12 行",
        "content": "x = 1",
        "path": "a.py",
    }


def test_the_four_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second preview shape."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if keys == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the file preview result is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_exits_ask_the_home() -> None:
    """The deny refusal, the normal read, and the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_preview_result(") == 3, (
        "the definition plus the two exits are the only spellings, "
        f"found {source.count('_preview_result(')}"
    )
