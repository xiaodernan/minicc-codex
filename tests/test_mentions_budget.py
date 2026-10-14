"""Fence tests for ``minicc.mentions`` injection-budget and redact gate.

Companion to ``test_mentions_pure.py``: that file pins tokenization and the
reject/missing/binary gates; this one pins the per-file/per-message budget,
truncation marking, the ``omitted`` outcome, and the ``redact`` gate
(``.minicc/mcp.json`` content is injected but secrets are scrubbed).

Run directly or via the repo gate:
    python tests/test_mentions_budget.py
    python -m pytest tests/test_mentions_budget.py -q -W error
"""

import tempfile
from pathlib import Path

from minicc.mentions import build_mention_context


def _ws_with(files: dict[str, bytes]):
    d = tempfile.TemporaryDirectory()
    root = Path(d.name)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    return d, root


def test_within_budget_not_truncated():
    d, root = _ws_with({"f.txt": b"short"})
    try:
        block, records = build_mention_context(
            "@f.txt", root, max_chars_per_file=100, max_total_chars=1000
        )
        assert records[0]["status"] == "injected"
        assert records[0]["truncated"] is False
        assert "[truncated]" not in block
    finally:
        d.cleanup()


def test_oversize_file_truncated_and_marked():
    d, root = _ws_with({"f.txt": b"x" * 50})
    try:
        block, records = build_mention_context(
            "@f.txt", root, max_chars_per_file=10, max_total_chars=1000
        )
        assert records[0]["status"] == "injected"
        assert records[0]["truncated"] is True
        assert "[truncated]" in block
    finally:
        d.cleanup()


def test_second_file_omitted_when_budget_exhausted():
    # A fills the whole budget exactly; B then has remaining == 0 -> omitted.
    d, root = _ws_with({"a.txt": b"a" * 30, "b.txt": b"b" * 30})
    try:
        block, records = build_mention_context(
            "@a.txt @b.txt", root, max_chars_per_file=1000, max_total_chars=30
        )
        statuses = {r["token"]: r["status"] for r in records}
        assert statuses["a.txt"] == "injected"
        assert statuses["b.txt"] == "omitted"
        assert "超出注入预算" in block
    finally:
        d.cleanup()


def test_redact_gate_scrubs_secret_in_mcp_json():
    # .minicc/mcp.json is in the redact set: content is injected but secrets
    # (sk-* / Bearer) must be scrubbed before it reaches the model.
    # Built at runtime so no literal secret-shaped token sits in the diff
    # (the pre-commit secret scanner flags contiguous sk-* / Bearer literals).
    secret = "sk-" + "a" * 20
    content = ('{"headers": {"Authorization": "Bearer ' + secret + '"}}').encode()
    d, root = _ws_with({".minicc/mcp.json": content})
    try:
        block, records = build_mention_context("@.minicc/mcp.json", root)
        assert records[0]["status"] == "injected"
        assert secret not in block
        assert "[REDACTED" in block
    finally:
        d.cleanup()


def test_redact_gate_keeps_non_secret_content():
    d, root = _ws_with({".minicc/mcp.json": b'{"servers": {"x": {}}}'})
    try:
        block, records = build_mention_context("@.minicc/mcp.json", root)
        assert records[0]["status"] == "injected"
        assert "servers" in block
    finally:
        d.cleanup()


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__, "-q", "-W", "error"]))
