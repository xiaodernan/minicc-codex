"""M8-T827 — web/styles.css is one encoding, and the build refuses anything else.

A real shipped defect: T781/T814's glassmorphism section was appended with
PowerShell ``WriteAllText`` (UTF-16 by default) onto an otherwise UTF-8 file.
``readFileSync(path, "utf8")`` silently replaced all 13,413 NUL bytes with
U+FFFD, esbuild minified the replacements, and the CSS bundle served garbage
for the entire enhancement — yet ``npm run check:web`` stayed green because the
garbage was byte-stable. The prettiness was written but never actually rendered.

Three cells, each a different guard:

* the source stylesheet is valid UTF-8 with no NUL and no U+FFFD;
* every content-hashed bundle the manifest ships is too (the corruption used to
  survive into the artifact);
* the build script actively rejects mixed encoding, so a future bad append
  fails ``npm run build`` / ``check:web`` instead of shipping silently.

All three are offline, dependency-free file reads — they run in every job,
including the Python-only ones that do not ``npm ci``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "web"
STYLE_SOURCE = WEB / "styles.css"
MANIFEST = WEB / "asset-manifest.json"
ASSETS = WEB / "assets"
BUILD_SCRIPT = REPO / "scripts" / "build-web.mjs"

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _read_utf8_strict(path: Path) -> tuple[bytes, str]:
    """Return (raw_bytes, text), failing loudly on broken encoding."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")  # raises UnicodeDecodeError on mixed UTF-16
    return raw, text


def test_every_source_stylesheet_is_pure_utf8() -> None:
    # Not just styles.css: web/index.html links styles-enhancements.css too, and
    # a bad append to either would silently break that whole sheet in browsers.
    sheets = sorted(WEB.glob("*.css")) + sorted((WEB / "vendor").glob("*.css"))
    assert STYLE_SOURCE in sheets
    for sheet in sheets:
        raw, text = _read_utf8_strict(sheet)
        assert 0 not in raw, f"{sheet.name}: a NUL byte means UTF-16 was appended to a UTF-8 file"
        assert "\ufffd" not in text, f"{sheet.name}: U+FFFD means invalid UTF-8 was silently replaced"
    # The shipped enhancement must actually be present as readable text, not
    # replacement characters — this is what a broken append used to hide.
    main_text = STYLE_SOURCE.read_text("utf-8")
    assert "glassmorphism" in main_text.lower()
    assert ".toast" in main_text
    # Balanced braces is a cheap sanity check that a whole section was not lost.
    assert main_text.count("{") == main_text.count("}")


def test_no_shipped_bundle_carries_replacement_characters() -> None:
    manifest = json.loads(MANIFEST.read_text("utf-8"))
    referenced = manifest.values()
    asserted = 0
    for logical in referenced:
        path = WEB / logical.lstrip("/")
        raw, text = _read_utf8_strict(path)
        assert 0 not in raw, f"{path} ships a NUL byte"
        assert "\ufffd" not in text, f"{path} ships U+FFFD (broken encoding reached the artifact)"
        asserted += 1
    assert asserted >= 3, "expected the app, game and styles bundles in the manifest"


def test_the_build_script_rejects_mixed_encoding() -> None:
    source = BUILD_SCRIPT.read_text("utf-8")
    assert "assertUtf8Text" in source, "the build must own the encoding guard"
    assert "NUL byte" in source
    assert "fatal: true" in source or "TextDecoder" in source, (
        "the guard must fail on invalid UTF-8, not silently replace it"
    )
    # The stylesheet must actually go through the guard, not just define it.
    assert "assertUtf8Text(join(outDir, \"styles.css\"))" in source
