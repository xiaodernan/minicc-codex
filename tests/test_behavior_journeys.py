"""M8-T1289: the synthetic-visitor aggregate must tell the truth about its sample.

These tests never launch a browser. They pin the aggregation contract the admin
panel depends on: honest empty state, malformed lines skipped instead of
rescued, bounded reads, per-persona sample sizes, and a confidence band that
keeps a three-session bounce rate from reading like a product fact.
"""

from __future__ import annotations

import json
from pathlib import Path

from minicc.behavior_journeys import (
    HOW_TO,
    MAX_JOURNEYS,
    MAX_VIEWS,
    build_journey_report,
    journey_path,
    load_journeys,
)


def _write(workspace: Path, rows: list[object]) -> Path:
    path = journey_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [row if isinstance(row, str) else json.dumps(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _journey(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "persona": "wanderer",
        "started_at": "2026-11-22T04:00:00.000Z",
        "dwell_ms": 2400,
        "views": ["pulse", "manual"],
        "clicks": 3,
        "rage_clicks": 0,
        "bounced": False,
        "exit_reason": "completed",
        "last_view": "manual",
        "synthetic": True,
    }
    base.update(overrides)
    return base


def test_an_absent_log_is_an_honest_empty_state(tmp_path: Path) -> None:
    report = build_journey_report(tmp_path)
    assert report["live"] is False
    assert report["total"] == 0
    assert report["personas"] == []
    assert report["bounce_rate"] is None
    assert report["median_dwell_ms"] is None
    assert report["last_views"] == []
    assert report["window"] is None
    assert report["confidence"] == "empty"
    assert report["how_to"] == HOW_TO
    assert report["source"] == "synthetic-real-execution"
    assert "empty" in str(report["note"])


def test_aggregates_count_what_the_sessions_actually_did(tmp_path: Path) -> None:
    _write(
        tmp_path,
        [
            _journey(persona="wanderer", dwell_ms=1000, views=["pulse", "manual"], clicks=4, bounced=True, last_view="pulse", exit_reason="lost"),
            _journey(persona="wanderer", dwell_ms=3000, views=["pulse", "manual", "atlas", "archive"], clicks=6, bounced=True, last_view="manual", exit_reason="lost"),
            _journey(persona="wanderer", dwell_ms=5000, views=["pulse", "manual", "atlas"], clicks=2, last_view="atlas"),
            _journey(persona="reader", dwell_ms=9000, views=["manual"], clicks=0, last_view="manual", started_at="2026-11-22T05:00:00.000Z"),
        ],
    )
    report = build_journey_report(tmp_path)

    assert report["live"] is True
    assert report["total"] == 4
    assert report["bounce_rate"] == 0.5
    assert report["median_dwell_ms"] == 4000
    assert report["mean_clicks"] == 3.0
    assert report["confidence"] == "thin"

    wanderer = next(row for row in report["personas"] if row["id"] == "wanderer")
    assert wanderer["runs"] == 3
    assert wanderer["bounce_rate"] == 0.667
    assert wanderer["median_dwell_ms"] == 3000
    assert wanderer["mean_clicks"] == 4.0
    assert wanderer["mean_views"] == 3.0
    assert wanderer["top_exit"] in {"pulse", "manual"}

    exits = {row["view"]: row["count"] for row in report["last_views"]}
    assert exits["pulse"] == 1 and exits["manual"] == 1
    assert report["window"] == {"start": "2026-11-22T04:00:00.000Z", "end": "2026-11-22T05:00:00.000Z"}


def test_malformed_lines_are_skipped_not_rescued(tmp_path: Path) -> None:
    _write(
        tmp_path,
        [
            "not json at all",
            json.dumps(["a", "list", "not", "a", "journey"]),
            json.dumps({"persona": "", "dwell_ms": 900}),
            json.dumps({"dwell_ms": 900}),
            json.dumps(_journey(persona="impatient", dwell_ms=800, bounced=True)),
        ],
    )
    rows = load_journeys(tmp_path)
    assert len(rows) == 1
    assert rows[0]["persona"] == "impatient"
    report = build_journey_report(tmp_path)
    assert report["total"] == 1
    assert report["bounce_rate"] == 1.0


def test_reads_are_bounded_and_ids_are_clipped(tmp_path: Path) -> None:
    rows = [_journey(persona=f"p{index % 3}", dwell_ms=1000 + index) for index in range(MAX_JOURNEYS + 25)]
    _write(tmp_path, rows)
    loaded = load_journeys(tmp_path)
    assert len(loaded) == MAX_JOURNEYS
    # the tail is kept: the newest sessions are the interesting ones
    assert loaded[-1]["dwell_ms"] == 1000 + MAX_JOURNEYS + 24

    _write(
        tmp_path,
        [
            _journey(
                persona="x" * 90,
                views=[f"v{index}" for index in range(MAX_VIEWS + 10)],
                last_view="y" * 90,
            )
        ],
    )
    row = load_journeys(tmp_path)[0]
    assert len(row["persona"]) == 32
    assert len(row["views"]) == MAX_VIEWS
    assert len(row["last_view"]) == 32


def test_confidence_bands_follow_the_sample_size(tmp_path: Path) -> None:
    _write(tmp_path, [_journey() for _ in range(12)])
    assert build_journey_report(tmp_path)["confidence"] == "usable"
    _write(tmp_path, [_journey() for _ in range(31)])
    assert build_journey_report(tmp_path)["confidence"] == "solid"


def test_an_unreadable_log_never_raises(tmp_path: Path) -> None:
    path = journey_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()  # a directory where the log should be
    assert load_journeys(tmp_path) == []
    report = build_journey_report(tmp_path)
    assert report["live"] is False
    assert report["total"] == 0


def test_rage_bursts_are_counted_separately(tmp_path: Path) -> None:
    _write(
        tmp_path,
        [
            _journey(persona="wanderer", rage_clicks=2),
            _journey(persona="wanderer", rage_clicks=0),
            _journey(persona="impatient", rage_clicks=1),
        ],
    )
    report = build_journey_report(tmp_path)
    assert report["rage_journeys"] == 2
    wanderer = next(row for row in report["personas"] if row["id"] == "wanderer")
    assert wanderer["rage_journeys"] == 1


def test_boot_time_keeps_null_and_zero_apart(tmp_path: Path) -> None:
    # 0 would claim "clickable instantly"; null says "never became clickable".
    # A report that merges them would flatter the product, so they stay apart.
    _write(
        tmp_path,
        [
            _journey(persona="wanderer", boot_ms=900),
            _journey(persona="wanderer", boot_ms=None),
            _journey(persona="reader", boot_ms=1500, page_errors=2),
        ],
    )
    report = build_journey_report(tmp_path)
    assert report["median_boot_ms"] == 1200
    assert report["page_errors"] == 2
    assert load_journeys(tmp_path)[1]["boot_ms"] is None
