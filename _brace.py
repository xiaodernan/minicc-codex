from pathlib import Path

raw = Path("web/styles.css").read_text(encoding="utf-8")
open_b = raw.count("{")
close_b = raw.count("}")
print("open:", open_b, "close:", close_b, "delta:", close_b - open_b)

depth = 0
for idx, line in enumerate(raw.splitlines(), 1):
    stripped = line.split("/*")[0]
    for ch in stripped:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                print("NEGATIVE depth at line", idx, repr(line))
                raise SystemExit
print("final depth:", depth)
