"""M8-T759 — README 承诺的交互命令必须和保留名册一致。

`minicc/commands.py::RESERVED_COMMAND_NAMES` 是 slash 命令的保留家：自定义
`.minicc/commands/<name>.md` 不得遮蔽内置名。README 引用一份
"交互命令"清单，但那行字由人写——名单和代码各自漂移过一次（README
漏了 `/quit`，即 `/exit` 的别名），而没有人在 CI 里问这个问题。这个门
只问一件事：README 那行交互命令里点名的每个保留名，以及代码里的每个
保留名，两边必须互相看得见。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"

from minicc.commands import RESERVED_COMMAND_NAMES


def _readme_interaction_line() -> str:
    text = README.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("- 交互命令："):
            return line
    raise AssertionError("README.md no longer declares the interaction-command line")


def test_every_reserved_name_is_advertised() -> None:
    line = _readme_interaction_line()
    advertised = set(re.findall(r"/([a-z][a-z0-9-]*)", line))
    missing = sorted(RESERVED_COMMAND_NAMES - advertised)
    assert missing == [], (
        "RESERVED_COMMAND_NAMES ships these slash commands but README.md's "
        "interaction-command line does not advertise them: " + ", ".join(missing)
    )


def test_every_advertised_name_is_reserved() -> None:
    line = _readme_interaction_line()
    advertised = set(re.findall(r"/([a-z][a-z0-9-]*)", line))
    unexpected = sorted(advertised - RESERVED_COMMAND_NAMES)
    assert unexpected == [], (
        "README.md's interaction-command line names slash commands that are "
        "not in RESERVED_COMMAND_NAMES: " + ", ".join(unexpected)
    )
