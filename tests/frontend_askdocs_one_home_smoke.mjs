// M8-T975: the Ask-the-Repo panel is wired end to end — panel module →
// stream re-export → main route → sidebar button → command palette →
// i18n in both locales → manual chapter 10. One wiring home per layer;
// this smoke fails if any of them drifts or if a credential literal
// ever lands in the panel.

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const SRC = path.join("web", "src");
const PANEL = path.join(SRC, "panels", "askdocs.js");
const STREAM = path.join(SRC, "chat", "stream.js");
const MAIN = path.join(SRC, "main.js");
const PALETTE = path.join(SRC, "core", "command-palette.js");
const I18N = path.join(SRC, "core", "i18n.js");
const HTML = path.join("web", "index.html");
const MANUAL = path.join(SRC, "panels", "manual.js");

const panel = await readFile(PANEL, "utf8");
assert.match(panel, /export async function openAskDocsPanel/, "panel must export openAskDocsPanel");
assert.match(panel, /\/api\/rag\/query/, "panel must call /api/rag/query");
assert.match(panel, /requestJson\(/, "panel must go through the shared transport (auth headers, timeout)");
assert.match(panel, /from "\.\.\/core\/transport\.js"/, "panel must import the shared transport");
assert.equal(panel.includes("sk-"), false, "panel must not embed a credential-shaped literal");

const stream = await readFile(STREAM, "utf8");
assert.match(stream, /import \{ openAskDocsPanel \} from "\.\.\/panels\/askdocs\.js"/, "stream must import the panel");
assert.match(stream, /export \{ openAskDocsPanel \}/, "stream must re-export the panel");

const main = await readFile(MAIN, "utf8");
assert.match(main, /openAskDocsPanel/, "main must import the panel");
assert.match(main, /view === "askdocs"/, "main must route view=askdocs to the panel");

const html = await readFile(HTML, "utf8");
assert.match(html, /data-view="askdocs"/, "sidebar button missing");
assert.match(html, /data-i18n="nav\.askdocs"/, "sidebar button must be wired to i18n");
assert.match(html, /data-lucide="file-search-2"/, "sidebar button icon must be the file-search-2 home");

const palette = await readFile(PALETTE, "utf8");
assert.match(palette, /\{ id: "askdocs", glyph: "file-search-2"/, "command palette entry missing");
assert.match(palette, /openAskDocsPanel/, "command palette must run openAskDocsPanel");

const i18n = await readFile(I18N, "utf8");
const occurrences = (needle) => i18n.split(needle).length - 1;
assert.equal(occurrences('"nav.askdocs":'), 2, "nav.askdocs must exist exactly twice (zh + en)");
assert.equal(occurrences('"askdocs.title":'), 2, "askdocs.title must exist exactly twice (zh + en)");
assert.equal(occurrences('"palette.cmd.askdocs":'), 2, "palette.cmd.askdocs must exist exactly twice (zh + en)");

const manual = await readFile(MANUAL, "utf8");
assert.match(manual, /id: "askdocs"/, "manual chapter 10 must be registered");
assert.match(manual, /zhAskDocs/, "manual must carry the zh chapter body");
assert.match(manual, /enAskDocs/, "manual must carry the en chapter body");

// M8-T1316: the wide-context path is actually reachable from the panel —
// a depth selector feeds a budget into /api/rag/query, and the returned
// assembly evidence is rendered with real line anchors.
assert.match(panel, /id="askdocsDepth"/, "depth selector missing");
assert.match(panel, /askdocs\.depthWide/, "depth options must come from the dictionary");
assert.match(panel, /"50000:48:20"/, "deep mode must encode budget:fanout:per - recall, not just budget");
assert.match(panel, /fanout=\$\{fanout\}/, "fanout must reach the query URL in deep mode");
assert.match(panel, /askdocs\.deepWarning/, "deep mode must warn about cost and no-model assembly");
assert.match(panel, /budget=\$\{budget\}/, "the selected budget must be appended to the query URL");
assert.match(panel, /contextEvidence\(context, sources\)/, "assembly evidence must be rendered");
assert.match(panel, /source\.start_line/, "sources must show real line anchors");
for (const key of ["askdocs.depth", "askdocs.depthPrecise", "askdocs.depthWide", "askdocs.depthDeep",
                   "askdocs.contextEvidence", "askdocs.contextStat", "askdocs.contextPacked",
                   "askdocs.contextChunks", "askdocs.contextFp", "askdocs.contextFanout",
                   "askdocs.deepHint", "askdocs.deepWarning"]) {
  assert.equal(occurrences(`"${key}":`), 2, `${key} must exist in both locales`);
}

console.log("askdocs smoke: PASS");
