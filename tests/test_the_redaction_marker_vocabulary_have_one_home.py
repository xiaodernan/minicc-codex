"""M8-T486 — 脱敏标记词汇表两个家：日志面与模型面各写一份

脱敏标记是安全词汇表，它的读者跨模块：日志过滤器、模型上下文、任务存
储的 id 修复，全都认这几个字符串。重构前它有三个家：

- `[REDACTED:credential]` 在 `logging_setup.REDACTED` 与
  `tools/registry.LABELLED_REDACTED` **各声明一份**——日志面与模型面各写
  各的替换文本；
- 「这个值是不是已经脱敏了」的前缀判断，在两个文件里各手拼一次
  （`startswith("[REDACTED")`）；
- `task_store` 为了修复被旧脱敏规则打残的 task_id，把
  `[REDACTED:llm_api_key]` 这个标记按字面量又抄了一遍。

标记在两个面上拼得不一样，就是同一个秘密在一张脸上被遮、在另一张脸上只
是被换了件衣服；前缀判断漏了一处，就是二次脱敏把标记越裹越长（M8-T290
修过的那条）。家安在 `minicc/tools/registry.py`——脱敏规则本来的家，
logging_setup 本来就 import 它。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/tools/registry.py"
CREDENTIAL = "[REDACTED:credential]"
LLM_API_KEY = "[REDACTED:llm_api_key]"
PREFIX = "[REDACTED"


def test_the_home_owns_the_marker_vocabulary() -> None:
    from minicc.tools.registry import (
        LABELLED_REDACTED,
        REDACTED_LLM_API_KEY,
        REDACTED_PREFIX,
        is_redacted,
    )

    assert REDACTED_PREFIX == PREFIX
    assert LABELLED_REDACTED == CREDENTIAL
    assert REDACTED_LLM_API_KEY == LLM_API_KEY
    assert is_redacted(CREDENTIAL) is True
    assert is_redacted("[REDACTED]") is True
    assert is_redacted("[REDACTED:github_token]") is True
    assert is_redacted("plain text") is False
    assert is_redacted("") is False


def test_no_other_module_spells_a_marker_inline() -> None:
    """Census: each marker literal appears once, in the home."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in (PREFIX, CREDENTIAL, LLM_API_KEY):
                offenders.append(f"{relative}:{node.lineno} {node.value!r}")
    assert len(offenders) == 3 and all(item.startswith(HOME) for item in offenders), (
        "a redaction marker is spelled inline outside its one home: "
        + ", ".join(offenders)
    )


def test_both_faces_share_one_marker_object() -> None:
    """The log filter and the model context replace with the same object."""
    from minicc import logging_setup
    from minicc.tools import registry

    assert logging_setup.REDACTED is registry.LABELLED_REDACTED
    assert logging_setup.is_redacted is registry.is_redacted
    assert logging_setup.REDACTED_PREFIX is registry.REDACTED_PREFIX


def test_task_store_repairs_with_the_homes_marker() -> None:
    from minicc import task_store
    from minicc.tools import registry

    assert task_store.REDACTED_LLM_API_KEY is registry.REDACTED_LLM_API_KEY


def test_the_log_face_masks_a_secret_with_the_shared_marker() -> None:
    from minicc.logging_setup import redact
    from minicc.tools.registry import REDACTED_LLM_API_KEY

    once = redact("the key is sk-abcdef1234567890, use it")
    assert "sk-abcdef1234567890" not in once
    assert REDACTED_LLM_API_KEY in once


def test_masking_twice_does_not_grow_the_line() -> None:
    """The M8-T290 property both prefix guards exist for."""
    from minicc.logging_setup import redact
    from minicc.tools.registry import redact_text

    for face in (redact, lambda text: redact_text(text)[0]):
        once = face("api_key = sk-abcdef1234567890")
        twice = face(once)
        assert twice == once, (once, twice)
        assert "[REDACTED[REDACTED" not in twice


def test_the_two_faces_agree_on_the_marker_for_the_same_secret() -> None:
    """One secret, one marker, on both faces."""
    from minicc.logging_setup import redact
    from minicc.tools.registry import REDACTED_LLM_API_KEY, redact_text

    secret = "sk-abcdef1234567890"
    assert REDACTED_LLM_API_KEY in redact(secret)
    assert REDACTED_LLM_API_KEY in redact_text(secret)[0]
