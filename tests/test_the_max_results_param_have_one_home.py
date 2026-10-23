"""The web_search result-cap wire name must have exactly one home."""

from __future__ import annotations

import pathlib

from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.web import MAX_RESULTS_PARAM

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_constant_is_the_wire_name():
    assert MAX_RESULTS_PARAM == "max_results"


def test_schema_declaration_uses_the_constant(tmp_path):
    registry = build_registry(Editor(tmp_path))
    spec = registry.spec("web_search")
    names = [param.name for param in spec.params]
    assert MAX_RESULTS_PARAM in names


def test_reader_uses_the_constant():
    source = (REPO / "minicc" / "tools" / "web.py").read_text(encoding="utf-8")
    assert "args.get(MAX_RESULTS_PARAM, 5)" in source


def test_census_exactly_one_literal_in_the_repo():
    hits = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if '"max_results"' in line:
                hits.append((path.relative_to(REPO).as_posix(), lineno))
    assert len(hits) == 1, hits
    path, lineno = hits[0]
    assert path == "minicc/tools/web.py"
    source = (REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 5):lineno + 1])
    assert "MAX_RESULTS_PARAM" in window, window


def test_schema_declaration_site_uses_the_constant():
    init = (REPO / "minicc" / "tools" / "__init__.py").read_text(encoding="utf-8")
    assert "Param(MAX_RESULTS_PARAM," in init
