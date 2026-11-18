# -*- coding: utf-8 -*-
"""M8-T1211 - the pre-push battery must itself stay honest.

References ``scripts/pre_push_gates.py`` - the one-liner that keeps this file in
the audience floor. The battery's value is that every red it catches is a
red CI would have caught; these legs prove the runner runs its gates, can say
no, and lists them all.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "pre_push_gates.py"
assert SCRIPT.is_file(), "scripts/pre_push_gates.py must exist for this audience to exist"


def _load():
    spec = importlib.util.spec_from_file_location("pre_push_gates", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_scripts_pre_push_gates_lists_every_gate(capsys):
    module = _load()

    code = module.main(["--list"])

    assert code == 0
    out = capsys.readouterr().out
    flat = " ".join(out.split())
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) >= 10
    for expected in ("doc pointers", "route coverage", "impact floor", "web i18n keys resolve"):
        assert expected in flat
    assert len(set(lines)) >= 10, "gate lines must not be duplicated"


def test_scripts_pre_push_gates_self_test_exits_with_the_reserved_code(capsys):
    module = _load()

    code = module.main(["--self-test"])

    assert code == module.SELF_TEST_EXIT
    out = capsys.readouterr().out
    assert "synthetic-fail -> red" in out


def test_scripts_pre_push_gates_only_filter_matches_substring(capsys):
    module = _load()

    code = module.main(["--only", "doc"])

    out = capsys.readouterr().out
    assert code in (0, 1)  # either green or an honest red; never usage error
    assert "no gate matches" not in out


def test_scripts_pre_push_gates_only_filter_with_no_match_is_a_usage_error(capsys):
    module = _load()

    code = module.main(["--only", "zzzz-nope"])

    assert code == 2
    assert "no gate matches" in capsys.readouterr().out
