"""M8-T490 — 未识别键判词两个家：配置加载器与 MCP 加载器各拼一套

「你写了一个没有任何查找会读的键」这条警告有两个家：`config.py` 的
config.json 层（主语是层标签 + 文件路径）与 `mcp.py` 的 server 条目（主
语是 server 名）。判词句子「不会被读取（已按默认值运行）」和它的建议尾
巴「，是否想写 X？」在两个加载器里各手拼一遍——一个加载器改了措辞而另
一个没跟上，就是一类用户从没见过的警告，而没有任何测试会红。

家安在 `minicc/config.py`，紧挨 `_unrecognized_layer_keys`——同一件事的
另一半（哪些键算未识别）本来就住在这里。

`mcp.py` 里按传输限定的死键报告（「不会被读取（只有 X 传输会读它）」）
是另一个时刻的另一件事，按判别式留在原地，门禁钉住它仍只有一个现场。
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/config.py"
MCP = "minicc/mcp.py"
VERDICT = "不会被读取（已按默认值运行）"
TAIL = "，是否想写 "
TRANSPORT = "不会被读取（只有"


def _literal_strings():
    """Every string literal's text - f-string parts joined, so a
    hand-written f-string is seen as one literal, not its pieces."""
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        inside_fstring: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for child in ast.iter_child_nodes(node):
                    inside_fstring.add(id(child))
        for node in ast.walk(tree):
            if id(node) in inside_fstring:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield path, node.lineno, node.value
            elif isinstance(node, ast.JoinedStr):
                parts = [
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                ]
                yield path, node.lineno, "".join(parts)


def _sites(fragment: str) -> list[str]:
    return [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_strings()
        if fragment in text
    ]


def test_the_home_pins_both_shapes() -> None:
    from minicc.config import unrecognized_key_warning

    assert (
        unrecognized_key_warning("用户配置 /tmp/x", "max_truns")
        == "用户配置 /tmp/x 中的键 'max_truns' 不会被读取（已按默认值运行）"
    )
    assert (
        unrecognized_key_warning("MCP server 'srv'", "commnd", "command")
        == "MCP server 'srv' 中的键 'commnd' 不会被读取（已按默认值运行），是否想写 'command'？"
    )


def test_the_verdict_and_its_tail_are_spelled_exactly_once() -> None:
    for fragment in (VERDICT, TAIL):
        offenders = _sites(fragment)
        assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
            f"{fragment!r} is spelled by hand outside its one home: "
            + ", ".join(offenders)
        )


def test_both_loaders_ask_the_home() -> None:
    config = (REPO / HOME).read_text(encoding="utf-8")
    mcp = (REPO / MCP).read_text(encoding="utf-8")
    assert config.count("unrecognized_key_warning(") == 2, (
        "the definition plus the config-layer call are the only spellings"
    )
    assert mcp.count("unrecognized_key_warning(") == 1, (
        "the MCP loader must ask the home exactly once"
    )


def test_the_mcp_loader_shares_one_object() -> None:
    from minicc import config, mcp

    assert mcp.unrecognized_key_warning is config.unrecognized_key_warning


def test_the_mcp_loader_emits_the_homes_sentence(tmp_path: Path, monkeypatch) -> None:
    """Drive the real MCP loader: a misspelled key draws the home's warning."""
    from minicc.config import unrecognized_key_warning
    from minicc.mcp import load_mcp_config

    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_MCP", "1")
    workspace = tmp_path / "ws"
    (workspace / ".minicc").mkdir(parents=True)
    (workspace / ".minicc" / "mcp.json").write_text(
        json.dumps({"servers": {"typo": {"command": "echo", "commnd": "echo"}}}),
        encoding="utf-8",
    )
    captured: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    handler = Capture()
    logger = logging.getLogger("minicc.mcp")
    logger.addHandler(handler)
    try:
        load_mcp_config(workspace)
    finally:
        logger.removeHandler(handler)
    assert captured == [
        unrecognized_key_warning("MCP server 'typo'", "commnd", "command")
    ], captured


def test_the_config_loader_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    """Drive the real config loader: a stray key draws the home's warning."""
    import os

    from minicc.config import load_config, unrecognized_key_warning

    cwd = tmp_path / "cwd"
    home = tmp_path / "home"
    for directory in (cwd, home):
        directory.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "test-key-placeholder")
    monkeypatch.chdir(cwd)
    for key in [
        k
        for k in os.environ
        if k.startswith("MINICC_") and k not in {"MINICC_HOME", "MINICC_API_KEY"}
    ]:
        monkeypatch.delenv(key)
    (home / "config.json").write_text(
        json.dumps({"api_key": "test-key-placeholder", "modle": "gpt-4"}),
        encoding="utf-8",
    )
    load_config()
    messages = [m for m in caplog.messages if "modle" in m]
    assert len(messages) == 1, messages
    assert messages[0] == unrecognized_key_warning(
        f"用户配置 {home / 'config.json'}", "modle", "model"
    ), messages[0]


def test_the_transport_scoped_report_is_a_different_fact() -> None:
    """A key the transport never consults is another moment, one site."""
    offenders = _sites(TRANSPORT)
    assert len(offenders) == 1 and offenders[0].startswith(MCP + ":"), (
        "the transport-scoped report is one fact with one site: "
        + ", ".join(offenders)
    )
