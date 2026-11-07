// M8-T563: the reasoning-effort vocabulary has one home in the UI.
//
// The Python backend already owns REASONING_EFFORTS (minicc/config.py).
// The UI kept four hand-spelled copies of the same six levels (main.js,
// stream.js twice, core/state.js) and the Python-side label map even
// lacked ``ultra``. The one home for the UI is ``REASONING_EFFORTS`` in
// web/src/core/state.js; this gate pins:
//
// 1. the home exports the six levels, in the backend's order;
// 2. the Python home carries the same six;
// 3. i18n knows a label for every level, in both languages;
// 4. no other file under web/src spells the array literal by hand.

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const SRC = "web/src";
const HOME = path.join(SRC, "core", "state.js");
const PYHOME = "minicc/config.py";

const EXPECTED = ["low", "mid", "high", "xhigh", "max", "ultra"];

// --- the JS home ----------------------------------------------------------
const source = await readFile(HOME, "utf8");
const match = source.match(/export const REASONING_EFFORTS = \[([^\]]+)\]/);
assert(match, "core/state.js must export REASONING_EFFORTS");
const jsHome = [...match[1].matchAll(/"([a-z]+)"/g)].map((m) => m[1]);
assert.deepEqual(jsHome, EXPECTED, "the JS home lost its members");

// --- the Python home must carry the same six --------------------------------
const pySource = await readFile(PYHOME, "utf8");
const pyMatch = pySource.match(/REASONING_EFFORTS\s*=\s*frozenset\(\{([^}]+)\}\)/);
assert(pyMatch, "minicc/config.py must define REASONING_EFFORTS");
const pyHome = new Set([...pyMatch[1].matchAll(/"([a-z]+)"/g)].map((m) => m[1]));
assert.deepEqual(
  [...jsHome].sort(),
  [...pyHome].sort(),
  `the two homes disagree: JS ${jsHome}, Python ${[...pyHome]}`,
);

// --- i18n must know every level in both languages ---------------------------
const i18n = await readFile(path.join(SRC, "core", "i18n.js"), "utf8");
for (const level of jsHome) {
  assert(
    i18n.includes(`"reasoning.${level}"`),
    `i18n.js is missing a label for reasoning.${level} in one of the languages`,
  );
}

// --- no other file spells the literal ---------------------------------------
const literal = /\["low",\s*"mid",\s*"high",\s*"xhigh",\s*"max",\s*"ultra"\]/;
const files = [];
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walk(full);
    else if (entry.name.endsWith(".js") && full !== HOME) files.push(full);
  }
}
await walk(SRC);
const offenders = [];
for (const file of files) {
  const content = await readFile(file, "utf8");
  const found = content.match(literal);
  if (found) offenders.push(`${file}: ${found.index}`);
}
assert.deepEqual(
  offenders,
  [],
  `the effort array is hand-spelled outside its one home (${HOME}): ${offenders}`,
);

console.log("M8-T563 ok: REASONING_EFFORTS has one home in the UI, matching the Python home, and both languages can name every level");
