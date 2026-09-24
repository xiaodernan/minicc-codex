"""Gates for the checker that resolves cross-references in the project's markdown.

The defect this guards is one this repository shipped and then re-shipped:
M8-T34's roadmap row pointed at 「第十八批 M8-T34」, a subsection that does not
exist — the 第十八批 section records M8's exit criteria and never mentions
M8-T34. M8-T35 rewrote that row to explain the mistake, and the new sentence
ended with the *same* broken pointer. Two humans-in-a-row (the same author twice)
reading their own text did not see it; only a second reader that resolves every
pointer mechanically will.

Precision is the hard part, not coverage: ``见`` is a Chinese suffix in 可见,
意见, 预见, 见证, 见收益, so harvesting on the marker alone produced 48 "distinct
pointers" of which almost none were pointers. The rule these tests hold is that
a span counts only when it names a locator (``第N批`` / ``第N节`` / ``附录 X``)
or an id (``M8-T34``, ``M4-3``, ``P0-1``), and a locator plus an id is a claim
about *where* the id lives — the exact claim that was wrong.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "doc_pointers.py"


def _load(name: str = "minicc_doc_pointers"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; @dataclass(slots=True) resolves annotations via
    # sys.modules, so register the module before executing it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dp = _load()


def _pointed_at(root: Path, name: str):
    """A fresh copy of the tool aimed at another repository root.

    Reloading rather than mutating ``dp`` is deliberate: the tool memoises five
    git-derived sets, and clearing them by hand is a way for a gate to go red for
    reasons of test hygiene instead of reasons of code.
    """
    module = _load(name)
    module.REPO_ROOT = root
    return module


_COUNTER = iter(range(1, 1000))


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "core.hooksPath=no-such-hook-dir",
            "-c",
            "user.name=gate",
            "-c",
            "user.email=gate@example.test",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stdout}{proc.stderr}"
    return proc.stdout


def _scratch_repo(tmp_path: Path, doc: str):
    """A committed repository holding ``doc``, returned as (tool, document path).

    A real git repository is the only honest fixture here: the thing under test
    is "what would a fresh clone see", and that question has no answer that does
    not involve an index.
    """
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "minicc").mkdir()
    (root / "output").mkdir()
    (root / ".gitignore").write_text("output/\n.minicc/\n", encoding="utf-8")
    (root / "README.md").write_text("# scratch\n", encoding="utf-8")
    (root / "minicc" / "app.py").write_text("import json\n\nprint(json)\n", encoding="utf-8")
    (root / "docs" / "NOTES.md").write_text(doc, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")
    return _pointed_at(root, f"minicc_doc_pointers_scratch_{next(_COUNTER)}"), root / "docs" / "NOTES.md"

#: A document that contains one correct pointer of every supported shape, plus
#: prose that must *not* be read as a pointer.
_GOOD_DOC = """\
# 测试文档

## 一、第一节

可见、意见、预见、见证、见收益，还有「口径见下方注记」——这些都不是指针。

## 三、第三节

### M4 记录（第二批，2026-09-22）

| M4-3 `POST /api/*` 覆盖 | ✅ | 细节 |

详见「第三节」，也见「第二批 M4-3 行」，附录 A 里另有清单。

## 附录 A：清单
"""

#: The shipped defect, in miniature: a section that exists, an id that exists,
#: and a pointer claiming the id lives in the section when it does not.
_BAD_DOC = """\
# 测试文档

## 四、明确不做什么

| M8-T34 探针 | ✅ | 结论 |

### M8 退出标准真跑记录（第十八批，2026-09-23）

