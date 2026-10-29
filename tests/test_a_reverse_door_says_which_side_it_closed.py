"""A reverse door has to say *which* side it closed on.

`.github/workflows/ci.yml` runs one mutation gate - the web smoke against an
unreachable provider - and expresses it as a single inverted bit:

    if npm run test:web; then
      echo "MUTATION NOT CAUGHT: ..."
      exit 1
    fi
    echo "mutation caught: ..."

That shape reads "the smoke exited non-zero" and writes "the chain was tested and
broke where it should".  Those are not the same event, and nothing here tells them
apart: the smoke prints **one** line in its whole file (`tests/web_smoke.mjs:410`,
only on success), so a run that never started - a renamed npm script, a deleted
smoke file, a browser that will not launch, an assertion that dies in suite 1
before the product path - produces exactly the same door verdict as the mutation
this step exists to catch.  Measured locally (see the batch record): four of the
five scenarios this batch runs print the identical success line and exit 0.

The fix keeps the door's promise and adds the half it never had: the smoke says
where it got to, and the door refuses to claim a catch it cannot show evidence of.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SMOKE = REPO_ROOT / "tests" / "web_smoke.mjs"

#: the two things the door is allowed to treat as "the smoke really ran"
BROWSER_MARKER = "web smoke: browser up"
CHAIN_MARKER = "web smoke: suite product path"
DECLARATION = "MUTATION NOT CAUGHT"
#: the two reasons a non-zero exit is the **gate** failing rather than the product
NOT_RAN = "REVERSE DOOR DID NOT RUN"
NOT_REACHED = "REVERSE DOOR GUARDED NOTHING"


def _ci_text() -> str:
    return CI.read_text(encoding="utf-8")


def _door_block() -> str:
    """The shell the workflow actually runs for the mutation step.

    Extraction failures raise, they do not return "": a door the test could not
    find is not a door that does not exist, and the whole point of this batch is
    that the two are easy to confuse.
    """
    lines = _ci_text().splitlines()
    try:
        name_at = next(i for i, line in enumerate(lines)
                       if line.strip() == "- name: Run web smoke (expected to fail)")
    except StopIteration:
        raise AssertionError("no step named 'Run web smoke (expected to fail)' in ci.yml")
    run_at = next((i for i in range(name_at + 1, len(lines)) if lines[i].strip().startswith("run:")), None)
    if run_at is None:
        raise AssertionError(f"the mutation step at ci.yml:{name_at + 1} has no run: block")
    key_indent = len(lines[run_at]) - len(lines[run_at].lstrip())
    body = []
    for line in lines[run_at + 1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= key_indent:
            break
        body.append(line)
    if not any("npm run test:web" in line for line in body):
        raise AssertionError("the extracted run block does not invoke the web smoke")
    block = "\n".join(body)
    dedent = min((len(line) - len(line.lstrip())) for line in body if line.strip())
    return "\n".join(line[dedent:] if line.strip() else "" for line in body) + "\n"


def _npm_stub(tmp_path: Path, *, stdout_lines: list[str], exit_code: int) -> dict[str, str]:
    """A stand-in for `npm run test:web` that reports what it was told to."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "npm"
    body = "".join(f'echo "{line}"\n' for line in stdout_lines)
    script.write_text(f"#!/bin/sh\n{body}exit {exit_code}\n", encoding="utf-8")
    script.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "MINICC_WEB_URL": "http://127.0.0.1:1"}


