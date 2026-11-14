// M8-T964/M8-T974: the `?` help panel renders from the single
// SHORTCUT_GROUPS home (web/src/cheat-sheet-data.js) shared with the
// manual's chapter 4. This smoke pins the same promises the hard-coded
// table used to pin, against the single source instead:
//
// * the data home exists, exports SHORTCUT_GROUPS, and the help panel
//   imports it instead of re-literalizing the rows;
// * every global binding main.js handles appears in the data (Ctrl/⌘N,
//   Ctrl/⌘K, Ctrl/⌘L, Enter, Shift+Enter, /, ?, Esc) - and the reference
//   lists itself;
// * every row carries BOTH a zh and an en label (no mixed-language rows);
// * the "?" handler exists with the same input-guard as "/" (typing ?
//   in the composer must not fling the panel open).

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const MAIN = path.join("web", "src", "main.js");
const STREAM = path.join("web", "src", "chat", "stream.js");
const DATA = path.join("web", "src", "cheat-sheet-data.js");

const main = (await readFile(MAIN, "utf8")).replace(/\r\n/g, "\n");
const stream = (await readFile(STREAM, "utf8")).replace(/\r\n/g, "\n");

// --- the single source exists and the panel renders from it -----------------

assert.ok(stream.includes("SHORTCUT_GROUPS"), "help panel no longer references the single data home");
assert.match(stream, /import \{ SHORTCUT_GROUPS \} from "\.\.\/cheat-sheet-data\.js"/, "help panel's import of the data home disappeared");
assert.ok(stream.includes('state.locale === "zh"'), "help panel locale split disappeared");

const { SHORTCUT_GROUPS, shortcutRows } = await import(pathToFileURL(path.resolve(DATA)).href);
assert.ok(Array.isArray(SHORTCUT_GROUPS) && SHORTCUT_GROUPS.length > 0, "SHORTCUT_GROUPS is missing or empty");
const rows = shortcutRows();
assert.ok(rows.length >= 14, `cheat sheet shrank to ${rows.length} rows`);

// --- every handled binding appears in the data -------------------------------

const squash = (s) => String(s).replace(/\s+/g, "");
const norms = rows.map((row) => squash(row.key));
const hasKey = (binding) => norms.some((k) => k === squash(binding));

for (const binding of ["Enter", "Shift+Enter", "Ctrl/⌘ N", "Ctrl/⌘ K", "Ctrl/⌘ L", "/", "?", "Esc"]) {
  assert.ok(hasKey(binding), `binding ${binding} missing from the cheat-sheet data`);
}

// --- zh and en labels are both present on every row ---------------------------

for (const row of rows) {
  assert.ok(typeof row.zh === "string" && row.zh.trim().length > 0, `row missing its zh label: ${JSON.stringify(row)}`);
  assert.ok(typeof row.en === "string" && row.en.trim().length > 0, `row missing its en label: ${JSON.stringify(row)}`);
}
for (const group of SHORTCUT_GROUPS) {
  assert.ok(group.zh && group.en, `group ${group.id} is missing a zh or en title`);
  assert.ok(Array.isArray(group.rows) && group.rows.length > 0, `group ${group.id} has no rows`);
}

// --- handlers exist for each advertised binding -------------------------------

assert.match(main, /key\.toLowerCase\(\) === "n"/, "Ctrl/⌘N handler missing");
assert.match(main, /key\.toLowerCase\(\) === "k"/, "Ctrl/⌘K handler missing");
assert.match(main, /key\.toLowerCase\(\) === "l"/, "Ctrl/⌘L handler missing");
assert.match(main, /key === "\/" && document\.activeElement\?\.tagName !== "TEXTAREA"/, "slash handler missing or unguarded");
assert.match(main, /key === "\?" && document\.activeElement\?\.tagName !== "TEXTAREA"/, "question-mark handler missing or unguarded");

// --- the ? handler opens the help panel ----------------------------------------

const questionMarkLine = main.split("\n").find((line) => line.includes('key === "?"'));
assert.match(questionMarkLine, /openHelpPanel\(\)/, "? must open the help panel");

console.log("help-shortcuts smoke: PASS");
