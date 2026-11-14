"""minicc.roadmap_archive — the ledger as a browsable fact pack.

``/api/digest`` counts this document (batches / lines). This module is
the same document read shape-wise: every ``## 批次 N - M8-TNNN: title``
heading, parsed once per request, grouped by century into eras. The
front-end Archive panel renders it as a vertical museum timeline.

Design rules (same discipline as ``minicc.digest``):
- never raises: a missing or odd document degrades to an empty archive
- no network, no ``.minicc`` access, no writes of any kind
- bounded output: titles are clipped to 220 chars; no prose is echoed
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_HEADING = re.compile(r"^## 批次 (\d+)\s*[—–-]+\s*(.*)$", re.MULTILINE)
_SEPARATORS = re.compile(r"[：:]")
_TITLE_MAX = 220


def _split_id_and_title(rest: str) -> tuple[str | None, str]:
    parts = _SEPARATORS.split(rest, 1)
    if len(parts) == 2:
        return parts[0].strip() or None, parts[1].strip()
    return None, rest.strip()


def build_roadmap_archive(roadmap: Path | str) -> dict[str, Any]:
    """Parse ``docs/ROADMAP_TO_PRODUCT.md`` into a bounded fact pack."""
    path = Path(roadmap)
    payload: dict[str, Any] = {
        "schema_version": "minicc.roadmap-archive.v1",
        "is_roadmap": False,
        "total": 0,
        "entries": [],
        "eras": [],
    }
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return payload
    entries: list[dict[str, Any]] = []
    for match in _HEADING.finditer(text):
        batch = int(match.group(1))
        ident, title = _split_id_and_title(match.group(2))
        entries.append({
            "batch": batch,
            "id": ident,
            "title": title[:_TITLE_MAX],
        })
    if not entries:
        return payload
    payload["is_roadmap"] = True
    payload["total"] = len(entries)
    payload["entries"] = entries
    max_batch = max(entry["batch"] for entry in entries)
    eras = []
    start = 0
    while start <= max_batch:
        segment = [entry for entry in entries if start <= entry["batch"] < start + 100]
        if segment:
            eras.append({
                "from": start,
                "to": start + 99,
                "count": len(segment),
            })
        start += 100
    payload["eras"] = eras
    return payload
