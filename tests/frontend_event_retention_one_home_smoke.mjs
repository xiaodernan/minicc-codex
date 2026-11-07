// M8-T585: the event-retention and session-view caps each have one home.
//
// Two numbers, two facts, several hand spellings:
//
//   2048    - how many event identities a binding remembers (dedup
//             sets in task-reducer.js) and how many recent timeline
//             events are kept (task-reducer.js), plus the panels-side
//             seen-event-keys tracker (state.js MAX_SEEN_EVENT_KEYS);
//   180_000 - the per-session markup size cap, applied identically by
//             the localStorage persistence path and the DOM render path
//             (session-cache.js and state.js spelled it separately).
//
// The homes: MAX_SEEN_EVENT_KEYS in web/src/core/bounded-cache.js,
// MAX_SESSION_VIEW_CHARS in web/src/core/session-cache.js. state.js
// re-exports both for existing importers. finalizedTaskIds' own 2048
// (web/src/core/state.js) bounds finalized task identities, not events,
// and is intentionally NOT folded into the home - it is the one allowed
// bare spelling in web/src.

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const SRC = path.join("web", "src");
const BOUNDED = path.join(SRC, "core", "bounded-cache.js");
const SESSION = path.join(SRC, "core", "session-cache.js");
const STATE = path.join(SRC, "core", "state.js");
const REDUCER = path.join(SRC, "core", "task-reducer.js");

const bounded = await readFile(BOUNDED, "utf8");
assert.match(bounded, /export const MAX_SEEN_EVENT_KEYS = 2048;/, "bounded-cache.js must own MAX_SEEN_EVENT_KEYS");

const session = await readFile(SESSION, "utf8");
assert.match(session, /export const MAX_SESSION_VIEW_CHARS = 180_000;/, "session-cache.js must own MAX_SESSION_VIEW_CHARS");

const state = await readFile(STATE, "utf8");
assert.match(state, /export \{ MAX_SEEN_EVENT_KEYS \} from "\.\/bounded-cache\.js";/, "state.js must re-export the event-key home");
assert.match(state, /export \{ MAX_SESSION_VIEW_CHARS \} from "\.\/session-cache\.js";/, "state.js must re-export the session-view cap home");

const eventOffenders = [];
const viewOffenders = [];
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walk(full);
    else if (entry.name.endsWith(".js")) files.push(full);
  }
}
const files = [];
await walk(SRC);
for (const file of files) {
  const content = await readFile(file, "utf8");
  const lines = content.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.trim().startsWith("//")) continue; // comments are not references
    if (/(?<![0-9_])2048(?![0-9_])/.test(line)) {
      const allowed =
        (file === BOUNDED && /MAX_SEEN_EVENT_KEYS = 2048/.test(line))
        || (file === STATE && /BoundedSet\(2048\)/.test(line));
      if (!allowed) eventOffenders.push(`${file}:${index + 1}: ${line.trim()}`);
    }
    if (/(?<![0-9_])180_000(?![0-9_])|(?<![0-9_])180000(?![0-9_])/.test(line)) {
      const allowed = file === SESSION && /MAX_SESSION_VIEW_CHARS = 180_000/.test(line);
      if (!allowed) viewOffenders.push(`${file}:${index + 1}: ${line.trim()}`);
    }
  }
}
assert.deepEqual(eventOffenders, [], `the 2048 retention cap is spelled outside its home: ${eventOffenders}`);
assert.deepEqual(viewOffenders, [], `the 180_000 session-view cap is spelled outside its home: ${viewOffenders}`);

// the reducer asks the home, not a local constant
const reducer = await readFile(REDUCER, "utf8");
assert(!/(?<![0-9_])2048(?![0-9_])/.test(reducer), "task-reducer.js must ask MAX_SEEN_EVENT_KEYS, not spell 2048");

console.log("M8-T585 ok: the event-retention and session-view caps each have one home; state.js re-exports; the one allowed bare 2048 is finalizedTaskIds' own bound");
