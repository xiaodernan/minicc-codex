"""M8-T533 — one deny question per refresh, not one per candidate file.

M8-T351 taught the evidence index to ask ``permissions.json`` about every
candidate.  It asked through ``audit.tool_denied_by_rule``, which loads the
policy twice per call (once to see whether it is readable, once to match),
and ``load_permission_rules`` stats the rules file on every load.  The result
was two stats of ``.minicc/permissions.json`` **per indexed file** - the call
counter gate caught it at 7.208 calls per file, over its 7.0 ceiling.

The index now loads the policy once per refresh and keeps asking the matcher.
The question has to stay asked (a workspace with no rules file still consults
the path), and its cost has to stop growing with the number of files: that
constancy is what this gate measures, at two sizes.
"""

from __future__ import annotations

from pathlib import Path

from minicc.agent.retrieval import LocalEvidenceIndex

RULES_NAME = "permissions.json"


def _permission_stats(root: Path) -> tuple[int, int]:
    """Build an index over ``root``; return (rules-file stats, files indexed)."""
    seen = {"stat": 0}
    original = Path.stat

    def counted(self, *args, **kwargs):
        if self.name == RULES_NAME:
            seen["stat"] += 1
        return original(self, *args, **kwargs)

    Path.stat = counted  # type: ignore[method-assign]
    try:
        index = LocalEvidenceIndex(root, max_files=1500, refresh_interval=0.0)
        indexed = int(index.stats()["files_indexed"])
    finally:
        Path.stat = original  # type: ignore[method-assign]
        assert Path.stat is original, "the counter leaked a patch"
    return seen["stat"], indexed


def _tree(root: Path, files: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for number in range(files):
        (root / f"m{number}.py").write_text("x = 1\n", encoding="utf-8")


def test_the_deny_question_does_not_grow_with_the_file_count(tmp_path: Path) -> None:
    small = tmp_path / "small"
    big = tmp_path / "big"
    _tree(small, 5)
    _tree(big, 50)

    small_stats, small_files = _permission_stats(small)
    big_stats, big_files = _permission_stats(big)

    assert (small_files, big_files) == (5, 50), (small_files, big_files)
    assert small_stats >= 1, "the rules file was never consulted (vacuous gate)"
    assert big_stats == small_stats, (
        f"the deny question is asked per file: {small_stats} stats for "
        f"{small_files} files, {big_stats} for {big_files}"
    )