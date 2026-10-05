"""M8-T136: a hook that fails to launch must speak the one vocabulary that has a reader.

``minicc/hooks.py`` has four failure paths in ``_run_one`` — bad env key, spawn
failure, pipe failure, timeout — plus the two exit-code branches. Three of the
failure paths resolved the hook's ``on_failure`` policy; the bad-env-key path
instead stamped ``decision="error"``.  That spelling has no reader: the only
thing the agent loop consults is ``HookOutcome.denied``, which is
``self.decision == "deny"`` (``minicc/agent/loop.py:1069``), so a
``PreToolUse`` hook whose config carried ``"on_failure": "deny"`` and an env key
like ``MY-VAR`` silently allowed the tool call, and the trace line printed
``status="ok"`` because only ``decision == "deny"`` maps to an error status.

Two measurements made before writing this file, both on a detached plane at the
tip this gate lands on:
* ``{"env": {"MY-VAR": "1"}, "on_failure": "deny"}`` ⇒ ``entry.decision ==
  "error"``, ``outcome.denied is False``; the control ``{"MY_VAR": "1"}`` with
  ``exit 2`` ⇒ ``"deny"``, ``denied is True``.  So the red is a refused
  decision, not a crash.
* ``grep -rn "load_error" minicc/`` ⇒ producers at ``hooks.py:158``/``:168``,
  one reader at ``describe()``; ``decision="error"`` appears exactly once in the
  package and nowhere else ⇒ an unread status, not a documented third outcome.

Deliberately NOT done here: validating env key names at load time.  The loader
is all-or-nothing (any ``HookConfigError`` clears ``self.specs``), so a typo in
one hook's env block would disable every other hook in the file — including the
deny hooks — which is a wider fail-open than the bug.  Case
``test_the_illegal_env_key_hook_loads_while_a_broken_matcher_blanks_the_set``
pins that choice both ways.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import minicc.hooks as hooks_module
from minicc.hooks import HookOutcome, HookRunner, HookSpec

REPO_ROOT = Path(__file__).resolve().parent.parent
MINICC_DIR = REPO_ROOT / "minicc"
PAYLOAD: dict[str, Any] = {
    "event": "PreToolUse",
    "tool": "write_file",
    "arguments": {"path": "notes.md"},
}
ILLEGAL_ENV_KEY = "MINICC-HOOK"  # a hyphen is not legal in an env key name
DENY_COMMAND = "exit 2"  # cmd.exe / sh both leave errorlevel 2
PROCEED_COMMAND = "exit 0"


def _runner(workspace: Path, entries: list[dict[str, Any]]) -> HookRunner:
    return HookRunner(
        workspace, config={"hooks": {"PreToolUse": entries}}
    )


def _code_built_runner(workspace: Path, *, on_failure: str) -> tuple[HookRunner, HookOutcome]:
    """A spec whose env block the launcher (not the loader) refuses.

    Built directly because the loader never sees this shape: it is the shape a
    plugin constructs.  The failure still has to resolve the same policy.
    """
    runner = HookRunner(workspace, config={"hooks": {}})
    runner.specs.append(
        HookSpec(
            event="PreToolUse",
            command=PROCEED_COMMAND,
            env={ILLEGAL_ENV_KEY: "1"},
            on_failure=on_failure,
        )
    )
    return runner, runner.run("PreToolUse", PAYLOAD)


def test_a_launch_failure_with_on_failure_deny_denies_the_tool(tmp_path: Path) -> None:
    """The clause that was broken: policy over an unread status."""
    runner, outcome = _code_built_runner(tmp_path, on_failure="deny")
    entry = outcome.outputs[0]
    assert outcome.denied, (
        f"on_failure=deny must deny when the hook never launched; "
        f"entry={entry!r} outcome.decision={outcome.decision!r}"
    )
    assert outcome.decision == "deny", entry
    reason = outcome.denial_reason()
    assert ILLEGAL_ENV_KEY in reason, (
        f"the denial must name the offending env key, got {reason!r}"
    )


def test_the_same_failure_with_on_failure_continue_allows_and_stays_in_vocabulary(
    tmp_path: Path,
) -> None:
    """on_failure=continue is still the user's choice — but it must be sayable.

    Asserting the literal spelling, not just ``not denied``: the shipped code
    answered ``"error"``, which reads as allow only by accident.
    """
    _runner_obj, outcome = _code_built_runner(tmp_path, on_failure="continue")
    entry = outcome.outputs[0]
    assert entry["decision"] == "allow", entry
    assert ILLEGAL_ENV_KEY in str(entry.get("reason") or ""), entry


def test_the_file_config_path_denies_too(tmp_path: Path, monkeypatch) -> None:
    """Reachability: hooks.json is what production actually feeds the runner."""
    monkeypatch.delenv("MINICC_HOOKS", raising=False)
    cfg = tmp_path / ".minicc"
    cfg.mkdir()
    (cfg / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "command": PROCEED_COMMAND,
                            "env": {ILLEGAL_ENV_KEY: "1"},
                            "on_failure": "deny",
                        }
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    runner = HookRunner(tmp_path)
    assert len(runner.specs) == 1, (runner.load_error, runner.specs)
    outcome = runner.run("PreToolUse", PAYLOAD)
    assert outcome.denied, (runner.load_error, outcome.outputs)


def test_a_working_deny_hook_is_unchanged(tmp_path: Path) -> None:
    """Control: the exit-code path this fix must not touch."""
    runner = _runner(
        tmp_path, [{"command": DENY_COMMAND, "env": {"MINICC_HOOK_VAR": "1"}}]
    )
    outcome = runner.run("PreToolUse", PAYLOAD)
    assert outcome.denied, outcome.outputs
    assert outcome.outputs[0]["decision"] == "deny", outcome.outputs


def test_the_illegal_env_key_hook_loads_while_a_broken_matcher_blanks_the_set(
    tmp_path: Path,
) -> None:
    """The design choice, pinned from both ends.

    A bad matcher rejects the whole file (``specs == []``), so load-time
    validation is a per-file switch.  An illegal env key must keep loading and
    fail per-hook instead — otherwise one typo would disarm every deny hook in
    the same file, which is a bigger fail-open than the bug being fixed.
    """
    illegal_env = _runner(
        tmp_path,
        [{"command": PROCEED_COMMAND, "env": {ILLEGAL_ENV_KEY: "1"}, "on_failure": "deny"}],
    )
    assert illegal_env.load_error is None, illegal_env.load_error
    assert len(illegal_env.specs) == 1, illegal_env.specs
    broken_matcher = _runner(
        tmp_path, [{"command": PROCEED_COMMAND, "matcher": "(", "on_failure": "deny"}]
    )
    assert broken_matcher.load_error, "a bad matcher must still be a load error"
    assert broken_matcher.specs == [], broken_matcher.specs


def test_run_one_never_produces_a_decision_spelling_without_a_reader() -> None:
    """Lexical census of the vocabulary this method can emit, from its own AST.

    Collects every value assigned to ``decision`` inside ``_run_one`` — keyword
    arguments, ``entry["decision"] = ...`` assignments, dict literals, and both
    branches of a ternary — and requires the set to be exactly the two spellings
    ``HookOutcome.denied`` can read.
    """
    source = Path(hooks_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_run_one"
    )

    def constants(node: ast.expr) -> list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.IfExp):
            return constants(node.body) + constants(node.orelse)
        return []

    found: list[str] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.keyword) and node.arg == "decision" and node.value is not None:
            found += constants(node.value)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "decision"
                ):
                    found += constants(node.value)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "decision":
                    found += constants(value)
    assert len(found) >= 5, f"the census read only {found}; it must cover every branch"
    spellings = set(found)
    assert spellings == {"allow", "deny"}, (
        f"_run_one emits {sorted(spellings)}; HookOutcome.denied only reads 'deny', "
        "so any other spelling is an allow with extra steps"
    )


def test_the_deny_reader_recognises_only_deny() -> None:
    """Why an unread status is a silent allow — the mechanism, not the symptom."""
    for spelling in ("error", "", "blocked", "Allow", "DENY"):
        outcome = HookOutcome(decision=spelling)
        assert outcome.denied is False, spelling
        assert outcome.denial_reason() == "hook denied", spelling
    assert HookOutcome(decision="deny").denied is True


def test_the_loop_is_the_only_decision_reader_and_acts_on_denied() -> None:
    """The consumer this gate protects must still consult ``denied``.

    If the loop stops reading ``outcome.denied``, the deny vocabulary this fix
    standardises on is decoration — so the claim is re-measured, not assumed.
    """
    loop_source = (MINICC_DIR / "agent" / "loop.py").read_text(encoding="utf-8")
    tree = ast.parse(loop_source)
    reads = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "denied"
        and isinstance(node.value, ast.Name)
        and node.value.id in {"outcome", "hook_outcome"}
    ]
    assert len(reads) >= 2, f"expected a UserPromptSubmit and a PreToolUse leg, got {reads}"
    # Every construction site loads hooks.json from the workspace, so the file
    # path (not a test-only config dict) is what production arms.
    constructions = []
    for path in sorted(MINICC_DIR.glob("*.py")):
        if path.name == "hooks.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "HookRunner":
                keywords = {kw.arg for kw in node.keywords}
                constructions.append((f"{path.name}:{node.lineno}", "config" in keywords))
    assert len(constructions) >= 2, constructions
    assert all(not uses_config for _site, uses_config in constructions), constructions


def _forbidden_decision_assertions(source: str) -> list[str]:
    """Asserts that compare a ``decision`` to a spelling outside allow|deny.

    AST, not text: this file's own docstring quotes the shipped spelling, and a
    line scan would charge its own prose (the shape that matters is an
    assertion or a literal keyword argument, not a mention).
    """
    hits: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            for index, other in enumerate(operands):
                if isinstance(other, ast.Constant) and isinstance(other.value, str):
                    if other.value in {"allow", "deny"}:
                        continue
                    partner = operands[index - 1] if index else operands[1]
                    if "decision" in ast.dump(partner):
                        hits.append(f"line {node.lineno}: {other.value!r}")
        elif isinstance(node, ast.keyword) and node.arg == "decision":
            if isinstance(node.value, ast.Constant) and node.value.value not in {"allow", "deny"}:
                hits.append(f"line {node.value.lineno}: literal {node.value.value!r}")
    return hits


def test_no_test_needs_the_removed_spelling() -> None:
    """The fix deletes a status; nothing may still ask for it.

    Scoped to this package's own hook tests, with a positive control on the
    shipped spelling so an empty result cannot mean a blind detector.
    """
    files = sorted((REPO_ROOT / "tests").glob("test_hook*.py"))
    assert files, "the scan read no hook test file at all"
    per_file = {path.name: _forbidden_decision_assertions(path.read_text(encoding="utf-8")) for path in files}
    assert all(hits == [] for hits in per_file.values()), per_file
    control = _forbidden_decision_assertions(
        'assert entry["decision"] == "error"\n'
        'o = HookOutcome(decision="error")\n'
        'assert o.denied is False\n'
    )
    assert len(control) == 2, control
