"""M8-T427 — 搜索结果记录三键三个家：两个解析器与合并输出各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/tools/web.py"

FIELDS = {"snippet", "title", "url"}


def test_the_home_builds_the_record() -> None:
    """The constructor owns the three keys."""
    from minicc.tools.web import search_result

    assert search_result("t", "u", "s") == {"title": "t", "url": "u", "snippet": "s"}


def test_the_three_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second record shape."""
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
        "the web search result record is spelled by hand outside its "
        "one home: " + ", ".join(offenders)
    )


def test_every_site_asks_the_home() -> None:
    """Two parsers, the merge, and the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("search_result(") == 4, (
        "the definition plus the DuckDuckGo entry, the Bing placeholder "
        f"and the merge are the only spellings, found {source.count('search_result(')}"
    )
