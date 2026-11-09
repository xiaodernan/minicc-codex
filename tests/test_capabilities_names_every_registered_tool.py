"""P5：--capabilities 必须逐条点名注册表里的工具，且不许有第二份名单。

能力目录一旦手写就会和注册表漂移：注册了新工具而目录没跟上，机器读到
的能力比模型实际能调用的少；删了工具而目录没改，则会承诺一个根本不存
在的工具。这里把 CLI 的 stdout 与 ``build_registry`` 本身逐项对比，让
漂移在注册表变更的同一批次里就变红。
"""

from __future__ import annotations

import json

from minicc.main import main
from minicc.tools import Editor, build_registry


def _capabilities(tmp_path, capsys, extra: list[str] | None = None) -> dict:
    argv = ["--capabilities", "--workspace", str(tmp_path), *(extra or [])]
    assert main(argv) == 0
    return json.loads(capsys.readouterr().out)


def test_capabilities_names_every_registered_tool(tmp_path, capsys) -> None:
    payload = _capabilities(tmp_path, capsys)
    registry = build_registry(Editor(tmp_path))

    assert payload["count"] == len(registry.names())
    assert [tool["name"] for tool in payload["tools"]] == registry.names()
    assert set(tool["name"] for tool in payload["tools"]) == set(registry.names())
    for tool in payload["tools"]:
        assert tool["description"] == registry.spec(tool["name"]).description


def test_json_flag_does_not_wrap_the_capability_object_a_second_time(tmp_path, capsys) -> None:
    plain = _capabilities(tmp_path, capsys)
    combined = _capabilities(tmp_path, capsys, ["--json"])

    assert combined == plain
    assert set(combined) == {"count", "tools"}
