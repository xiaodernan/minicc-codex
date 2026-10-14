"""行为级栅栏：minicc.audit 的安全授权纯逻辑契约。

这些函数是「允许/拒绝工具执行」的唯一裁决点，安全关键却长期零单测。
本文件把每条契约钉成可复跑的断言，覆盖：

- ``tool_requires_authorization``：write/exec 必走门、readonly 网络工具必走门、
  readonly 非网络工具免门、声明 ``network`` 能力的工具必走门。
- ``_is_network_tool``：工具名 + 能力声明两类判定。
- ``normalize_permission_mode``：default/plan/acceptEdits/yolo 及其别名/大小写/
  空白；非法值抛 ``ValueError``。
- ``AuthorizationDecision.to_event``：允许/拒绝两份事件形状。
- ``_executable_name``：路径/扩展名/大小写归一。
- ``command_uses_network``：argv 感知的网络探测（M3-T4），含引号保护、
  包管理器动词、python -m 模块、shell 包装器递归。
- ``authorize_tool``：yolo / 网络查询 / 只读 / 计划模式 / 写入 / 命令执行 /
  未知风险 各分支，**一律 workspace=None** 保持密封（不触碰 permissions.json /
  session allowlist 集成路径，那些由别车道以集成测试覆盖）。

全程无临时目录、无 git、无网络，秒级可跑。直接调用（绕过 pytest 收尾）也行：
``python tests/test_audit_authorization.py``。
"""

from __future__ import annotations

import pytest

from minicc.audit import (
    AuthorizationDecision,
    _executable_name,
    _is_network_tool,
    authorize_tool,
    command_uses_network,
    normalize_permission_mode,
    tool_requires_authorization,
)


# --------------------------------------------------------------------------
# tool_requires_authorization
# --------------------------------------------------------------------------

def test_write_risk_always_requires_auth():
    assert tool_requires_authorization("write_file", "write") is True
    assert tool_requires_authorization("anything", "write", ("network",)) is True


def test_exec_risk_always_requires_auth():
    assert tool_requires_authorization("bash", "exec") is True


def test_readonly_network_tool_name_requires_auth():
    assert tool_requires_authorization("web_search", "readonly") is True
    assert tool_requires_authorization("webfetch", "readonly") is True


def test_readonly_non_network_tool_skips_auth():
    assert tool_requires_authorization("read_file", "readonly") is False


def test_readonly_tool_with_network_capability_requires_auth():
    assert tool_requires_authorization("read_file", "readonly", ("network",)) is True


def test_none_risk_readonly_skips_auth():
    assert tool_requires_authorization("read_file", None) is False


# --------------------------------------------------------------------------
# _is_network_tool
# --------------------------------------------------------------------------

def test_network_tool_names():
    assert _is_network_tool("web_search") is True
    assert _is_network_tool("webfetch") is True


def test_non_network_tool_name():
    assert _is_network_tool("read_file") is False


def test_network_capability_declaration():
    assert _is_network_tool("read_file", ("network",)) is True
    assert _is_network_tool("read_file", ("read", "network")) is True


def test_empty_and_none_tool_are_not_network():
    assert _is_network_tool("") is False
    assert _is_network_tool(None) is False


# --------------------------------------------------------------------------
# normalize_permission_mode
# --------------------------------------------------------------------------

def test_normalize_canonical_modes():
    assert normalize_permission_mode("default") == "default"
    assert normalize_permission_mode("plan") == "plan"
    assert normalize_permission_mode("acceptEdits") == "acceptEdits"
    assert normalize_permission_mode("yolo") == "yolo"


def test_normalize_empty_and_aliases_map_to_default():
    assert normalize_permission_mode("") == "default"
    assert normalize_permission_mode("normal") == "default"
    assert normalize_permission_mode("standard") == "default"


def test_normalize_accept_edits_aliases():
    assert normalize_permission_mode("acceptedits") == "acceptEdits"
    assert normalize_permission_mode("accept-edits") == "acceptEdits"
    assert normalize_permission_mode("accept_edits") == "acceptEdits"


def test_normalize_case_and_whitespace_insensitive():
    assert normalize_permission_mode("YOLO") == "yolo"
    assert normalize_permission_mode(" Plan ") == "plan"


def test_normalize_none_defaults_to_default():
    assert normalize_permission_mode(None) == "default"


def test_normalize_invalid_raises():
    with pytest.raises(ValueError):
        normalize_permission_mode("bogus")
    with pytest.raises(ValueError):
        normalize_permission_mode(123)


# --------------------------------------------------------------------------
# AuthorizationDecision.to_event
# --------------------------------------------------------------------------

def test_to_event_allowed_shape():
    decision = AuthorizationDecision(True, "write", "reason", "task_write")
    event = decision.to_event("my_tool")
    assert event == {
        "kind": "authorization",
        "name": "my_tool",
        "status": "ok",
        "phase": "permission",
        "code": "tool_authorized",
        "summary": "reason",
        "risk": "write",
        "authorization": "task_write",
    }


def test_to_event_denied_shape():
    decision = AuthorizationDecision(False, "exec", "nope", "missing_task_exec")
    event = decision.to_event("bash")
    assert event["status"] == "denied"
    assert event["code"] == "tool_denied_by_policy"
    assert event["name"] == "bash"


# --------------------------------------------------------------------------
# _executable_name
# --------------------------------------------------------------------------

def test_executable_name_bare():
    assert _executable_name("curl") == "curl"


def test_executable_name_strips_path_and_extension():
    assert _executable_name("C:\\Windows\\System32\\curl.exe") == "curl"
    assert _executable_name("/usr/bin/wget.cmd") == "wget"
    assert _executable_name("python.exe") == "python"


