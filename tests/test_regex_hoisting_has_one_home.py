"""M8-T835: hot-path regexes compile once, not per call.

Two lexers ran ``re.compile`` inside their function bodies: impact's JS token
lexer (called per scanned module) and the fake provider's completion-judge
marker matcher (called per judge turn in tests). Hoisting them to module
constants keeps the pattern identical and makes the compile a one-time cost;
this gate fails if either constant goes back inside a function body.
"""

from __future__ import annotations

import re

from minicc import impact as impact_module
from minicc.llm import fake as fake_module


def test_impact_lexer_is_compiled_at_module_import() -> None:
    pattern = getattr(impact_module, "_JS_LEXER_RE", None)
    assert pattern is not None, "impact._JS_LEXER_RE must exist at module import time"
    assert isinstance(pattern, re.Pattern)
    tokens = impact_module._js_tokens("import x from './mod.js'; // comment\nfrom './other.js'")
    assert tokens, "the hoisted lexer must still tokenize JS import text"


def test_fake_marker_is_compiled_at_module_import() -> None:
    pattern = getattr(fake_module, "_CITABLE_EVIDENCE_MARKER", None)
    assert pattern is not None, "fake._CITABLE_EVIDENCE_MARKER must exist at module import time"
    assert isinstance(pattern, re.Pattern)
    assert pattern.search("执行证据（event-1）：\n") is not None
