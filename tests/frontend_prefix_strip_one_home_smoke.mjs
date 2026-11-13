// M8-T908: the prefix fingerprint strip answers its own shape.
//
// M8-T907 shipped system/msgs/tools fingerprints in every usage record;
// this strip is their face in the task detail modal. The smoke pins the
// pure module (imported for real), the single render home riding
// runtimeMetricsMarkup (so the inspector inherits it for free), honest
// absence for pre-T907 snapshots, the shared i18n key, and the tone rules.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { prefixRows, prefixStripMarkup } from "../web/src/core/prefix-strip.js";

const SRC = path.join("web", "src");
const PANELS = path.join(SRC, "panels", "index.js");
const I18N = path.join(SRC, "core", "i18n.js");
const STYLES = path.join("web", "styles.css");

// --- pure module behavior -----------------------------------------------------

assert.deepEqual(prefixRows(null), [], "non-array degrades to empty");
assert.deepEqual(prefixRows([]), [], "empty degrades to empty");

const mixed = [
  null,
  { prompt_tokens: 100, prompt_cache_hit_tokens: 90 }, // pre-T907: no fingerprints, no story
  { prompt_tokens: 1000, prompt_cache_hit_tokens: 900, system_fp: "88352327d51c", msgs_fp: "a4efb4a71234", tools_fp: "8fab4c14e053" },
  { prompt_tokens: 800, prompt_cache_hit_tokens: 100, system_fp: "88352327d51c", msgs_fp: "b9c2d1e0ff00", tools_fp: "8fab4c14e053" },
];
const rows = prefixRows(mixed);
assert.equal(rows.length, 2, "fingerprint-less rows are dropped, fingerprinted rows kept");
assert.equal(rows[0].sys, "88352327", "fingerprints truncate to 8 hex");
assert.equal(rows[0].msgs, "a4efb4a7");
assert.equal(rows[0].prompt, 1000);
assert.equal(rows[1].prompt, 800);

const many = Array.from({ length: 30 }, (_, i) => ({
  prompt_tokens: 100, prompt_cache_hit_tokens: i,
  system_fp: `s${i}`, msgs_fp: `m${i}`, tools_fp: `t${i}`,
}));
assert.equal(prefixRows(many).length, 12, "strip capped at 12 rows");

// markup: rates and tones
const markup = prefixStripMarkup(rows, { hitLabel: "命中" });
assert.match(markup, /data-tone="mint"/, "90% hit renders mint");
assert.match(markup, /data-tone="rose"/, "12.5% hit renders rose");
assert.match(markup, /90%/, "the rate itself is visible");
assert.match(markup, /命中/, "the hit label resolves through the caller");
assert.match(markup, /prefix-strip-row/);
assert.ok(!prefixStripMarkup([], {}), "empty rows render nothing at all");
assert.equal(prefixStripMarkup(undefined, {}), "", "undefined rows render nothing");

// --- one render home ------------------------------------------------------------

const panels = (await readFile(PANELS, "utf8")).replace(/\r\n/g, "\n");
assert.equal(panels.split("prefixRows(").length - 1, 1, "the rows are built in exactly one place");
assert.equal(panels.split("prefixStripMarkup(").length - 1, 1, "one render call (the import is brace-listed)");
assert.match(panels, /prefixStripMarkup\(prefixRows\(data\?\.usage_by_turn\)/, "runtimeMetricsMarkup is the render home");
assert.match(panels, /hitLabel: t\("ledger\.cacheHits"\)/, "the hit label reuses the existing dict key");
assert.ok(!panels.includes('state.locale === "zh" ? "命中"'), "no hardcoded locale ternaries for the label");

// --- the shared key exists in both locales ---------------------------------------

const i18n = (await readFile(I18N, "utf8")).replace(/\r\n/g, "\n");
const zhMatch = i18n.match(/zh: \{(.*?)\n  \},\n  en: \{/s);
const enMatch = i18n.match(/  en: \{(.*?)\n  \},\n\}/s);
assert.ok(zhMatch && enMatch, "i18n.js parses as a zh/en pair");
for (const column of [zhMatch[1], enMatch[1]]) {
  assert.match(column, /"ledger\.cacheHits":/, "the shared key is missing from one locale");
}

// --- styles ----------------------------------------------------------------------

const styles = await readFile(STYLES, "utf8");
for (const cls of ["prefix-strip", "prefix-strip-row", "prefix-strip-n"]) {
  assert.match(styles, new RegExp(`\\.${cls}`), `.${cls} unstyled`);
}
for (const tone of ["mint", "amber", "rose"]) {
  assert.match(styles, new RegExp(`b\\[data-tone="${tone}"\\]`), `tone ${tone} unstyled`);
}

console.log("prefix-strip smoke: PASS");
