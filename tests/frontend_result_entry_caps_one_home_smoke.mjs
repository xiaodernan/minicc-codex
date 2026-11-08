// M8-T598: the two per-turn entry caps have one home each side.
//
// The backend bounds two per-binding lists at 64: usage_by_turn
// (MAX_RESULT_USAGE_ENTRIES) and compaction_events
// (MAX_RESULT_COMPACTION_ENTRIES) - both declared in minicc/agent/loop.py
// and kept as the two names because they bound different facts at the
// same width. The frontend reducer keeps the same two lists for the
// rendering binding with a bare .slice(-64) - a hand-copy that could
// silently fall out of step.
//
// The reducer cannot import Python, so this gate reads the Python home
// and pins:
//
// 1. loop.py declares both constants, both with the same value (64);
// 2. the reducer spells .slice(-64) exactly twice, only on the
//    usage_by_turn and compaction_events lines;
// 3. no other web/src .js file spells a .slice(-64).

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const REDUCER = path.join("web", "src", "core", "task-reducer.js");
const PYLOOP = path.join("minicc", "agent", "loop.py");

const py = await readFile(PYLOOP, "utf8");
const usage = py.match(/MAX_RESULT_USAGE_ENTRIES\s*=\s*(\d+)/);
const compaction = py.match(/MAX_RESULT_COMPACTION_ENTRIES\s*=\s*(\d+)/);
assert(usage, "loop.py must declare MAX_RESULT_USAGE_ENTRIES");
assert(compaction, "loop.py must declare MAX_RESULT_COMPACTION_ENTRIES");
assert.equal(Number(usage[1]), Number(compaction[1]), "the two homes disagree - they must both name 64 today");

const reducer = await readFile(REDUCER, "utf8");
const lines = reducer.split("\n");
const slice64 = lines
  .map((line, index) => [index + 1, line])
  .filter(([, line]) => line.includes(".slice(-64)"));
assert.equal(slice64.length, 2, `expected exactly 2 .slice(-64) sites, found ${slice64.length}`);
for (const [lineno, line] of slice64) {
  assert(
    line.includes("usage_by_turn") || line.includes("compaction_events"),
    `line ${lineno}: .slice(-64) on an unexpected entry: ${line.trim()}`,
  );
}

const SRC = path.join("web", "src");
const offenders = [];
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walk(full);
    else if (entry.name.endsWith(".js") && full !== REDUCER) {
      const content = await readFile(full, "utf8");
      if (content.includes(".slice(-64)")) offenders.push(full);
    }
  }
}
await walk(SRC);
assert.deepEqual(offenders, [], `the 64 entry cap is spelled elsewhere under web/src: ${offenders}`);

console.log(`M8-T598 ok: both 64 entry caps (usage_by_turn=${usage[1]}, compaction_events=${compaction[1]}) are asked by name in the Python home and pinned in the reducer; nothing else spells them`);
