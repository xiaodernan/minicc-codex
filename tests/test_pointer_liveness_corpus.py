"""M8-T84: the pointer checker's exemption-liveness verdict must not depend on which documents you ask it to print.

Two failure modes, both measured on the plane before this batch (commit ``46ed854``,
19 corpus documents, 245 tracked files):

  * ``python scripts/doc_pointers.py --check <one absolute document>`` exited 1 and
    printed 1–14 rows of 「豁免 … 是陈旧登记 / 是死行」 for exemption keys that the
    whole-corpus run — rc=0, zero rows — says are alive. The liveness question was
    being answered against whatever subset the caller happened to pass, so checking
    one document invented dead policy in the other eighteen.
  * the same command with a *relative* document (the form a human types from the
    repo root) exited 1 without printing any findings at all: ``check_document``
    mapped the document back onto ``REPO_ROOT`` with an unguarded ``relative_to``,
    and a relative path is not a subpath of an absolute root, so a ``ValueError``
    escaped. An exit code that means 「the report could not run」 arriving dressed
    as 「dangling references found」 is the exact failure ``ensure_utf8_output`` was
    written to prevent.

Both are the same root: the caller's argument list was used for two different jobs
— *which documents to print* and *what population an exemption is matched against*
— and was never normalised. The fix keeps the predicate ``check_exempt_tables``
honest to its own contract (scan exactly the documents you are handed, which is
what lets ``tests/test_doc_pointers.py`` plant a fake corpus) and does the
widening in ``main``, naming the corpus in the report so a reader can see which
population a clean run was clean over.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "doc_pointers.py"
README = REPO_ROOT / "README.md"
ROADMAP = REPO_ROOT / "docs" / "ROADMAP_TO_PRODUCT.md"
PLUGIN_API = REPO_ROOT / "docs" / "PLUGIN_API.md"

_CORPUS_SIZE = re.compile(r"exemption liveness answered against (\d+) corpus documents")
_SUBSET_SIZE = re.compile(r"in (\d+) documents")


def _load(name: str):
    """A fresh copy of the checker.

    Reloading rather than mutating the shared module is the idiom
    ``tests/test_doc_pointers.py`` already uses: the tool memoises its git-derived
    sets, and clearing them by hand lets a gate go red for reasons of test hygiene
    instead of reasons of code. One gate here needs a *different* shipped corpus,
    and that has to be a module whose ``DEFAULT_DOCS`` can be narrowed without
    taking the other gates' readings with it.
    """
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dp = _load("minicc_doc_pointers_liveness")


def _run(module, argv: list[str], capsys) -> tuple[int, list[str], str]:
    """Invoke the checker the way its own ``main`` is invoked, and split its report."""
    rc = module.main(argv)
    out = capsys.readouterr().out
    return rc, [line for line in out.splitlines() if line.startswith("DANGLING")], out


def _footer(out: str) -> str:
    lines = [line for line in out.splitlines() if "tracked files" in line]
    assert len(lines) == 1, f"报告没有留下唯一一行总数：{lines}"
    return lines[0]


def test_a_subset_check_does_not_invent_dead_exemptions(capsys) -> None:
    """The whole point of the batch: a one-document report must say what the corpus says.

    Before this batch the corpus run reported nothing while *every* single-document
    run reported 1–14 dead exemption rows. A reviewer who then deleted the 「stale」
    entries the tool had just named would have removed live policy — which is why
    this gate loops the whole population instead of picking the worst offender.
    """
    rc_all, rows_all, out_all = _run(dp, ["--check", "--quiet", *[str(p) for p in dp.DEFAULT_DOCS]], capsys)
    assert rc_all == 0, f"整个语料本来是干净的，这一轮先红了：{rows_all}"
    assert _SUBSET_SIZE.search(_footer(out_all)).group(1) == str(len(dp.DEFAULT_DOCS))

    offenders = []
    for document in dp.DEFAULT_DOCS:
        rc, rows, _ = _run(dp, ["--check", "--quiet", str(document)], capsys)
        if rc != 0 or rows:
            offenders.append(f"{document.name}: rc={rc} {rows[:2]}")
    assert offenders == [], (
        "单文档 --check 报出了整个语料没有的死行（豁免的生命力被按调用方递进来的子集回答了；"
        f"{len(dp.DEFAULT_DOCS)} 份文档里这些子集仍然报错）：{offenders}"
    )


def test_a_relative_document_is_checked_instead_of_crashing(capsys, monkeypatch) -> None:
    """The form a person actually types from the repo root must produce a report.

    This is not the same assertion as the one above: the absolute-path subset
    produced *wrong findings*, the relative one produced *no findings and a
    traceback*, and only the second pretends to be a clean exit code while
    checking nothing.
    """
    monkeypatch.chdir(REPO_ROOT)
    offenders = []
    for document in dp.DEFAULT_DOCS:
        relative = document.relative_to(REPO_ROOT).as_posix()
        rc, rows, out = _run(dp, ["--check", "--quiet", relative], capsys)
        footer = _SUBSET_SIZE.search(_footer(out))
        if rc != 0 or rows or footer is None or footer.group(1) != "1":
            offenders.append(f"{relative}: rc={rc} rows={rows[:2]} footer={footer and footer.group(0)}")
    assert offenders == [], (
        f"相对路径的子集检查没有交出一份「我查过了」的报告（本批之前它是 ValueError + exit 1，"
        f"stdout 一行结果都没有）：{offenders}"
    )


def test_the_report_names_the_population_its_verdict_came_from(capsys, tmp_path, monkeypatch) -> None:
    """A clean subset run has to be readable as clean-over-N, not clean-over-1.

    The numbers come from the same union the checker builds, so this gate pins the
    footer to the rule rather than to a hand-copied 19 — the mistake M8-T38's own
    record was written to stop.
    """
    one = _run(dp, ["--check", "--quiet", str(README)], capsys)
    expect_one = len(dict.fromkeys([*dp.DEFAULT_DOCS, README]))
    assert _CORPUS_SIZE.search(_footer(one[2])).group(1) == str(expect_one)
    assert expect_one > 1, "语料只有 1 份文档的话，这条门什么也没钉住"

    pair = _run(dp, ["--check", "--quiet", str(README), str(PLUGIN_API)], capsys)
    expect_pair = len(dict.fromkeys([*dp.DEFAULT_DOCS, README, PLUGIN_API]))
    assert _CORPUS_SIZE.search(_footer(pair[2])).group(1) == str(expect_pair)
    assert expect_pair == expect_one, "README 与 PLUGIN_API 都已经在语料里，分母不该动"

    alien = tmp_path / "ALIEN.md"
    alien.write_text("# 仓库外的文档\n\n它没有指向本仓库任何路径。\n", encoding="utf-8")
    extra = _run(dp, ["--check", "--quiet", str(alien)], capsys)
    assert _CORPUS_SIZE.search(_footer(extra[2])).group(1) == str(expect_one + 1), (
        "调用方另递的文档没有进语料分母：它带来的引用也就不会被算成引用"
    )
    assert extra[0] == 0 and extra[1] == [], f"仓库外的一份文档应当被检查而不是把报告打死：{extra[1]}"

    # The same file handed over under two spellings must still be one file. This is
    # the only observable that catches a missing ``resolve()`` — the guard added for
    # the crash below quietly makes a relative path *runnable*, so nothing else here
    # would notice that the corpus now counts the roadmap twice (measured: 19 becomes
    # 20 while no new document was added).
    monkeypatch.chdir(REPO_ROOT)
    relative = _run(dp, ["--check", "--quiet", README.relative_to(REPO_ROOT).as_posix()], capsys)
    assert _CORPUS_SIZE.search(_footer(relative[2])).group(1) == str(expect_one), (
        f"相对路径的 README 被当成第二份文档收进语料了（分母从 {expect_one} 涨到 "
        f"{_CORPUS_SIZE.search(_footer(relative[2])).group(1)}）：{_footer(relative[2])}"
    )


def test_a_genuinely_dead_exemption_is_still_declared_dead_under_a_subset_check(capsys) -> None:
    """Reverse control: widening the corpus must not widen the verdict into silence.

    Without this gate, ``problems.extend(check_exempt_tables(liveness_corpus))``
    could be replaced by nothing at all and every gate above would stay green.
    """
    key = "zzz_t84_planted_uncited_file.js"
    plain = dp._NOT_A_REPO_PATH
    planted = dict(plain)
    planted[key] = "本轮植入：量「放宽语料」有没有把检查本身放宽成无话可说"
    original = dp._EVIDENCE_TABLES
    argv = ["--check", "--quiet", str(README), str(ROADMAP)]
    dp._EVIDENCE_TABLES = tuple(planted if t is plain else t for t in original)
    try:
        rc, rows, _ = _run(dp, argv, capsys)
    finally:
        dp._EVIDENCE_TABLES = original
    named = [line for line in rows if key in line]
    assert rc == 1 and len(named) == 1 and "已无任何文档引用" in named[0], (
        f"植入一条谁都不引用的豁免，子集检查却不再点它：rc={rc} rows={rows}"
    )
    assert dp._EVIDENCE_TABLES == original, "表格恢复失败，后面的门会读到植入的键"
    rc_clean, rows_clean, _ = _run(dp, argv, capsys)
    assert rc_clean == 0 and rows_clean == [], f"撤掉植入之后同一组子集仍然红：{rows_clean}"


def test_a_shipped_document_counts_even_when_the_caller_hands_over_another_one(capsys) -> None:
    """The union has two halves, and only one of them is 「whatever the caller passed」.

    The shipped corpus is narrowed to README plus the roadmap on a private copy of
    the tool, and the caller is given README alone. Ten of the fourteen exemption
    keys are reachable only through the roadmap — measured here, README's citations
    are a subset of the roadmap's, and ``docs/PLUGIN_API.md`` revives none of them —
    so under the pre-batch behaviour (answer against ``args.documents``) all ten get
    reported dead, while under the corpus-wide answer exactly one key stays reported.
    """
    module = _load("minicc_doc_pointers_narrowed")
    module.DEFAULT_DOCS = (README, ROADMAP)
    usage_called = module.exemption_usage([README])
    usage_corpus = module.exemption_usage([README, ROADMAP])
    uncited_here = sorted(key for key, hits in usage_called.items() if hits == 0)
    carried_by_corpus = sorted(key for key in uncited_here if usage_corpus[key] > 0)
    assert carried_by_corpus, "没有一条豁免是靠调用方没递的那份文档站住的，这条门钉不住并集"

    rc, rows, out = _run(module, ["--check", "--quiet", str(README)], capsys)
    assert _CORPUS_SIZE.search(_footer(out)).group(1) == "2", (
        f"收窄后的语料没有生效，这一轮读的还是磁盘上的 19 份：{_footer(out)}"
    )
    wrongly_dead = [key for key in carried_by_corpus if any(key in line for line in rows)]
    assert wrongly_dead == [], (
        f"调用方只递了 README，可 ROADMAP 就在语料里；这些豁免靠它站着，死行名单却点名它们："
        f"{wrongly_dead}"
    )
    # And the checker is not merely quiet: one key really is unreachable from both
    # corpus documents, and it must still be named. Either complaint counts — a key
    # nobody mentions in prose is 陈旧登记, a mentioned-but-unreachable one is 死行,
    # and the tool stops at the first kind.
    still_dead = sorted(key for key in uncited_here if any(key in line for line in rows))
    assert still_dead, f"rc={rc}，语料里明明有一条谁都引用不到的豁免，名单却空了：{_footer(out)}"
    assert len(carried_by_corpus) + len(still_dead) == len(uncited_here), (
        f"靠语料复活的 {len(carried_by_corpus)} 条与仍死的 {len(still_dead)} 条对不上 README "
        f"单独递给谓词时的 {len(uncited_here)} 条无人引用豁免"
    )


def test_a_relative_document_still_gets_the_floors_registered_for_its_repo_path(capsys, monkeypatch) -> None:
    """Floors index by the repo-relative name, so that name has to be derived, not assumed.

    ``MIN_POINTERS``, ``MIN_LINKS`` and ``MIN_EVIDENCE`` are all keyed by
    ``docs/ROADMAP_TO_PRODUCT.md``. If the caller's spelling reaches the checker
    unresolved, the lookup misses and the floor meant to catch a blind reader stops
    applying to the largest document in the repository — no crash, no finding, just
    a rule that quietly no longer runs. This is the observable that catches a missing
    ``resolve()`` after ``check_document`` learned to tolerate alien paths.
    """
    _, stats = dp.check_document(ROADMAP)
    monkeypatch.setitem(dp.MIN_POINTERS, "docs/ROADMAP_TO_PRODUCT.md", stats.pointers + 1)
    monkeypatch.chdir(REPO_ROOT)
    rc, rows, _ = _run(dp, ["--check", "--quiet", "docs/ROADMAP_TO_PRODUCT.md"], capsys)
    fired = [line for line in rows if "INVENTORY" in line and "docs/ROADMAP_TO_PRODUCT.md" in line]
    assert rc == 1 and len(fired) == 1, (
        f"相对路径递给检查器时，登记在仓库相对名上的指针地板没有生效：rc={rc} rows={rows[:3]}"
    )


def test_the_liveness_predicate_still_scans_exactly_what_it_is_given(capsys) -> None:
    """Keep the widening in ``main``: the helper must stay a pure function of its corpus.

    ``tests/test_doc_pointers.py`` measures a planted key against a fake corpus it
    assembles itself. If the union moved into ``check_exempt_tables`` those controls
    would silently be answered against the real shipped documents — a green tick on
    a rule nobody checked.
    """
    whole = dp.check_exempt_tables(list(dp.DEFAULT_DOCS))
    assert whole == [], f"整个语料应当没有陈旧豁免，这一轮先红了：{[p.detail for p in whole]}"
    thin = {document.name: len(dp.check_exempt_tables([document])) for document in dp.DEFAULT_DOCS}
    assert all(count > 0 for count in thin.values()), (
        f"某份文档单独递给谓词时它竟然什么也没判（并集被挪进了谓词？）：{thin}"
    )


def test_the_documented_command_still_passes_with_a_relative_document() -> None:
    """The CLI surface, not just the Python surface.

    ``docs/`` and CI both invoke the script as a command; the crash this batch
    removed was a command-line one, so one of these gates has to run it that way.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--quiet", "docs/PLUGIN_API.md"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"rc={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr[-400:]}"
    )
    assert "DANGLING" not in result.stdout and "Traceback" not in result.stderr
    assert _CORPUS_SIZE.search(result.stdout) is not None, result.stdout
