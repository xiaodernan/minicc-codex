"""M8-T607 — the fixture vocabularies ask their one homes.

Four pieces of test vocabulary were spelled by hand in multiple places:

* the three fixture doors - ``("v2", "behavior", "legacy")`` - at three test
  sites;
* ``GUIDANCE_FILES`` - the four workspace guidance files - copied from
  ``minicc/prompt.py`` into ``test_core_agent.py``'s parametrize list;
* ``HOOK_EVENTS`` - the four Claude-Code-style hook events - re-spelled
  inline inside ``test_hooks_validation.py``;
* ``GRADER_SCRIPTS`` - the card table the loader/runner
  (``minicc/bench_tasks.py``) owns - shadowed by a local copy inside
  ``tests/test_grader_reads_only_named_keys.py``.

Each now has one home.
"""

from __future__ import annotations

import importlib
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_the_fixture_doors_have_one_home() -> None:
    mod = importlib.import_module("tests._fixture_doors")
    assert mod.DOORS == ("v2", "behavior", "legacy")


def test_guidance_files_are_imported_not_redefined() -> None:
    from minicc.prompt import GUIDANCE_FILES

    test_mod = importlib.import_module("tests.test_core_agent")
    assert test_mod.GUIDANCE_FILES is GUIDANCE_FILES


def test_hook_events_are_imported_not_redefined() -> None:
    from minicc.hooks import HOOK_EVENTS

    test_mod = importlib.import_module("tests.test_hooks_validation")
    assert test_mod.HOOK_EVENTS is HOOK_EVENTS


def test_grader_scripts_are_imported_not_redefined() -> None:
    from minicc.bench_tasks import GRADER_SCRIPTS

    test_mod = importlib.import_module("tests.test_grader_reads_only_named_keys")
    assert test_mod.SCRIPTS is GRADER_SCRIPTS
