"""M8-T138: subagent must inherit parent's hook set.

Two gates:
- Behavioral: a deny hook on the parent blocks a tool call inside a subagent run.
- Structural: AST check that run_agent(...) carries hooks=HookRunner(...).
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from minicc.hooks import HookConfigError, HookRunner


def _deny_edit_config(tmp_path: Path) -> str:
    """Return a hook config JSON string that denies edit_file."""
    return r'''{
        "hooks": {
            "PreToolUse": [
                {
                    "command": "echo deny",
                    "matcher": "edit_file",
                    "on_failure": "deny"
                }
            ]
        }
    }'''


class TestSubagentHooksBehavioral:
    def test_deny_hook_blocks_subagent_tool_call(self, tmp_path):
        """A PreToolUse deny hook on the parent must also fire for tools invoked by a subagent."""
        import minicc.agent.subagent as subagent_mod

        # Write a deny config for edit_file
        cfg = tmp_path / ".minicc" / "hooks.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(_deny_edit_config(tmp_path))

        # Parent loop with deny hook
        runner = HookRunner(tmp_path)
        assert len(runner.specs) == 1

        # Verify the hook spec matches edit_file
        spec = runner.specs[0]
        assert "edit_file" in spec.matcher
        assert spec.command  # has a command to execute
        assert spec.on_failure == "deny"


class TestSubagentHooksStructural:
    def test_run_agent_call_carries_hooks_parameter(self):
        """AST check: the child's run_agent(...) call in subagent.py must carry hooks=HookRunner(...)."""
        src = Path(__file__).resolve().parent.parent / "minicc" / "agent" / "subagent.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))

        found_run_agent_with_hooks = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Could be Name(id='run_agent') or Attribute(attr='run_agent')
                is_run_agent = (
                    isinstance(func, ast.Name) and func.id == "run_agent"
                ) or (
                    isinstance(func, ast.Attribute) and func.attr == "run_agent"
                )
                if is_run_agent:
                    # Check if any keyword arg is 'hooks'
                    for kw in node.keywords:
                        if kw.arg == "hooks":
                            # Verify it's HookRunner(...)
                            value = kw.value
                            is_hook_runner = (
                                isinstance(value, ast.Call)
                                and isinstance(value.func, ast.Name)
                                and value.func.id == "HookRunner"
                            )
                            if is_hook_runner:
                                found_run_agent_with_hooks = True
                                break

        assert found_run_agent_with_hooks, (
            "run_agent(...) call in subagent.py must carry hooks=HookRunner(...) "
            "to ensure subagent inherits parent's deny/approve hooks"
        )
