// M8-T1311 — t(key, params) fills {placeholders} without changing the old
// t(key) path. The dictionary stays the single home for every word: only the
// numbers are substituted by the caller. Missing params stay visible as
// "{name}" rather than degrading into a plausible-looking "undefined".
// DOM-free: state.js reads localStorage at import time, so stub it first.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

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
assert.ok(!/\.replace\("\{shown\}"/.test(stream), "no hand-rolled placeholder substitution left");
const gate = await readFile("tests/frontend_i18n_dict_one_home_smoke.mjs", "utf8");
assert.ok(gate.includes('(?:,\\s*\\{[^}]*\\})?'), "the dict gate must still match two-arg t() calls");

console.log("i18n interpolation smoke passed: no-arg path unchanged, both locales interpolate, missing params stay visible, fallback intact, dict gate sees two-arg calls");
