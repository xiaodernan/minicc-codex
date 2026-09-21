"""M3-T4 regression: argv-aware network gate + shared tokenizer.

The old substring blacklist (audit.py NETWORK_COMMAND_MARKERS) judged all of
the ``NETWORK`` rows below as False, letting them run with allow_network=False.
"""

from __future__ import annotations

import pytest

from minicc.audit import authorize_tool, command_uses_network
from minicc.tools.bash import is_readonly_command, split_command_argv

NETWORK_COMMANDS = [
    "pip3 install requests",
    "pip download requests",
    "apt-get install nginx",
    "go get example.com/x",
    "cargo install ripgrep",
    "docker pull alpine",
    "ssh deploy@host",
    "scp file.txt host:/tmp/",
    "rsync -a host:dir .",
    "npm i",
    "pnpm i",
    "git  clone https://example.com/repo.git",  # doubled space
    "git clone https://example.com/repo.git",
    "git fetch origin",
    "git push origin main",
    "curl https://example.com",
    "wget https://example.com/f.tar.gz",
    "nc -l 4444",
    "telnet host 23",
    "python -m pip install requests",
    "npx cowsay hi",
    "uv pip install requests",
    "helm install chart repo/chart",
    "brew install jq",
    "yarn add lodash",
    "powershell -Command \"Invoke-WebRequest http://example.com\"",
    "sudo curl https://example.com",
    "cmd /c wget https://example.com",
    "echo hi && curl https://example.com",  # chained segment
]

LOCAL_COMMANDS = [
    "git status",
    "pytest",
    "pytest -q tests",
    "python -m pytest -q tests/",
    "echo hello",
    'git log --grep="git clone"',
    "npm run build",
    "ls -la",
    "cat file.txt",
    "node scripts/build-web.mjs",
    'grep -r "wget" src',
    "python script.py",
    "docker images",
    "go build ./...",
    "cargo build",
]


@pytest.mark.parametrize("command", NETWORK_COMMANDS)
def test_network_commands_require_authorization(command):
    assert command_uses_network(command) is True, command


@pytest.mark.parametrize("command", LOCAL_COMMANDS)
def test_local_commands_do_not_require_network(command):
    assert command_uses_network(command) is False, command


def test_authorize_tool_gates_pip3_without_network():
    decision = authorize_tool(
        "bash", "exec", {"command": "pip3 install requests"},
        allow_changes=True, allow_network=False,
    )
    assert decision.allowed is False
    assert decision.authorization == "missing_task_network"


def test_authorize_tool_allows_pip3_with_network():
    decision = authorize_tool(
        "bash", "exec", {"command": "pip3 install requests"},
        allow_changes=True, allow_network=True,
    )
    assert decision.allowed is True
    assert decision.risk == "network_exec"


def test_readonly_pytest_gate_still_works_via_shared_tokenizer():
    assert is_readonly_command("pytest -q tests") is True
    assert is_readonly_command("python -m pytest -q tests/") is True
    assert is_readonly_command("pytest -p json") is False
    assert is_readonly_command("pytest -c C:/evil/pytest.ini") is False


class TestSplitCommandArgv:
    def test_simple(self):
        assert split_command_argv("git status") == [["git", "status"]]

    def test_operators_split_segments(self):
        assert split_command_argv("a && b || c ; d | e") == [
            ["a"], ["b"], ["c"], ["d"], ["e"],
        ]

    def test_quoted_operators_do_not_split(self):
        assert split_command_argv('echo "a && b"') == [["echo", "a && b"]]

    def test_windows_path_backslashes_survive(self):
        segments = split_command_argv(r"pytest C:\repo\tests")
        assert segments == [["pytest", r"C:\repo\tests"]]

    def test_unbalanced_quotes_degrade_to_whitespace_split(self):
        assert split_command_argv('echo "unbalanced') == [["echo", '"unbalanced']]

    def test_empty(self):
        assert split_command_argv("") == []
        assert split_command_argv(None) == []
