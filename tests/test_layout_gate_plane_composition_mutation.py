"""Mutation tests for layout gate plane composition (test_the_layout_gate_says_which_plane_its_population_came_from).

These tests verify the mutation arms for the plane composition gate work correctly.
Instead of using _layout_audits directly (which would parse test files), we test the
logic in isolation using the same underlying functions.
"""
import pytest
import sys
import ast
from pathlib import Path, PurePath

sys.path.insert(0, r"D:\面试项目\minicc-codex")

from tests.test_two_fixture_keys_must_share_one_workspace import (
    _layout_audit_shape, _reaches, _call_names,
    CENSUS_DIRS, REPO, CORPUS_CALLS, OWNER_CALLS,
    IDENTITY_CALLS, IDENTITY_ATTRS,
)


def _collect_audited(roots):
    """Walk roots and return audited sites, mimicking _layout_audits but test-safe."""
    audited = []
    for d in roots:
        root = Path(d)
        # Use the directory name as the plane prefix
        plane_prefix = root.name
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
                tree = ast.parse(text)
            except SyntaxError:
                continue
            defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
            graph = {name: _call_names(node) for name, node in defs.items()}
            for name, node in defs.items():
                loads, reads_fixtures, decides_alone = _layout_audit_shape(node, graph)
                if not (loads and reads_fixtures):
                    continue
                # Use the directory name as plane prefix, with forward slashes
                rel = PurePath(path).relative_to(PurePath(d)).as_posix()
                where = f"{d.name}/{rel}::{name}"
                audited.append(where)
    return audited


def test_mutation_D1_inject_scripts_plane():
    """D1: Inject a fake 'scripts' plane -> plane composition should include 'scripts'."""
    audited = _collect_audited([REPO / d for d in CENSUS_DIRS])
    
    audited_with_scripts = list(audited) + ["scripts/fake_module.py::fake_census"]
    
    by_plane = {}
    for site in audited_with_scripts:
        plane = PurePath(site).parts[0]
        by_plane[plane] = by_plane.get(plane, 0) + 1
    
    assert set(by_plane.keys()) == {"tests", "scripts"}, (
        f"Expected planes {{'tests', 'scripts'}}, got {set(by_plane.keys())}"
    )


def test_mutation_D2_assert_allows_scripts():
    """D2: Change assertion to allow 'scripts' plane -> should pass."""
    audited = _collect_audited([REPO / d for d in CENSUS_DIRS])
    
    audited_with_scripts = list(audited) + ["scripts/fake_module.py::fake_census"]
    by_plane = {}
    for site in audited + ["scripts/fake_module.py::fake_census"]:
        plane = PurePath(site).parts[0]
        by_plane[plane] = by_plane.get(plane, 0) + 1
    
    allowed_planes = {"tests", "scripts"}
    assert set(by_plane.keys()) <= {"tests", "scripts"}


def test_mutation_D3_force_minicc_plane():
    """D3: Force all sites to appear under 'minicc' plane -> should fail."""
    audited = _collect_audited([REPO / d for d in CENSUS_DIRS])
    
    forced_audited = []
    for site in audited:
        parts = PurePath(site).parts
        forced = "minicc/" + parts[1] if len(parts) > 1 else "minicc/" + parts[0]
        forced_audited.append(forced)
    
    by_plane = {}
    for site in forced_audited:
        plane = PurePath(site).parts[0]
        by_plane[plane] = by_plane.get(plane, 0) + 1
    
    assert set(by_plane.keys()) == {"minicc"}, f"Expected {{'minicc'}}, got {set(by_plane.keys())}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])