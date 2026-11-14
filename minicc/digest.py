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


def format_digest(report: dict[str, Any], *, json_out: bool = False) -> str:
    """Human-readable rendering of :func:`build_digest` (or JSON passthrough)."""
    if json_out:
        import json

        return json.dumps(report, ensure_ascii=False)

    def field(value: Any) -> str:
        return "—" if value is None else str(value)

    lines = [f"minicc digest · workspace {report.get('workspace')}"]
    lines.append("repository: git" if report.get("is_git") else "repository: not a git work tree")
    if report.get("is_git"):
        lines.append(f"branch: {field(report.get('branch'))}{' @ ' + str(report['head_short']) if report.get('head_short') else ''}")
        ahead = report.get("upstream_ahead")
        behind = report.get("upstream_behind")
        lines.append(
            f"upstream: {('ahead ' + str(ahead)) if ahead is not None else 'upstream not configured'}"
            + (f" · behind {behind}" if behind is not None else "")
        )
        lines.append(f"dirty entries: {field(report.get('dirty_entries'))}")
        lines.append(f"commits: {field(report.get('total_commits'))}")
        lines.append(f"first commit: {field(report.get('first_commit_at'))}")
        lines.append(f"tracked files: {field(report.get('tracked_files'))}")
        lines.append(f"test files: {field(report.get('test_files'))}")
    lines.append(f"roadmap batches: {field(report.get('roadmap_batches'))}")
    lines.append(f"roadmap lines: {field(report.get('roadmap_lines'))}")
    lines.append(f"changelog lines: {field(report.get('changelog_lines'))}")
    recent = report.get("recent_commits")
    if recent:
        lines.append("recent commits:")
        for item in recent:
            lines.append(f"  {field(item.get('short'))}  {field(item.get('subject'))}")
    return "\n".join(lines)


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
        "recent_commits": None,
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

    # Twelve most recent commits: bounded, verbatim-ish (subject truncated to
    # 140 chars), read with fixed arguments. This is the newest member of the
    # fact pack and the raw material the Journal screen renders.
    raw = _git(root, ["log", "-n", "12", "--format=%h%x1f%cI%x1f%s%x1e"])
    if raw:
        recent: list[dict[str, str]] = []
        for chunk in raw.split("\x1e"):
            parts = chunk.strip("\n").split("\x1f")
            if len(parts) != 3:
                continue
            short, at, subject = parts
            recent.append({"short": short, "at": at, "subject": subject[:140]})
        payload["recent_commits"] = recent
    return payload
