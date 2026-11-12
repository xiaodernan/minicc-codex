import re, pathlib
from minicc import cli_io

keys = set(cli_io._MESSAGES["zh_cn"])
print("keys in table:", len(keys))
pattern = re.compile(r"""\btr\(\s*["']([A-Za-z0-9_]+)["']""")
used = {}
for path in pathlib.Path("minicc").rglob("*.py"):
    if "__pycache__" in path.parts:
        continue
    for match in pattern.finditer(path.read_text(encoding="utf-8")):
        used.setdefault(match.group(1), []).append(path.as_posix())
print("keys read via tr():", len(used))
unread = sorted(keys - set(used))
print("unread keys (%d): %s" % (len(unread), ", ".join(unread)))
unknown = sorted(set(used) - keys)
print("read but absent from table (%d): %s" % (len(unknown), unknown))
