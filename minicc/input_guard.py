"""The one ``<field> 不能为空`` guard for JSON payload fields.

RPC params, HTTP POST bodies and task payloads arrive as ``Any``
from JSON.  Every reader of such a value needs the same two halves:
reject a missing, blank or non-string value with one message, and
hand back the stripped text.

The home is a leaf module on purpose.  ``web`` re-exports the HTTP
server, so ``webserver`` sits *below* ``web`` in the import order -
a home inside ``web`` is unreachable from the very transport that
needs it most, and that is exactly why ``webserver`` hand-rolled the
guard ten times: seven of those sites kept the isinstance half and
dropped the strip half, so ``"   "`` sailed through as a real session
id and a name with stray spaces was stored, looked up and audited
under a spelling no client ever sent.

Both halves matter: the isinstance half keeps a JSON number from
becoming a session id, the strip half keeps whitespace from becoming
a name.  A site that spells the message by hand owns neither half.
"""

from __future__ import annotations

from typing import Any


def require_text(raw: Any, field: str) -> str:
    """Return ``raw`` stripped, or raise naming ``field``."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field} 不能为空")
    return raw.strip()
