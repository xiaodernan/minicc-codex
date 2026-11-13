"""M8-T907: the prefix fingerprint ships with every usage record.

The gateway's prefix cache pays or refuses on byte-stable prefixes. When a
task reads ``hit=0`` on its second turn there was no way to tell *why* - a
drifting system message, unstable tool schemas, or a rebuilt history all die
silently behind the same counters. ``prefix_fingerprint`` ships the shape
with the usage record so the task snapshot alone answers it: consecutive
turns share ``tools_fp`` and extend ``msgs_fp``'s lineage; a moving
``system_fp`` means the prompt is rebuilt per turn and will never cache.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from minicc.llm.usage import prefix_fingerprint


def test_same_content_same_fingerprint():
    a = prefix_fingerprint([{"role": "system", "content": "hello"}, {"role": "user", "content": "world"}], [{"name": "read_file"}])
    b = prefix_fingerprint([{"role": "system", "content": "hello"}, {"role": "user", "content": "world"}], [{"name": "read_file"}])
    assert a == b, "identical prefixes must fingerprint identically"


def test_one_drifting_byte_changes_msgs_fp():
    base = [{"role": "system", "content": "stable"}, {"role": "user", "content": "hello"}]
    drift = [{"role": "system", "content": "stable"}, {"role": "user", "content": "hello "}]
    a = prefix_fingerprint(base)
    b = prefix_fingerprint(drift)
    assert a["msgs_fp"] != b["msgs_fp"], "a single trailing space must move the lineage"
    assert a["system_fp"] == b["system_fp"], "the system message did not drift"
    assert a["tools_fp"] == b["tools_fp"]


def test_system_drift_is_its_own_field():
    a = prefix_fingerprint([{"role": "system", "content": "v1"}])
    b = prefix_fingerprint([{"role": "system", "content": "v2"}])
    assert a["system_fp"] != b["system_fp"], "a rebuilt prompt must be visible"


def test_tools_drift_is_its_own_field():
    a = prefix_fingerprint([], [{"name": "read_file"}])
    b = prefix_fingerprint([], [{"name": "read_file"}, {"name": "edit_file"}])
    assert a["tools_fp"] != b["tools_fp"]
    assert a["msgs_fp"] == b["msgs_fp"] == prefix_fingerprint([])["msgs_fp"]


def test_shape_and_counts():
    fp = prefix_fingerprint(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        [{"name": "t"}],
    )
    assert set(fp) == {"system_fp", "msgs_fp", "tools_fp", "n_msgs", "chain"}
    assert fp["n_msgs"] == 2
    for key in ("system_fp", "msgs_fp", "tools_fp"):
        assert len(fp[key]) == 12 and all(c in "0123456789abcdef" for c in fp[key]), key


def test_chain_shares_prefix_length_between_lineages():
    # T1 ships 92 messages, T2 ships the same 92 plus three tail messages:
    # the chains must agree on every shared index, and the first disagreement
    # lands exactly at the append point. A drift anywhere earlier would show
    # up as a mid-chain split instead.
    head = [{"role": "system", "content": "s"}] + [{"role": "user", "content": f"m{i}"} for i in range(10)]
    tail = [{"role": "assistant", "content": "done"}]
    short = prefix_fingerprint(head)["chain"]
    long = prefix_fingerprint(head + tail)["chain"]
    assert long[: len(short)] == short, "a pure append must extend the chain without moving it"
    assert len(long) == len(short) + len(tail)


def test_empty_and_malformed_inputs_degrade():
    empty = prefix_fingerprint([])
    assert empty["n_msgs"] == 0 and empty["system_fp"]
    none = prefix_fingerprint(None, None)
    assert none["n_msgs"] == 0
    # non-mapping rows are skipped, not fatal
    mixed = prefix_fingerprint(["garbage", {"role": "user", "content": "x"}])
    assert mixed["n_msgs"] == 1


def test_provider_attaches_fingerprints_to_usage():
    # the two call sites in _attempt_once must both ship the fingerprint;
    # pin the wiring textually so a refactor cannot drop one leg silently
    src = Path(__file__).resolve().parent.parent.joinpath("minicc", "llm", "openai_provider.py").read_text(encoding="utf8")
    import re
    attach = re.findall(
        r"if isinstance\(response\.usage, dict\):\n\s+response\.usage\.update\(prefix_fingerprint\(outbound, tools\)",
        src,
    )
    assert len(attach) == 2, f"expected the fingerprint on both attempt paths, saw {len(attach)}"
    assert "prefix_fingerprint" in src.split("from .usage import (")[1].split(")")[0], "the import must ride the usage group"
