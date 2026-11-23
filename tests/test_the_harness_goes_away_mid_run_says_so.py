"""M8-T1321: a server that dies mid-suite is the step's answer, not the suite's.

Measured on this repository with the harness killed a few seconds after each
suite started (``scratch/measure1305/summary.tsv``, ports 8801-8804): every one
of the four exited 1, and what they left behind differed by suite, not by cause.
``orbit_smoke`` printed a ``net::ERR_`` line, ``stategraph_smoke`` a
``page.evaluate: TypeError: Failed to fetch``, ``admin_smoke`` an assertion about
the panel's own context tile, and ``web_smoke`` - the one the mutation gate
trusts - named ``PRODUCT_PATH_NO_COMPLETION_VERDICT``, a real product code, for a
run whose server had stopped existing. None of the four named the harness.

M8-T1304's probe cannot help here: it answers before the browser launches, when
the server is by definition still alive. So each suite now asks the same question
again at the moment it fails. The failure's own shape is deliberately not the
judge - a quoted Playwright sentence inside an assertion would convict the
product for a dead server - and the answer comes from ``/api/health``, which is
what decides whether the run gets ``HARNESS_LOST`` (exit 3) or its own stack
(exit 1).

Asking that question turned up a second member of the same defect class, this
time in the guard itself: the probe ran on ``globalThis.fetch``, whose pooled
socket stays open for seconds after the answer, and a ``process.exit`` taken with
that handle mid-close does not exit - it aborts in libuv (0xC0000409). The step
that existed to say "the harness went away" was itself dying in a way the log
could not attribute. The probe is now a one-shot ``node:http`` call that answers
only once its socket has closed, which is what the exit-code tests below are able
to demand a real exit code rather than a crash number.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SUITES = REPO_ROOT / "tests" / "web_smoke_suites.mjs"
VERDICT = REPO_ROOT / "scripts" / "web_smoke_verdict.py"

# A named directory the children are written into, kept out of the repository so a
# run cannot be mistaken for a suite that pytest would collect.
_CHILD_DIR = Path(tempfile.gettempdir()) / "minicc-harness-loss-children"


def _module_constant(name: str) -> int:
    found = re.search(rf"export const {name} = (\d+);", SUITES.read_text(encoding="utf-8"))
    assert found, f"tests/web_smoke_suites.mjs no longer exports a numeric {name}"
    return int(found.group(1))


HARNESS_LOST_EXIT = _module_constant("HARNESS_LOST_EXIT")

# The re-probe is the only new work a failing suite does, and requireHarness
# bounds it at 4000ms. Four times that, plus the child's own start-up, is the
# ceiling a honest guard cannot exceed without becoming the thing it reports.
PROBE_SECONDS_ALLOWED = 20.0

# One node start-up (measured 0.4-0.9s on this box) plus a loopback health call on
# a socket that closes when it is done. The same probe through globalThis.fetch
# held the loop 4.17s after answering, which is the number this ceiling exists to
# keep out of the suite.
PROBE_DRAIN_SECONDS_ALLOWED = 2.0

HEALTH_SERVER_PREAMBLE = """
import { createServer } from "node:http";
"""

LIVE_HEALTH_SERVER = """
let serving = true;
const server = createServer((req, res) => {
  if (!serving) {
    req.destroy();
    return;
  }
  res.writeHead(200, { "content-type": "application/json" });
  res.end(JSON.stringify({ ok: true, service: "minicc" }));
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const baseUrl = `http://127.0.0.1:${server.address().port}`;
server.unref();
const decided = [];
"""


def _node(script: str) -> subprocess.CompletedProcess:
    """Run one child the way a suite runs: a file on disk, handed to node itself.

    A file is the shape the suites actually have, and `node -e` puts the same
    source on Node's own module-evaluation exit path - one more difference between
    the instrument and the thing it is measuring. (The libuv abort first blamed on
    that difference follows the probe's transport, not the driver: see
    `closedSocketHealthCall`.)
    """
    child = _CHILD_DIR / "child_suite.mjs"
    child.parent.mkdir(parents=True, exist_ok=True)
    child.write_text(script, encoding="utf-8")
    started = time.monotonic()
    result = subprocess.run(
        ["node", child.name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(child.parent),
        timeout=120,
        check=False,
    )
    result.elapsed = time.monotonic() - started
    return result


def _child(failure: str, stop_server: bool, *, observe_exit: bool = False) -> subprocess.CompletedProcess:
    """Drive one real suite process: probe a live server, then fail as named.

    The decision is read at the ``exitImpl`` seam so the assertion can name which way the
    guard decided. ``observe_exit`` drops that seam and lets the child take its own exit,
    which is the only way to see the hazard this batch's own drafting ran into on Windows:
    The exit itself is the shipped one in the ``observe_exit`` children, and it
    reaches the parent as exit 3; the abort that first drafting blamed on it lived
    in ``node -e``, not in the guard.
    """
    script = (
        HEALTH_SERVER_PREAMBLE
        + f'import {{ requireHarnessOrExit }} from "{SUITES.as_uri()}";\n'
        + LIVE_HEALTH_SERVER
        + (
            "await requireHarnessOrExit(baseUrl);\n"
            if observe_exit
            else "await requireHarnessOrExit(baseUrl, { exitImpl: (code) => {\n"
            '  decided.push(code);\n  console.log("DECIDED", JSON.stringify(decided));\n'
            "}});\n"
        )
        + ("serving = false; " if stop_server else "")
        + f"{failure}\n"
    )
    result = _node(script)
    decided = re.findall(r"DECIDED (\[.*?\])", result.stdout)
    result.decided = json.loads(decided[-1]) if decided else []
    return result


def _run_verdict(tmp_path, text: str, exit_code: int = 3, name: str = "lost.log"):
    log = tmp_path / name
    log.write_text(text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(VERDICT), "--exit-code", str(exit_code), "--log", str(log)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        timeout=120,
        check=False,
    )


def test_the_server_says_whether_the_run_lost_its_harness() -> None:
    result = _child('throw new Error("page.goto: net::ERR_CONNECTION_REFUSED");', stop_server=True)
    assert result.decided == [3], (
        f"a suite whose server vanished decided {result.decided} (child rc {result.returncode}): "
        f"{result.stdout}{result.stderr}"
    )
    assert "SMOKE_FAILURE_CODE=HARNESS_LOST" in result.stderr, result.stderr
    assert "HARNESS_UNREACHABLE" not in result.stderr, (
        "the run did reach its server once; saying it never did would erase that the step measured something"
    )
    assert "run partway" in result.stderr and "partial coverage" in result.stderr, result.stderr
    assert "127.0.0.1" in result.stderr, "the sentence must name the server that went away"
    assert "restart the server" in result.stderr, result.stderr
    assert "net::ERR_CONNECTION_REFUSED" in result.stderr, (
        f"the suite's own last words must stay in the log: {result.stderr}"
    )
    assert result.elapsed < PROBE_SECONDS_ALLOWED, (
        f"the loss path took {result.elapsed:.1f}s; it adds one health probe and nothing else"
    )


def test_a_product_failure_with_the_server_answering_keeps_its_own_verdict() -> None:
    result = _child(
        'throw new Error("AssertionError [ERR_ASSERTION]: product path task must reach completion_complete");',
        stop_server=False,
    )
    assert result.decided == [1], (
        f"the server answered, so this is the product's and must stay exit 1: {result.stderr}"
    )
    assert "SMOKE_FAILURE_CODE" not in result.stderr, result.stderr
    assert "product path task must reach completion_complete" in result.stderr, result.stderr
    assert "at " in result.stderr, "the stack Node would have printed must not be swallowed"


def test_an_assertion_that_quotes_a_connection_error_is_still_the_products() -> None:
    # The shape list is colour for the sentence, never the judge: with the server
    # answering, a message that merely contains ERR_CONNECTION_REFUSED cannot
    # move the run onto the harness plane.
    result = _child(
        'throw new Error("AssertionError [ERR_ASSERTION]: panel must not say net::ERR_CONNECTION_REFUSED");',
        stop_server=False,
    )
    assert result.decided == [1], f"a quoted connection string read as a lost harness: {result.stderr}"
    assert "HARNESS_LOST" not in result.stderr, result.stderr


def test_a_child_that_takes_its_own_exit_exits_the_loss_code_not_a_crash() -> None:
    # The mechanism is only worth its exit code if a real process can hand that code to
    # the CI step. This child overrides nothing, so the exit is the shipped one.
    result = _child('throw new Error("page.goto: net::ERR_CONNECTION_REFUSED");', stop_server=True, observe_exit=True)
    assert result.returncode == HARNESS_LOST_EXIT, (
        f"a lost harness must exit {HARNESS_LOST_EXIT}, not {result.returncode:#x}: {result.stderr}"
    )
    assert "SMOKE_FAILURE_CODE=HARNESS_LOST" in result.stderr, result.stderr
    assert "partial coverage" in result.stderr, f"the announcement must survive the exit: {result.stderr}"


def test_a_child_that_takes_its_own_exit_keeps_the_products_code() -> None:
    # The same path, the other answer: an intact server must not cost the suite the exit
    # code the mutation gate reads.
    result = _child('throw new Error("AssertionError: timeline must render the sent turn");', stop_server=False, observe_exit=True)
    assert result.returncode == 1, f"the server answered, so the suite keeps its own exit code: {result.returncode:#x}"
    assert "SMOKE_FAILURE_CODE" not in result.stderr, result.stderr
    assert "timeline must render the sent turn" in result.stderr, result.stderr


def test_the_probe_hands_the_process_back_rather_than_holding_it() -> None:
    # Every suite calls this probe at least once, so the probe's own handles are
    # the suite's handles: measured with one health call against a live server and
    # no process.exit afterwards, globalThis.fetch held the loop 4.17s (undici
    # keeps its pooled socket) against 0.91s for the transport now in the module -
    # and an exit taken while that socket is still open does not exit, it aborts in
    # libuv. A guard that crashes the step it is guarding is the defect wearing the
    # guard's own clothes.
    script = (
        HEALTH_SERVER_PREAMBLE
        + f'import {{ requireHarness }} from "{SUITES.as_uri()}";\n'
        + LIVE_HEALTH_SERVER
        + 'console.log("ANSWERED " + JSON.stringify(await requireHarness(baseUrl)));\n'
    )
    result = _node(script)
    assert "ANSWERED" in result.stdout, result.stdout + result.stderr
    assert '"ok":true' in result.stdout, f"the probe did not believe a live server: {result.stdout}"
    assert result.elapsed < PROBE_DRAIN_SECONDS_ALLOWED, (
        f"the probe left the process holding {result.elapsed:.2f}s of work; "
        "a suite that passed still has to reach its own exit"
    )
    module_source = SUITES.read_text(encoding="utf-8")
    assert "fetchImpl = closedSocketHealthCall" in module_source, (
        "the probe must default to the transport that closes its socket, not to globalThis.fetch"
    )
    assert "AbortSignal.timeout" not in module_source, (
        "the timeout belongs to the socket, not to a signal the transport never reads"
    )


def test_the_probe_names_the_socket_error_when_nothing_is_listening() -> None:
    # "The server went away" is only useful if the sentence can say how it knows.
    # The transport owns that word now, so the name of the refusal is checked here
    # rather than left to whichever library happens to answer the call.
    script = (
        f'import {{ requireHarness }} from "{SUITES.as_uri()}";\n'
        + 'console.log(JSON.stringify(await requireHarness("http://127.0.0.1:8799")));\n'
    )
    result = _node(script)
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is False, f"something is answering port 8799: {payload}"
    assert "ECONNREFUSED" in payload["detail"], f"the refusal did not reach the sentence: {payload}"


def test_a_server_that_stops_talking_is_an_answer_not_a_wait() -> None:
    # The other way a probe can go wrong: a listener that accepts and never
    # responds. That must come back as "no answer" inside the bound the caller set,
    # because a suite that hangs is a step that never reports either plane.
    script = (
        HEALTH_SERVER_PREAMBLE
        + f'import {{ requireHarness }} from "{SUITES.as_uri()}";\n'
        + "const server = createServer(() => {});\n"
        + "await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));\n"
        + "const baseUrl = `http://127.0.0.1:${server.address().port}`;\n"
        + "server.unref();\n"
        + 'console.log("ANSWERED " + JSON.stringify(await requireHarness(baseUrl, { timeoutMs: 500 })));\n'
    )
    result = _node(script)
    assert result.returncode == 0, f"a silent listener hung or crashed the probe: {result.stderr}"
    assert '"ok":false' in result.stdout, result.stdout
    assert "got no answer in 500ms" in result.stdout, result.stdout
    assert result.elapsed < PROBE_DRAIN_SECONDS_ALLOWED, (
        f"a silent server cost {result.elapsed:.2f}s against a 500ms bound"
    )


def test_the_suite_that_collects_its_errors_asks_before_it_exits() -> None:
    collected = []
    for path in _live_url_suites():
        source = path.read_text(encoding="utf-8")
        if "if (errors.length)" not in source:
            continue
        collected.append(path.name)
        block = source.split("if (errors.length)", 1)[1].split("\n}", 1)[0]
        assert "await exitIfHarnessLost(baseUrl);" in block, (
            f"{path.name} swallows its failures into an array and exits 1 without asking its server: "
            "a run that lost the harness mid-way reports a product failure here, and its stack is already printed"
        )
        assert 'import { exitIfHarnessLost' in source or "exitIfHarnessLost, " in source, (
            f"{path.name} must take the second look from the shared module"
        )
    assert len(collected) >= 5, f"only {collected}; the collected-error shape is the one this case exists for"


def test_the_hook_arrives_with_the_probe_and_never_doubles_up() -> None:
    script = (
        HEALTH_SERVER_PREAMBLE
        + f'import {{ requireHarnessOrExit, watchHarnessLoss }} from "{SUITES.as_uri()}";\n'
        + LIVE_HEALTH_SERVER
        + "const before = process.listenerCount('uncaughtException') + process.listenerCount('unhandledRejection');\n"
        "await requireHarnessOrExit(baseUrl);\n"
        "const afterProbe = process.listenerCount('uncaughtException') + process.listenerCount('unhandledRejection');\n"
        "watchHarnessLoss(baseUrl);\n"
        "watchHarnessLoss(baseUrl);\n"
        "const afterTwice = process.listenerCount('uncaughtException') + process.listenerCount('unhandledRejection');\n"
        "console.log(JSON.stringify({ before, afterProbe, afterTwice }));\n"
        + "process.exit(0);\n"
    )
    result = _node(script)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["before"] == 0, f"importing the module must not take over the process: {payload}"
    assert payload["afterProbe"] == 2, f"the passing probe must arm the watcher: {payload}"
    assert payload["afterTwice"] == payload["afterProbe"], f"a watcher per process, not per call: {payload}"


def test_a_run_that_never_reached_its_server_arms_nothing() -> None:
    # M8-T1304's answer already covers this run; arming a second voice would let
    # one step print two harness codes for a server that never existed.
    script = (
        f'import {{ requireHarnessOrExit }} from "{SUITES.as_uri()}";\n'
        "const before = process.listenerCount('uncaughtException') + process.listenerCount('unhandledRejection');\n"
        "await requireHarnessOrExit('http://127.0.0.1:8799', { exitImpl: () => {} });\n"
        "const after = process.listenerCount('uncaughtException') + process.listenerCount('unhandledRejection');\n"
        "console.log(JSON.stringify({ before, after }));\n"
    )
    result = _node(script)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"before": 0, "after": 0}, f"a failed probe armed the mid-run watcher: {payload}"


def test_the_verdict_gives_a_run_that_lost_its_server_its_own_sentence(tmp_path) -> None:
    result = _run_verdict(tmp_path, "SMOKE_FAILURE_CODE=HARNESS_LOST\n")
    assert result.returncode == 3, result.stdout + result.stderr
    assert "harness lost mid-suite" in result.stdout, result.stdout
    assert "partial coverage" in result.stdout, result.stdout
    assert "tested nothing" not in result.stdout, (
        f"assertions did run in this step: {result.stdout}"
    )
    assert "mutation caught" not in result.stdout, result.stdout


def test_a_lost_harness_is_not_silenced_by_a_product_code_in_either_order(tmp_path) -> None:
    forward = _run_verdict(
        tmp_path,
        "SMOKE_FAILURE_CODE=HARNESS_LOST\nSMOKE_FAILURE_CODE=PRODUCT_PATH_NO_COMPLETION_VERDICT\n",
    )
    reverse = _run_verdict(
        tmp_path,
        "SMOKE_FAILURE_CODE=PRODUCT_PATH_NO_COMPLETION_VERDICT\nSMOKE_FAILURE_CODE=HARNESS_LOST\n",
        name="reverse.log",
    )
    for name, result in (("forward", forward), ("reverse", reverse)):
        assert result.returncode == 3, f"{name}: a run whose server died reported a product verdict: {result.stdout}"
        assert "harness lost mid-suite" in result.stdout, f"{name}: {result.stdout}"
    # And the plane the two harness answers share stays ordered: a run that never
    # reached its server did not run partway, whichever order the codes arrive in.
    both = _run_verdict(
        tmp_path,
        "SMOKE_FAILURE_CODE=HARNESS_UNREACHABLE\nSMOKE_FAILURE_CODE=HARNESS_LOST\n",
        name="both.log",
    )
    assert both.returncode == 3, both.stdout
    assert "harness absent" in both.stdout and "tested nothing" in both.stdout, both.stdout
    caught = _run_verdict(
        tmp_path, "SMOKE_FAILURE_CODE=PRODUCT_PATH_NO_COMPLETION_VERDICT\n", exit_code=1, name="caught.log"
    )
    assert caught.returncode == 0 and "mutation caught" in caught.stdout, caught.stdout


def test_the_module_and_the_verdict_agree_on_the_loss_code_and_the_plane() -> None:
    module_source = SUITES.read_text(encoding="utf-8")
    verdict_source = VERDICT.read_text(encoding="utf-8")
    code = re.search(r'HARNESS_LOST_CODE = "([A-Z_]+)"', module_source)
    exit_code = re.search(r"HARNESS_LOST_EXIT = (\d+)", module_source)
    verdict_code = re.search(r'HARNESS_LOST_CODE = "([A-Z_]+)"', verdict_source)
    harness_exit = re.search(r"HARNESS_EXIT = (\d+)", verdict_source)
    assert code and exit_code and verdict_code and harness_exit, "one of the two sides lost its constant"
    assert code.group(1) == verdict_code.group(1), "the smoke and the verdict name different codes"
    assert exit_code.group(1) == harness_exit.group(1) != "1", (
        "a lost harness shares the absent harness's plane and must not collide with 'caught' (0) "
        f"or 'unattributed' (1): smoke {exit_code.group(1)}, verdict {harness_exit.group(1)}"
    )
    assert "watchHarnessLoss(baseUrl," in module_source, (
        "the watcher is armed by the probe that passed, so a suite cannot forget to ask for it"
    )


def _live_url_suites() -> list[Path]:
    return sorted(
        path
        for path in (REPO_ROOT / "tests").glob("*_smoke.mjs")
        if "process.env.MINICC_WEB_URL" in path.read_text(encoding="utf-8")
    )


def test_every_suite_that_drives_a_live_url_can_report_a_lost_harness() -> None:
    suites = _live_url_suites()
    assert len(suites) >= 13, f"only {len(suites)} live-URL suites found; the roster is the denominator"
    for path in suites:
        source = path.read_text(encoding="utf-8")
        assert "await requireHarnessOrExit(baseUrl);" in source, f"{path.name} never probes its server"
        assert "function exitIfHarnessLost" not in source, (
            f"{path.name} defines its own second look; a private copy is the drift the module exists to prevent"
        )
        assert "process.on(" not in source, (
            f"{path.name} hooks the process itself: one watcher per run, taken from the shared module"
        )
