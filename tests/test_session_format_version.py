"""M8-T82: a checkpoint format version must have one writer and one real reader.

Measured first: ``minicc/session.py`` wrote ``"version": 1`` at six sites and read it
nowhere, while the healthy shape in the same package (``minicc/snapshots.py``) branches
on its version. An unread version field is a promise the format never keeps - the next
incompatible writer would reshape old files instead of refusing them.

The gate is deliberately about derivation, not agreement: it changes the constant and
requires the bytes on disk to follow. Comparing the file against ``SESSION_FORMAT_VERSION``
after a normal write would pass even if the writer hardcoded the literal.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from minicc import session as session_module
from minicc.session import SESSION_FORMAT_VERSION, SessionError, SessionStore

SESSION_SOURCE = Path(session_module.__file__)


def _payload(store: SessionStore) -> dict:
    return json.loads(store.path.read_text(encoding="utf-8"))


def test_the_writer_follows_the_constant_not_a_copy_of_it(tmp_path: Path, monkeypatch) -> None:
    """Change the number; the file must change with it."""
    monkeypatch.setattr(session_module, "SESSION_FORMAT_VERSION", 7)
    store = SessionStore(tmp_path, "derive-check")
    store.save([{"role": "user", "content": "hi"}])
    written = _payload(store)
    assert written["version"] == 7, (
        f"the writer emitted {written['version']!r} while the constant said 7: "
        "some site still hardcodes the literal and a future bump will split them"
    )


def test_six_writers_became_one_source(tmp_path: Path) -> None:
    """Every version the file writes today must come from the same place."""
    store = SessionStore(tmp_path, "single-source")
    store.save([{"role": "user", "content": "a"}])
    store.save_view({"last_item": 3, "compact_tools": False})
    payload = _payload(store)
    assert payload["version"] == SESSION_FORMAT_VERSION, payload
    assert payload["view"]["version"] == SESSION_FORMAT_VERSION, payload["view"]


def test_a_version_this_code_cannot_read_is_refused(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "from-the-future")
    store.save([{"role": "user", "content": "a"}])
    payload = _payload(store)
    payload["version"] = SESSION_FORMAT_VERSION + 1
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SessionError) as raised:
        SessionStore(tmp_path, "from-the-future").load("sys")
    message = str(raised.value)
    assert str(SESSION_FORMAT_VERSION + 1) in message and str(SESSION_FORMAT_VERSION) in message, (
        f"the refusal must name both numbers so a reader can act on it: {message!r}"
    )


def test_a_versionless_checkpoint_is_still_readable(tmp_path: Path) -> None:
    """The other side: files written before this field meant anything still load."""
    store = SessionStore(tmp_path, "legacy")
    store.save([{"role": "user", "content": "a"}])
    payload = _payload(store)
    del payload["version"]
    store.path.write_text(json.dumps(payload), encoding="utf-8")
    assert SessionStore(tmp_path, "legacy").load("sys")[-1]["content"] == "a"


def test_the_source_holds_exactly_one_version_literal() -> None:
    tree = ast.parse(SESSION_SOURCE.read_text(encoding="utf-8"), filename=str(SESSION_SOURCE))
    literals: list[int] = []
    declared = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value.endswith("version")
                    and isinstance(value, ast.Constant)
                ):
                    literals.append(value.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SESSION_FORMAT_VERSION":
                    declared.append(node.value)
    assert literals == [], f"version literals are back in session.py: {literals}"
    assert len(declared) == 1 and isinstance(declared[0], ast.Constant), (
        f"expected one SESSION_FORMAT_VERSION assignment, found {len(declared)}"
    )


def test_someone_actually_reads_the_declared_version() -> None:
    """The defect was six writers and zero Load sites - keep that shape impossible."""
    tree = ast.parse(SESSION_SOURCE.read_text(encoding="utf-8"), filename=str(SESSION_SOURCE))
    loads = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) \
                and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str) and node.slice.value.endswith("version"):
            loads += 1
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" and node.args \
                and isinstance(node.args[0], ast.Constant) \
                and isinstance(node.args[0].value, str) and node.args[0].value.endswith("version"):
            loads += 1
    assert loads >= 1, (
        "session.py went back to writing a format version nobody reads; "
        "the field only earns its keep if a reader branches on it"
    )
