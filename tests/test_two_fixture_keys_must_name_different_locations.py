"""M8-T108: two fixture keys must name two *locations*, not merely two spellings.

Batch 92 taught the load doors to compare a fixture's keys against each other, but it compared the
normalised spellings byte for byte. Whether two spellings name one file is not a property of the
bytes - it is a property of the volume the workspace is built on. Measured on this plane (a
case-insensitive volume, `b771eb0`): ``{"A.txt": "upper", "a.txt": "lower"}`` was accepted by all
three doors and left a workspace of **one** file holding ``lower``, with nothing raised, and
``{"p/q.txt", "P/Q.txt"}`` did the same. ``{"P": file, "p/q.txt": child}`` raised ``FileExistsError``
after writing ``P``, and ``{"p/q.txt": child, "P": file}`` raised ``PermissionError``.

The gate is therefore written so it does not bake this host in:
* the host's own identity relation is measured by writing two spellings into a temp dir, and the
  door matrix's expected answer is read from that measurement;
* the two host policies (fold and do-not-fold) are additionally *supplied* to the owner in one run,
  so the plane this batch was written on is not the only plane whose answer is checked.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from minicc import bench_tasks, behavior_bench, benchmarks

REPO = Path(__file__).resolve().parents[1]
BACKSLASH = chr(92)

DOORS = ("v2", "behavior", "legacy")

# Each shape names one location twice on a case-insensitive volume and two locations on a
# case-sensitive one. All are added on top of a real shipped task's own fixture, so a refusal can
# only come from this pair.
CASE_SHAPES: dict[str, dict[str, str]] = {
    "case-duplicate": {"A.txt": "upper", "a.txt": "lower"},
    "case-dir-file": {"p/q.txt": "one", "P/Q.txt": "two"},
    "case-file-then-child": {"P": "is-a-file", "p/q.txt": "child"},
    "case-child-then-file": {"p/q.txt": "child", "P": "is-a-file"},
}

# Distinct on every host: the second key differs by more than case.
NOT_A_PAIR = {"A.txt": "one", "a.md": "two"}

# The batch-92 class reached through a different separator spelling: one location on every host.
SPELLING_VARIANT = {f"A{BACKSLASH}B.txt": "one", "A/B.txt": "two"}

# A spelling with a directory in it, used to ask the owner **how** it consults the host. Both keys
# are two real files on any volume, so the call below must not refuse; only the call log matters.
SEGMENT_SPELLING = {"pkg/a.txt": "1", "b.txt": "2"}

# The segments of the spelling above, as its author wrote them - not the owner's splitting method.
AUTHORED_SEGMENTS = {"pkg", "a.txt", "b.txt"}


def _shipped_task(door: str) -> dict:
    if door == "v2":
        payload = json.loads((REPO / "benchmarks" / "tasks.v2.json").read_text(encoding="utf-8"))
        tasks = payload["tasks"] if isinstance(payload, dict) else payload
        chosen = next(task for task in tasks if task.get("fixture"))
    elif door == "behavior":
        chosen = next(task for task in behavior_bench.behavior_tasks() if task.get("fixture"))
    else:
        chosen = next(task for task in benchmarks.load_tasks() if not task.get("grader"))
    return json.loads(json.dumps(chosen))


def _run_door(door: str, fixture: dict, tmp_path: Path) -> None:
    task = _shipped_task(door)
    task["fixture"] = {**(task.get("fixture") or {}), **fixture}
    task["id"] = f"{task.get('id')}-case"
    if door == "v2":
        bench_tasks.validate_task(task)
    elif door == "behavior":
        behavior_bench.validate_behavior_task(task)
    else:
        path = tmp_path / "legacy-case.json"
        path.write_text(json.dumps([task], ensure_ascii=False), encoding="utf-8")
        benchmarks.load_tasks(path)


def _ask(fixture: dict) -> None:
    bench_tasks.require_writable_fixture({"id": "case-rule", "fixture": fixture})


def _host_folds_case(tmp_path: Path) -> bool:
    """Ask the volume, not the platform name: can two spellings hold two contents?"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    upper = tmp_path / "CaseFoldProbe"
    lower = tmp_path / "casefoldprobe"
    upper.write_text("1", encoding="utf-8")
    lower.write_text("2", encoding="utf-8")
    left = sorted(p.name for p in tmp_path.iterdir())
    if len(left) == 1:
        assert tmp_path.joinpath(*left).read_text(encoding="utf-8") == "2", (
            f"a folding volume must have replaced the first write, found {left}"
        )
        return True
    assert len(left) == 2, f"the probe expected one or two entries, found {left}"
    return False


