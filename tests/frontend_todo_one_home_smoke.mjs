// M8-T384: the todo checklist's status and priority vocabularies each have
// one home on the frontend, mirroring TODO_STATUSES / TODO_PRIORITIES in
// minicc/tools/todo.py.
//
// The panel's normalizer used to spell both lists out by hand.  The backend
// validates every entry against todo.py's tuples and the tool schema
// advertises exactly those, so a hand-written frontend copy is a second
// contract for the same fact: add a status on one side and the other side
// silently coerces it to "pending".  This gate reads the sources, not the
// DOM, because the drift lives in the source.

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const SRC = "web/src";
const files = [];
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walk(full);
    else if (entry.name.endsWith(".js")) files.push(full);
  }
}
await walk(SRC);

const HOME = path.join(SRC, "core", "state.js");
const VOCABULARIES = {
  TODO_STATUSES: ["pending", "in_progress", "completed"],
  TODO_PRIORITIES: ["high", "medium", "low"],
};

const homeSource = await readFile(HOME, "utf8");
for (const [name, members] of Object.entries(VOCABULARIES)) {
  const block = homeSource.match(new RegExp(`export const ${name} = new Set\\(\\[([\\s\\S]*?)\\]\\);`));
  assert(block, `${HOME} must export ${name} - the todo vocabularies have one home`);
  const homeMembers = [...block[1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
  for (const member of members) {
    assert(homeMembers.includes(member), `the one home ${name} is missing ${member}`);
  }
}

const offenders = [];
for (const file of files) {
  if (file === HOME) continue;
  const source = await readFile(file, "utf8");
  for (const match of source.matchAll(/\[[^\]\[]*\]/g)) {
    const text = match[0];
    const members = [...text.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
    for (const [name, expected] of Object.entries(VOCABULARIES)) {
      const isTheVocabulary =
        members.length === expected.length &&
        expected.every((member) => members.includes(member));
      if (isTheVocabulary) {
        const line = source.slice(0, match.index).split("\n").length;
        offenders.push(`${file}:${line} spells ${name}: ${text}`);
      }
    }
  }
}
assert.deepEqual(
  offenders,
  [],
  "these files write out a todo vocabulary by hand; the one home is " +
  `TODO_STATUSES / TODO_PRIORITIES in ${HOME}: ${offenders.join("; ")}`,
);

console.log("M8-T384 ok: the todo statuses and priorities each have one frontend home");
