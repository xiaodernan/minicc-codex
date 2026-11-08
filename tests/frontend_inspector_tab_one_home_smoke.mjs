// M8-T592: the inspector-tab vocabulary has one home in the UI.
//
// The three inspector tabs were spelled inline in chat/stream.js's validator,
// hardcoded as data-inspector-tab attributes in web/index.html, and read
// from runtime.inspectorTab seeded in core/state.js - four spellings of
// the same three tokens, none named. The one home is INSPECTOR_TABS in
// core/state.js; this gate pins:
//
// 1. the home exports ["changes", "files", "verification"] in order;
// 2. index.html's data-inspector-tab buttons appear in the same order;
// 3. the runtime default is derived from the home (INSPECTOR_TABS[0]);
// 4. no file under web/src spells the array literal by hand;
// 5. stream.js asks the home (import + includes, no inline literal).

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const SRC = path.join("web", "src");
const HOME = path.join(SRC, "core", "state.js");
const STREAM = path.join(SRC, "chat", "stream.js");
const HTML = path.join("web", "index.html");
const EXPECTED = ["changes", "files", "verification"];

const source = await readFile(HOME, "utf8");
const match = source.match(/export const INSPECTOR_TABS = \[([^\]]+)\]/);
assert(match, "core/state.js must export INSPECTOR_TABS");
const jsHome = [...match[1].matchAll(/"([a-z]+)"/g)].map((m) => m[1]);
assert.deepEqual(jsHome, EXPECTED, "the JS home lost or reordered its members");

const runtimeLine = source.match(/inspectorTab:\s*INSPECTOR_TABS\[0\]/);
assert(runtimeLine, "the runtime default must be derived from the home (INSPECTOR_TABS[0])");

const html = await readFile(HTML, "utf8");
const buttons = [...html.matchAll(/data-inspector-tab="([a-z]+)"/g)].map((m) => m[1]);
assert.deepEqual(buttons, EXPECTED, "index.html's data-inspector-tab buttons drift from the home");

const stream = await readFile(STREAM, "utf8");
assert(
  /import \{[^}]*INSPECTOR_TABS[^}]*\} from "\.\.\/core\/state\.js"/.test(stream),
  "chat/stream.js must import INSPECTOR_TABS",
);
assert(
  !/\[\s*"changes",\s*"files",\s*"verification"\s*\]/.test(stream),
  "chat/stream.js still spells the tab array inline",
);

const literal = /\[\s*"changes",\s*"files",\s*"verification"\s*\]/;
const files = [];
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walk(full);
    else if (entry.name.endsWith(".js") && path.normalize(full) !== path.normalize(HOME)) files.push(full);
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
  `the tab array is hand-spelled outside its one home (${HOME}): ${offenders}`,
);

console.log("M8-T592 ok: INSPECTOR_TABS has one home in the UI (core/state.js); index.html buttons, the runtime default, and stream.js all derive from it");
