"""M8-T907: the send boundary and the session store ship the same bytes.

Root cause chain, measured on the live gateway: the session store sanitized
history at save time, so the disk carried redacted digests where the
previous task's request had shipped the raw bytes; the next task loaded that
history and the gateway's prefix cache died from the first redacted message
onward (``hit=0`` on a 51k-token prefix that should have extended, while the
same shape with an unredacted history hit 94.6%). The fix ships the
sanitized shape at the send boundary: the provider's outbound copy, the
store's saved payload, and therefore every prefix fingerprint now agree by
construction.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from minicc.llm.openai_provider import redact_outbound_messages
from minicc.llm.usage import prefix_fingerprint
from minicc.tools.registry import redact_message


def _history_with_secrets() -> list[dict]:
    digest = "a" * 64
    return [
        {"role": "system", "content": "你是 minicc。"},
        {"role": "user", "content": "读取 README.md"},
        {"role": "tool", "content": f'{{"digest": "{digest}", "key": "sk-abc123def456"}}'},
        {"role": "tool", "nested": {"authorization": "Bearer abcdefghij1234"}},
    ]


def test_secrets_are_redacted_before_shipping():
    shipped = redact_outbound_messages(_history_with_secrets())
    assert "sk-abc123def456" not in shipped[2]["content"], "the api key must not reach the gateway"
    assert "Bearer abcdefghij1234" not in str(shipped[3]), "the bearer token must not reach the gateway"
    # the digest is not a credential-shaped value and survives untouched,
    # which is exactly what keeps the cache prefix meaningful
    assert "a" * 64 in shipped[2]["content"]


def test_callers_live_list_is_never_mutated():
    messages = _history_with_secrets()
    before = [dict(item) for item in messages]
    redact_outbound_messages(messages)
    assert messages == before, "the agent loop's live history must stay verbatim"


def test_redaction_is_idempotent_so_shipped_and_stored_agree():
    once = redact_outbound_messages(_history_with_secrets())
    twice = redact_outbound_messages(once)
    assert once == twice, "shipping sanitized input must be byte-stable"

    # the contract that fixes the cache: the shape shipped from the live
    # (verbatim) history equals the shape shipped from the store's
    # (redacted) reload of that same history
    from_store = redact_outbound_messages(
        [{"role": "tool", "content": 'file digest: sk-abc123def456'}]
    )
    from_memory = redact_outbound_messages(
        [{"role": "tool", "content": 'file digest: sk-abc123def456'}]
    )
    assert from_store == from_memory
    assert prefix_fingerprint(from_store)["msgs_fp"] == prefix_fingerprint(from_memory)["msgs_fp"]


def test_store_and_send_share_one_recursive_shape():
    # the session's _redacted_message must be the same function the provider
    # ships through - a second hand-rolled copy is a drift waiting to happen
    session_src = Path(__file__).resolve().parent.parent.joinpath("minicc", "session.py").read_text(encoding="utf8")
    assert "return redact_message(message)" in session_src, "session sanitization must delegate to the shared shape"
    body = session_src.split("def _redacted_message")[1].split("def _non_negative_int")[0]
    assert "redact_text(value)[0]" not in body, "the old inline recursion must be gone"


def test_provider_ships_the_sanitized_copy_on_both_attempt_paths():
    provider_src = Path(__file__).resolve().parent.parent.joinpath("minicc", "llm", "openai_provider.py").read_text(encoding="utf8")
    body = provider_src.split("async def _attempt_once")[1].split("# -- client")[0]
    assert body.count("redact_outbound_messages(messages)") == 1, "one sanitization at the boundary"
    assert body.count("await self._responses_once(outbound") == 2, "both protocol paths ship the sanitized copy"
    assert body.count("await self._chat_completions_once(outbound") == 2
    assert body.count("prefix_fingerprint(outbound, tools)") == 2, "the fingerprint reads the shipped bytes"
    assert "prefix_fingerprint(messages" not in body, "fingerprinting the unsanitized list would lie about the prefix"


def test_redact_message_handles_non_string_scalars():
    assert redact_message(42) == 42
    assert redact_message(None) is None
    assert redact_message({"deep": {"list": ["sk-abc123def456", 7, None]}}) == {
        "deep": {"list": ["[REDACTED:llm_api_key]", 7, None]}
    }
