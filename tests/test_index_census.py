"""M8-T72: a walk that stopped early must say where it stopped.

``LocalEvidenceIndex`` has two budgets and reports the answer to neither of
them.  ``_files()`` returns as soon as it has ``max_files`` candidates, and it
also breaks out of ``os.walk`` when the directory count passes
``max(4000, max_files * 4)``.  When either fires, every file past that point is
simply absent, and the metric that was computed over the surviving prefix is
indistinguishable - in the report - from a metric computed over the workspace.

Measured on ``ac76061`` with the planted trees this file builds (batch record
has the table):

* 1301 ``.py`` files, default cap 1200: the target sorts past the cut, so
  ``evaluate_retrieval`` returns ``recall@5=0.0`` and
  ``retrieval_decision`` prints "lexical 基线不达标, 下一步评估引入本地
  embedding" - an architecture recommendation produced by a walk budget.  The
  report keys are ``case_count, ks, metrics, results, schema_version,
  workspace``.  The index's own ``stats()`` - which does say ``truncated`` -
  is discarded by the caller and appears nowhere in it.
* 4300 directories holding 20 files, all of them past directory 4000: with the
  default file budget the walk finishes (the ceiling is ``max(4000, 1200 * 4)``)
  and indexes 20 of 20.  Score the same tree with ``max_files=900`` and the
  ceiling drops to 4000, so the walk stops before any of them: ``stats()`` then
  reads ``files_indexed=0, truncated=false``.  The only budget that file
  publishes is ``file_limit``, and 0 is not >= 900 - nothing in it reveals that
  a ceiling was reached at all.

That second shape is why ``truncated`` cannot be derived from the record count
at all.  ``truncated = len(records) >= max_files`` reads "did I fill the file
budget", and it goes wrong in both directions: a walk that died on the
*directory* budget indexes too few to look truncated, and a walk that collected
``max_files`` candidates of which some then refused to open indexes too few to
look truncated either - so the flag can say "complete" precisely when the
denominator is short, which is the only case the flag exists for.  Here the
candidate is made to refuse by driving the ``except OSError`` branch that
production already has, rather than by hoping for a race.

The rule this gate installs is the one ``minicc/impact.py`` already applies to
itself (``truncated`` plus ``analysis_incomplete`` plus a ``limitations``
list): a number whose denominator is short is reported as uninterpretable, not
as a low score.  ``census_is_complete`` is that judgement and it is written
once - the report, the decision text and this file all read it from there.
"""

from __future__ import annotations

import contextlib
import inspect
import json
from pathlib import Path

from minicc import benchmarks
from minicc.agent.retrieval import LocalEvidenceIndex, census_is_complete


@contextlib.contextmanager
def unreadable(*names: str):
    """Make these filenames raise OSError on open(), the way a file that
    vanished mid-walk does.  This drives the ``except OSError`` branch of
    ``_build_record`` that production already has; it does not add one."""
    original = Path.open

    def patched(self, *args, **kwargs):
        if self.name in names:
            raise OSError(2, "No such file or directory", str(self))
        return original(self, *args, **kwargs)

    Path.open = patched  # type: ignore[method-assign]
    try:
        yield
    finally:
        Path.open = original  # type: ignore[method-assign]
        assert Path.open is original, "the patch leaked"


@contextlib.contextmanager
def vanishing(*names: str):
    """The other drop channel: a candidate that was there when the walk
    collected it and is gone by the time the indexer asks for its signature."""
    original = Path.stat

    def patched(self, **kwargs):
        if self.name in names:
            raise FileNotFoundError(2, "No such file or directory", str(self))
        return original(self, **kwargs)

    Path.stat = patched  # type: ignore[method-assign]
    try:
        yield
    finally:
        Path.stat = original  # type: ignore[method-assign]
        assert Path.stat is original, "the patch leaked"


def _tree(root: Path, count: int, *, dirs: int = 0) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if dirs:
        # Files only in the LAST directories, so a walk that dies on the
        # directory budget sees none of them.
        for i in range(dirs):
            (root / f"d{i:04d}").mkdir(parents=True, exist_ok=True)
        for i in range(count):
            directory = root / f"d{dirs - count + i:04d}"
            (directory / f"deep_{i}.py").write_text(
                f"def deep_marker_{i}_zzz():\n    return {i}\n", encoding="utf-8"
            )
        return root
    for i in range(count):
        # zz_* sorts last within a directory, so it is past a file-budget cut.
        name = "zz_target.py" if i == count - 1 else f"f{i:05d}.py"
        marker = "unique_marker_for_zz_target" if name == "zz_target.py" else f"shard_{i}_zzz"
        (root / name).write_text(f"def {marker}():\n    return {i}\n", encoding="utf-8")
    return root


