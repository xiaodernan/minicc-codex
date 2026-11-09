"""M8-T696 -- `minicc --doctor --json` machine-readable report + credential-free dispatch."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from minicc.main import main


def test_doctor_json_emits_machine_readable_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Deliberately no MINICC_API_KEY/MINICC_BASE_URL: doctor must not need credentials.
    monkeypatch.delenv("MINICC_API_KEY", raising=False)
    monkeypatch.delenv("MINICC_BASE_URL", raising=False)
    rc = main(["--doctor", "--json", "--workspace", str(tmp_path)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"ok", "warn", "fatal", "checks"}
    assert isinstance(payload["checks"], list) and payload["checks"]
    for check in payload["checks"]:
        assert {"name", "severity", "detail"} <= set(check)


def test_doctor_strict_json_fails_on_warnings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MINICC_API_KEY", raising=False)
    monkeypatch.delenv("MINICC_BASE_URL", raising=False)
    rc = main(["--doctor-strict", "--json", "--workspace", str(tmp_path)])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["warn"] > 0
    assert payload["fatal"] == 0


def test_json_without_doctor_is_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MINICC_API_KEY", raising=False)
    monkeypatch.delenv("MINICC_BASE_URL", raising=False)
    rc = main(["--json", "--workspace", str(tmp_path)])
    assert rc == 2
    assert "--json" in capsys.readouterr().out


def test_doctor_works_without_credentials(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh machine with no .env and no key can still self-diagnose."""
    monkeypatch.delenv("MINICC_API_KEY", raising=False)
    monkeypatch.delenv("MINICC_BASE_URL", raising=False)
    monkeypatch.delenv("MINICC_MODEL", raising=False)
    rc = main(["--doctor", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out
    assert "minicc doctor" in out
    assert "MINICC_API_KEY" not in out
    assert rc == 0
