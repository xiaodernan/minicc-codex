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


def _embedded_ipv4_candidates(ip: "ipaddress.IPv4Address | ipaddress.IPv6Address") -> list["ipaddress.IPv4Address"]:
    """嵌入式 IPv4 形态的解包：IPv4-mapped / 6to4 / Teredo 客户端地址。

    部分形态（6to4 实测）不被 ``is_private`` 覆盖——一个 6to4 AAAA 记录
    （2002:0a00:0001:: 嵌入 10.0.0.1）会带着 False 畅通通过私网检查。
    解包后按 IPv4 统一校验，结论不再依赖 Python 版本对各类 tunnel 形态的
    属性判定。
    """
    embedded: list["ipaddress.IPv4Address"] = []
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        embedded.append(mapped)
    sixtofour = getattr(ip, "sixtofour", None)
    if sixtofour is not None:
        embedded.append(sixtofour)
    teredo = getattr(ip, "teredo", None)
    if teredo:
        client = teredo[1] if isinstance(teredo, tuple) else (teredo.get("client") if isinstance(teredo, dict) else None)
        if client is not None:
            embedded.append(client)
    return embedded


def _is_blocked_address(ip: "ipaddress.IPv4Address | ipaddress.IPv6Address") -> bool:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    return any(
        v4.is_private
        or v4.is_loopback
        or v4.is_link_local
        or v4.is_reserved
        for v4 in _embedded_ipv4_candidates(ip)
    )


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
        if _is_blocked_address(ip):
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
