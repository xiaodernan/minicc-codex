"""Narrow repair scope to evidence that can affect a failed verifier."""

from __future__ import annotations

import re
from typing import Any


def repair_scope(events: list[dict[str, Any]], verification: dict[str, Any]) -> dict[str, object]:
    """Return bounded affected files and failed tests without guessing ownership.

    The agent still re-checks the files before editing.  This scope only prevents
    a verifier failure from causing an unfocused full-workspace repair prompt.

    M8-T314: a bash write names no path, so the scope was built from the
    events' ``path`` field alone and came out empty for a task that edited
    through the shell.  The loop's ``verification_required`` trace carries
    the paths it worked out, so those are read too.
    """
    writes: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("write") and event.get("path"):
            writes.append(str(event["path"]))
        detail = event.get("detail")
        if isinstance(detail, dict):
            for path in detail.get("changed_paths") or []:
                text = str(path or "").strip()
                if text:
                    writes.append(text)
    failed_tests = [str(item) for item in verification.get("failed_tests") or [] if str(item)]
    tokens = {
        fragment.casefold()
        for test in failed_tests
        for token in re.findall(r"[A-Za-z_][\w.-]{2,}", test)
        for fragment in re.split(r"[_.-]+", token)
        if len(fragment) >= 3
    }
    related = [path for path in writes if any(token in path.casefold() for token in tokens)]
    targets = list(dict.fromkeys(related or writes))[-12:]
    return {
        "failed_tests": failed_tests[:12],
        "changed_paths": list(dict.fromkeys(writes))[-24:],
        "repair_targets": targets,
        "reason": "matched_failed_test" if related else "changed_file_evidence",
    }


__all__ = ["repair_scope"]
