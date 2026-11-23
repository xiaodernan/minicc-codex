"""M8-T1305: the visitor-journey driver names a missing server as its own fault.

Before this guard, ``scripts/behavior_sim.mjs`` pointed at a port with nothing
bound launched Chromium, waited the full ``--ready-timeout`` (45s) and then wrote
one ``could-not-drive`` bounce per persona - a missing workbench reported as
visitor behaviour. A dead port is an environment problem; no journey ran, so no
number it produced can say anything about how people use the product.

The emit path lives in the side-effect-free ``scripts/behavior_harness.mjs`` so
it can be driven with an injected fetch / exitImpl without a browser. One test
runs the real driver against a dead port to prove the guard sits before
``chromium.launch`` and before any journey is appended.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "scripts" / "behavior_harness.mjs"
DRIVER = REPO_ROOT / "scripts" / "behavior_sim.mjs"
DEAD_URL = "http://127.0.0.1:8797"

# The old path spent the full READY_TIMEOUT (45s) after launching a browser. A
# 12s ceiling is a quarter of that: a healthy probe on a refused port finishes
# in well under a second, while any regression into Playwright's navigation
# timeout blows the bound.
PROBE_SECONDS_ALLOWED = 12.0


def _node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
        timeout=120,
        check=False,
    )


def _drive_probe(fetch_expr: str, url: str = DEAD_URL) -> subprocess.CompletedProcess:
    script = (
        f'import {{ requireBehaviorHarness, probeBehaviorHarness }} from "{HARNESS.as_uri()}";\n'
        "const codes = [];\n"
        f"const fetchImpl = {fetch_expr};\n"
        f'await requireBehaviorHarness("{url}", {{ fetchImpl, exitImpl: (c) => codes.push(c) }});\n'
        'console.log("EXITED_WITH", JSON.stringify(codes));\n'
    )
    return _node(script)


def _healthy_fetch() -> str:
    # A real Response-shaped object: ok=true and the exact minicc health payload.
    return "async () => ({ ok: true, json: async () => ({ ok: true, service: 'minicc' }) })"


def test_refused_connection_names_the_harness_with_a_dedicated_code() -> None:
    result = _drive_probe("globalThis.fetch")
    assert result.returncode == 0, result.stderr
    assert f"EXITED_WITH [{3}]" in result.stdout, result.stdout
    assert "BEHAVIOR_HARNESS_UNREACHABLE" in result.stderr, result.stderr
    assert "SMOKE_FAILURE_CODE=BEHAVIOR_HARNESS_UNREACHABLE" in result.stderr
    # It must not borrow a product/visitor vocabulary.
    assert "could-not-drive" not in result.stderr
    assert "bounce" not in result.stderr.lower()


def test_refused_connection_fails_fast_without_a_browser(tmp_path) -> None:
    out = tmp_path / "journeys.jsonl"
    started = time.monotonic()
    result = subprocess.run(
        [
            "node",
            str(DRIVER),
            "--url",
            DEAD_URL,
            "--runs",
            "1",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
        timeout=120,
        check=False,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    elapsed = time.monotonic() - started
    assert result.returncode == 3, (result.returncode, result.stderr)
    assert "BEHAVIOR_HARNESS_UNREACHABLE" in result.stderr, result.stderr
    assert elapsed < PROBE_SECONDS_ALLOWED, f"dead-port probe took {elapsed:.1f}s"
    # No browser journey was measured; nothing should have been appended.
    assert not out.exists(), "a dead port must not record visitor journeys"


def test_healthy_payload_passes_through_without_exiting() -> None:
    result = _drive_probe(_healthy_fetch())
    assert result.returncode == 0, result.stderr
    assert "EXITED_WITH []" in result.stdout, result.stdout
    assert "BEHAVIOR_HARNESS_UNREACHABLE" not in result.stderr


def test_a_stranger_answer_is_not_mistaken_for_the_harness() -> None:
    cases = {
        "non_minicc_200": "async () => ({ ok: true, json: async () => ({ ok: true, service: 'someone-else' }) })",
        "service_503": "async () => ({ ok: false, status: 503 })",
        "non_json": "async () => ({ ok: true, json: async () => { throw new Error('bad json'); } })",
    }
    for name, fetch_expr in cases.items():
        result = _drive_probe(fetch_expr)
        assert result.returncode == 0, (name, result.stderr)
        assert f"EXITED_WITH [{3}]" in result.stdout, (name, result.stdout)
        assert "BEHAVIOR_HARNESS_UNREACHABLE" in result.stderr, (name, result.stderr)


def test_probe_url_is_derived_from_the_given_base() -> None:
    result = _node(
        f'import {{ probeBehaviorHarness }} from "{HARNESS.as_uri()}";\n'
        f"const r = await probeBehaviorHarness('{DEAD_URL}', {{ fetchImpl: globalThis.fetch }});\n"
        'console.log(r.probeUrl);\n'
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{DEAD_URL}/api/health", result.stdout


def test_driver_calls_the_guard_before_launching_chromium() -> None:
    source = DRIVER.read_text(encoding="utf-8")
    assert 'import { requireBehaviorHarness } from "./behavior_harness.mjs";' in source
    guard = source.index("await requireBehaviorHarness(BASE_URL)")
    launch = source.index("chromium.launch(")
    assert guard < launch, "the harness guard must run before a browser is launched"
    harness = HARNESS.read_text(encoding="utf-8")
    assert 'export const BEHAVIOR_HARNESS_UNREACHABLE = "BEHAVIOR_HARNESS_UNREACHABLE";' in harness
    assert "export const BEHAVIOR_HARNESS_UNREACHABLE_EXIT = 3;" in harness
    assert "BEHAVIOR_HARNESS_UNREACHABLE" in source or "requireBehaviorHarness" in source
