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
    # "the" must not pull in notes.md ("the theory of everything").
    assert all("notes.md" != hit.path for hit in noisy)


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


def test_thousand_file_index_builds_under_three_seconds(tmp_path: Path) -> None:
    for package in range(100):
        directory = tmp_path / f"pkg{package:03d}"
        for number in range(10):
            _write(directory / f"mod_{number}.py", f"def handler_{package}_{number}(payload):\n    return payload\n")
    start = time.perf_counter()
    index = LocalEvidenceIndex(tmp_path, max_files=1500)
    stats = index.stats()
    elapsed = time.perf_counter() - start
    assert stats["files_indexed"] == 1000
    assert stats["symbols_extracted"] == 1000
    assert elapsed < 3.0
    assert stats["last_build_ms"] < 3000.0
    hits = index.search("handler_7_7")
    assert hits and hits[0].path == "pkg007/mod_7.py"
