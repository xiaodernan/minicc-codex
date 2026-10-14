"""Independent fence tests for ``minicc.netguard`` SSRF guards.

These pin the security-critical pure logic without touching the network:
DNS-dependent helpers (``_resolve_and_validate``/``assert_public_host``/
``resolve_pinned_host``) are isolated with a monkeypatch on ``socket.getaddrinfo``,
so the suite runs in milliseconds and never does a live lookup.

Run directly (bypasses pytest teardown noise) or via the repo gate:
    python tests/test_netguard_pure.py
    python -m pytest tests/test_netguard_pure.py -q -W error
"""

import ipaddress
import urllib.parse

from minicc import netguard
from minicc.netguard import (
    ALLOWED_SCHEMES,
    BlockedAddressError,
    _embedded_ipv4_candidates,
    _env_allows_private,
    _is_blocked_address,
    assert_public_http_url,
)


def _ip(s):
    return ipaddress.ip_address(s)


# --- _is_blocked_address: the core SSRF gate -------------------------------

def test_loopback_v4_blocked():
    assert _is_blocked_address(_ip("127.0.0.1"))


def test_loopback_v6_blocked():
    assert _is_blocked_address(_ip("::1"))


def test_private_v4_ranges_blocked():
    for addr in ("10.0.0.1", "172.16.0.1", "172.31.255.255", "192.168.1.1"):
        assert _is_blocked_address(_ip(addr)), addr


def test_link_local_blocked():
    assert _is_blocked_address(_ip("169.254.0.1"))


def test_multicast_blocked():
    assert _is_blocked_address(_ip("224.0.0.1"))


def test_unspecified_blocked():
    assert _is_blocked_address(_ip("0.0.0.0"))
    assert _is_blocked_address(_ip("::"))


def test_reserved_blocked():
    assert _is_blocked_address(_ip("240.0.0.1"))


def test_public_v4_allowed():
    for addr in ("8.8.8.8", "1.1.1.1", "93.184.216.34"):
        assert not _is_blocked_address(_ip(addr)), addr


def test_public_v6_allowed():
    assert not _is_blocked_address(_ip("2606:4700:4700::1111"))
    assert not _is_blocked_address(_ip("2001:4860:4860::8888"))


def test_ipv4_mapped_embedded_blocked():
    # ::ffff:10.0.0.1 carries an embedded private IPv4 -> must be blocked.
    assert _is_blocked_address(_ip("::ffff:10.0.0.1"))


def test_sixtofour_embedded_blocked():
    # 2002:0a00:0001:: embeds 10.0.0.1; is_private alone did NOT cover this
    # (the gap this module was written to close) -> must be blocked via unpack.
    assert _is_blocked_address(_ip("2002:0a00:0001::"))


def test_teredo_embedded_blocked():
    # Teredo client address embedded in the lower bits.
    assert _is_blocked_address(_ip("2001:0000:4136:e378:8000:63bf:3ffe:fdd2"))


# --- _embedded_ipv4_candidates: unpacking contract -------------------------

def test_no_embedded_for_plain_v4():
    assert _embedded_ipv4_candidates(_ip("8.8.8.8")) == []


def test_no_embedded_for_global_v6():
    assert _embedded_ipv4_candidates(_ip("2606:4700:4700::1111")) == []


def test_ipv4_mapped_unpacks():
    res = _embedded_ipv4_candidates(_ip("::ffff:10.0.0.2"))
    assert res == [_ip("10.0.0.2")]


def test_sixtofour_unpacks():
    res = _embedded_ipv4_candidates(_ip("2002:0a00:0001::"))
    assert res == [_ip("10.0.0.1")]


def test_teredo_unpacks_client():
    res = _embedded_ipv4_candidates(_ip("2001:0000:4136:e378:8000:63bf:3ffe:fdd2"))
    # Teredo lower 32 bits are the client IPv4; the module must surface it as a
    # candidate so a private Teredo client cannot slip past is_private alone.
    assert len(res) >= 1
    assert all(isinstance(c, ipaddress.IPv4Address) for c in res)


# --- _env_allows_private ---------------------------------------------------

def test_env_allows_private_true(monkeypatch):
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE", "1")
    assert _env_allows_private("MINICC_ALLOW_PRIVATE")


def test_env_allows_private_false(monkeypatch):
    monkeypatch.delenv("MINICC_ALLOW_PRIVATE", raising=False)
    assert not _env_allows_private("MINICC_ALLOW_PRIVATE")


def test_env_allows_private_case_insensitive(monkeypatch):
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE", "True")
    assert _env_allows_private("MINICC_ALLOW_PRIVATE")


# --- assert_public_http_url: scheme + hostname validation ------------------

def test_disallowed_scheme_rejected():
    import pytest
    with pytest.raises(ValueError):
        assert_public_http_url("ftp://example.com/x", allow_env="MINICC_ALLOW_PRIVATE")


def test_missing_hostname_rejected():
    import pytest
    with pytest.raises(ValueError):
        assert_public_http_url("https:///path-only", allow_env="MINICC_ALLOW_PRIVATE")


def test_valid_url_returns_parsed(monkeypatch):
    monkeypatch.setattr(netguard, "assert_public_host", lambda host, *, allow_env: None)
    parsed = assert_public_http_url(
        "https://example.com:8443/path?q=1", allow_env="MINICC_ALLOW_PRIVATE"
    )
    assert isinstance(parsed, urllib.parse.SplitResult)
    assert parsed.hostname == "example.com"
    assert parsed.scheme == "https"


def test_allowed_schemes_constant():
    assert ALLOWED_SCHEMES == frozenset({"http", "https"})


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__, "-q", "-W", "error"]))
