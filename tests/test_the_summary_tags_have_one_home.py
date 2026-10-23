"""The tool-summary tag vocabulary must have exactly one home.

M8-T480: ``CODE_`` now names **two** vocabularies and each has its own home.
``tools/schemas.py`` owns the tool-summary tags - ``[UPPER_SNAKE]`` strings
rendered by ``tagged()`` - and ``webserver.py`` owns the HTTP API's
machine-readable error codes - ``lower_snake`` strings looked up over an
exception's MRO (M8-T474).  They are different facts that happen to share a
naming convention, so this door scopes its census to the homes and leaves each
vocabulary's own door to pin its contents.  Before this batch the census read
"every ``CODE_*`` in the package lives in ``schemas.py``", which M8-T474 turned
into a permanent false red: the HTTP vocabulary is a legitimate second home,
and a door that cannot tell two vocabularies apart ends up accusing a correct
one.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from minicc.tools import schemas
from minicc.tools.registry import error_result, denied_result
from minicc.tools.schemas import tagged

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = "minicc/tools/schemas.py"
#: M8-T480: the two homes a ``CODE_*`` name may live in.  Each vocabulary has
#: its own door (``test_the_error_code_vocabulary_have_one_home.py`` for the
#: HTTP codes); this one only insists the name is defined once and in one of
#: them, so a third home cannot appear unnoticed.
API_HOME = "minicc/webserver.py"
HOMES = frozenset({HOME, API_HOME})
TAG_SHAPE = re.compile(r"^\[[A-Z][A-Z_0-9]*\]")

#: Not tool-summary tags, and deliberately not in the vocabulary: ``[DONE]``
#: is the SSE terminator the *provider* protocol defines, and ``[REDACTED]``
#: is a marker written into file **content** where a secret used to be.  Both
#: are foreign wire facts with their own owners.
FOREIGN_TAGS = ("[DONE]", "[REDACTED]")


def _codes() -> dict[str, str]:
    tree = ast.parse((REPO / HOME).read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id.startswith("CODE_")
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            found[node.targets[0].id] = node.value.value
    return found


def _code_homes() -> dict[str, list[str]]:
    """Every ``CODE_*`` name in the package, and the modules defining it."""
    found: dict[str, list[str]] = {}
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id.startswith("CODE_")
            ):
                found.setdefault(node.targets[0].id, []).append(rel)
    return found


def test_a_code_name_is_defined_exactly_once():
    """Two definitions of one name is the drift, whichever module they are in."""
    duplicates = {name: homes for name, homes in _code_homes().items() if len(homes) != 1}
    assert duplicates == {}, duplicates


def test_every_code_name_lives_in_one_of_the_two_vocabulary_homes():
    """A ``CODE_*`` name belongs to the summary tags or to the HTTP codes.

    M8-T480: ``webserver.py`` is a legitimate second home (M8-T474), so the
    census is the set of homes rather than the one module.  A third module
    defining a ``CODE_*`` name is what this still refuses.
    """
    strangers = {name: homes for name, homes in _code_homes().items()
                 if homes[0] not in HOMES}
    assert strangers == {}, strangers


def test_both_vocabularies_are_still_populated():
    """Neither home may go quietly empty and leave the census vacuous."""
    homes = _code_homes()
    assert {name for name, where in homes.items() if where == [HOME]} == set(_codes()), homes
    assert any(where == [API_HOME] for where in homes.values()), homes


def test_the_two_vocabularies_share_no_name():
    """One spelling in both homes would be one fact with two owners."""
    summary = {name for name, where in _code_homes().items() if where == [HOME]}
    api = {name for name, where in _code_homes().items() if where == [API_HOME]}
    assert summary & api == set(), sorted(summary & api)


def test_the_home_is_a_leaf_module():
    tree = ast.parse((REPO / HOME).read_text(encoding="utf-8"))
    intra = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.level > 0 or (node.module or "").startswith("minicc")):
            intra.append(node.lineno)
        elif isinstance(node, ast.Import):
            intra.extend(node.lineno for alias in node.names if alias.name.startswith("minicc"))
    assert intra == [], intra


def test_tagged_is_the_one_wire_shape():
    assert tagged("CODE", "message") == "[CODE] message"
    assert tagged("X", "") == "[X] "


@pytest.mark.parametrize("name", sorted(_codes()))
def test_every_code_round_trips_through_the_shape(name):
    code = getattr(schemas, name)
    assert tagged(code, "body") == f"[{code}] body"


def test_no_site_spells_a_tag_by_hand():
    """A hand-spelled tag is a code the vocabulary cannot rename.

    Every ``[TAG]`` literal in the package must live in the home - the two
    documented exceptions are foreign wire facts with their own owners.
    """
    strays = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            values = []
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                values = [node.value]
            elif isinstance(node, ast.JoinedStr):
                values = [
                    "".join(
                        part.value
                        for part in node.values
                        if isinstance(part, ast.Constant) and isinstance(part.value, str)
                    )
                ]
            for value in values:
                if TAG_SHAPE.match(value) and value not in FOREIGN_TAGS:
                    strays.append((path.as_posix(), node.lineno, value))
    assert strays == [], strays


def test_the_error_results_are_built_by_the_home():
    assert error_result("MY_CODE", "body").summary == "[MY_CODE] body"
    assert denied_result("body").summary.startswith("[DENIED] ")


def test_the_old_home_is_gone():
    """registry used to define the four codes itself; it imports them now."""
    source = (REPO / "minicc" / "tools" / "registry.py").read_text(encoding="utf-8")
    assert "CODE_UNKNOWN_TOOL = " not in source
    assert "CODE_DENIED = " not in source
    assert "from .schemas import" in source


def test_a_guarded_summary_keeps_its_exact_text():
    """The refactor moved the spelling, never the bytes the model reads."""
    assert tagged(schemas.CODE_CANCELLED, "任务已取消，未执行工具 read_file") == (
        "[CANCELLED] 任务已取消，未执行工具 read_file"
    )
    assert tagged(schemas.CODE_TOOL_ERROR, "无法执行命令: boom") == "[TOOL_ERROR] 无法执行命令: boom"
    assert tagged(schemas.CODE_INVALID_ARGUMENTS, "command 不能为空") == (
        "[INVALID_ARGUMENTS] command 不能为空"
    )
