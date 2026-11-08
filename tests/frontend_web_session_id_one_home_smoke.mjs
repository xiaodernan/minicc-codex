// M8-T582: the web face's default session id has one home.
//
// ``"web-latest"`` is the session id a task rides when nobody named one.
// It was spelled by hand in the TaskRequest dataclass default, the payload
// fallback, the worker's argv default, web.py's two readers, markdown.js's
// two render-time fallbacks and a test fixture - six Python spellings plus
// two JS spellings, none named. The Python home is ``WEB_SESSION_ID`` in
// minicc/task_contract.py; the JS face cannot import Python, so its two
// literals stay inline and this gate pins them to the home, and pins:
//
// 1. the Python home defines WEB_SESSION_ID with that exact value;
// 2. no other file under minicc/ spells the literal at all;
// 3. web/src/chat/markdown.js carries the literal exactly twice;
// 4. no other web/src .js file spells it.

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const PYHOME = "minicc/task_contract.py";
const JSHOME = path.join("web", "src", "chat", "markdown.js");
const SRC = path.join("web", "src");
const PACKAGE = "minicc";
const LITERAL = "web-latest";

// --- the Python home carries the value -------------------------------------
const py = await readFile(PYHOME, "utf8");
const pyMatch = py.match(/WEB_SESSION_ID\s*=\s*"([^"]+)"/);
assert(pyMatch, "minicc/task_contract.py must define WEB_SESSION_ID");
assert.deepEqual(pyMatch[1], LITERAL, "WEB_SESSION_ID drifted from the documented value");

// --- no other Python file spells the literal --------------------------------
const pyOffenders = [];
async function walkPy(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walkPy(full);
    else if (entry.name.endsWith(".py") && full !== path.normalize(PYHOME)) {
      const content = await readFile(full, "utf8");
      if (content.includes(LITERAL)) pyOffenders.push(full);
    }
  }
}
await walkPy(PACKAGE);
assert.deepEqual(
  pyOffenders,
  [],
  `the session-id literal is spelled outside its home (${PYHOME}): ${pyOffenders}`,
);

// --- the JS face carries exactly the two inline literals --------------------
const md = await readFile(JSHOME, "utf8");
const jsCount = md.split(LITERAL).length - 1;
assert.equal(jsCount, 2, `markdown.js must carry exactly 2 inline "${LITERAL}" fallbacks, found ${jsCount}`);

const jsOffenders = [];
async function walkJs(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walkJs(full);
    else if (entry.name.endsWith(".js") && path.normalize(full) !== path.normalize(JSHOME)) {
      const content = await readFile(full, "utf8");
      if (content.includes(LITERAL)) jsOffenders.push(full);
    }
  }
}
await walkJs(SRC);
assert.deepEqual(
  jsOffenders,
  [],
  `the session-id literal is spelled outside markdown.js under web/src: ${jsOffenders}`,
);

console.log(`M8-T582 ok: WEB_SESSION_ID has one home (${PYHOME}); the JS face's two literals match it and no other file spells it`);
