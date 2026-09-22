"""Config-surface gates: an attribute read off a config object must be declared.

``getattr(obj, "name", default)`` is how this codebase tolerates duck-typed and
legacy config objects, but it also silences the one mistake that matters: reading
a key that was never declared, so the default silently wins forever.
``max_completion_continues`` was capped at 3 in every release for exactly that
reason - the call site had a default and ``Config`` had no field, so no user,
project config file or environment variable could move it.

The second gate covers the other half of "reachable": a key that works but is
written nowhere a human reads. That one exists because this same increment added
two knobs and shipped them undocumented until the scan caught it.
"""

from __future__ import annotations

import ast
import re
from dataclasses import fields
from pathlib import Path

from minicc.config import Config

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "minicc"
EXAMPLE_FILE = REPO_ROOT / "minicc.config.example"
# Floor, not an expectation: the day someone narrows the scan the gate must go red
# instead of passing over an empty list.
_MIN_SITES = 30


def _config_fields() -> set[str]:
    return {field.name for field in fields(Config)}


def _config_getattr_sites() -> list[tuple[str, int, str]]:
    sites: list[tuple[str, int, str]] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "getattr" or len(node.args) != 3:
                continue
            target, attribute = node.args[0], node.args[1]
            if not isinstance(attribute, ast.Constant) or not isinstance(attribute.value, str):
                continue
            if ast.unparse(target).split(".")[-1] != "config":
                continue
            sites.append((path.relative_to(REPO_ROOT).as_posix(), node.lineno, attribute.value))
    return sites


def test_the_config_getattr_scan_covers_the_real_surface() -> None:
    assert len(_config_getattr_sites()) >= _MIN_SITES


def test_every_config_getattr_names_a_field_config_declares() -> None:
    declared = _config_fields()
    offenders = sorted({
        f"{name} at {path}:{line}"
        for path, line, name in _config_getattr_sites() if name not in declared
    })
    assert not offenders, (
        "这些 getattr 读取的键在 Config 上不存在，默认值永远生效（配置项实际不可设置）：" + "；".join(offenders)
    )


def _config_env_keys() -> set[str]:
    text = (PACKAGE_ROOT / "config.py").read_text(encoding="utf-8")
    return set(re.findall(r'"(MINICC_[A-Z0-9_]+)"', text))


def _loader_assigned_fields() -> set[str]:
    """Field names the ``Config(...)`` construction inside ``config.py`` passes."""
    tree = ast.parse((PACKAGE_ROOT / "config.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Config":
            return {keyword.arg for keyword in node.keywords if keyword.arg}
    return set()


# Pinned to "unlimited" by the loader on purpose: a stale env file must not be
# able to truncate a running task. The CLI keeps an explicit escape hatch.
_CONSTANT_FIELDS = frozenset({"max_duration_seconds", "max_tool_calls"})


def test_the_loader_construction_is_actually_scanned() -> None:
    assert len(_loader_assigned_fields()) >= 30


def test_every_config_field_is_resolved_by_a_config_layer() -> None:
    """A field nothing assigns is a constant wearing a dataclass costume.

    ``timeout`` was read by five HTTP call sites and set by nobody: no
    ``MINICC_TIMEOUT``, no ``config.json`` key, only the CLI's ``--timeout``. So
    the Web workbench and every task worker it spawned ran at the compiled-in
    default and had no way to ask for more.
    """
    unreachable = sorted(_config_fields() - _loader_assigned_fields() - _CONSTANT_FIELDS)
    assert not unreachable, (
        "这些字段没有任何配置层会给它赋值，永远只能用 dataclass 默认值：" + "；".join(unreachable)
    )


def test_the_env_key_scan_covers_the_real_surface() -> None:
    # ``load_config`` reads every user-facing key through one literal; a scan that
    # suddenly returns a handful of names means the pattern broke, not the config.
    assert len(_config_env_keys()) >= 30


def test_a_new_config_key_ships_documented_in_the_example_file() -> None:
    """A knob nobody can discover is as unreachable as one that cannot be set.

    ``config.py`` is the user-facing config surface, so every key it reads has to
    appear in ``minicc.config.example`` - which had drifted to 17 of 37 missing
    before this gate existed. Dev-only switches (``MINICC_FAKE_PROVIDER``,
    ``MINICC_EVAL_GRADER_DIR``, ``MINICC_HOOKS``) are read outside ``config.py``
    and stay out of the user example file on purpose.
    """
    example = EXAMPLE_FILE.read_text(encoding="utf-8")
    undocumented = sorted(key for key in _config_env_keys() if key not in example)
    assert not undocumented, (
        "这些环境变量在 config.py 里会被读取，但 minicc.config.example 从未提到，"
        "用户无从知道它们存在：" + "；".join(undocumented)
    )
