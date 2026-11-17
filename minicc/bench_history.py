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


def read_history(workspace: Path, *, limit: int = _MAX_ENTRIES) -> dict[str, Any]:
    """Read up to `limit` newest entries; honest absent state three-states: absent / empty / present."""
    path = _history_path(workspace)
    if not path.is_file():
        return {
            "present": False,
            "reason": "no bench history yet — run the v2 suite (python -m minicc.bench_tasks --suite v2 --record)",
            "count": 0,
            "entries": [],
        }
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {
            "present": False,
            "reason": f"could not read {path}",
            "count": 0,
            "entries": [],
        }

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

    if limit < 0:
        limit = 0
    window = parsed[-limit:][::-1] if limit else []

    def _avg(items: list[float]) -> float | None:
        if not items:
            return None
        return round(sum(items) / len(items), 3)

    scores = [float(item["score"]) for item in window if isinstance(item.get("score"), (int, float))]
    elapsed = [float(item["elapsed_ms"]) for item in window if isinstance(item.get("elapsed_ms"), (int, float))]
    mean_score = _avg(scores)
    mean_elapsed_ms = _avg(elapsed)

    return {
        "present": bool(window),
        "count": len(window),
        "total_lines_matched": len(parsed),
        "skipped_lines": bad_lines,
        "mean_score": mean_score,
        "mean_elapsed_ms": mean_elapsed_ms,
        "window_from": (window[-1]["ts"] if window else None),
        "window_to": (window[0]["ts"] if window else None),
        "entries": window,
    }


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
