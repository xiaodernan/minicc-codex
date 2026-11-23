// M8-T1320: the repo still carries hundreds of `zh() ? "中文" : "English"`
// ternaries that bypass the i18n dictionary. A full migration is a long
// project (the ledger tracks it as a standing boundary), but the count must
// never grow: every new feature must put its copy in the dictionary instead of
// adding one more inline pair.
//
// This is a RATCHET, not a cleanup. It reads web/src from disk, counts the
// inline binary-locale ternaries, and fails if the number exceeds the pinned
// baseline. Lowering the count is always fine; the baseline is then updated
// deliberately alongside the migration that earned it.

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const SRC = "web/src";
const BASELINE = 847;

// Matches `zh() ? "..." : "..."` and `locale === "zh" ? "..." : "..."`
// where BOTH branches are string literals — the shape that hides copy from
// the t("key") dictionary gate. Deliberately narrow: ternaries that choose a
// number, a key, or a computed value are not user-visible copy.
const INLINE = /(?:zh\(\)|locale\s*===\s*"zh")[\s\S]{0,12}\?[\s\S]{0,12}["'][^"'\n]{2,}["'][\s\S]{0,12}:[\s\S]{0,12}["'][^"'\n]{0,}["']/g;

async function scan(dir) {
  let total = 0;
  const byFile = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      const inner = await scan(full);
      total += inner.total;
      byFile.push(...inner.byFile);
      continue;
    }
    if (!entry.name.endsWith(".js")) continue;
    const content = await readFile(full, "utf8");
    const n = (content.match(INLINE) || []).length;
    if (n) {
      total += n;
      byFile.push([full.replace(/\\/g, "/"), n]);
    }
  }
  return { total, byFile };
}

const { total, byFile } = await scan(SRC);
assert.ok(
  total <= BASELINE,
  `inline bilingual ternaries grew ${BASELINE} -> ${total}; put new copy in the dictionary. ` +
  `Top files: ${byFile.sort((a, b) => b[1] - a[1]).slice(0, 5).map(([f, n]) => `${f}=${n}`).join(", ")}`,
);

console.log(`M8-T1320 ok: inline bilingual ternaries ${total} <= baseline ${BASELINE} (ratchet, never grows)`);
