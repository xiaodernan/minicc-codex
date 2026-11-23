// M8-T564: the i18n dictionary is one fact in two languages.
//
// Every user-visible sentence comes through ``t(key)``.  The two locale
// blocks were allowed to drift independently, and the drift reached the
// screen: four ``game.*`` keys existed only in zh, so English players
// stared at raw keys (``t()`` falls back to the key itself).
//
// This gate pins:
//   1. zh and en carry exactly the same key set;
//   2. neither dictionary repeats a key (object literals silently drop);
//   3. every literal ``t("...")`` key referenced anywhere under web/src
//      has a translation in both languages.
//
// It reads the sources, not the DOM.

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const SRC = "web/src";
const HOME = path.join(SRC, "core", "i18n.js");
const text = await readFile(HOME, "utf8");

const zhStart = text.indexOf("  zh: {");
const enStart = text.indexOf("  en: {");
const end = text.lastIndexOf("};");
assert(zhStart !== -1 && enStart !== -1 && end > enStart, "i18n.js must hold zh:/en: blocks");

// Keys look like ``foo.bar`` or "quoted.key" at the start of an entry; the
// t() fallback to the raw key means every referenced name must exist.
const KEY_RE = /(?:^|[,\n{])\s*(?:"([^"]+)"|([A-Za-z_$][\w.-]*))\s*:/g;

function keysOf(block) {
  const out = [];
  for (const match of block.matchAll(KEY_RE)) out.push(match[1] ?? match[2]);
  return out;
}

const zh = keysOf(text.slice(zhStart, enStart));
const en = keysOf(text.slice(enStart, end));
const zhSet = new Set(zh.filter((k) => k !== "zh"));
const enSet = new Set(en.filter((k) => k !== "en"));

const onlyZh = [...zhSet].filter((k) => !enSet.has(k)).sort();
const onlyEn = [...enSet].filter((k) => !zhSet.has(k)).sort();
assert.deepEqual(onlyZh, [], `missing from en (English players see the raw key): ${onlyZh.join(", ")}`);
assert.deepEqual(onlyEn, [], `missing from zh (Chinese players see the raw key): ${onlyEn.join(", ")}`);

const dupZh = zh.filter((k, i) => zh.indexOf(k) !== i && k !== "zh");
const dupEn = en.filter((k, i) => en.indexOf(k) !== i && k !== "en");
assert.deepEqual([...new Set(dupZh)], [], `the zh dictionary repeats keys: ${[...new Set(dupZh)]}`);
assert.deepEqual([...new Set(dupEn)], [], `the en dictionary repeats keys: ${[...new Set(dupEn)]}`);

// Every literal t("key") reference must exist in both dictionaries.
const referenced = new Map();
// M8-T1314: atlas (and future callers) pass a DYNAMIC key to t() from a
// *_KEYS constant array, e.g. t(MILESTONE_KEYS[index], params). The literal
// regex cannot see those keys, so four milestone sentences could vanish from
// one locale unnoticed. Any string literal inside a `const NAME_KEYS=[...]`
// array is a declared i18n key and must exist in both dictionaries too.
const dynamicKeys = new Map();
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await walk(full);
      continue;
    }
    if (!entry.name.endsWith(".js")) continue;
    const content = await readFile(full, "utf8");
    // M8-T1311: t() now takes an optional params object. Interpolated call
    // sites must still be checked for a real key in both dictionaries — a
    // two-arg call must not slip past the gate just because its text changed.
    for (const match of content.matchAll(/\bt\(\s*"([A-Za-z0-9_.-]+)"\s*(?:,\s*\{[^}]*\})?\s*\)/g)) {
      if (!referenced.has(match[1])) referenced.set(match[1], full);
    }
    for (const decl of content.matchAll(/\bconst\s+[A-Z][A-Z0-9_]*_KEYS\s*=\s*\[([\s\S]*?)\]/g)) {
      for (const lit of decl[1].matchAll(/"([A-Za-z0-9_.-]+)"/g)) {
        if (!dynamicKeys.has(lit[1])) dynamicKeys.set(lit[1], full);
      }
    }
  }
}
await walk(SRC);
for (const [key, file] of dynamicKeys) {
  if (!referenced.has(key)) referenced.set(key, `${file} (*_KEYS array)`);
}

const missing = [];
for (const [key, file] of referenced) {
  if (!zhSet.has(key) || !enSet.has(key)) missing.push(`${key} (referenced at ${file})`);
}
assert.deepEqual(
  missing.sort(),
  [],
  `t() references keys that have no translation: ${missing.join(", ")}`,
);

console.log(`M8-T564 ok: zh/en carry the same ${zhSet.size} keys; ${referenced.size} t() references (${dynamicKeys.size} from *_KEYS arrays) all resolve`);
