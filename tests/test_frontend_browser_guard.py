"""M8-T1322: a missing browser is the step's answer, not a product failure.

The focused frontend job installs Chromium before it runs 23 npm scripts. Four
of the resulting 26 .mjs files really launch a browser; the other 22 are static
or DOM-free contracts. Before this guard, an empty PLAYWRIGHT_BROWSERS_PATH made
all four exit 1 with Playwright's executable-not-found stack and no failure
code (scratch/measure1322/summary.tsv). They now name HARNESS_BROWSER_MISSING
and exit 3 before their first assertion.

The roster is derived from that CI step's npm commands, package.json, and the
presence of chromium.launch in each resolved .mjs file. A new browser suite
added to the step must either take the shared guard or turn this spec red.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "tests" / "frontend_browser_guard.mjs"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PACKAGE = REPO_ROOT / "package.json"
CHILD_DIR = Path(tempfile.gettempdir()) / "minicc-frontend-browser-guard-children"


def _node(script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    child = CHILD_DIR / "child_suite.mjs"
    child.parent.mkdir(parents=True, exist_ok=True)
    child.write_text(script, encoding="utf-8")
    started = time.monotonic()
    result = subprocess.run(
        ["node", str(child)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
        env=env,
        timeout=60,
        check=False,
    )
    result.elapsed = time.monotonic() - started
    return result


def _ci_frontend_commands() -> list[str]:
    source = CI.read_text(encoding="utf-8")
    match = re.search(
        r"      - name: Verify responsive UI and task protocol\n"
        r"        run: \|\n"
        r"((?:          .*\n)+)",
        source,
    )
    assert match, "the focused frontend CI step disappeared; the roster has no source"
    return re.findall(r"^\s+npm run ([A-Za-z0-9:_-]+)\s*$", match.group(1), re.MULTILINE)


def _ci_frontend_paths() -> list[Path]:
    scripts = json.loads(PACKAGE.read_text(encoding="utf-8"))["scripts"]
    paths: list[Path] = []
    for command in _ci_frontend_commands():
        script = scripts[command]
        for relative in re.findall(r"\bnode\s+([^\s]+\.mjs)\b", script):
            path = REPO_ROOT / relative
            assert path.is_file(), f"CI command {command} names missing {relative}"
            paths.append(path)
    return paths


def _browser_suites() -> list[Path]:
    return sorted(
        path
        for path in _ci_frontend_paths()
        if re.search(r"\bchromium\.launch\s*\(", path.read_text(encoding="utf-8"))
    )


def test_the_guard_names_the_missing_executable_and_uses_the_infrastructure_exit() -> None:
    script = """
import { requireBrowserOrExit, BROWSER_MISSING_CODE, BROWSER_MISSING_EXIT } from "__GUARD__";
const lines = [];
const result = await requireBrowserOrExit({
  chromiumImpl: { executablePath: () => "/missing/chromium" },
  existsImpl: () => false,
  exitImpl: (code) => { lines.push(`EXIT=${code}`); return code; },
  writeImpl: (line) => lines.push(line),
});
console.log(JSON.stringify({ result, lines, code: BROWSER_MISSING_CODE, exit: BROWSER_MISSING_EXIT }));
""".replace("__GUARD__", GUARD.as_uri())
    result = _node(script)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["code"] == "HARNESS_BROWSER_MISSING", payload
    assert payload["exit"] == payload["result"] == 3, payload
    assert payload["lines"][0] == "SMOKE_FAILURE_CODE=HARNESS_BROWSER_MISSING", payload
    assert "EXIT=3" in payload["lines"], payload
    sentence = "\n".join(payload["lines"])
    assert "/missing/chromium" in sentence, sentence
    assert "npx playwright install chromium" in sentence, sentence
    assert "no browser assertions ran" in sentence, sentence


def test_an_installed_executable_passes_without_announcing_or_exiting() -> None:
    script = """
import { requireBrowserOrExit } from "__GUARD__";
const lines = [];
const result = await requireBrowserOrExit({
  chromiumImpl: { executablePath: () => "/present/chromium" },
  existsImpl: (path) => path === "/present/chromium",
  exitImpl: (code) => { lines.push(`EXIT=${code}`); return code; },
  writeImpl: (line) => lines.push(line),
});
console.log(JSON.stringify({ result, lines }));
""".replace("__GUARD__", GUARD.as_uri())
    result = _node(script)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["result"] == {"ok": True, "executablePath": "/present/chromium"}, payload
    assert payload["lines"] == [], payload


def test_the_real_missing_browser_path_exits_three_before_the_caller_continues(tmp_path: Path) -> None:
    empty = tmp_path / "empty-browsers"
    empty.mkdir()
    script = """
import { requireBrowserOrExit } from "__GUARD__";
await requireBrowserOrExit();
console.log("SHOULD_NOT_REACH_LAUNCH");
""".replace("__GUARD__", GUARD.as_uri())
    result = _node(script, env=dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(empty)))
    assert result.returncode == 3, f"rc={result.returncode}: {result.stdout}{result.stderr}"
    assert "SMOKE_FAILURE_CODE=HARNESS_BROWSER_MISSING" in result.stderr, result.stderr
    assert "SHOULD_NOT_REACH_LAUNCH" not in result.stdout, result.stdout
    assert "browserType.launch" not in result.stderr, result.stderr
    assert result.elapsed < 15, f"the missing-browser path took {result.elapsed:.1f}s"


def test_every_ci_frontend_suite_that_launches_chromium_takes_the_shared_guard() -> None:
    suites = _browser_suites()
    assert len(suites) >= 4, f"only {len(suites)} browser suites derived; the parser lost the denominator"
    for path in suites:
        source = path.read_text(encoding="utf-8")
        assert 'from "./frontend_browser_guard.mjs"' in source, f"{path.name} does not import the shared guard"
        guard = source.find("await requireBrowserOrExit();")
        launch = source.find("chromium.launch")
        first_assert = re.search(r"\bassert\s*[.(]", source)
        assert guard >= 0 and launch >= 0 and guard < launch, f"{path.name} guards after the browser launch"
        assert first_assert is not None and guard < first_assert.start(), (
            f"{path.name} runs assertions before the missing-browser answer; 'no browser assertions ran' would be a lie"
        )
        assert "function requireBrowserOrExit" not in source, f"{path.name} defines a private second guard"


def test_all_derived_browser_suites_report_the_same_missing_browser_plane(tmp_path: Path) -> None:
    empty = tmp_path / "empty-browsers"
    empty.mkdir()
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(empty))
    for path in _browser_suites():
        result = subprocess.run(
            ["node", path.name],
            cwd=str(REPO_ROOT / "tests"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=60,
            check=False,
        )
        assert result.returncode == 3, f"{path.name}: rc={result.returncode}: {result.stdout}{result.stderr}"
        assert "SMOKE_FAILURE_CODE=HARNESS_BROWSER_MISSING" in result.stderr, f"{path.name}: {result.stderr}"
        assert "browserType.launch" not in result.stderr, f"{path.name} still tried to launch: {result.stderr}"
