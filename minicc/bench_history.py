"""Bench v2 history — an append-only JSONL of real run summaries.

Why JSONL and not SQLite: the bench history is both written rarely (one line per
``--suite v2`` invocation or micro-smoke) and read on every unlock of the
admin panel. A tiny JSONL file is crash-safe on partial write (each line is
independent) and trivial to query in-memory for ≤ a few hundred entries —
the panel shows trend, not transactions.

Contract
--------

- **Location**: ``<workspace>/.minicc/bench_history.jsonl``. Never outside the
  workspace — the harness must work in a sandbox with only the workspace path.
- **Line shape**: one ``{"ts": …, "suite": "v2", "kind": "…", "task_id": "…",
  "score": <float 0-1>, "elapsed_ms": int, "provider": str, "deterministic": bool}"
  JSON object per line. Parsing **must be tolerant**: an unparseable line ends
  the read — we never invent the tail.
- **Read limit**: ``limit=200`` newest lines. Anything beyond that is reported
  as ``count`` with a note, not read — a five-year-old run with a 500k bench file
  still opens instantly.
- **Zero-model path**: the reading side never calls a model. The admin tile
  displays numbers you could reproduce with ``wc -l`` and ``jq`` — that is the whole
  point.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .cli_io import cli_out
from .clock import utc_stamp

_FILENAME = "bench_history.jsonl"
_MAX_ENTRIES = 200


def _history_path(workspace: Path) -> Path:
    return Path(workspace) / ".minicc" / _FILENAME


def append_entry(
    workspace: Path,
    entry: dict[str, Any],
    *,
    allow_changes: bool,
) -> dict[str, Any]:
    """Append one line to bench_history.jsonl; refuse when writes are not allowed."""
    if not allow_changes:
        return {"recorded": False, "reason": "allow_changes is off for this workspace"}

    required = ("ts", "suite", "kind", "task_id", "score", "elapsed_ms")
    missing = [key for key in required if key not in entry]
    if missing:
        return {"recorded": False, "reason": f"missing required keys: {', '.join(missing)}"}

    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
    target = _history_path(workspace)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return {"recorded": True, "path": str(target)}


def _parse_ts(raw: Any) -> datetime | None:
    """Parse a history timestamp; unparseable / missing values are simply not in any window."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        stamp = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)


def parse_window_days(raw: Any) -> int | None:
    """``last-30d`` / ``30d`` / ``30`` → 30; anything else → None (unfiltered, never a 500).

    ASCII digits only: ``"²".isdigit()`` is true and ``int("²")`` raises, and a
    query parameter is not allowed to reach an exception.
    """
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    if text.startswith("last-"):
        text = text[5:]
    if text.endswith("d"):
        text = text[:-1]
    return int(text) if text.isascii() and text.isdigit() else None


def _answer(
    *,
    state: str,
    reason: str,
    filters: dict[str, Any],
    total_lines: int | None,
    total_lines_matched: int | None,
    skipped_lines: int | None,
    window: list[dict[str, Any]],
) -> dict[str, Any]:
    """One shape for every state, so a caller cannot read a missing key as a zero.

    `total_lines` counts the rows in the file and never moves with the filters;
    `total_lines_matched` is what survived them; `count` is what fits the cap.
    An unreadable file leaves all three `None` — "we could not count" is not "zero".
    """
    def _avg(items: list[float]) -> float | None:
        if not items:
            return None
        return round(sum(items) / len(items), 3)

    scores = [float(item["score"]) for item in window if isinstance(item.get("score"), (int, float))]
    elapsed = [float(item["elapsed_ms"]) for item in window if isinstance(item.get("elapsed_ms"), (int, float))]
    return {
        "present": state == "present",
        "state": state,
        "reason": reason,
        "count": len(window),
        "total_lines": total_lines,
        "total_lines_matched": total_lines_matched,
        "skipped_lines": skipped_lines,
        "mean_score": _avg(scores),
        "mean_elapsed_ms": _avg(elapsed),
        "window_from": (window[-1]["ts"] if window else None),
        "window_to": (window[0]["ts"] if window else None),
        "filters": filters,
        "entries": window,
    }


