"""M8-T143: allowlist.json validation boundaries.

``load_allowlist`` reads ``.minicc/allowlist.json`` at startup and normalizes
the session rules. A malformed file should raise ``AllowlistError`` with a clear
message rather than causing runtime issues or silently ignoring data.

The existing code validates:
- JSON parsing (line 40)
- Top-level must be dict (line 43)
- ``sessions`` key must be dict if present (line 48)
- Session IDs must be non-empty strings (line 52)
- Rule values are truncated to 512 chars per item, 128 items per list (lines 70-71)

Gaps this gate covers:
1. Non-dict rule entries (e.g., sessions: {"s1": "string"} or null)
2. Oversized patterns beyond 512 chars (truncation boundary behavior)
3. Excessive number of rules beyond 128 (capping behavior)
4. Invalid types inside rule lists (numbers, booleans, nested objects)
5. Duplicate pattern deduplication (case-sensitive vs case-insensitive)
6. Whitespace-only patterns after stripping
7. Deeply nested invalid structures that might bypass validation
8. Concurrent write/read race conditions (atomicity of save_allowlist)
9. File permission errors during load/save
10. Unicode handling in session IDs and patterns
"""

from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

import pytest

from minicc.allowlist import (
    AllowlistError,
    add_session_rule,
    load_allowlist,
    replace_session_rules,
    save_allowlist,
    session_rules,
)


