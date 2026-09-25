"""Enhanced deterministic retrieval tests.

Covers: mixed EN/CJK tokenization, path-pattern signals, guidance files,
mtime freshness, symbol extraction, stats(), limit boundaries, empty
queries and the 1000-file build budget.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from minicc.agent.retrieval import LocalEvidenceIndex


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _build_project(root: Path) -> LocalEvidenceIndex:
    """7-file pseudo project: guidance + python + js + tests + docs."""

    _write(root / "AGENTS.md", "# 项目约定\n\n项目使用 Python 编写，运行 pytest 执行测试。构建命令：python -m pytest。\n文档放在 docs 目录。\n")
    _write(root / "src" / "parser.py", '"""Widget parsing helpers."""\n\n\nclass WidgetParser:\n    pass\n\n\ndef parse_widget(raw):\n    return raw\n\n\ndef load_config(path):\n    return {}\n')
    _write(root / "src" / "auth.py", "# 处理用户登录\nclass UserAuth:\n    def login(self, name):\n        return True\n")
    _write(root / "web" / "view.py", "def render_view(item):\n    return item\n")
    _write(root / "web" / "charts.js", "function renderChart(data) {\n  return data;\n}\nconst chartConfig = {width: 100};\n// TODO: fix legend overlap\n")
    _write(root / "tests" / "test_parser.py", "from src.parser import parse_widget\n\nFAILED tests/test_parser.py::test_parse_widget\n")
    _write(root / "docs" / "notes.md", "the theory of everything\n")
    return LocalEvidenceIndex(root)


def test_english_query_ranks_symbol_and_content_matches(tmp_path: Path) -> None:
    index = _build_project(tmp_path)
    hits = index.search("parse widget config")
    assert hits, "expected hits for english query"
    assert hits[0].path == "src/parser.py"
    assert "parse_widget" in hits[0].symbols
    assert "load_config" in hits[0].symbols
    top3 = {hit.path for hit in hits[:3]}
    assert "src/parser.py" in top3
    assert "tests/test_parser.py" in top3
    assert "symbol" in hits[0].reason
    assert "content" in hits[0].reason


def test_cjk_bigram_query_hits_expected_file(tmp_path: Path) -> None:
    index = _build_project(tmp_path)
    hits = index.search("用户登录")
    assert hits and hits[0].path == "src/auth.py"
    # A two-character query collapses to exactly one bigram.
    assert index.search("登录")[0].path == "src/auth.py"


def test_mixed_cjk_english_query(tmp_path: Path) -> None:
    index = _build_project(tmp_path)
    hits = index.search("修复 parser 的 bug")
    assert hits and hits[0].path == "src/parser.py"


def test_stopwords_are_removed_from_queries(tmp_path: Path) -> None:
    index = _build_project(tmp_path)
    plain = index.search("parse widget")
    noisy = index.search("the and of parse widget")
    assert plain and noisy
    # Stopword noise must not change the ranking.
    assert [hit.path for hit in plain] == [hit.path for hit in noisy]
    # "the" must not pull in docs/notes.md ("the theory of everything").  The
    # comparison is on the file *name*, because the indexed path is
    # ``docs/notes.md``: the bare ``"notes.md" != hit.path`` shape this line used
    # to carry can never fire, and M8-T48 measured it staying green while a
    # mutation handed out exactly the fabricated hit the comment forbids.
    assert all(Path(hit.path).name != "notes.md" for hit in noisy), [hit.path for hit in noisy]


def test_path_pattern_basename_and_suffix_are_strong_signals(tmp_path: Path) -> None:
    index = _build_project(tmp_path)
    hits = index.search("修复 view.py 里的 bug")
    assert hits and hits[0].path == "web/view.py"
    assert "path-pattern" in hits[0].reason
    # A bare ".py" suffix query should only surface python files on top.
    ext_hits = index.search("列出 .py 文件")
    assert ext_hits
    assert all(hit.path.endswith(".py") for hit in ext_hits[:3])


def test_guidance_file_is_boosted_and_minicc_instructions_indexed(tmp_path: Path) -> None:
    index = _build_project(tmp_path)
    hits = index.search("构建 测试 约定")
    assert hits and hits[0].path == "AGENTS.md"
    assert "guidance" in hits[0].reason


def test_minicc_instructions_bypass_skip_dir(tmp_path: Path) -> None:
    _write(tmp_path / ".minicc" / "instructions.md", "部署流程：先跑 tests 再发布\n")
    _write(tmp_path / "app.py", "x = 1\n")
    index = LocalEvidenceIndex(tmp_path)
    assert index.stats()["files_indexed"] == 2
    hits = index.search("部署")
    assert hits and hits[0].path == ".minicc/instructions.md"


def test_mtime_freshness_prefers_recent_files(tmp_path: Path) -> None:
    _write(tmp_path / "alpha_old.py", "alpha beta\n")
    _write(tmp_path / "alpha_new.py", "alpha beta\n")
    now = time.time()
    os.utime(tmp_path / "alpha_old.py", (now - 90 * 86400, now - 90 * 86400))
    os.utime(tmp_path / "alpha_new.py", (now - 3600, now - 3600))
    hits = LocalEvidenceIndex(tmp_path).search("alpha")
    assert len(hits) >= 2
    assert hits[0].path == "alpha_new.py"
    scores = {hit.path: hit.score for hit in hits}
    assert scores["alpha_new.py"] > scores["alpha_old.py"]


def test_symbols_cover_python_js_and_todo_markers(tmp_path: Path) -> None:
    index = _build_project(tmp_path)
    hits = index.search("renderChart")
    assert hits and hits[0].path == "web/charts.js"
    assert "renderChart" in hits[0].symbols
    assert "chartConfig" in hits[0].symbols  # const extraction
    marker_hits = index.search("TODO fix")
    assert marker_hits and marker_hits[0].path == "web/charts.js"
    assert any(symbol.upper().startswith("TODO") for symbol in marker_hits[0].symbols)


def test_stats_reports_build_metrics(tmp_path: Path) -> None:
    index = _build_project(tmp_path)
    stats = index.stats()
    assert set(stats) >= {"files_indexed", "symbols_extracted", "last_build_ms"}
    assert stats["files_indexed"] == 7
    # parse_widget, load_config, WidgetParser, UserAuth, login, render_view,
    # renderChart, chartConfig, TODO marker = 9 extracted symbols.
    assert stats["symbols_extracted"] == 9
    assert 0 < stats["last_build_ms"] < 3000.0
    before = index.stats()
    index.search("parse")
    # The snapshot is built once and cached; stats stay stable afterwards.
    assert index.stats() == before


def test_limit_boundaries_and_empty_query(tmp_path: Path) -> None:
    for number in range(8):
        _write(tmp_path / f"alpha_{number}.py", "alpha\n")
    index = LocalEvidenceIndex(tmp_path)
    assert len(index.search("alpha", limit=1)) == 1
    assert len(index.search("alpha", limit=0)) == 1  # clamped to 1
    assert len(index.search("alpha", limit=3)) == 3
    assert len(index.search("alpha", limit=100)) == 8  # capped at 20
    hits = index.search("alpha", limit=100)
    assert hits[0].path == "alpha_0.py"  # deterministic tie-break by path
    # Empty / whitespace-only / None queries return no hits.
    assert index.search("") == []
    assert index.search("   ") == []
    assert index.search(None) == []  # type: ignore[arg-type]


def test_to_dict_keeps_consumer_contract(tmp_path: Path) -> None:
    index = _build_project(tmp_path)
    hits = index.search("parse widget")
    assert hits
    payload = hits[0].to_dict()
    # web.py reads path/reason/symbols from to_dict()-shaped hits.
    for key in ("path", "reason", "symbols", "score"):
        assert key in payload
    assert isinstance(payload["symbols"], list)
    assert payload["path"] == "src/parser.py"
    assert isinstance(payload["reason"], str) and payload["reason"]


def _package_tree(root: Path, packages: int) -> None:
    for package in range(packages):
        directory = root / f"pkg{package:03d}"
        for number in range(10):
            _write(directory / f"mod_{number}.py", f"def handler_{package}_{number}(payload):\n    return payload\n")


def _count_filesystem_calls(run) -> dict[str, int]:
    """Count the filesystem calls ``run()`` makes, then restore every patch.

    Python 3.11 binds ``os.stat`` into pathlib's accessor at import time, so
    wrapping the ``os`` module would silently miss every ``Path.stat()`` the
    indexer makes.  The counters therefore wrap the methods it actually calls.
    """

    counters = {"stat": 0, "open": 0, "is_symlink": 0, "iterdir": 0, "walk": 0}
    original = {
        "stat": Path.stat,
        "open": Path.open,
        "is_symlink": Path.is_symlink,
        "iterdir": Path.iterdir,
        "walk": os.walk,
    }

    def wrap(key: str):
        real = original[key]

        def counted(*args, **kwargs):
            counters[key] += 1
            return real(*args, **kwargs)

        return counted

    Path.stat = wrap("stat")  # type: ignore[method-assign]
    Path.open = wrap("open")  # type: ignore[method-assign]
    Path.is_symlink = wrap("is_symlink")  # type: ignore[method-assign]
    Path.iterdir = wrap("iterdir")  # type: ignore[method-assign]
    os.walk = wrap("walk")  # type: ignore[assignment]
    try:
        run()
    finally:
        Path.stat = original["stat"]  # type: ignore[method-assign]
        Path.open = original["open"]  # type: ignore[method-assign]
        Path.is_symlink = original["is_symlink"]  # type: ignore[method-assign]
        Path.iterdir = original["iterdir"]  # type: ignore[method-assign]
        os.walk = original["walk"]  # type: ignore[assignment]
    assert Path.stat is original["stat"], "the counter leaked a patch"
    return counters


def _cold_build_counts(root: Path) -> tuple[dict[str, int], int]:
    seen: dict[str, int] = {}

    def build() -> None:
        index = LocalEvidenceIndex(root, max_files=1500)
        seen["files"] = int(index.stats()["files_indexed"])

    calls = _count_filesystem_calls(build)
    return calls, seen["files"]


def test_thousand_file_index_builds_within_budget(tmp_path: Path) -> None:
    """A liveness bound.  The performance judgement moved to the call counter.

    The stopwatch used to carry that judgement by itself and it was
    unschedulable: the same 1000-file shape measured 3.06s, 19.90s and 45.05s
    minutes apart on one machine, because per-file cost here is dominated by
    file creation and virus scanning rather than by this code.
    ``test_index_build_makes_a_constant_number_of_filesystem_calls_per_file``
    now decides whether the indexer got worse *at the filesystem*, and that
    judgement is a function of the code alone.  A build that got slower purely
    on CPU reddens nothing here - measured in M8-T45, see the batch record.  What
    stays in this test is the one thing a timer can honestly decide: that a build
    finishes.
    """
    _package_tree(tmp_path, 100)
    start = time.perf_counter()
    index = LocalEvidenceIndex(tmp_path, max_files=1500)
    stats = index.stats()
    elapsed = time.perf_counter() - start
    assert stats["files_indexed"] == 1000
    assert stats["symbols_extracted"] == 1000
    # 120s is ~15x the slowest reading this shape has ever produced on this
    # machine.  It is deliberately not a regression detector - a build that
    # reopens every file should redden the call counter, not this line.
    assert elapsed < 120.0
    assert stats["last_build_ms"] < 120_000.0
    hits = index.search("handler_7_7")
    assert hits and hits[0].path == "pkg007/mod_7.py"


def test_index_build_makes_a_constant_number_of_filesystem_calls_per_file(tmp_path: Path) -> None:
    """Two scales, one ratio: the quantity has to stop being a stopwatch.

    Measured for this exact code: 250 files -> 5.232 calls per file, 1000 files
    -> 5.208, ratio 0.9954, and those per-file figures were identical across all
    six probe runs; the wall time of the very same 250-file build read 0.74,
    0.99, 1.27, 0.82, 1.91 and 0.94 seconds (the batch record's table).  The
    ceiling catches a constant that grew (more syscalls per file), the ratio
    catches syscalls growing *with* the file count; different failure modes, so
    both stay.  What neither sees is work that costs CPU and no syscalls: with
    an ``O(n^2 log n)`` scan on ``_refresh`` they moved by zero calls.
    """
    small = tmp_path / "small"
    big = tmp_path / "big"
    _package_tree(small, 25)
    _package_tree(big, 100)
    small_calls, small_files = _cold_build_counts(small)
    big_calls, big_files = _cold_build_counts(big)
    assert (small_files, big_files) == (250, 1000)
    # Every indexed body is opened exactly once per build...
    assert small_calls["open"] == small_files
    assert big_calls["open"] == big_files
    # ...and the tree is walked once per build, not once per file.
    assert small_calls["walk"] == 1
    assert big_calls["walk"] == 1
    per_small = sum(small_calls.values()) / small_files
    per_big = sum(big_calls.values()) / big_files
    assert per_big <= 7.0, (per_small, per_big)
    assert per_big / per_small <= 1.25, (per_small, per_big)


def test_the_call_counter_is_the_same_number_on_every_rebuild(tmp_path: Path) -> None:
    """Load-independence stated as an identity, not as a margin.

    The instrument is deterministic to the last call, which is exactly what the
    seconds reading never was; it also proves the counters reset between builds
    instead of accumulating.
    """
    tree = tmp_path / "tree"
    _package_tree(tree, 25)
    first, first_files = _cold_build_counts(tree)
    second, second_files = _cold_build_counts(tree)
    assert first == second, (first, second)
    assert (first_files, second_files) == (250, 250)
    assert sum(first.values()) > 250, "the build indexed nothing and the counter is vacuous"


def test_the_counter_can_see_quadratic_growth(tmp_path: Path) -> None:
    """A "no growth" reading is only evidence after growth has been witnessed.

    Every two-scale gate above would also pass with a counter that never fires,
    so the same harness is run over a deliberately quadratic rescan at 20 and 50
    files, with a linear one-file-one-stat loop as the control group.
    """
    small = tmp_path / "q_small"
    big = tmp_path / "q_big"
    _package_tree(small, 2)
    _package_tree(big, 5)

    def per_file(root: Path, quadratic: bool) -> float:
        files = sorted(root.rglob("*.py"))
        assert len(files) in (20, 50)

        def run() -> None:
            if quadratic:
                for _ in files:
                    for path in files:
                        path.stat()
            else:
                for path in files:
                    path.stat()

        calls = _count_filesystem_calls(run)
        return sum(calls.values()) / len(files)

    assert per_file(small, False) == per_file(big, False) == 1.0
    growth = per_file(big, True) / per_file(small, True)
    assert growth > 2.0, growth


def test_searching_a_built_index_touches_no_disk(tmp_path: Path) -> None:
    """Twenty queries must not cost twenty workspace scans.

    ``refresh_interval`` is pinned high on purpose: the claim under test is
    about retrieval, and letting the freshness tick fire inside the counted
    window would make this gate load-sensitive - the very defect M8-T45 is about.
    """
    tree = tmp_path / "tree"
    _package_tree(tree, 25)
    index = LocalEvidenceIndex(tree, max_files=1500, refresh_interval=3600.0)
    assert index.stats()["files_indexed"] == 250
    results: list[list[object]] = []

    def run() -> None:
        for offset in range(20):
            results.append(index.search(f"handler_{offset}_3", limit=20))

    calls = _count_filesystem_calls(run)
    assert calls == {"stat": 0, "open": 0, "is_symlink": 0, "iterdir": 0, "walk": 0}, calls
    # The window was not empty: the queries really matched.
    assert results and all(hits for hits in results), results
    assert len(results) == 20


def test_refreshing_an_unchanged_tree_reopens_no_file_body(tmp_path: Path) -> None:
    """The one-second tick has to stay cheap on a live workspace.

    ``_refresh`` reuses records whose (mtime, size) signature is unchanged, so a
    keystroke must not re-read 250 bodies.  The walk and the stats still happen
    - that is how change is detected - so this asserts exactly which half is free.
    """
    tree = tmp_path / "tree"
    _package_tree(tree, 25)
    index = LocalEvidenceIndex(tree, max_files=1500, refresh_interval=3600.0)
    assert index.stats()["files_indexed"] == 250
    calls = _count_filesystem_calls(index.refresh)
    assert calls["open"] == 0, calls
    assert calls["walk"] == 1, calls
    assert calls["stat"] >= 250, calls
    assert index.stats()["files_rebuilt"] == 0


def test_credential_stores_are_never_offered_as_evidence(tmp_path: Path) -> None:
    """A hit is a pointer, so pointing at ``secrets.json`` *is* the leak path.

    The index never copies file bodies into a result, which made it easy to
    believe it was safe: measured before the name rule existed, a query for
    "api key token secret" ranked ``secrets.json`` first with reason
    "filename+path+content+fresh" - the agent is told to go read it, and the
    ``SECRET_FILENAMES`` constant written to prevent that was referenced
    nowhere. So the guarantee is now by name, and this gate pins both
    directions: credential stores out, ordinary sources in.
    """
    sentinel = "SENTINEL-VALUE-9f3a7c2b"
    for name in (
        ".env",
        "secrets.json",
        "credentials.toml",
        "service-account.json",
        "deploy.pem",
        "nested/secrets.yaml",
    ):
        _write(tmp_path / name, "api_key = " + sentinel + "\ntoken: " + sentinel + "\n")
    # Ordinary code that mentions secrets must stay findable, or the rule is
    # just an over-broad substring filter.
    for name in ("app.py", "secrets_store.py", "test_credentials.py", "config.py", "README.md"):
        _write(tmp_path / name, "handler = 1\nvalue = '" + sentinel + "'\n")

    index = LocalEvidenceIndex(tmp_path)
    indexed = {rel for _path, rel in index._files()}

    assert indexed == {"app.py", "secrets_store.py", "test_credentials.py", "config.py", "README.md"}
    hits = index.search("api key token secret credentials", limit=20)
    paths = {hit.path for hit in hits}
    assert not (paths & {"secrets.json", "credentials.toml", "service-account.json", "nested/secrets.yaml"})
    assert sentinel not in str([hit.to_dict() for hit in hits])
    assert index.stats()["files_indexed"] == 5, index.stats()


def test_the_secret_name_rule_is_exact_not_a_substring() -> None:
    """The boundary of the filter, stated as data."""
    from minicc.agent.retrieval import is_secret_filename

    blocked = ["secrets.json", "Secrets.yaml", "credentials.toml", "service-account.json",
               "gcp-service-account-key.json", "deploy.pem", "tls.key", "my-api-key.json",
               ".env", ".env.production", ".ENV"]
    allowed = ["app.py", "secrets_store.py", "secret_rotation.py", "test_credentials.py",
               "credentials.rs", "secrets.go", "api_keys.py", "config.py", "README.md", "keys.md"]
    assert [name for name in blocked if not is_secret_filename(name)] == []
    assert [name for name in allowed if is_secret_filename(name)] == []


def _scorer_spy(index: LocalEvidenceIndex, query: str, *, limit: int = 20) -> tuple[list[str], list[object]]:
    """Run one search and return ``(records handed to the scorer, hits)``.

    ``search()`` looks the scorer up as a module attribute on every iteration, so
    wrapping ``retrieval._score_record`` is the only instrument that sees the
    *candidate set* rather than its output - a pre-filter or an early exit is
    invisible in the hit list but obvious here.  The uninstall is checked, because
    a leaked spy would silently re-define what the next test measures.
    """

    import minicc.agent.retrieval as retrieval

    original = retrieval._score_record
    seen: list[str] = []

    def spy(record, plan, now):
        seen.append(record.rel)
        return original(record, plan, now)

    retrieval._score_record = spy  # type: ignore[assignment]
    try:
        hits = index.search(query, limit=limit)
    finally:
        retrieval._score_record = original  # type: ignore[assignment]
    assert retrieval._score_record is original, "the scorer spy leaked a patch"
    return seen, hits


def test_every_search_scores_the_whole_table_regardless_of_the_answer(tmp_path: Path) -> None:
    """Retrieval cost is a function of the table, never of the query's luck.

    Measured here (120 records) and on a 300-record tree: a query that hits once,
    one that hits twenty and one that hits nothing all hand every record to the
    scorer, in table order; only the empty
    query scores zero, because ``plan.is_empty`` returns before the loop.  Wall
    time read 3.85ms per query at 300 synthetic records and 9-12ms over the 227
    records of this repository.  The truncation witness below is what turns the
    number from a constant the code prints into a measurement of the table.
    """
    tree = tmp_path / "tree"
    _package_tree(tree, 12)
    index = LocalEvidenceIndex(tree, max_files=1500, refresh_interval=3600.0)
    # The table is built lazily, so stats() has to run before it exists.
    indexed = int(index.stats()["files_indexed"])
    assert indexed == 120
    records = [record.rel for record in index._records]
    # The reported table and the walked table have to be one number.  Reading
    # ``index._records`` alone is self-referential - it is the very list the loop
    # walks - so a build that stored a truncated table while still reporting the
    # full count would slide through; probe N2 in the batch record is that shape.
    assert len(records) == indexed, (len(records), indexed)
    for query in ("handler_13_3", "handler_7", "no_such_term_at_all"):
        seen, _hits = _scorer_spy(index, query)
        assert seen == records, query
    empty_seen, empty_hits = _scorer_spy(index, "")
    assert empty_seen == [] and empty_hits == []
    original_records = index._records
    for keep in (60, 20, 5, 1):
        index._records = original_records[:keep]
        try:
            seen, _hits = _scorer_spy(index, "handler_7")
            assert len(seen) == keep, keep
        finally:
            index._records = original_records


def test_a_match_beyond_the_limit_is_still_offered(tmp_path: Path) -> None:
    """A ranking cap must never quietly become a scan cap.

    60 files, one unique term in the record that is *last* in scan order - the
    carrier is picked from ``index._records`` instead of assumed, so the gate does
    not depend on ``os.walk``'s order.  Measured: that file is the 60th record
    handed to the scorer and comes back with reason "content+fresh".  Slicing the
    loop to ``self._records[:limit]`` - the change that would make search cost
    constant - is *not* an invisible defect: measured here it reddened three
    pre-existing gates.  What those infer from the result set, this gate measures
    on the candidate set, and that quantity is the per-query CPU term M8-T45
    declared invisible to the filesystem counter.
    """
    _package_tree(tmp_path, 6)
    index = LocalEvidenceIndex(tmp_path, max_files=1500, refresh_interval=3600.0)
    assert index.stats()["files_indexed"] == 60
    last = index._records[-1].rel
    target = tmp_path / last
    target.write_text(target.read_text(encoding="utf-8") + "\n# UNSEENDEEPTERM\n", encoding="utf-8")
    index.refresh()
    assert index._records[-1].rel == last, "the scan order moved under the test"
    seen, hits = _scorer_spy(index, "UNSEENDEEPTERM", limit=8)
    assert seen.index(last) + 1 == 60
    assert [hit.path for hit in hits] == [last]
    assert hits[0].reason == "content+fresh"


def test_freshness_alone_never_fabricates_a_hit(tmp_path: Path) -> None:
    """A brand-new file sharing no term is still not evidence.

    ``_score_record`` adds the mtime bonus *after* the "not matched" guard
    (retrieval.py:310), and this pins that order by behaviour: ``src/alpha.py`` is
    touched this very second, is still handed to the scorer, and is not returned
    for a query it shares nothing with.  Replacing that guard with ``if False``
    made the fresh file come back as real-looking evidence; the worker would then
    be told to go read it.  Mutation reading in the batch record.

    Running that mutation is also what exposed the unfireable assertion in
    ``test_stopwords_are_removed_from_queries``, which claimed this exact
    contract and could not see the hit.
    """
    alpha = _write(tmp_path / "src" / "alpha.py", "alpha beta gamma\n")
    _write(tmp_path / "src" / "widget.py", "def widget_factory():\n    return 1\n")
    now = time.time()
    os.utime(alpha, (now, now))
    index = LocalEvidenceIndex(tmp_path, refresh_interval=3600.0)
    seen, hits = _scorer_spy(index, "widget", limit=20)
    assert "src/alpha.py" in seen, "the guard has to be reached, not skipped by pre-filtering"
    assert [hit.path for hit in hits] == ["src/widget.py"]
    assert all("alpha" not in hit.path for hit in hits)


def test_resident_guidance_is_a_last_resort_not_a_top_hit(tmp_path: Path) -> None:
    """The one documented exception, and the half that makes it safe.

    A guidance file with zero term overlap still gets the constant resident boost:
    measured ``AGENTS.md`` at 5.0 with reason "guidance-resident+fresh", which is
    *more* than a genuine single-term content match (4.0, see the deep-match gate
    above).  That stays harmless only because ``search()`` falls back to resident
    guidance when the real list is empty - so with one genuine match in the
    workspace the guidance file is dropped, not ranked second.  Neither direction
    was tested at all before M8-T48.
    """
    _write(tmp_path / "AGENTS.md", "# 项目约定\n\n保持简短。\n")
    _write(tmp_path / "src" / "widget.py", "def widget_factory():\n    return 1\n")
    index = LocalEvidenceIndex(tmp_path, refresh_interval=3600.0)
    matched_seen, matched_hits = _scorer_spy(index, "widget", limit=20)
    assert len(matched_seen) == 2
    assert [hit.path for hit in matched_hits] == ["src/widget.py"]
    stray_seen, stray_hits = _scorer_spy(index, "zzzqqx", limit=20)
    assert len(stray_seen) == 2
    assert [hit.path for hit in stray_hits] == ["AGENTS.md"]
    assert stray_hits[0].reason == "guidance-resident+fresh"
    assert 4.9 < stray_hits[0].score <= 5.0
