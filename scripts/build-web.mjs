// Bundle the workbench from ES module entry points.
//
//   web/src/main.js  -> web/app.js   (IIFE, window globals for the arcade)
//   web/src/game.js  -> web/game.js  (separate arcade bundle)
//
// Usage: node scripts/build-web.mjs [--check]

import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
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

function writeIfNeeded(path, content) {
  mkdirSync(dirname(path), { recursive: true });
  if (check) {
    let current = "";
    try {
      current = readFileSync(path, "utf8");
    } catch {
      current = "";
    }
    if (current !== content) {
      console.error(`${path} is stale — run \`npm run build:web\``);
      process.exitCode = 1;
      return false;
    }
    return true;
  }
  writeFileSync(path, content, "utf8");
  return true;
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
  ["styles.css", readFileSync(join(outDir, "styles.css"), "utf8"), "css"],
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
