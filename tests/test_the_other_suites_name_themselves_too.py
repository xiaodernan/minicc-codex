"""M8-T537: the three other suites name themselves when they fail.

The mutation step reads the smoke through ``scripts/web_smoke_verdict.py``,
which accepts only ``PRODUCT_PATH_NO_COMPLETION_VERDICT``. Before this batch,
the timeline / desktop / mobile suites failed with a bare assertion: the
verdict could only say "without naming a failure code", which is the same
sentence an infrastructure failure gets. Now each suite runs inside
``runNamedSuite(code, ...)`` and prints ``SMOKE_FAILURE_CODE=<SUITE>_FAILED``,
so a rejected mutation names the suite instead of shrugging.

The emit path lives in ``tests/web_smoke_suites.mjs`` so a node child can
exercise it without launching Chromium: a throwing run must print exactly one
code, a passing run must print none, and the product path's own code must not
be shadowed by a second one from an outer wrapper.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE = REPO_ROOT / "tests" / "web_smoke.mjs"
SUITES = REPO_ROOT / "tests" / "web_smoke_suites.mjs"
VERDICT = REPO_ROOT / "scripts" / "web_smoke_verdict.py"

SUITE_CODES = (
    ("TIMELINE_SUITE_FAILED", "runAgentTimelineSmoke"),
    ("DESKTOP_SUITE_FAILED", "runDesktopSmoke"),
    ("MOBILE_SUITE_FAILED", "runMobileSmoke"),
)


def _node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
        check=False,
    )


def _module():
    spec = importlib.util.spec_from_file_location("web_smoke_verdict", VERDICT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_failed_suite_prints_its_own_code() -> None:
    result = _node(
        f'import {{ runNamedSuite }} from "{SUITES.as_uri()}";\n'
        'await runNamedSuite("TIMELINE_SUITE_FAILED", () => { throw new Error("boom"); });\n'
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert "SMOKE_FAILURE_CODE=TIMELINE_SUITE_FAILED" in result.stderr, result.stderr


def test_a_passing_suite_prints_no_code() -> None:
    result = _node(
        f'import {{ runNamedSuite }} from "{SUITES.as_uri()}";\n'
        'await runNamedSuite("TIMELINE_SUITE_FAILED", () => {});\n'
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SMOKE_FAILURE_CODE" not in result.stderr, result.stderr


def test_an_outer_wrapper_does_not_shadow_the_product_path_code() -> None:
    script = (
        f'import {{ failProductPath, runNamedSuite }} from "{SUITES.as_uri()}";\n'
        'try { await runNamedSuite("TIMELINE_SUITE_FAILED", '
        '() => failProductPath("PRODUCT_PATH_NO_TOOL_EVIDENCE", "x")); } catch {}\n'
    )
    result = _node(script)
    assert "SMOKE_FAILURE_CODE=PRODUCT_PATH_NO_TOOL_EVIDENCE" in result.stderr, result.stderr
    assert "TIMELINE_SUITE_FAILED" not in result.stderr, (
        "the outer suite code shadowed the product-path code; the verdict would reject "
        "the very failure the mutation injected"
    )


def test_every_suite_call_is_wrapped_with_its_own_code() -> None:
    source = SMOKE.read_text(encoding="utf-8")
    for code, function in SUITE_CODES:
        assert re.search(
            rf'await runNamedSuite\(\s*"{code}"\s*,\s*\(\)\s*=>\s*{function}\(browser\)\s*\)',
            source,
        ), f"{function} must run inside runNamedSuite(\"{code}\", ...)"
    assert "await runProductPathSmoke(browser);" in source, (
        "the product path names its own codes; wrapping it would replace them with a suite code"
    )
    assert not re.search(
        r'runNamedSuite\(\s*"[A-Z_]+"\s*,\s*\(\)\s*=>\s*runProductPathSmoke', source
    ), "the product path must not be wrapped; its five codes are finer than a suite code"


def test_the_smoke_takes_the_emit_sites_from_the_shared_module() -> None:
    source = SMOKE.read_text(encoding="utf-8")
    assert 'from "./web_smoke_suites.mjs"' in source, (
        "a second copy of the emit sites in web_smoke.mjs would drift from the module the "
        "node child tests exercise"
    )
    assert "function failProductPath(" not in source, "the smoke still defines its own failProductPath"
    module = SUITES.read_text(encoding="utf-8")
    assert 'SMOKE_FAILURE_CODE=${code}' in module
    assert len({code for code, _ in SUITE_CODES}) == 3, "two suites would share a code"


def test_the_verdict_names_the_failing_suite() -> None:
    module = _module()
    caught, verdict = module.decide(1, "SMOKE_FAILURE_CODE=MOBILE_SUITE_FAILED\n")
    assert caught is False
    assert "MOBILE_SUITE_FAILED" in verdict, verdict
    assert module.EXPECTED_CODE in verdict, verdict
    assert "without naming a failure code" not in verdict, (
        "a named suite failure must not read like an infrastructure error"
    )
