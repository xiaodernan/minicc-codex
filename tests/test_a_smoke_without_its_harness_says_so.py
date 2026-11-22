"""M8-T1304: a smoke whose own server is missing says so, in its own words.

Measured on this repository with nothing bound on ``127.0.0.1:8799``: each of
the five suites tried exited 1 after launching a browser, ``web_smoke.mjs``
named ``TIMELINE_SUITE_FAILED`` - a product suite that never ran, because its
catch block reports any failure of the block it wraps - while
``admin_smoke.mjs``, ``orbit_smoke.mjs``, ``en_cjk_smoke.mjs`` and
``manual_smoke.mjs`` exited 1 naming no code at all. Both readings put a missing
harness inside the product's vocabulary, and the mutation step cannot tell them
apart from a caught regression.

Every suite that drives a live URL now probes ``/api/health`` before
``chromium.launch`` and exits 3 naming ``HARNESS_UNREACHABLE``. The probe is
tested here without a browser: the emit path lives in
``tests/web_smoke_suites.mjs``, and the verdict's answer is driven through its
own CLI so the exit code the CI step sees is the one under test.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SUITES = REPO_ROOT / "tests" / "web_smoke_suites.mjs"
VERDICT = REPO_ROOT / "scripts" / "web_smoke_verdict.py"
DEAD_URL = "http://127.0.0.1:8799"

# The five measured pre-guard runs took 4-5s of wall clock each, every one of
# them launching a browser first. The bound is that ceiling multiplied by four:
# a loaded machine must not turn this into a flake, and a probe that regressed
# into Playwright's own 30s navigation timeout would still be caught here.
MEASURED_BROWSER_FAILURE_SECONDS = 5.0
PROBE_SECONDS_ALLOWED = MEASURED_BROWSER_FAILURE_SECONDS * 4


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


def _verdict_argv(exit_code: int, log: Path) -> list[str]:
    return [sys.executable, str(VERDICT), "--exit-code", str(exit_code), "--log", str(log)]


def _run_verdict(tmp_path, text: str, exit_code: int = 3, name: str = "smoke.log"):
    log = tmp_path / name
    log.write_text(text, encoding="utf-8")
    return subprocess.run(
        _verdict_argv(exit_code, log),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        timeout=120,
        check=False,
    )


def _live_url_suites() -> list[Path]:
    return sorted(
        path
        for path in (REPO_ROOT / "tests").glob("*_smoke.mjs")
        if "process.env.MINICC_WEB_URL" in path.read_text(encoding="utf-8")
    )


def test_a_refused_port_names_the_harness_instead_of_a_product_suite() -> None:
    started = time.monotonic()
    result = _node(
        f'import {{ requireHarnessOrExit }} from "{SUITES.as_uri()}";\n'
        "const exitCodes = [];\n"
        f'await requireHarnessOrExit("{DEAD_URL}", {{ exitImpl: (code) => exitCodes.push(code) }});\n'
        'console.log("EXITED_WITH", JSON.stringify(exitCodes));\n'
    )
    elapsed = time.monotonic() - started
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SMOKE_FAILURE_CODE=HARNESS_UNREACHABLE" in result.stderr, result.stderr
    assert "EXITED_WITH [3]" in result.stdout, (
        f"a missing harness must exit with its own code, not 1: {result.stdout}"
    )
    assert DEAD_URL + "/api/health" in result.stderr, result.stderr
    assert "MINICC_WEB_URL" in result.stderr, "the message must name the knob that points at a server"
    assert "no suite ran" in result.stderr, result.stderr
    assert "TIMELINE_SUITE_FAILED" not in result.stderr, "the harness must not borrow a product suite's code"
    assert elapsed < PROBE_SECONDS_ALLOWED, (
        f"the probe took {elapsed:.1f}s; the browser failure it replaces measured "
        f"{MEASURED_BROWSER_FAILURE_SECONDS}s, so the step would pay for both"
    )


def test_a_server_answering_the_probe_lets_the_suite_through() -> None:
    script = (
        f'import {{ createServer }} from "node:http";\n'
        f'import {{ requireHarnessOrExit }} from "{SUITES.as_uri()}";\n'
        'const server = createServer((req, res) => {\n'
        '  res.writeHead(200, { "content-type": "application/json" });\n'
        '  res.end(JSON.stringify({ ok: true, service: "minicc" }));\n'
        "});\n"
        "await new Promise((resolve) => server.listen(0, \"127.0.0.1\", resolve));\n"
        'const baseUrl = `http://127.0.0.1:${server.address().port}`;\n'
        "let exited = null;\n"
        "const harness = await requireHarnessOrExit(baseUrl, { exitImpl: (code) => { exited = code; } });\n"
        "server.close();\n"
        'console.log(JSON.stringify({ ok: harness.ok, exited, path: harness.probeUrl.replace(baseUrl, "") }));\n'
    )
    result = _node(script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SMOKE_FAILURE_CODE" not in result.stderr, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"ok": True, "exited": None, "path": "/api/health"}, payload


def test_a_port_that_answers_but_is_not_the_app_is_not_the_harness() -> None:
    # The probe would otherwise accept any listener; the mutation step needs to
    # know the minicc server bound the port it is about to drive.
    for label, fetch_stub in (
        ("http 503", "{ ok: false, status: 503, json: async () => ({}) }"),
        ("foreign payload", '{ ok: true, json: async () => ({ ok: true, service: "something else" }) }'),
        ("no json", "{ ok: true, json: async () => { throw new Error('not json'); } }"),
    ):
        result = _node(
            f'import {{ requireHarness }} from "{SUITES.as_uri()}";\n'
            f'const r = await requireHarness("{DEAD_URL}", {{ fetchImpl: async () => ({fetch_stub}) }});\n'
            'console.log(JSON.stringify(r));\n'
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["ok"] is False, f"{label} read as a healthy harness: {payload}"
        assert payload["detail"], f"{label} said the harness was missing without saying why: {payload}"


def test_the_probe_runs_before_any_browser_is_launched() -> None:
    suites = _live_url_suites()
    assert len(suites) >= 13, f"only {len(suites)} live-URL suites found; the roster is the denominator"
    for path in suites:
        source = path.read_text(encoding="utf-8")
        assert "await requireHarnessOrExit(baseUrl);" in source, (
            f"{path.name} drives a live URL but never probes it: a missing server reaches the log "
            "as this suite's own failure code, or as no code at all"
        )
        guard = source.index("await requireHarnessOrExit(baseUrl);")
        launch = source.index("chromium.launch")
        assert guard < launch, f"{path.name}: the browser launches before the harness is probed"
        assert 'requireHarnessOrExit' in source.splitlines()[0] or any(
            line.startswith("import") and "requireHarnessOrExit" in line for line in source.splitlines()
        ), f"{path.name} must take the probe from the shared module"
        assert "function requireHarness" not in source, (
            f"{path.name} defines its own probe; a private copy is the drift this module exists to prevent"
        )


def test_the_shared_module_and_the_verdict_agree_on_the_code_and_the_exit() -> None:
    module_source = SUITES.read_text(encoding="utf-8")
    verdict_source = VERDICT.read_text(encoding="utf-8")
    code = re.search(r'HARNESS_UNREACHABLE_CODE = "([A-Z_]+)"', module_source)
    exit_code = re.search(r"HARNESS_UNREACHABLE_EXIT = (\d+)", module_source)
    verdict_code = re.search(r'HARNESS_CODE = "([A-Z_]+)"', verdict_source)
    verdict_exit = re.search(r"HARNESS_EXIT = (\d+)", verdict_source)
    assert code and exit_code and verdict_code and verdict_exit, "one of the two sides lost its constant"
    assert code.group(1) == verdict_code.group(1), "the smoke and the verdict name different codes"
    assert exit_code.group(1) == verdict_exit.group(1), "the smoke and the verdict exit with different numbers"
    assert exit_code.group(1) not in {"0", "1"}, (
        "a harness failure must not share an exit code with 'caught' (0) or 'unattributed' (1)"
    )


def test_the_verdict_says_the_step_tested_nothing(tmp_path) -> None:
    result = _run_verdict(tmp_path, f"SMOKE_FAILURE_CODE={DEAD_URL.rsplit('/', 1)[-1].upper()}_IRRELEVANT\n")
    assert result.returncode == 1, result.stdout + result.stderr
    result = _run_verdict(
        tmp_path, "page.goto: net::ERR_CONNECTION_REFUSED\nSMOKE_FAILURE_CODE=HARNESS_UNREACHABLE\n"
    )
    assert result.returncode == 3, f"a step that ran zero suites exited {result.returncode}: {result.stdout}"
    assert "harness" in result.stdout.lower(), result.stdout
    assert "tested nothing" in result.stdout, result.stdout
    assert "mutation caught" not in result.stdout, result.stdout


def test_the_harness_answer_is_not_silenced_by_a_later_product_code(tmp_path) -> None:
    # A suite that probes, fails, and still announces a product code is lying
    # twice; the harness is the fact the step needs, whichever order it arrives.
    forward = _run_verdict(
        tmp_path,
        "SMOKE_FAILURE_CODE=HARNESS_UNREACHABLE\nSMOKE_FAILURE_CODE=PRODUCT_PATH_NO_COMPLETION_VERDICT\n",
    )
    reverse = _run_verdict(
        tmp_path,
        "SMOKE_FAILURE_CODE=PRODUCT_PATH_NO_COMPLETION_VERDICT\nSMOKE_FAILURE_CODE=HARNESS_UNREACHABLE\n",
        name="reverse.log",
    )
    for name, result in (("forward", forward), ("reverse", reverse)):
        assert result.returncode == 3, f"{name}: {result.stdout}"
        assert "tested nothing" in result.stdout, f"{name}: {result.stdout}"
    caught = _run_verdict(
        tmp_path, "SMOKE_FAILURE_CODE=PRODUCT_PATH_NO_COMPLETION_VERDICT\n", exit_code=1, name="caught.log"
    )
    assert caught.returncode == 0, caught.stdout
    assert "mutation caught" in caught.stdout, caught.stdout


def test_the_mutation_step_still_drives_the_verdict_through_the_smoke_log() -> None:
    block = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = block.split("web-smoke-mutation:", 1)[1]
    assert 'python scripts/web_smoke_verdict.py --exit-code "$rc" --log web-smoke-mutation.log' in job
    assert "MINICC_WEB_URL" in job, (
        "the smoke reads its server from MINICC_WEB_URL; a step that stops setting it would "
        "make every run report a missing harness"
    )
