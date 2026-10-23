"""The one place a UTC moment becomes a wire string.

Three spellings are in active use, and each has readers that depend on its
exact shape:

* ``utc_stamp`` - ``2026-10-24T06:57:34Z``: whole seconds, ``Z`` suffix.
  Task snapshots, memory entries and the todo file carry this one.
* ``utc_now_iso`` - ``2026-10-24T06:57:34+00:00``: whole seconds, explicit
  offset.  Session records and the editor's change log carry this one.
* ``utc_iso`` - ``2026-10-24T06:57:34.123456+00:00``: microsecond precision,
  rendered from an epoch float.  The task manager's records and the web API
  carry this one.

Before this module the three spellings were written out at nine call sites: a
format string one site forgets to update is a timestamp no reader can compare,
and a ``gmtime`` that quietly becomes ``localtime`` is a snapshot whose
creation time is off by the host's timezone.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

#: The wire format for whole-second UTC stamps with the ``Z`` suffix.
UTC_STAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_stamp(epoch: float | None = None) -> str:
    """The whole-second, ``Z``-suffixed rendering of a moment (default: now)."""
    return time.strftime(UTC_STAMP_FORMAT, time.gmtime(epoch))


def utc_now_iso() -> str:
    """The whole-second, offset-suffixed rendering of now."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def utc_iso(timestamp: float | None) -> str | None:
    """The microsecond, offset-suffixed rendering of an epoch (None stays None)."""
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, UTC).isoformat()


__all__ = ["UTC_STAMP_FORMAT", "utc_iso", "utc_now_iso", "utc_stamp"]