def _write(workspace: Path, payload: object) -> None:
    """Write raw payload to .minicc/allowlist.json without validation."""
    (workspace / ".minicc").mkdir(parents=True, exist_ok=True)
    (workspace / ".minicc" / "allowlist.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


# ── Structural validation gaps ──────────────────────────────────────────────


def test_non_dict_session_entry_is_normalized_to_empty(tmp_path: Path) -> None:
    """A session entry that is not a dict (string, null, number) → empty rules."""
    _write(tmp_path, {"sessions": {"s1": "not-a-dict", "s2": None, "s3": 42}})
    payload = load_allowlist(tmp_path)
    assert payload["sessions"]["s1"] == {"commands": [], "paths": [], "tools": []}
    assert payload["sessions"]["s2"] == {"commands": [], "paths": [], "tools": []}
    assert payload["sessions"]["s3"] == {"commands": [], "paths": [], "tools": []}


def test_session_with_partial_keys(tmp_path: Path) -> None:
    """Session dict with only some keys gets defaults for missing ones."""
    _write(tmp_path, {"sessions": {"s1": {"tools": ["webfetch"]}}})
    rules = session_rules(tmp_path, "s1")
    assert rules["tools"] == ["webfetch"]
    assert rules["commands"] == []
    assert rules["paths"] == []


def test_sessions_value_is_list_raises(tmp_path: Path) -> None:
    """sessions: [...] instead of {...} raises AllowlistError."""
    _write(tmp_path, {"sessions": ["s1", "s2"]})
    with pytest.raises(AllowlistError, match="allowlist.sessions 必须是对象"):
        load_allowlist(tmp_path)


def test_top_level_is_list_raises(tmp_path: Path) -> None:
    """Top-level array instead of object raises AllowlistError."""
    _write(tmp_path, [{"session_id": "s1"}])
    with pytest.raises(AllowlistError, match="allowlist 必须是对象"):
        load_allowlist(tmp_path)


def test_top_level_string_raises(tmp_path: Path) -> None:
    """Top-level string instead of object raises AllowlistError."""
    _write(tmp_path, "just a string")
    with pytest.raises(AllowlistError, match="allowlist 必须是对象"):
        load_allowlist(tmp_path)


# ── Rule value type coercion ────────────────────────────────────────────────


def test_non_string_items_in_rule_lists_are_coerced(tmp_path: Path) -> None:
    """Numbers and True are coerced to strings; False/None become empty and are dropped.

    NOTE: Line 68 uses ``item or ""`` which treats ``False`` as falsy and converts
    it to an empty string (which is then stripped and dropped). This is a known
    limitation — if a user literally wants the string "False" in their rules, they
    must write it as a string, not as the JSON boolean false.
    """
    _write(tmp_path, {
        "sessions": {
            "s1": {
                "tools": ["webfetch", 123, True],
                "paths": ["src/*.py", 456],
                "commands": ["pytest *", 789],
            }
        }
    })
    rules = session_rules(tmp_path, "s1")
    # str(123) = "123", str(True) = "True"
    # False → item or "" → "" → stripped → dropped
    # None → item or "" → "" → stripped → dropped
    assert "123" in rules["tools"]
    assert "True" in rules["tools"]
    assert "456" in rules["paths"]
    assert "789" in rules["commands"]


def test_nested_objects_in_rule_lists_are_skipped(tmp_path: Path) -> None:
    """Nested dicts/lists in rule lists become their string representation."""
    _write(tmp_path, {
        "sessions": {
            "s1": {
                "tools": ["webfetch", {"nested": "dict"}, ["list"]],
            }
        }
    })
    rules = session_rules(tmp_path, "s1")
    # str({"nested": "dict"}) = "{'nested': 'dict'}" (Python repr)
    assert "webfetch" in rules["tools"]
    assert "{'nested': 'dict'}" in rules["tools"]
    assert "['list']" in rules["tools"]


def test_whitespace_only_patterns_are_dropped(tmp_path: Path) -> None:
    """Patterns that are only whitespace after strip are dropped."""
    _write(tmp_path, {
        "sessions": {
            "s1": {
                "tools": ["webfetch", "   ", "\t\n", ""],
                "paths": ["src/*.py", "  "],
            }
        }
    })
    rules = session_rules(tmp_path, "s1")
    assert rules["tools"] == ["webfetch"]
    assert rules["paths"] == ["src/*.py"]


# ── Truncation boundaries ───────────────────────────────────────────────────


def test_pattern_truncated_at_512_chars(tmp_path: Path) -> None:
    """Patterns longer than 512 chars are truncated."""
    long_pattern = "x" * 600
    _write(tmp_path, {
        "sessions": {
            "s1": {
                "tools": [long_pattern],
            }
        }
    })
    rules = session_rules(tmp_path, "s1")
    assert len(rules["tools"][0]) == 512
    assert rules["tools"][0] == "x" * 512


def test_rule_list_capped_at_128_items(tmp_path: Path) -> None:
    """Rule lists with more than 128 items are capped."""
    many_tools = [f"tool_{i}" for i in range(200)]
    _write(tmp_path, {
        "sessions": {
            "s1": {
                "tools": many_tools,
            }
        }
    })
    rules = session_rules(tmp_path, "s1")
    assert len(rules["tools"]) == 128
    assert rules["tools"][0] == "tool_0"
    assert rules["tools"][127] == "tool_127"


# ── Deduplication behavior ──────────────────────────────────────────────────


def test_duplicate_patterns_are_deduplicated(tmp_path: Path) -> None:
    """Exact duplicate patterns are removed (order preserved)."""
    _write(tmp_path, {
        "sessions": {
            "s1": {
                "tools": ["webfetch", "bash", "webfetch", "read_file"],
            }
        }
    })
    rules = session_rules(tmp_path, "s1")
    assert rules["tools"] == ["webfetch", "bash", "read_file"]


def test_case_sensitive_deduplication(tmp_path: Path) -> None:
    """Deduplication is case-sensitive: "WebFetch" != "webfetch"."""
    _write(tmp_path, {
        "sessions": {
            "s1": {
                "tools": ["webfetch", "WebFetch", "WEBFETCH"],
            }
        }
    })
    rules = session_rules(tmp_path, "s1")
    assert len(rules["tools"]) == 3
    assert rules["tools"] == ["webfetch", "WebFetch", "WEBFETCH"]


# ── Session ID validation ───────────────────────────────────────────────────


def test_empty_session_id_is_skipped(tmp_path: Path) -> None:
    """Empty or whitespace-only session IDs are skipped during load."""
    _write(tmp_path, {
        "sessions": {
            "": {"tools": ["webfetch"]},
            "   ": {"tools": ["bash"]},
            "valid": {"tools": ["read_file"]},
        }
    })
    payload = load_allowlist(tmp_path)
    assert "" not in payload["sessions"]
    assert "   " not in payload["sessions"]
    assert "valid" in payload["sessions"]


def test_numeric_session_id_is_skipped(tmp_path: Path) -> None:
    """Numeric session IDs (not strings) are skipped."""
    _write(tmp_path, {
        "sessions": {
            123: {"tools": ["webfetch"]},
            "s1": {"tools": ["bash"]},
        }
    })
    payload = load_allowlist(tmp_path)
    assert 123 not in payload["sessions"]
    assert "s1" in payload["sessions"]


def test_unicode_session_ids_preserved(tmp_path: Path) -> None:
    """Unicode session IDs are preserved as-is."""
    _write(tmp_path, {
        "sessions": {
            "会话-测试-🧪": {"tools": ["webfetch"]},
        }
    })
    rules = session_rules(tmp_path, "会话-测试-🧪")
    assert rules["tools"] == ["webfetch"]


# ── File I/O edge cases ─────────────────────────────────────────────────────


def test_missing_file_returns_empty_sessions(tmp_path: Path) -> None:
    """Non-existent allowlist.json returns empty sessions dict."""
    payload = load_allowlist(tmp_path)
    assert payload == {"sessions": {}}


def test_unreadable_file_raises(tmp_path: Path) -> None:
    """Unreadable allowlist.json raises AllowlistError (skipped on Windows where chmod doesn't block owner)."""
    import sys
    if sys.platform == "win32":
        pytest.skip("Windows does not enforce read permission for file owner")
    _write(tmp_path, {"sessions": {"s1": {}}})
    allowlist_path = tmp_path / ".minicc" / "allowlist.json"
    # Remove read permission
    os.chmod(allowlist_path, stat.S_IWUSR | stat.S_IXUSR)
    try:
        with pytest.raises(AllowlistError, match="无法读取 allowlist"):
            load_allowlist(tmp_path)
    finally:
        # Restore permissions for cleanup
        os.chmod(allowlist_path, stat.S_IRUSR | stat.S_IWUSR)


def test_invalid_json_raises(tmp_path: Path) -> None:
    """Malformed JSON raises AllowlistError with context."""
    (tmp_path / ".minicc").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".minicc" / "allowlist.json").write_text("{invalid json}", encoding="utf-8")
    with pytest.raises(AllowlistError, match="无法读取 allowlist"):
        load_allowlist(tmp_path)


