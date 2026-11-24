"""M8-T1333: minicc must never bind itself to a Clash proxy from .env.

M8-T1174 re-exported any HTTP(S)_PROXY / ALL_PROXY found in .env into
``os.environ`` so the whole process tree routed through 127.0.0.1:7897. With
Clash retired, a single stale proxy line silently turns every outbound call
into ECONNREFUSED again. Config resolution must read MINICC_* keys from .env
but leave the process proxy environment alone.
"""

from __future__ import annotations

import os
from pathlib import Path

from minicc.config import load_config

PROXY_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
)


def _clear(monkeypatch) -> None:
    for key in PROXY_KEYS + ("MINICC_API_KEY", "MINICC_BASE_URL", "MINICC_MODEL", "MINICC_HOME"):
        monkeypatch.delenv(key, raising=False)


def test_a_stale_proxy_in_dotenv_is_never_exported(tmp_path: Path, monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINICC_HOME", str(tmp_path))
    monkeypatch.setenv("MINICC_API_KEY", "sk-test")
    monkeypatch.setenv("MINICC_BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("MINICC_MODEL", "m")
    (tmp_path / ".env").write_text(
        "HTTPS_PROXY=http://127.0.0.1:7897\n"
        "HTTP_PROXY=http://127.0.0.1:7897\n"
        "ALL_PROXY=http://127.0.0.1:7897\n"
        "MINICC_MODEL=from-dotenv\n",
        encoding="utf-8",
    )

    load_config()

    for key in PROXY_KEYS:
        assert key not in os.environ, f"{key} was exported from .env — minicc re-bound itself to a proxy"


def test_a_real_environment_proxy_is_left_untouched(tmp_path: Path, monkeypatch) -> None:
    """An operator-set proxy in the real environment is respected, not cleared."""
    _clear(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINICC_HOME", str(tmp_path))
    monkeypatch.setenv("MINICC_API_KEY", "sk-test")
    monkeypatch.setenv("MINICC_BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("MINICC_MODEL", "m")
    monkeypatch.setenv("HTTPS_PROXY", "http://10.0.0.1:8080")
    (tmp_path / ".env").write_text("MINICC_MODEL=from-dotenv\n", encoding="utf-8")

    load_config()

    assert os.environ.get("HTTPS_PROXY") == "http://10.0.0.1:8080"


def test_config_source_has_no_proxy_export() -> None:
    """Static guard: the re-export loop must not come back."""
    body = Path("minicc/config.py").read_text(encoding="utf-8")
    assert "os.environ[_key] = _value" not in body
    assert "_PROXY_KEYS" not in body
