"""Fence tests for ``minicc.mcp.RECOGNIZED_KEYS`` derivation (M8-T258).

``RECOGNIZED_KEYS`` used to be a hand-copied literal inside ``load_mcp_config``;
it now derives from ``McpServerConfig``'s fields (minus ``name``, which is the
entry's dict key, not a per-entry field). These tests pin both the derivation
relationship and the observable warning behavior so a drifting literal - or a
new dataclass field that never reaches the warning gate - goes red.

Run directly or via the repo gate:
    python tests/test_mcp_recognized_keys_derive.py
    python -m pytest tests/test_mcp_recognized_keys_derive.py -q -W error
"""

import json
import logging
import tempfile
from dataclasses import fields
from pathlib import Path

from minicc.mcp import RECOGNIZED_KEYS, McpServerConfig, load_mcp_config

_EXPECTED = {"command", "url", "args", "env", "headers", "read_only"}


def test_recognized_keys_matches_dataclass_fields():
    # the single-source-of-truth invariant: every config field except the
    # entry key name is a recognized entry key.
    assert RECOGNIZED_KEYS == {f.name for f in fields(McpServerConfig)} - {"name"}


def test_recognized_keys_exact_set():
    # pin the exact set so removing a key from the derivation goes red.
    assert set(RECOGNIZED_KEYS) == _EXPECTED


def test_name_excluded_from_recognized():
    assert "name" not in RECOGNIZED_KEYS


def _write_mcp(root: Path, entry: dict) -> None:
    (root / ".minicc").mkdir(parents=True, exist_ok=True)
    (root / ".minicc" / "mcp.json").write_text(
        json.dumps({"servers": {"s": entry}}), encoding="utf-8"
    )


def test_unknown_key_is_warned(caplog):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write_mcp(root, {"command": "echo", "bogus_key": 1})
        with caplog.at_level(logging.WARNING):
            load_mcp_config(root)
        assert any("bogus_key" in record.getMessage() for record in caplog.records)


def test_all_recognized_keys_no_warning(caplog):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write_mcp(root, {
            "command": "echo",
            "args": ["hi"],
            "env": {},
            "headers": {},
            "read_only": False,
            "url": "",
        })
        with caplog.at_level(logging.WARNING):
            load_mcp_config(root)
        assert not any("不会被读取" in record.getMessage() for record in caplog.records)


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__, "-q", "-W", "error"]))
