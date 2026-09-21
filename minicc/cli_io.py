"""The only stdout writer in ``minicc/`` (M8-T5).

Diagnostics belong in ``logging`` (see :mod:`minicc.logging_setup`), user-facing
CLI/REPL lines belong here. Keeping one call site for ``print`` means the
terminal protocol stays on stdout while every other message can be redirected,
leveled and redacted.
"""

from __future__ import annotations

import sys
from typing import Any

__all__ = ["cli_out"]


def cli_out(*parts: Any, file: Any = None, sep: str = " ", end: str = "\n") -> None:
    print(*parts, sep=sep, end=end, file=file or sys.stdout, flush=True)
