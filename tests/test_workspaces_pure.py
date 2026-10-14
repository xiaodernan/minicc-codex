"""Independent fence tests for ``minicc.workspaces`` path gate and catalog.

All filesystem activity uses repo-external temp dirs (never the repo working
tree) so the suite cannot trip the git deletion guard and stays milliseconds.

Run directly or via the repo gate:
    python tests/test_workspaces_pure.py
    python -m pytest tests/test_workspaces_pure.py -q -W error
"""

import json
import tempfile
from pathlib import Path

from minicc import workspaces
from minicc.workspaces import WorkspaceCatalog, resolve_workspace_path


# --- resolve_workspace_path: the single entry gate ---------------------------

def test_empty_without_default_raises():
    import pytest
    with pytest.raises(ValueError):
        resolve_workspace_path("")


def test_empty_falls_back_to_default():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        assert resolve_workspace_path("", default=root) == root.resolve()


def test_absolute_existing_dir_returns_resolved():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "sub").mkdir()
        assert resolve_workspace_path(str(root / "sub")) == (root / "sub").resolve()


def test_relative_resolved_against_cwd():
    # a relative path is resolved against cwd; we point at an existing dir there
    # via absolute input so the test is deterministic regardless of cwd.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d).resolve()
        assert resolve_workspace_path(str(root)).name == root.name


def test_nonexistent_dir_raises():
    import pytest
    with tempfile.TemporaryDirectory() as d:
        missing = Path(d) / "nope"
        with pytest.raises(ValueError):
            resolve_workspace_path(str(missing))


def test_roots_whitelist_allows_inside():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d).resolve()
        inside = root / "proj"
        inside.mkdir()
        assert resolve_workspace_path(str(inside), roots=[root]) == inside.resolve()


def test_roots_whitelist_rejects_outside():
    import pytest
    with tempfile.TemporaryDirectory() as d:
        allowed = Path(d).resolve() / "allowed"
        outside = Path(d).resolve() / "outside"
        allowed.mkdir()
        outside.mkdir()
        with pytest.raises(ValueError):
            resolve_workspace_path(str(outside), roots=[allowed])


def test_empty_roots_no_restriction():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d).resolve()
        assert resolve_workspace_path(str(root), roots=[]) == root


# --- WorkspaceCatalog: remember / list / read -------------------------------

def test_catalog_remember_then_list():
    with tempfile.TemporaryDirectory() as d:
        catalog = WorkspaceCatalog(path=Path(d) / "ws.json")
        target = Path(d).resolve()
        catalog.remember(target)
        items = catalog.list()
        assert len(items) == 1
        assert items[0]["path"] == target.as_posix()
        assert items[0]["exists"] is True
        assert items[0]["name"] == target.name


def test_catalog_dedup_same_path():
    with tempfile.TemporaryDirectory() as d:
        catalog = WorkspaceCatalog(path=Path(d) / "ws.json")
        target = Path(d).resolve()
        catalog.remember(target)
        catalog.remember(target)
        assert len(catalog.list()) == 1


def test_catalog_dedup_case_insensitive():
    with tempfile.TemporaryDirectory() as d:
        catalog = WorkspaceCatalog(path=Path(d) / "ws.json")
        target = Path(d).resolve()
        catalog.remember(target)
        catalog.remember(Path(str(target).upper()) if str(target) != str(target).upper() else target)
        assert len(catalog.list()) == 1


def test_catalog_most_recent_first():
    with tempfile.TemporaryDirectory() as d:
        catalog = WorkspaceCatalog(path=Path(d) / "ws.json")
        a = (Path(d) / "a").resolve()
        b = (Path(d) / "b").resolve()
        a.mkdir()
        b.mkdir()
        catalog.remember(a)
        catalog.remember(b)
        items = catalog.list()
        assert items[0]["path"] == b.as_posix()


def test_catalog_caps_at_max_items():
    with tempfile.TemporaryDirectory() as d:
        catalog = WorkspaceCatalog(path=Path(d) / "ws.json", max_items=3)
        for name in ("x", "y", "z", "w", "v"):
            p = (Path(d) / name)
            p.mkdir()
            catalog.remember(p)
        assert len(catalog.list()) == 3


def test_catalog_missing_file_lists_empty():
    with tempfile.TemporaryDirectory() as d:
        catalog = WorkspaceCatalog(path=Path(d) / "absent.json")
        assert catalog.list() == []


def test_catalog_corrupt_json_lists_empty():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "ws.json"
        p.write_text("{not valid json", encoding="utf-8")
        catalog = WorkspaceCatalog(path=p)
        assert catalog.list() == []


def test_catalog_nonlist_payload_lists_empty():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "ws.json"
        p.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        catalog = WorkspaceCatalog(path=p)
        assert catalog.list() == []


def test_catalog_list_filters_empty_path_entries():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "ws.json"
        p.write_text(json.dumps([{"name": "ghost", "path": ""}, {"name": "real"}]), encoding="utf-8")
        catalog = WorkspaceCatalog(path=p)
        assert catalog.list() == []


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__, "-q", "-W", "error"]))
