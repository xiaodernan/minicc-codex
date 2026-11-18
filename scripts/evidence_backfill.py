#!/usr/bin/env python
"""M8-T1207 - capture one real CI run into the evidence gate, once, on demand.

The Java service (minicc-cloud-evidence) backfills a run's truth exactly once
when asked for it by id; this script asks, so the admin tile's
``?latest=1`` has something real to show. Nothing is re-run, nothing is
dispatched - the evidence is the record, not a rehearsal.

Usage:
    python scripts/evidence_backfill.py --run-id 44229273754
    python scripts/evidence_backfill.py --run-id 44229273754 --url http://127.0.0.1:8088
"""

from __future__ import annotations

import argparse
import json
import urllib.request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidence-backfill", description=__doc__)
    parser.add_argument("--run-id", required=True, help="the GitHub Actions run id (digits)")
    parser.add_argument("--url", default="http://127.0.0.1:8088", help="evidence gate base URL")
    args = parser.parse_args(argv)

    if not args.run_id.isdigit():
        parser.error("--run-id must be the GitHub run id (digits only)")

    target = f"{args.url.rstrip('/')}/api/evidence?run_id={args.run_id}"
    try:
        with urllib.request.urlopen(target, timeout=30) as response:
            body = response.read(1024 * 512)
            payload = json.loads(body)
    except Exception as exc:  # noqa: BLE001 - the operator wants the honest failure line
        print(f"evidence backfill failed: {type(exc).__name__}: {exc}")
        return 1

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if not payload.get("present"):
        print("evidence store says not present; check the Java service log for the reason")
        return 1
    latest = payload.get("latest") or {}
    print(f"captured run {latest.get('run_id')}: conclusion={latest.get('conclusion')} "
          f"job={latest.get('job_name')} sha={str(latest.get('head_sha') or '')[:7]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