三条全绿。见下方「第十八批 M8-T34」。
"""


def _pointer_problems(text: str) -> list[str]:
    problems, checked, boxes = dp.check_pointers(Path("synthetic.md"), text)
    assert checked or sum(boxes.values())
    return [f"{p.detail}" for p in problems]


def test_prose_that_merely_ends_with_the_marker_is_not_harvested() -> None:
    problems, checked, boxes = dp.check_pointers(Path("synthetic.md"), _GOOD_DOC)
    assert problems == []
    # The fixture is the box table in miniature. Measured, not assumed: the five
    # suffixes on one line collapse into *one* harvested span, because 、 does not
    # terminate a span the way ，。 do — so 「word-interior」 counts marker runs, not
    # occurrences of the character. Writing ``== 5`` here would have been an
    # expectation about the character rather than about this extractor.
    assert boxes[dp.BOX_WORD] == 1
    assert boxes[dp.BOX_NO_LOCATOR] == 1
    assert boxes[dp.BOX_CHECKED] == 2 == checked
    # Counted, not silently dropped: 「口径见下方注记」 is a gap in what is guarded.
    assert sum(boxes.values()) == len(dp._pointer_spans(_GOOD_DOC)) == 4


def test_locator_plus_id_is_a_claim_about_where_the_id_lives() -> None:
    # Positive control: same ids, but the id really is inside the named section.
    assert _pointer_problems(_GOOD_DOC) == []
    problems = _pointer_problems(_BAD_DOC)
    assert len(problems) == 1, problems
    assert "M8-T34" in problems[0]
    assert "第十八批" in problems[0]


def test_pointer_to_a_batch_that_never_existed_is_reported() -> None:
    text = "# T\n\n### 记录（第七批）\n\n内容。见「第九十九批」。\n"
    problems = _pointer_problems(text)
    assert len(problems) == 1
    assert "第九十九批" in problems[0]


def test_a_suffix_that_keeps_growing_still_resolves() -> None:
    text = "# T\n\n### 记录（第十五批续二）\n\nM8-T31 结论。见「第十五批续二」的 M8-T31。\n"
    assert _pointer_problems(text) == []
    # 续 must not be satisfied by the longer 续二 section it prefixes.
    text_missing = "# T\n\n### 记录（第十五批续二）\n\n内容。见「第十五批续」。\n"
    assert len(_pointer_problems(text_missing)) == 1


def test_numbered_section_pointers_use_the_heading_numeral_not_the_words() -> None:
    text = "# T\n\n## 四、明确不做什么\n\n内容。见第四节。\n"
    assert _pointer_problems(text) == []
    assert len(_pointer_problems("# T\n\n## 四、内容\n\n见第十一节。\n")) == 1


def test_appendix_pointers_resolve_by_letter() -> None:
    assert _pointer_problems("# T\n\n## 附录 B：注记\n\n见附录 B。\n") == []
    assert len(_pointer_problems("# T\n\n## 附录 B：注记\n\n见附录 E。\n")) == 1


def test_a_bare_id_pointer_only_has_to_exist_somewhere_in_the_doc() -> None:
    assert _pointer_problems("# T\n\n## 一、x\n\n见 M8-T16 行。\n| M8-T16 429 | ✅ | 结论 |\n") == []
    assert len(_pointer_problems("# T\n\n## 一、x\n\n见 M8-T999 行。\n")) == 1


def test_relative_links_must_resolve_and_urls_are_left_alone(tmp_path: Path) -> None:
    (tmp_path / "real.md").write_text("# real\n", encoding="utf-8")
    text = (
        "[ok](real.md)\n[missing](nope.md)\n[ext](https://example.test/x)\n[frag](#anchor)\n"
    )
    problems, checked, generated = dp.check_links(tmp_path / "doc.md", text)
    assert checked == 2 and generated == 0, "the URL and the in-page fragment are not this tool's business"
    assert len(problems) == 1 and "nope.md" in problems[0].detail
    # Outside a work tree there is no index to consult, so a synthetic document in
    # a temp directory is judged by existence — the one case that has to keep
    # working for every other gate in this file to be writable.

    inside = dp.check_links(
        REPO_ROOT / "docs" / "doc.md",
        "[tracked](ROADMAP_TO_PRODUCT.md)\n"
        "[generated](../output/playwright/never-generated-here.png)\n"
        "[gone](nope-again-this-time.md)\n",
    )
    problems, checked, generated = inside
    assert checked == 3, "a generated target is still a target the reader looked at"
    assert generated == 1
    assert [p.detail for p in problems] == ["链接目标 nope-again-this-time.md 不存在"], problems
    # The ignored artifact is red neither way: it is the class that made
    # ``--check`` pass on the machine that ran the build and fail in a clone.


def test_cross_document_section_pointer_needs_the_file_named(tmp_path: Path) -> None:
    # 第十二节 does exist in docs/AUDIT_2026-09-20.md; naming the file is what
    # makes such a pointer checkable at all, and the gate holds that line.
    named = "复核命令见 [docs/AUDIT_2026-09-20.md](docs/AUDIT_2026-09-20.md) 第十二节。\n"
    assert _pointer_problems(named) == []
    vague = "复核命令见审核文档第十二节。\n"
    assert len(_pointer_problems(vague)) == 1


def test_floors_fire_when_the_extractor_goes_blind(monkeypatch) -> None:
    document = REPO_ROOT / "docs" / "ROADMAP_TO_PRODUCT.md"
    _, stats = dp.check_document(document)
    assert stats.pointers >= 15
    monkeypatch.setitem(dp.MIN_POINTERS, "docs/ROADMAP_TO_PRODUCT.md", stats.pointers + 1)
    problems, _ = dp.check_document(document)
    assert [p.kind for p in problems] == ["INVENTORY"]
    assert str(stats.pointers) in problems[0].detail


def test_shipped_documents_have_no_dangling_references() -> None:
    problems: list[dp.Problem] = []
    totals = {"pointers": 0, "links": 0}
    for document in dp.DEFAULT_DOCS:
        found, stats = dp.check_document(document)
        problems.extend(found)
        totals["pointers"] += stats.pointers
        totals["links"] += stats.links
    assert problems == []
    # Anti-vacuity: a clean run over an empty inventory would prove nothing.
    assert totals["pointers"] >= 25
    assert totals["links"] >= 15


def test_documented_command_runs_end_to_end() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--quiet"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DANGLING" not in result.stdout
    assert "pointers" in result.stdout


def test_a_pointer_written_inside_a_code_span_is_a_quotation_not_a_claim() -> None:
    """README illustrates the defect by quoting it; quoting must not be checked.

    Without the masking step this gate is red for the wrong reason — and the
    first version of the tool was, which is how the rule got written down. The
    cost of the rule is honest and recorded: a genuinely dangling pointer that
    someone wrote inside a code span is invisible here, exactly like a prefix
    dispatch is invisible to a ``path ==`` scan.
    """
    quoted = "# T\n\n缺陷长这样：`见「第十八批 M8-T34」`。\n"
    problems, checked, boxes = dp.check_pointers(Path("synthetic.md"), quoted)
    assert problems == [] and checked == 0
    # Masking blanks the whole span, marker included, so the quotation is never
    # harvested at all — it is not an unresolved marker, it is absent. My first
    # version of this gate asserted ``unresolved == 1`` and was wrong: the tool
    # was already right, and an expectation written from what I wanted the tool
    # to do is the same mistake as a self-satisfying id check.
    assert sum(boxes.values()) == 0

    prose = "# T\n\n结论见「第十八批 M8-T34」。\n"
    prose_problems = dp.check_pointers(Path("synthetic.md"), prose)[0]
    # The unquoted same text is a claim, and a claim in a document with no such
    # section is two complaints: the batch paragraph does not exist, and the id
    # is not declared anywhere. Quoting it is what makes both disappear.
    assert len(prose_problems) == 2, prose_problems
    # Distinguish the two claims by what each one asserts, not by the span text:
    # every detail quotes the whole 「…」, so counting 「第十八批」 there says
    # nothing about which complaint fired.
    assert sum("指向不存在的段落" in p.detail for p in prose_problems) == 1
    assert sum("没有这个编号" in p.detail for p in prose_problems) == 1


# --------------------------------------------------------------------------- #
# M8-T37: the evidence reader — files, line numbers and test names cited inside
# inline code. Each gate below is written against a red the tool actually threw
# on the shipped docs, so none of them is a hypothetical.
# --------------------------------------------------------------------------- #

_ROADMAP = REPO_ROOT / "docs" / "ROADMAP_TO_PRODUCT.md"


def _evidence(*spans: str, claims: int | None = None) -> list[str]:
    """Run the reader over synthetic citations, the way roadmap writes them.

    ``claims`` is how many of the spans the reader should treat as location
    claims at all. Passing ``claims=0`` says "this shape must be *refused*, not
    merely tolerated" — without it, a reader that checked every backtick would
    satisfy an empty-problems assertion just as happily as one that knows its
    business.
    """
    text = "# T\n\n" + "\n".join(f"结论见 `{span}`。" for span in spans) + "\n"
    problems, checked = dp.check_evidence(_ROADMAP, text)
    expected = len(spans) if claims is None else claims
    assert checked == expected, list(zip(spans, [checked] * len(spans)))
    return [p.detail for p in problems]


def test_a_citation_to_a_moved_test_says_where_it_actually_lives() -> None:
    # Verbatim from roadmap M1-3's acceptance line: the test exists, just not in
    # that file and not without the m1t1_ prefix. "The file is real" is not a
    # reason to let a citation that lands nowhere stand.
    assert _evidence(
        "tests/test_p0_p1_p2.py::test_recovery_required_does_not_loop_on_plain_text"
    ) == [
        "tests/test_p0_p1_p2.py::test_recovery_required_does_not_loop_on_plain_text 没有这个测试："
        "它定义在 test_m1t1_recovery_required_does_not_loop_on_plain_text"
    ]
    assert _evidence(
        "tests/test_m1_integrity.py::test_m1t1_recovery_required_does_not_loop_on_plain_text"
    ) == []


def test_a_bare_test_name_may_be_a_module_or_a_function_but_nothing_else() -> None:
    # `test_grader_unreadable` is how roadmap:207 cited the gate; the real name
    # has a suffix, and test_core is a module, not a function — both accepted.
    assert _evidence("test_grader_unreadable")[0].startswith("test_grader_unreadable 既不是测试文件名")
    assert _evidence("test_grader_unreadable_by_file_tools", "test_core") == []


def test_an_abbreviation_is_a_claim_and_a_method_name_is_not() -> None:
    # The docs cite minicc's packages by their package-relative name, and web's
    # by theirs; both resolve. `tools/call` is an MCP method and `loop.py` alone
    # is a name, not a location — admitting either would flood the reader.
    assert _evidence("agent/loop.py", "core/scope.js", "llm/stream_merge.py") == []
    assert _evidence("agent/no_such_module.py") == ["agent/no_such_module.py 指向的路径在仓库里不存在"]
    # Refused, not merely silent: a shape the reader declines must never reach
    # the counter, or the inventory number is prose style rather than eyesight.
    assert _evidence("127.0.0.0/8", "--session-id/--resume", "tools/call", "loop.py", claims=0) == []


def test_a_line_number_is_checked_against_the_file_it_claims() -> None:
    assert _evidence("tests/test_doc_pointers.py:99999")[0].startswith(
        "tests/test_doc_pointers.py:99999 在第"
    )
    assert _evidence("tests/test_doc_pointers.py:1") == []
    # A dated snapshot records where the line was on its date; rewriting that
    # would falsify the record, so the line check is what steps down — not the
    # existence check, which still catches a path that never existed.
    audit = REPO_ROOT / "docs" / "AUDIT_2026-09-20.md"
    problems, checked = dp.check_evidence(audit, "# T\n\n`minicc/config.py:99999` `minicc/nope.py`\n")
    assert checked == 2 and [p.detail for p in problems] == ["minicc/nope.py 指向的路径在仓库里不存在"]


def test_an_attribute_citation_has_to_appear_in_that_file() -> None:
    assert _evidence("minicc/config.py.Config") == []
    assert _evidence("minicc/config.py.definitely_not_in_this_file") == [
        "minicc/config.py.definitely_not_in_this_file 说 minicc/config.py 里有 definitely_not_in_this_file，那里没有"
    ]


def test_every_exemption_pays_for_itself_with_a_reason_and_a_live_reference() -> None:
    for table in dp._EVIDENCE_TABLES:
        assert table, "an empty exemption table is not a fence"
    # Empty reason: a name in a set is how an exemption quietly outlives the
    # thing it excuses. Stale reference: the day the docs stop citing it, the
    # entry must go, or nobody can tell a granted exception from a dead one.
    documents = [d for d in dp.DEFAULT_DOCS if d.exists()]
    assert dp.check_exempt_tables(documents) == []
    key = "web/never_mentioned_anywhere.js"
    original = dp._RETIRED_PATH
    monkey = dict(original)
    monkey[key] = ""
    dp._EVIDENCE_TABLES = tuple(monkey if t is original else t for t in dp._EVIDENCE_TABLES)
    try:
        problems = dp.check_exempt_tables(documents)
    finally:
        dp._EVIDENCE_TABLES = tuple(original if t is monkey else t for t in dp._EVIDENCE_TABLES)
    # Both complaints fire, from two independent checks: the entry has no reason,
    # and no document cites it any more. My first version asserted one problem and
    # was wrong — a fake key earns both, and only asserting the pair keeps the two
    # rules from being quietly collapsed into one.
    assert {p.detail for p in problems} == {
        f"豁免 {key} 没有理由",
        f"豁免 {key} 已无任何文档引用，是陈旧登记",
    }, problems
    # And the real tables are clean again: the restore above is not a no-op.
    assert dp.check_exempt_tables(documents) == []


def test_exempted_citations_still_count_as_considered() -> None:
    # If the exemption check ran before the counter, a document whose pointers
    # are mostly exempt would report the same inventory as one with none — and
    # the floor meant to catch a blind reader would be catching prose style.
    assert _evidence(".minicc/config.json", "workspace/app.py", "minicc/config.py") == []
    # A bare name with no slash is not a location claim even when it is exempt:
    # counting it would let the inventory floor be met by words.
    assert _evidence("AGENTS.md", claims=0) == []
    _, stats = dp.check_document(REPO_ROOT / "README.md")
    assert stats.evidence >= 12, "README's floor must stay under what it actually holds"


def test_each_resolve_root_answers_a_shipped_citation() -> None:
    """A root no document reaches is dead code in a table that looks like policy."""
    answered: dict[str, str] = {}
    for document in dp.DEFAULT_DOCS:
        relative = document.relative_to(REPO_ROOT).as_posix()
        if relative in dp._OUT_OF_SCOPE_DOCS:
            continue
        for _, span in dp._code_spans(document.read_text(encoding="utf-8")):
            match = dp._PATH_REF.match(span) or dp._DIR_REF.match(span) or dp._TEST_REF.match(span)
            if match is None or dp._evidence_shape(span) is None:
                continue
            rel = match.groupdict().get("path") or match.groupdict().get("file")
            if not rel or dp._holds(rel):
                continue
            for base in dp._RESOLVE_ROOTS[1:]:
                if dp._holds(f"{base}/{rel}"):
                    answered.setdefault(base, f"{relative}: {span}")
                    break
    for base in dp._RESOLVE_ROOTS[1:]:
        assert base in answered, f"_{base} 没有任何 shipped 引用走到，是死行"
    assert len(answered) == len(dp._RESOLVE_ROOTS) - 1


def test_a_path_claim_written_outside_backticks_gets_its_own_reader() -> None:
    # The evidence reader only looks inside code spans, so dropping the backticks
    # would be a way to write a dangling path that no gate sees. This is that
    # other half: bare names are still shorthand, a slash makes it a claim.
    assert dp.prose_path_claims("见 docs/NOPE_XYZ.md 与 loop.py，还有 minicc/config.py。") == [
        "docs/NOPE_XYZ.md",
        "minicc/config.py",
    ]
    problems, stats = dp.check_document(_ROADMAP)
    assert stats.prose_paths >= 1 and problems == []


# --------------------------------------------------------------------------- #
# M8-T38: the inventory must be a function of what git holds, not of what this
# directory happens to contain. Each gate below was written after measuring the
# same HEAD report two different numbers — 782 evidence pointers in a clean
# checkout, 811 on the machine that had been building and running things here.
# --------------------------------------------------------------------------- #


def test_the_head_set_is_a_function_of_the_index_not_of_this_directory() -> None:
    listed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files"], capture_output=True, text=True, encoding="utf-8"
    ).stdout
    recomputed = {line.replace("\\", "/").split("/")[0] for line in listed.splitlines() if "/" in line}
    heads = set(dp._top_level())
    assert heads == recomputed, f"头集与 git ls-files 重算的不一致，多出 {sorted(heads - recomputed)}"
    # A directory that exists here but is absent from the index is a build or run
    # leftover; admitting it as a head is exactly how one HEAD grew 29 claims.
    disk = {entry.name for entry in REPO_ROOT.iterdir() if entry.is_dir()}
    leftover = {name for name in disk - heads if dp._git_ignored(name)}
    assert not leftover & heads
    assert heads <= disk, f"git 说有、磁盘却没有：{sorted(heads - disk)}"
    if (REPO_ROOT / "output").is_dir():
        assert "output" in leftover, "开发机上这条门必须真的看到 leftovers，否则它是空转的"


def test_planted_generated_directories_do_not_move_the_inventory(tmp_path: Path) -> None:
    tool, document = _scratch_repo(
        tmp_path, "# 记录\n\n结论见 `minicc/app.py:2`、`output/report.json` 与 `.minicc/state.json`。\n"
    )
    problems, stats = tool.check_document(document)
    assert problems == []
    assert stats.evidence == 2, "tracked 的那条，加上被豁免键 admit 的那条；output/ 不在索引里，连断言都算不上"
    root = document.parent.parent
    (root / "output" / "report.json").write_text("{}", encoding="utf-8")
    (root / ".minicc").mkdir()
    (root / ".minicc" / "state.json").write_text("{}", encoding="utf-8")
    after = _pointed_at(root, f"minicc_doc_pointers_planted_{next(_COUNTER)}")
    later_problems, later = after.check_document(document)
    assert later.evidence == stats.evidence, "同一份文档，只因为本机跑过一次构建，清单就长了"
    assert later_problems == []


def test_a_file_only_this_machine_has_is_red_on_this_machine_too(tmp_path: Path) -> None:
    tool, document = _scratch_repo(tmp_path, "# 记录\n\n实现见 `minicc/planted.py`。\n")
    root = document.parent.parent
    (root / "minicc" / "planted.py").write_text("VALUE = 1\n", encoding="utf-8")
    problems, stats = tool.check_document(document)
    assert stats.evidence == 1, "它得先被算作断言，否则这条红永远点不亮"
    assert len(problems) == 1, problems
    assert "指向的路径在仓库里不存在" in problems[0].detail, problems
    assert "git 没有跟踪" in problems[0].detail and "minicc/planted.py" in problems[0].detail, problems
    # Staging is enough to make it a repository fact, and that is the workflow's
    # order of operations: ``git add`` the new file, then write its citation.
    _git(root, "add", "minicc/planted.py")
    later = _pointed_at(root, f"minicc_doc_pointers_staged_{next(_COUNTER)}")
    assert later.check_document(document)[0] == []


def test_an_unreachable_exemption_reports_itself_as_dead(tmp_path: Path) -> None:
    documents = [d for d in dp.DEFAULT_DOCS if d.exists()]
    usage = dp.exemption_usage(documents)
    assert len(usage) == sum(len(table) for table in dp._EVIDENCE_TABLES)
    assert all(hits > 0 for hits in usage.values()), [k for k, v in usage.items() if v == 0]
    # A hit counter alone can be decorative, so load the two keys and see whether
    # the verdict or the inventory moves. M8-T37 shipped five keys that could
    # never be reached at all, and the reason nobody noticed is that nobody had
    # asked a table whether it fired.
    _, base = dp.check_document(_ROADMAP)
    build = dp._BUILD_OUTPUT_PATH
    narrowed = {key: reason for key, reason in build.items() if key != "minicc/web_static"}
    dp._EVIDENCE_TABLES = tuple(narrowed if t is build else t for t in dp._EVIDENCE_TABLES)
    try:
        freed = dp.check_document(_ROADMAP)[0]
    finally:
        dp._EVIDENCE_TABLES = tuple(build if t is narrowed else t for t in dp._EVIDENCE_TABLES)
    # A build-output citation resolves nowhere in a clean checkout, so taking its
    # exemption away turns it red — the key is holding something up. The count is
    # reconciled against the hit counter rather than copied out of a run: M8-T38's
    # own record added two citations of this key and a hand-written `== 2` went red
    # on the batch that was busy proving hand-written counts are worthless.
    freed_here = [p for p in freed if "minicc/web_static" in p.detail]
    assert freed == freed_here, freed
    assert len(freed_here) == dp.exemption_usage([_ROADMAP])["minicc/web_static"] >= 1, freed
    assert dp.check_document(_ROADMAP)[0] == []
    # A "not a repository path" key has the other job: it *admits* the citation as
    # a claim before excusing it, so removing one moves the inventory instead of
    # the verdict. Asserting only reds would call every such key dead.
    plain = dp._NOT_A_REPO_PATH
    wo = {key: reason for key, reason in plain.items() if key != ".minicc/"}
    dp._EVIDENCE_TABLES = tuple(wo if t is plain else t for t in dp._EVIDENCE_TABLES)
    try:
        shrunk = dp.check_document(_ROADMAP)[1]
    finally:
        dp._EVIDENCE_TABLES = tuple(plain if t is wo else t for t in dp._EVIDENCE_TABLES)
    assert shrunk.evidence < base.evidence, "撤掉一条豁免，清单竟然一格没动"
    assert dp.check_document(_ROADMAP)[1].evidence == base.evidence

    # Two ways an exemption can stop paying rent, and they need two complaints:
    # nothing cites it any more (stale), or it is still cited but can never be
    # reached again (dead row). The second is what five of M8-T37's keys were.
    key = "zzz_nothing_on_earth_cites_this_root/"
    monkey = dict(plain)
    monkey[key] = "刻意没人引用得到的键，用来量这条门的牙口"
    dp._EVIDENCE_TABLES = tuple(monkey if t is plain else t for t in dp._EVIDENCE_TABLES)
    try:
        uncited = [p.detail for p in dp.check_exempt_tables(documents)]
        cited_here = tmp_path / "CITED.md"
        # The bare prefix form is what the staleness rule can see and neither
        # reader can reach: no file after the slash, so no claim is ever formed.
        cited_here.write_text(f"# 说明\n\n这一族的路径前缀写作 {key}，仓库里没有。\n", encoding="utf-8")
        cited = [p.detail for p in dp.check_exempt_tables(documents + [cited_here])]
    finally:
        dp._EVIDENCE_TABLES = tuple(plain if t is monkey else t for t in dp._EVIDENCE_TABLES)
    assert uncited == [f"豁免 {key} 已无任何文档引用，是陈旧登记"], uncited
    assert cited == [f"豁免 {key} 没有命中任何在仓引用：这条规则现在挡不到东西，是死行"], cited
    assert dp.check_exempt_tables(documents) == []


#: Prose that must never be read as a pointer. The last one is not hypothetical:
#: it is a line this repository's own roadmap shipped, and until M8-T39 it *passed*
#: as a checked pointer — 「可见价值低于 M6–M8 任何一项」 is 可见 plus an unrelated id,
#: and both ids exist somewhere in the file, so the old rule had nothing to complain
#: about. A skipped span is merely unguarded; a fabricated one is a green tick on a
#: sentence that never claimed anything.
_NOT_POINTERS = [
    "这是典型的一个月重构、零用户可见收益，且这两个文件正是 M2/M3 的。",
    "控制台未见错误。",
    "| 长回答体验与进度可见性 | 中 |",
    "**：这条缺的「可满足性见证」现在有了。",
    "使用方法和口径见收益表。",
    "可见价值低于 M6–M8 任何一项，排在 M8 之后。",
]


def test_a_word_internal_marker_is_not_a_pointer_even_when_prose_holds_an_id() -> None:
    for line in _NOT_POINTERS:
        text = f"# T\n\n## 一、x\n\n{line}\n| M8-T34 探针 | ✅ | 结论 |\n"
        problems, checked, boxes = dp.check_pointers(Path("synthetic.md"), text)
        assert checked == 0, f"这条被当成了指针：{line} → {boxes}"
        assert boxes[dp.BOX_WORD] == 1, boxes
        assert problems == []
    # Anti-vacuity: the list must actually contain the case it was written for.
    assert any("M6–M8" in line for line in _NOT_POINTERS)


#: Every citation shape the tool claims to read. Written as one document with an
#: expected count, so a shape that quietly stops being harvested shows up as a
#: number moving rather than as a green run nobody checks.
_CITATION_DOC = """\
# T

