"""M7-T5: @-mention content injection (bounded, workspace-contained) and
the safety gates around it (junction escape, .minicc credentials, redaction).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.mentions import (
    MENTION_MAX_FILES,
    apply_mentions,
    build_mention_context,
    extract_mention_tokens,
)


def _make_dir_link(link: Path, target: Path) -> bool:
    """Create a directory junction (Windows) or symlink (POSIX)."""
    if os.name == "nt":
        try:
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
            return True
        except (OSError, ImportError, AttributeError):
            return False
    try:
        link.symlink_to(target, target_is_directory=True)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# token extraction
# ---------------------------------------------------------------------------


def test_extract_tokens_order_dedupe_and_email_boundary() -> None:
    tokens = extract_mention_tokens(
        "对比 @src/main.py 和 @README.md，再确认 @src/main.py；邮箱 someone@example.com 不是引用。"
    )
    assert tokens == ["src/main.py", "README.md"]


def test_extract_tokens_strips_trailing_punctuation_and_caps() -> None:
    text = " ".join(f"@f{i}.txt。" for i in range(15))
    tokens = extract_mention_tokens(text)
    assert len(tokens) == MENTION_MAX_FILES
    assert tokens[0] == "f0.txt"


# ---------------------------------------------------------------------------
# injection + budgets
# ---------------------------------------------------------------------------


def test_injects_file_head_with_path_annotation(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello from main')\n", encoding="utf-8")
    block, records = build_mention_context("看看 @src/main.py 做什么", tmp_path)
    assert 'path="src/main.py"' in block
    assert "hello from main" in block
    assert "[truncated]" not in block
    assert records[0]["status"] == "injected"
    assert records[0]["truncated"] is False


def test_oversized_file_truncates_at_line_boundary(tmp_path: Path) -> None:
    lines = [f"line-{index:04d}-{'y' * 20}" for index in range(200)]
    (tmp_path / "big.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    block, records = build_mention_context("@big.py", tmp_path, max_chars_per_file=150)
    assert "[truncated]" in block
    assert records[0]["truncated"] is True
    body = block.split(">\n", 1)[1].rsplit("\n[truncated]", 1)[0]
    assert len(body) <= 150
    assert body.endswith(lines[3])  # cut lands on a whole line


def test_total_budget_omits_extra_files(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("A" * 80 + "\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("B" * 80 + "\n", encoding="utf-8")
    block, records = build_mention_context(
        "@a.txt @b.txt", tmp_path, max_chars_per_file=60, max_total_chars=60
    )
    injected = [item for item in records if item["status"] == "injected"]
    omitted = [item for item in records if item["status"] == "omitted"]
    assert [item["path"] for item in injected] == ["a.txt"]
    assert [item["path"] for item in omitted] == ["b.txt"]
    assert "B" * 60 not in block
    assert "b.txt" in block  # the omission is still surfaced to the model


def test_apply_mentions_appends_block(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("note body\n", encoding="utf-8")
    message, records = apply_mentions("总结 @note.md", tmp_path)
    assert message.startswith("总结 @note.md")
    assert "note body" in message
    plain, plain_records = apply_mentions("没有引用的问题", tmp_path)
    assert plain == "没有引用的问题"
    assert plain_records == []


# ---------------------------------------------------------------------------
# security gates
# ---------------------------------------------------------------------------


def test_rejects_parent_escape_and_absolute_paths(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("DO-NOT-INJECT", encoding="utf-8")
    relative_escape = "../" + outside.name
    block, records = build_mention_context(
        f"@{relative_escape} @{outside.as_posix()} @~/Desktop/file", tmp_path
    )
    assert all(item["status"] == "rejected" for item in records)
    assert len(records) == 3
    assert "DO-NOT-INJECT" not in block


def test_junction_escape_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("TOPSECRET-mentions", encoding="utf-8")
    if not _make_dir_link(workspace / "link", outside):
        pytest.skip("cannot create directory junction/symlink here")
    block, records = build_mention_context("@link/secret.txt", workspace)
    assert records[0]["status"] == "rejected"
    assert "TOPSECRET-mentions" not in block


def test_minicc_credential_files_rejected(tmp_path: Path) -> None:
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "web_token.json").write_text(
        json.dumps({"token": "T" * 64}), encoding="utf-8"
    )
    block, records = build_mention_context("@.minicc/web_token.json", tmp_path)
    assert records[0]["status"] == "rejected"
    assert "T" * 64 not in block


def test_mcp_headers_are_redacted(tmp_path: Path) -> None:
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "mcp.json").write_text(
        json.dumps({"servers": {"remote": {"headers": {"Authorization": "Bearer sk-mentionssecret"}}}}),
        encoding="utf-8",
    )
    block, records = build_mention_context("@.minicc/mcp.json", tmp_path)
    assert records[0]["status"] == "injected"
    assert "sk-mentionssecret" not in block
    assert "REDACTED" in block


def test_missing_binary_are_annotated_without_content(tmp_path: Path) -> None:
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01BINARYBODY\x02")
    block, records = build_mention_context("@nope.txt @blob.bin", tmp_path)
    statuses = {item["status"] for item in records}
    assert statuses == {"missing", "binary"}
    assert "BINARYBODY" not in block
    assert block == ""  # nothing injected, nothing rejected -> no block


def test_cjk_glued_token_resolves_to_existing_prefix(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("cjk prefix body\n", encoding="utf-8")
    block, records = build_mention_context("@a.py是什么以及 @a.py。它做什么", tmp_path)
    assert records[0]["status"] == "injected"
    assert records[0]["path"] == "a.py"
    assert "cjk prefix body" in block


def test_cjk_punctuation_adjacent_mention_is_extracted(tmp_path: Path) -> None:
    # Hand-typed Chinese with a full-width period directly before @ (no space)
    # must still register, while emails stay excluded.
    (tmp_path / "big30.txt").write_text("FIRSTLINE\n", encoding="utf-8")
    assert extract_mention_tokens("不要调用任何工具。@big30.txt 的第一行") == ["big30.txt"]
    assert extract_mention_tokens("email someone@evil.com only @big30.txt") == ["big30.txt"]
    block, records = build_mention_context("不要调用任何工具。@big30.txt 的第一行", tmp_path)
    assert records[0]["status"] == "injected"
    assert "FIRSTLINE" in block


# ---------------------------------------------------------------------------
# AgentService wiring: the model's user message carries the content and the
# task emits a mentions_resolved trace event.
# ---------------------------------------------------------------------------


class _CapturingFake:
    """Wraps the scripted fake provider and records every message list."""

    instances: list["_CapturingFake"] = []

    def __init__(self, *args, **kwargs) -> None:
        from minicc.llm.fake import FakeProvider

        self._inner = FakeProvider()
        self.seen_messages: list[list] = []
        _CapturingFake.instances.append(self)

    async def chat(self, messages, tools, on_delta=None):
        self.seen_messages.append([dict(item) for item in messages])
        return await self._inner.chat(messages, tools, on_delta=on_delta)

    async def close(self) -> None:
        await self._inner.close()


def test_chat_locked_injects_mentions_and_emits_event(tmp_path: Path, monkeypatch) -> None:
    from minicc import web as web_module

    _CapturingFake.instances = []
    monkeypatch.setattr(web_module, "OpenAICompatibleProvider", _CapturingFake)
    config = SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
        fallback_models=(),
    )
    (tmp_path / "hello.txt").write_text("MENTION-INJECTED-MARKER\n", encoding="utf-8")
    service = web_module.AgentService(tmp_path, config)
    try:
        result = service._chat_locked(
            {
                "message": "这个文件说什么 @hello.txt，另外 @../outside.txt",
                "session_id": "mentions-wiring",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    assert result["error"] is None
    user_messages = [
        item
        for provider in _CapturingFake.instances
        for messages in provider.seen_messages
        for item in messages
        if item.get("role") == "user"
    ]
    assert any(
        "MENTION-INJECTED-MARKER" in str(item.get("content"))
        and 'path="hello.txt"' in str(item.get("content"))
        for item in user_messages
    )
    assert not any("outside.txt" in str(item.get("content") or "") and "REJECT" in str(item.get("content")) for item in user_messages)
    trace_codes = [event.get("code") for event in result["events"] if event.get("kind") == "trace"]
    assert "mentions_resolved" in trace_codes
    mention_event = next(
        event for event in result["events"] if event.get("code") == "mentions_resolved"
    )
    statuses = {record["path"]: record["status"] for record in mention_event["detail"]["records"]}
    assert statuses["hello.txt"] == "injected"
    assert statuses["../outside.txt"] == "rejected"