def _text_files(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if path.is_file() and not path.name.startswith(".")
    )


CENSUS_KEYS = {
    "files_indexed",
    "files_seen",
    "files_skipped",
    "file_limit",
    "directories_walked",
    "directory_budget",
    "truncated",
}


# --- the census has to exist, and has to answer for itself -----------------


def test_index_stats_publish_what_the_walk_saw(tmp_path: Path) -> None:
    ws = _tree(tmp_path, 4)
    stats = LocalEvidenceIndex(ws).stats()
    missing = CENSUS_KEYS - set(stats)
    assert not missing, (
        f"stats() reports {sorted(stats)} but not {sorted(missing)} - a metric "
        "computed over a prefix of the workspace has to carry the prefix's size, "
        "or its reader cannot tell it apart from a full scan"
    )
    assert stats["files_seen"] == len(_text_files(ws)) == stats["files_indexed"], (
        f"on a walk that ended by exhaustion the census has to add up: {stats}"
    )
    assert stats["truncated"] is False
    assert census_is_complete(stats) is True, (
        "a complete walk must not be flagged - otherwise every gate that reads "
        "this flag reddens on healthy trees and gets ignored"
    )


def test_the_census_adds_up_when_a_file_refuses_to_open(tmp_path: Path) -> None:
    ws = _tree(tmp_path, 12)
    with unreadable("f00003.py", "f00007.py"):
        stats = LocalEvidenceIndex(ws, max_files=10).stats()
    assert stats["files_seen"] == 10, (
        f"the walk collects up to the budget before returning, so the candidate "
        f"count is the budget: {stats}"
    )
    assert stats["files_skipped"] == 2, (
        f"two candidates refused to open and nothing counted them: {stats}"
    )
    assert stats["files_indexed"] + stats["files_skipped"] == stats["files_seen"], (
        f"the census has to reconcile: {stats}"
    )
    assert stats["truncated"] is True, (
        "this is the shape the old flag got wrong: 8 records is below the limit "
        "of 10, so 'did I fill the budget' answers 'no' while the walk really "
        f"stopped early and 4 of 12 files were never even offered ({stats})"
    )
    assert census_is_complete(stats) is False


def test_a_walk_that_dies_on_the_directory_budget_reports_a_short_denominator(
    tmp_path: Path,
) -> None:
    ws = _tree(tmp_path, 5, dirs=40)
    on_disk = _text_files(ws)
    stats = LocalEvidenceIndex(ws, max_directories=20).stats()
    assert stats["directories_walked"] == 20, (
        f"the walk broke at the budget and the report must say where: {stats}"
    )
    assert stats["directory_budget"] == 20
    assert stats["files_seen"] < len(on_disk), (
        f"{len(on_disk)} files exist and the walk offered {stats['files_seen']} - "
        f"that is the loss this gate is about ({stats})"
    )
    assert stats["truncated"] is True, (
        "the file budget was nowhere near: indexed is far below file_limit, so a "
        "flag derived from the record count calls this complete while it is empty"
        f" ({stats})"
    )
    hits = LocalEvidenceIndex(ws, max_directories=20).search("deep_marker_0_zzz", limit=5)
    assert hits == [], (
        "sanity: the target really is invisible to this walk, so the metric over "
        "it is measuring a tree that does not exist"
    )


def test_a_candidate_that_vanished_before_indexing_is_still_counted(tmp_path: Path) -> None:
    """The second ``except OSError`` in ``_refresh``, separately witnessed.

    Both drop channels sit in the same loop and a census that only counts one of
    them reconciles for exactly half the ways a file can go missing.
    """
    ws = _tree(tmp_path, 6)
    with vanishing("f00001.py"):
        stats = LocalEvidenceIndex(ws, max_files=100).stats()
    assert stats["files_seen"] == 6, stats
    assert stats["files_skipped"] == 1, (
        f"a candidate that disappeared between collection and stat() was dropped "
        f"without being counted: {stats}"
    )
    assert stats["files_indexed"] + stats["files_skipped"] == stats["files_seen"], stats
    assert stats["truncated"] is False, "the walk did finish; this loss is the other channel"
    assert census_is_complete(stats) is False, stats


