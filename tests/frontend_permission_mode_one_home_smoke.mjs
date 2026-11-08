// M8-T580: the permission-mode vocabulary has one home in the UI.
//
// The Python backend already owns PERMISSION_MODES (minicc/audit.py,
// gated by tests/test_the_switch_vocabularies_have_one_home.py).
// The UI kept three hand-spelled homes: core/state.js (an inline array in
// the localStorage validation), panels/index.js (an exported array), and
// index.html (the four data-mode radio buttons). The one home for the UI
// is PERMISSION_MODES in web/src/core/state.js; this gate pins:
//
// 1. the home exports the four modes, in the documented order;
// 2. the Python home carries the same four;
// 3. index.html's data-mode buttons appear in the same order;
// 4. no other file under web/src spells the array literal by hand.

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const SRC = "web/src";
const HOME = path.join(SRC, "core", "state.js");
const PYHOME = "minicc/audit.py";
const HTML = "web/index.html";
const PANEL = path.join(SRC, "panels", "index.js");

const EXPECTED = ["default", "plan", "acceptEdits", "yolo"];

// --- the JS home ----------------------------------------------------------
const source = await readFile(HOME, "utf8");
const match = source.match(/export const PERMISSION_MODES = \[([^\]]+)\]/);
assert(match, "core/state.js must export PERMISSION_MODES");
const jsHome = [...match[1].matchAll(/"([a-zA-Z]+)"/g)].map((m) => m[1]);
assert.deepEqual(jsHome, EXPECTED, "the JS home lost its members");

// --- the Python home must carry the same four ------------------------------
const pySource = await readFile(PYHOME, "utf8");
const pyMatch = pySource.match(/PERMISSION_MODES\s*=\s*frozenset\(\{([^}]+)\}\)/);
assert(pyMatch, "minicc/audit.py must define PERMISSION_MODES");
const pyHome = new Set([...pyMatch[1].matchAll(/"([a-zA-Z]+)"/g)].map((m) => m[1]));
assert.deepEqual([...jsHome].sort(), [...pyHome].sort(), "the two homes disagree");

// --- index.html's radio buttons carry the same order -----------------------
const html = await readFile(HTML, "utf8");
const buttons = [...html.matchAll(/data-mode="([a-zA-Za-z]+)"/g)].map((m) => m[1]);
assert.deepEqual(buttons, EXPECTED, "index.html's data-mode buttons drift from the home");

// --- no other file spells the literal --------------------------------------
const literal = /\[\s*"default",\s*"plan",\s*"acceptEdits",\s*"yolo"\s*\]/;
const files = [];
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walk(full);
    else if (entry.name.endsWith(".js") && full !== HOME && full !== PANEL) files.push(full);
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
  `the mode array is hand-spelled outside its one home (${HOME}): ${offenders}`,
);

// --- the panel's surface is a re-export, not a second copy ------------------
const panelSource = await readFile(PANEL, "utf8");
assert(
  !literal.test(panelSource),
  "panels/index.js spells the mode array again instead of re-exporting the home",
);
assert(
  /export\s*\{\s*PERMISSION_MODES\s*\}/.test(panelSource),
  "panels/index.js must re-export PERMISSION_MODES for main.js",
);

console.log(
  "M8-T580 ok: PERMISSION_MODES has one home in the UI (core/state.js), it matches the Python home and the static buttons, and no second copy survives",
);