@pytest.mark.parametrize("label", sorted(CASE_SHAPES))
def test_a_folding_host_makes_the_two_keys_one_position(label: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Supplied policy: on a volume that folds case, each shape is the silent-overwrite class."""
    monkeypatch.setattr(os.path, "normcase", lambda value: value.lower())
    with pytest.raises(ValueError) as caught:
        _ask(CASE_SHAPES[label])
    message = str(caught.value)
    assert "fixture 键" in message, f"{label}: the refusal must name the keys: {message}"


@pytest.mark.parametrize("label", sorted(CASE_SHAPES))
def test_a_case_sensitive_host_must_still_accept_those_keys(
    label: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Supplied policy: where case distinguishes files, the pair is two real files and must load."""
    monkeypatch.setattr(os.path, "normcase", lambda value: value)
    _ask(CASE_SHAPES[label])


def test_a_key_pair_beyond_case_is_accepted_under_both_policies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rule folds spellings to decide identity; it does not forbid mixed case."""
    for policy in (lambda value: value, lambda value: value.lower()):
        monkeypatch.setattr(os.path, "normcase", policy)
        _ask(NOT_A_PAIR)


def test_one_location_under_a_different_spelling_needs_no_case_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``A\\B.txt`` with ``A/B.txt`` is the batch-92 class: identical once separators are read."""
    monkeypatch.setattr(os.path, "normcase", lambda value: value)
    with pytest.raises(ValueError) as caught:
        _ask(SPELLING_VARIANT)
    assert "同一个位置" in str(caught.value), str(caught.value)


@pytest.mark.parametrize("door", DOORS)
@pytest.mark.parametrize("label", sorted(CASE_SHAPES))
def test_every_load_door_answers_what_the_volume_actually_does(label: str, door: str, tmp_path: Path) -> None:
    """The shipped doors must refuse exactly when this host would merge the two writes."""
    folds = _host_folds_case(tmp_path / "probe")
    fixture = CASE_SHAPES[label]
    workspace = tmp_path / f"door-{door}-{label.replace(' ', '_')}"
    workspace.mkdir()
    if folds:
        with pytest.raises(ValueError) as caught:
            _run_door(door, fixture, workspace)
        assert "fixture 键" in str(caught.value), str(caught.value)
    else:
        _run_door(door, fixture, workspace)


def test_the_write_point_still_merges_the_two_spellings(tmp_path: Path) -> None:
    """The door is the only thing between the agent and a silent loss: the host's own answer, pinned.

    On a folding volume ``prepare_fixture`` raises nothing and leaves one file holding the later
    content; on a case-sensitive one it leaves both. Either way the write point is unchanged, which
    is why the refusal has to happen at load time.
    """
    root = tmp_path / "workspace"
    root.mkdir()
    folds = _host_folds_case(tmp_path / "probe")
    behavior_bench.prepare_fixture({"fixture": dict(CASE_SHAPES["case-duplicate"])}, root)
    left = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    if folds:
        assert left == ["A.txt"], f"expected the volume to merge the writes, tree was {left}"
        assert (root / "A.txt").read_text(encoding="utf-8") == "lower", (
            "the surviving file must hold the later write - that is the silent loss"
        )
    else:
        assert left == ["A.txt", "a.txt"], f"expected two files on this volume, tree was {left}"


def test_the_refusal_names_the_task_and_both_authored_spellings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A folded spelling would send the author hunting for a key they never wrote."""
    monkeypatch.setattr(os.path, "normcase", lambda value: value.lower())
    for label, fixture in CASE_SHAPES.items():
        with pytest.raises(ValueError) as caught:
            _ask(fixture)
        message = str(caught.value)
        for key in fixture:
            assert repr(key) in message, f"{label}: refusal must name {key!r}: {message}"
        assert "'case-rule'" in message, f"{label}: refusal must name the task id: {message}"


def _host_identity_calls(monkeypatch: pytest.MonkeyPatch, fixture: dict[str, str]) -> list[str]:
    """Ask the owner with the host's identity function recorded - behaviour left exactly as shipped.

    The recording wrapper returns the host's own answer, so the verdict the owner reaches is the
    verdict this volume would reach; only the *question* is observable afterwards.
    """
    real = os.path.normcase
    asked: list[str] = []
    monkeypatch.setattr(os.path, "normcase", lambda value: asked.append(value) or real(value))
    bench_tasks.require_writable_fixture({"id": "case-rule", "fixture": dict(fixture)})
    return asked


def test_the_identity_question_is_asked_per_segment_of_the_authored_spelling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every segment the author wrote must reach the host, and no whole path may.

    This replaces a gate that searched the owner's body for the *word* ``normcase``: deleting the
    call while leaving the word kept that gate green (batch 93's W1 predicted 19 reds and got 18).
    What is actually claimed is measurable at the call boundary. A whole path must not reach the
    host because ``os.path.normcase`` also rewrites ``/`` on this volume, and a folded whole path
    would quietly stop matching the parent/child prefixes the owner compares - which is batch 93's
    W3, seen here as a named cell instead of a count.
    """
    asked = _host_identity_calls(monkeypatch, SEGMENT_SPELLING)
    whole = [value for value in asked if "/" in value]
    assert whole == [], f"the host is asked per segment, but whole paths reached it: {whole}"
    missing = sorted(AUTHORED_SEGMENTS - set(asked))
    assert missing == [], f"these authored segments never reached the host: {missing} (asked {asked})"
    assert len(asked) >= len(AUTHORED_SEGMENTS), (
        f"the host was asked {len(asked)} times for {asked}; at least one question per authored "
        f"segment ({len(AUTHORED_SEGMENTS)}) - the count is a floor, not the owner's loop shape"
    )


def test_the_identity_gate_is_live_when_the_owner_stops_asking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reach for the cell above: two keys in one workspace must make the host get asked about both."""
    asked = _host_identity_calls(monkeypatch, {"x.txt": "1", "y.txt": "2"})
    assert asked.count("x.txt") >= 1 and asked.count("y.txt") >= 1, (
        f"a host that is never asked cannot answer; the owner asked it about {asked}"
    )


def test_the_identity_question_is_the_hosts_own_function() -> None:
    """The source half this gate really protects: the owner must not fold case in its own body.

    Whether the owner *asks* the host is proven by the two call-boundary cells above; a token search
    cannot show it. What a token search does protect is the other failure: folding the case in the
    source would refuse a legal task on a case-sensitive volume, and it does so whatever spelling of
    "fold in the source" the author picks, so the list names the spellings rather than the one word.
    """
    owners: list[str] = []
    for path in sorted((REPO / "minicc").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "require_writable_fixture":
                body = ast.unparse(node)
                if "同一个位置" in body:
                    owners.append(path.name)
                    for folded in (".lower(", ".upper(", ".casefold("):
                        assert folded not in body, (
                            f"{path.name}: {folded!r} decides identity in the source, "
                            "not on the host's answer"
                        )
    assert owners == ["bench_tasks.py"], f"the pair rule must live in exactly one owner; found {owners}"


def _fixture_refusals(tasks: list[dict]) -> list[tuple[str, str]]:
    """Audit a population by asking the owner the doors ask - not a copy of its comparison."""
    refusals: list[tuple[str, str]] = []
    for task in tasks:
        fixture = task.get("fixture") if isinstance(task, dict) else None
        if not isinstance(fixture, dict):
            continue
        try:
            bench_tasks.require_writable_fixture(task)
        except ValueError as exc:
            refusals.append((str(task.get("id")), str(exc)))
    return refusals


def _shipped_populations() -> dict[str, list[dict]]:
    payload = json.loads((REPO / "benchmarks" / "tasks.v2.json").read_text(encoding="utf-8"))
    v2 = payload["tasks"] if isinstance(payload, dict) else payload
    return {
        "legacy": list(benchmarks.load_tasks()),
        "v2": list(v2),
        "behavior": list(behavior_bench.behavior_tasks()),
    }


def test_no_shipped_task_names_one_location_twice() -> None:
    """Census: nothing in the corpus is refused by the rule the doors now apply.

    The floors come from this same walk, so a narrowed population cannot make the claim vacuous.
    """
    populations = _shipped_populations()
    offenders: list[tuple[str, str]] = []
    items = 0
    for label, tasks in populations.items():
        assert len(tasks) >= 10, f"{label}: only {len(tasks)} tasks loaded - the census read nothing"
        # The legacy corpus carries no fixture at all (measured: 30 tasks, 0 fixtures), so its floor
        # is the task count; the fixture floor below comes from the suites that do carry one.
        items += sum(len(task["fixture"]) for task in tasks if isinstance(task.get("fixture"), dict))
        offenders.extend((label, detail) for detail in _fixture_refusals(tasks))
    assert items >= 30, f"the census walked only {items} fixture entries"
    assert offenders == [], f"shipped tasks would now be refused: {offenders[:5]}"


@pytest.mark.parametrize("policy", ("fold", "identity"))
def test_the_census_detector_has_reach_over_the_class_it_audits(
    policy: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"Zero offenders" must be able to name an offender, or it is reading nothing.

    A population the test supplies, in memory, carries one case-folded pair and one clean task; the
    census walks it and reports exactly the planted task under a folding policy and nothing where
    the two spellings really are two files.
    """
    monkeypatch.setattr(os.path, "normcase", (lambda value: value.lower()) if policy == "fold"
                        else (lambda value: value))
    population = [
        {"id": "planted-fold-pair", "fixture": dict(CASE_SHAPES["case-duplicate"])},
        {"id": "clean-distinct", "fixture": dict(NOT_A_PAIR)},
        {"id": "planted-spelling-variant", "fixture": dict(SPELLING_VARIANT)},
    ]
    found = _fixture_refusals(population)
    named = sorted(task_id for task_id, _ in found)
    if policy == "fold":
        assert named == ["planted-fold-pair", "planted-spelling-variant"], (
            f"the census must name both planted collisions, found {named}"
        )
    else:
        assert named == ["planted-spelling-variant"], (
            f"on a case-sensitive volume only the spelling variant collides, found {named}"
        )