def test_a_walk_that_finished_but_could_not_read_a_file_is_still_incomplete(
    tmp_path: Path,
) -> None:
    """Isolates the second way the denominator can be short.

    The case above reaches the file budget too, so without this one the
    ``files_skipped`` half of ``census_is_complete`` has no witness: deleting it
    reddens nothing else in the suite (measured - it was the mutation that found
    this gap).
    """
    ws = _tree(tmp_path, 12)
    with unreadable("f00003.py"):
        stats = LocalEvidenceIndex(ws, max_files=100).stats()
    assert stats["truncated"] is False, (
        "sanity: the budget was nowhere near, so this case is about a dropped "
        f"candidate and nothing else ({stats})"
    )
    assert stats["files_skipped"] == 1, stats
    assert stats["files_seen"] == stats["files_indexed"] + 1 == len(_text_files(ws)), stats
    assert census_is_complete(stats) is False, (
        "an exhausted walk that could not read one candidate is still not a scan "
        f"of the whole tree ({stats})"
    )
    assert "不引入向量检索" not in benchmarks.retrieval_decision(0.9, index=stats)


# --- the retrieval report has to carry the census it scored ----------------


def test_evaluate_retrieval_publishes_the_index_it_scored(tmp_path: Path) -> None:
    ws = _tree(tmp_path / "healthy", 4)
    cases = [{"id": "h1", "query": "shard_0_zzz", "targets": ["f00000.py"]}]
    report = benchmarks.evaluate_retrieval(cases, workspace=ws)
    assert "index" in report, (
        f"the report carries {sorted(report)}; the metric's denominator is not one "
        "of them, so a reader cannot tell 'recall dropped' from 'the walk stopped'"
    )
    published = report["index"]
    assert CENSUS_KEYS <= set(published), f"published census is missing {CENSUS_KEYS - set(published)}"
    direct = LocalEvidenceIndex(ws).stats()
    assert {k: published[k] for k in CENSUS_KEYS if k in published} == {
        k: direct[k] for k in CENSUS_KEYS if k in direct
    }, (
        "the census in the report must be the one that produced the metric, not a "
        f"second index built afterwards ({published} vs {direct})"
    )
    assert census_is_complete(published) is True


def test_a_truncated_walk_is_not_reported_as_a_recall_failure(tmp_path: Path) -> None:
    ws = _tree(tmp_path / "big", 30)
    cases = [
        {"id": "b1", "query": "unique_marker_for_zz_target", "targets": ["zz_target.py"]}
    ]
    report = benchmarks.evaluate_retrieval(cases, workspace=ws, max_files=10)
    recall5 = report["metrics"]["recall@5"]
    assert recall5 == 0.0, (
        f"precondition: the target is past the cut, so the raw metric does look "
        f"like a retrieval failure ({report['metrics']})"
    )
    assert census_is_complete(report["index"]) is False, (
        "the walk stopped at 10 of 30 candidates and did not say so: "
        f"{report['index']}"
    )
    decision = benchmarks.retrieval_decision(recall5, index=report["index"])
    assert "embedding" not in decision, (
        f"a file budget must not recommend building an embedding stack: {decision}"
    )
    assert "不引入向量检索" not in decision, (
        f"nor may it certify the baseline as passing: {decision}"
    )
    assert "截断" in decision or "不完整" in decision, (
        f"the conclusion has to name the actual cause: {decision}"
    )
    for token in ("files_indexed", "file_limit"):
        assert token in decision, f"the conclusion must carry the denominator ({token}): {decision}"


def test_the_floor_conclusion_needs_the_census_that_scored_it(tmp_path: Path) -> None:
    """Both directions come from a real walk, not from a dict this file wrote.

    ``index=None`` also refuses to certify: a caller that did not look at the
    denominator has an unknown denominator, and "unknown" must not fall through
    to the confident branch.
    """
    complete = LocalEvidenceIndex(_tree(tmp_path / "ok", 3)).stats()
    cut = LocalEvidenceIndex(_tree(tmp_path / "cut", 5, dirs=40), max_directories=20).stats()
    assert census_is_complete(complete) is True and census_is_complete(cut) is False
    assert "不引入向量检索" in benchmarks.retrieval_decision(0.9, index=complete), (
        f"a complete census must still be able to conclude: {complete}"
    )
    assert "不引入向量检索" not in benchmarks.retrieval_decision(0.9, index=cut), (
        f"a truncated walk must not certify the baseline: {cut}"
    )
    assert "不引入向量检索" not in benchmarks.retrieval_decision(0.9, index=None), (
        "an unknown denominator must not fall through to the confident branch"
    )
    assert "不引入向量检索" not in benchmarks.retrieval_decision(0.9), (
        "an omitted census argument is an unknown denominator too"
    )
    assert "embedding" not in benchmarks.retrieval_decision(0.0, index=cut)
    # No cases is still the first branch: a census cannot rescue a missing metric.
    assert "无法判定" in benchmarks.retrieval_decision(None, index=complete)
    assert census_is_complete({}) is False, "a report with no census is not a complete one"


# --- the CLI writes the same thing the code knows --------------------------


