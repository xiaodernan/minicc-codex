from pathlib import Path
from minicc.agent.check_commands import command_parts, verification_identity
from minicc.agent.completion import CompletionDecision, _enforce_completion_evidence
from minicc.agent.test_selection import relevant_python_tests
from minicc.agent.tool_policy import is_verification_evidence


def test_windows_interpreter_and_paths_are_preserved():
    command = '"C:\\Program Files\\Python311\\python.exe" -B -m pytest "tests\\test_app.py" -q'
    assert command_parts(command)[0] == "C:\\Program Files\\Python311\\python.exe"
    assert is_verification_evidence("bash", {"command": command}, "ok")
    assert verification_identity(command) == verification_identity("pytest tests/test_app.py -v")
    assert command_parts('pytest --ignore="a b" -k "hello world"') == ["pytest", "--ignore=a b", "-k", "hello world"]


def test_equivalent_recheck_resolves_failure_but_other_selection_does_not():
    events = [
        {"name": "write_file", "path": "app.py", "status": "ok", "write": True},
        {"name": "bash", "command": "python -m pytest tests/test_app.py -q", "status": "error"},
        {"name": "bash", "command": "pytest ./tests/test_other.py -v", "status": "ok"},
    ]
    def decision(): return CompletionDecision(status="complete", rationale="done", evidence=["event-1"])
    assert _enforce_completion_evidence(decision(), events, []).status == "continue"
    events.append({"name": "bash", "command": "pytest ./tests/test_app.py -vv", "status": "ok"})
    assert _enforce_completion_evidence(decision(), events, []).status == "complete"


def test_ast_discovery_handles_src_layout_multiline_alias_and_ignores_comments(tmp_path):
    (tmp_path / "tests").mkdir()
    fixtures = {
        "test_import.py": "import package.module as alias\n",
        "test_from.py": "from package import (\n module as alias,\n)\n",
        "test_symbols.py": "from package.module import Thing\n",
        "test_comment.py": "# from package.module import Thing\n",
        "test_string.py": "text='import package.module'\n",
        "test_other.py": "from package.other import Thing\n",
    }
    for name, content in fixtures.items():
        (tmp_path / "tests" / name).write_text(content)
    selected = relevant_python_tests(tmp_path, ["src/package/module.py"])
    assert selected == ["tests/test_from.py", "tests/test_import.py", "tests/test_symbols.py"]
