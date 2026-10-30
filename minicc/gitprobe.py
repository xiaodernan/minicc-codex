"""Ask git whether a directory has a work tree we could read.

M8-T547: ``git status`` exits 128 both for "not a git repository" - where an
empty changed list is the truth - and for "this is a repository I am
forbidden to read" (``dubious ownership``), where the same empty list is the
read-failure collapse.  The probe separates the two.

M8-T548: the change view needs the same distinction, so the rule moved here
from the agent loop - one home, two readers.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def work_tree_verdict(workspace: str | Path) -> tuple[str, str]:
    """One of ``("yes", "")``, ``("no", "")``, ``("unknown", why)``.

    ``git rev-parse --is-inside-work-tree`` answers ``true`` inside a work
    tree and ``false`` in a bare repository; a directory that is not a
    repository fails with git's own ``not a git repository``.  Anything
    else - the probe could not run, or failed for a reason we cannot read -
    is ``unknown``: the caller keeps its failure, because an unreadable
    tree must not pass for a clean one.
    """
    try:
        probe = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(workspace),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "unknown", f"rev-parse 无法运行: {exc}"
    if probe.returncode == 0:
        return ("yes" if probe.stdout.strip() == "true" else "no"), ""
    stderr = (probe.stderr or "").strip()
    if "not a git repository" in stderr:
        return "no", ""
    return "unknown", (stderr.splitlines()[0][:200] if stderr else f"退出码 {probe.returncode}")
