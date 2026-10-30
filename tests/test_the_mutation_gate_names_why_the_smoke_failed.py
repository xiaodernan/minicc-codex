"""M8-T534: "the smoke failed" only proves the chain when it failed for the chain's reason.

Measured at batch 522, the mutation job's step was

    if npm run test:web; then ... exit 1; fi

so every non-zero exit - Playwright without a browser, a web server that never
bound its port, a syntax error - reported the mutation as caught. The smoke's
own baseline against an unreachable provider fails at the completion assertion
(rc=1, ``web_smoke.mjs`` "product path task must reach completion_complete"),
but the step could not tell that failure apart from an infrastructure one.

The smoke now prints a stable ``SMOKE_FAILURE_CODE=<CODE>`` from its
product-path assertions, and ``scripts/web_smoke_verdict.py`` accepts exactly
the completion code. These cases drive that decision from synthetic logs in
both directions, and pin the two emit sites that keep the code real: the
assertion that names ``completion_complete`` and the CI step that reads the
verdict instead of the bare exit status.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERDICT = REPO_ROOT / "scripts" / "web_smoke_verdict.py"
SMOKE = REPO_ROOT / "tests" / "web_smoke.mjs"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _module():
    spec = importlib.util.spec_from_file_location("web_smoke_verdict", VERDICT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ci_job(name: str) -> str:
    ci = CI.read_text(encoding="utf-8")
    start = ci.index(f"  {name}:")
    rest = ci[start + len(name) + 3:]
    following = re.search(r"^  \S", rest, re.MULTILINE)
    return rest[: following.start()] if following else rest


def test_a_passing_smoke_is_not_a_caught_mutation() -> None:
    module = _module()
    caught, verdict = module.decide(0, "web smoke passed: timeline, product path, desktop, mobile\n")
    assert caught is False
    assert "MUTATION NOT CAUGHT" in verdict


def test_an_infrastructure_failure_names_no_mutation_reason() -> None:
    module = _module()
    log = (
        "browserType.launch: Executable doesn't exist at /home/runner/.cache/ms-playwright/chromium-1234/chrome-linux/chrome\n"
        "    at file:///home/runner/work/minicc/tests/web_smoke.mjs:407:3\n"
    )
    caught, verdict = module.decide(1, log)
    assert caught is False
    assert "without naming a failure code" in verdict


def test_the_completion_verdict_code_is_the_caught_mutation() -> None:
    module = _module()
    log = (
        "SMOKE_FAILURE_CODE=PRODUCT_PATH_NO_COMPLETION_VERDICT\n"
        "AssertionError [ERR_ASSERTION]: product path task must reach completion_complete\n"
    )
    caught, verdict = module.decide(1, log)
    assert caught is True
    assert verdict == "mutation caught: PRODUCT_PATH_NO_COMPLETION_VERDICT"


def test_a_different_product_path_code_is_not_attributed() -> None:
    module = _module()
    caught, verdict = module.decide(1, "SMOKE_FAILURE_CODE=PRODUCT_PATH_NO_TOOL_EVIDENCE\n")
    assert caught is False
    assert "PRODUCT_PATH_NO_TOOL_EVIDENCE" in verdict
    assert module.EXPECTED_CODE in verdict


def test_the_cli_exit_code_follows_the_verdict(tmp_path) -> None:
    caught_log = tmp_path / "caught.log"
    caught_log.write_text("SMOKE_FAILURE_CODE=PRODUCT_PATH_NO_COMPLETION_VERDICT\n", encoding="utf-8")
    caught = subprocess.run(
        [sys.executable, str(VERDICT), "--exit-code", "1", "--log", str(caught_log)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        check=False,
    )
    assert caught.returncode == 0, caught.stdout + caught.stderr
    assert "mutation caught" in caught.stdout

    passed_log = tmp_path / "passed.log"
    passed_log.write_text("web smoke passed: timeline, product path, desktop, mobile\n", encoding="utf-8")
    passed = subprocess.run(
        [sys.executable, str(VERDICT), "--exit-code", "0", "--log", str(passed_log)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        check=False,
    )
    assert passed.returncode == 1, passed.stdout + passed.stderr
    assert "MUTATION NOT CAUGHT" in passed.stdout


def test_a_missing_log_is_not_a_caught_mutation(tmp_path) -> None:
    missing = subprocess.run(
        [sys.executable, str(VERDICT), "--exit-code", "1", "--log", str(tmp_path / "never-written.log")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        check=False,
    )
    assert missing.returncode == 1, missing.stdout + missing.stderr
    assert "not attributed" in missing.stdout


def test_the_completion_assertion_emits_the_code_the_verdict_accepts() -> None:
    module = _module()
    source = SMOKE.read_text(encoding="utf-8")
    assert module.EXPECTED_CODE in source, (
        "the verdict accepts a code the smoke never emits; the mutation step would reject every real failure"
    )
    assert re.search(
        r'failProductPath\(\s*"PRODUCT_PATH_NO_COMPLETION_VERDICT"\s*,\s*'
        r'"product path task must reach completion_complete',
        source,
    ), "the expected code must be emitted by the completion assertion itself, not somewhere else in the file"


def test_the_ci_step_reads_the_smoke_log_through_the_verdict() -> None:
    block = _ci_job("web-smoke-mutation")
    assert "npm run test:web > web-smoke-mutation.log 2>&1" in block, (
        "the smoke's output must be captured for the verdict, or the code is unreadable"
    )
    assert 'python scripts/web_smoke_verdict.py --exit-code "$rc" --log web-smoke-mutation.log' in block
    assert "web-smoke-mutation.log" in block.split("Upload mutation logs", 1)[-1], (
        "the captured log must be uploaded, otherwise a rejected mutation has no evidence to read"
    )
    assert "if npm run test:web; then" not in block, (
        "a bare non-zero exit must not report the mutation as caught; that is the defect this gate closes"
    )
