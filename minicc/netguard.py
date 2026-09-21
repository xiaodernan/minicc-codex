"""Shared SSRF checks for webfetch and HTTP MCP URLs."""

from __future__ import annotations

import ipaddress
import os
import socket
import urllib.parse

from .config import TRUTHY

ALLOWED_SCHEMES = frozenset({"http", "https"})


class BlockedAddressError(ValueError):
    """A hostname resolved to a private, loopback, or reserved address."""


def _env_allows_private(allow_env: str) -> bool:
    return os.getenv(allow_env, "").strip().lower() in TRUTHY


def _resolve_and_validate(host: str) -> str:
    """Resolve ``host`` once, reject any private/reserved address, return first public IP.

    Resolving exactly once and returning the address lets callers *pin* the
    connection to this IP, closing the DNS-rebinding window where a hostname
    resolves publicly at check time but to loopback at connect time.
    """
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise BlockedAddressError(f"无法解析主机 {host}: {exc}") from exc
    pinned = ""
    for info in infos:
        address = str(info[4][0])
        try:
            ip = ipaddress.ip_address(address.split("%")[0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise BlockedAddressError(f"IP {ip} 属于私有/保留地址段，已按 SSRF 防护拒绝")
        if not pinned:
            pinned = str(ip)
    if not pinned:
        raise BlockedAddressError(f"主机 {host} 没有可用的 IP 地址")
    return pinned


def assert_public_host(host: str, *, allow_env: str) -> None:
    """Reject hosts that resolve to private/loopback/reserved ranges."""
    if _env_allows_private(allow_env):
        return
    _resolve_and_validate(host)


def resolve_pinned_host(host: str, *, allow_env: str) -> str:
    """Resolve once, validate, and return the IP to pin connections to.

    Returns ``""`` when private fetches are explicitly allowed via ``allow_env``
    (callers then connect by hostname as usual).
    """
    if _env_allows_private(allow_env):
        return ""
    return _resolve_and_validate(host)


def assert_public_http_url(url: str, *, allow_env: str) -> urllib.parse.ParseResult:
    """Parse an http(s) URL and reject private/loopback targets."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"仅支持 http/https URL: {url!r}")
    if not parsed.hostname:
        raise ValueError(f"URL 缺少主机名: {url!r}")
    assert_public_host(parsed.hostname, allow_env=allow_env)
    return parsed


__all__ = [
    "ALLOWED_SCHEMES",
    "BlockedAddressError",
    "assert_public_host",
    "assert_public_http_url",
    "resolve_pinned_host",
]
