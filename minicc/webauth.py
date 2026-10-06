"""Authentication and origin policy for the local web workbench.

The workbench is a single-user local product. Two deployment shapes exist:

- loopback binding (default): auth stays available but is not required, so
  existing local workflows and smoke tests keep working unchanged.
- non-loopback binding (``--host 0.0.0.0`` etc.): a token is mandatory. The
  token is provided explicitly (``--token`` / ``MINICC_WEB_TOKEN``) or
  auto-generated and persisted under ``<workspace>/.minicc/web_token.json``.

EventSource cannot send headers, so the token is accepted from both the
``Authorization: Bearer`` header and a ``token`` query parameter.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import string
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

ENV_TOKEN = "MINICC_WEB_TOKEN"


def _read_store_json(store: Path) -> object:
    """Read the token store, riding out brief replace-induced open denials.

    os.replace is atomic, but on Windows a CreateFile racing the directory
    swap can briefly get ACCESS_DENIED (Errno 13); the window is
    microseconds, so a short backoff always wins. JSONDecodeError is not
    retried - an atomic replace can never expose a half-written file.
    """
    last_exc: PermissionError | None = None
    for attempt in range(8):
        try:
            return json.loads(store.read_text(encoding="utf-8"))
        except PermissionError as exc:
            last_exc = exc
            time.sleep(0.005 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _atomic_replace(source: Path, dest: Path) -> None:
    """os.replace with a short backoff for concurrent-destination denials.

    On Windows, replacing a destination that another thread is reading (or
    replacing) fails with PermissionError; the window is microseconds, so
    the backoff always wins. POSIX replace is atomic and never hits this.
    """
    for attempt in range(8):
        try:
            os.replace(source, dest)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.01 * (attempt + 1))
TOKEN_FILE_NAME = "web_token.json"
TOKEN_BYTES = 32

# `::0` is deliberately absent: it normalizes to `::`, the IPv6 UNSPECIFIED /
# all-interfaces address (ip_address("::0").is_unspecified is True,
# .is_loopback is False) — the analogue of `0.0.0.0`, which is likewise not
# listed. Treating it as loopback let `--host ::0` bind every interface while
# requiring no token, and echoed an `http://[::0]` Origin (M8-T117).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
# Hostname suffixes that stay inside the developer's own machine even when
# the OS resolves several loopback names (``localhost.<domain>`` on macOS).
#
# M3-T2: ``.local`` was removed — it is mDNS/Bonjour, not loopback. Any host
# on the LAN can claim ``evil.local``, and treating it as loopback meant
# ``Origin: http://evil.local`` was echoed back in Access-Control-Allow-Origin
# and (via the same predicate) ``--host evil.local`` skipped mandatory auth.
LOOPBACK_SUFFIXES = (".localhost",)


class WebAuthError(RuntimeError):
    """Token storage is unreadable or the token is invalid."""


def is_loopback_host(host: str | None) -> bool:
    raw = str(host or "").strip().lower()
    if not raw:
        return False
    if raw in LOOPBACK_HOSTS:
        return True
    host_part = raw.rsplit(":", 1)[0] if raw.count(":") == 1 else raw
    host_part = host_part.strip("[]")
    if host_part in LOOPBACK_HOSTS:
        return True
    return any(host_part.endswith(suffix) for suffix in LOOPBACK_SUFFIXES)


def generate_token() -> str:
    # URL-safe alphabet without padding so the token can also be pasted into
    # an EventSource query string without escaping.
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(TOKEN_BYTES * 2))


def token_store_path(workspace: Path) -> Path:
    return Path(workspace) / ".minicc" / TOKEN_FILE_NAME


def load_or_create_token(workspace: Path, explicit: str | None = None) -> tuple[str, bool]:
    """Return ``(token, created)``.

    Precedence: explicit argument > ``MINICC_WEB_TOKEN`` > persisted file.
    When no token exists anywhere a new one is generated and persisted with
    owner-only permissions.
    """
    if explicit and explicit.strip():
        return explicit.strip(), False
    env_token = os.getenv(ENV_TOKEN, "").strip()
    if env_token:
        return env_token, False
    store = token_store_path(workspace)
    try:
        exists = store.is_file()
    except OSError as exc:
        # A state dir without the execute bit (e.g. chmod 0o444) makes even
        # stat() fail with EACCES; surface it as WebAuthError, not a bare
        # PermissionError leaking out of the web server startup path.
        raise WebAuthError(f"无法访问 {store}: {exc}") from exc
    if exists:
        try:
            data = _read_store_json(store)
        except (json.JSONDecodeError, OSError) as exc:
            raise WebAuthError(f"无法读取 {store}: {exc}") from exc
        if not isinstance(data, dict):
            raise WebAuthError(f"{store} 顶层必须是 JSON 对象，得到 {type(data).__name__!r}")
        token = str(data.get("token") or "").strip()
        if token:
            return token, False
    token = generate_token()
    store.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"token": token}, ensure_ascii=False, indent=2)
    # Re-check after the generation window: a racing thread may have already
    # written a complete store while we generated ours; prefer the winner and
    # skip the replace entirely, which removes almost all replace-replace
    # contention under a thundering-herd first startup.
    winner = ""
    try:
        existing = _read_store_json(store)
        if isinstance(existing, dict):
            winner = str(existing.get("token") or "").strip()
    except (json.JSONDecodeError, OSError):
        pass
    if winner:
        return winner, False
    # Write-then-replace (same shape as benchmarks._write_results): a racing
    # first-startup thread must never observe a half-written store. CI run
    # 37525348677 caught exactly that - thread B's is_file() saw the file
    # thread A was still writing and died on JSONDecodeError inside the read
    # path. os.replace is atomic on both POSIX and Windows.
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=store.parent,
            prefix=f".{store.name}.", suffix=".tmp", delete=False,
        ) as handle:
            tmp = Path(handle.name)
            temporary = tmp
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _atomic_replace(tmp, store)
        temporary = None
    except OSError as exc:
        raise WebAuthError(f"无法写入 {store}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    if os.name == "posix":
        try:
            os.chmod(store, 0o600)
        except OSError as exc:
            raise WebAuthError(f"无法设置 {store} 权限: {exc}") from exc
    return token, True


class WebAuth:
    """Stateless bearer-token check with timing-safe comparison."""

    def __init__(self, token: str, *, required: bool) -> None:
        self.token = token
        self.required = bool(required)

    def check(self, presented: str | None) -> bool:
        if not self.required:
            return True
        if not presented:
            return False
        return hmac.compare_digest(self.token, presented.strip())

    def check_headers(self, headers: object, query_token: str | None = None) -> bool:
        header_value = ""
        try:
            header_value = str(headers.get("Authorization", "") or "")
        except AttributeError:
            header_value = ""
        if header_value.lower().startswith("bearer "):
            if self.check(header_value[7:]):
                return True
        # Fallback for EventSource, which cannot attach headers.
        if query_token and self.check(query_token):
            return True
        # Not required means the endpoint is open regardless of credentials.
        return not self.required


def origin_allowed(origin: str | None) -> bool:
    """Allow same-origin requests (no Origin header) and loopback origins.

    Cross-origin JavaScript from any other site must not read the API. Browsers
    only enforce this through CORS response headers, so the server omits them
    unless the origin is one of the developer's own loopback origins.
    """
    if not origin:
        return False
    parsed = urlsplit(origin.strip())
    if parsed.scheme not in {"http", "https"}:
        return False
    return is_loopback_host(parsed.hostname)


def cors_origin(origin: str | None) -> str | None:
    return origin if origin_allowed(origin) else None
