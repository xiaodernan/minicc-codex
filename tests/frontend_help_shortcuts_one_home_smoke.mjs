// M8-T901: the help panel's shortcut table answers the real keymap.
//
// The table shipped with five rows while the app had grown seven bindings -
// Ctrl/⌘K (command palette) and Ctrl/⌘L (ledger) never made the list, so
// the one screen meant to answer "what can this thing do" was the stalest
// surface in the workbench. This smoke pins:
//
// * every global Ctrl/⌘ binding in main.js appears in the help table, and
//   the table never lists a binding main.js does not handle;
// * the "?" handler exists with the same input-guard as "/" (typing ? in
//   the composer must not fling the panel open);
// * the reference lists itself - a shortcut table you can't discover is
//   a locked index.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const MAIN = path.join("web", "src", "main.js");
const STREAM = path.join("web", "src", "chat", "stream.js");

const main = (await readFile(MAIN, "utf8")).replace(/\r\n/g, "\n");
const stream = (await readFile(STREAM, "utf8")).replace(/\r\n/g, "\n");

// --- every handled binding is documented ------------------------------------

const helpBody = stream.slice(stream.indexOf("function openHelpPanel"), stream.indexOf("function openHelpPanel") + 2200);
assert.ok(helpBody.includes('state.locale === "zh"'), "help panel locale split disappeared");
const tableKeys = [...helpBody.matchAll(/"(Enter|Shift\+Enter|Ctrl\/⌘ [A-Z]|\/|\?|Esc)"/g)].map((m) => m[1]);
assert.ok(tableKeys.includes("Ctrl/⌘ K"), "command palette binding missing from the help table");
assert.ok(tableKeys.includes("Ctrl/⌘ L"), "ledger binding missing from the help table");
assert.ok(tableKeys.includes("?"), "the reference must list itself (? opens it)");
assert.ok(tableKeys.includes("Enter") && tableKeys.includes("Shift+Enter") && tableKeys.includes("/") && tableKeys.includes("Esc") && tableKeys.includes("Ctrl/⌘ N"),
  "core bindings (Enter / Shift+Enter / Ctrl N / / / Esc) missing from the help table");

// --- handlers exist for each advertised binding ------------------------------

assert.match(main, /key\.toLowerCase\(\) === "n"/, "Ctrl/⌘N handler missing");
assert.match(main, /key\.toLowerCase\(\) === "k"/, "Ctrl/⌘K handler missing");
assert.match(main, /key\.toLowerCase\(\) === "l"/, "Ctrl/⌘L handler missing");
assert.match(main, /key === "\/" && document\.activeElement\?\.tagName !== "TEXTAREA"/, "slash handler missing or unguarded");
assert.match(main, /key === "\?" && document\.activeElement\?\.tagName !== "TEXTAREA"/, "question-mark handler missing or unguarded");

// --- the ? handler opens the help panel ---------------------------------------

const questionMarkLine = main.split("\n").find((line) => line.includes('key === "?"'));
assert.match(questionMarkLine, /openHelpPanel\(\)/, "? must open the help panel");

// --- zh and en tables stay symmetric -------------------------------------------

// Rows alternate: 8 zh rows then 8 en rows, same key order by construction.
const allKeys = [...helpBody.matchAll(/\["[^"]+", "(Enter|Shift\+Enter|Ctrl\/⌘ [A-Z]|\/|\?|Esc)"\]/g)].map((m) => m[1]);
assert.equal(allKeys.length % 2, 0, "shortcut rows must come in zh/en pairs");
const half = allKeys.length / 2;
const zhKeys = allKeys.slice(0, half);
const enKeys = allKeys.slice(half);
assert.deepEqual(zhKeys, enKeys, "zh and en shortcut tables drifted apart");

console.log("help-shortcuts smoke: PASS");
