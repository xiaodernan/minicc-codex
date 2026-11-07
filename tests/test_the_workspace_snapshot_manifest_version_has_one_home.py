"""M8-T570 — the snapshot manifest format version is one fact, not three spellings of 2.

The number 2 is written once (capture) and read twice (before_write fallback,
restore). A manifest written with ``version: 3`` while a reader still expects
``2`` silently routes every restore through the legacy layout - files
disappear or a wrong ``files`` root is used with no error raised at all.
The figure was spelled twice inline (``== 2``
patterns) plus once in the writer; this batch gives it one home.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/snapshots.py"
CONSTANT = "WORKSPACE_SNAPSHOT_MANIFEST_VERSION"


def test_the_home_answers_the_question() -> None:
    from minicc.snapshots import WORKSPACE_SNAPSHOT_MANIFEST_VERSION

    assert WORKSPACE_SNAPSHOT_MANIFEST_VERSION == 2


def test_capture_writes_the_manifest_with_the_home() -> None:
    import subprocess

    from minicc.snapshots import WORKSPACE_SNAPSHOT_MANIFEST_VERSION, capture, snapshot_dir

    workspace = Path(_tmp()) / "ws"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.example"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=workspace, check=True, capture_output=True)
    target = workspace / "tracked.py"
    target.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workspace, check=True, capture_output=True)
    target.write_text("x = 2\n", encoding="utf-8")
    capture(workspace, "t-one")
    manifest_path = snapshot_dir(workspace, "t-one") / "manifest.json"
    assert manifest_path.is_file(), manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == WORKSPACE_SNAPSHOT_MANIFEST_VERSION
    assert manifest["files"] == ["tracked.py"]


def test_every_reader_of_the_version_asks_the_home() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert CONSTANT in source
    # Three readers plus the definition site, all asking the home: 4 occurrences.
    assert source.count(CONSTANT) >= 4, source.count(CONSTANT)
    assert '"version": 2' not in source
    assert "== 2 else" not in source


def test_no_module_spells_the_snapshot_version_inline() -> None:
    SNAPSHOT_SHAPE = {"version", "task_id", "files", "digests", "sizes", "missing", "skipped", "skipped_reasons", "workspace"}
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            version_value = next(
                (value.value for key, value in zip(node.keys, node.values)
                 if isinstance(key, ast.Constant) and key.value == "version"
                 and isinstance(value, ast.Constant)),
                None,
            )
            if SNAPSHOT_SHAPE <= keys and version_value == 2 and relative != HOME:
                offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "the workspace snapshot manifest is spelled inline outside its one "
        f"home ({HOME}): " + ", ".join(offenders)
    )


def _tmp() -> str:
    import tempfile

    return tempfile.mkdtemp(prefix="minicc-manifest-version-")
