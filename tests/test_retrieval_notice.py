"""M8-T74: the interactive candidate list must carry the walk's denominator.

M8-T72 closed this class on the evaluation path (``benchmarks.py``).  The same
budgeted ``os.walk`` feeds the chat path, where a short list is shown to a human
as "本地索引提供 N 个候选文件" and to the model as the only evidence hint of the
turn - both phrased like statements about the whole workspace.

Two halves, deliberately:

* a behavioural gate over the three shipped builders, run against a *real*
  index so the hit shape and the census come from production, and
* a structural gate that enumerates index consumers from the AST, so a fourth
  reader cannot appear without going red here.  The checker takes a parsed tree
  rather than a line number, and the reverse control plants a violating site in
  source text instead of editing the tracked file.
"""

from __future__ import annotations

import ast
from pathlib import Path

from minicc.agent.retrieval import LocalEvidenceIndex, census_is_complete, census_notice
from minicc.web import _evidence_for_planner, _evidence_model_note, _evidence_trace_event

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTICE_MARK = "[检索口径]"

_COMPLETE = {
    "files_indexed": 9,
    "files_seen": 9,
    "files_skipped": 0,
    "file_limit": 1200,
    "directories_walked": 3,
    "directory_budget": 4800,
    "truncated": False,
}
_TRUNCATED = {**_COMPLETE, "files_seen": 1, "files_indexed": 1, "truncated": True}


# --------------------------------------------------------------------------
# source measurement


def _call_names(node: ast.AST) -> set[str]:
    """Every callee name reachable in ``node``, for chained and plain calls."""
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def uncredited_index_sites(tree: ast.AST) -> list[str]:
    """Functions that search the bounded index without ever asking its census.

    A site is credited when the same function reads ``stats()`` (the census), so
    the judgement stays with ``census_is_complete`` rather than a second copy.
    """
    sites: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        called = _call_names(node)
        if "get_evidence_index" in called and "search" in called:
            if "stats" not in called:
                sites.append(f"{node.name}:{node.lineno}")
    return sites


def production_sites() -> list[tuple[Path, list[str]]]:
    found: list[tuple[Path, list[str]]] = []
    for path in sorted((REPO_ROOT / "minicc").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        dirty = uncredited_index_sites(tree)
        if dirty:
            found.append((path, dirty))
    return found


# --------------------------------------------------------------------------
# fixtures built by the real index


def _tree(root: Path, files: int, *, max_files: int | None = None) -> LocalEvidenceIndex:
    workspace = root / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    for index in range(files):
        (workspace / f"widget_{index}.py").write_text(
            f"def parse_widget_{index}():\n    return {index}\n", encoding="utf-8"
        )
    kwargs = {} if max_files is None else {"max_files": max_files}
    return LocalEvidenceIndex(workspace, **kwargs)


# --------------------------------------------------------------------------
# the structural gate, both ways


def test_no_production_site_searches_the_index_without_reading_its_census() -> None:
    dirty = production_sites()
    assert dirty == [], (
        "these functions hand a bounded walk's result to a human or the model "
        f"without ever reading stats(): {dirty}"
    )


def test_the_checker_reports_a_planted_site_and_accepts_a_credited_one() -> None:
    """Green above means nothing unless red is reachable."""
    planted = ast.parse(
        "from minicc.agent.retrieval import get_evidence_index\n"
        "def handler():\n"
        "    return get_evidence_index(p).search('widget')\n"
    )
    credited = ast.parse(
        "from minicc.agent.retrieval import get_evidence_index\n"
        "def handler():\n"
        "    index = get_evidence_index(p)\n"
        "    hits = index.search('widget')\n"
        "    return hits, index.stats()\n"
    )
    assert uncredited_index_sites(planted) == ["handler:2"], (
        "the planted reader never asks stats(); the checker must name it"
    )
    assert uncredited_index_sites(credited) == [], (
        "a reader that does take the census must not be reported, or the gate "
        "becomes noise"
    )


def test_the_census_predicates_agree_with_the_notice() -> None:
    """The sentence and the boolean answer the same question in both directions."""
    assert census_is_complete(_COMPLETE) is True
    assert census_notice(_COMPLETE) == "", "a complete walk must not add noise"
    assert census_is_complete(_TRUNCATED) is False
    assert NOTICE_MARK in census_notice(_TRUNCATED)
    assert "file_limit=1200" in census_notice(_TRUNCATED), (
        "the notice has to carry the denominator, not just an apology"
    )
    assert NOTICE_MARK in census_notice(None), (
        "an unknown denominator is not a proven complete one"
    )


# --------------------------------------------------------------------------
# the three consumers, on real hits and a real census


def test_a_complete_walk_adds_no_caveat_to_any_consumer(tmp_path: Path) -> None:
    index = _tree(tmp_path, 3)
    hits = index.search("parse widget")
    census = index.stats()
    assert hits and census_is_complete(census) is True, census
    assert NOTICE_MARK not in _evidence_model_note(hits, census)
    event = _evidence_trace_event(hits, census)
    assert event is not None
    assert event["summary"] == f"本地索引提供 {len(hits)} 个候选文件，Agent 会逐项复核"
    assert event["detail"]["census_complete"] is True
    assert NOTICE_MARK not in _evidence_for_planner(hits, census)


def test_a_truncated_walk_tells_the_model_and_the_human_aloud(tmp_path: Path) -> None:
    index = _tree(tmp_path / "cut", 3, max_files=1)
    hits = index.search("parse widget")
    census = index.stats()
    assert census_is_complete(census) is False, (
        f"the planted tree must truncate; got {census}"
    )
    note = _evidence_model_note(hits, census)
    assert NOTICE_MARK in note and "file_limit=1" in note, note
    event = _evidence_trace_event(hits, census)
    assert event is not None
    assert "未走完工作区" in event["summary"], event["summary"]
    assert event["detail"]["census_complete"] is False
    assert event["detail"]["census"]["file_limit"] == 1
    planner = _evidence_for_planner(hits, census)
    assert NOTICE_MARK in planner and planner.endswith(census_notice(census))


def test_an_empty_list_from_a_truncated_walk_is_not_reported_as_no_evidence(
    tmp_path: Path,
) -> None:
    """The sharpest shape of the defect: nothing matched *and* the walk stopped.

    Silence here is what told the model "there is nothing else in the workspace".
    """
    index = _tree(tmp_path / "none", 3, max_files=1)
    hits = index.search("zzz_no_such_marker_at_all")
    census = index.stats()
    assert hits == [], "the planted query must genuinely match nothing"
    assert census_is_complete(census) is False, census
    assert NOTICE_MARK in _evidence_model_note(hits, census)
    assert _evidence_trace_event(hits, census) is None, (
        "no rows, so no row: the model note above is the only channel here"
    )
    assert _evidence_for_planner(hits, census).startswith(NOTICE_MARK)


def test_a_complete_walk_with_no_hits_stays_silent(tmp_path: Path) -> None:
    index = _tree(tmp_path / "quiet", 2)
    census = index.stats()
    assert census_is_complete(census) is True, census
    hits = index.search("zzz_no_such_marker_at_all")
    assert hits == []
    assert _evidence_model_note(hits, census) == "", (
        "absence plus a complete walk really is absence - do not add a warning"
    )
    assert _evidence_for_planner(hits, census) == ""
