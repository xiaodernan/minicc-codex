"""The .minicc internal filenames must have exactly one home each."""

from __future__ import annotations

import ast
import pathlib

from minicc.allowlist import ALLOWLIST_NAME
from minicc.hooks import HOOKS_FILENAME
from minicc.permissions import PERMISSIONS_NAME
from minicc.internal_paths import AUDIT_NAME, MCP_CONFIG_NAME
from minicc.tools.fs import _MINICC_DENY_FILES, _MINICC_REDACT_FILES
from minicc.webauth import TOKEN_FILE_NAME

REPO = pathlib.Path(__file__).resolve().parents[1]


def _literal_counts() -> dict[str, list[tuple[str, int]]]:
    hits: dict[str, list[tuple[str, int]]] = {}
    for path in sorted((REPO / "minicc").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                hits.setdefault(node.value, []).append(
                    (path.relative_to(REPO).as_posix(), node.lineno)
                )
    return hits


def test_deny_set_names_the_five_internal_files():
    assert _MINICC_DENY_FILES == {
        ALLOWLIST_NAME,
        TOKEN_FILE_NAME,
        "audit.jsonl",
        HOOKS_FILENAME,
        PERMISSIONS_NAME,
    }


def test_owner_constants_are_the_wire_names():
    assert ALLOWLIST_NAME == "allowlist.json"
    assert TOKEN_FILE_NAME == "web_token.json"
    assert HOOKS_FILENAME == "hooks.json"
    assert PERMISSIONS_NAME == "permissions.json"


def test_four_names_have_exactly_one_literal_each():
    counts = _literal_counts()
    for name in (ALLOWLIST_NAME, TOKEN_FILE_NAME, HOOKS_FILENAME, PERMISSIONS_NAME,
                 AUDIT_NAME, MCP_CONFIG_NAME):
        hits = counts.get(name, [])
        assert len(hits) == 1, (name, hits)
        assert hits[0][0] == "minicc/internal_paths.py", (name, hits)


def test_fs_has_no_filename_literals_of_its_own():
    tree = ast.parse((REPO / "minicc" / "tools" / "fs.py").read_text(encoding="utf-8"))
    values = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    for name in (ALLOWLIST_NAME, TOKEN_FILE_NAME, HOOKS_FILENAME, PERMISSIONS_NAME,
                 AUDIT_NAME, MCP_CONFIG_NAME):
        assert name not in values, name
