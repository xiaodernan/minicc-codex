"""M8-T488 — 模型流重试判词两个家：真 provider 与冒充它的 fake 各拼一句

``模型流中断，正在进行第 N 次重试`` 是 provider 流式重试时写进 trace 的
判词。它有两个家：真 provider（``openai_provider`` 的流重试循环）与假
provider（``fake`` 的故障注入）。fake 的存在意义就是**冒充生产轨迹**——
它自己的注释写着「a log or event assertion written here describes the
production trace」。同一个句子两边各拼一遍，真 provider 改了措辞而 fake
没跟上，所有针对 fake 的断言就在描述一条生产上再也写不出来的轨迹，而且
全绿。

家安在 ``minicc/llm/base.py``，紧挨 ``retry_detail``——同一条 trace 事件
的另一半（detail 两个键）早就立了家，summary 这句却一直在外面漂。

``模型请求暂时失败，正在进行第 N 次尝试``（流之前的请求重试）是另一个时
刻的另一件事，按前缀家族判别式留在原地。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/llm/base.py"
REAL = "minicc/llm/openai_provider.py"
FAKE = "minicc/llm/fake.py"
PREFIX = "模型流中断，正在进行第"
PRE_STREAM = "模型请求暂时失败"


def _literal_strings():
    """Every string literal's text - f-string parts joined, so a
    hand-written ``f"模型流中断，正在进行第 {n} 次重试"`` is seen too."""
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


def test_the_home_pins_the_sentence() -> None:
    from minicc.llm.base import stream_retry_summary

    assert stream_retry_summary(1) == "模型流中断，正在进行第 1 次重试"
    assert stream_retry_summary(3) == "模型流中断，正在进行第 3 次重试"


def test_the_sentence_is_spelled_exactly_once_in_the_package() -> None:
    offenders = [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_strings()
        if text.startswith(PREFIX)
    ]
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the stream-retry summary is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_both_faces_ask_the_home() -> None:
    real = (REPO / REAL).read_text(encoding="utf-8")
    fake = (REPO / FAKE).read_text(encoding="utf-8")
    assert real.count("stream_retry_summary(attempt + 1)") == 1, (
        "the real stream retry must ask the home for the summary"
    )
    assert fake.count("stream_retry_summary(attempt + 1)") == 1, (
        "the fake's imitation must ask the home for the summary"
    )


def test_both_faces_share_one_object() -> None:
    from minicc.llm import base, fake, openai_provider

    assert openai_provider.stream_retry_summary is base.stream_retry_summary
    assert fake.stream_retry_summary is base.stream_retry_summary


def test_the_fake_emits_the_production_sentence(monkeypatch) -> None:
    """The whole point of the fake: its trace *is* the production trace."""
    import asyncio

    from minicc.llm.base import stream_retry_summary
    from minicc.llm.fake import FakeProvider

    monkeypatch.setenv("MINICC_FAKE_PROVIDER_FAULTS", "2")
    seen: list[dict] = []
    provider = FakeProvider(on_status=seen.append)
    asyncio.run(
        provider.chat([{"role": "user", "content": "hi"}], tools=[{"name": "tree"}])
    )
    summaries = [
        event.get("summary") for event in seen if event.get("code") == "provider_retry"
    ]
    assert summaries == [stream_retry_summary(1), stream_retry_summary(2)]


def test_the_pre_stream_retry_is_a_different_fact() -> None:
    """A different moment keeps its own wording, in exactly one place."""
    offenders = [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_strings()
        if text.startswith(PRE_STREAM)
    ]
    assert len(offenders) == 1 and offenders[0].startswith(REAL + ":"), (
        "the pre-stream retry sentence is one fact with one site: "
        + ", ".join(offenders)
    )
