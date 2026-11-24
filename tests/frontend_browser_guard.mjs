import { existsSync } from "node:fs";
import { chromium } from "playwright";
import { deferredExit } from "./web_smoke_suites.mjs";

export const BROWSER_MISSING_CODE = "HARNESS_BROWSER_MISSING";
export const BROWSER_UNUSABLE_CODE = "HARNESS_BROWSER_UNUSABLE";
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
  if (existsImpl(executablePath)) {
    // M8-T1327: a file on disk is not a browser that starts. Missing system
    // libraries, a wrong architecture or a corrupt install all pass existsSync
    // and then throw a raw Playwright stack from the suite's own launch — an
    // unattributed product failure. Prove it can start once, before the suite.
    // Injected fakes without launch() skip this, so the unit seam stays cheap.
    if (typeof chromiumImpl.launch === "function") {
      let browser = null;
      try {
        browser = await chromiumImpl.launch({ headless: true, timeout: 30000 });
      } catch (error) {
        writeImpl(`SMOKE_FAILURE_CODE=${BROWSER_UNUSABLE_CODE}`);
        writeImpl(
          [
            `${BROWSER_UNUSABLE_CODE}: Chromium exists at ${executablePath} but could not start ` +
              `(${(error && error.message) || error}).`,
            "Install the system libraries with `npx playwright install chromium --with-deps` and re-run.",
            `The suite is exiting ${BROWSER_MISSING_EXIT} without launching its own browser: ` +
              "no browser assertions ran, so this step says nothing about the product.",
          ].join(" "),
        );
        return exitImpl(BROWSER_MISSING_EXIT);
      } finally {
        if (browser) await browser.close().catch(() => {});
      }
    }
    return { ok: true, executablePath };
  }

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
