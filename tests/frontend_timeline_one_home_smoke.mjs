// M8-T904: the task timeline answers its own shape.
//
// The pulse card's archive rows answer "what ran"; the timeline answers
// "what ran when, how big, how did it end". This smoke pins the pure
// module (imported for real, not regex), the single render home inside
// openPulseStage, the i18n keys in both locales (CRLF-normalized read —
// node sees raw bytes where Python gates read universal newlines), the
// HTML slots, and the styles including the reduced-motion guard.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { taskTimelineSeries, taskTimelineTone, taskTimelineHeight, taskTimelineMarkup, compactTokens } from "../web/src/core/timeline-series.js";

const SRC = path.join("web", "src");
const STREAM = path.join(SRC, "chat", "stream.js");
const I18N = path.join(SRC, "core", "i18n.js");
const HTML = path.join("web", "index.html");
const STYLES = path.join("web", "styles.css");

// --- pure module behavior ---------------------------------------------------

assert.equal(taskTimelineTone("completed"), "mint");
assert.equal(taskTimelineTone("failed"), "rose");
assert.equal(taskTimelineTone("cancelled"), "amber");
assert.equal(taskTimelineTone("interrupted"), "amber");
assert.equal(taskTimelineTone("running"), "pulse", "live tasks breathe, not lie");
assert.equal(taskTimelineTone(""), "quiet");

// log scale: a 1M-token giant must not flatten a 2k-token run to zero
const big = taskTimelineHeight(1_000_000, 1_000_000);
const small = taskTimelineHeight(2_000, 1_000_000);
const zero = taskTimelineHeight(0, 1_000_000);
assert.equal(big, 100, "the max task fills the track");
assert.ok(small >= 12, "12% floor keeps tiny runs visible");
assert.ok(small < big, "log scale keeps the ordering");
assert.equal(zero, 8, "zero tokens still renders an 8% stub - a run happened, silence would lie");
assert.ok(taskTimelineHeight(2_000, 0) === 0, "no max, no height");

assert.equal(compactTokens(0), "0");
assert.equal(compactTokens(999), "999");
assert.equal(compactTokens(12_400), "12.4k");
assert.equal(compactTokens(1_000_000), "1M");

// newest-first input (the /api/tasks projection) -> oldest-left output
const tasks = [
  { task_id: "t3", status: "running", tokens_used: { total_tokens: 4000 }, created_at_epoch: 3000, preview: "third" },
  { task_id: "t2", status: "failed", tokens_used: { total_tokens: 12_000 }, created_at_epoch: 2000, preview: "second" },
  { task_id: "t1", status: "completed", tokens_used: { total_tokens: 2_000_000 }, created_at_epoch: 1000, preview: "first" },
];
const series = taskTimelineSeries(tasks);
assert.equal(series.length, 3, "every task becomes a node");
assert.equal(series[0].id, "t1", "oldest first on the strip");
assert.equal(series[2].id, "t3");
assert.equal(series[2].tone, "pulse");
assert.equal(series[0].tone, "mint");
assert.equal(series[0].height, 100, "the 2M-token run anchors the scale");
assert.ok(series[1].height > series[2].height, "failed 12k run renders taller than running 4k run");
assert.equal(taskTimelineSeries(null).length, 0, "non-array degrades");
assert.equal(taskTimelineSeries([]).length, 0, "empty list degrades to empty series");

const capped = Array.from({ length: 30 }, (_, i) => ({ task_id: `t${i}`, status: "completed", tokens_used: { total_tokens: 100 }, created_at_epoch: i }));
assert.equal(taskTimelineSeries(capped).length, 12, "strip capped at 12 nodes");

// markup: escaping, tone attributes, honest degradation
const markup = taskTimelineMarkup(series, { empty: "none", old: "older", new: "latest", tokensUnit: "tokens", noTokens: "none" });
assert.match(markup, /data-tone="mint"/);
assert.match(markup, /data-tone="rose"/);
assert.match(markup, /data-tone="pulse"/);
assert.match(markup, /data-open-task="t1"/, "nodes ride the existing data-open-task delegation");
assert.match(markup, /2M tokens/, "token totals surface in the tooltip");
assert.ok(!markup.includes("pulse-timeline-empty"), "a non-empty series never renders the empty stub");
assert.match(taskTimelineMarkup([], { empty: "none" }), /pulse-timeline-empty/, "empty series renders the honest empty stub");
assert.equal(taskTimelineMarkup([], {}), "", "no label, no markup at all");
const xss = taskTimelineSeries([{ task_id: 'x"y', status: "completed", preview: "<script>alert(1)</script>", tokens_used: { total_tokens: 5 } }]);
assert.ok(!taskTimelineMarkup(xss, { tokensUnit: "tokens" }).includes("<script>"), "preview is escaped into tooltips");

// --- one render home ---------------------------------------------------------

const stream = (await readFile(STREAM, "utf8")).replace(/\r\n/g, "\n");
assert.equal(stream.split("taskTimelineSeries(").length - 1, 1, "the series is built in exactly one place (openPulseStage)");
assert.equal(stream.split("taskTimelineMarkup(").length - 1, 1, "one render call (the import is brace-listed, not a call)");
assert.match(stream, /timeline\.innerHTML = taskTimelineMarkup/, "openPulseStage is the render home");
assert.match(stream, /t\("pulse\.timelineEmpty"\)/, "the empty label resolves through the literal-key gate");
assert.match(stream, /t\("pulse\.timelineOld"\)/);
assert.match(stream, /t\("pulse\.timelineNew"\)/);

// --- keys in both locales ----------------------------------------------------

const i18n = (await readFile(I18N, "utf8")).replace(/\r\n/g, "\n");
const zhMatch = i18n.match(/zh: \{(.*?)\n  \},\n  en: \{/s);
const enMatch = i18n.match(/  en: \{(.*?)\n  \},\n\}/s);
assert.ok(zhMatch && enMatch, "i18n.js parses as a zh/en pair");
for (const key of ["pulse.timelineOld", "pulse.timelineNew", "pulse.timelineEmpty"]) {
  for (const column of [zhMatch[1], enMatch[1]]) {
    assert.match(column, new RegExp(`"${key.replace(".", "\\.")}":`), `${key} missing from one locale`);
  }
}

// --- slots and styles ---------------------------------------------------------

const html = (await readFile(HTML, "utf8")).replace(/\r\n/g, "\n");
assert.match(html, /id="pulseTimeline"/, "the pulse stage carries the timeline slot");
assert.match(html, /id="pulseTimelineCount"/, "the kicker carries the count slot");
assert.match(html, /data-i18n="pulse\.epoch"/, "the kicker caption reuses the existing epoch key");
assert.match(html, /pulse-epoch-shell/, "the timeline lives in its own card shell above the archive");

const styles = await readFile(STYLES, "utf8");
for (const cls of ["pulse-timeline-track", "pulse-timeline-node", "pulse-timeline-bar", "pulse-timeline-tip", "pulse-timeline-axis", "pulse-timeline-empty"]) {
  assert.match(styles, new RegExp(`\\.${cls}`), `.${cls} unstyled`);
}
assert.match(styles, /\[data-tone="pulse"\].*animation/, "live tasks breathe");
assert.match(styles, /prefers-reduced-motion[\s\S]*pulse-timeline/, "reduced-motion turns the breath off");

console.log("timeline smoke: PASS");