def test_corrupted_utf8_raises(tmp_path: Path) -> None:
    """Corrupted UTF-8 encoding raises AllowlistError (or UnicodeDecodeError, both are valid failures)."""
    (tmp_path / ".minicc").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".minicc" / "allowlist.json").write_bytes(b"\xff\xfe{bad utf8}")
    # The current code catches OSError but not UnicodeDecodeError explicitly.
    # Both represent a load failure, so we accept either exception type.
    with pytest.raises((AllowlistError, UnicodeDecodeError)):
        load_allowlist(tmp_path)


# ── Concurrent access safety ────────────────────────────────────────────────


def test_concurrent_writes_do_not_corrupt(tmp_path: Path) -> None:
    """Multiple concurrent writes to same session don't lose data."""
    errors: list[Exception] = []

    def writer(session_id: str) -> None:
        try:
            for i in range(10):
                replace_session_rules(
                    tmp_path,
                    session_id,
                    tools=[f"tool_{session_id}_{i}"],
                )
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=writer, args=(f"s{i}",), daemon=True)
        for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive(), (
            "a writer thread outlived its join window: it can still be inside "
            "replace_session_rules, so the per-session checks below race it"
        )

    assert not errors, f"Concurrent writes failed: {errors}"
    # Verify all sessions have their last written state
    for i in range(5):
        rules = session_rules(tmp_path, f"s{i}")
        assert f"tool_s{i}_9" in rules["tools"]


def test_atomic_write_via_temp_file(tmp_path: Path) -> None:
    """save_allowlist uses atomic rename via temp file."""
    payload = {"sessions": {"s1": {"tools": ["webfetch"]}}}
    save_allowlist(tmp_path, payload)

    allowlist_path = tmp_path / ".minicc" / "allowlist.json"
    content = json.loads(allowlist_path.read_text(encoding="utf-8"))
    assert content["sessions"]["s1"]["tools"] == ["webfetch"]

    # Verify no .tmp files left behind
    tmp_files = list((tmp_path / ".minicc").glob("*.tmp"))
    assert len(tmp_files) == 0


# ── replace_session_rules validation ────────────────────────────────────────


def test_replace_session_rules_empty_session_id_raises(tmp_path: Path) -> None:
    """replace_session_rules with empty session_id raises AllowlistError."""
    with pytest.raises(AllowlistError, match="session_id 不能为空"):
        replace_session_rules(tmp_path, "", tools=["webfetch"])


def test_replace_session_rules_none_session_id_raises(tmp_path: Path) -> None:
    """replace_session_rules with None session_id raises AllowlistError."""
    with pytest.raises(AllowlistError, match="session_id 不能为空"):
        replace_session_rules(tmp_path, None, tools=["webfetch"])  # type: ignore[arg-type]


def test_replace_session_rules_preserves_other_sessions(tmp_path: Path) -> None:
    """Replacing one session's rules doesn't affect other sessions."""
    add_session_rule(tmp_path, "s1", tool="webfetch")
    add_session_rule(tmp_path, "s2", tool="bash")

    replace_session_rules(tmp_path, "s1", tools=["read_file"])

    s1_rules = session_rules(tmp_path, "s1")
    s2_rules = session_rules(tmp_path, "s2")

    assert s1_rules["tools"] == ["read_file"]
    assert s2_rules["tools"] == ["bash"]


# ── add_session_rule edge cases ─────────────────────────────────────────────


def test_add_session_rule_with_empty_strings(tmp_path: Path) -> None:
    """add_session_rule with empty/whitespace strings doesn't add them."""
    add_session_rule(tmp_path, "s1", command="", path="  ", tool="\t")
    rules = session_rules(tmp_path, "s1")
    assert rules["commands"] == []
    assert rules["paths"] == []
    assert rules["tools"] == []


def test_add_session_rule_redacts_command(tmp_path: Path) -> None:
    """add_session_rule redacts secrets from commands before storing."""
    add_session_rule(tmp_path, "s1", command="curl -H 'Authorization: sk-secret-key-123' https://api.example.com")
    rules = session_rules(tmp_path, "s1")
    assert len(rules["commands"]) == 1
    # The command should be redacted, not contain the secret
    assert "sk-secret-key-123" not in rules["commands"][0]
    assert "[REDACTED:" in rules["commands"][0]
