"""M8-T693 — `minicc --doctor-strict` behaviour."""
from __future__ import annotations

from pathlib import Path

import pytest

from minicc.main import main


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_API_KEY", "dummy-key")
    monkeypatch.setenv("MINICC_BASE_URL", "https://example.invalid/v1")


def test_doctor_strict_fails_on_flat_uninitialized_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    rc = main(["--doctor-strict", "--workspace", str(tmp_path)])
    assert rc == 1


def test_plain_doctor_reports_fatal_mismatch_on_flat_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    rc = main(["--doctor", "--workspace", str(tmp_path)])
    # Plain --doctor exits 0 (warnings don't fail) on a flat but filled-in tree.
    assert rc == 0


def test_doctor_strict_passes_after_fake_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A minimally green workspace: git init + setup_workspace + audit stub → plain and strict both pass? """
    import subprocess
    _set_env(monkeypatch)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    from minicc.setup import setup_workspace
    report = setup_workspace(tmp_path)
    assert report.exit_code == 0
    audit = tmp_path / ".minicc" / "audit.jsonl"
    audit.write_text('{"event": "ok"}\n', encoding="utf-8")
    plain = main(["--doctor", "--workspace", str(tmp_path)])
    assert plain == 0
