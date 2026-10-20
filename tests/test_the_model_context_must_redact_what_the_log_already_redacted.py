"""M8-T268: the model context must redact what the log already redacted.

The log filter owned three labelled-key patterns (``api_key=…``,
``"password": "…"``, ``?token=…``) and the model context owned none of them.
The same string was therefore masked in the log file and handed to the model
in plaintext - the tool output went through ``redact_text`` on its way into
the conversation, and ``redact_text`` only knew the *value* shapes
(``sk-…``, ``Bearer …``, JWTs, PEM blocks).

The patterns now live in one place, so the two sides cannot drift again.

This door pins:

* a labelled credential is masked in the model context;
* a labelled credential is still masked in the log;
* the pass stays idempotent, and ordinary text is left alone.
"""

from __future__ import annotations

import pytest

from minicc.logging_setup import REDACTED, redact
from minicc.tools.registry import redact_text

# Deliberately *not* matching any known value shape (no ``sk-``, no
# ``Bearer``, no JWT): if these strings survive, it is because the labelled
# form was not covered, not because a value-shape rule happened to catch them.
API_KEY = "Zx9q-local-provider-key-not-a-pattern-4242"
PASSWORD = "correct-horse-battery-staple-9001"
TOKEN = "8f14e45fceea167a5a36dedd4bea2543"


@pytest.mark.parametrize(
    "raw",
    [
        f'{{"api_key": "{API_KEY}"}}',
        f'api_key={API_KEY}',
        f"MINICC_API_KEY: {API_KEY}",
        f"?token={TOKEN}&x=1",
        f'"password": "{PASSWORD}"',
        f"password={PASSWORD}",
        f"Authorization: {TOKEN}",
    ],
)
def test_the_model_context_masks_a_labelled_credential(raw: str) -> None:
    """The half the model context was missing."""
    masked, changed = redact_text(raw)
    assert changed, f"the labelled credential was not recognised: {raw!r}"
    for needle in (API_KEY, PASSWORD, TOKEN):
        assert needle not in masked


@pytest.mark.parametrize(
    "raw",
    [
        f'{{"api_key": "{API_KEY}"}}',
        f"api_key={API_KEY}",
        f"?token={TOKEN}&x=1",
        f'"password": "{PASSWORD}"',
    ],
)
def test_the_log_still_masks_the_same_credential(raw: str) -> None:
    """The control: the log side must not lose what it already had."""
    masked = redact(raw)
    for needle in (API_KEY, PASSWORD, TOKEN):
        assert needle not in masked
    assert REDACTED in masked


def test_the_two_sides_now_agree_on_what_is_a_credential() -> None:
    """The drift this door exists for: same input, same verdict."""
    raw = f'{{"api_key": "{API_KEY}"}}'
    model_side, model_changed = redact_text(raw)
    log_side = redact(raw)
    assert model_changed and API_KEY not in model_side
    assert API_KEY not in log_side


def test_the_pass_is_idempotent_on_the_model_side() -> None:
    raw = f"api_key={API_KEY} password={PASSWORD}"
    once, _changed = redact_text(raw)
    twice, _changed_again = redact_text(once)
    assert once == twice
    assert API_KEY not in once and PASSWORD not in once


def test_the_log_pass_is_still_idempotent() -> None:
    raw = f"api_key={API_KEY} password={PASSWORD}"
    once = redact(raw)
    assert redact(once) == once


def test_ordinary_text_is_left_alone() -> None:
    """The control: the labelled rules must not eat normal content."""
    text = "request body rejected: message 不能为空 (task-abc123)"
    masked, changed = redact_text(text)
    assert changed is False, f"ordinary text was rewritten: {masked!r}"
    assert masked == text


def test_an_already_redacted_value_is_not_wrapped_again() -> None:
    """M8-T268 regression: the quoted rule's value accepts brackets.

    The mcp.json headers are redacted to ``[REDACTED]`` by their own step
    before the model context sees them, so a second pass must leave that
    marker alone - otherwise it grew into ``[REDACTED:credential]`` and the
    file preview stopped matching the shape it promises.
    """
    raw = '{"servers": {"docs": {"headers": {"Authorization": "[REDACTED]"}}}}'
    masked, _changed = redact_text(raw)
    assert "[REDACTED]" in masked
    assert "[REDACTED:credential]" not in masked
    assert masked == raw, "an already-redacted value was rewritten"
