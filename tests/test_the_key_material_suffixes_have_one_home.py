"""M8-T511 — 密钥材料后缀词表三个家：`.pem`/`.key`/`.p12`/`.pfx`/`.kdbx`

「带这个后缀的文件本身就是密钥」这张表有三个家、且已经漂移：文件工具
知道四件（`tools/fs.py` 的 `SENSITIVE_SUFFIXES`），索引器知道五件
（`retrieval.py` 的 `SECRET_SUFFIXES`，多学了 `.kdbx`），验证 walk 行内
只写了两件。后果不是报错而是静默：一把 `.p12` 证书，工具拒绝读，验证却
当干净输入放行缓存复用。

家安在新叶子模块 `minicc/secret_suffixes.py`：读者分布在 `agent` 与
`tools`，只有叶子模块能同时被两者引用。取向取**并集**——多拒一个文件
是安全方向。存成 tuple 而不是 set：文件工具要把它交给 `str.endswith`。
"""

from __future__ import annotations

import ast
from pathlib import Path

from minicc.agent.retrieval import is_secret_filename
from minicc.agent.verification_plan import VerificationCommand, verification_state
from minicc.secret_suffixes import KEY_MATERIAL_SUFFIXES
from minicc.tools.fs import _is_sensitive_path

REPO = Path(__file__).resolve().parents[1]
HOME = "minicc/secret_suffixes.py"
SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kdbx")


def test_the_home_pins_the_tuple() -> None:
    assert KEY_MATERIAL_SUFFIXES == SUFFIXES
    # A tuple, because the tools hand it to str.endswith.
    assert isinstance(KEY_MATERIAL_SUFFIXES, tuple)


def test_each_suffix_is_spelled_exactly_once_in_the_home() -> None:
    hits: dict[str, list[tuple[str, int]]] = {}
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in SUFFIXES:
                hits.setdefault(node.value, []).append(
                    (path.relative_to(REPO).as_posix(), node.lineno)
                )
    for suffix in SUFFIXES:
        sites = hits.get(suffix, [])
        assert len(sites) == 1 and sites[0][0] == HOME, (suffix, sites)


def test_the_tools_surface_asks_the_home() -> None:
    for suffix in SUFFIXES:
        assert _is_sensitive_path(f"server{suffix}") is True, suffix
    assert _is_sensitive_path("server.PEM".lower()) is True
    assert _is_sensitive_path("main.py") is False


def test_the_index_surface_asks_the_home() -> None:
    for suffix in SUFFIXES:
        assert is_secret_filename(f"deploy{suffix}") is True, suffix
    assert is_secret_filename("deploy.txt") is False


def test_the_verification_surface_asks_the_home(tmp_path: Path) -> None:
    commands = [VerificationCommand(command="pytest -q", label="pytest")]

    def state(*names: str) -> tuple[str, bool]:
        workspace = tmp_path / ("ws-" + "-".join(n.strip(".") for n in names))
        workspace.mkdir()
        for name in names:
            (workspace / name).write_text("x = 1\n", encoding="utf-8")
        return verification_state(workspace, ["app.py"], commands)

    for suffix in SUFFIXES:
        digest, cacheable = state("app.py", f"server{suffix}")
        assert digest and cacheable is False, suffix
    digest, cacheable = state("app.py")
    assert digest and cacheable is True
