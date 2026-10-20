"""M8-T280: the artefacts a check leaves behind are not verification inputs.

The verification fingerprint hashes the whole workspace tree, so the guard
can tell whether the *inputs* changed while a check was running.  But a check
writes into the workspace too: ``.coverage``, ``coverage.xml``,
``htmlcov/``, ``junit.xml``.  Those files entered the fingerprint, so a run
that produced them changed the fingerprint - and the verifier rewrote a
**passing** result as "the workspace changed during verification".

The task then failed for a reason the model cannot fix and the user cannot
see: the deliverable was right and the check was green.

This door pins:

* an artefact a check writes does not change the fingerprint;
* the input the check reads does change it;
* the control: an unrelated file still invalidates the fingerprint.
"""

from __future__ import annotations

from pathlib import Path

from minicc.agent.verification_plan import (
    VerificationCommand,
    verification_fingerprint,
)

COMMANDS = [VerificationCommand(command="python -m pytest -q", label="pytest")]


def _fingerprint(root: Path) -> str:
    return verification_fingerprint(root, [], COMMANDS)


def test_a_coverage_artefact_does_not_change_the_fingerprint(tmp_path: Path) -> None:
    """The artefact appears *after* the first fingerprint - the exact shape."""
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    before = _fingerprint(tmp_path)
    (tmp_path / ".coverage").write_bytes(b"binary coverage data")
    (tmp_path / "coverage.xml").write_text("<coverage/>", encoding="utf-8")
    (tmp_path / "junit.xml").write_text("<testsuite/>", encoding="utf-8")
    after = _fingerprint(tmp_path)
    assert before == after, "the check's own artefacts changed the fingerprint"


def test_a_coverage_report_directory_does_not_change_the_fingerprint(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    before = _fingerprint(tmp_path)
    report = tmp_path / "htmlcov"
    report.mkdir()
    (report / "index.html").write_text("<html></html>", encoding="utf-8")
    assert before == _fingerprint(tmp_path)


def test_the_input_the_check_reads_does_change_the_fingerprint(tmp_path: Path) -> None:
    """The control: a real input still invalidates the cached result."""
    source = tmp_path / "app.py"
    source.write_text("print('hi')\n", encoding="utf-8")
    before = _fingerprint(tmp_path)
    source.write_text("print('bye')\n", encoding="utf-8")
    assert before != _fingerprint(tmp_path)


def test_an_unrelated_file_still_changes_the_fingerprint(tmp_path: Path) -> None:
    """The other control: the fingerprint is still a workspace identity."""
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    before = _fingerprint(tmp_path)
    (tmp_path / "other.py").write_text("x = 1\n", encoding="utf-8")
    assert before != _fingerprint(tmp_path)
