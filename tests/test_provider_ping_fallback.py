# -*- coding: utf-8 -*-
"""M8-T1182 — the doctor probe: env first, .env fallback, never the key, offline under fake provider."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import minicc.provider_ping as pp


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for key in ("MINICC_BASE_URL", "MINICC_API_KEY", "MINICC_MODEL", "MINICC_FAKE_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    try:
        from minicc.oracle_common import default_cache

        default_cache.delete(pp._CACHE_KEY)
    except Exception:
        pass
    yield


class _Resp:
    status = 200

    def read(self, n: int = -1) -> bytes:
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fake_provider_skips_the_network_entirely(monkeypatch):
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    calls = []

    def fake_urlopen(*a, **k):
        calls.append(a)
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = pp.fetch_provider_ping(force_refresh=True)
    assert out["live"] is False
    assert out["configured"] is False
    assert "FAKE_PROVIDER" in out["error"]
    assert calls == []


def test_explicit_env_wins_without_touching_the_config_resolver(monkeypatch):
    monkeypatch.setenv("MINICC_BASE_URL", "https://gw.example.test/v1")
    monkeypatch.setenv("MINICC_API_KEY", "sk-test-not-a-key")
    monkeypatch.setenv("MINICC_MODEL", "m")

    def _refuse(*a, **k):
        raise AssertionError("config resolver must not be consulted when env is set")

    import minicc.config as _config

    monkeypatch.setattr(_config, "load_config", _refuse)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    out = pp.fetch_provider_ping(force_refresh=True)
    assert out["live"] is True
    assert out["gateway"] == "gw.example.test"


def test_dotenv_fallback_carries_the_key_but_never_echoes_it(monkeypatch):
    import json as _json

    captured: dict = {}

    def fake_urlopen(request, *a, **k):
        captured["auth"] = request.get_header("Authorization")
        captured["url"] = request.full_url
        return _Resp()

    import minicc.config as _config

    monkeypatch.setattr(
        _config, "load_config",
        lambda *a, **k: SimpleNamespace(base_url="https://gw.example.test/v1",
                                        api_key="sk-test-not-a-key",
                                        model="m"),
    )
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = pp.fetch_provider_ping(force_refresh=True)
    assert out["live"] is True
    assert out["configured"] is True
    assert captured["auth"] == "Bearer sk-test-not-a-key"
    assert captured["url"] == "https://gw.example.test/v1/models"
    payload_blob = _json.dumps(out)
    assert "sk-test-not-a-key" not in payload_blob


def test_broken_config_resolver_falls_through_to_honest_not_set(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("config exploded")

    import minicc.config as _config

    monkeypatch.setattr(_config, "load_config", _boom)
    out = pp.fetch_provider_ping(force_refresh=True)
    assert out["live"] is False
    assert out["configured"] is False
    assert out["error"] == "MINICC_BASE_URL is not set"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
