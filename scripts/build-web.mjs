// Bundle the workbench from ES module entry points.
//
//   web/src/main.js  -> web/app.js   (IIFE, window globals for the arcade)
//   web/src/game.js  -> web/game.js  (separate arcade bundle)
//
// Usage: node scripts/build-web.mjs [--check]

import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { TextDecoder } from "node:util";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { createHash } from "node:crypto";
import { transform } from "esbuild";

const root = fileURLToPath(new URL("..", import.meta.url));
const srcDir = join(root, "web", "src");
const outDir = join(root, "web");
const check = process.argv.includes("--check");

async function bundle(entry, outfile) {
  const result = await build({
    absWorkingDir: root,
    entryPoints: [entry],
    bundle: true,
    format: "iife",
    platform: "browser",
    target: "es2020",
    outfile,
    write: false,
    logLevel: "silent",
    legalComments: "none",
  });
  const file = result.outputFiles[0];
  if (!file) throw new Error(`esbuild produced no output for ${entry}`);
  return file.text;
}

// A Windows checkout writes CRLF (core.autocrlf) where esbuild emits LF.
// Line endings are not content; everything else must still match exactly.
const normalizeEol = (text) => text.replace(/\r\n/g, "\n");

function writeIfNeeded(path, content) {
  mkdirSync(dirname(path), { recursive: true });
  let current = "";
  try {
    current = readFileSync(path, "utf8");
  } catch {
    current = "";
  }
  // A build that changes nothing should write nothing: on a CRLF checkout a
  // needless rewrite leaves `git status` claiming the artifacts changed.
  if (normalizeEol(current) === normalizeEol(content)) return true;
  if (check) {
    console.error(`${path} is stale — run \`npm run build:web\``);
    process.exitCode = 1;
    return false;
  }
  writeFileSync(path, content, "utf8");
  return true;
}

// M8-T827: a stylesheet once shipped half UTF-8 / half UTF-16LE. PowerShell's
// WriteAllText defaults to UTF-16 on Windows, so appending a block produced NUL-
// interleaved bytes; readFileSync(...,"utf8") silently turned every one of them
// into U+FFFD, esbuild happily minified the replacements, and the shipped bundle
// served garbage for the entire glassmorphism/toast section — while --check
// stayed green because the garbage was stable. Read source files as raw bytes
// and refuse mixed/broken encoding before they can enter a content-hashed asset.
function assertUtf8Text(path) {
  const bytes = readFileSync(path);
  const nul = bytes.indexOf(0);
  if (nul !== -1) {
    throw new Error(
      `${path} contains a NUL byte at offset ${nul} — likely UTF-16 text appended to a UTF-8 file ` +
      `(PowerShell WriteAllText writes UTF-16 by default). Rewrite it as UTF-8 without BOM.`);
  }
  // fatal decoder: any invalid UTF-8 sequence is an error, not a U+FFFD replacement.
  const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  if (text.includes("\ufffd")) {
    throw new Error(`${path} contains a U+FFFD replacement character — it is not valid UTF-8 source.`);
  }
  return text;
}

const app = await bundle(join(srcDir, "main.js"), join(outDir, "app.js"));
const game = await bundle(join(srcDir, "game.js"), join(outDir, "game.js"));
const appOk = writeIfNeeded(join(outDir, "app.js"), app);
const gameOk = writeIfNeeded(join(outDir, "game.js"), game);
if (check) {
  if (appOk && gameOk && process.exitCode !== 1) {
    console.log(`web/app.js + web/game.js are up to date (${app.length + game.length} chars)`);
  }
} else {
  console.log(`built web/app.js (${app.length} chars)`);
  console.log(`built web/game.js (${game.length} chars)`);
}

const manifest = {};
for (const [name, source, loader] of [
  ["app.js", app, "js"],
  ["game.js", game, "js"],
  ["styles.css", assertUtf8Text(join(outDir, "styles.css")), "css"],
]) {
  const { code } = await transform(source, { loader, minify: true, target: "es2020", legalComments: "none" });
  const hash = createHash("sha256").update(code).digest("hex").slice(0, 16);
  const dot = name.lastIndexOf(".");
  const asset = `assets/${name.slice(0, dot)}.${hash}${name.slice(dot)}`;
  manifest[`/${name}`] = `/${asset}`;
  writeIfNeeded(join(outDir, asset), code);
}
writeIfNeeded(join(outDir, "asset-manifest.json"), JSON.stringify(manifest, null, 2) + "\n");

// Content-hashed bundles accumulate one file per build. Only the three the
// manifest references are ever served (static_assets.py resolves logical paths
// through it), so prune the rest. In --check mode an unreferenced bundle is a
// freshness failure: CI must catch stale-asset buildup, not just stale app.js.
const assetsDir = join(outDir, "assets");
const referenced = new Set(Object.values(manifest).map((asset) => asset.split("/").pop()));
let stale = [];
try {
  stale = readdirSync(assetsDir).filter((name) => !referenced.has(name));
} catch {
  stale = [];
}
if (check) {
  if (stale.length) {
    console.error(
      `web/assets has ${stale.length} bundle(s) not referenced by asset-manifest.json ` +
      `(${stale.join(", ")}) — run \`npm run build:web\``,
    );
    process.exitCode = 1;
  } else if (process.exitCode !== 1) {
    console.log(`web/assets is clean (${referenced.size} referenced bundle(s))`);
  }
} else {
  for (const name of stale) rmSync(join(assetsDir, name), { force: true });
  if (stale.length) console.log(`pruned ${stale.length} stale asset bundle(s)`);
}
