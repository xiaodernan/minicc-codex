# -*- coding: utf-8 -*-
from pathlib import Path

p = Path("web/src/core/i18n.js")
raw = p.read_bytes()
t = raw.decode("utf-8")
NL = "\r\n"
old_en = '"scroll.title": "Mouse wheel", "scroll.osNote": "Follows the OS scroll direction", "scroll.osHint": "Windows/Linux: scroll down to look down (classic). macOS defaults to natural, trackpad-style. To flip direction, change OS settings — the page no longer hijacks the wheel.",' + NL
new_en = '"scroll.title": "Mouse wheel", "scroll.osNote": "Follows the OS scroll direction", "scroll.osHint": "The page no longer hijacks the wheel — flip it here.", "scroll.natural": "Follow system", "scroll.invert": "Invert wheel", "scroll.invertHint": "Up-scroll scrolls up, down-scroll scrolls down — this app only; takes effect immediately.",' + NL
assert t.count(old_en) == 1
t = t.replace(old_en, new_en, 1)
p.write_bytes(t.encode("utf-8"))
raw = p.read_bytes()
crlf = raw.count(b"\r\n"); lf = raw.count(b"\n") - crlf
print("en keys added; CRLF", crlf, "LF-only", lf)
