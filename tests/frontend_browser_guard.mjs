import { existsSync } from "node:fs";
import { chromium } from "playwright";
import { deferredExit } from "./web_smoke_suites.mjs";

export const BROWSER_MISSING_CODE = "HARNESS_BROWSER_MISSING";
export const BROWSER_MISSING_EXIT = 3;

const exitAndStop = (code) => {
  deferredExit(code);
  // The caller must not reach chromium.launch while the deferred exit is pending.
  return new Promise(() => {});
};

export async function requireBrowserOrExit({
  chromiumImpl = chromium,
  existsImpl = existsSync,
  exitImpl = exitAndStop,
  writeImpl = (line) => console.error(line),
} = {}) {
  const executablePath = chromiumImpl.executablePath();
  if (existsImpl(executablePath)) return { ok: true, executablePath };

  writeImpl(`SMOKE_FAILURE_CODE=${BROWSER_MISSING_CODE}`);
  writeImpl(
    [
      `${BROWSER_MISSING_CODE}: Chromium is not installed at ${executablePath}.`,
      "Run `npx playwright install chromium` (CI uses `npx playwright install chromium --with-deps`).",
      `The suite is exiting ${BROWSER_MISSING_EXIT} without launching a browser: no browser assertions ran, so nothing this step ` +
        "reports says anything about the product.",
    ].join(" "),
  );
  return exitImpl(BROWSER_MISSING_EXIT);
}
