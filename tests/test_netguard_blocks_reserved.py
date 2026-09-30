"""M8-T122: netguard must reject reserved-only IPv6 addresses on the reserved clause.

3ff::1 and 5f00::1 (the legacy IPv6 benchmarking range) are refused by no term in
the guard except ``is_reserved``: measured on this interpreter both report False
for is_private, is_loopback, is_link_local, is_multicast and is_unspecified. If
that term is ever dropped, the pinned resolver returns them as if public.

The controls pin the scope of such an edit. 240.0.0.1 and 255.255.255.255 are
reserved *and* private, 224.0.0.1 is multicast, and 127.0.0.1 is loopback - so all
four stay refused when only the reserved term is removed. A public address pins
rather than being refused, proving resolution flows and only bad ranges refuse.
"""

from __future__ import annotations

import socket

import pytest

from minicc.netguard import BlockedAddressError, resolve_pinned_host

# A name the suite never sets, so the guard is always armed for these calls.
GUARD_ARMED = "MINICC_T122_GUARD_IS_ON"


def _pinned(monkeypatch: pytest.MonkeyPatch, ip: str) -> str:
    monkeypatch.delenv(GUARD_ARMED, raising=False)
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", (ip, 0))]
    )
    return resolve_pinned_host("target.test", allow_env=GUARD_ARMED)


@pytest.mark.parametrize("addr", ["3ff::1", "5f00::1"])
def test_reserved_only_ipv6_is_blocked(monkeypatch: pytest.MonkeyPatch, addr: str) -> None:
    with pytest.raises(BlockedAddressError):
        _pinned(monkeypatch, addr)


@pytest.mark.parametrize("addr", ["240.0.0.1", "255.255.255.255", "224.0.0.1", "127.0.0.1"])
def test_refusals_survive_without_reserved_term(monkeypatch: pytest.MonkeyPatch, addr: str) -> None:
    """Each control is refused by a clause other than is_reserved."""
    with pytest.raises(BlockedAddressError):
        _pinned(monkeypatch, addr)


def test_public_address_is_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Control: a public address resolves and pins rather than being refused."""
    assert _pinned(monkeypatch, "93.184.216.34") == "93.184.216.34"
