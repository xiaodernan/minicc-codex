"""Gates for M8-T542: one ``--check`` lists each directory once, and every reader
answers from that one listing.

Through M8-T541 one ``impacted_tests.py --check`` walked the same directories eight
times: ``minicc`` three times (``_read_trees``, ``build``, ``verified_facades``),
``tests`` three times (``_read_trees``, ``census_gates``, ``_audience_documents``),
``scripts`` once and the workflows once. A directory listing is a fact that cannot
change inside one run, and its cost is paid again every time a batch adds a gate.

The legs below count listings, not seconds: a wall-clock reading that moves with
the machine cannot keep this claim honest. One leg refuses to let any reader list
behind the snapshot, and two compute the floor, the census and the facade exemption
through both the snapshot and the standalone readers: "listed once" is only worth
shipping when it answers the same thing.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package; register the module before executing it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic(root: Path) -> None:
    """A tree where each judgment has one non-trivial answer.

    ``minicc.pkg`` is a verified facade (its ``__all__`` is exactly what it binds),
    ``minicc.pkg.x`` is reached by nothing, ``minicc.lonely`` by one test, and one
    test walks ``minicc`` so the census has a gate to find.
    """
    (root / "minicc" / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "docs").mkdir()
    (root / "minicc" / "__init__.py").write_text("", encoding="utf-8")
    (root / "minicc" / "lonely.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "minicc" / "pkg" / "__init__.py").write_text(
        "from .x import Y\n\n__all__ = ['Y']\n", encoding="utf-8")
    (root / "minicc" / "pkg" / "x.py").write_text("Y = 1\n", encoding="utf-8")
    (root / "tests" / "test_uses.py").write_text(
        "from minicc import lonely\n\n\ndef test_it():\n    assert lonely.VALUE == 1\n",
        encoding="utf-8")
    (root / "tests" / "test_walks_the_tree.py").write_text(
        "from pathlib import Path\n\n\ndef test_walks():\n"
        "    for path in Path('minicc').rglob('*.py'):\n        assert path\n",
        encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "steps:\n  - run: python scripts/foo.py\n", encoding="utf-8")
    (root / "scripts" / "foo.py").write_text("print(1)\n", encoding="utf-8")
    (root / "docs" / "x.md").write_text("# x\n", encoding="utf-8")
    (root / "README.md").write_text("# x\n", encoding="utf-8")


def _point_at(monkeypatch, script, root: Path) -> None:
    monkeypatch.setattr(script, "REPO_ROOT", root)
    monkeypatch.setattr(script, "WORKFLOWS", root / ".github" / "workflows")


# --------------------------------------------------------------------------- #
# 1. One run, one listing per directory - counted, and it listed everything.
# --------------------------------------------------------------------------- #


def test_the_impact_check_lists_each_directory_once() -> None:
    script = _load("minicc_impacted_listings_t542", "scripts/impacted_tests.py")
    expected = {
        ("minicc", "*.py"): len(list((REPO_ROOT / "minicc").rglob("*.py"))),
        ("tests", "*.py"): len(list((REPO_ROOT / "tests").glob("*.py"))),
        ("scripts", "*.py"): len(list((REPO_ROOT / "scripts").glob("*.py"))),
        ("workflows", "*.yml"): len(
            list((REPO_ROOT / ".github" / "workflows").glob("*.yml"))),
    }
    records: list[tuple[str, str, int]] = []
    real_glob, real_rglob = Path.glob, Path.rglob

    def glob(self, pattern, *args, **kwargs):
        found = list(real_glob(self, pattern, *args, **kwargs))
        records.append((self.name, pattern, len(found)))
        return found

    def rglob(self, pattern, *args, **kwargs):
        found = list(real_rglob(self, pattern, *args, **kwargs))
        records.append((self.name, pattern, len(found)))
        return found

    Path.glob, Path.rglob = glob, rglob
    try:
        code = script.main(["README.md", "--check"])
    finally:
        Path.glob, Path.rglob = real_glob, real_rglob
    assert code == 0, code
    assert len(records) == 4, (
        f"{len(records)} directory listings in one --check; each of the four "
        "directories is one fact and is asked once"
    )
    assert sorted(records) == sorted(
        (directory, pattern, count) for (directory, pattern), count in expected.items()
    ), (records, expected)


# --------------------------------------------------------------------------- #
# 2. No reader lists behind the snapshot.
# --------------------------------------------------------------------------- #


def test_no_reader_lists_the_tree_behind_the_snapshot(monkeypatch) -> None:
    script = _load("minicc_impacted_readers_t542", "scripts/impacted_tests.py")
    listings = script._listings()
    trees = script._read_trees(listings)

    def boom(*args, **kwargs):
        raise AssertionError("a reader listed the tree after the snapshot was taken")

    monkeypatch.setattr(script, "_modules", boom)
    monkeypatch.setattr(script, "_script_modules", boom)
    monkeypatch.setattr(Path, "glob", boom)
    monkeypatch.setattr(Path, "rglob", boom)

    audience, references, all_tests = script.build(trees, listings)
    gates = script.census_gates(trees, listings.tests)
    floor = script.unattended(audience, trees, listings.modules)
    assert floor == [], floor
    assert gates and references and all_tests


# --------------------------------------------------------------------------- #
# 3. The snapshot answers what the standalone readers answer.
# --------------------------------------------------------------------------- #


def test_the_snapshot_answers_what_the_standalone_readers_answer(
    tmp_path: Path, monkeypatch,
) -> None:
    script = _load("minicc_impacted_equality_t542", "scripts/impacted_tests.py")
    root = tmp_path / "repo"
    _synthetic(root)
    _point_at(monkeypatch, script, root)

    listings = script._listings()
    trees = script._read_trees(listings)
    snap_audience, snap_refs, snap_all = script.build(trees, listings)
    snap_gates = script.census_gates(trees, listings.tests)
    snap_facades = script.verified_facades(modules=listings.modules, trees=trees)
    snap_floor = script.unattended(snap_audience, trees, listings.modules)

    lone_audience, lone_refs, lone_all = script.build()
    lone_gates = script.census_gates()
    lone_facades = script.verified_facades()
    lone_floor = script.unattended(lone_audience)

    assert snap_audience == lone_audience
    assert snap_refs == lone_refs
    assert snap_all == lone_all
    assert snap_gates == lone_gates
    assert snap_facades == lone_facades
    assert snap_floor == lone_floor == ["minicc.pkg.x"]


# --------------------------------------------------------------------------- #
# 4. The floor is still answered through the snapshot, not diluted by it.
# --------------------------------------------------------------------------- #


def test_an_unattended_module_is_still_named_through_the_snapshot(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    script = _load("minicc_impacted_floor_t542", "scripts/impacted_tests.py")
    root = tmp_path / "repo"
    _synthetic(root)
    _point_at(monkeypatch, script, root)
    code = script.main(["README.md", "--check"])
    captured = capsys.readouterr()
    assert code == 1, (code, captured.out, captured.err)
    assert "minicc.pkg.x" in captured.err, captured.err
    assert "minicc.pkg.__init__" not in captured.err, (
        f"a verified facade was reported as unattended: {captured.err!r}"
    )
