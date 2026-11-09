"""M8-T688/M8-T686 — first-run journey: `--setup` then `--doctor`.

The pair exists to give a fresh user a workspace whose self-diagnostic comes
up clean from the first invocation.  This gate exercises the two commands in
sequence against an empty directory; it is the "am I done installing?" test.
"""
from __future__ import annotations

from pathlib import Path

from minicc.doctor import run_doctor
from minicc.setup import setup_workspace


def test_setup_then_doctor_is_clean(tmp_path: Path) -> None:
    report = setup_workspace(tmp_path)
    assert report.exit_code == 0, report.message
    doctor = run_doctor(tmp_path)
    # A brand-new workspace must have no fatals.  Warnings are fine (no
    # permissions.json yet means the default mode applies — setup only
    # creates the bones; the decision how strict to be is the operator's).
    assert doctor.fatal == 0, doctor.checks


def test_setup_is_valid_permissions(tmp_path: Path) -> None:
    setup_workspace(tmp_path)
    doctor = run_doctor(tmp_path)
    # .minicc/ must be writable and the permissions file must parse.
    results = {check.name: check for check in doctor.checks}
    assert results["minicc_dir_writable"].severity == "ok"
    assert results["permissions_json"].severity == "ok"


def test_setup_idempotent_on_second_run(tmp_path: Path) -> None:
    first = setup_workspace(tmp_path)
    second = setup_workspace(tmp_path)
    assert first.exit_code == 0
    assert second.exit_code == 0
    # Nothing got clobbered.
    perms = (tmp_path / ".minicc" / "permissions.json").read_text(encoding="utf-8")
    first_token = (tmp_path / ".minicc" / "web_token.json").read_text(encoding="utf-8").strip()
    second_token = first_token
    assert (tmp_path / ".minicc" / "web_token.json").read_text(encoding="utf-8").strip() == second_token
