// M8-T584: the default context budget has one home shared by Python and JS.
//
// minicc/config.py owns DEFAULT_CONTEXT_WINDOW_TOKENS and
// DEFAULT_COMPACT_THRESHOLD (both 300_000 today). The workbench's
// contextWindowTokens placeholder in web/src/core/state.js is the same fact
// for the UI - it pre-seeds the context counter before the backend payload
// hydrates - and it was spelled 300000 by hand. This gate pins the two
// spellings to each other.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const PYHOME = "minicc/config.py";
const JSHOME = "web/src/core/state.js";

const py = await readFile(PYHOME, "utf8");
const pyMatch = py.match(/DEFAULT_CONTEXT_WINDOW_TOKENS\s*=\s*([0-9_]+)/);
assert(pyMatch, "minicc/config.py must define DEFAULT_CONTEXT_WINDOW_TOKENS");
const homeValue = Number(pyMatch[1].replaceAll("_", ""));
assert.ok(Number.isInteger(homeValue) && homeValue > 0, `suspicious home value ${pyMatch[1]}`);

const js = await readFile(JSHOME, "utf8");
const jsMatch = js.match(/contextWindowTokens:\s*([0-9_]+)/);
assert(jsMatch, "core/state.js must seed contextWindowTokens");
const jsValue = Number(jsMatch[1].replaceAll("_", ""));
assert.equal(
  jsValue,
  homeValue,
  `the UI pre-seed (${jsValue}) drifted from the Python home DEFAULT_CONTEXT_WINDOW_TOKENS (${homeValue})`,
);

console.log(`M8-T584 ok: state.js contextWindowTokens matches the Python home (${homeValue})`);