def test_cli_report_and_markdown_carry_the_census(tmp_path: Path) -> None:
    ws = _tree(tmp_path / "cli", 30)
    dataset = tmp_path / "ds.json"
    dataset.write_text(
        json.dumps({
            "workspace": str(ws), "ks": [1, 5], "max_files": 10,
            "cases": [{"id": "b1", "query": "unique_marker_for_zz_target",
                       "targets": ["zz_target.py"]}],
        }),
        encoding="utf-8",
    )
    json_out, md_out = tmp_path / "r.json", tmp_path / "r.md"
    code = benchmarks.main([
        "--suite", "retrieval", "--fixtures", str(dataset),
        "--json-out", str(json_out), "--markdown-out", str(md_out),
    ])
    assert code == 0, "an uninterpretable baseline is a finding, not a crash"
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert "index" in payload, f"json report keys: {sorted(payload)}"
    assert payload["index"]["truncated"] is True
    # The conclusion has to quote the numbers it is refusing on.  Checking only
    # for the absence of "embedding" would pass vacuously: the unknown-census
    # branch of `retrieval_decision` never mentions embeddings either, so this is
    # what witnesses that the CLI really handed the census over.
    assert "embedding" not in payload["decision"], (
        f"the CLI read a truncated walk as a recall failure: {payload['decision']}"
    )
    assert "file_limit=10" in payload["decision"], (
        "the conclusion does not quote the budget it is refusing on, so the CLI "
        f"may have passed no census at all: {payload['decision']}"
    )
    md = md_out.read_text(encoding="utf-8")
    lines = [line for line in md.splitlines() if line.startswith("Index census:")]
    assert len(lines) == 1, (
        "the markdown is what gets quoted into the roadmap; it needs exactly one "
        f"census line of its own (found {len(lines)}) - the conclusion paragraph "
        f"mentions the same keys, so a substring check on the whole file cannot "
        f"tell them apart\n{md}"
    )
    census_line = lines[0]
    for token in ("files_indexed=10", "file_limit=10", "truncated=True", "口径完整=False"):
        assert token in census_line, f"{token!r} missing from the census line: {census_line}"
    assert "截断" in md or "不完整" in md, f"the markdown conclusion must name the cause:\n{md}"


# --- the committed repo baseline stays interpretable -----------------------


def test_the_repo_self_scan_is_not_truncated() -> None:
    """The floor test in test_retrieval_eval.py is only meaningful while this holds.

    Measured on this repo: 230 text files against a 1200 budget, so the file
    budget is not close.  The directory budget is the one that can move - it is
    ``max(4000, max_files * 4)`` and this tree has ~90 directories - and a build
    that leaves temp trees inside the workspace walks straight into it.
    """
    ws = Path(benchmarks.REPO_ROOT).resolve()
    stats = LocalEvidenceIndex(ws).stats()
    assert CENSUS_KEYS <= set(stats), f"no census to check: {sorted(stats)}"
    assert census_is_complete(stats) is True, (
        f"the repo's own retrieval baseline is no longer over the whole tree: {stats}"
    )
    assert stats["files_skipped"] == 0, f"unreadable candidates changed the denominator: {stats}"
    assert stats["files_indexed"] >= 150, (
        f"only {stats['files_indexed']} files indexed from the repo - if the tree "
        "moved or the filters changed, the floor test is green because it scanned "
        f"almost nothing ({stats})"
    )
    used = stats["files_indexed"] / stats["file_limit"]
    assert used < 0.8, (
        f"the file budget is {used:.0%} consumed; the next temp tree inside the "
        f"workspace will truncate the self-scan and every metric under it ({stats})"
    )
    dirs_used = stats["directories_walked"] / stats["directory_budget"]
    assert dirs_used < 0.5, (
        f"the directory budget is {dirs_used:.0%} consumed ({stats}); a walk that "
        "stops on it indexes a prefix silently"
    )


def test_the_gate_is_reachable(tmp_path: Path) -> None:
    """Without this, an import that stopped matching would make the file green."""
    assert callable(census_is_complete)
    ws = _tree(tmp_path, 2)
    params = inspect.signature(LocalEvidenceIndex.__init__).parameters
    assert "max_directories" in params, (
        "the directory budget is unreachable without this, and a walk that only "
        "truncates at 4000 directories cannot be tested here"
    )
    assert params["max_directories"].default is None, (
        "None has to mean 'derive it from the file budget', or the seam changes "
        "what production does by default"
    )
    default = LocalEvidenceIndex(ws)
    assert default.max_directories == max(4_000, default.max_files * 4), (
        f"the documented default formula no longer matches: {default.max_directories}"
    )
    assert LocalEvidenceIndex(ws).stats()["truncated"] is False
