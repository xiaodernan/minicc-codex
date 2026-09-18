"""Behavioral coverage for explainable, bounded dependency impact."""
from pathlib import Path

import pytest

from minicc.impact import analyze_change_impact


def sources(root: Path, mapping: dict[str, str]):
    for name, content in mapping.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def rows(result, key="impacted_files"):
    return {row["path"]: row for row in result[key]}


def test_python_transitive_chain_and_cycle_are_explained(tmp_path):
    sources(tmp_path, {
        "app/core.py": "from . import service\n",
        "app/service.py": "from .core import process\n",
        "tests/test_service.py": "from app.service import serve\n",
        "tests/test_unrelated.py": "text = 'from app.core import process'\n# import app.core\n",
    })
    result = analyze_change_impact(tmp_path, ["app/core.py"])
    assert set(rows(result)) == {"app/service.py", "tests/test_service.py"}
    assert rows(result)["tests/test_service.py"]["chain"] == ["app/core.py", "app/service.py", "tests/test_service.py"]
    assert list(rows(result, "recommended_tests")) == ["tests/test_service.py"]
    assert result["stats"]["edges"] == 3


def test_src_layout_package_initializers_and_deleted_modules(tmp_path):
    sources(tmp_path, {
        "src/pkg/__init__.py": "",
        "src/pkg/service.py": "from .deleted import run\n",
        "tests/test_service.py": "from pkg import service as api\n",
    })
    deleted = analyze_change_impact(tmp_path, ["src/pkg/deleted.py"])
    assert rows(deleted)["tests/test_service.py"]["distance"] == 2
    package = analyze_change_impact(tmp_path, ["src/pkg/__init__.py"])
    assert "tests/test_service.py" in rows(package)


def test_js_ts_reexports_require_index_and_emitted_js_resolution(tmp_path):
    sources(tmp_path, {
        "src/core.ts": "export const answer = 42;",
        "src/api/index.ts": "export {answer} from '../core.js';",
        "src/consumer.js": "import { answer } from './api';",
        "tests/core.spec.ts": "const api = require('../src/consumer');",
        "src/noise.js": "const s = \"import x from './core'\"; /* import x from './core' */ // import './core'\n",
    })
    result = analyze_change_impact(tmp_path, ["src/core.ts"])
    assert set(rows(result)) == {"src/api/index.ts", "src/consumer.js", "tests/core.spec.ts"}
    assert rows(result, "recommended_tests")["tests/core.spec.ts"]["chain"] == ["src/core.ts", "src/api/index.ts", "src/consumer.js", "tests/core.spec.ts"]


def test_incremental_cache_invalidates_changes_and_deletions(tmp_path):
    sources(tmp_path, {"core.py": "", "use.py": "import core\n", "other.py": ""})
    cold = analyze_change_impact(tmp_path, ["core.py"])
    warm = analyze_change_impact(tmp_path, ["core.py"])
    assert cold["stats"]["cache_hits"] == 0
    assert warm["stats"]["cache_hits"] == 3
    (tmp_path / "use.py").write_text("import other\n")
    assert not rows(analyze_change_impact(tmp_path, ["core.py"]))
    (tmp_path / "use.py").unlink()
    assert analyze_change_impact(tmp_path, ["other.py"])["stats"]["indexed_files"] == 2


def test_output_limit_keeps_true_totals_and_shortest_chain(tmp_path):
    sources(tmp_path, {"core.py": "", "a.py": "import core", "b.py": "import a\nimport core", "tests/test_all.py": "import b"})
    result = analyze_change_impact(tmp_path, ["core.py"], limit=1)
    assert result["truncated"]
    assert len(result["impacted_files"]) == 1
    assert result["stats"]["impacted_files"] == 3
    assert result["recommended_tests"][0]["chain"] == ["core.py", "b.py", "tests/test_all.py"]


