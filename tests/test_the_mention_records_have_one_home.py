"""M8-T407 — 提及记录五字段四个家：两个助手与两个注入分支各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/mentions.py"

FIELDS = {"token", "path", "status", "reason", "truncated"}


def test_the_home_exists_in_mentions() -> None:
    """mentions.py owns the record shape in one builder."""
    from minicc.mentions import _record

    record = _record("tok", "a/b.py", "injected", "", False)
    assert set(record) == FIELDS
    assert record == {
        "token": "tok", "path": "a/b.py", "status": "injected",
        "reason": "", "truncated": False,
    }


def test_no_module_inlines_the_record_shape() -> None:
    """No module spells the five fields as a dict literal outside the builder."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if len(node.keys) >= 3 and keys == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the mention record shape is spelled inline outside its one builder: "
        + ", ".join(offenders)
    )


def test_mention_records_still_carry_every_field(tmp_path: Path) -> None:
    """Behavior unchanged: injected and rejected records keep all five fields."""
    from minicc.mentions import build_mention_context

    (tmp_path / "a.py").write_text("print('a')\n", encoding="utf-8")
    (tmp_path / "big.py").write_text("x = 1\n" * 5000, encoding="utf-8")
    _block, records = build_mention_context(
        "@a.py @big.py @../outside.py", tmp_path,
        max_chars_per_file=50,
    )
    by_path = {record["path"]: record for record in records}
    assert set(by_path["a.py"]) == FIELDS
    assert by_path["a.py"]["status"] == "injected"
    assert by_path["big.py"]["truncated"] is True
    assert any(record["status"] == "rejected" for record in records), records