def test_executable_name_casefolds():
    assert _executable_name("/bin/Git.EXE") == "git"


def test_executable_name_none():
    assert _executable_name(None) == "none"


# --------------------------------------------------------------------------
# command_uses_network (M3-T4 argv-aware detection)
# --------------------------------------------------------------------------

def test_network_executables_detected():
    assert command_uses_network("curl https://x") is True
    assert command_uses_network("wget http://x") is True
    assert command_uses_network("ssh user@host") is True
    assert command_uses_network("scp f user@h:/x") is True
    assert command_uses_network("rsync -a host:/p /l") is True


def test_package_manager_verbs_detected():
    assert command_uses_network("pip3 install requests") is True
    assert command_uses_network("pip install requests") is True
    assert command_uses_network("npm install lodash") is True
    assert command_uses_network("docker build .") is True
    assert command_uses_network("kubectl get pods") is True
    assert command_uses_network("go get example.com/x") is True
    assert command_uses_network("python3 -m pip download x") is True


def test_python_m_module_network_only_for_network_modules():
    assert command_uses_network("python -m pip install x") is True
    assert command_uses_network("python -m poetry add x") is True
    assert command_uses_network("python -m pytest") is False


def test_git_clone_detected_but_grep_inside_quotes_not():
    assert command_uses_network("git clone x") is True
    assert command_uses_network('git log --grep="git clone"') is False
    assert command_uses_network("git status") is False
    assert command_uses_network("git fetch") is True


def test_non_network_commands_clean():
    assert command_uses_network("ls -la") is False
    assert command_uses_network("echo hello") is False
    assert command_uses_network("npm run build") is False
    assert command_uses_network("cargo build") is False
    assert command_uses_network(None) is False


def test_shell_wrappers_recurse():
    assert command_uses_network("sudo curl https://x") is True
    assert command_uses_network("cmd /c wget http://x") is True
    assert command_uses_network("sh -c 'curl x'") is True
    assert command_uses_network('powershell -Command "pip install x"') is True


def test_npx_always_network():
    assert command_uses_network("npx create-react-app") is True


# --------------------------------------------------------------------------
# authorize_tool (workspace=None: hermetic flag-branch coverage)
# --------------------------------------------------------------------------

def _decide(tool, risk, arguments=None, *, allow_changes=False, allow_network=False,
            permission_mode="default", capabilities=()):
    return authorize_tool(
        tool, risk, arguments or {},
        allow_changes=allow_changes, allow_network=allow_network,
        permission_mode=permission_mode, workspace=None, capabilities=capabilities,
    )


def test_yolo_readonly_allowed():
    d = _decide("read_file", "readonly", permission_mode="yolo")
    assert d.allowed is True
    assert d.authorization == "task_yolo"
    assert d.risk == "readonly"


def test_yolo_write_allowed():
    d = _decide("write_file", "write", permission_mode="yolo")
    assert d.allowed is True
    assert d.authorization == "task_yolo"


def test_yolo_exec_allowed():
    d = _decide("bash", "exec", {"command": "echo hi"}, permission_mode="yolo")
    assert d.allowed is True
    assert d.authorization == "task_yolo"


def test_network_readonly_allowed_when_granted():
    d = _decide("webfetch", "readonly", allow_network=True)
    assert d.allowed is True
    assert d.authorization == "task_network"
    assert d.risk == "network_readonly"


def test_network_readonly_denied_without_grant():
    d = _decide("webfetch", "readonly", allow_network=False)
    assert d.allowed is False
    assert d.authorization == "missing_task_network"


def test_readonly_non_network_auto_allowed():
    d = _decide("read_file", "readonly")
    assert d.allowed is True
    assert d.authorization == "default_readonly"


def test_write_plan_mode_denied():
    d = _decide("write_file", "write", allow_changes=True, allow_network=True,
                permission_mode="plan")
    assert d.allowed is False
    assert d.authorization == "plan_mode_write"


def test_write_default_with_allow_changes():
    d = _decide("write_file", "write", allow_changes=True)
    assert d.allowed is True
    assert d.authorization == "task_write"


def test_write_with_network_capability_needs_network_grant():
    d = _decide("write_file", "write", capabilities=("network",))
    assert d.allowed is False
    assert d.authorization == "missing_task_network"


def test_write_accept_edits_auto_allowed():
    d = _decide("write_file", "write", permission_mode="acceptEdits")
    assert d.allowed is True
    assert d.authorization == "task_write"


def test_exec_network_command_allowed():
    d = _decide("bash", "exec", {"command": "curl https://x"},
                allow_changes=True, allow_network=True)
    assert d.allowed is True
    assert d.authorization == "task_network"
    assert d.risk == "network_exec"


def test_exec_network_command_denied_without_grant():
    d = _decide("bash", "exec", {"command": "curl https://x"},
                allow_changes=True, allow_network=False)
    assert d.allowed is False
    assert d.authorization == "missing_task_network"


def test_exec_readonly_pytest_verification_allowed():
    d = _decide("bash", "exec", {"command": "pytest -q"})
    assert d.allowed is True
    assert d.authorization == "safe_verification"
    assert d.risk == "readonly_exec"


def test_exec_non_readonly_allowed_with_changes():
    d = _decide("bash", "exec", {"command": "echo hi"}, allow_changes=True)
    assert d.allowed is True
    assert d.authorization == "task_exec"


def test_exec_non_readonly_denied_without_changes():
    d = _decide("bash", "exec", {"command": "echo hi"}, allow_changes=False)
    assert d.allowed is False
    assert d.authorization == "missing_task_exec"


def test_unknown_risk_denied():
    d = _decide("weird_tool", None, allow_changes=True, allow_network=True)
    assert d.allowed is False
    assert d.authorization == "unknown_risk"
    assert d.risk == "unknown"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
