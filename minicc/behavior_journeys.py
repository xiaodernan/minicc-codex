"""M8-T1289: synthetic visitor journeys, aggregated for the admin panel.

The brief asks the project to simulate *real* user behaviour — the visitor who
loses patience and closes the tab, the one who has no idea where to go and
clicks around at random. This module does not invent those numbers.
``scripts/behavior_sim.mjs`` drives real headless Chromium sessions through the
actual UI and appends one JSON line per session; this module only aggregates
what those sessions actually did.

Honesty rules, the same ones the rest of the admin surface keeps:

* an empty log is an honest empty state — ``live: False`` plus the exact
  command that would fill it, never a fabricated placeholder;
* a malformed line is skipped, never rescued into a plausible-looking journey;
* every aggregate carries the sample size it came from, because a 100 % bounce
  rate over three sessions is not a fact about the product;
* nothing here calls a model or the network, and nothing here writes.

The log lives under the workspace's ``.minicc/`` state directory (git-ignored),
so a fresh clone honestly reports "no journeys yet".
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

JOURNEY_DIR = "behavior"
JOURNEY_FILE = "journeys.jsonl"
MAX_JOURNEYS = 400
MAX_VIEWS = 40
MAX_TRANSITIONS = 24
MAX_ID = 32

HOW_TO = "node scripts/behavior_sim.mjs --runs 6"
SOURCE = "synthetic-real-execution"

# Sample-size bands. Below "thin" the panel says the number is directional at
# best; the thresholds are deliberately conservative and stated in the payload
# so the UI never has to guess.
THIN = 10
USABLE = 30


def state_dir(workspace: Path) -> Path:
    """The workspace's own state directory.

    Deliberately *not* falling back to ``~/.minicc``: a journey belongs to the
    workspace whose UI it walked through. Reading another project's log just
    because this one has no ``.minicc`` yet would be a quiet lie, so a fresh
    clone answers the empty state instead.
    """
    return Path(workspace) / ".minicc"


def journey_path(workspace: Path) -> Path:
    """Absolute path of the journey log for *workspace* (may not exist)."""
    return state_dir(workspace) / JOURNEY_DIR / JOURNEY_FILE


def _as_count(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number >= 0 else 0


def _as_text(value: Any, limit: int = MAX_ID) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _clean(record: Any) -> dict[str, Any] | None:
    """Validate one JSON line into the bounded shape the panel reads.

    Returns ``None`` for anything that is not a journey — a wrong type, a
    missing persona, or a record so broken that aggregating it would invent
    behaviour rather than describe it.
    """
    if not isinstance(record, dict):
        return None
    persona = _as_text(record.get("persona"))
    if not persona:
        return None
    raw_views = record.get("views")
    views: list[str] = []
    if isinstance(raw_views, list):
        for item in raw_views:
            text = _as_text(item)
            if text:
                views.append(text)
            if len(views) >= MAX_VIEWS:
                break
    last_view = _as_text(record.get("last_view")) or (views[-1] if views else _as_text(record.get("view")))
    # boot_ms is the one field where 0 and null mean different things: 0 would
    # claim the sidebar was clickable instantly, null says it never became
    # clickable before the visitor gave up. Keep them apart.
    boot_raw = record.get("boot_ms")
    boot_ms: int | None = None
    if isinstance(boot_raw, (int, float)) and not isinstance(boot_raw, bool) and boot_raw >= 0:
        boot_ms = int(boot_raw)
    # Transitions are the "clicked around lost" evidence — an ordered pair per
    # move. Older records predate the field, so an absent or broken list is an
    # honest empty list, never a reconstructed guess.
    transitions: list[tuple[str, str]] = []
    raw_pairs = record.get("transitions")
    if isinstance(raw_pairs, list):
        for item in raw_pairs:
            if isinstance(item, dict):
                src = _as_text(item.get("from"))
                dst = _as_text(item.get("to"))
                if src and dst:
                    transitions.append((src, dst))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                src, dst = _as_text(item[0]), _as_text(item[1])
                if src and dst:
                    transitions.append((src, dst))
            if len(transitions) >= MAX_TRANSITIONS:
                break
    return {
        "persona": persona,
        "started_at": _as_text(record.get("started_at"), 40),
        "dwell_ms": _as_count(record.get("dwell_ms")),
        "boot_ms": boot_ms,
        "views": views,
        "transitions": transitions,
        "clicks": _as_count(record.get("clicks")),
        "rage_clicks": _as_count(record.get("rage_clicks")),
        "page_errors": _as_count(record.get("page_errors")),
        "bounced": bool(record.get("bounced")),
        "exit_reason": _as_text(record.get("exit_reason")),
        "last_view": last_view,
    }


def load_journeys(workspace: Path, limit: int = MAX_JOURNEYS) -> list[dict[str, Any]]:
    """Read the last *limit* valid journeys. Never raises.

    OSError (missing file, a directory where the file should be, a permission
    denial) and Unicode garbage both degrade to the journeys read so far, so a
    half-written log still answers with the sessions that are complete.
    """
    path = journey_path(workspace)
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        cleaned = _clean(record)
        if cleaned is not None:
            rows.append(cleaned)
    if limit > 0:
        rows = rows[-limit:]
    return rows


def _rate(part: int, whole: int) -> float | None:
    if whole <= 0:
        return None
    return round(part / whole, 3)


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    return int(statistics.median(values))


def _confidence(total: int) -> str:
    if total >= USABLE:
        return "solid"
    if total >= THIN:
        return "usable"
    return "thin"


def _persona_row(persona: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    runs = len(rows)
    bounced = sum(1 for row in rows if row["bounced"])
    views_total = sum(len(row["views"]) for row in rows)
    clicks_total = sum(row["clicks"] for row in rows)
    dwell = [row["dwell_ms"] for row in rows if row["dwell_ms"] > 0]
    exits: dict[str, int] = {}
    for row in rows:
        if row["bounced"] and row["last_view"]:
            exits[row["last_view"]] = exits.get(row["last_view"], 0) + 1
    top_exit = max(exits.items(), key=lambda item: item[1])[0] if exits else ""
    return {
        "id": persona,
        "runs": runs,
        "bounce_rate": _rate(bounced, runs),
        "median_dwell_ms": _median(dwell),
        "mean_clicks": round(clicks_total / runs, 2) if runs else None,
        "mean_views": round(views_total / runs, 2) if runs else None,
        "rage_journeys": sum(1 for row in rows if row["rage_clicks"] > 0),
        "top_exit": top_exit,
    }


def build_journey_report(workspace: Path) -> dict[str, Any]:
    """Aggregate the journey log into the payload ``/api/behavior/journeys`` serves.

    Never raises: an unreadable or absent log answers the honest empty state so
    the admin panel can explain how to produce real sessions instead of showing
    a plausible-looking zero.
    """
    try:
        rows = load_journeys(workspace)
    except Exception:  # noqa: BLE001 - the admin surface must never 500 on a broken log
        rows = []

    if not rows:
        return {
            "live": False,
            "total": 0,
            "personas": [],
            "bounce_rate": None,
            "median_dwell_ms": None,
            "median_boot_ms": None,
            "mean_clicks": None,
            "rage_journeys": 0,
            "page_errors": 0,
            "transitions": [],
            "last_views": [],
            "window": None,
            "confidence": "empty",
            "source": SOURCE,
            "how_to": HOW_TO,
            "note": "No journeys recorded yet — the log is empty because nothing has run, not because nobody bounced.",
        }

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["persona"], []).append(row)

    personas = [_persona_row(name, group) for name, group in sorted(grouped.items())]
    personas.sort(key=lambda item: (-item["runs"], item["id"]))

    total = len(rows)
    bounced = sum(1 for row in rows if row["bounced"])
    dwell = [row["dwell_ms"] for row in rows if row["dwell_ms"] > 0]
    clicks_total = sum(row["clicks"] for row in rows)

    exits: dict[str, int] = {}
    for row in rows:
        if row["bounced"] and row["last_view"]:
            exits[row["last_view"]] = exits.get(row["last_view"], 0) + 1
    last_views = [
        {"view": view, "count": count, "share": _rate(count, bounced)}
        for view, count in sorted(exits.items(), key=lambda item: (-item[1], item[0]))[:6]
    ]

    stamps = sorted(row["started_at"] for row in rows if row["started_at"])
    window = {"start": stamps[0], "end": stamps[-1]} if stamps else None

    # Counted per *journey*, not per occurrence: a visitor who bounced between
    # two rooms five times has still only walked that path once as a story.
    # So ``share`` can never exceed 1.0 and always reads as "how many sessions
    # took this step".
    pairs: dict[tuple[str, str], int] = {}
    for row in rows:
        for pair in set(row["transitions"]):
            pairs[pair] = pairs.get(pair, 0) + 1
    transitions = [
        {"from": src, "to": dst, "count": count, "share": _rate(count, total)}
        for (src, dst), count in sorted(pairs.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]

    return {
        "live": True,
        "total": total,
        "personas": personas,
        "bounce_rate": _rate(bounced, total),
        "median_dwell_ms": _median(dwell),
        "median_boot_ms": _median([row["boot_ms"] for row in rows if isinstance(row["boot_ms"], int)]),
        "mean_clicks": round(clicks_total / total, 2) if total else None,
        "rage_journeys": sum(1 for row in rows if row["rage_clicks"] > 0),
        "page_errors": sum(row["page_errors"] for row in rows),
        "transitions": transitions,
        "last_views": last_views,
        "window": window,
        "confidence": _confidence(total),
        "source": SOURCE,
        "how_to": HOW_TO,
        "note": "",
    }
