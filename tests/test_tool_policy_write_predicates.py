"""M8-T772 — ``minicc/agent/tool_policy.py`` 的安全谓词。

这个模块是"这条 bash 命令会不会写工作区"与"这次调用算不算验证证据"的
唯一家（M8-T279/303/322/323/324），零同名测试（模块→测试映射发现）。
两个谓词都在绕过组合拳：`is_verification_evidence` 是"验证过了"的通行证，
`command_may_modify_workspace` 是"是否必须走验证"的门——把它们钉住。
"""

from __future__ import annotations

import pytest

from minicc.agent import tool_policy as tp


# ---------- 词汇 ----------

def test_core_write_tools():
    assert tp.CORE_WRITE_TOOLS == frozenset({"write_file", "edit_file"})


def test_write_tool_names_include_worktree_ops():
    assert tp.WRITE_TOOL_NAMES == frozenset(
        {"write_file", "edit_file", "worktree_create", "worktree_remove", "git_stage", "git_commit"}
    )


def test_node_package_managers():
    assert tp.NODE_PACKAGE_MANAGERS == frozenset({"npm", "pnpm", "yarn"})


# ---------- command_may_modify_workspace ----------

@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("", False),
        ("echo hello", False),
        ("cat > out.txt", True),             # 重定向无视程序
        ("rm -rf build", True),
        ("mkdir dist", True),
        ("sed -i s/a/b/ file.txt", True),
        ("sed s/a/b/ file.txt", False),
        ("git status", False),
        ("git commit -m 'x'", True),
        ("git diff", False),
        ("npx tsc", True),                  # 无 --noEmit → 会发射
        ("npx tsc --noEmit", False),
        ("tsc --noEmit", False),
        ("npm run format", True),           # format ⇒ 改写源码
        ("npm run format:check", False),
        ("npm run lint:fix", True),
        ("npm run test", False),
        ("npm install lodash", True),
        ("npm ls", False),
        ("python -c 'import os'", True),    # inline code 可写任意东西
        ("python -m pytest", False),        # -m 是检查器调用
        ("node --check src/app.js", False), # --check 只解析
        ("node -e 'code()'", True),
        ("python -m unittest -v", False),
        ("rsync -a src/ dst/", True),
    ],
)
def test_command_may_modify_workspace(command, expected):
    assert tp.command_may_modify_workspace(command) is expected


# ---------- is_verification_evidence ----------

def _ok(cmd: str, **extra):
    args = {"command": cmd}
    args.update(extra)
    return {"command": cmd, **extra}


@pytest.mark.parametrize(
    ("arguments", "tool", "status", "expected"),
    [
        ({"command": "pytest -q"}, "bash", "ok", True),
        ({"command": "pytest"}, "bash", "error", False),   # 失败不算证据
        ({"command": "pytest -q"}, "read_file", "ok", False),
        ({"command": "pytest -q", "run_in_background": True}, "bash", "ok", False),
        ({"command": "echo pytest"}, "bash", "ok", False),
        ({"command": "pytest -q && rm x"}, "bash", "ok", False),  # 组合拳不行
        ({"command": "pytest --collect-only"}, "bash", "ok", False),
        ({"command": "mypy src/"}, "bash", "ok", True),
        ({"command": "ruff check ."}, "bash", "ok", True),
        ({"command": "ruff check --fix ."}, "bash", "ok", False),
        ({"command": "ruff format --check ."}, "bash", "ok", True),
        ({"command": "node --check src/app.js"}, "bash", "ok", True),
        ({"command": "pnpm test"}, "bash", "ok", True),
        ({"command": "pnpm run test:unit"}, "bash", "ok", True),
        ({"command": "pnpm format"}, "bash", "ok", False),
        ({"command": "pnpm build"}, "bash", "ok", True),
    ],
)
def test_is_verification_evidence(arguments, tool, status, expected):
    assert tp.is_verification_evidence(tool, arguments, status) is expected


# ---------- is_workspace_write / predicts_workspace_write ----------

def test_is_workspace_write_requires_ok_status():
    assert tp.is_workspace_write("write_file", {"path": "a"}, "ok") is True
    assert tp.is_workspace_write("write_file", {"path": "a"}, "error") is False


def test_is_workspace_write_bash_uses_command_heuristic():
    assert tp.is_workspace_write("bash", {"command": "rm -rf x"}, "ok") is True
    assert tp.is_workspace_write("bash", {"command": "echo hi"}, "ok") is False


def test_predicts_workspace_write_ignores_status():
    # 问的是"可能"，因此在状态回来之前就能用
    assert tp.predicts_workspace_write("write_file", {"path": "a"}) is True
    assert tp.predicts_workspace_write("bash", {"command": "sed -i s/a/b/ f"}) is True
    assert tp.predicts_workspace_write("read_file", {"path": "a"}) is False
