"""Independent fence tests for ``minicc.mentions`` token extraction + injection.

``extract_mention_tokens`` is pure (regex + dedup + cap). ``build_mention_context``
needs a workspace on disk, so the integration-side cases use a repo-external
temp dir (never the repo working tree) to avoid the git deletion guard.

Run directly or via the repo gate:
    python tests/test_mentions_pure.py
    python -m pytest tests/test_mentions_pure.py -q -W error
"""

import tempfile
from pathlib import Path

from minicc import mentions
from minicc.mentions import MENTION_MAX_FILES, apply_mentions, build_mention_context, extract_mention_tokens


# --- extract_mention_tokens: pure regex fence --------------------------------

def test_single_token():
    assert extract_mention_tokens("see @src/app.py here") == ["src/app.py"]


def test_email_not_a_mention():
    # a@b.com: the @ is preceded by an ASCII letter -> negative lookbehind
    # must exclude it (otherwise every email becomes a mention).
    assert extract_mention_tokens("write a@b.com please") == []


def test_cjk_prefix_allowed():
    # CJK before @ is not an ASCII alnum, so the lookbehind passes.
    assert extract_mention_tokens("用户@a.py 是什么") == ["a.py"]


def test_trailing_fullwidth_punctuation_stripped():
    # 。 (U+3002) is in the excluded class and in _TRAILING_PUNCTUATION.
    assert extract_mention_tokens("@a.py。") == ["a.py"]


def test_multiple_tokens_ordered():
    assert extract_mention_tokens("@a.py @b.py @c.py") == ["a.py", "b.py", "c.py"]


def test_dedup_preserves_first():
    assert extract_mention_tokens("@a.py @a.py @b.py") == ["a.py", "b.py"]


def test_cjk_glued_token_kept():
    # hand-typed CJK glues onto the path; the tokenizer keeps it (the resolver
    # later walks it back to a real file).
    assert extract_mention_tokens("@a.py是什么") == ["a.py是什么"]


def test_max_files_capped():
    names = " ".join(f"@f{i}.py" for i in range(MENTION_MAX_FILES + 5))
    tokens = extract_mention_tokens(names)
    assert len(tokens) == MENTION_MAX_FILES


def test_alphanum_before_at_excluded():
    assert extract_mention_tokens("x@y") == []


def test_empty_message():
    assert extract_mention_tokens("") == []


# --- build_mention_context: workspace-backed injection fence -----------------

def _ws_with(files: dict[str, bytes]):
    d = tempfile.TemporaryDirectory()
    root = Path(d.name)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    return d, root


def test_injected_block_contains_file():
    d, root = _ws_with({"f.py": b"hello world"})
    try:
        block, records = build_mention_context("read @f.py", root)
        assert records and records[0]["status"] == "injected"
        assert 'path="f.py"' in block
        assert "hello world" in block
    finally:
        d.cleanup()


def test_drive_letter_absolute_rejected():
    # A drive-letter path is rejected identically on every platform (the code
    # matches "^[A-Za-z]:" precisely because "/etc/..." is only absolute on
    # POSIX). This must be rejected with the absolute-path reason.
    d, root = _ws_with({})
    try:
        block, records = build_mention_context("x @C:/Windows/system32", root)
        assert records and records[0]["status"] == "rejected"
        assert "绝对路径" in records[0]["reason"]
    finally:
        d.cleanup()


def test_posix_absolute_rejected_or_out_of_workspace():
    # On POSIX "/etc/passwd" is absolute; on Windows it is rooted-but-driveless
    # and lands in the workspace-escape branch. Either way it is rejected.
    d, root = _ws_with({})
    try:
        block, records = build_mention_context("x @/etc/passwd", root)
        assert records and records[0]["status"] == "rejected"
    finally:
        d.cleanup()


def test_home_path_rejected():
    d, root = _ws_with({})
    try:
        block, records = build_mention_context("x @~/secret", root)
        assert records and records[0]["status"] == "rejected"
    finally:
        d.cleanup()


def test_minicc_credential_denied():
    # allowlist.json is in the deny set -> must never be injected.
    d, root = _ws_with({".minicc/allowlist.json": b"token"})
    try:
        block, records = build_mention_context("x @.minicc/allowlist.json", root)
        assert records and records[0]["status"] == "rejected"
        assert ".minicc" in records[0]["reason"]
    finally:
        d.cleanup()


def test_missing_file_annotated():
    d, root = _ws_with({})
    try:
        block, records = build_mention_context("x @nope.txt", root)
        assert records and records[0]["status"] == "missing"
    finally:
        d.cleanup()


def test_binary_file_rejected():
    d, root = _ws_with({"bin": b"\x00\x01\x02"})
    try:
        block, records = build_mention_context("x @bin", root)
        assert records and records[0]["status"] == "binary"
    finally:
        d.cleanup()


def test_apply_mentions_appends_block():
    d, root = _ws_with({"f.py": b"data"})
    try:
        msg, records = apply_mentions("hi @f.py", root)
        assert "hi" in msg
        assert 'path="f.py"' in msg
        assert records[0]["status"] == "injected"
    finally:
        d.cleanup()


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__, "-q", "-W", "error"]))
