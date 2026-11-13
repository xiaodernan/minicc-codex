// M8-T899: the per-call cache-hit series answers its own shape.
//
// usage_by_turn has been accumulated twice over — live by the SSE reducer
// and in the task snapshot — but nothing rendered it, so the only cache
// surface was one aggregate ring that a cold first turn drags down. This
// smoke pins the series module (imported for real, not regex), the single
// render home, the i18n keys in both locales, and the reducer's one home
// for the accumulation.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { cacheTurnSeries, cacheTurnTone } from "../web/src/core/cache-series.js";

const SRC = path.join("web", "src");
const PANELS = path.join(SRC, "panels", "index.js");
const REDUCER = path.join(SRC, "core", "task-reducer.js");
const I18N = path.join(SRC, "core", "i18n.js");
const STYLES = path.join("web", "styles.css");

// --- pure module behavior -------------------------------------------------

assert.deepEqual(cacheTurnSeries(null), [], "non-array input degrades to empty");
assert.deepEqual(cacheTurnSeries(undefined), [], "undefined degrades to empty");

const mixed = [
  null,
  { prompt_tokens: 0, prompt_cache_hit_tokens: 0 }, // no prompt, no story
  { prompt_tokens: 1000, prompt_cache_hit_tokens: 0, prompt_cache_miss_tokens: 1000 }, // cold
  { kind: "completion_judge", prompt_tokens: 800, prompt_cache_hit_tokens: 600, prompt_cache_miss_tokens: 200 },
  { prompt_tokens: 900, prompt_cache_hit_tokens: 900, prompt_cache_miss_tokens: 0 }, // full hit
  { prompt_tokens: 700 }, // no hit/miss split reported — null rate, not zero
];
const series = cacheTurnSeries(mixed);
assert.equal(series.length, 4, "entries without a prompt are dropped, objects kept");
assert.deepEqual(
  series.map((p) => p.rate),
  [0, 0.75, 1, null],
  "rates: cold 0, judge 0.75, full hit 1, unreported null",
);
assert.equal(series[1].kind, "completion_judge", "kind tag survives into the series");
assert.equal(cacheTurnTone(0.85), "mint");
assert.equal(cacheTurnTone(0.5), "amber");
assert.equal(cacheTurnTone(0.1), "rose");
assert.equal(cacheTurnTone(null), "quiet", "unreported is quiet, never mint");

const many = Array.from({ length: 40 }, (_, i) => ({ prompt_tokens: 10, prompt_cache_hit_tokens: i, prompt_cache_miss_tokens: 10 }));
assert.equal(cacheTurnSeries(many).length, 24, "series capped at 24 bars");

// --- one render home -------------------------------------------------------

const panels = await readFile(PANELS, "utf8");
assert.equal(panels.split("cacheTurnSparkline(").length - 1, 2, "one definition + exactly one call site inside runtimeMetricsMarkup");
assert.match(panels, /cacheTurnSparkline\(data\?\.usage_by_turn\)/, "runtimeMetricsMarkup is the render home");
assert.equal(panels.split("cacheTurnSeries(").length - 1, 1, "the pure module is called exactly once (inside cacheTurnSparkline)");

const reducer = await readFile(REDUCER, "utf8");
assert.match(reducer, /usage_by_turn = \[\.\.\.\(data\.usage_by_turn \|\| \[\]\), \{ \.\.\.payload\.usage \}\]\.slice\(-64\)/, "usage_by_turn accumulates in exactly one reducer case");

// --- keys in both locales --------------------------------------------------

const i18nRaw = await readFile(I18N, "utf8");
const i18n = i18nRaw.replace(/\r\n/g, "\n"); // CRLF-native file; Python gates read it with universal newlines
const zhMatch = i18n.match(/zh: \{(.*?)\n  \},\n  en: \{/s);
const enMatch = i18n.match(/  en: \{(.*?)\n  \},\n\}/s);
assert.ok(zhMatch && enMatch, "i18n.js parses as a zh/en pair");
for (const column of [zhMatch[1], enMatch[1]]) {
  assert.match(column, /"ledger\.perCallTitle":/, "per-call title missing from one locale");
}

// --- styles ship the four tones ---------------------------------------------

const styles = await readFile(STYLES, "utf8");
for (const tone of ["mint", "amber", "rose", "quiet"]) {
  assert.match(styles, new RegExp(`\\.cache-series-${tone}`), `sparkline tone .${tone} unstyled`);
}

console.log("cache-series smoke: PASS");
