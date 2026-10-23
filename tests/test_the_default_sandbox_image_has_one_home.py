"""M8-T481 — 默认沙箱镜像两个家：config.py 的常量与 sandbox.py 的硬编码默认参数

``minicc/config.py`` 声明 ``DEFAULT_SANDBOX_IMAGE`` 作为默认沙箱镜像之家，
配置路径（dataclass 字段默认值、``pick`` 回退值）都从它出发。但
``SandboxRunner.__init__`` 的 ``image`` 参数自己抄了一份 ``"python:3.11-slim"``，
而 ``tools/__init__.py`` 的 ``sandbox or SandboxRunner()`` 不传 image——那条路
吃的正是 sandbox.py 的硬编码默认值。改 DEFAULT_SANDBOX_IMAGE 只改到配置路径，
工具路径仍跑旧镜像：同一台机器上两条路径用不同镜像，且没有任何东西会失败。

本门禁把默认镜像钉在一个家里：包里除 config.py 那一处声明外，不允许任何
模块再用字面量承载这个值；SandboxRunner 的默认值必须是家里那个对象本身。
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/config.py"
IMAGE = "python:3.11-slim"


def test_the_home_lives_in_config() -> None:
    """config.py owns the default sandbox image, with the pinned value."""
    from minicc.config import DEFAULT_SANDBOX_IMAGE

    assert DEFAULT_SANDBOX_IMAGE == IMAGE


def test_no_other_module_spells_the_image_inline() -> None:
    """No module spells the default image as a literal outside the one declaration."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == IMAGE:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME), (
        "the default sandbox image is spelled inline outside its one home: "
        + ", ".join(offenders)
    )


def test_sandbox_runner_takes_the_home_object_as_its_default() -> None:
    """SandboxRunner's default image is the home object, not a second copy."""
    from minicc.config import DEFAULT_SANDBOX_IMAGE
    from minicc.sandbox import SandboxRunner

    default = inspect.signature(SandboxRunner.__init__).parameters["image"].default
    assert default is DEFAULT_SANDBOX_IMAGE


def test_the_tools_path_receives_the_home_value() -> None:
    """``sandbox or SandboxRunner()`` in tools/__init__.py gets the home value.

    That call site passes no image, so it runs on the constructor default.
    A drifted default there would silently serve a different image on every
    path that does not go through the config object.
    """
    from minicc.config import DEFAULT_SANDBOX_IMAGE
    from minicc.sandbox import SandboxRunner

    runner = SandboxRunner()
    assert runner.image is DEFAULT_SANDBOX_IMAGE
    assert runner.image == IMAGE
