// M8-T556: the timeline chip has a name for every code the backend can mint.
//
// The trace timeline renders every event with ``traceLabel(event)``, and an
// unknown code silently falls back to "阶段事件"/"Stage event" - an anonymous
// chip.  The phase gate (M8-T370) already pins the same fact for phases;
// this gate pins it for event codes:
//
// 1. every code the backend mints (scanned from ``minicc/**/*.py``, plus the
//    handful of dynamic emission sites listed below) has a label in both
//    languages;
// 2. the zh and en label maps carry exactly the same key set;
// 3. every label is minted somewhere or is the frontend's own synthetic
//    code - no dead labels;
// 4. the map is spelled in exactly one place: ``web/src/panels/index.js``
//    - a hand-written copy next to it is a second home.
//
// It reads the sources, not the DOM, because the drift was in the source.

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const SRC = "web/src";
const HOME = path.join(SRC, "panels", "index.js");
const PACKAGES = "minicc";

// Dynamic emission sites that a literal scan cannot see.  Each entry names
// the site that mints the code so the list can be checked against reality:
//   minicc/task_manager.py  code=f"completion_{decision.status}" (4 statuses)
//   minicc/agent/verifier.py  status-to-code map (lines ~90)
//   minicc/task_manager.py  code=recovery_mode (3 values)
//   minicc/task_manager.py  auto_orchestration_triggered / batch_started
//   minicc/agent/loop.py  (literal codes are picked up by the scan)
const EXTRA_DYNAMIC = [
  "completion_complete",
  "completion_continue",
  "completion_blocked",
  "completion_unknown",
  "verification_passed",
  "verification_failed",
  "verification_skipped",
  "verification_blocked",
  "session_checkpoint",
  "safe_readonly_checkpoint",
  "reinspect_required",
  "auto_orchestration_triggered",
  "batch_started",
];

// The one code the frontend mints itself (compactModelUpdateEvents folds
// earlier model_update events into a single history entry).
const FRONTEND_ONLY = ["model_update_history"];

// --- collect the backend vocabulary ------------------------------------------
const minted = new Set(EXTRA_DYNAMIC);
async function walkBackend(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await walkBackend(full);
      continue;
    }
    if (!entry.name.endsWith(".py")) continue;
    const source = await readFile(full, "utf8");
    for (const match of source.matchAll(/code=\s*["']([a-z_0-9]+)["']/g)) {
      minted.add(match[1]);
    }
    for (const match of source.matchAll(/["']code["']\s*:\s*["']([a-z_0-9]+)["']/g)) {
      minted.add(match[1]);
    }
  }
}
await walkBackend(PACKAGES);

// --- read the home -----------------------------------------------------------
const source = await readFile(HOME, "utf8");
const maps = source.match(
  /const labels = state\.locale === "zh"\s*\n\s*\?\s*\{([\s\S]*?)\}\s*\n\s*:\s*\{([\s\S]*?)\};/,
);
assert(maps, "panels/index.js must hold the zh/en label maps in traceLabel");

function keysOf(block) {
  return [...block.matchAll(/(\w+):\s*"/g)].map((match) => match[1]);
}
const zh = keysOf(maps[1]);
const en = keysOf(maps[2]);
const zhSet = new Set(zh);
const enSet = new Set(en);

// 1. every minted code has a name in both languages
const missing = [...minted].filter((code) => !zhSet.has(code) || !enSet.has(code)).sort();
assert.deepEqual(
  missing,
  [],
  `these backend codes have no name, so the timeline chip reads as "阶段事件": ${missing.join(", ")}`,
);

// 2. zh and en carry exactly the same keys
const onlyZh = [...zhSet].filter((code) => !enSet.has(code)).sort();
const onlyEn = [...enSet].filter((code) => !zhSet.has(code)).sort();
assert.deepEqual(onlyZh, [], `named only in zh: ${onlyZh.join(", ")}`);
assert.deepEqual(onlyEn, [], `named only in en: ${onlyEn.join(", ")}`);

// 3. no dead labels: every label is minted somewhere (or is the frontend's own)
const dead = [...zhSet]
  .filter((code) => !minted.has(code) && !FRONTEND_ONLY.includes(code))
  .sort();
assert.deepEqual(
  dead,
  [],
  `these labels name no code anyone mints (backend or the frontend itself): ${dead.join(", ")}`,
);

// 5. the maps are maps
const dup = zh.filter((code, index) => zh.indexOf(code) !== index);
assert.deepEqual([...new Set(dup)], [], `the zh map repeats keys: ${[...new Set(dup)].join(", ")}`);

// 6. the hidden routine codes are not a second home for the vocabulary
const hidden = source.match(/const hiddenRoutineTraceCodes = new Set\(\[([^\]]+)\]\)/);
assert(hidden, "panels/index.js must define hiddenRoutineTraceCodes");
const hiddenCodes = [...hidden[1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
assert(hiddenCodes.length > 0, "the hidden routine codes set is empty");
for (const code of hiddenCodes) {
  const mintedOrFrontend = minted.has(code) || FRONTEND_ONLY.includes(code);
  assert(
    mintedOrFrontend,
    `the UI hides routine code ${code} that the backend never mints (drift: a name the filter will silently ignore)`,
  );
}

// 4. no hand-written copy of the map outside its home
const files = [];
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walk(full);
    else if (entry.name.endsWith(".js")) files.push(full);
  }
}
await walk(SRC);
const LABEL_KEY_RE = /\b(?:tool_round_finished|verification_passed|run_finished|provider_stream_error|stagnation_guard)\s*:\s*"/;
const copies = [];
for (const file of files) {
  if (file === HOME) continue;
  const content = await readFile(file, "utf8");
  const match = content.match(LABEL_KEY_RE);
  if (match) {
    const line = content.slice(0, content.indexOf(match[0])).split("\n").length;
    copies.push(`${file}:${line}`);
  }
}
assert.deepEqual(
  copies,
  [],
  "a hand-written copy of the trace-code label map lives outside its one home " +
    `(${HOME}): ${copies.join(", ")}`,
);

console.log(`M8-T556 ok: traceLabel names all ${minted.size} minted codes in both languages (zh/en parity ${zh.length} keys)`);