## 三、第三节

## 附录 B：注记

### 记录（第二批）

| M4-3 覆盖 | ✅ | 细节 |
| M8-T16 探针 | ✅ | 细节 |

详见「第三节」。见 M8-T16 行。见「第二批 M4-3 行」。见附录 B。
参见 M4-3。结论见下方M8-T16 那条。
"""


def test_every_citation_shape_the_tool_reads_is_harvested() -> None:
    problems, checked, boxes = dp.check_pointers(Path("synthetic.md"), _CITATION_DOC)
    assert problems == []
    assert checked == boxes[dp.BOX_CHECKED] == 6, boxes
    assert sum(boxes.values()) == 6, "多出来的标记没有被任何一箱接住"
    assert boxes[dp.BOX_WORD] == 0, boxes


def test_an_id_glued_onto_chinese_is_still_an_id() -> None:
    """``\\b`` reads Chinese as a word character, so 「见下方M8-T26」 had no boundary.

    The pointer was not skipped-and-counted: it was never harvested as a claim at
    all, because the id inside it was invisible. Measured on the shipped corpus,
    the fix moves 0 ids (every existing pointer happens to have a space), so this
    gate is the only thing standing between that class and a silent return.
    """
    assert dp._ID.findall("见下方M8-T26 那条") == ["M8-T26"]
    assert dp._ID.findall("上方M4-3 行的第三格") == ["M4-3"]
    assert dp._ID.findall("XM8-T34 与 minicc_m8") == [], "编号不能从半个词里长出来"
    spans = {span for _, span, _, _ in dp._pointer_spans("# T\n\n结论见下方M8-T26 那条。\n")}
    assert spans == {"下方M8-T26 那条"}, spans
    _, checked, boxes = dp.check_pointers(Path("synthetic.md"), _CITATION_DOC)
    assert boxes[dp.BOX_CHECKED] == checked >= 1


def test_the_box_account_is_printed_and_adds_up_on_the_shipped_documents() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    summary = result.stdout.strip().splitlines()[-1]
    markers = int(re.search(r"(\d+) 「见」 markers", summary).group(1))
    assert "markers=" in result.stdout
    counted = 0
    for box in dp.POINTER_BOXES:
        assert f"{box}=" in summary, f"总账里没有 {box} 这一箱"
        counted += int(re.search(rf"{box}=(\d+)", summary).group(1))
    # The printed account must add up to the printed denominator: a box the reader
    # cannot see, or a marker that fell between two boxes, breaks one of these two.
    assert counted == markers, (counted, markers, summary)


def test_boxes_have_floors_because_a_box_that_goes_blind_is_a_clean_run() -> None:
    account = {box: 0 for box in dp.POINTER_BOXES}
    markers = 0
    for document in dp.DEFAULT_DOCS:
        _, stats = dp.check_document(document)
        markers += stats.markers
        for box, count in stats.boxes.items():
            account[box] += count
    assert markers == sum(account.values()) > 100, account
    floors = {
        dp.BOX_CHECKED: 25,
        dp.BOX_NO_LOCATOR: 10,
        dp.BOX_LINK_TEXT: 5,
        # M8-T41 split the old hand-off box: only a gap span the evidence reader really
        # parses may stay here, so the count fell 7→2 and the remainder moved to
        # ``code-span-names-a-file``. Both floors sit under what the corpus holds today
        # (2 and 5) because a floor at the current count would red on the next prose
        # edit and teach nobody anything.
        dp.BOX_CODE_SPAN: 1,
        dp.BOX_CODE_NAME: 4,
        dp.BOX_QUOTED_NAME: 1,
        dp.BOX_PATH: 1,
        dp.BOX_WORD: 40,
    }
    assert set(floors) == set(dp.POINTER_BOXES)
    for box, floor in floors.items():
        assert account[box] >= floor > 0, f"{box} 只有 {account[box]} 条，低于下限 {floor}"


def test_a_box_that_stops_counting_is_a_complaint_not_a_clean_run(monkeypatch) -> None:
    """The reconciliation is checked against an independent recount of markers."""
    spans = dp._pointer_spans(_GOOD_DOC)
    assert len(spans) >= 3
    monkeypatch.setattr(dp, "_pointer_spans", lambda text: spans[1:])
    problems, _checked, boxes = dp.check_pointers(Path("synthetic.md"), _GOOD_DOC)
    assert [p.kind for p in problems] == ["RECONCILE"], problems
    assert len(spans) == sum(boxes.values()) + 1
    assert "计数前就跳过" in problems[0].detail


def test_an_arabic_section_number_is_a_locator_and_a_heading_answers_it() -> None:
    """``第8节`` and ``## 8. 继续实施`` are one fact written two ways.

    Both halves had to be taught at once. Reading the digit in prose but not in a
    heading would make every such pointer red; reading the heading but not the prose
    is what this repository shipped until M8-T40, and it left the pointer in the
    word-interior box — the same place 可见 lives, so it was counted as "not a
    reference" rather than "a reference nobody checked".
    """
    assert dp._numeral("8") == 8 and dp._numeral("十二") == 12
    assert dp._SECTION.search("交付说明第8节") and dp._BATCH.search("第3批")
    resolved = "# T\n\n## 8. 继续实施\n\n内容。见第8节。\n"
    assert _pointer_problems(resolved) == []
    problems, checked, boxes = dp.check_pointers(Path("synthetic.md"), resolved)
    assert checked == boxes[dp.BOX_CHECKED] == 1, (checked, boxes)
    assert boxes[dp.BOX_WORD] == 0, "指针掉进词内箱就是没人查"
    assert len(_pointer_problems("# T\n\n## 8. 继续实施\n\n见第7节。\n")) == 1
    # A number with no separator is a title, not a claim about being section N.
    assert len(_pointer_problems("# T\n\n## 8 继续实施\n\n见第8节。\n")) == 1


def test_an_arabic_pointer_to_a_nickname_still_needs_the_file_named() -> None:
    """The new locator inherits the old doctrine: a nickname is not a findable file."""
    assert _pointer_problems("接口见 [docs/PLUGIN_API.md](docs/PLUGIN_API.md) 第3节。\n") == []
    assert len(_pointer_problems("证据见交付说明第8节。\n")) == 1
    assert len(_pointer_problems("证据见交付说明第99节。\n")) == 1


def test_the_corpus_holds_arabic_pointers_and_the_tool_now_reads_every_one() -> None:
    """Not a synthetic-only fix: the digit spelling is in use, and it now resolves.

    The counter-example is M8-T39's glued-id change, whose corpus impact measured 0.
    Here it is 2 — and 0 spans naming a numbered place may sit in the word box, which
    is what makes this a closing gate rather than an opening one.
    """
    arabic = []
    in_word = []
    for document in dp.DEFAULT_DOCS:
        text = document.read_text(encoding="utf-8")
        for offset, span, box, _targets in dp._pointer_spans(text):
            line = dp._line_of(text, offset)
            if re.search(r"第\d+(?:节|批)", span):
                arabic.append((document.name, line, span, box))
                if box == dp.BOX_WORD:
                    in_word.append((document.name, line, span))
    assert len(arabic) == 2, arabic
    assert {box for *_x, box in arabic} == {dp.BOX_CHECKED}, arabic
    assert in_word == [], f"仍有编号指针躺在词内箱：{in_word}"


def test_no_two_level_two_headings_claim_the_same_number() -> None:
    """A tie is resolved by ``setdefault``, so the corpus has to say ties do not exist.

    Otherwise one pointer would silently stand for whichever section a dict happened
    to keep — the same single-number-covering-two-things failure M8-T39 opened.
    """
    claims: dict[tuple[str, int], list[str]] = {}
    for document in dp.DEFAULT_DOCS:
        for section in dp.sections(document.read_text(encoding="utf-8")):
            if section.level != 2:
                continue
            match = re.match(r"^([一二三四五六七八九十]+|\d+)[.、]", section.title)
            if match:
                claims.setdefault((document.name, dp._numeral(match.group(1))), []).append(
                    section.title[:30]
                )
    assert claims, "没有编号标题可查，这条门就是空的"
    ties = {key: titles for key, titles in claims.items() if len(titles) > 1}
    assert ties == {}, f"同一个编号被两个标题认领：{ties}"


def test_a_link_shape_inside_a_code_span_is_a_quotation(tmp_path: Path) -> None:
    """M8-T40 wrote a record that *quoted* a link to explain itself, and the gate went red.

    The pointer reader has treated backticks as quotation since M8-T37; this reader had
    no mask at all, so ```[总交付第9节](不存在.md)``` was a claim about a file that does
    not exist. Fixing the prose would have hidden a rule that only existed in one of the
    two readers.
    """
    (tmp_path / "real.md").write_text("# real\n", encoding="utf-8")
    text = "举例 `[总交付第9节](不存在.md)` 只是形状说明。\n\n再来一次 `[某节]( Nope.md)`。\n\n[真的](real.md)\n"
    problems, checked, generated = dp.check_links(tmp_path / "doc.md", text)
    assert checked == 1 and problems == [] and generated == 0, (checked, problems)
    # The unmasked shape is still a claim: the mask cannot be a blanket exemption.
    assert len(dp.check_links(tmp_path / "doc.md", "[假的](不存在.md)\n")[0]) == 1
    # And the pointer reader consults the same mask: a link that only exists inside
    # backticks buys no hand-off, while its unquoted twin does. (The quoted one lands in
    # 「word-interior」 because 说明… is not a citation position — M8-T39's rule, and this
    # batch leaves it alone.)
    assert _first_box("结论见「说明 `[README](README.md)` 那段」。\n") == dp.BOX_WORD
    assert _first_box("结论见「说明 [README](README.md) 那段」。\n") == dp.BOX_LINK_TEXT


def test_the_link_reader_actually_has_quotations_to_ignore() -> None:
    """Non-vacuity: if no shipped document quoted a link, the gate above would be decorative."""
    quoted = 0
    for document in dp.DEFAULT_DOCS:
        text = document.read_text(encoding="utf-8")
        quoted += len(list(dp._LINK.finditer(text))) - len(list(dp._LINK.finditer(dp._mask_code(text))))
    assert quoted >= 3, f"语料里只有 {quoted} 个被引用的链接形状，这条门的落点已经消失"


_NAME_DOC = "# T\n\n具体口径见 `config.py:331-338` 的注释。\n"
_FIELD_DOC = "# T\n\n字段口径见 `answer` 那一段。\n"


def _first_box(text: str) -> str:
    *_, box, _targets = dp._pointer_spans(text)[0]
    return box


def test_a_citation_at_a_bare_file_name_is_resolved_rather_than_deferred() -> None:
    """``carried-by-evidence-reader`` used to mean "there is a backtick nearby".

    A bare name is exactly the shape the evidence reader refuses on purpose — so the
    pointer reader booked the hand-off and nobody showed up. It now answers for those
    citations itself: existence, and a line range that fits the file it names.
    """
    assert _first_box(_NAME_DOC) == dp.BOX_CODE_NAME
    assert _pointer_problems(_NAME_DOC) == []
    typo = _NAME_DOC.replace("config.py:331-338", "config_typo_xyz.py")
    problems = _pointer_problems(typo)
    assert len(problems) == 1 and "没有任何同名文件" in problems[0], problems
    assert len(_pointer_problems(_NAME_DOC.replace("331-338", "99999-100000"))) == 1
    # A name under a directory git ignores is a run's own output: same three-state
    # answer the link reader gives, so it is counted and not reported.
    ignored = _NAME_DOC.replace("config.py:331-338", "output/playwright/whatever.json")
    assert _pointer_problems(ignored) == [] and _first_box(ignored) == dp.BOX_CODE_NAME


def test_the_hand_off_box_requires_the_other_reader_to_actually_parse_the_span() -> None:
    """The gap's code span must be a target, and a target-less one is not 「not a reference」."""
    assert _first_box("证据见 `docs/ROADMAP_TO_PRODUCT.md` 一段。\n") == dp.BOX_CODE_SPAN
    # A field name is neither an evidence shape nor a file: it is a real pointer whose
    # target cannot be looked up, which belongs with 口径见下方注记, not with 可见.
    assert _first_box(_FIELD_DOC) == dp.BOX_NO_LOCATOR
    handed_off = []
    for document in dp.DEFAULT_DOCS:
        for _offset, span, box, targets in dp._pointer_spans(document.read_text(encoding="utf-8")):
            if box == dp.BOX_CODE_SPAN and not any(kind == "evidence" for kind, _ in targets):
                handed_off.append((document.name, span))
    assert handed_off == [], f"这些指针被记成别人会查，其实没人查：{handed_off}"


