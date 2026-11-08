// M8-T603: the task-event kinds have one home shared by Python and JS.
//
// The backend emits task-event kinds (TASK_EVENT_KINDS in
// minicc/agent/protocol.py); the web face's reducer switches on the same
// eight. The two were hand-kept copies of one fact - and the reducer had
// no default arm, so a kind minted on one side and not spelled on the other
// vanished silently in the UI.
//
// This gate pins the cross-language contract:
//
// 1. the Python home defines exactly the eight kinds;
// 2. the reducer's case arms are exactly the home's set;
// 3. no other web/src file carries a case arm for any of the eight
//    (the reducer is the only switch on the wire vocabulary).

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const SRC = path.join("web", "src");
const REDUCER = path.join(SRC, "core", "task-reducer.js");
const PYHOME = path.join("minicc", "agent", "protocol.py");
const KINDS = ["timeline", "stream_delta", "state", "status", "usage", "context", "compaction", "result"];

const py = await readFile(PYHOME, "utf8");
const pyMatch = py.match(/TASK_EVENT_KINDS\s*=\s*frozenset\(\{([^}]+)\}\)/);
assert(pyMatch, "minicc/agent/protocol.py must define TASK_EVENT_KINDS");
const pyHome = [...pyMatch[1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
assert.deepEqual(
  [...pyHome].sort(),
  [...KINDS].sort(),
  `the Python home drifted: expected ${[...KINDS].sort()}, got ${[...pyHome].sort()}`,
);

const reducer = await readFile(REDUCER, "utf8");
const arms = [...reducer.matchAll(/case\s+"([a-z_]+)":/g)].map((m) => m[1]);
assert.deepEqual(
  [...new Set(arms)].sort(),
  [...KINDS].sort(),
  `the reducer's arms drifted from the Python home: got ${[...new Set(arms)].sort()}`,
);

const offenders = [];
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walk(full);
    else if (entry.name.endsWith(".js") && path.normalize(full) !== path.normalize(REDUCER)) {
      const content = await readFile(full, "utf8");
      for (const kind of KINDS) {
        if (new RegExp(`case\\s+"${kind}":`).test(content)) offenders.push(`${full}: case "${kind}"`);
      }
    }
  }
}
await walk(SRC);
assert.deepEqual(
  offenders,
  [],
  `the reducer is the only switch allowed to carry the wire vocabulary; these files spell a case arm too: ${offenders}`,
);

console.log("M8-T603 ok: TASK_EVENT_KINDS has one home shared by the Python runtime and the JS reducer; the eight kinds match on both faces and no second switch spells them");
