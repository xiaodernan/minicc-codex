# -*- coding: utf-8 -*-
from pathlib import Path

p = Path("web/src/core/i18n.js")
raw = p.read_bytes()
t = raw.decode("utf-8")

first = t.find('"scroll.title"')
second = t.find('"scroll.title"', first + 1)
print("zh idx:", first, "en idx:", second)
print("en context:", repr(t[second-60:second+320]))

NL = "\r\n"
old_en = None
i = second
j = t.find(NL, i)
line = t[i:j]
print("en line:", repr(line))
