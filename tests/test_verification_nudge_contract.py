"""M8-T56: a nudge that demands verification has to name verification.

Two v2 tasks (`v2-version-exact`, `v2-fix-uppercase`) came back `passed=true`
from the objective oracle and still died on the completion guard. The guard was
working as designed - it saw no fresh evidence - but the loop only told the
model "run a test or verification", which names nothing: in a fixture workspace
with no test suite the model cannot produce a command the gate counts, and it
has no way to learn which commands do count.

Everything here is read back from a real `run_agent` run, not from the source
that builds the prompts: a test that quotes the constant it is checking proves
only that the constant is still there.
"""

from __future__ import annotations

import asyncio
import json
import re
from copy import deepcopy
from pathlib import Path

from minicc.agent.loop import run_agent
from minicc.agent.tool_policy import is_verification_evidence
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor


# Placeholders the prompt uses so the model fills in its own changed file.
PLACEHOLDERS = {"<改动的.py文件>": "app.py", "<改动的.js文件>": "app.js"}

# The rule the gate enforces, in the words a model has to act on.
EVIDENCE_RULE = "直接执行脚本"
NO_CHECKER_FALLBACK = "没有任何可运行的检查"


def _tool_call(name: str, arguments: dict) -> dict:
    return {
        "id": f"call-{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


class RecordingProvider:
    """Scripted responses that keep every message list the loop actually sent."""

    def __init__(self, script: list[LLMResponse]) -> None:
        self.script = script
        self.calls = 0
        self.requests: list[list[dict]] = []

    async def chat(self, messages, tools, on_delta=None):
        self.requests.append(deepcopy(messages))
        index = min(self.calls, len(self.script) - 1)
        self.calls += 1
        response = self.script[index]
        if on_delta is not None and response.content:
            on_delta(response.content)
        return response

    async def close(self) -> None:
        return None


def _nudge_messages(provider: RecordingProvider) -> list[str]:
    """User messages the loop injected on top of the original prompt."""
    assert provider.requests, "the provider was never called"
    injected: list[str] = []
    for request in provider.requests:
        for message in request:
            content = str(message.get("content") or "")
            if message.get("role") == "user" and content.startswith("[执行器提示]"):
                injected.append(content)
    return injected


def _named_examples(nudge: str) -> list[str]:
    """The parenthesised example list, e.g. （例如 python -m pytest、…）."""
    match = re.search(r"（(?:例如 |(?:必须是 |之一))?(.*?)）", nudge)
    assert match, f"nudge lists no examples: {nudge}"
    return [part.strip() for part in match.group(1).split("、") if part.strip()]


def _drive_write_then_finish(tmp_path: Path) -> tuple[RecordingProvider, object]:
    provider = RecordingProvider([
        LLMResponse(tool_calls=[
            _tool_call("write_file", {"path": "changed.txt", "content": "changed\n"})
        ]),
        LLMResponse(content="已完成修改。"),
        LLMResponse(content="仍然结束。"),
        LLMResponse(content="仍然结束。"),
    ])
    result = asyncio.run(
        run_agent(
            provider,
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "修改 changed.txt"}],
            should_allow=lambda _name, _call: True,
            max_turns=6,
        )
    )
    return provider, result


def test_post_write_nudge_names_commands_the_gate_accepts(tmp_path: Path) -> None:
    provider, result = _drive_write_then_finish(tmp_path)
    nudges = _nudge_messages(provider)
    assert nudges, "the loop injected no nudge after the write"
    post_write = next(n for n in nudges if "本轮已经修改工作区" in n)

    examples = _named_examples(post_write)
    assert len(examples) >= 3, examples
    for example in examples:
        command = example
        for placeholder, name in PLACEHOLDERS.items():
            command = command.replace(placeholder, name)
        assert "<" not in command, f"unresolved placeholder in {command}"
        assert is_verification_evidence(
            "bash", {"command": command}, "ok"
        ), f"the nudge names a command the gate rejects: {command}"

    # Naming checkers is the point; so is saying what does *not* count.
    assert EVIDENCE_RULE in post_write
    # And the run must still end on the guard, not on a silently accepted write.
    assert result.error == "Agent 在修改工作区后没有完成验证"


def test_pre_finish_nudge_names_the_fallback_for_a_workspace_without_checks(
    tmp_path: Path,
) -> None:
    provider, _result = _drive_write_then_finish(tmp_path)
    nudges = _nudge_messages(provider)
    pre_finish = next((n for n in nudges if "还没有收到修改后的验证证据" in n), None)
    assert pre_finish is not None, f"no pre-finish nudge in {nudges}"

    # This is the line that decides whether a workspace with no test suite can
    # ever satisfy the gate (the failure mode both graded-right tasks hit).
    assert NO_CHECKER_FALLBACK in pre_finish
    assert EVIDENCE_RULE in pre_finish

    for example in _named_examples(pre_finish):
        command = example
        for placeholder, name in PLACEHOLDERS.items():
            command = command.replace(placeholder, name)
        assert "<" not in command, f"unresolved placeholder in {command}"
        assert is_verification_evidence(
            "bash", {"command": command}, "ok"
        ), f"the nudge names a command the gate rejects: {command}"


def test_the_named_fallback_itself_clears_the_gate() -> None:
    """The escape hatch must not be advice the gate ignores."""
    assert is_verification_evidence(
        "bash", {"command": "python -m compileall changed.py"}, "ok"
    )
    assert not is_verification_evidence(
        "bash", {"command": "python changed.py"}, "ok"
    )
