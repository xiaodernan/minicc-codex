# -*- coding: utf-8 -*-
text = open("web/src/core/i18n.js", encoding="utf-8").read()
for k in ['"scroll.title"', '"scroll.osNote"', '"scroll.osHint"']:
    i = text.find(k)
    print(k, "->", "found" if i != -1 else "MISSING")
    if i != -1:
        print("   ", repr(text[i:i+190]))
