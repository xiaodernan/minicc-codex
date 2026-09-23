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
    problems, checked, unresolved = dp.check_pointers(Path("synthetic.md"), text)
    assert checked or unresolved
    return [f"{p.detail}" for p in problems]


def test_prose_that_merely_ends_with_the_marker_is_not_harvested() -> None:
    problems, checked, unresolved = dp.check_pointers(Path("synthetic.md"), _GOOD_DOC)
    assert problems == []
    # 「见下方注记」 and friends are counted as a *gap*, not silently dropped.
    assert unresolved >= 2
    assert checked >= 2, "the doc must actually exercise the locator paths"


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
    problems, checked, unresolved = dp.check_pointers(Path("synthetic.md"), quoted)
    assert problems == [] and checked == 0
    # Masking blanks the whole span, marker included, so the quotation is never
    # harvested at all — it is not an unresolved marker, it is absent. My first
    # version of this gate asserted ``unresolved == 1`` and was wrong: the tool
    # was already right, and an expectation written from what I wanted the tool
    # to do is the same mistake as a self-satisfying id check.
    assert unresolved == 0

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
