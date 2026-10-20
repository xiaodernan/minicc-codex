"""M8-T303: the loader must refuse a contract the grader will refuse.

The embedded grader resolves a contract path against the workspace root and
refuses it when it escapes.  The loader did not - so a task whose contract
named ``../outside.txt`` passed validation, the agent ran a **full turn**,
and the grader then refused the whole run as NO-RESULT.  The cost of a
malformed task was paid before anything complained.

The loader owes the same rule, applied before the agent is paid.

This door pins:

* an escaping contract path is refused at load time;
* the control: an ordinary in-workspace path still passes.
"""

from __future__ import annotations

from typing import Any

import pytest

from minicc.bench_tasks import loader_blockers, spec_blockers


def _spec(path: str) -> dict[str, Any]:
    return {"files": [{"path": path, "contains": "x"}]}


@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        "../../etc/passwd",
        "sub/../../outside.txt",
        "/etc/passwd",
        "C:/Windows/system.ini",
    ],
)
def test_an_escaping_contract_path_is_refused(path: str) -> None:
    blockers = loader_blockers("file_contract", _spec(path))
    assert blockers, f"the escaping path {path!r} was not refused at load time"
    assert any("escape" in item for item in blockers), blockers


@pytest.mark.parametrize(
    "path",
    ["app.py", "src/app.py", "sub/dir/app.py", "./app.py"],
)
def test_an_ordinary_contract_path_still_passes(path: str) -> None:
    """The control: the gate is a rule, not a blanket ban."""
    blockers = loader_blockers("file_contract", _spec(path))
    assert not blockers, f"an in-workspace path was refused: {blockers}"


def test_an_empty_contract_is_still_refused() -> None:
    """The control: the pre-existing blocker still fires."""
    blockers = loader_blockers("file_contract", {"files": []})
    assert blockers


def test_the_grading_path_keeps_its_own_contract() -> None:
    """M8-T303: the escape rule is loader-only.

    The grading path refuses an escaping contract with the **grader's**
    exit code - that is a separate contract, pinned by
    ``tests/test_grader_no_result_channel.py``, and the loader's extra
    rule must not change it.
    """
    assert not any(
        "escape" in item for item in spec_blockers("file_contract", _spec("../outside.txt"))
    ), "the escape rule leaked into the grading path"
