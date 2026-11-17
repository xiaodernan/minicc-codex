# -*- coding: utf-8 -*-
"""M8-T1131: CLI bilingual part 2 — argparse help + audit decision reasons + doctor/commands."""
from pathlib import Path

# ---------- doctor.py: read exact bytes ----------
t = Path("minicc/doctor.py").read_text(encoding="utf-8")
import re
for i, line in enumerate(t.splitlines(), 1):
    if re.search(r"[一-鿿]", line):
        print(i, repr(line))
