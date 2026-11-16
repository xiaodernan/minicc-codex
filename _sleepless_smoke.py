from pathlib import Path
p = Path("tests/almanac_smoke.mjs")
t = p.read_text(encoding="utf-8")
old = '"oracle"];'
new = '"oracle", "sleepless"];'
assert t.count(old) == 1
t = t.replace(old, new, 1)
# also ensure CHAPTER_MARKERS has sleepless entry
if 'sleepless:' not in t:
    assert '  oracle: ["神谕", "The Oracle"],' in t
    t = t.replace('  oracle: ["神谕", "The Oracle"],',
                  '  oracle: ["神谕", "The Oracle"],\n  sleepless: ["无眠", "The Sleepless"],', 1)
# bump log line
t = t.replace('console.log("almanac smoke passed: 44 chapters', 'console.log("almanac smoke passed: 45 chapters')
p.write_text(t, encoding="utf-8", newline="\n")
print("almanac_smoke: sleepless added; chapters:", t.count('"sleepless"'))
