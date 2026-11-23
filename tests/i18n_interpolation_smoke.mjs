// M8-T1311 — t(key, params) fills {placeholders} without changing the old
// t(key) path. The dictionary stays the single home for every word: only the
// numbers are substituted by the caller. Missing params stay visible as
// "{name}" rather than degrading into a plausible-looking "undefined".
// DOM-free: state.js reads localStorage at import time, so stub it first.

import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
const { t, I18N } = await import("../web/src/core/i18n.js");
const { state } = await import("../web/src/core/state.js");

// The no-arg path must be the old one-liner verbatim: every existing call site
// keeps the exact same string in both locales.
for (const locale of ["zh", "en"]) {
  state.locale = locale;
  for (const key of ["changes.unavailable", "changes.partial", "changes.listTruncated"]) {
    assert.equal(t(key), I18N[locale][key], `${locale}/${key}: no-arg path changed`);
  }
}

// Interpolation in both locales, with the dictionary text as the only source.
state.locale = "en";
assert.equal(
  t("changes.listTruncated", { shown: 2, total: 5 }),
  "Showing the first 2 of 5 changes (all are counted in the totals).",
);
state.locale = "zh";
assert.equal(
  t("changes.listTruncated", { shown: 2, total: 5 }),
  "改动较多，仅显示前 2 条，共 5 条（总数已计入统计）。",
);

// A missing param leaves the placeholder — a typo must not read as real prose.
state.locale = "en";
assert.ok(t("changes.listTruncated", { shown: 2 }).includes("{total}"), "missing param must stay visible");
assert.ok(!/undefined/.test(t("changes.listTruncated", { shown: 2 })), "no 'undefined' in user-facing copy");

// Falsy-but-real values are substituted, and the unknown-key fallback is intact.
assert.ok(t("changes.listTruncated", { shown: 0, total: 5 }).includes("first 0"), "0 must be substituted");
assert.equal(t("no.such.key", { a: 1 }), "no.such.key", "fallback must still return the raw key");

// t() substitutes strings; escaping remains the caller's job. Pin that a value
// is inserted verbatim so nobody assumes t() sanitizes HTML.
assert.equal(t("changes.listTruncated", { shown: "<b>", total: 5 }).includes("<b>"), true);

// The source contract: the truncation call site uses the one-helper form, and
// the dictionary gate's regex still sees two-arg calls as references.
const stream = await readFile("web/src/chat/stream.js", "utf8");
assert.ok(/t\(\s*"changes\.listTruncated"\s*,\s*\{/.test(stream), "truncation copy must use t(key, params)");

// M8-T1313: every placeholder-carrying key must be filled by the one helper,
// in both locales, with no brace left behind. Covers the four stragglers that
// still hand-rolled replace() after T1311 (admin forecast x2, atlas x2).
const parametric = [
  ["admin.forecastLine", { n: "12.5", slope: "+0.4" }, ["12.5", "+0.4"]],
  ["admin.forecastNote", { lines: "800" }, ["800"]],
  ["atlas.charted", { n: 4, total: 119 }, ["4", "119"]],
  ["atlas.milestone25", { n: 30, total: 119 }, ["30", "119"]],
];
for (const locale of ["zh", "en"]) {
  state.locale = locale;
  for (const [key, params, values] of parametric) {
    const filled = t(key, params);
    assert.ok(!/\{[A-Za-z0-9_.-]+\}/.test(filled), `${locale}/${key}: placeholder left unfilled: ${filled}`);
    for (const value of values) assert.ok(filled.includes(value), `${locale}/${key}: missing value ${value}: ${filled}`);
  }
}

// No hand-rolled placeholder substitution anywhere in web/src — the helper is
// the single home. Reading the sources, not the DOM.
async function scanSources(dir) {
  const found = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...await scanSources(full));
    else if (entry.name.endsWith(".js")) {
      const content = await readFile(full, "utf8");
      if (/\.replace\(\s*"\{/.test(content)) found.push(full.replace(/\\/g, "/"));
    }
  }
  return found;
}
const handRolled = await scanSources("web/src");
assert.deepEqual(handRolled, [], `hand-rolled placeholder replace() left in: ${handRolled.join(", ")}`);

const gate = await readFile("tests/frontend_i18n_dict_one_home_smoke.mjs", "utf8");
assert.ok(gate.includes('(?:,\\s*\\{[^}]*\\})?'), "the dict gate must still match two-arg t() calls");
assert.ok(gate.includes("_KEYS"), "the dict gate must also resolve keys referenced from *_KEYS arrays");

// M8-T1314: every milestone key reached only through MILESTONE_KEYS[index]
// must interpolate in both locales with no brace left behind.
for (const locale of ["zh", "en"]) {
  state.locale = locale;
  for (const key of ["atlas.milestone25", "atlas.milestone50", "atlas.milestone75", "atlas.milestone100"]) {
    const filled = t(key, { n: 30, total: 119 });
    assert.ok(!/\{[A-Za-z0-9_.-]+\}/.test(filled), `${locale}/${key}: placeholder left: ${filled}`);
    assert.ok(filled.includes("30") && filled.includes("119"), `${locale}/${key}: values missing: ${filled}`);
  }
  // The context panel's honest four states all exist as real localized copy.
  for (const key of ["admin.contextTimeout", "admin.contextSlow", "admin.contextOutage",
                     "admin.contextEmpty", "admin.contextTruncated", "admin.contextBudget",
                     "admin.contextPacked", "admin.contextChunksCandidates", "admin.contextFingerprint"]) {
    assert.ok(typeof t(key) === "string" && t(key) !== key, `${locale}/${key}: missing translation`);
  }
}

// transport tags timeouts with a machine-readable code; panels use it to tell
// "slow" apart from "unreachable" instead of reporting every delay as a outage.
const transport = await readFile("web/src/core/transport.js", "utf8");
assert.ok(/timeoutError\.code\s*=\s*"timeout"/.test(transport), "timeout errors must carry code=timeout");
const adminSrc = await readFile("web/src/panels/admin.js", "utf8");
assert.ok(/error\.code\s*===\s*"timeout"/.test(adminSrc), "admin context tile must branch on the timeout code");

console.log("i18n interpolation smoke passed: no-arg path unchanged, all parametric keys fill in both locales, missing params stay visible, fallback intact, no hand-rolled replace left in web/src, dict gate sees two-arg calls");
