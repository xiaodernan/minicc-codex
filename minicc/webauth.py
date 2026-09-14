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
from pathlib import Path
from urllib.parse import urlsplit

ENV_TOKEN = "MINICC_WEB_TOKEN"
TOKEN_FILE_NAME = "web_token.json"
TOKEN_BYTES = 32

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]", "::0"})
# Hostname suffixes that stay inside the developer's own machine even when the
# OS resolves several loopback names (localhost.<domain> on macOS, .local).
LOOPBACK_SUFFIXES = (".localhost", ".local")


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
    if store.is_file():
        try:
            data = json.loads(store.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise WebAuthError(f"无法读取 {store}: {exc}") from exc
        token = str(data.get("token") or "").strip()
        if token:
            return token, False
    token = generate_token()
    store.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"token": token}, ensure_ascii=False, indent=2)
    try:
        store.write_text(payload, encoding="utf-8")
        if os.name == "posix":
            os.chmod(store, 0o600)
    except OSError as exc:
        raise WebAuthError(f"无法写入 {store}: {exc}") from exc
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