def test_ignored_directories_do_not_consume_scan_budget(tmp_path):
    sources(tmp_path, {".cache/hidden.py": "bad syntax (", "node_modules/untrusted.py": "bad syntax (", "core.py": "", "use.py": "import core"})
    result = analyze_change_impact(tmp_path, ["core.py"], max_files=2)
    assert result["stats"]["indexed_files"] == 2
    assert not result["truncated"]
    assert not result["warnings"]


def test_parse_dynamic_and_scan_limits_are_honest(tmp_path):
    sources(tmp_path, {"a.py": "bad syntax (", "b.py": "import importlib\nimportlib.import_module(name)", "c.js": "import(target); require(target); import('./a.js');", "d.py": ""})
    result = analyze_change_impact(tmp_path, ["a.py"])
    assert result["analysis_incomplete"]
    assert result["warnings"][0]["path"] == "a.py"
    assert result["stats"]["dynamic_imports"] == 4
    bounded = analyze_change_impact(tmp_path, ["a.py"], max_files=2)
    assert bounded["truncated"]
    assert bounded["stats"]["scanned_files"] == 2


@pytest.mark.parametrize("paths", [["../outside.py"], ["/etc/app.py"], ["C:\\outside.py"], ["a\n.py"], [123], "a.py"])
def test_rejects_paths_outside_workspace_or_invalid_payload(tmp_path, paths):
    with pytest.raises(ValueError):
        analyze_change_impact(tmp_path, paths)


def test_changed_test_recommended_and_path_separator_normalized(tmp_path):
    sources(tmp_path, {"tests/test_app.py": ""})
    result = analyze_change_impact(tmp_path, ["tests\\test_app.py"])
    assert result["changed_paths"] == ["tests/test_app.py"]
    assert result["recommended_tests"][0]["reason"] == "changed test"
    assert result["recommended_tests"][0]["distance"] == 0


def test_large_source_and_symlinks_are_not_read(tmp_path):
    sources(tmp_path, {"huge.py": "x" * 400_001, "core.py": ""})
    result = analyze_change_impact(tmp_path, ["core.py"])
    assert result["stats"]["skipped_files"] == 1
    assert result["analysis_incomplete"]
    assert result["warnings"][0]["reason"] == "source exceeds 400 KB"


def test_python_from_parent_package_does_not_invent_module_relationship(tmp_path):
    sources(tmp_path, {"pkg/base.py": "", "pkg/other.py": "", "tests/test_other.py": "from pkg.other import Thing"})
    assert not rows(analyze_change_impact(tmp_path, ["pkg/base.py"]))


def test_multiple_changed_roots_choose_shortest_deterministic_explanation(tmp_path):
    sources(tmp_path, {"a.py": "", "b.py": "import a", "c.py": "import b", "tests/test_c.py": "import c"})
    result = analyze_change_impact(tmp_path, ["a.py", "c.py"])
    assert result["recommended_tests"][0]["chain"] == ["c.py", "tests/test_c.py"]


def test_production_test_helper_is_not_recommended_as_a_test(tmp_path):
    sources(tmp_path, {"app/test_selection.py": "def relevant_tests(): pass", "src/test_api.py": "from app import test_selection\ndef test_real(): pass"})
    result = analyze_change_impact(tmp_path, ["app/test_selection.py"])
    assert list(rows(result, "recommended_tests")) == ["src/test_api.py"]


def test_deep_dependency_explanation_is_bounded_with_both_endpoints(tmp_path):
    sources(tmp_path, {**{f"module{index}.py": f"import module{index - 1}" if index else "" for index in range(50)}, "tests/test_deep.py": "import module49"})
    result = analyze_change_impact(tmp_path, ["module0.py"])
    recommendation = result["recommended_tests"][0]
    assert recommendation["distance"] == 50
    assert len(recommendation["chain"]) == 32
    assert recommendation["chain_truncated"]
    assert recommendation["chain"][0] == "module0.py"
    assert recommendation["chain"][-1] == "tests/test_deep.py"