def test_the_name_reader_has_work_in_the_shipped_corpus() -> None:
    """Non-vacuity: the new box has to be load-bearing on the documents as shipped."""
    resolved: list[tuple[str, str]] = []
    for document in dp.DEFAULT_DOCS:
        for _offset, _span, box, targets in dp._pointer_spans(document.read_text(encoding="utf-8")):
            if box == dp.BOX_CODE_NAME:
                names = [span for kind, span in targets if kind == "name"]
                assert names, (document.name, _offset)
                resolved += [(document.name, name) for name in names]
    assert len(resolved) >= 4, f"名字箱只剩 {len(resolved)} 条，这条门已经是空的：{resolved}"


def test_a_bracket_that_is_not_a_judged_link_buys_no_hand_off() -> None:
    """``carried-by-link-reader`` used to mean "a square bracket is somewhere nearby".

    The link reader walks ``[text](target)`` and then *declines* four targets: empty, an
    in-page anchor, an external URL, and — because a space breaks its grammar — a path it
    never parses at all. A citation landing on any of those was booked as checked while
    both readers disclaimed it, which is M8-T41's defect in the other hand-off box. Each
    shape is asserted from both sides: the box it lands in, and the link reader's own
    count of links it examined.
    """
    shapes = [
        "结论见 [待定] 的说明。\n",  # a bracket that is not a link at all
        "详见 [本节](#t) 的说明。\n",  # an in-page anchor
        "用法见 [官网](https://example.com/x)。\n",  # not a claim about this repository
        "细节见 [说明]()。\n",  # empty target
        "细节见 [说明](a b.md)。\n",  # a space the grammar will not parse
        "详见 `[说明](README.md)`。\n",  # only inside backticks: a quotation, masked both sides
    ]
    for text in shapes:
        assert _first_box(text) == dp.BOX_NO_LOCATOR, text
        _problems, checked, _generated = dp.check_links(Path("synthetic.md"), text)
        assert checked == 0, f"{text} 被记成已托管，可链接阅读器一条都没看"
    # A real hand-off is a real verdict — even the red kind. The box promises the reader
    # *answers*, not that the answer is pleasant.
    dangling = "详见 [说明](不存在.md)。\n"
    assert _first_box(dangling) == dp.BOX_LINK_TEXT
    assert len(dp.check_links(Path("synthetic.md"), dangling)[0]) == 1


