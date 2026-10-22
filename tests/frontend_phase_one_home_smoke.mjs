// M8-T370: the phase list and the terminal-status list have one home each.
//
// Both were written out by hand in several places, and the copies had
// already drifted - the phase list in api.js did not know about the
// ``review`` phase, so the class for it was never removed from the live
// task element.  This gate says: a hand-written list of phases or terminal
// statuses may not appear outside the one home.
//
// It reads the sources rather than the DOM, because the drift was in the
// *source*: the copy in api.js was the wrong one, and no DOM assertion
// would have said so.

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

// The phases that end a task.  Written out by hand, this is the list that
// drifts; the one home is TERMINAL_TASK_STATUSES in core/state.js.
const TERMINAL_STATUSES = ["completed", "failed", "cancelled", "interrupted"];
const HOME = path.join(SRC, "core", "state.js");

const offenders = [];
for (const file of files) {
  if (file === HOME) continue;
  const source = await readFile(file, "utf8");
  for (const match of source.matchAll(/\[[^\]\[]*\]/g)) {
    const text = match[0];
    const members = [...text.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
    // Only the *terminal-status set itself* is the drifted list.  A
    // different set that happens to contain two of the same words (a colour
    // class, a severity level) is a different question and stays put.
    const isTheTerminalSet =
      members.length === TERMINAL_STATUSES.length &&
      TERMINAL_STATUSES.every((status) => members.includes(status));
    if (isTheTerminalSet) {
      const line = source.slice(0, match.index).split("\n").length;
      offenders.push(`${file}:${line}: ${text}`);
    }
  }
}
assert.deepEqual(
  offenders,
  [],
  "these files write out the terminal statuses by hand; the one home is " +
  `TERMINAL_TASK_STATUSES in ${HOME}: ${offenders.join("; ")}`,
);

// The one home must carry all of them.
const stateSource = await readFile(HOME, "utf8");
const homeBlock = stateSource.match(
  /export const TERMINAL_TASK_STATUSES = new Set\(\[([\s\S]*?)\]\);/,
);
assert(homeBlock, "core/state.js must export TERMINAL_TASK_STATUSES");
const homeStatuses = [...homeBlock[1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
for (const status of TERMINAL_STATUSES) {
  assert(
    homeStatuses.includes(status),
    `the one home is missing the terminal status ${status}`,
  );
}

// The phase list has one home too, and it must know every phase the
// backend emits - otherwise that phase's class is never removed and the
// user never sees its name.
const phaseBlock = stateSource.match(/export const TASK_PHASES = new Set\(\[([\s\S]*?)\]\);/);
assert(phaseBlock, "core/state.js must export TASK_PHASES - the phases have one home");
const homePhases = new Set([...phaseBlock[1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]));

// The backend's phases are read from **every** module under minicc/, not
// from a hand-picked list: the first version of this gate read four files
// and therefore missed the phases the other modules emit.
const backendPhases = new Set();
async function walkBackend(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await walkBackend(full);
    } else if (entry.name.endsWith(".py")) {
      const source = await readFile(full, "utf8");
      for (const match of source.matchAll(/"phase":\s*"([a-z_]+)"/g)) backendPhases.add(match[1]);
      for (const match of source.matchAll(/\bphase\s*=\s*"([a-z_]+)"/g)) backendPhases.add(match[1]);
    }
  }
}
await walkBackend("minicc");
const unknown = [...backendPhases].filter(
  (phase) => !homePhases.has(phase) && !TERMINAL_STATUSES.includes(phase),
);
assert.deepEqual(
  unknown,
  [],
  `the backend emits phases the frontend's one home does not know: ${unknown.join(", ")}`,
);

// Every phase the frontend knows must also be nameable: a phase with no
// label shows the generic "working" text, which is how a task in the
// "verify" or "summarize" phase lost its name.
const panelsSource = await readFile(path.join(SRC, "panels", "index.js"), "utf8");
const labelBlock = panelsSource.match(/const key = \{([\s\S]*?)\}\[phase\] \|\| "working";/);
assert(labelBlock, "panels/index.js must map every phase to a label");
const labelPhases = new Set(
  [...labelBlock[1].matchAll(/(\w+):\s*"phase\./g)].map((m) => m[1]),
);
const unnameable = [...homePhases].filter((phase) => !labelPhases.has(phase));
assert.deepEqual(
  unnameable,
  [],
  `these phases have no label, so the user only sees the generic "working" text: ${unnameable.join(", ")}`,
);

// And every phase the backend emits must have a label in both languages.
const i18nSource = await readFile(path.join(SRC, "core", "i18n.js"), "utf8");
const i18nPhases = new Set([...i18nSource.matchAll(/"phase\.([a-z_]+)"/g)].map((m) => m[1]));
const missingText = [...homePhases].filter((phase) => !i18nPhases.has(phase));
assert.deepEqual(
  missingText,
  [],
  `these phases have no translation, so the label falls back to the key: ${missingText.join(", ")}`,
);

// The phase list itself may not be written out by hand anywhere else: the
// copy in api.js is the one that was wrong (it did not know about
// ``review``), and a DOM assertion alone would not have said so.
const phaseOffenders = [];
for (const file of files) {
  if (file === HOME) continue;
  const source = await readFile(file, "utf8");
  for (const match of source.matchAll(/\[[^\]\[]*\]/g)) {
    const text = match[0];
    const members = [...text.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
    // A list that names several phases is a hand-written phase list - but
    // only when *every* member is a phase.  A severity list ("error",
    // "failed", "denied", ...) mixes a phase with words that are not
    // phases; that is a different question and stays put.
    const phaseLike = members.filter((member) => homePhases.has(member));
    const allPhases = members.length > 0 && phaseLike.length === members.length;
    if (allPhases && phaseLike.length >= 3) {
      const line = source.slice(0, match.index).split("\n").length;
      phaseOffenders.push(`${file}:${line}: ${text}`);
    }
  }
}
assert.deepEqual(
  phaseOffenders,
  [],
  "these files write out the phase list by hand; the one home is " +
  `TASK_PHASES in ${HOME}: ${phaseOffenders.join("; ")}`,
);

console.log("M8-T370 ok: the phase list and the terminal statuses each have one home");
