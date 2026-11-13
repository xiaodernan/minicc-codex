"""minicc.workspace_digest — one read-only fact pack about this workspace.

``/api/metrics`` answers "what did the tasks cost". The digest answers
"what *is this place*": which branch HEAD sits on, how many commits and
batches this repository carries, how many files/tests/roadmap lines are
tracked. Every number is computed from local, offline sources — git and
the repository's own documents — so the payload never depends on the
network, on any model, or on a task store being present.

Design rules:
- never raises: a non-git workspace, a missing git binary or a giant
  repository all degrade to ``None`` fields, never to an exception
- no network, no ``.minicc`` access, no writes of any kind
- no subprocesses beyond ``git`` with fixed argument lists
- bounded output: roadmap/changelog are read line by line in memory,
  never echoed into the payload
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

_GIT_TIMEOUT = 5.0


def _git(workspace: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _line_count(path: Path) -> int | None:
    try:
        if not path.is_file():
            return None
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return None


def _count_batch_headings(path: Path) -> int | None:
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return sum(1 for line in text.splitlines() if line.startswith("## 批次"))


def build_digest(workspace: Path | str) -> dict[str, Any]:
    """The read-only fact pack for ``/api/digest`` and the Almanac panel."""
    root = Path(workspace)
    payload: dict[str, Any] = {
        "schema_version": "minicc.digest.v1",
        "workspace": str(root),
        "is_git": False,
        "branch": None,
        "head_short": None,
        "upstream_ahead": None,
        "upstream_behind": None,
        "dirty_entries": None,
        "total_commits": None,
        "first_commit_at": None,
        "roadmap_batches": None,
        "roadmap_lines": None,
        "changelog_lines": None,
        "tracked_files": None,
        "test_files": None,
    }

    if not root.is_dir():
        return payload

    inside = _git(root, ["rev-parse", "--is-inside-work-tree"])
    if inside is None or inside.strip() != "true":
        return payload
    payload["is_git"] = True

    branch = _git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    payload["branch"] = branch.strip() if branch else None

    head = _git(root, ["rev-parse", "--short", "HEAD"])
    payload["head_short"] = head.strip() if head else None

    ahead_behind = _git(root, ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"])
    if ahead_behind:
        parts = ahead_behind.split()
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            payload["upstream_behind"], payload["upstream_ahead"] = int(parts[0]), int(parts[1])

    status = _git(root, ["status", "--porcelain=v1", "-uall"])
    if status is not None:
        payload["dirty_entries"] = sum(1 for line in status.splitlines() if line.strip())

    commits = _git(root, ["rev-list", "--count", "HEAD"])
    if commits and commits.strip().isdigit():
        payload["total_commits"] = int(commits.strip())

    # NOTE: ``git log --reverse -1`` limits the walk to one commit *before*
    # the reversal — it returns HEAD, not the root. Ask for the root commits
    # explicitly instead (multi-root histories answer several SHAs).
    roots = _git(root, ["rev-list", "--max-parents=0", "HEAD"])
    if roots:
        root_sha = next((line.strip() for line in roots.splitlines() if line.strip()), "")
        if root_sha:
            stamp = _git(root, ["show", "-s", "--format=%cI", root_sha])
            payload["first_commit_at"] = stamp.strip() if stamp and stamp.strip() else None

    ls = _git(root, ["ls-files"])
    if ls is not None:
        files = [line for line in ls.splitlines() if line.strip()]
        payload["tracked_files"] = len(files)
        payload["test_files"] = sum(
            1
            for line in files
            if line.startswith("tests/") and (line.endswith(".py") or line.endswith(".mjs"))
        )

    roadmap = root / "docs" / "ROADMAP_TO_PRODUCT.md"
    payload["roadmap_batches"] = _count_batch_headings(roadmap)
    payload["roadmap_lines"] = _line_count(roadmap)
    payload["changelog_lines"] = _line_count(root / "docs" / "CHANGELOG.md")
    return payload