def test_a_link_that_starts_after_the_marker_words_is_still_handed_over() -> None:
    """The mirror defect: a resolvable link the old rule *missed* because the bracket
    was not the span's first character. It sat in 「no criterion」 — the account the tool
    admits it cannot check — while a fully checkable target was one space away.
    """
    text = "见下方 [说明](README.md) 一条。\n"
    assert _first_box(text) == dp.BOX_LINK_TEXT
    assert dp.check_links(Path("synthetic.md"), text)[1] == 1


def test_every_shipped_link_hand_off_shrinks_the_link_reader_when_removed() -> None:
    """Reconcile the box against its creditor, through the creditor's own return.

    For each marker filed as ``carried-by-link-reader`` the region is blanked and the
    link reader asked how many links it now sees. If that number does not fall, the
    reader never looked at what the pointer reader just promised it. The invariant is
    measured from ``check_links``, not from the pointer side's copy of the grammar, so
    the two skip lists cannot drift apart unnoticed.
    """
    handed_off = 0
    for document in dp.DEFAULT_DOCS:
        text = document.read_text(encoding="utf-8")
        masked = dp._mask_code(text)
        baseline = dp.check_links(document, text)[1]
        matches = list(dp._POINTER.finditer(masked))
        spans = dp._pointer_spans(text)
        assert len(matches) == len(spans), (document.name, len(matches), len(spans))
        for (offset, span, box, _targets), match in zip(spans, matches):
            if box != dp.BOX_LINK_TEXT:
                continue
            handed_off += 1
            after = offset + (2 if masked.startswith("参见", offset) else 1)
            blanked = masked[:after] + " " * (match.end() - after) + masked[match.end() :]
            assert dp.check_links(document, blanked)[1] < baseline, (document.name, span)
    assert handed_off >= 5, f"交接箱只剩 {handed_off} 条，这条门已经是空的"


