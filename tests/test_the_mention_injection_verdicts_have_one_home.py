"""M8-T499 — mention 注入拒绝判词四个家：两个检查点各拼两句

「.minicc 认证/授权文件不允许注入」和「permissions.json deny 规则不允许注
入」在 `mentions.py` 里各有**两个**家：原始 token 检查点（M2-T2/M8-T317）
和 CJK 收敛后路径检查点（M8-T65/M8-T290）。两处逐字相同。一条 mention 被
拒，用户读到哪句措词取决于 token 是手打的原样还是带了 CJK 粘连尾巴——一
处改了措词其余三处没跟上，没有任何测试会红。

家安在 `minicc/mentions.py` 模块层，紧挨 `_reject`——四个调用点都在这个
模块，家只服务这个模块。两条判词是两个事实（凭据门 vs deny 规则门），各
自一个家函数。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/mentions.py"
CREDENTIAL = ".minicc 认证/授权文件不允许注入"
DENY_RULE = "permissions.json deny 规则不允许注入"


def _literal_shapes():
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        inside_fstring: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for child in ast.iter_child_nodes(node):
                    inside_fstring.add(id(child))
        for node in ast.walk(tree):
            if id(node) in inside_fstring:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield path, node.lineno, node.value
            elif isinstance(node, ast.JoinedStr):
                parts = [
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                ]
                yield path, node.lineno, "".join(parts)


def _sites_of(sentence: str) -> list[str]:
    return [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_shapes()
        if text == sentence
    ]


def _reasons(message: str, workspace: Path) -> list[str]:
    from minicc.mentions import build_mention_context

    _block, records = build_mention_context(message, workspace)
    return [record["reason"] for record in records]


def test_the_credential_home_pins_the_sentence() -> None:
    from minicc.mentions import credential_injection_refusal

    assert credential_injection_refusal() == CREDENTIAL


def test_the_deny_rule_home_pins_the_sentence() -> None:
    from minicc.mentions import deny_rule_injection_refusal

    assert deny_rule_injection_refusal() == DENY_RULE


def test_the_credential_sentence_is_spelled_exactly_once() -> None:
    offenders = _sites_of(CREDENTIAL)
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the credential injection refusal is spelled by hand outside its "
        "one home: " + ", ".join(offenders)
    )


def test_the_deny_rule_sentence_is_spelled_exactly_once() -> None:
    offenders = _sites_of(DENY_RULE)
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the deny-rule injection refusal is spelled by hand outside its "
        "one home: " + ", ".join(offenders)
    )


def test_all_four_sites_ask_the_homes() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    for name in ("credential_injection_refusal(", "deny_rule_injection_refusal("):
        assert source.count(name) == 3, (
            f"mentions.py asks {name} {source.count(name)} times, expected 3 "
            "(one definition plus two checkpoints)"
        )


# --- one behavioural assertion per checkpoint x verdict ----------------------


def test_the_raw_token_credential_gate_emits_the_homes_sentence(
    tmp_path: Path,
) -> None:
    (tmp_path / ".minicc").mkdir()
    assert _reasons("@.minicc/web_token.json", tmp_path) == [CREDENTIAL]


def test_the_converged_credential_gate_emits_the_homes_sentence(
    tmp_path: Path,
) -> None:
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "web_token.json").write_text("{}", encoding="utf-8")
    assert _reasons("@.minicc/web_token.json是什么", tmp_path) == [CREDENTIAL]


def test_the_raw_token_deny_gate_emits_the_homes_sentence(tmp_path: Path) -> None:
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": ["secret.txt"]}}), encoding="utf-8"
    )
    (tmp_path / "secret.txt").write_text("s", encoding="utf-8")
    assert _reasons("@secret.txt", tmp_path) == [DENY_RULE]


def test_the_converged_deny_gate_emits_the_homes_sentence(tmp_path: Path) -> None:
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": ["secret.txt"]}}), encoding="utf-8"
    )
    (tmp_path / "secret.txt").write_text("s", encoding="utf-8")
    assert _reasons("@secret.txt是什么", tmp_path) == [DENY_RULE]
