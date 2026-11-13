"""M8-T686 — `minicc --doctor` self-diagnostic.

Every probe is small and offline; the report is machine-readable.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
import sys

from minicc.doctor import (
    DoctorCheck,
    DoctorReport,
    check_audit_log,
    check_git_worktree,
    check_llm_cache_affinity,
    check_minicc_compiles,
    check_minicc_dir_writable,
    check_minicc_import,
    check_permissions_json,
    check_python_version,
    check_web_token_permissions,
    format_report,
    run_doctor,
)
from minicc.internal_paths import AUDIT_NAME, PERMISSIONS_NAME, TOKEN_FILE_NAME


def test_llm_cache_affinity_is_ok_with_explicit_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_API_KEY", "sk-test")
    monkeypatch.setenv("MINICC_BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("MINICC_PROMPT_CACHE_KEY", "tenant-key")
    result = check_llm_cache_affinity(Path("."))
    assert result.severity == "ok"
    assert "explicit" in result.detail


def test_llm_cache_affinity_reports_derived_key_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_API_KEY", "sk-test")
    monkeypatch.delenv("MINICC_PROMPT_CACHE_KEY", raising=False)
    result = check_llm_cache_affinity(Path("."))
    assert result.severity == "ok"
    assert "derived" in result.detail


def _isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A workspace whose .env, project config and user config are all empty."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return tmp_path


def test_llm_cache_affinity_warns_without_llm_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MINICC_API_KEY", raising=False)
    monkeypatch.delenv("MINICC_PLAN_API_KEY", raising=False)
    monkeypatch.delenv("MINICC_BASE_URL", raising=False)
    _isolated_home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)  # load_config reads .env from the CWD, not the workspace
    result = check_llm_cache_affinity(tmp_path)
    assert result.severity == "warn"
    # With nothing configured load_config raises before the endpoint question,
    # so the probe either names the missing key (ConfigError) or the missing
    # endpoint (clean config with empty values); both must stay a warn that
    # says the affinity question cannot be answered here.
    assert "prefix-cache affinity not observable" in result.detail


def test_llm_cache_affinity_sees_a_dotenv_the_product_would_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """M8-T896: the probe must answer through the config layer, not os.environ.

    The first build read the process environment directly and warned "no LLM
    endpoint configured" while sitting in a repo whose .env a real turn was
    using at that very moment — the doctor disagreed with the product it
    doctors. A .env on disk (no process env vars at all) must read as ok.
    """
    for name in ("MINICC_API_KEY", "MINICC_PLAN_API_KEY", "MINICC_BASE_URL", "MINICC_PROMPT_CACHE_KEY"):
        monkeypatch.delenv(name, raising=False)
    _isolated_home(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("MINICC_API_KEY=sk-test\nMINICC_BASE_URL=https://gateway.test/v1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = check_llm_cache_affinity(tmp_path)
    assert result.severity == "ok", result.detail
    assert "derived" in result.detail


def test_python_version_is_ok_on_installed_python() -> None:
    result = check_python_version(Path("."))
    assert result.severity == "ok"
    assert sys.version_info[:2] >= (3, 11)


def test_minicc_imports_and_exposes_version() -> None:
    result = check_minicc_import(Path("."))
    assert result.severity == "ok"
    assert "import ok" in result.detail


def test_module_compiles() -> None:
    result = check_minicc_compiles(Path("."))
    assert result.severity == "ok", result


def test_minicc_dir_is_writable_in_tmp(tmp_path: Path) -> None:
    result = check_minicc_dir_writable(tmp_path)
    assert result.severity == "ok"


def test_minicc_dir_writable_when_minicc_uncreatable(tmp_path: Path) -> None:
    # Force a failure: make .minicc a file, not a dir, so mkdir() raises.
    state = tmp_path / ".minicc"
    state.write_text("i block you", encoding="utf-8")
    result = check_minicc_dir_writable(tmp_path)
    assert result.severity == "fatal"


def test_audit_log_warns_when_absent(tmp_path: Path) -> None:
    result = check_audit_log(tmp_path)
    assert result.severity == "warn"


def test_audit_log_fails_on_corrupt_last_line(tmp_path: Path) -> None:
    state = tmp_path / ".minicc"
    state.mkdir()
    (state / AUDIT_NAME).write_text("not-valid-json\n", encoding="utf-8")
    result = check_audit_log(tmp_path)
    assert result.severity == "fatal"


def test_audit_log_ok_when_last_line_parses(tmp_path: Path) -> None:
    state = tmp_path / ".minicc"
    state.mkdir()
    (state / AUDIT_NAME).write_text(
        '{"event": "tool_call", "tool": "bash"}\n', encoding="utf-8"
    )
    result = check_audit_log(tmp_path)
    assert result.severity == "ok"


def test_web_token_warns_when_absent(tmp_path: Path) -> None:
    result = check_web_token_permissions(tmp_path)
    assert result.severity == "warn"


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits only")
def test_web_token_fails_on_group_readable_mode(tmp_path: Path) -> None:
    state = tmp_path / ".minicc"
    state.mkdir()
    token = state / TOKEN_FILE_NAME
    token.write_text("secret", encoding="utf-8")
    token.chmod(0o644)
    result = check_web_token_permissions(tmp_path)
    assert result.severity == "fatal"


def test_permissions_json_warns_when_absent(tmp_path: Path) -> None:
    result = check_permissions_json(tmp_path)
    assert result.severity == "warn"


def test_permissions_json_fails_on_invalid_json(tmp_path: Path) -> None:
    state = tmp_path / ".minicc"
    state.mkdir()
    (state / PERMISSIONS_NAME).write_text("{\n", encoding="utf-8")
    result = check_permissions_json(tmp_path)
    assert result.severity == "fatal"


def test_permissions_json_ok_on_valid_empty(tmp_path: Path) -> None:
    state = tmp_path / ".minicc"
    state.mkdir()
    (state / PERMISSIONS_NAME).write_text(
        '{"allow": {}, "deny": {}}', encoding="utf-8"
    )
    result = check_permissions_json(tmp_path)
    assert result.severity == "ok"


def test_doctor_reports_shape(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    assert isinstance(report, DoctorReport)
    assert report.ok + report.warn + report.fatal == len(report.checks)
    assert all(isinstance(c, DoctorCheck) for c in report.checks)


def test_doctor_exit_code_zero_when_no_fatals(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    if report.fatal == 0:
        assert report.exit_code == 0
    else:
        assert report.exit_code == 1


def test_report_json_round_trip(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    text = format_report(report, json_out=True)
    payload = json.loads(text)
    assert set(payload) == {"ok", "warn", "fatal", "checks"}
    assert isinstance(payload["checks"], list)


def test_report_text_names_every_check(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    text = format_report(report)
    for check in report.checks:
        assert check.name in text
