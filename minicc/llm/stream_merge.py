"""Stream text assembly — one implementation per dialect, never both at once.

Two distinct cases exist and must not share logic:

- Within one attempt, each ``delta.content`` is an incremental fragment and is
  appended byte-for-byte. Any overlap-dedup here silently drops characters
  (P0-1: ``'hel'+'lo'`` became ``'helo'`` and polluted write_file/bash
  arguments).
- Across retry attempts, a gateway may replay the full cumulative text instead
  of resuming. Only there is overlap dedup legitimate, and only against
  already-committed text (:class:`merge_retry_snapshot`).

Some compatible gateways send cumulative snapshots *within* one attempt: every
fragment repeats everything emitted so far. The old per-fragment prefix test
decided that case by guessing, and every time an incremental fragment merely
happened to start with the text already accumulated it deleted characters -
``"7." + "7.7"`` became ``"7.7"``, and a live run stored "7.7" as the answer to
a memory that says "7.7.7". The dialects are not distinguishable from a single
fragment, so :class:`AttemptTextAssembler` demands a streak of whole-prefix
repeats before it reinterprets the stream. Until that streak appears the cost
is duplicated text, which is visible and fixable; the cost of guessing wrong
the other way is silent loss, which is neither.
"""

from __future__ import annotations

#: Consecutive fragments that each repeat the previous one in full, and grow,
#: before the stream is treated as cumulative snapshots. Two is the minimum
#: that a real snapshot stream can show (a three-chunk stream, which exists:
#: ``"aa", "aab", "aabc"``) while a single repeat - the case that silently
#: turned "7.7.7" into "7.7" - stays incremental.
CUMULATIVE_STREAK = 2


def append_delta(previous: str, fragment: str) -> tuple[str, str]:
    """Append one incremental delta fragment; return (merged, suffix)."""
    if not fragment:
        return previous, ""
    if not previous:
        return fragment, fragment
    return previous + fragment, fragment


class AttemptTextAssembler:
    """Merge one attempt's fragments, defaulting to byte-for-byte append."""

    def __init__(self) -> None:
        self.text = ""
        self._previous = ""
        self._streak = 0
        self._cumulative = False
        #: Set for the single :meth:`feed` call in which the stream was
        #: reinterpreted, so the caller can rebase anything it derived from the
        #: appended text (which may hold duplication) onto the snapshot.
        self.latched_now = False

    @property
    def cumulative(self) -> bool:
        """Whether the stream has been reinterpreted as cumulative snapshots."""
        return self._cumulative

    def feed(self, fragment: str) -> str:
        """Add one fragment and return the attempt's whole text so far."""
        self.latched_now = False
        if not fragment:
            return self.text
        # Compare against the previous fragment, not against our own buffer: in
        # incremental mode the buffer may already hold duplication, which no
        # snapshot would start with.
        grows_previous = (
            bool(self._previous)
            and len(fragment) > len(self._previous)
            and fragment.startswith(self._previous)
        )
        if self._cumulative:
            # Each snapshot is the truth for the attempt up to now.
            self.text = fragment if fragment.startswith(self.text) else self.text + fragment
        elif grows_previous:
            self._streak += 1
            if self._streak >= CUMULATIVE_STREAK:
                self._cumulative = True
                self.latched_now = True
                self.text = fragment
            else:
                self.text += fragment
        else:
            self._streak = 0
            self.text += fragment
        self._previous = fragment
        return self.text


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


__all__ = [
    "CUMULATIVE_STREAK",
    "AttemptTextAssembler",
    "append_delta",
    "merge_retry_snapshot",
]