def _run_door(tmp_path: Path, env: dict[str, str], shell: str) -> tuple[int, str]:
    block = _door_block()
    proc = subprocess.run([shell, "-e", "-c", block], cwd=str(tmp_path), env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


@pytest.fixture(scope="module")
def bash() -> str:
    """A shell that **runs** the step.

    `bash` on a Windows box can resolve to the WSL relay, which answers
    `execvpe(/bin/bash) failed` - a driver that ignores that reports "the smoke
    failed" for a suite that never started, which is the exact conflation this file
    exists to close.  So the candidate is asked to prove it runs, and if none does
    the legs say what did not run instead of going green.
    """
    candidates = [os.environ.get("MINICC_TEST_BASH"),
                  r"C:\Program Files\Git\bin\bash.exe",
                  r"C:\Program Files\Git\usr\bin\bash.exe",
                  "/bin/bash", "bash"]
    for candidate in filter(None, candidates):
        if not Path(candidate).is_file() and shutil.which(candidate) is None:
            continue
        try:
            probe = subprocess.run([candidate, "-c", "echo ok"], capture_output=True,
                                   text=True, timeout=30, encoding="utf-8", errors="replace")
        except Exception:
            continue
        if probe.returncode == 0 and "ok" in (probe.stdout or ""):
            return candidate
    pytest.skip("no shell here can execute the workflow step, so these legs did not run")


def test_a_door_that_never_ran_does_not_claim_a_catch(tmp_path: Path, bash: str) -> None:
    """The smoke exited non-zero **without ever saying it started**: not a catch.

    Red before this batch by construction - the shipped door reads one bit and has
    no way to tell this apart from the mutation it guards.
    """
    code, out = _run_door(tmp_path, _npm_stub(tmp_path, stdout_lines=[], exit_code=3), bash)
    assert code != 0, (
        "the step claimed 'mutation caught' while the smoke produced no evidence it "
        "ever started; a renamed script, a missing browser or a deleted smoke file "
        f"look like this: exit={code} output={out!r}"
    )
    assert NOT_RAN in out, (
        f"the door refused, but not for the reason it should: {out!r}"
    )
    assert DECLARATION not in out, (
        "a smoke that produced no evidence of running is not a smoke that passed the "
        "broken chain; the two readings must not come from the same branch"
    )


def test_a_door_that_ran_and_failed_still_closes(tmp_path: Path, bash: str) -> None:
    """Anti-vacuity: the fix must not turn the door into a step that always fails."""
    code, out = _run_door(tmp_path, _npm_stub(
        tmp_path, stdout_lines=[BROWSER_MARKER, CHAIN_MARKER], exit_code=3), bash)
    assert code == 0, (
        f"a smoke that reported reaching the product path and failing must count as a "
        f"caught mutation; exit={code} output={out!r}"
    )
    assert "mutation caught" in out, out
    assert DECLARATION not in out and NOT_RAN not in out and NOT_REACHED not in out, (
        "the step reached more than one verdict branch for one run"
    )


def test_a_smoke_that_dies_before_the_chain_is_not_a_catch(tmp_path: Path, bash: str) -> None:
    """Suite 1 of four failing (a DOM assert) is not the chain breaking."""
    code, out = _run_door(tmp_path, _npm_stub(tmp_path, stdout_lines=[BROWSER_MARKER], exit_code=1), bash)
    assert code != 0, (
        "the door claimed a caught mutation for a run that never entered the product "
        f"path it guards; exit={code} output={out!r}"
    )
    assert NOT_REACHED in out, (
        f"the door refused, but not for the reason it should: {out!r}"
    )


def test_a_passing_smoke_still_opens_the_door(tmp_path: Path, bash: str) -> None:
    """The forward direction the step already had must survive the fix."""
    code, out = _run_door(tmp_path, _npm_stub(
        tmp_path, stdout_lines=[BROWSER_MARKER, CHAIN_MARKER], exit_code=0), bash)
    assert code != 0, f"the smoke passed against a broken provider and the door agreed; exit={code}"
    assert DECLARATION in out, out


def test_the_markers_the_door_asks_for_are_printed_by_the_smoke() -> None:
    """The workflow and the suite drift apart unless one file names the other's words.

    Checked in **both** directions: the step has to ask for every marker there is (an
    arm that drops one grep would otherwise leave a door that only half believes the
    smoke ran), and it must not ask for a word the suite stopped printing.
    """
    block = _door_block()
    asked = set(re.findall(r'grep -q "([^"]+)"', block))
    missing_from_door = [marker for marker in (BROWSER_MARKER, CHAIN_MARKER) if marker not in asked]
    assert not missing_from_door, (
        f"the mutation step no longer asks for {missing_from_door}: a door that checks "
        "one of the two evidence lines is a door that reads the other one as free"
    )
    smoke = SMOKE.read_text(encoding="utf-8")
    missing_from_smoke = [marker for marker in sorted(asked) if f'"{marker}' not in smoke]
    assert not missing_from_smoke, (
        f"the step asks for {missing_from_smoke} but tests/web_smoke.mjs never prints them; "
        "the door would fail every CI run for a reason that is not in the product"
    )
    launched = smoke.index("chromium.launch(")
    started = smoke.index(f'"{BROWSER_MARKER}')
    assert launched < started, (
        "the browser marker is printed before the browser is launched, so it reports a "
        "script that started rather than a suite that could run"
    )


def test_every_declared_reverse_door_carries_its_evidence() -> None:
    """A census, not a list: any new door must say what it guarded.

    Scoped to steps that declare themselves a mutation gate with the
    ``MUTATION NOT CAUGHT`` branch - the file's own words for "this is a reverse
    door".  The count is asserted non-zero first, because a census that found
    nothing is exactly the failure mode this batch is about.
    """
    ci = _ci_text()
    steps = re.findall(r"- name: .*?\n(?=      - name: |  \S)", ci, re.S)
    doors = [step for step in steps if DECLARATION in step]
    assert doors, (
        f"no step in ci.yml declares {DECLARATION!r} any more; either the mutation gate "
        "was deleted - which is a product loss, not a green test - or this census "
        "stopped being able to read the file"
    )
    unprotected = [step.splitlines()[0].strip() for step in doors
                   if CHAIN_MARKER not in step or "grep" not in step]
    assert not unprotected, (
        f"these reverse doors press 'did not run' and 'caught it' into one success: "
        f"{unprotected}"
    )
