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


def assert_public_host(host: str, *, allow_env: str) -> None:
    """Reject hosts that resolve to private/loopback/reserved ranges."""
    if _env_allows_private(allow_env):
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise BlockedAddressError(f"无法解析主机 {host}: {exc}") from exc
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
]
