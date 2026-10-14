"""`minicc.task_contract` must pin the request/result transport contract.

`TaskRequest`/`TaskResult` are the versioned structures passed between the
thread executor and detached workers. Their parsing is where a produced payload
could *lie* about its own bookkeeping, or where a bad schema/empty message could
slip through. These tests pin the contract:

- `resolve_task_permissions`: yolo forces both flags on, plan forces changes off,
  default/acceptEdits honor the flags, illegal modes raise.
- `TaskRequest.from_payload`: schema v1/v2 accepted, v3 rejected, empty message
  rejected, non-dict attachments dropped, round-trips.
- `TaskResult.from_payload`: `children_rolled_up` -- host billing bookkeeping --
  is **stripped** so a produced payload cannot claim the subtree was already
  folded and skip the fold; other fields round-trip.

Pure logic, no IO, so it runs under plain pytest (no temp-dir teardown).
"""
from __future__ import annotations

import pytest

from minicc.task_contract import (
    TaskRequest,
    TaskResult,
    resolve_task_permissions,
)


# --- resolve_task_permissions ----------------------------------------------


def test_default_mode_honors_flags():
    changes, network, mode = resolve_task_permissions({})
    assert (changes, network, mode) == (False, False, "default")


def test_default_mode_allows_changes_when_flag_set():
    changes, network, mode = resolve_task_permissions(
        {"allow_changes": True, "allow_network": True}
    )
    assert (changes, network, mode) == (True, True, "default")


def test_plan_mode_forces_changes_off_but_keeps_network_flag():
    changes, network, mode = resolve_task_permissions(
        {"permission_mode": "plan", "allow_network": True}
    )
    assert changes is False
    assert network is True
    assert mode == "plan"


def test_yolo_mode_forces_both_flags_on_regardless_of_payload():
    changes, network, mode = resolve_task_permissions(
        {"permission_mode": "yolo", "allow_changes": False, "allow_network": False}
    )
    assert (changes, network, mode) == (True, True, "yolo")


def test_yolo_param_turns_changes_on_under_default_mode():
    changes, network, mode = resolve_task_permissions({}, yolo=True)
    assert changes is True
    assert network is False
    assert mode == "default"


def test_accept_edits_alias_normalizes_and_honors_flags():
    changes, network, mode = resolve_task_permissions(
        {"permission_mode": "accept-edits", "allow_changes": True}
    )
    assert mode == "acceptEdits"
    assert changes is True


def test_illegal_permission_mode_raises():
    with pytest.raises(ValueError):
        resolve_task_permissions({"permission_mode": "definitely-not-a-mode"})


# --- TaskRequest.from_payload -------------------------------------------------


def test_schema_v1_accepted_as_legacy():
    # v1 input is accepted (not rejected) but normalized to the current v2
    # internal representation on construction.
    req = TaskRequest.from_payload({"message": "hi", "schema_version": 1})
    assert req.message == "hi"
    assert req.schema_version == 2


def test_schema_v2_accepted():
    req = TaskRequest.from_payload({"message": "hi"})
    assert req.schema_version == 2


def test_schema_v3_rejected():
    with pytest.raises(ValueError):
        TaskRequest.from_payload({"message": "hi", "schema_version": 3})


def test_empty_message_rejected():
    with pytest.raises(ValueError):
        TaskRequest.from_payload({"message": "   "})


def test_non_dict_attachments_dropped():
    req = TaskRequest.from_payload(
        {
            "message": "hi",
            "attachments": [{"ok": 1}, "not-a-dict", 42, {"also": 2}],
        }
    )
    assert req.attachments == [{"ok": 1}, {"also": 2}]


def test_request_round_trips_through_payload():
    original = TaskRequest.from_payload(
        {
            "message": "do the thing",
            "task_id": "t1",
            "workspace_path": "/w",
            "allow_changes": True,
            "model": "m",
        }
    )
    restored = TaskRequest.from_payload(original.to_payload())
    assert restored.message == "do the thing"
    assert restored.task_id == "t1"
    assert restored.workspace_path == "/w"
    assert restored.allow_changes is True
    assert restored.model == "m"
    assert restored.schema_version == 2


# --- TaskResult.from_payload (security contract) ---------------------------


def test_children_rolled_up_is_stripped_from_metadata():
    # A produced payload must NOT be able to claim the subtree was already
    # folded and so skip the host's billing fold.
    result = TaskResult.from_payload(
        {"answer": "ok", "children_rolled_up": True}
    )
    assert result.answer == "ok"
    assert "children_rolled_up" not in result.metadata
    assert result.metadata == {}


def test_result_keeps_core_fields_and_pushes_extras_to_metadata():
    result = TaskResult.from_payload(
        {
            "answer": "a",
            "error": "e",
            "cancelled": True,
            "tokens_used": {"x": 1},
            "extra": "kept",
        }
    )
    assert result.answer == "a"
    assert result.error == "e"
    assert result.cancelled is True
    assert result.tokens_used == {"x": 1}
    assert result.metadata == {"extra": "kept"}


def test_result_round_trips_through_payload():
    original = TaskResult(answer="a", tokens_used={"x": 1}, metadata={"k": "v"})
    restored = TaskResult.from_payload(original.to_payload())
    assert restored.answer == "a"
    assert restored.tokens_used == {"x": 1}
    assert restored.metadata == {"k": "v"}
    # children_rolled_up can never sneak in via to_payload
    assert "children_rolled_up" not in original.to_payload()