def test_a_quoted_pointer_is_answered_only_by_a_label_on_the_side_it_claims() -> None:
    """「见下文「X」」 is a two-part assertion: a label named X exists, *and* it is below.

    M8-T43 harvested these pointers for the first time, and a harvest without a reader
    would move a marker out of the honest open account into 「word-interior」, whose meaning
    is "this is not a reference" (M8-T40). So the reader is pinned in both directions and
    against all three ways a passage in this repository gets a name.
    """
    declared = "#### 基线统计口径\n"
    assert _pointer_problems("口径见下文「基线」一条。\n")  # nothing declares it
    assert _pointer_problems(declared + "口径见下文「基线」一条。\n")  # 下文: above is the wrong side
    assert _pointer_problems("口径见下文「基线」一条。\n" + declared) == []
    assert _pointer_problems(declared + "口径见上文「基线」一条。\n") == []
    assert _pointer_problems("口径见下文「基线」一条。\n**基线口径**：略。\n") == []
    assert _pointer_problems("口径见下表「基线」一条。\n| 基线口径 | 说明 |\n|---|---|\n") == []


def test_every_word_in_the_shared_place_word_list_harvests_its_quoted_form() -> None:
    """One tuple now feeds both patterns; the loop is over that tuple, not a copy of it.

    The lists used to drift: the harvest's directional group knew ten place-words and
    ``_CITATION_HEAD`` knew the same notion with seventeen, so 「见下文「X」」 - whose word was
    in the longer list - never took the quote-delimited branch. Its name arrived glued
    inside a raw span and no reader was asked about it. A hand-copied list here would go
    stale exactly the same way and stay green.
    """
    for word in dp._DIRECTION:
        text = f"口径见{word}「基线」一条。\n#### 基线统计口径\n"
        assert _first_box(text) == dp.BOX_QUOTED_NAME, word


