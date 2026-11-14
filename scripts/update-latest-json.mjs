/**
 * docs/latest.json — the machine-readable face of the project for the
 * personal showcase (xiaodernan.github.io) to render on a low-frequency
 * schedule. No secrets, no cross-repo token; reads only local git + this
 * repository's own documents.
 *
 * Intentionally small, intentionally boring, intentionally stable. When a
 * field disappears here, the showcase falls back to its last-known value —
 * so deletions are deliberate, never accidental.
 */
import { execSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const DOC_PATH = join(ROOT, "docs", "ROADMAP_TO_PRODUCT.md");
const CHANGE_PATH = join(ROOT, "docs", "CHANGELOG.md");
const OUT_PATH = join(ROOT, "docs", "latest.json");

function sh(command) {
  try {
    return execSync(command, { cwd: ROOT, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 }).trim();
  } catch {
    return null;
  }
}

function gitDateOfRoot() {
  const root = sh("git rev-list --max-parents=0 HEAD")?.split("\n")[0]?.trim();
  if (!root) return "";
  return sh(`git show -s --format=%cI ${root}`) ?? "";
}

const head = sh("git rev-parse HEAD") ?? "";
const headShort = head.slice(0, 7);
const branch = sh("git rev-parse --abbrev-ref HEAD") ?? "main";
const totalCommits = Number(sh("git rev-list --count HEAD") ?? "0") || 0;
const firstFull = gitDateOfRoot();
const firstCommitDate = firstFull.includes("T") ? firstFull.slice(0, firstFull.indexOf("T")) : firstFull;

const roadmap = readFileSync(DOC_PATH, "utf-8");
const batchSections = (roadmap.match(/^## 批次 \d+/gm) ?? []).length;
const changelog = readFileSync(CHANGE_PATH, "utf-8");
const changelogEntries = (changelog.match(/^## /gm) ?? []).length;
const trackedFiles = (sh("git ls-files") ?? "").split("\n").filter((l) => l.trim()).length;
const testFiles = (sh("git ls-files tests/") ?? "").split("\n").filter((l) => /\.(py|mjs)$/.test(l)).length;
const roadmapLines = roadmap.split("\n").length;

const payload = {
  schema_version: "minicc.latest.v1",
  generated_at: new Date().toISOString(),
  branch,
  head: headShort,
  total_commits: totalCommits,
  first_commit_at: firstCommitDate,
  roadmap_batches: batchSections,
  changelog_entries: changelogEntries,
  roadmap_lines: roadmapLines,
  tracked_files: trackedFiles,
  test_files: testFiles,
  almanac_chapters: 9,
  feature_surface: [
    "workbench",
    "ledger",
    "pulse",
    "almanac",
    "templates",
    "replay",
    "running-light",
    "spring-cloud-plane",
    "redis-cache",
    "cached-first-call",
    "cli-digest",
    "api-digest",
    "manual",
  ],
  headline: "minicc-codex - a local-first coding workbench where the model, the tools, and the gates all answer to you.",
};

writeFileSync(OUT_PATH, JSON.stringify(payload, null, 2) + "\n", "utf-8");
console.log(`wrote ${OUT_PATH}`);
