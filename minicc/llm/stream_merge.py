"""Stream text assembly — single implementation for incremental deltas.

Two distinct cases exist and must not share logic:

- ``append_delta``: within one attempt, each ``delta.content`` is an
  incremental fragment. It must be concatenated byte-for-byte. Any
  overlap-dedup here silently drops characters (P0-1: ``'hel'+'lo'``
  became ``'helo'`` and polluted write_file/bash arguments).
- ``merge_retry_snapshot``: across retry attempts, a gateway may replay
  the full cumulative text instead of resuming. Only here is overlap
  dedup legitimate, and only against already-committed text.
"""

from __future__ import annotations


def append_delta(previous: str, fragment: str) -> tuple[str, str]:
    """Append one incremental delta fragment; return (merged, suffix)."""
    if not fragment:
        return previous, ""
    if not previous:
        return fragment, fragment
    return previous + fragment, fragment


def accumulate_attempt_text(attempt: str, fragment: str) -> tuple[str, str]:
    """Update one attempt's text from a new delta content fragment.

    Most gateways send incremental fragments (append byte-for-byte). Some
    send cumulative snapshots (each fragment repeats the whole attempt text
    so far). Detect the cumulative case by prefix: when the new fragment
    starts with everything accumulated so far, it *is* the new attempt text;
    otherwise it is an incremental fragment to append. No overlap-dedup is
    ever applied to incremental fragments — that was P0-1.
    """
    if not fragment:
        return attempt, ""
    if not attempt:
        return fragment, fragment
    if fragment.startswith(attempt):
        return fragment, fragment[len(attempt):]
    return attempt + fragment, fragment


def merge_retry_snapshot(previous: str, current: str) -> tuple[str, str]:
    """Merge a retried full response and return only the new suffix."""
    if not previous:
        return current, current
    if not current:
        return previous, ""
    if current.startswith(previous):
        return current, current[len(previous):]
    if previous.startswith(current):
        return previous, ""
    max_overlap = min(len(previous), len(current))
    for size in range(max_overlap, 0, -1):
        if previous[-size:] == current[:size]:
            return previous + current[size:], current[size:]
    return previous + current, current


__all__ = ["append_delta", "accumulate_attempt_text", "merge_retry_snapshot"]
