"""Ask git whether a directory has a work tree we could read.

M8-T547: ``git status`` exits 128 both for "not a git repository" - where an
empty changed list is the truth - and for "this is a repository I am
forbidden to read" (``dubious ownership``), where the same empty list is the
read-failure collapse.  The probe separates the two.

M8-T548: the change view needs the same distinction, so the rule moved here
from the agent loop - one home, two readers.

M8-T546: the **words** of those failure answers moved here too.  "git status
did not run", "git status timed out", "git status exited N" used to be
hand-spelled by the agent loop, the snapshot reader and the change view - the
same fact in three homes, and each hand-spelling drifted.  The builders below
are the one home; every reader asks them.
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


def git_status_unavailable_reason(
    exc: BaseException | None = None,
    *,
    timeout_seconds: float = 20.0,
    subject: str = "脏文件清单",
) -> str:
    """One sentence for a ``git status`` that did not get to run at all.

    ``exc`` is the failure that stopped the command (``OSError`` /
    ``TimeoutExpired``).  A caller that only saw the exit-127 ``git
    unavailable`` collapse passes ``None`` and keeps the timeout / PATH note
    instead of a machine-specific exception text.
    """
    if exc is not None:
        return f"git status 无法运行: {exc}"
    return f"git status 无法运行（{int(timeout_seconds)} 秒超时或 PATH 里没有 git），{subject}没有读出来"


def git_status_timeout_reason(seconds: float, subject: str) -> str:
    """One sentence for a ``git status`` that did not finish in time."""
    return f"git status 超时（{int(seconds)} 秒）：工作区可能太大，{subject}没有读出来"


def git_status_exit_reason(code: int, stderr: str = "") -> str:
    """One sentence for a ``git status`` that ran and the read is untrustworthy.

    The exit code is the headline; git's own first stderr line is the
    actionable half (safe.directory, index.lock, not a repository), so it is
    carried along, truncated to 200 characters.
    """
    reason = f"git status 退出码 {code}"
    first = (stderr or "").strip().splitlines()
    if first:
        reason += f": {first[0][:200]}"
    return reason
