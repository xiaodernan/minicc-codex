import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";
const screenshotsDir = "output";

function state(page, expression) {
  return page.evaluate((source) => window.eval(source), expression);
}

async function assertCanvasPainted(page) {
  const paintedPixels = await page.locator("#gameCanvas").evaluate((canvas) => {
    const context = canvas.getContext("2d");
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let index = 3; index < pixels.length; index += 64) count += pixels[index] > 0 ? 1 : 0;
    return count;
  });
  assert.ok(paintedPixels > 100, "game canvas should contain rendered pixels");
}

async function openGame(page) {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const arcadeButton = page.locator("#arcadeButton");
  if ((await page.evaluate(() => window.innerWidth)) <= 780) {
    await page.locator("#sidebarOpen").click();
    await page.locator(".sidebar.open").waitFor();
  }
  await arcadeButton.click();
  await page.locator("#gameModal.show").waitFor();
  await assertCanvasPainted(page);
}

async function runDesktopSmoke(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const initialTheme = await state(page, "document.documentElement.dataset.theme");
  await page.locator("#themeButton").click();
  const toggledTheme = await state(page, "document.documentElement.dataset.theme");
  assert.notEqual(toggledTheme, initialTheme, "theme control should switch theme");
  assert.equal(await state(page, "localStorage.getItem('minicc-theme')"), toggledTheme, "theme preference should persist");
  if (toggledTheme !== "light") await page.locator("#themeButton").click();
  assert.equal(await state(page, "document.documentElement.dataset.theme"), "light", "theme control should enable light mode");
  assert.match(await page.locator("#themeButton").getAttribute("aria-label"), /暗色|dark/i);
  await page.reload({ waitUntil: "networkidle" });
  assert.equal(await state(page, "document.documentElement.dataset.theme"), "light", "light preference should survive reload");
  await openGame(page);
  await page.locator("#gameDifficulty").selectOption("normal");
  assert.deepEqual(await state(page, "({ difficulty: game.difficulty, sun: game.sun, target: game.waveTarget })"), {
    difficulty: "normal", sun: 200, target: 8,
  });
  await page.locator("#gameDifficulty").selectOption("nightmare");
  assert.deepEqual(await state(page, "({ difficulty: game.difficulty, sun: game.sun, target: game.waveTarget })"), {
    difficulty: "nightmare", sun: 150, target: 11,
  });

  await page.locator("#gameStart").click();
  await page.waitForTimeout(120);
  const audioStarted = await state(page, "({ running: game.running, hasAudio: Boolean(game.audio), audioState: game.audio?.ctx?.state || null })");
  assert.equal(audioStarted.running, true, "start button should begin a battle");
  assert.equal(audioStarted.hasAudio, true, "a user gesture should initialize Web Audio when available");
  assert.ok(["running", "suspended"].includes(audioStarted.audioState), "audio context should be initialized");

  await page.locator("#gameVolume").evaluate((input) => {
    input.value = "35";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  assert.deepEqual(await state(page, "({ volume: game.volume, master: Boolean(game.audio?.master) })"), { volume: 35, master: true });
  await page.locator("#gameSoundToggle").click();
  assert.equal(await state(page, "game.musicOn"), false, "sound toggle should disable sound");
  await page.locator("#gameSoundToggle").click();
  assert.equal(await state(page, "game.musicOn"), true, "sound toggle should re-enable sound");

  await page.locator("#gamePause").click();
  const manualPauseStart = await state(page, "game.elapsed");
  await page.waitForTimeout(140);
  assert.equal(await state(page, "game.elapsed"), manualPauseStart, "manual pause must freeze elapsed time");
  await page.locator("#gamePause").click();
  await page.waitForTimeout(80);
  assert.ok(await state(page, "game.elapsed") > manualPauseStart, "resume should advance elapsed time");

  await state(page, "Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange'))");
  const hiddenPauseStart = await state(page, "game.elapsed");
  assert.equal(await state(page, "game.pauseReasons.has('visibility') && game.paused"), true, "visibility change should pause the battle");
  await page.waitForTimeout(140);
  assert.equal(await state(page, "game.elapsed"), hiddenPauseStart, "hidden page must freeze elapsed time");
  await state(page, "Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange'))");
  await page.waitForTimeout(80);
  assert.equal(await state(page, "game.paused"), false, "visible page should resume when no manual pause remains");

  await state(page, "game.elapsed = 3600000; game.zombies = []; game.last = performance.now(); gameLoop(performance.now() + 16); game.paused = true; cancelAnimationFrame(game.frame)");
  assert.equal(await state(page, "game.running"), true, "a long elapsed battle must not fail because time expired");

  await state(page, "game.paused = false; game.last = performance.now(); game.zombies = [{ row: 0, x: 55, y: 0, slowTimer: 0, speed: 0, attackInterval: 1000, hp: 1, maxHp: 1, type: 'basic', seed: 0 }]; gameLoop(performance.now() + 16)");
  assert.deepEqual(await state(page, "({ running: game.running, status: document.querySelector('#gameStatus').textContent })"), {
    running: false, status: "僵尸进屋了",
  });

  await page.screenshot({ path: `${screenshotsDir}/game-smoke-desktop.png`, fullPage: true });
  assert.deepEqual(consoleErrors, [], `desktop browser errors: ${consoleErrors.join(" | ")}`);
  await page.close();
}

async function runAudioFallbackSmoke(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.addInitScript(() => {
    Object.defineProperty(window, "AudioContext", { configurable: true, value: undefined });
    Object.defineProperty(window, "webkitAudioContext", { configurable: true, value: undefined });
  });
  await openGame(page);
  await page.locator("#gameStart").click();
  await page.waitForTimeout(80);
  assert.deepEqual(await state(page, "({ running: game.running, audio: game.audio })"), { running: true, audio: null }, "gameplay must run without Web Audio");
  await assertCanvasPainted(page);
  assert.deepEqual(consoleErrors, [], `audio fallback browser errors: ${consoleErrors.join(" | ")}`);
  await page.close();
}

async function runMobileSmoke(browser) {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 1 });
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await openGame(page);
  await page.locator("#gameStart").click();
  await page.waitForTimeout(80);
  const layout = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    modalWidth: document.querySelector("#gameModal .game-card").getBoundingClientRect().width,
    canvasWidth: document.querySelector("#gameCanvas").getBoundingClientRect().width,
  }));
  assert.ok(layout.documentWidth <= layout.viewport + 1, `mobile page should not overflow horizontally: ${JSON.stringify(layout)}`);
  assert.ok(layout.modalWidth <= layout.viewport, `mobile modal should fit viewport: ${JSON.stringify(layout)}`);
  assert.ok(layout.canvasWidth <= layout.modalWidth, `mobile canvas should fit its panel: ${JSON.stringify(layout)}`);
  await page.screenshot({ path: `${screenshotsDir}/game-smoke-mobile.png`, fullPage: true });
  assert.deepEqual(consoleErrors, [], `mobile browser errors: ${consoleErrors.join(" | ")}`);
  await page.close();
}

await mkdir(screenshotsDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  await runDesktopSmoke(browser);
  await runAudioFallbackSmoke(browser);
  await runMobileSmoke(browser);
  console.log("web smoke passed: desktop, audio fallback, mobile");
} finally {
  await browser.close();
}
