"""M8-T510 — env 文件家族三个家：`.env` 与 `.env.<profile>`

「这个名字是 env 文件吗」有三个家、三种问法：索引器
（`retrieval.py`，`startswith(".env")` 宽网）、文件工具
（`tools/fs.py`，精确 `.env` 或 `.env.` 前缀且豁免 `.env.example`）、
验证walk（`verification_plan.py`，同款但不豁免）。三个问题的**策略**故意
不同（工具可读 `.env.example`，另两者不豁免），但**家族形状**是一个事
实：家族哪天多了成员，三处必须同时知道。

家安在新叶子模块 `minicc/env_files.py`：读者分布在 `agent` 与 `tools`，
而 tools 不能从 agent 导入，只有叶子模块能同时被两者引用。config 层读
cwd 下字面 `.env` 当配置源是另一个事实，保留自己的拼法。
"""

from __future__ import annotations

import ast
from pathlib import Path

from minicc.agent.retrieval import is_secret_filename
from minicc.agent.verification_plan import VerificationCommand, verification_state
from minicc.env_files import ENV_FAMILY_PREFIX, ENV_FILENAME, is_env_filename
from minicc.tools.fs import _is_sensitive_path

REPO = Path(__file__).resolve().parents[1]
HOME = "minicc/env_files.py"


def test_the_home_pins_the_family() -> None:
    assert ENV_FILENAME == ".env"
    assert ENV_FAMILY_PREFIX == ".env."
    assert is_env_filename(".env") is True
    assert is_env_filename(".env.local") is True
    assert is_env_filename(".env.production") is True
    # In the family; whether a surface exempts it is that surface's policy.
    assert is_env_filename(".env.example") is True
    # The strict family needs the dot: a bare prefix would also net ".envrc".
    assert is_env_filename(".envrc") is False
    assert is_env_filename(".envx") is False
    assert is_env_filename("env") is False
    assert is_env_filename("prod.env") is False


def test_the_family_judgment_is_spelled_nowhere_else() -> None:
    """No hand-spelled family judgment, and every reader asks the home."""
    predicate_literals: list[tuple[str, int]] = []
    loads: dict[str, int] = {"is_env_filename": 0, "ENV_FILENAME": 0, "ENV_FAMILY_PREFIX": 0}
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in loads:
                    loads[node.id] += 1
            if isinstance(node, ast.Constant) and node.value in (".env", ".env."):
                parent_is_predicate = False
                for parent in ast.walk(tree):
                    children: list[ast.AST] = []
                    if isinstance(parent, ast.Compare):
                        children = [parent.left, *parent.comparators]
                    elif (isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute)
                          and parent.func.attr == "startswith"):
                        children = list(parent.args)
                    if any(child is node for child in children):
                        parent_is_predicate = True
                        break
                if parent_is_predicate:
                    predicate_literals.append((path.relative_to(REPO).as_posix(), node.lineno))
    assert predicate_literals == [], (
        "the env-file family is judged by a hand-spelled literal outside its home: "
        + ", ".join(f"{p}:{ln}" for p, ln in predicate_literals)
    )
    # Two readers call the predicate; the home body and the indexer's wide net
    # read the two constants.
    assert loads == {"is_env_filename": 2, "ENV_FILENAME": 2, "ENV_FAMILY_PREFIX": 1}, loads


def test_the_tools_surface_asks_the_home() -> None:
    assert _is_sensitive_path(".env") is True
    assert _is_sensitive_path("sub/dir/.env.local") is True
    # This surface's own carve-out, now visible at the caller.
    assert _is_sensitive_path(".env.example") is False
    assert _is_sensitive_path(".envrc") is False
    assert _is_sensitive_path("credentials.json") is True
    assert _is_sensitive_path("id_rsa") is True
    assert _is_sensitive_path("server.pem") is True
    assert _is_sensitive_path("main.py") is False


def test_the_verification_surface_asks_the_home(tmp_path: Path) -> None:
    commands = [VerificationCommand(command="pytest -q", label="pytest")]

    def state(*names: str) -> tuple[str, bool]:
        workspace = tmp_path / ("ws-" + "-".join(names))
        workspace.mkdir()
        for name in names:
            (workspace / name).write_text("x = 1\n", encoding="utf-8")
        return verification_state(workspace, ["app.py"], commands)

    digest, cacheable = state("app.py", ".env")
    assert digest and cacheable is False
    digest, cacheable = state("app.py", ".env.local")
    assert digest and cacheable is False
    # No carve-out here: an example file still disables reuse.
    digest, cacheable = state("app.py", ".env.example")
    assert digest and cacheable is False
    # The other half of the same line stays pinned too.
    digest, cacheable = state("app.py", "server.pem")
    assert digest and cacheable is False
    digest, cacheable = state("app.py")
    assert digest and cacheable is True


def test_the_index_surface_asks_the_home() -> None:
    # The indexer's net is deliberately wider: anything starting with .env,
    # which also catches .envrc - and it exempts nothing.
    assert is_secret_filename(".env") is True
    assert is_secret_filename(".env.local") is True
    assert is_secret_filename(".env.example") is True
    assert is_secret_filename(".envrc") is True
    assert is_secret_filename("credentials.rs") is False
