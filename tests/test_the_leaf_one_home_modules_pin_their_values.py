"""M8-T756 — 四个"一事一源"叶子模块的取值钉住。

这四个模块各自回答一个"只有一处"的事实，但值本身从没有被测试钉住：
任何一方静默改动（比如谁把 ``KEY_MATERIAL_SUFFIXES`` 又扩了 ``.kdbx``、
谁把 ``QUOTE_CHARS`` 写成 list 而不再是 frozenset、谁把 ``ENV_FAMILY_PREFIX``
顺手改成 ``.env*``），读侧都不会报错，只会让"deny-list 防不住"这类"不像
fail 的 fail"悄悄发生。值就是门，钉住它们。

四个模块：
- ``minicc/secret_suffixes.py`` —— 按后缀判定密钥材料；
- ``minicc/internal_paths.py`` —— ``.minicc/`` 内部文件名的唯一拼写；
- ``minicc/env_files.py`` —— ``is_env_filename`` 的族形状；
- ``minicc/shell_lexing.py`` —— 引号字符集。
"""

from __future__ import annotations

import pytest

from minicc import env_files, internal_paths, secret_suffixes, shell_lexing


# ---------- secret_suffixes ----------

def test_key_material_suffixes_is_the_one_tuple():
    assert secret_suffixes.KEY_MATERIAL_SUFFIXES == (
        ".pem", ".key", ".p12", ".pfx", ".kdbx",
    )
    assert isinstance(secret_suffixes.KEY_MATERIAL_SUFFIXES, tuple)
    assert ".kdbx" in secret_suffixes.KEY_MATERIAL_SUFFIXES


@pytest.mark.parametrize("name", ["id.pem", "tls.key", "cert.p12", "store.pfx", "vault.kdbx"])
def test_key_material_suffixes_match_by_endswith(name):
    assert name.endswith(secret_suffixes.KEY_MATERIAL_SUFFIXES)


# ---------- internal_paths ----------

def test_internal_paths_are_the_one_spelling():
    assert internal_paths.ALLOWLIST_NAME == "allowlist.json"
    assert internal_paths.AUDIT_NAME == "audit.jsonl"
    assert internal_paths.HOOKS_FILENAME == "hooks.json"
    assert internal_paths.PERMISSIONS_NAME == "permissions.json"
    assert internal_paths.TOKEN_FILE_NAME == "web_token.json"
    assert internal_paths.MCP_CONFIG_NAME == "mcp.json"


def test_internal_paths_all_bare_names_not_paths():
    # 拼写是文件名而不是路径——deny-list 依赖这一条断言才能防住 ../ 逃逸
    for name in (
        internal_paths.ALLOWLIST_NAME,
        internal_paths.AUDIT_NAME,
        internal_paths.HOOKS_FILENAME,
        internal_paths.PERMISSIONS_NAME,
        internal_paths.TOKEN_FILE_NAME,
        internal_paths.MCP_CONFIG_NAME,
    ):
        assert "/" not in name and "\\" not in name and ".." not in name


# ---------- env_files ----------

@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (".env", True),
        (".env.local", True),
        (".env.production", True),
        (".env.example", True),  # 族形状含 .env.example；是否可读是策略，另一层决定
        ("env", False),
        (".envrc", False),       # 不以 ".env." 开头
        ("foo.env", False),
        (".ENV", False),         # 大小写敏感——本测试钉住现有行为
        (".env ", False),        # 尾空格不以 ".env." 开头——实现正确地不认（钉住现有行为）
    ],
)
def test_is_env_filename_truth_table(name, expected):
    assert env_files.is_env_filename(name) is expected


def test_env_family_constants_are_the_one_spelling():
    assert env_files.ENV_FILENAME == ".env"
    assert env_files.ENV_FAMILY_PREFIX == ".env."


# ---------- shell_lexing ----------

def test_quote_chars_are_the_one_frozen_set():
    assert shell_lexing.QUOTE_CHARS == frozenset({'"', "'"})
    assert isinstance(shell_lexing.QUOTE_CHARS, frozenset)
