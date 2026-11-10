"""M8-T765 — ``minicc/tools/fs.py`` 的守卫规则（deny 逻辑）钉住。

这个模块是"agent 看不到/不能直接动的文件"的门的集中处，零同名测试
（模块→测试映射发现）。这些是安全规则，不是风格规则：任何一次漂移
（把 `permissions.json` 从 deny 列表漏掉、`mcp.json` 的 header 不再脱敏、
`.minicc/x/../web_token.json` 绕过）就是一次真实上升权限。

钉住四件：
1. `_minicc_relative_parts` —— 归一化（collapse `..`、大小写不敏感、
   Windows 反斜杠）；
2. `_minicc_sensitive_kind` —— deny / redact / 不敏感 的判定；
3. `_redact_mcp_headers` —— BOM 容忍 + 不可解析即拒绝 + headers 全部脱敏；
4. `_is_sensitive_path` —— `.env` 族、key material、敏感裸名。
"""

from __future__ import annotations

import json

import pytest

from minicc.tools import fs
from minicc.tools.registry import ToolError


# ---------- _minicc_relative_parts ----------

@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".minicc/web_token.json", ("web_token.json",)),
        (".minicc/x/../web_token.json", ("web_token.json",)),   # M8-T266 回归
        ("a/.minicc/mcp.json", ("mcp.json",)),
        ("a/.minicc/worker/cfg.config.json", ("worker", "cfg.config.json")),
        ("a/x/cdn.config.json", ()),                            # 不在 .minicc 内
        (".MINICC/web_token.json", ("web_token.json",)),        # 大小写不敏感
    ],
)
def test_minicc_relative_parts_normalizes(path, expected):
    assert fs._minicc_relative_parts(path) == expected


def test_minicc_relative_parts_accepts_windows_separators():
    assert fs._minicc_relative_parts(".minicc\\x\\..\\web_token.json") == (
        "web_token.json",
    )


# ---------- _minicc_sensitive_kind ----------

@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".minicc/web_token.json", "deny"),
        (".minicc/permissions.json", "deny"),
        (".minicc/allowlist.json", "deny"),
        (".minicc/audit.jsonl", "deny"),
        (".minicc/hooks.json", "deny"),
        (".minicc/worker/run.config.json", "deny"),
        (".minicc/mcp.json", "redact"),
        (".minicc/notes.txt", None),
        ("other/web_token.json", None),
        (".MINICC/Web_Token.JSON", "deny"),                     # 大小写不敏感
    ],
)
def test_minicc_sensitive_kind(path, expected):
    assert fs._minicc_sensitive_kind(path) == expected


# ---------- _redact_mcp_headers ----------

def test_redact_mcp_headers_masks_every_header_value():
    payload = json.dumps(
        {
            "servers": {
                "one": {"headers": {"authorization": "Bearer sk-secret", "x-custom": "tok"}},
                "two": {"headers": {"x-api-key": "abc123"}},
                "no_headers": {"url": "http://example.com"},
            }
        }
    )
    out = json.loads(fs._redact_mcp_headers(payload))
    assert out["servers"]["one"]["headers"] == {
        "authorization": "[REDACTED]",
        "x-custom": "[REDACTED]",
    }
    assert out["servers"]["two"]["headers"] == {"x-api-key": "[REDACTED]"}
    assert out["servers"]["no_headers"] == {"url": "http://example.com"}


def test_redact_mcp_headers_tolerates_a_utf8_bom():
    payload = '\ufeff{"servers": {"s": {"headers": {"a": "b"}}}}'
    out = json.loads(fs._redact_mcp_headers(payload))
    assert out["servers"]["s"]["headers"] == {"a": "[REDACTED]"}


def test_redact_mcp_headers_refuses_unparseable_input():
    with pytest.raises(ToolError):
        fs._redact_mcp_headers("{not json at all")


# ---------- _is_sensitive_path ----------

@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".env", True),
        (".env.local", True),
        (".env.example", False),   # the one named carve-out of this surface
        ("foo/.env.production", True),
        ("id_rsa", True),
        ("id_ed25519", True),
        ("credentials.json", True),
        ("secrets.json", True),
        ("cert.pem", True),
        ("key.p12", True),
        ("store.pfx", True),
        ("vault.kdbx", True),
        ("app.py", False),
        ("notes/.envx", False),
    ],
)
def test_is_sensitive_path(path, expected):
    assert fs._is_sensitive_path(path) is expected


def test_minicc_sensitive_refusal_mentions_the_human_route():
    text = fs._minicc_sensitive_refusal("读取", ".minicc/web_token.json")
    assert ".minicc/web_token.json" in text
    # 必须给出"找人类、出 workspace"的出口，而不是只给拒绝
    assert "web_token.json" in text
