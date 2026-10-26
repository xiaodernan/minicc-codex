"""M8-T520: a word-shaped credential must not become a rewrite rule over ordinary text.

The registry in :mod:`minicc.logging_setup` holds *exact* values, and masking them was a plain
``segment.replace(secret, REDACTED)`` - no boundary. ``MIN_SECRET_LENGTH = 4`` is the only thing
admitting a value, so ``api_key="test"`` (a fixture in ``tests/test_completion_liveness.py``)
entered the module-global registry and then rewrote ``tests/``, ``latest`` and ``attested`` in
every later log line of that process. The operator-visible damage: a red message naming a pytest
tmp directory and a test function, both chewed up, so the door's own verdict became unreadable.

``minicc/tools/registry.py`` already knows this on the pattern axis - its ``sk-`` rule carries
``(?<![A-Za-z0-9])`` because "task ids must remain stable". The exact-value registry was the one
face that never asked.

These legs read production through ``redact()`` / ``_registered()``, never a copy of the rule, and
each one restores the registry around itself: a gate that registers a word-shaped value and leaves
it there would *cause* the order-dependent red it exists to prevent.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from minicc import logging_setup
from minicc.logging_setup import REDACTED, configure_logging, get_logger, redact, register_secret

WORD_VALUE = "test"
DASHED_VALUES = (
    "Zx9q-local-provider-key-not-a-pattern-4242",
    "Wt7k-local-web-token-not-a-pattern-9182",
    "ab12-cd34-ef56",
)
LONG_WORD_VALUE = "notarealbutlongewordvalue"


@contextmanager
def registry(*values: str) -> Iterator[None]:
    """Install *values* as the whole registry for the body, then give back what was there."""
    saved = set(logging_setup._secrets)  # noqa: SLF001
    logging_setup._secrets.clear()  # noqa: SLF001
    for value in values:
        register_secret(value)
    try:
        yield
    finally:
        logging_setup._secrets.clear()  # noqa: SLF001
        logging_setup._secrets.update(saved)  # noqa: SLF001


def test_a_word_shaped_credential_masks_a_bare_occurrence() -> None:
    """The fix may not be "word-shaped values are ignored": standing alone, the value is masked.

    The line carries no ``key =`` / ``token:`` label on purpose: the labelled-key patterns mask
    ``provider key = test`` with an **empty** registry, so a leg written that way stays green even
    when the exact-value registry masks nothing (arm A6 measures exactly that).
    """
    with registry(WORD_VALUE):
        out = redact("the run stopped after test failed")
        assert REDACTED in out, f"a bare occurrence of the registered value survived unmasked: {out!r}"
        assert "after test failed" not in out, f"the registered value is still readable in the line: {out!r}"
        assert out.count(REDACTED) == 1, f"only the value itself may be replaced, not the sentence: {out!r}"


def test_the_same_credential_does_not_rewrite_a_longer_identifier() -> None:
    """The defect: the value glued inside longer words and paths was masked too, every time."""
    line = "task started in tests/test_core.py while the latest answer is attested"
    with registry(WORD_VALUE):
        out = redact(line)
        assert out == line, (
            "a word-shaped credential rewrote text that is not it: "
            f"{line!r} -> {out!r}"
        )
        for glued in ("tests/", "test_core.py", "latest", "attested"):
            assert glued in out, f"the identifier {glued!r} did not survive masking: {out!r}"


def test_a_punctuation_bearing_credential_still_masks_glued() -> None:
    """The safety ceiling of this batch: values that are not word-shaped keep substring masking."""
    value = DASHED_VALUES[0]
    glued = f"x=prefix{value}suffix"
    with registry(value):
        out = redact(glued)
        assert value not in out, f"a dashed credential stopped being masked where it is glued: {out!r}"
        assert out == "x=prefix" + REDACTED + "suffix", (
            f"the non-word-shaped branch must mask exactly as substring masking did: {out!r}"
        )


@pytest.mark.parametrize("value", ["admin", "public", "hunter2", LONG_WORD_VALUE])
def test_the_class_is_the_values_shape_not_a_word_list(value: str) -> None:
    """Both clauses repeat for synthetic word-shaped values, so the branch cannot be a table of words."""
    bare = f"the config value is {value} now"
    glued_prefix = f"the {value}ification and pre{value} are unrelated"
    with registry(value):
        assert REDACTED in redact(bare), f"a word-shaped credential is not masked standing alone: {bare!r}"
        kept = redact(glued_prefix)
        assert kept == glued_prefix, (
            f"a word-shaped credential rewrote identifiers that merely contain it: {glued_prefix!r} -> {kept!r}"
        )
        assert f"{value}ification" in kept and f"pre{value}" in kept, kept


def test_the_class_is_the_values_shape_not_its_length() -> None:
    """A long word-shaped value takes the same branch as a 4-char one; length only admits."""
    line = f"run {LONG_WORD_VALUE} inside my{LONG_WORD_VALUE}dir"
    with registry(LONG_WORD_VALUE, WORD_VALUE):
        out = redact(line)
        assert REDACTED in out, f"the standalone occurrence of a long word-shaped value survived: {out!r}"
        assert f"my{LONG_WORD_VALUE}dir" in out, (
            f"the long value was masked by substring, as if its length made it a real secret: {out!r}"
        )
        assert out.count(REDACTED) == 1, f"only one of the two occurrences is the value: {out!r}"
    short = "x" * (logging_setup.MIN_SECRET_LENGTH - 1)
    with registry(short):
        assert short not in logging_setup._secrets, (  # noqa: SLF001
            f"a value shorter than MIN_SECRET_LENGTH={logging_setup.MIN_SECRET_LENGTH} entered the registry"
        )


def test_cjk_adjacent_occurrences_are_still_masked() -> None:
    """The boundary class is ASCII words only, so a value glued to CJK is still the value."""
    line = "使用test登录失败"
    with registry(WORD_VALUE):
        out = redact(line)
        assert REDACTED in out, (
            f"an ASCII word-shaped value next to CJK went unmasked - the boundary class is too wide: {out!r}"
        )
        assert out == "使用" + REDACTED + "登录失败", out


def test_idempotence_holds_under_the_boundary_rule() -> None:
    """A second pass over the masked line changes nothing, on every shape this batch touches."""
    cases = (
        f"the run stopped after {WORD_VALUE} failed",
        "task started in tests/test_core.py while the latest answer is attested",
        "x=prefix" + DASHED_VALUES[2] + "suffix",
        f"使用{WORD_VALUE}登录失败",
        "failed with key [REDACTED:api_key] and the bare value api_key echoed",
    )
    with registry(WORD_VALUE, "api_key", *DASHED_VALUES):
        for line in cases:
            once = redact(line)
            twice = redact(once)
            assert once == twice, f"masking is not idempotent: {line!r} -> {once!r} -> {twice!r}"
            assert "]]" not in twice and "[" + REDACTED not in twice, f"a marker grew inside a marker: {twice!r}"


def test_the_marker_guard_survives_the_boundary_rule() -> None:
    """The pre-existing marker defence (tests/test_logging.py:736) must still hold after this change.

    The value here is chosen so its own spelling also names a marker label: without the guard,
    masking would run *inside* ``[REDACTED:api_key]`` and every pass would grow the line.
    """
    line = "failed with key [REDACTED:api_key] and the bare value api_key echoed"
    with registry("api_key"):
        once = redact(line)
        assert "[REDACTED:api_key]" in once, (
            f"an upstream marker was rewritten by the registry: {once!r}"
        )
        assert "api_key echoed" not in once, f"the standalone occurrence went unmasked: {once!r}"
        assert "]]" not in once, f"masking nested inside an existing marker: {once!r}"
        assert redact(once) == once, f"a second pass grows the line: {once!r} -> {redact(once)!r}"


def test_the_admission_floor_is_unchanged_and_derived() -> None:
    """The floor is read from MIN_SECRET_LENGTH itself, so the gate cannot rot when it moves."""
    floor = logging_setup.MIN_SECRET_LENGTH
    below = "a" * (floor - 1)
    at = "b" * floor
    with registry(below, at):
        secrets = set(logging_setup._secrets)  # noqa: SLF001
        assert at in secrets, f"a value of exactly MIN_SECRET_LENGTH={floor} was refused: {secrets}"
        assert below not in secrets, (
            f"a value of {floor - 1} chars was admitted; the floor {floor} is what this gate pins"
        )


def test_a_real_handler_line_keeps_its_path_intact(tmp_path: Path) -> None:
    """The whole chain - register, format, filter, write - not just the masking helper."""
    saved_handlers = list(logging.getLogger(logging_setup.ROOT_NAME).handlers)
    saved_flag = logging_setup._configured  # noqa: SLF001
    target = tmp_path / "oplog.txt"
    try:
        with registry(WORD_VALUE):
            configure_logging(level="WARNING", log_file=target, force=True)
            get_logger("web").warning("retry after test failed while loading tests/test_core.py")
            for handler in logging.getLogger(logging_setup.ROOT_NAME).handlers:
                handler.flush()
            written = target.read_text(encoding="utf-8")
            assert "tests/test_core.py" in written, (
                f"the log file lost a path that never was the credential: {written!r}"
            )
            assert REDACTED in written, (
                f"the standalone occurrence never reached the file masked: {written!r}"
            )
            assert "after test failed" not in written, (
                f"the registered credential reached the log file in the clear: {written!r}"
            )
    finally:
        logger = logging.getLogger(logging_setup.ROOT_NAME)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        for handler in saved_handlers:
            logger.addHandler(handler)
        logging_setup._configured = saved_flag  # noqa: SLF001


def test_the_registry_masks_at_least_as_much_as_before_on_dashed_values() -> None:
    """Three dashed credentials x three placements each: byte-identical to plain substring masking."""
    for value in DASHED_VALUES:
        for line in (
            f"key = {value}",
            f"prefix{value}suffix",
            f'config: "{value}"',
        ):
            with registry(value):
                out = redact(line)
                assert value not in out, f"{value!r} survived the placement {line!r}: {out!r}"
                assert out == line.replace(value, REDACTED), (
                    f"the non-word-shaped branch diverged from substring masking for {line!r}: {out!r}"
                )
