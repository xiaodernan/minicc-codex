"""M8-T330 — hook 入参：**先脱敏再截断**，而且要**说清被截断了**

`payloads_for_tool_call` 原来写的是：

```python
redacted, _ = redact_text(text[:4000])
```

**先截断、后脱敏**。于是两件事同时坏掉：

* **跨界的密钥只剩半截** → 脱敏的模式**匹配不上**它 → **半截凭据进了 hook 的
  stdin**（hook 是用户自己的进程，泄漏面小，但与"入参被脱敏"的承诺不符）；
* **没人说这个值被截断过** → `PreToolUse` 是用户自备的**否决层**，它拿到的
  `arguments.content` 只有前 4000 字符，**第 4001 字符以后的策略违规它永远看不到**，
  却以为看到了全部。

本门禁钉住：跨界的那一半**不在**载荷里；被截断时**有标记**；普通值不变。
"""

from __future__ import annotations

from minicc.hooks import MAX_HOOK_ARG_CHARS, payloads_for_tool_call


def test_a_secret_across_the_cut_is_not_carried_half() -> None:
    """The cut must not produce a half credential.

    The secret starts just before the cut and ends after it, so cutting
    first would leave its first half in the payload.  (It is preceded by a
    space on purpose: a secret glued to word characters is deliberately
    **not** redacted - the lookbehind keeps ``task-...`` identifiers
    intact.)
    """
    payload = payloads_for_tool_call(
        "PreToolUse",
        "write_file",
        {"content": "x" * (MAX_HOOK_ARG_CHARS - 10) + " sk-abc123def456"},
    )
    value = payload["arguments"]["content"]
    assert "sk-" not in value, (
        f"half a credential reached the hook: {value[-80:]!r}"
    )


def test_a_secret_before_the_cut_is_redacted() -> None:
    """The control: the ordinary case is unchanged."""
    payload = payloads_for_tool_call(
        "PreToolUse",
        "write_file",
        {"content": 'api_key = "sk-abc123def456"'},
    )
    value = payload["arguments"]["content"]
    assert "sk-abc123def456" not in value, value


def test_a_cut_value_says_it_was_cut() -> None:
    """The hook has to know it is looking at a prefix."""
    payload = payloads_for_tool_call(
        "PreToolUse",
        "write_file",
        {"content": "y" * (MAX_HOOK_ARG_CHARS + 500)},
    )
    value = payload["arguments"]["content"]
    assert value.endswith("[truncated]"), value[-40:]
    assert len(value) <= MAX_HOOK_ARG_CHARS + len("[truncated]"), len(value)


def test_a_short_value_is_not_marked() -> None:
    """The control: nothing is said when there is nothing to say."""
    payload = payloads_for_tool_call(
        "PreToolUse", "write_file", {"content": "short"}
    )
    assert payload["arguments"]["content"] == "short", payload


def test_the_event_and_tool_still_travel() -> None:
    """The control: the payload's shape is unchanged."""
    payload = payloads_for_tool_call(
        "PreToolUse", "write_file", {"content": "x"}, risk="write"
    )
    assert payload["event"] == "PreToolUse", payload
    assert payload["tool"] == "write_file", payload
    assert payload["risk"] == "write", payload
