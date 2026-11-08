"""M8-T528: the CI credential gate must read at least as wide as the product's own redaction table.

The probe used to carry a private three-rule list while the product masks eight
shapes - five product shapes were invisible to CI, the configured-key reader
accepted one of the six spellings the product's own loader accepts, and a scan
over an absent state directory printed the same PASS line as a clean scan over
hundreds of files. These legs bind the gate to the product table, to the
product loader, and to a published disposition that keeps the audit doc's own
illustration text from failing the gate; they also pin that no output line ever
carries matched content.

Every fixture value below is assembled at runtime from innocuous pieces - this
file must not contain a secret-shaped literal, because the repository's own
pre-commit secret hook grades exactly that.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "reliability_probe_under_test", REPO_ROOT / "scripts" / "reliability_probe.py"
)
rp = importlib.util.module_from_spec(_spec)
sys.modules["reliability_probe_under_test"] = rp
_spec.loader.exec_module(rp)

from minicc.config import _parse_env_file  # noqa: E402
from minicc.tools import registry  # noqa: E402


def _marker_name(replacement: str) -> str:
    found = rp._MARKER.search(replacement)
    return found.group(1) if found else "private_key_block"


def _product_shapes() -> list[tuple[str, str]]:
    """(marker-derived rule name, runtime-assembled value) for every product shape."""
    return [
        ("llm_api_key", "sk-" + "x" * 12),
        ("llm_api_key", "sk-" + "x" * 30),
        ("github_token", "ghp_" + "a" * 30),
        ("github_pat", "github_pat_" + "a" * 30),
        ("aws_access_key", "AKIA" + "B" * 16),
        ("bearer_token", "Bearer " + "c" * 20),
        ("url_credentials", "redis://user:" + "d" * 12 + "@db.example.com:6379/0"),
        ("jwt", "eyJ" + "e" * 12 + ".eyJ" + "f" * 12 + "." + "g" * 12),
        ("private_key_block",
         rp._PEM_BANNER + "\n" + "h" * 60 + "\n-----END " + "PR" + "IVATE KEY-----"),
    ]


def test_the_gate_reads_every_rule_the_product_masks() -> None:
    """Each product rule must arrive in the gate under its own marker token,
    with the product's own pattern - a hand-copied table drifts, this cannot."""
    gate = dict(rp.CREDENTIAL_RULES)
    for pattern, replacement in registry._REDACT_RULES:
        name = _marker_name(replacement)
        assert name in gate, f"product rule {name} is invisible to the CI credential gate"
        assert gate[name].pattern == pattern.pattern, (
            f"gate pattern for {name} differs from the product's own"
        )
    assert "pem_banner" in gate, "the gate-only bare-banner rule went away"


def test_every_shape_the_product_masks_the_gate_flags(tmp_path) -> None:
    """Product masks and CI gate flag must hold the same shapes, including the
    eight-to-nineteen character sk- run the old private list could not see."""
    for name, value in _product_shapes():
        matching = [(pat, rep) for pat, rep in registry._REDACT_RULES if pat.search(value)]
        assert matching, f"no product rule matches the {name} shape any more"
        assert _marker_name(matching[0][1]) == name, f"{name} lost its marker binding"
        redacted, changed = registry.redact_text(value)
        assert changed and matching[0][1] in redacted, f"product no longer masks the {name} shape"
    target = tmp_path / "state"
    target.mkdir()
    shapes = _product_shapes() + [("pem_banner", rp._PEM_BANNER)]
    for i, (_name, value) in enumerate(shapes):
        (target / f"s{i}.log").write_text("prefix " + value + " suffix\n", encoding="utf-8")
    leak, published, files_read = rp.scan_credentials([target])
    flagged = {finding.rsplit(": ", 1)[1] for finding in leak}
    assert files_read == len(shapes)
    assert leak and not published
    for name in {name for name, _value in shapes}:
        assert name in flagged, f"gate missed the shape {name}"


