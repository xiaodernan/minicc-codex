"""M8-T568 — 路径集合与树集合相等：两种读者都只能看到同一批源码。

一个脚本被两种读者用：只要路径的（audience 列表、哪些文件被列过）与要树的
（build/census）。两者必须走同一条路径串；否则「某个读者不想解析」随时会退化成
「那个读者列举的不是这批源码」——今天的同源只是恰好，没有任何门钉住它。
第五百二十四批 §7 第 4 位点名了这笔账（「没有门钉住路径集合与树集合相等」）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "impacted_tests.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("impacted_tests_paths_trees", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The module carries dataclasses under ``from __future__ import annotations``;
    # annotations resolve through sys.modules, so register before exec.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_home_enumerates_exactly_the_listed_sources() -> None:
    module = _load_script()
    assert hasattr(module, "_listed_sources"), (
        "the one home for enumerating the sources is gone; every other reader "
        "now spells the concatenation itself"
    )
    listings = module._listings()
    sources = module._listed_sources(listings)
    assert sources == [*listings.modules.values(), *listings.tests], (
        "the path home and the listing drifted: the path reader would walk a "
        "different set than the tree reader parses"
    )


def test_every_listed_source_is_parsed_exactly_once() -> None:
    module = _load_script()
    listings = module._listings()
    trees = module._read_trees(listings)
    paths = module._listed_sources(listings)
    # The snapshot read each listed source exactly once (dict key per source):
    # no list/test silently dropped, no path doubled.
    assert len(trees) == len(paths)
    assert set(trees) == set(paths)
    assert len(paths) == len(set(paths))


def test_the_two_snapshots_agree_with_each_other() -> None:
    module = _load_script()
    first = module._listings()
    second = module._listings()
    for field in ("modules", "tests", "scripts", "workflows"):
        a = getattr(first, field)
        b = getattr(second, field)
        assert a == b, (
            f"two listings of {field} disagree; a reader that caches one and "
            "trusts the other is answering a different question"
        )


def test_a_reader_that_wants_paths_gets_the_same_set() -> None:
    """The future reader this batch is for: paths without trees."""
    module = _load_script()
    listings = module._listings()
    assert set(module._listed_sources(listings)) == set(
        list(listings.modules.values()) + list(listings.tests)
    )
