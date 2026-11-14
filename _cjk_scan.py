from pathlib import Path
import re

CJK = re.compile(r"[\u4e00-\u9fff]")
# Files expected to carry zh literals by design reference: i18n dict itself,
# cheat-sheet-data, manual, almanac, zh-side is always inside a zh() branch
# or t() key. We flag lines with CJK NOT inside those contexts only as a
# heuristic report; the point is to list files and let a human judge.
for path in sorted(Path("web/src").rglob("*.js")):
    text = path.read_text(encoding="utf-8", errors="replace")
    count = len(CJK.findall(text))
    lines = sum(1 for line in text.splitlines() if CJK.search(line))
    if count:
        print(f"{path.as_posix():60s} cjk={count:4d} lines={lines:4d}")
