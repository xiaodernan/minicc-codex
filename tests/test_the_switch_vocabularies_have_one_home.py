"""M8-T383 — 六个开关词表各自只有一个家：config 校验 / provider 构造 / CLI choices 三面同源"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"

# vocabulary name -> (home module, home file, expected members)
HOMES = {
    "SANDBOX_MODES": ("minicc.config", "minicc/config.py", {"host", "docker", "auto"}),
    "REASONING_EFFORTS": ("minicc.config", "minicc/config.py", {"low", "mid", "high", "xhigh", "max", "ultra"}),
    "TOOL_MODES": ("minicc.config", "minicc/config.py", {"auto", "native", "envelope"}),
    "LLM_PROTOCOLS": ("minicc.config", "minicc/config.py", {"auto", "responses", "chat_completions"}),
    "PROVIDER_TYPES": ("minicc.config", "minicc/config.py", {"auto", "openai", "anthropic"}),
    "TASK_EXECUTORS": ("minicc.config", "minicc/config.py", {"thread", "process"}),
    "PERMISSION_MODES": ("minicc.audit", "minicc/audit.py", {"default", "plan", "acceptEdits", "yolo"}),
}

CLI_FLAGS = {
    "--reasoning-effort": "REASONING_EFFORTS",
    "--tool-mode": "TOOL_MODES",
    "--sandbox": "SANDBOX_MODES",
    "--provider-type": "PROVIDER_TYPES",
    "--task-executor": "TASK_EXECUTORS",
    "--permission-mode": "PERMISSION_MODES",
}

# Named subsets are legitimate, but they must stay subsets of their home.
SUBSETS = {
    "WRITABLE_PERMISSION_MODES": ("minicc.agent.subagent", "PERMISSION_MODES"),
    "EXEC_PERMISSION_MODES": ("minicc.agent.subagent", "PERMISSION_MODES"),
}


def _home_value(name: str):
    module_name, _, _ = HOMES[name]
    return getattr(importlib.import_module(module_name), name)


def test_every_switch_vocabulary_has_one_home() -> None:
    """Each vocabulary exists in exactly its home module, with the expected members."""
    for name, (module_name, _, members) in HOMES.items():
        value = _home_value(name)
        assert set(value) == members, f"{name} in {module_name}: {sorted(value)}"


def test_cli_choices_derive_from_their_home() -> None:
    """main.py's choices for every switch flag equal their home, derived not hand-written."""
    from minicc.main import _parser

    parser = _parser()
    by_flag = {
        option: action
        for action in parser._actions
        for option in action.option_strings
    }
    for flag, home_name in CLI_FLAGS.items():
        action = by_flag[flag]
        assert action.choices is not None, f"{flag} lost its choices"
        assert set(action.choices) == set(_home_value(home_name)), (
            f"{flag} choices drifted from {home_name}"
        )


def test_no_module_inlines_a_switch_vocabulary() -> None:
    """No module outside the home spells a switch vocabulary as a literal.

    Scans both ``set`` and ``tuple`` literals - argparse choices arrive as
    tuples (M8-T382's lesson), config validations as sets.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) < 2 or len(elements) != len(node.elts):
                continue
            for name, (_, home_file, members) in HOMES.items():
                if elements == frozenset(members) and relative != home_file:
                    offenders.append(f"{relative}:{node.lineno} spells {name}")
            # M8-T399: the named subsets are facts too. task_manager spelled
            # WRITABLE_PERMISSION_MODES by hand and only the subset-of-home
            # check existed - nothing watched for a *second* copy.
            for name, (subset_home, home_name) in SUBSETS.items():
                subset = getattr(importlib.import_module(subset_home), name)
                if (
                    len(node.elts) >= 2
                    and elements == frozenset(subset)
                    and relative != subset_home.replace(".", "/") + ".py"
                ):
                    offenders.append(f"{relative}:{node.lineno} spells {name}")
    assert not offenders, "inline switch vocabularies outside their home: " + ", ".join(offenders)


def test_the_home_itself_declares_each_vocabulary_exactly_once() -> None:
    """The home file may spell the vocabulary exactly once - its declaration."""
    for name, (_, home_file, members) in HOMES.items():
        path = REPO / home_file
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hits = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if elements == frozenset(members) and len(node.elts) == len(members):
                hits += 1
        assert hits == 1, f"{home_file} spells {name} {hits} times (declaration is 1)"


def test_named_subsets_stay_subsets_of_their_home() -> None:
    """A named subset of a switch vocabulary must remain a subset of it."""
    for subset_name, (module_name, home_name) in SUBSETS.items():
        subset = getattr(importlib.import_module(module_name), subset_name)
        home = _home_value(home_name)
        assert set(subset) <= set(home), f"{subset_name} escaped {home_name}: {sorted(subset)}"
