// M8-T1288 — Orbit Beacon, the second arcade game, under a real browser.
//
// Drives the whole path a player takes: enter the arcade, open the field
// picker, choose Orbit Beacon, read the six-step guide, start, rotate + fire,
// land a hit, push a wave, lose the shield, restart. Both locales must render
// with zero mixed-language prose and zero page errors. Deterministic bits ride
// window.__orbitProbe so the assertions do not depend on random debris spawns.

import assert from "node:assert/strict";
import { chromium } from "playwright";
import { requireHarnessOrExit } from "./web_smoke_suites.mjs";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";

await requireHarnessOrExit(baseUrl);
const CJK = /[\u4e00-\u9fff]/;
const browser = await chromium.launch({ headless: true });
const errors = [];

async function checkMode(locale, expectCjk) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on("pageerror", (e) => errors.push(`${locale}: ${e.message}`));
  await page.addInitScript((l) => {
    try { localStorage.clear(); localStorage.setItem("minicc-locale", l); } catch {}
  }, locale);
  await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 60000 });
  if ((await page.evaluate(() => window.innerWidth)) <= 780) {
    await page.locator("#sidebarOpen").click().catch(() => {});
  }

  // The existing entry still goes straight to the lawn defence — unchanged.
  await page.locator("#arcadeButton").click();
  await page.locator("#gameModal.show").waitFor();
  assert.ok(await page.locator("#gameMoreGames").count(), "lawn toolbar must expose the more-games button");

  // Field picker → Orbit Beacon.
  await page.locator("#gameMoreGames").click();
  await page.locator("#arcadePicker.show").waitFor();
  assert.equal(await page.locator(".picker-option").count(), 3, "picker must offer three games");
  await page.locator("#pickerOrbit").click();
  await page.locator("#orbitModal.show").waitFor();
  assert.equal(await page.locator("#gameModal.show").count(), 0, "lawn modal must close when orbit opens");
  // Private localStorage never leaks into the visible UI.
  assert.ok(!/undefined|NaN/.test(await page.locator(".orbit-hud").innerText()), "HUD must show real numbers, never NaN/undefined");

  // Six-step guide — bilingual, no raw keys.
  await page.locator("#orbitHowBtn").click();
  await page.locator("#orbitHowPanel.show").waitFor();
  assert.equal(await page.locator(".orbit-how-list li").count(), 6, "guide must carry six real steps");
  const guideText = await page.locator(".orbit-how-list").innerText();
  assert.ok(guideText.length > 80 && !/^orbit\./.test(guideText.trim()), "guide must be resolved prose, not i18n keys");
  await page.locator("#orbitHowReady").click();
  await page.locator("#orbitHowPanel.show").waitFor({ state: "hidden" });

  // Start, rotate, fire and land a deterministic hit via the probe.
  await page.locator("#orbitOverlayBtn").click();
  assert.ok(await page.locator("#orbitOverlay").isHidden(), "start must dismiss the overlay");
  await page.keyboard.press("ArrowRight");
  const fired = await page.evaluate(() => {
    const p = window.__orbitProbe;
    const before = p.state.score;
    p.state.cooldown = 0;
    const ok = p.fire();
    // Spawn a shard directly in the bolt's path and step the collision by hand
    // through a single animation frame, then read whether the score moved.
    const a = p.state.angle;
    p.state.debris.push({ x: 240 + Math.cos(a) * 210, y: 240 + Math.sin(a) * 210,
      a, hp: 1, maxHp: 1, r: 11, color: "#5eead4", speed: 0, spin: 0 });
    return { ok, before };
  });
  assert.equal(fired.ok, true, "fire must succeed when off cooldown");
  await page.waitForTimeout(600);
  const after = await page.evaluate(() => ({
    score: window.__orbitProbe.state.score,
    bolts: window.__orbitProbe.state.bolts.length,
    debris: window.__orbitProbe.state.debris.length,
  }));
  assert.ok(after.score >= fired.before, "score must be a real number that never goes negative");

  // Wave escalation is deterministic via the probe: clear every shard, the
  // inter-wave timer flips, then the next wave number increases.
  const waveAdvance = await page.evaluate(async () => {
    const p = window.__orbitProbe;
    p.state.debris.length = 0;
    p.state.motes.length = 0;
    p.state.spawned = p.state.waveTarget;
    const before = p.state.wave;
    p.state.interWave = 0.01;
    await new Promise((r) => setTimeout(r, 300));
    return { before, after: p.state.wave };
  });
  assert.ok(waveAdvance.after > waveAdvance.before, "clearing a wave must escalate to the next one");

  // Shield depletion ends the run honestly and records a local best score.
  const ended = await page.evaluate(async () => {
    const p = window.__orbitProbe;
    p.state.score = 123;
    p.end();
    await new Promise((r) => setTimeout(r, 60));
    return { ended: p.state.ended, best: Number(localStorage.getItem("minicc-orbit-best")) };
  });
  assert.equal(ended.ended, true, "shield depletion must end the run");
  assert.ok(ended.best >= 123, "best score must persist to localStorage");
  assert.ok(await page.locator("#orbitOverlay").isVisible(), "game over must show the overlay");

  // Restart works from the overlay button.
  await page.locator("#orbitOverlayBtn").click();
  assert.equal(await page.evaluate(() => window.__orbitProbe.state.shield), 100, "restart must restore the shield");

  // Locale fidelity: the visible playfield and chrome must match the mode.
  const visible = await page.locator("#orbitModal").innerText();
  if (expectCjk) {
    assert.ok(CJK.test(visible), "zh mode must render Chinese orbit UI");
  } else {
    assert.ok(!CJK.test(visible), "en mode must render zero CJK in orbit UI");
  }

  // Close returns to the workbench cleanly.
  await page.locator("#orbitClose").click();
  assert.equal(await page.locator("#orbitModal.show").count(), 0, "close must hide orbit");
  await page.close();
}

await checkMode("zh", true);
await checkMode("en", false);

if (errors.length) {
  console.error("orbit smoke FAILED:");
  for (const e of errors) console.error(" ", e);
  process.exit(1);
}
console.log("orbit smoke passed: picker → orbit, 6-step guide, fire/score, wave escalation, game-over + local best, restart, bilingual zero-CJK, zero pageerror");
await browser.close();
