"""M8-T121: netguard must reject multicast addresses on the multicast clause.

224.0.0.1 and ff02::1 are the two SSRF-relevant addresses for which
``is_multicast`` is the *sole* blocking term: measured on this interpreter,
both report False for is_private, is_loopback, is_link_local, is_reserved and
is_unspecified. If ``is_multicast`` is ever dropped from the guard, the pinned
resolver returns them as if public and the caller dials a multicast group.

The controls pin the half a naive edit would also break: loopback, link-local
and reserved refusals do not depend on the multicast term (each also trips
is_private), and the public control proves resolution really flows - so a
multicast refusal can only come from the clause under test, never from a
broken fixture that refuses everything.
"""

from __future__ import annotations

import socket

import pytest

from minicc.netguard import BlockedAddressError, resolve_pinned_host

# A name the suite never sets, so the guard is always armed for these calls.
GUARD_ARMED = "MINICC_T121_GUARD_IS_ON"


def _pinned(monkeypatch: pytest.MonkeyPatch, ip: str) -> str:
    monkeypatch.delenv(GUARD_ARMED, raising=False)
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", (ip, 0))]
    )
    return resolve_pinned_host("target.test", allow_env=GUARD_ARMED)


@pytest.mark.parametrize("addr", ["224.0.0.1", "ff02::1"])
def test_multicast_is_blocked(monkeypatch: pytest.MonkeyPatch, addr: str) -> None:
    with pytest.raises(BlockedAddressError):
        _pinned(monkeypatch, addr)


@pytest.mark.parametrize("addr", ["127.0.0.1", "169.254.1.1", "240.0.0.1"])
def test_non_multicast_refusals_survive(monkeypatch: pytest.MonkeyPatch, addr: str) -> None:
    """Loopback/link-local/reserved stay refused without the multicast term."""
    with pytest.raises(BlockedAddressError):
        _pinned(monkeypatch, addr)


def test_public_address_is_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Control: a public address resolves and pins rather than being refused."""
    assert _pinned(monkeypatch, "93.184.216.34") == "93.184.216.34"
