// M8-T610: the approval-frame timeout has one home on each face.
//
// The server owns the 60-second wait (minicc/web.py APPROVAL_TIMEOUT_SECONDS)
// and emits ``timeout_seconds`` in its frame; the web face renders the same
// deadline (approvals.js APPROVAL_TIMEOUT_SECONDS). The two faces were
// unpinned and the JS re-spelled the number twice. This gate pins the two
// homes to each other and forbids a bare 60-second literal in the file that
// belongs to the web home.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const HOME = path.join("web", "src", "core", "approvals.js");
const PYHOME = path.join("minicc", "web.py");

const js = await readFile(HOME, "utf8");
const jsMatch = js.match(/export const APPROVAL_TIMEOUT_SECONDS\s*=\s*(\d+(?:\.\d+)?)\s*;/);
assert(jsMatch, "approvals.js must export APPROVAL_TIMEOUT_SECONDS");
const jsValue = jsMatch[1];

const py = await readFile(PYHOME, "utf8");
const pyMatch = py.match(/APPROVAL_TIMEOUT_SECONDS\s*=\s*(\d+(?:\.\d+)?)\s*(?:#|\n)/);
assert(pyMatch, "minicc/web.py must define APPROVAL_TIMEOUT_SECONDS");
const pyValue = pyMatch[1];
assert.equal(Number(jsValue), Number(pyValue), `the two faces disagree: JS = ${jsValue}, Python = ${pyValue}`);

const code = js
  .replace(/\/\/[^\n]*/g, "")
  .replace(/"[^"\n]*"/g, "")
  .split("\n")
  .filter((line) => !/APPROVAL_TIMEOUT_SECONDS\s*=\s*\d/.test(line))
  .join("\n");
assert(
  !/(?<![0-9_])60(?![0-9_])/.test(code),
  "the bare 60 literal reappeared in approvals.js outside its APPROVAL_TIMEOUT_SECONDS constant",
);

console.log("M8-T610 ok: APPROVAL_TIMEOUT_SECONDS has one home on each face (60s) and the two faces agree");
