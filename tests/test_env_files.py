"""M8-T794: minicc/env_files.py tests.

Tests for env file family detection:
- env_files.ENV_FILENAME
- env_files.ENV_FAMILY_PREFIX
- env_files.is_env_filename
"""

from __future__ import annotations

import pytest

from minicc.env_files import ENV_FILENAME, ENV_FAMILY_PREFIX, is_env_filename


def test_env_filename_constant() -> None:
    assert ENV_FILENAME == ".env"


def test_env_family_prefix_constant() -> None:
    assert ENV_FAMILY_PREFIX == ".env."


def test_is_env_filename_exact_match() -> None:
    assert is_env_filename(".env") is True


def test_is_env_filename_variant() -> None:
    assert is_env_filename(".env.local") is True
    assert is_env_filename(".env.production") is True


def test_is_env_filename_not_env_file() -> None:
    assert is_env_filename("README.md") is False
    assert is_env_filename(".envrc") is False
    assert is_env_filename("env") is False

