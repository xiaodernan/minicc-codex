// M8-T394: the approval decision vocabulary has one frontend home, mirroring
// APPROVAL_DECISIONS in minicc/audit.py.
//
// The approval card used to spell the three data-decision buttons out by
// hand. The server validates every decision against audit.py's frozenset and
// rejects anything else with a ValueError, so a hand-written frontend copy is
// a second contract for the same fact: add a decision on one side and the
// other side either offers a button the server refuses or forgets to offer
// one it accepts. This gate reads the sources, not the DOM, because the
// drift lives in the source.

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

const HOME = path.join(SRC, "core", "approvals.js");
const MEMBERS = ["allow", "always", "deny"];

const homeSource = await readFile(HOME, "utf8");
const block = homeSource.match(/export const APPROVAL_DECISIONS = \[([\s\S]*?)\];/);
assert(block, `${HOME} must export APPROVAL_DECISIONS - the decisions have one home`);
const homeMembers = [...block[1].matchAll(/"([a-z]+)"/g)].map((m) => m[1]);
for (const member of MEMBERS) {
  assert(homeMembers.includes(member), `the one home APPROVAL_DECISIONS is missing ${member}`);
}
assert.equal(homeMembers.length, MEMBERS.length, `the one home grew a fourth decision: ${homeMembers}`);

const offenders = [];
for (const file of files) {
  if (file === HOME) continue;
  const source = await readFile(file, "utf-8");
  for (const match of source.matchAll(/\[[^\]\[]*\]/g)) {
    const text = match[0];
    const members = [...text.matchAll(/"([a-z]+)"/g)].map((m) => m[1]);
    const isTheVocabulary =
      members.length === MEMBERS.length &&
      MEMBERS.every((member) => members.includes(member));
    if (isTheVocabulary) {
      const line = source.slice(0, match.index).split("\n").length;
      offenders.push(`${file}:${line} spells APPROVAL_DECISIONS: ${text}`);
    }
  }
}
assert.deepEqual(
  offenders,
  [],
  "these files write out the approval decisions by hand; the one home is " +
    `APPROVAL_DECISIONS in ${HOME}: ${offenders.join("; ")}`,
);

console.log("M8-T394 ok: the approval decisions have one frontend home");
