"""M8-T604 — the six Chinese reasoning-effort labels spell once across faces.

The CLI's reasoning trace (minicc/agent/loop.py, inline dict) and the UI's
zh i18n labels (web/src/core/i18n.js, ``reasoning.*``) both answer one
question — what each of the six reasoning efforts is *called in Chinese* —
and each spelled it inline. Nothing pinned the two spellings together; they
were identical **by accident of history**. Flip one Chinese word on either
face and every test would stay green, because nothing on either side reads
the other face.

This gate pins:

* the inline effort-label dict in loop.py, and the ``reasoning.*`` keys in
  i18n.js's zh column, carry exactly the same six labels, byte-identical.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOOP = REPO / "minicc" / "agent" / "loop.py"
I18N = REPO / "web" / "src" / "core" / "i18n.js"


def _effort_labels_python() -> dict[str, str]:
    source = LOOP.read_text(encoding="utf-8")
    match = re.search(r"effort_label = \{([^}]+)\}", source)
    assert match, "the inline effort_label dict in minicc/agent/loop.py was not found"
    return dict(re.findall(r'"([a-z]+)": "([^"]+)"', match.group(1)))


def _i18n_zh_reasoning() -> dict[str, str]:
    source = I18N.read_text(encoding="utf-8")
    keys = ("low", "mid", "high", "xhigh", "max", "ultra")
    out: dict[str, str] = {}
    for key in keys:
        match = re.search(rf'"{re.escape("reasoning." + key)}": "([^"]+)"', source)
        assert match, f"i18n.js does not declare a reasoning.{key} label"
        out[key] = match.group(1)
    return out


def test_the_effort_labels_match_across_the_two_faces() -> None:
    python_labels = _effort_labels_python()
    i18n_labels = _i18n_zh_reasoning()
    assert python_labels.keys() == i18n_labels.keys(), (
        f"the two faces enumerate different efforts: python {sorted(python_labels)}, "
        f"i18n {sorted(i18n_labels)}"
    )
    drifted = [key for key in python_labels if python_labels[key] != i18n_labels.get(key)]
    assert drifted == [], (
        "the two faces spell the same Chinese label differently for "
        + ", ".join(f"{key}: python={python_labels[key]!r} vs i18n={i18n_labels[key]!r}" for key in drifted)
    )


def test_python_face_covers_the_home() -> None:
    from minicc.config import REASONING_EFFORTS

    python_labels = _effort_labels_python()
    assert set(python_labels) == set(REASONING_EFFORTS)
