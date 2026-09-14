// Build the web workbench's classic-script bundle from ordered source chunks.
//
// web/src/*.js are plain-script chunks that intentionally share one scope
// (no ES module imports): concatenation in filename order reproduces the
// original app.js byte for byte. esbuild is optional — when installed we
// also emit a minified app.min.js next to the readable bundle.
//
// Usage: node scripts/build-web.mjs [--check]

import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const srcDir = join(root, "web", "src");
const outFile = join(root, "web", "app.js");
const minFile = join(root, "web", "app.min.js");

const chunks = readdirSync(srcDir).filter((name) => name.endsWith(".js")).sort();
if (chunks.length === 0) throw new Error("no source chunks found in web/src");

let bundle = "";
for (const name of chunks) {
  const raw = readFileSync(join(srcDir, name), "utf8");
  // The per-chunk provenance note (first line) is stripped so the readable
  // bundle stays byte-identical to the pre-split original.
  const lines = raw.split("\n");
  const body = lines[0].startsWith("// NOTE:") ? lines.slice(1).join("\n") : raw;
  bundle += body;
}

const check = process.argv.includes("--check");
if (check) {
  const current = readFileSync(outFile, "utf8");
  if (current !== bundle) {
    console.error("web/app.js is stale — run `npm run build:web`");
    process.exit(1);
  }
  console.log(`web/app.js is up to date (${bundle.length} chars, ${chunks.length} chunks)`);
} else {
  writeFileSync(outFile, bundle, "utf8");
  console.log(`built web/app.js (${bundle.length} chars, ${chunks.length} chunks)`);
}

// Optional minified artifact (local-first: readable app.js remains the default).
try {
  const { transform } = await import("esbuild");
  const minified = await transform(bundle, { loader: "js", minify: true, target: "es2020" });
  writeFileSync(minFile, minified.code, "utf8");
  console.log(`built web/app.min.js (${minified.code.length} chars, minified)`);
} catch (error) {
  if (check) throw error;
  console.log("esbuild not installed — skipped web/app.min.js");
}
