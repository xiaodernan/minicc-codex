"""Narrow repair scope to evidence that can affect a failed verifier."""

from __future__ import annotations

import re
from typing import Any


def repair_scope(events: list[dict[str, Any]], verification: dict[str, Any]) -> dict[str, object]:
    """Return bounded affected files and failed tests without guessing ownership.

    The agent still re-checks the files before editing.  This scope only prevents
    a verifier failure from causing an unfocused full-workspace repair prompt.
    """
    writes = [
        str(event.get("path") or "")
        for event in events
        if isinstance(event, dict) and event.get("write") and event.get("path")
    ]
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
