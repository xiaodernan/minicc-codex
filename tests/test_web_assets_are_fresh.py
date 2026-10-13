"""The shipped web bundles must be what the current sources build (M8-T201).

Motivation was a real CI red, not a hypothetical: ``ef8623e`` changed
``web/styles.css`` but never re-ran the build, so ``npm run check:web`` went red on
main - the manifest still named ``styles.71ada7d03ff2361a.css`` while the source
now hashes to ``styles.da950694dbb1a284.css``. Nothing local caught it; only the
CI job did, after the push.

Three cells, in the order a reader meets them:

* P1 - every bundle the manifest names must exist on disk.
* P2 - no bundle on disk may be absent from the manifest (an orphan is a
  leftover from a build that no longer describes the sources).
* P3 - the sources must actually *build to* the named bundles. Only this one
  catches content drift, because the hash covers esbuild's minified output;
  reproducing that in Python is not possible, so the cell shells out to the
  build script's own ``--check``. It skips when node is not on PATH, the same way
  the webauth gates skip on a non-POSIX volume.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "web"
MANIFEST = WEB / "asset-manifest.json"
ASSETS = WEB / "assets"
BUILD_SCRIPT = REPO / "scripts" / "build-web.mjs"

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not on PATH")


def _manifest() -> dict[str, str]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _referenced_names(manifest: dict[str, str] | None = None) -> set[str]:
    manifest = _manifest() if manifest is None else manifest
    return {asset.rsplit("/", 1)[-1] for asset in manifest.values()}


def _disk_names() -> set[str]:
    return {p.name for p in ASSETS.iterdir() if p.is_file()}


# --- P1: every named bundle exists ---------------------------------------


def test_every_bundle_the_manifest_names_is_on_disk() -> None:
    """P1: the manifest is a promise about files that exist."""
    missing = sorted(_referenced_names() - _disk_names())
    assert missing == [], (
        f"asset-manifest.json names bundles that do not exist: {missing}"
    )


def test_the_manifest_has_at_least_one_entry() -> None:
    """A manifest that names nothing would make P1 vacuously true."""
    manifest = _manifest()
    assert len(manifest) >= 3, f"the manifest only names {len(manifest)} bundles: {manifest}"


# --- P2: no orphan bundles ------------------------------------------------


def test_no_bundle_on_disk_is_absent_from_the_manifest() -> None:
    """P2: an orphan is a build that no longer describes the sources."""
    orphans = sorted(_disk_names() - _referenced_names())
    assert orphans == [], (
        f"web/assets holds bundles the manifest never references: {orphans}"
    )


def test_a_hardcoded_manifest_would_not_satisfy_the_two_cells() -> None:
    """Control for P1+P2: a manifest pointing at one existing and one missing name.

    Without this, both cells above could be green because the predicate went
    blind - which is exactly how a stale hash stayed invisible until CI.
    """
    manifest = _manifest()
    names = sorted(_referenced_names(manifest))
    assert names, "the manifest names no bundles at all"
    # Shape A: the manifest promises a bundle that is not on disk.
    planted = dict(manifest)
    planted["/planted.js"] = f"/assets/definitely-not-here-{names[0]}"
    assert sorted(_referenced_names(planted) - _disk_names()) == [
        f"definitely-not-here-{names[0]}"
    ], "P1's predicate does not see a missing bundle"
    # Shape B: a bundle is on disk but the manifest dropped its entry, so
    # its file is an orphan. Building from that manifest would prune nothing
    # and ship a bundle the app never loads.
    dropped = dict(manifest)
    dropped.pop("/styles.css", None)
    orphans = _disk_names() - _referenced_names(dropped)
    assert len(orphans) == 1, (
        f"P2's predicate should see exactly the dropped bundle, saw {sorted(orphans)}"
    )
    assert next(iter(orphans)).startswith("styles."), (
        f"the dropped entry should orphan the styles bundle, got {orphans}"
    )


# --- P3: the sources build to the named bundles ---------------------------


@needs_node
def test_the_sources_build_to_the_bundles_the_manifest_names() -> None:
    """P3: the only cell that catches content drift.

    ``ef8623e`` edited ``styles.css`` and left the old bundle in place; the
    manifest names matched the disk names, so P1 and P2 both stayed green. The
    build script's own ``--check`` recomputes esbuild's minified output and its
    hash, so it is the instrument that sees the drift.
    """
    proc = subprocess.run(
        [NODE or "node", str(BUILD_SCRIPT), "--check"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, (
        "web assets are stale - run `npm run build:web` (or `node "
        f"scripts/build-web.mjs`):\n{output}"
    )
    assert "stale" not in output.lower(), (
        f"the build reported staleness without failing:\n{output}"
    )
