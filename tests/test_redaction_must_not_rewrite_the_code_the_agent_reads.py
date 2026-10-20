"""M8-T292 — 脱敏规则不能改写 agent 读到的代码。

把日志侧的"带标签凭据"规则搬到模型上下文（M8-T268）时，日志侧的误伤只
影响一行日志，模型侧的误伤**改写了 agent 读到的源码**——它会照着被篡改的
代码做判断，编辑出来的文件也与磁盘上的不一致。

三条判据：

* 键要有**词边界**：``{"monkey": …}`` 里的 ``key`` 不是密钥键；
* 值要**像凭据**：``compute()`` 是代码，``abcd1234efgh5678`` 是凭据；
* 已经脱敏的值不再被二次包裹，且不谎报"改动了"。
"""

from __future__ import annotations

import pytest

from minicc.tools.registry import redact_text

ORDINARY_CODE = [
    '{"monkey": "banana"}',
    "self.token = compute()",
    "config.key = value",
    'x = {"key": "value"}',
    'result = {"status": "ok", "path": "a.py"}',
    "password = read_from_env()",
    "def token(): return secrets.token_hex(16)",
]

CREDENTIALS = [
    '{"api_key": "abcd1234efgh5678"}',
    "api_key=abcd1234efgh5678",
    '"password": "hunter2xyz"',
    "?token=8f14e45fceea167a5a36&x=1",
]


@pytest.mark.parametrize("text", ORDINARY_CODE)
def test_ordinary_code_is_not_redacted(text: str) -> None:
    """The agent must see the code as it is on disk."""
    masked, changed = redact_text(text)
    assert masked == text, f"ordinary code was rewritten: {masked!r}"
    assert changed is False, f"ordinary code was reported as redacted: {text!r}"


@pytest.mark.parametrize("text", CREDENTIALS)
def test_a_credential_is_still_redacted(text: str) -> None:
    """The control: the real leak stays closed."""
    masked, changed = redact_text(text)
    assert changed is True, f"a credential was not recognised: {text!r}"
    assert "abcd1234efgh5678" not in masked
    assert "hunter2xyz" not in masked
    assert "8f14e45fceea167a5a36" not in masked


def test_an_already_redacted_value_is_not_wrapped_again() -> None:
    """And the pass does not claim a change it did not make."""
    raw = '{"api_key": "[REDACTED:credential]"}'
    masked, changed = redact_text(raw)
    assert masked == raw
    assert changed is False, "a second pass claimed to have redacted something"
