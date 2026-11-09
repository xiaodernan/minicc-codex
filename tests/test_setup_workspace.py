"""M8-T688 — `minicc --setup` scaffolding."""
from __future__ import annotations

import json
import os
import pytest
from pathlib import Path

from minicc.internal_paths import PERMISSIONS_NAME, TOKEN_FILE_NAME
from minicc.setup import (
    DEFAULT_PERMISSIONS,
    SetupReport,
    setup_workspace,
)


def test_setup_creates_scaffold(tmp_path: Path) -> None:
    report = setup_workspace(tmp_path)
    assert report.exit_code == 0
    assert report.created_dir
    assert report.created_permissions
    assert report.created_web_token
    state = tmp_path / ".minicc"
    assert state.is_dir()
    permissions = state / PERMISSIONS_NAME
    token = state / TOKEN_FILE_NAME
    assert permissions.exists()
    assert token.exists()
    payload = json.loads(permissions.read_text(encoding="utf-8"))
    assert payload["deny"]["paths"][0] == ".env" or ".env" in payload["deny"]["paths"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits only")
def test_setup_sets_token_private_mode(tmp_path: Path) -> None:
    report = setup_workspace(tmp_path)
    assert report.exit_code == 0
    token = tmp_path / ".minicc" / TOKEN_FILE_NAME
    mode = token.stat().st_mode & 0o777
    assert mode == 0o600, oct(mode)


def test_setup_is_idempotent(tmp_path: Path) -> None:
    first = setup_workspace(tmp_path)
    assert first.exit_code == 0
    assert first.created_permissions and first.created_web_token

    second = setup_workspace(tmp_path)
    assert second.exit_code == 0
    assert not second.created_permissions
    assert not second.created_web_token


def test_setup_never_overwrites_existing_permissions(tmp_path: Path) -> None:
    state = tmp_path / ".minicc"
    state.mkdir()
    custom = '{"deny": {"paths": ["important"]}, "allow": {"paths": [], "tools": [], "commands": []}}'
    (state / PERMISSIONS_NAME).write_text(custom, encoding="utf-8")

    report = setup_workspace(tmp_path)
    assert report.exit_code == 0
    assert not report.created_permissions
    assert (state / PERMISSIONS_NAME).read_text(encoding="utf-8") == custom


def test_setup_never_overwrites_existing_token(tmp_path: Path) -> None:
    state = tmp_path / ".minicc"
    state.mkdir()
    (state / TOKEN_FILE_NAME).write_text("preserve-me\n", encoding="utf-8")

    report = setup_workspace(tmp_path)
    assert report.exit_code == 0
    assert not report.created_web_token
    assert (state / TOKEN_FILE_NAME).read_text(encoding="utf-8").strip() == "preserve-me"


def test_default_permissions_has_routes() -> None:
    assert DEFAULT_PERMISSIONS["deny"]["paths"]
    # Both common document names must be present.
    assert ".env" in DEFAULT_PERMISSIONS["deny"]["paths"]


def test_setup_report_message_nonempty(tmp_path: Path) -> None:
    report = setup_workspace(tmp_path)
    assert report.message
