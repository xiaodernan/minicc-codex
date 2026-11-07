// M8-T565: the frontend must not re-derive facts the backend decided.
//
// `run_finished` always arrives with `phase == "review"` (minicc/agent/loop.py
// emit_trace), so a client-side conditional forcing "review" was a second
// home for a backend decision - and exactly the kind of hand-copied shape
// that silently drops the new answer when the backend changes phase.
// This gate pins that no module under web/src selects a phase from an
// event-code comparison.

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const SRC = "web/src";

// A ternary picking on an event code to *decide a phase* - the shape that
// used to live in toolEventHtml (run_finished -> "review").
const TRIFECTA_RE = /"[a-z_]+"\s*\?\s*"(?:planning|tool|review|verify|repair|execution|permission|intake|summarize)"/;

const files = [];
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walk(full);
    else if (entry.name.endsWith(".js")) files.push(full);
  }
}
await walk(SRC);

const offenders = [];
for (const file of files) {
  const content = await readFile(file, "utf8");
  const match = content.match(TRIFECTA_RE);
  if (match) {
    const line = content.slice(0, content.indexOf(match[0])).split("\n").length;
    offenders.push(`${file}:${line}: ${match[0]}`);
  }
}
assert.deepEqual(
  offenders,
  [],
  "a frontend module selects a phase from an event-code comparison instead of "
    + `asking the backend: ${offenders.join("; ")}`,
);

console.log("M8-T565 ok: the frontend never re-derives the phase from an event code");