def test_a_pointer_wrapped_in_its_own_bold_label_cannot_answer_itself() -> None:
    """``**当前实测口径见本节「当前实测」一段**`` - the only declaration is the sentence itself.

    M8-T36 settled that a target has to *declare* a name; keeping the label's extent is
    what makes that checkable here. Remove the self-quote guard and this line turns green,
    which is how the mutation proof shows the guard carries weight.
    """
    text = "- **当前实测口径见本节「当前实测」一段**\n"
    assert _first_box(text) == dp.BOX_QUOTED_NAME
    assert _pointer_problems(text)
    assert _pointer_problems(text + "## 当前实测读数\n") == []


def test_a_quoted_pointer_without_a_place_word_is_not_a_locative_citation() -> None:
    """The narrowing that keeps M8-T39/T40 alive: only 见<place-word>「X」 cites a location.

    「结论见「基线」这里。」 quotes a description, not a place, so the head test still decides
    it and it lands in 「word-interior」 even where a heading declares the name. Giving the
    benefit of the doubt to *every* quoted span would re-file M8-T40's mask shape here, and
    that gate's point is that a quotation is not an assertion.
    """
    assert _first_box("结论见「基线」这里。\n#### 基线统计口径\n") == dp.BOX_WORD


def test_every_shipped_quoted_name_pointer_answers_for_itself() -> None:
    """The new box must hold real tenants, and each one must be answered by its own document.

    The count is the M8-T42 lesson in the other direction: a box nobody lives in is a rule
    that only exists in its own tests. Each shipped marker is re-asked here so the reading
    cannot be held up by the summary line alone.
    """
    tenants = 0
    for document in dp.DEFAULT_DOCS:
        text = document.read_text(encoding="utf-8")
        labels = dp._declared_labels(text)
        for offset, span, box, _targets in dp._pointer_spans(text):
            if box != dp.BOX_QUOTED_NAME:
                continue
            tenants += 1
            problems = dp._check_quoted_name(document, text, offset, span, labels)
            assert problems == [], (document.name, span)
    assert tenants >= 1, f"引号命名箱只剩 {tenants} 条，这条门已经是空的"


