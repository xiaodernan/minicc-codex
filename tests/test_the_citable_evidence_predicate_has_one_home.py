"""M8-T557 — 可核对证据判据只有一个家。

判定「哪条执行证据能给目标背书」这个事实住在完成评估（``minicc/agent/completion.py``）：
真门用它来决定 reviewer 引用的证据是否可采信。fake provider 是测试驱动的脚本化评委，
它要产出一条真门肯收的引用，就必须问同一个家——否则它在按自己那份拷贝判案，
agent 的判据漂移就会被「假评委」悄悄吸收掉，测试永远绿。

红先行：落地前 fake.py 手抄了这条判据（``kind != "trace" and name and name != "agent"``），
本门先红（普查命中），再绿。
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/completion.py"

#: The inline spelling that marks a private copy of the judgment.
INLINE_SPELLING = 'kind != "trace"'


def _read(relative: str) -> str:
    return (REPO / relative).read_text(encoding="utf-8")


def test_the_home_answers_the_question() -> None:
    """Behavior pins: the judgment itself, case by case."""
    from minicc.agent.completion import is_citable_evidence_item

    assert is_citable_evidence_item({"write": True}) is True
    assert is_citable_evidence_item({"kind": "verification"}) is True
    assert is_citable_evidence_item({"status": "error"}) is True
    assert is_citable_evidence_item({"kind": "tool", "name": "bash"}) is True
    assert is_citable_evidence_item({"kind": "tool", "name": "agent"}) is False
    assert is_citable_evidence_item({"kind": "trace", "name": "agent"}) is False
    assert is_citable_evidence_item({"kind": "trace"}) is False
    assert is_citable_evidence_item({}) is False


def test_the_gate_and_the_fake_ask_the_one_home() -> None:
    assert "is_citable_evidence_item(item)" in _read(HOME), (
        "the completion review must ask the one home for the events bucket"
    )
    assert "is_citable_evidence_item(item)" in _read("minicc/llm/fake.py"), (
        "the fake provider must ask the one home, not a private copy"
    )


def test_no_module_spells_the_judgment_inline() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(REPO).as_posix()
        for line_number, line in enumerate(source.splitlines(), 1):
            if INLINE_SPELLING in line and relative != HOME:
                offenders.append(f"{relative}:{line_number}")
    assert not offenders, (
        "a private copy of the citable-evidence judgment lives inline outside "
        f"its one home ({HOME}): " + ", ".join(offenders)
    )
