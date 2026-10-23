"""The one shape of a runtime trace event.

Forty-eight places used to write this record by hand: forty-six exact
seven-key dict literals across the agent loop, the task manager, the web
service, the CLI and all three LLM providers, plus two near-misses - the
loop's own builder (six keys, ``detail`` added conditionally) and the
subagent lifecycle event (the seven keys plus three of its own).

A trace event is the one record every layer emits and every consumer reads
by key, so a key one writer forgets is not a crash: the timeline still
accepts the dict, the report still prints the row, and the missing field is
simply absent for whoever looks for it later.  The constructor below is the
only place the shape is spelled out; a new field is added here once and
every emitter gets it on the next run.
"""

from __future__ import annotations

from typing import Any


def trace_event(
    name: str,
    status: str,
    phase: str,
    code: str,
    summary: str,
    detail: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    """Build one trace event; ``kind`` is always ``"trace"`` and comes first.

    ``detail`` is omitted entirely when it is None, which is the shape the
    agent loop's ``emit_trace`` produced for a milestone with no payload.
    """
    event: dict[str, Any] = {
        "kind": "trace",
        "name": name,
        "status": status,
        "phase": phase,
        "code": code,
        "summary": summary,
    }
    if detail is not None:
        event["detail"] = detail
    return event