def read_history(
    workspace: Path,
    *,
    limit: int = _MAX_ENTRIES,
    suite: str | None = None,
    kind: str | None = None,
    window_days: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read up to `limit` newest entries and say which of five states this is.

    `state` is the honest answer; `present` only ever means "there are rows to
    draw". The five are not interchangeable: the file is not there (absent), it
    is there but could not be read (unreadable), it is readable but holds no
    entries (empty), it has entries and the filter kept none (filtered_empty),
    it has entries and the cap kept none (capped), or there is a window (present).
    """
    path = _history_path(workspace)
    filters = {"suite": suite, "kind": kind, "window_days": window_days}
    if not path.is_file():
        return _answer(
            state="absent",
            reason="no bench history yet — run the v2 suite (python -m minicc.bench_tasks --suite v2 --record)",
            filters=filters, total_lines=0, total_lines_matched=0, skipped_lines=0, window=[],
        )
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return _answer(
            state="unreadable",
            reason=f"could not read {path}: {exc}",
            filters=filters, total_lines=None, total_lines_matched=None, skipped_lines=None, window=[],
        )

    parsed: list[dict[str, Any]] = []
    bad_lines = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if not isinstance(obj, dict):
                bad_lines += 1
                continue
            parsed.append(obj)
        except json.JSONDecodeError:
            bad_lines += 1

    total_lines = len(parsed)
    if not parsed:
        return _answer(
            state="empty",
            reason=f"{path} holds no entries yet"
            + (f" ({bad_lines} line(s) could not be parsed)" if bad_lines else ""),
            filters=filters, total_lines=0, total_lines_matched=0, skipped_lines=bad_lines, window=[],
        )

    if suite is not None:
        parsed = [item for item in parsed if item.get("suite") == suite]
    if kind is not None:
        parsed = [item for item in parsed if item.get("kind") == kind]
    if window_days is not None and window_days >= 0:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=window_days)
        parsed = [
            item for item in parsed
            if (stamp := _parse_ts(item.get("ts"))) is not None and stamp >= cutoff
        ]

    if not parsed:
        wanted = ", ".join(
            f"{name}={value}" for name, value in filters.items() if value is not None
        )
        return _answer(
            state="filtered_empty",
            reason=f"the file has {total_lines} entries; none match {wanted or 'this filter'}",
            filters=filters, total_lines=total_lines, total_lines_matched=0,
            skipped_lines=bad_lines, window=[],
        )

    if limit < 0:
        limit = 0
    window = parsed[-limit:][::-1] if limit else []
    if not window:
        return _answer(
            state="capped",
            reason=f"the file has {total_lines} entries and {len(parsed)} match, but limit={limit} asks for none",
            filters=filters, total_lines=total_lines, total_lines_matched=len(parsed),
            skipped_lines=bad_lines, window=[],
        )

    return _answer(
        state="present", reason="", filters=filters, total_lines=total_lines,
        total_lines_matched=len(parsed), skipped_lines=bad_lines, window=window,
    )


def ingest_report(workspace: Path, evaluation_json: Path, *, allow_changes: bool) -> dict[str, Any]:
    """Translate a benchmarks/evaluation.json into bench_history rows.

    Two shapes are written, each honest about what is actually known:

    - one ``suite_run`` row always (records "a run was observed"; its ``score``
      is the real ``pass_at_1`` or ``None`` when nothing was judged);
    - one row per graded | task row, when the report executed anything;
      ``score`` is 1.0 for pass, 0.0 for fail, ``None`` for refused.
    """
    if not allow_changes:
        return {"recorded": False, "reason": "allow_changes is off for this workspace"}
    if not evaluation_json.is_file():
        return {"recorded": False, "reason": f"report not found: {evaluation_json}"}
    try:
        report = json.loads(evaluation_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"recorded": False, "reason": f"{type(exc).__name__}: {exc}"}

    writer = []
    metrics = report.get("metrics") or {}
    results = report.get("results") or []
    suite_version = report.get("suite_version") or "unknown"
    suite = str(suite_version).split("-", 1)[0] if isinstance(suite_version, str) else "unknown"

    writer.append({
        "ts": utc_stamp(),
        "suite": suite,
        "kind": "suite_run",
        "task_id": "*",
        "score": metrics.get("pass_at_1"),
        "elapsed_ms": metrics.get("latency_p50_ms"),
        "provider": "unknown",
        "deterministic": True,
    })

    for row in results:
        task_id = row.get("task_id") or "unknown"
        passed = row.get("passed")
        score = None
        if passed is True:
            score = 1.0
        elif passed is False:
            score = 0.0
        writer.append({
            "ts": utc_stamp(),
            "suite": suite,
            "kind": str(row.get("grader_type") or "ungraded"),
            "task_id": task_id,
            "score": score,
            "elapsed_ms": row.get("elapsed_ms") or row.get("latency_ms"),
            "provider": "unknown",
            "deterministic": True,
        })

    entries = 0
    for entry in writer:
        outcome = append_entry(workspace, entry, allow_changes=True)
        if outcome.get("recorded"):
            entries += 1
    return {"recorded": True, "entries": entries, "path": str(_history_path(workspace))}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Append or inspect the minicc bench history.")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--append", metavar="JSON",
                        help="one JSON object to append, or '-' for stdin")
    parser.add_argument("--allow-changes", action="store_true",
                        help="declare explicitly the caller has write permission for this workspace")
    parser.add_argument("--show", action="store_true", help="print the read history as JSON")
    parser.add_argument("--ingest", metavar="FILE", help="translate a benchmarks/evaluation.json into history lines")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    if args.append is not None:
        if args.append == "-":
            raw = sys.stdin.read()
        else:
            raw = args.append
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as exc:
            cli_out(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        entry.setdefault("ts", utc_stamp())
        out = append_entry(workspace, entry, allow_changes=args.allow_changes)
        cli_out(json.dumps(out, ensure_ascii=False))
        return 0 if out.get("recorded") else 1

    if args.ingest is not None:
        out = ingest_report(workspace, Path(args.ingest), allow_changes=args.allow_changes)
        cli_out(json.dumps(out, ensure_ascii=False))
        return 0 if out.get("recorded") else 1

    if args.show:
        out = read_history(workspace)
        cli_out(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
