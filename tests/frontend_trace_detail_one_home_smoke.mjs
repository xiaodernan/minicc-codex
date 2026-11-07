// M8-T588: the trace-detail renderers derive iteration from their dicts.
//
// panels/index.js carries two near-identical renderers for event.detail:
// traceDetailPreview (short, capped) and traceDetail (full). Each used to
// hand-maintain (a) a zh/en labels dict and (b) a literal key list walked
// next to it - the two structures drifted independently. The preview list
// even carried a key the detail dicts never had, so the expanded view
// silently swallowed that field.
//
// The one structure per renderer is now the labels dict; iteration derives
// from Object.keys(). This gate pins:
//
// 1. neither renderer mentions a hand-written key list;
// 2. the zh dict and the en dict carry the same keys, in both renderers;
// 3. the preview dict's keys are a subset of the detail dict's keys;
// 4. both renderers know recovery_inspection_required (the key that was
//    only in the preview).

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const FILE = "web/src/panels/index.js";
const src = await readFile(FILE, "utf8");

const a = src.indexOf("export function traceDetailPreview");
const b = src.indexOf("export function traceEvidenceMarkup");
const c = src.indexOf("export function traceDetail(");
const d = src.indexOf("export function shortEventText");
assert(a > -1 && b > a, "traceDetailPreview not found");
assert(c > -1 && d > c, "traceDetail not found");

const preview = src.slice(a, b);
const detail = src.slice(c, d);

for (const [name, fn] of [["preview", preview], ["detail", detail]]) {
  assert(!/for \(const key of \[/.test(fn), `${name}: the hand-written key list is back (derive with Object.keys(labels))`);
  assert(!/const keys = \[/.test(fn), `${name}: the hand-written key array is back`);
}

function dictsOf(fn) {
  const zh = fn.match(/state\.locale === "zh"\s*\n\s*\?\s*\{([\s\S]*?)\}\s*\n\s*:\s*\{([\s\S]*?)\}\s*;/);
  assert(zh, "could not locate the zh/en label dicts");
  const keysOf = (body) => [...body.matchAll(/([a-z_]+):/g)].map((m) => m[1]);
  return { zh: keysOf(zh[1]), en: keysOf(zh[2]) };
}

const p = dictsOf(preview);
const f = dictsOf(detail);
assert.deepEqual(p.zh, p.en, "preview: the zh and en label dicts disagree");
assert.deepEqual(f.zh, f.en, "detail: the zh and en label dicts disagree");
assert(
  p.zh.every((k) => f.zh.includes(k)),
  `preview keys must be a subset of the detail dict's keys; missing: ${p.zh.filter((k) => !f.zh.includes(k))}`,
);
assert(p.zh.includes("recovery_inspection_required"), "the preview lost recovery_inspection_required");
assert(f.zh.includes("recovery_inspection_required"), "the detail dict must render recovery_inspection_required too");

console.log("M8-T588 ok: both trace-detail renderers derive iteration from their label dicts; zh/en key sets match; preview keys are a subset of detail keys");
