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
  build script's own ``--check``.

  Two skip reasons, because they are different situations: the Python test jobs do
  not ``npm ci``, so ``node`` resolves while ``esbuild`` does not. Treating that as
  a failure would redden CI for a missing toolchain, not for stale assets - the
  exact opposite of what this gate is for. The static cells P1/P2 need neither and
  still run everywhere; ``check:web`` in the JavaScript job owns P3 in CI.

* P4 - a CRLF checkout is not a stale build. The gate compares text files; on
  Windows (``core.autocrlf=true``) every file is CRLF while esbuild emits LF, so
  P3 was permanently red on the developer platform for a checkout artifact.
  P4 builds its own CRLF plane, so the cell means the same thing on every host.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "web"
MANIFEST = WEB / "asset-manifest.json"
ASSETS = WEB / "assets"
STYLE_SOURCE = WEB / "styles.css"
BUILD_SCRIPT = REPO / "scripts" / "build-web.mjs"

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

NODE = shutil.which("node")
ESBUILD = (REPO / "node_modules" / "esbuild").is_dir()


def _build_toolchain_ready() -> str | None:
    """``None`` when the build can run, otherwise the reason it cannot."""
    if NODE is None:
        return "node is not on PATH"
    if not ESBUILD:
        return "node_modules/esbuild is not installed (run `npm ci`)"
    return None


needs_build = pytest.mark.skipif(_build_toolchain_ready() is not None,
                                 reason=_build_toolchain_ready() or "")


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


@needs_build
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


# --- P4: a CRLF checkout is not a stale build -----------------------------


def _crlf_plane() -> Path:
    """A copy of the web sources and bundles with every text file in CRLF.

    It lives under ``node_modules/.cache`` on purpose: Node's resolver walks up
    ancestor directories, so the copied build script finds the repository's own
    ``esbuild`` without a junction (whose removal can recurse into the target).
    """
    cache = REPO / "node_modules" / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    plane = Path(tempfile.mkdtemp(prefix="crlf-plane-", dir=str(cache)))
    (plane / "scripts").mkdir()
    (plane / "web").mkdir()
    shutil.copytree(WEB / "src", plane / "web" / "src")
    shutil.copytree(ASSETS, plane / "web" / "assets")
    for name in ("app.js", "game.js", "styles.css", "asset-manifest.json"):
        shutil.copy2(WEB / name, plane / "web" / name)
    shutil.copy2(BUILD_SCRIPT, plane / "scripts" / "build-web.mjs")
    for path in list((plane / "web").rglob("*")) + [plane / "scripts" / "build-web.mjs"]:
        if path.is_file():
            raw = path.read_bytes()
            if b"\x00" not in raw:
                path.write_bytes(raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    return plane


def _run_build_check(plane: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [NODE or "node", str(plane / "scripts" / "build-web.mjs"), "--check"],
        cwd=str(plane),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


@needs_build
def test_a_crlf_checkout_is_not_a_stale_build() -> None:
    """P4: line endings come from the checkout, not from the sources.

    Measured on Windows before the normalisation: six of six files were reported
    stale while HEAD's committed bundles were byte-identical to esbuild's LF
    output. A gate that is red on the development machine for a checkout
    artifact trains its readers to ignore it. The scratch plane makes the
    platform fact explicit instead of trusting the host, so this cell is
    meaningful on Linux too. The second phase appends a comment to ``app.js``
    and demands a red - without it the cell would pass just as well if the
    checker had stopped looking.
    """
    plane = _crlf_plane()
    try:
        clean = _run_build_check(plane)
        output = clean.stdout + clean.stderr
        assert clean.returncode == 0, f"a CRLF checkout was reported stale:\n{output}"
        assert "stale" not in output.lower(), (
            f"the build reported staleness without failing:\n{output}"
        )

        drifted = plane / "web" / "app.js"
        drifted.write_bytes(drifted.read_bytes() + b"// drift\r\n")
        dirty = _run_build_check(plane)
        dirty_output = dirty.stdout + dirty.stderr
        assert dirty.returncode != 0, "the drift phase went green; P4 is vacuous"
        assert "app.js is stale" in dirty_output, (
            "the drift phase failed without naming the edited bundle:\n" + dirty_output
        )
    finally:
        shutil.rmtree(plane, ignore_errors=True)
