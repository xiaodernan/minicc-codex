"""Reverse-control cells for the web asset freshness gate (M8-T262).

``test_web_assets_are_fresh.py`` shipped with a control cell that plants a fake
manifest so P1 and P2 cannot go green by going blind - but nothing locked that in at
the gate level, so a later edit could blunt ``_referenced_names`` or ``_disk_names``
and CI would not notice.

Measured before this file existed: blinding ``_referenced_names`` to return an empty
set reddens 2 cells; blinding ``_disk_names`` likewise reddens 2. The predicates were
already load-bearing - what was missing was the table entry that keeps them so.

P3 is a different situation and this file does not pretend otherwise. Its real guard
is ``assert proc.returncode == 0`` against the build script's own ``--check``; the
second assertion (``"stale" not in output``) is redundant - measured: blunting it
reddens nothing. The load-bearing reverse control is therefore "make the tree stale
and the cell must fail", which is the first cell below. It needs the build toolchain,
so it carries the same skip the gate itself carries, and it is deliberately **not**
wired into the gate table: an arm that expects a cell which CI skips would redden the
Python plane for a missing toolchain rather than for stale assets.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_web_assets_are_fresh import (  # noqa: E402
    ASSETS,
    MANIFEST,
    STYLE_SOURCE,
    _build_toolchain_ready,
    _disk_names,
    _referenced_names,
    test_the_sources_build_to_the_bundles_the_manifest_names,
)

needs_build = pytest.mark.skipif(_build_toolchain_ready() is not None,
                                 reason=_build_toolchain_ready() or "")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _disk_names_of(directory: Path) -> set[str]:
    return {p.name for p in directory.iterdir() if p.is_file()}


def _referenced_names_of(manifest: dict[str, str]) -> set[str]:
    return {asset.rsplit("/", 1)[-1] for asset in manifest.values()}


# --- the load-bearing P3 reverse control --------------------------------


@needs_build
def test_editing_a_real_source_makes_the_p3_cell_go_red() -> None:
    """Make the tree stale; the gate's own P3 cell must fail.

    This is the control the gate cannot make for itself: its second P3 assertion is
    redundant (measured - blunting it reddens nothing), and its first one only ever
    passes while the assets are fresh. Edit a real rule - not a comment, because
    esbuild's minify strips comments - and the cell must raise.
    """
    pristine = STYLE_SOURCE.read_bytes()
    before = _sha(STYLE_SOURCE)
    try:
        STYLE_SOURCE.write_text(
            STYLE_SOURCE.read_text(encoding="utf-8")
            + "\n.m8-t261-probe { color: #123456; }\n",
            encoding="utf-8",
        )
        with pytest.raises(AssertionError) as raised:
            test_the_sources_build_to_the_bundles_the_manifest_names()
        assert "stale" in str(raised.value).lower(), (
            f"the P3 cell failed for some other reason: {raised.value}"
        )
    finally:
        STYLE_SOURCE.write_bytes(pristine)

    assert _sha(STYLE_SOURCE) == before, (
        "web/styles.css was not restored byte-exactly after the staleness probe"
    )


# --- predicate-level reverse controls (no toolchain needed) ---------------


def test_a_missing_bundle_is_seen_by_the_p1_predicate() -> None:
    """Blinding ``_referenced_names`` to an empty set must be caught here."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    names = sorted(_referenced_names_of(manifest))
    assert names, "the manifest names no bundles at all"
    planted = dict(manifest)
    planted["/planted.js"] = "/assets/definitely-not-here.js"
    missing = _referenced_names(planted) - _disk_names()
    assert missing == {"definitely-not-here.js"}, (
        f"P1's predicate did not see the planted missing bundle, saw {sorted(missing)}"
    )


def test_an_orphan_bundle_is_seen_by_the_p2_predicate() -> None:
    """Blinding ``_disk_names`` to an empty set must be caught here."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert "/styles.css" in manifest, (
        "the manifest no longer has a styles entry to drop, so this control cannot "
        "plant an orphan - rewrite it around whatever the manifest holds now"
    )
    dropped = dict(manifest)
    dropped.pop("/styles.css")
    orphans = _disk_names() - _referenced_names(dropped)
    assert len(orphans) == 1, (
        f"P2's predicate should see exactly the dropped bundle, saw {sorted(orphans)}"
    )
    assert next(iter(orphans)).startswith("styles."), (
        f"the dropped entry should orphan the styles bundle, got {sorted(orphans)}"
    )


def test_the_manifest_and_disk_still_agree() -> None:
    """The shipped state both predicates are supposed to report clean."""
    assert _referenced_names() - _disk_names() == set(), (
        "the manifest names bundles that are not on disk"
    )
    assert _disk_names() - _referenced_names() == set(), (
        "web/assets holds bundles the manifest never references"
    )


def test_the_manifest_still_names_at_least_three_bundles() -> None:
    """A manifest naming nothing would make P1 vacuously true."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(manifest) >= 3, f"the manifest only names {len(manifest)} bundles"


# --- the predicates are imported, not copied ------------------------------


def test_this_file_carries_no_private_copy_of_the_predicates() -> None:
    """Read by AST, not by substring: this file's docstring names what it borrows."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(tree)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for borrowed in ("_referenced_names", "_disk_names", "_manifest"):
        assert borrowed not in defined, (
            f"{borrowed} is defined here instead of being imported - this file would "
            "keep passing while the gate it names is broken"
        )
    assert _referenced_names is not None and _disk_names is not None


def test_the_predicates_here_are_the_gate_s_objects() -> None:
    """Identity check, so a private re-export cannot slip in beside the import."""
    from test_web_assets_are_fresh import _disk_names as disk, _referenced_names as ref

    assert _referenced_names is ref and _disk_names is disk
    assert MANIFEST.is_file() and ASSETS.is_dir()
