"""M8-T286 — 一组 hook 共享一个总预算

每个 hook 有自己的超时上限（最多 60 秒），但**整组**没有上限。所以 N 个
各 60 秒的 hook 会让一次工具调用卡住 N 分钟，而且期间没有任何东西能打断
它——hook 是在事件循环里同步跑的。

现在同一个事件的全部 hook 共享一个截止时间：剩下的时间不够跑下一条时，
那条被跳过并说明原因。

This door pins:

* the whole set shares one budget;
* a hook that does not fit in what is left is skipped, and says so;
* the controls: one hook still runs normally, and the total budget is
  generous enough for the ordinary case.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from minicc.hooks import MAX_HOOK_TOTAL_SECONDS, HookRunner


def _hooks(workspace: Path, count: int, timeout: int) -> None:
    path = workspace / ".minicc" / "hooks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "hooks": {
                "PreToolUse": [
                    {
                        "command": "python -c \"import time; time.sleep(30)\"",
                        "timeout": timeout,
                    }
                    for _ in range(count)
                ]
            }
        }),
        encoding="utf-8",
    )


def test_the_whole_set_shares_one_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A set that cannot fit is cut short, and the cut is visible."""
    import minicc.hooks as hooks_module

    monkeypatch.setattr(hooks_module, "MAX_HOOK_TOTAL_SECONDS", 2.0)
    _hooks(tmp_path, count=4, timeout=30)

    runner = HookRunner(tmp_path)
    assert len(runner.specs) == 4

    started = time.monotonic()
    outcome = runner.run("PreToolUse", {"tool": "bash"})
    elapsed = time.monotonic() - started

    assert elapsed < 20, f"the hook set ran for {elapsed:.1f}s; the budget is 2s"
    assert any("预算" in str(item.get("reason") or "") for item in outcome.outputs), (
        f"the budget cut was not disclosed: {outcome.outputs}"
    )


def test_one_hook_still_runs_normally(tmp_path: Path) -> None:
    """The control: the ordinary case is untouched."""
    path = tmp_path / ".minicc" / "hooks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "hooks": {
                "PreToolUse": [{
                    "command": "python -c \"print('hi')\"",
                    "timeout": 10,
                }]
            }
        }),
        encoding="utf-8",
    )
    outcome = HookRunner(tmp_path).run("PreToolUse", {"tool": "bash"})
    assert len(outcome.outputs) == 1
    assert outcome.outputs[0].get("decision") == "allow"


def test_the_budget_is_generous_for_the_ordinary_case(tmp_path: Path) -> None:
    """A handful of quick hooks must not hit the ceiling."""
    path = tmp_path / ".minicc" / "hooks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "hooks": {
                "PreToolUse": [
                    {"command": "python -c \"print('x')\"", "timeout": 5}
                    for _ in range(3)
                ]
            }
        }),
        encoding="utf-8",
    )
    outcome = HookRunner(tmp_path).run("PreToolUse", {"tool": "bash"})
    assert len(outcome.outputs) == 3
    assert not any("预算" in str(item.get("reason") or "") for item in outcome.outputs)


def test_the_budget_is_a_shared_ceiling() -> None:
    """The constant is a ceiling, not a per-hook value."""
    assert MAX_HOOK_TOTAL_SECONDS >= 1.0