def test_the_script_recompiles_from_source_with_warnings_escalated() -> None:
    """``-W error`` only bites when the source is really compiled - and a fresh .pyc hides it.

    M8-T43 wrote an escaped backtick inside a plain docstring: an invalid escape sequence,
    which CPython reports while compiling. The suite stayed green because the cached
    bytecode was newer than the source, so no ``-W error`` process ever re-read the file -
    the mutation run of this batch found it only because rewriting the source invalidated
    that cache. Recompiling the bytes on disk is the one way this file's warnings surface.
    """
    import warnings as escalation

    with escalation.catch_warnings():
        escalation.simplefilter("error")
        compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec")


def test_a_pointer_that_names_a_document_is_answered_in_that_document() -> None:
    """「结论见 README.md 第8节」 must not be answered by *this* document's 第8节.

    The pair is the whole point: a lone green reading proves nothing until the same number
    resolves for the reason the pointer gives. Measured before the change, these two texts
    produced byte-identical accounts (checked=1, no problems), which is how a pointer at a
    document with no numbered section at all survived every gate.
    """
    head = "## 8. 继续实施\n\n正文。\n\n"
    readme = dp.REPO_ROOT / "README.md"
    assert 8 not in dp._numbered_sections(readme), (
        "门的前提没了：README.md 现在有了编号二级标题，换成一个确实没有的文档再跑"
    )
    assert dp._numbered_sections(dp.REPO_ROOT / "docs" / "PLUGIN_API.md").get(3) is not None, (
        "门的前提没了：docs/PLUGIN_API.md 的第3节不在了，正向控制组就只是句空话"
    )

    pointed_elsewhere = head + "结论见 README.md 第8节。\n"
    problems, checked, _boxes = dp.check_pointers(Path("synthetic.md"), pointed_elsewhere)
    assert checked == 1, "它仍在 checked 箱里：一个点名了别处、又答错了地方的指针必须计入总分"
    assert [p.detail for p in problems] == [
        "「README.md 第8节」 说第8节在 README.md 里，那里查不到这个编号的章节"
    ], problems

    really_here = head + "结论见第8节。\n"
    assert dp.check_pointers(Path("synthetic.md"), really_here)[0] == []

    owns_it = head + "结论见 docs/PLUGIN_API.md 第3节。\n"
    assert dp.check_pointers(Path("synthetic.md"), owns_it)[0] == [], "点名的文档真有这一节，必须绿"


def test_a_bare_file_name_beside_a_link_is_still_this_markers_claim() -> None:
    """The link reader answers the link; a second name in the same span answers to nobody.

    ``carried-by-link-reader`` was written against one claim per marker. The control (a name
    that does exist, so the whole line is still green) is what makes this a gate rather than a
    complaint about any file name in prose.
    """
    missing = "口径见 nope_missing_file.md 与 [说明](README.md)。\n"
    problems, checked, boxes = dp.check_pointers(Path("synthetic.md"), missing)
    assert checked == 0 and boxes[dp.BOX_LINK_TEXT] == 1, boxes
    assert [p.detail for p in problems] == ["指针引用的 `nope_missing_file.md` 在仓库里没有任何同名文件"]

    present = "口径见 README.md 与 [说明](docs/ROADMAP_TO_PRODUCT.md)。\n"
    problems, checked, boxes = dp.check_pointers(Path("synthetic.md"), present)
    assert problems == [] and boxes[dp.BOX_LINK_TEXT] == 1, problems


def test_a_bare_file_name_after_see_is_a_citation_not_a_word() -> None:
    """「口径见 nope.md」 points at something; 「可见收益」 does not, and the boxes mean it.

    Filing the first in ``word-interior`` was self-contradicting: that box exists to say "no
    reference was made here", and it was also the box with no reader at all.
    """
    text = "口径见 nope_missing_file.md。\n"
    problems, _checked, boxes = dp.check_pointers(Path("synthetic.md"), text)
    assert boxes[dp.BOX_WORD] == 0 and boxes[dp.BOX_NO_LOCATOR] == 1, boxes
    assert [p.detail for p in problems] == ["指针引用的 `nope_missing_file.md` 在仓库里没有任何同名文件"]
    # The old exemption still holds: a 见 that is a suffix is not a citation, name or not.
    assert dp._pointer_box("", "可见 nope_missing_file.md", "") == dp.BOX_WORD


def test_the_pointer_reader_leaves_slashed_names_to_the_prose_reader() -> None:
    """One claim, one invoice: a name carrying a directory is the prose reader's business.

    ``_prose_path_claims`` keeps only claims with a slash, so the pointer reader picks up
    exactly the complement of that test - not a superset, or every path-shaped citation in a
    pointer would start showing up twice, which is the accounting error M8-T41 was about.
    """
    assert dp._span_names("docs/nope_missing_x.md 第8节") == []
    assert dp._span_names("nope_missing_x.md 第8节") == ["nope_missing_x.md"]
    # A link's own target is already judged by check_links, so it is never re-invoiced here.
    assert dp._span_names("[说明](docs/nope_missing_x.md)") == []
    # ...but a document written in the marker's own text still owns the section claim.
    assert [name for name, _ in dp._span_documents("docs/nope_missing_x.md 第8节")] == [
        "docs/nope_missing_x.md"
    ]
    assert dp._span_documents("[说明](docs/nope_missing_x.md)") == []


def test_a_blamed_document_is_named_in_the_complaint() -> None:
    """A red that says "第8节 不存在" would teach a writer to fix the wrong file.

    The section *does* exist - here. Only the sentence naming the document makes the failure
    actionable, so the name is part of the gate, not decoration.
    """
    text = "## 8. 继续实施\n\n结论见 README.md 第8节。\n"
    details = [p.detail for p in dp.check_pointers(Path("synthetic.md"), text)[0]]
    assert len(details) == 1 and "README.md" in details[0], details


def test_the_bare_name_shape_is_defined_exactly_once() -> None:
    """The extension list must not become a fourth copy - M8-T43's whole lesson.

    ``_CITATION_HEAD`` is built from ``_PROSE_PATH.pattern`` rather than re-typed, so the
    decision "this is a file name" cannot drift from the decision "this name belongs to the
    pointer reader". A re-typed copy would compile and pass every other gate here.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    assert dp._PROSE_PATH.pattern in dp._CITATION_HEAD.pattern
    assert source.count("py|md|toml|json|txt|example") == 1, (
        "裸文件名形状又出现了一份手抄副本：谁改了其中一份，另一份就会安静地不同意"
    )
