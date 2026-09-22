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

The third pair closes the loop from the human's side: ``minicc.config.example``
is the contract a user actually copies from, so every knob it names has to be
settable through ``config.json`` under both spellings - and a name that is not
a knob at all has to say so instead of loading a clean, unrelated config in
silence (``{"max_truns": 40}`` used to be indistinguishable from success).
"""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import fields
from pathlib import Path

import pytest

from minicc.config import Config, load_config

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


# Documented in the example file but read straight from os.environ by another
# module (`logging_setup`, `webauth`, `netguard`, `mcp`, and `home_dir()`
# itself), so a config.json layer is genuinely not where they work.  The gate
# below forbids a key from parking here that config.py does in fact read, so
# this cannot become a dumping ground for names nobody wants to fix.
_ENV_ONLY_KEYS: dict[str, str] = {
    "MINICC_HOME": "决定去哪儿读 config.json，只能来自环境变量",
    "MINICC_LOG_LEVEL": "logging_setup 直接读 os.environ",
    "MINICC_LOG_FILE": "logging_setup 直接读 os.environ",
    "MINICC_WEB_TOKEN": "webauth 读环境变量 / --token / web_token.json",
    "MINICC_ALLOW_PRIVATE_FETCH": "netguard 直接读 os.environ",
    "MINICC_ALLOW_PRIVATE_MCP": "mcp 直接读 os.environ",
}

# `MINICC_SANDBOX` is the one documented name that does not strip onto its
# `Config` field (`sandbox_mode`).  The resolver accepts both bare spellings
# for it; every other knob needs no such exception.
_IRREGULAR_ENV_NAMES = frozenset({"MINICC_SANDBOX"})

# A name no resolver lookup can produce, and not close enough to one to be
# rescued by the suggestion matcher.
_SENTINEL_KEY = "zz_not_a_config_key"


def _resolver_env_names() -> set[str]:
    """Names the resolver consults, read off the call sites that pass literals.

    Stricter than grepping ``MINICC_*`` out of ``config.py``: that regex also
    matches ``os.getenv("MINICC_HOME")`` and the M2-T8 export list, neither of
    which makes a key settable from ``config.json``.
    """
    tree = ast.parse((PACKAGE_ROOT / "config.py").read_text(encoding="utf-8"))
    positions = {"pick": 1, "_optional_positive_int": 0, "_optional_positive_float": 0}
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        index = positions.get(node.func.id)
        if index is None or len(node.args) <= index:
            continue
        argument = node.args[index]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            names.add(argument.value)
    return names


def _documented_keys() -> dict[str, str]:
    """`MINICC_*` keys the example file documents, with the value it suggests."""
    keys: dict[str, str] = {}
    pattern = re.compile(r"^#?\s*(MINICC_[A-Z0-9_]+)=(.*)$")
    for line in EXAMPLE_FILE.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            keys[match.group(1)] = match.group(2).strip()
    return keys


def _documented_knobs() -> dict[str, str]:
    return {
        key: value
        for key, value in _documented_keys().items()
        if key not in _ENV_ONLY_KEYS
    }


@pytest.fixture()
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(tmp_path)
    for key in [k for k in os.environ if k.startswith("MINICC_")]:
        monkeypatch.delenv(key, raising=False)
    # Credentials come from the environment so the row under test is the only
    # thing the config.json file contributes.
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "sk-gate-key")
    monkeypatch.setenv("MINICC_BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("MINICC_MODEL", "gate-model")
    yield home
    for key in [k for k in os.environ if k.startswith("MINICC_")]:
        os.environ.pop(key, None)


def _load_from(home: Path, payload: dict[str, object]) -> Config:
    (home / "config.json").write_text(json.dumps(payload), encoding="utf-8")
    return load_config()


def test_the_documented_key_inventory_is_actually_scanned() -> None:
    assert len(_documented_knobs()) >= 25


def test_env_only_keys_are_parked_for_a_real_reason() -> None:
    """An allowlisted name must be documented and must genuinely bypass config.py."""
    assert len(_resolver_env_names()) >= 25
    documented = set(_documented_keys())
    read_by_config = _resolver_env_names()
    assert set(_ENV_ONLY_KEYS) <= documented, (
        "这些键不在 minicc.config.example 里，不该出现在豁免清单上："
        + "；".join(sorted(set(_ENV_ONLY_KEYS) - documented))
    )
    parked_but_read = sorted(set(_ENV_ONLY_KEYS) & read_by_config)
    assert not parked_but_read, (
        "这些键其实由 config.py 解析，config.json 应当生效，不能再用「只能走环境变量」豁免："
        + "；".join(parked_but_read)
    )


@pytest.mark.parametrize("key,value", sorted(_documented_knobs().items()))
def test_a_documented_key_works_from_config_json_under_both_spellings(
    isolated_home: Path, key: str, value: str
) -> None:
    """The example file is a contract: every knob it names must be settable in
    the file layer, under the env spelling and the bare spelling.

    A key nobody in the resolver consults used to be invisible - `{"max_truns":
    40}` loaded a clean, unrelated config with no message at all.
    """
    bare = key.removeprefix("MINICC_").lower()
    # The sentinel keeps this gate honest: it rides in every payload, so if the
    # stray-key reporter ever stops reporting, "recognized" can no longer be
    # satisfied by an always-empty list.
    via_env = _load_from(isolated_home, {key: value, _SENTINEL_KEY: "x"})
    via_bare = _load_from(isolated_home, {bare: value, _SENTINEL_KEY: "x"})
    assert via_env.unrecognized_config_keys == (_SENTINEL_KEY,), (
        f"{key} 写进 config.json 会被当作不认识的键"
    )
    assert via_bare.unrecognized_config_keys == (_SENTINEL_KEY,), (
        f"{bare} 写进 config.json 会被当作不认识的键"
    )
    assert via_env == via_bare, f"{key} 与 {bare} 两种拼法解析出了不同的配置"


def test_documented_env_names_strip_onto_config_fields() -> None:
    """Naming is the only documentation a key has once the file is open."""
    declared = _config_fields()
    irregular = {
        key
        for key in _documented_knobs()
        if key.removeprefix("MINICC_").lower() not in declared
    }
    assert irregular == set(_IRREGULAR_ENV_NAMES), (
        "这些文档化的环境变量剥掉前缀后对不上任何 Config 字段（用户按字段名写键会静默失效）："
        + "；".join(sorted(irregular ^ _IRREGULAR_ENV_NAMES))
    )