def test_the_bare_banner_is_a_gate_extra_the_product_cannot_see() -> None:
    """The product needs a closed block; an unclosed banner is still a leak shape."""
    redacted, changed = registry.redact_text(rp._PEM_BANNER + "\nno end marker here\n")
    assert not changed, "the product unexpectedly masks a bare banner - the extra is redundant now"
    assert any(name == "pem_banner" and pattern.search(rp._PEM_BANNER)
               for name, pattern in rp.CREDENTIAL_RULES)


_ENV_SPELLINGS = [
    "MINICC_API_KEY={v}\n",
    'MINICC_API_KEY="{v}"\n',
    "export MINICC_API_KEY={v}\n",
    "MINICC_API_KEY = {v}\n",
    "  MINICC_API_KEY={v}\n",
    "MINICC_API_KEY={v}  # inline comment\n",
]


def test_the_configured_key_reader_sees_what_the_product_loader_sees(tmp_path) -> None:
    """Six loader spellings, one reader: the gate must not be blinder than the product."""
    value = "door-configured-key-" + "0" * 12
    for i, spelling in enumerate(_ENV_SPELLINGS):
        env = tmp_path / f"env{i}"
        env.write_text(spelling.format(v=value), encoding="utf-8")
        assert _parse_env_file(env).get("MINICC_API_KEY") == value, f"loader itself broke on {spelling!r}"
        assert rp._configured_key(env) == value, f"gate lost the loader spelling {spelling!r}"


def test_a_broken_env_file_disables_the_rule_without_quoting_it(tmp_path, capsys) -> None:
    """A malformed .env must not crash the scan, and the note must not echo the line."""
    env = tmp_path / "env"
    env.write_text(
        "MINICC_API_KEY=" + "z" * 20 + "\n"
        + "this line has no equals sign and carries " + "q" * 10 + "\n",
        encoding="utf-8",
    )
    assert rp._configured_key(env) == ""
    out = capsys.readouterr().out
    assert "ConfigError" in out and "withheld" in out
    assert "q" * 10 not in out, "the note echoed the line the loader refused"


def test_a_value_already_published_in_tracked_files_is_disclosure_not_leak(tmp_path) -> None:
    """The audit doc's own illustration, copied into state, must not fail the gate."""
    value = "Bearer " + "k" * 24
    target = tmp_path / "state"
    target.mkdir()
    (target / "copy.log").write_text("the doc said " + value + " in prose\n", encoding="utf-8")
    leak, published, _files = rp.scan_credentials([target], published_provider=lambda: [value])
    assert leak == [], "a published value was graded as a leak"
    assert len(published) == 1 and published[0].rsplit(": ", 1)[1] == "bearer_token"
    assert value not in published[0], "the finding string carried the matched text"
    leak_bare, published_bare, _files = rp.scan_credentials([target])
    assert leak_bare and not published_bare, "without published knowledge the same bytes must leak"


def test_an_absent_target_is_reported_not_celebrated(capsys) -> None:
    """A scan over zero files must be distinguishable from a clean scan."""
    missing = REPO_ROOT / ".minicc-does-not-exist-m8t528"
    assert not missing.exists()
    code = rp.credential_phase([missing])
    out = capsys.readouterr().out
    assert code == 0, "an absent state directory is a CI fact, not a failure"
    assert "0 file(s) read" in out, "the verdict hid the files-read denominator"
    assert "ABSENT" in out and "read zero files" in out


def test_no_output_carries_the_matched_text(tmp_path, capsys) -> None:
    """A real leak fails the gate by shape and path alone."""
    value = "sk-" + "x" * 28
    target = tmp_path / "state"
    target.mkdir()
    (target / "a.log").write_text("token=" + value + "\n", encoding="utf-8")
    code = rp.credential_phase([target])
    out = capsys.readouterr().out
    assert code == 1, "an un-published leak must fail the gate"
    assert "llm_api_key" in out, "the verdict must name the rule that fired"
    assert value not in out, "the output carried the matched text"
