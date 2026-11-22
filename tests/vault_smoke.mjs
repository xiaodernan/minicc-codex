// M8-T1291 — Prefix Vault, the third arcade game, under a real browser.
//
// Walks the exact route a player takes: arcade → field picker → Prefix Vault →
// five-step guide → cache a prefix → hit it → evict least-recently-used →
// lose the last life → restart. Deterministic steps use window.__vaultProbe so
// the assertions never depend on the random prefix generator or wall clock.
// Both locales must render zero mixed-language prose and zero page errors.

import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";
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

  await page.locator("#arcadeButton").click();
  await page.locator("#gameModal.show").waitFor();
  await page.locator("#gameMoreGames").click();
  await page.locator("#arcadePicker.show").waitFor();
  assert.equal(await page.locator(".picker-option").count(), 3, "picker must offer three fields");
  await page.locator("#pickerVault").click();
  await page.locator("#vaultModal.show").waitFor();
  assert.equal(await page.locator("#orbitModal.show").count(), 0, "orbit must be closed when vault opens");
  const hud = await page.locator(".vault-hud").innerText();
  assert.ok(!/undefined|NaN/.test(hud), "vault HUD must show real numbers only");

  // Guide: five real steps, resolved prose, dismissible.
  await page.locator("#vaultHowBtn").click();
  await page.locator("#vaultHowPanel.show").waitFor();
  assert.equal(await page.locator("#vaultHowPanel .orbit-how-list li").count(), 5, "guide must carry five real steps");
  const guide = await page.locator("#vaultHowPanel .orbit-how-list").innerText();
  assert.ok(guide.length > 80 && !/^vault\./.test(guide.trim()), "guide must be resolved prose, not i18n keys");
  await page.locator("#vaultHowReady").click();
  await page.locator("#vaultHowPanel.show").waitFor({ state: "hidden" });

  await page.locator("#vaultOverlayBtn").click();
  assert.ok(await page.locator("#vaultOverlay").isHidden(), "start must dismiss the overlay");

  // Cache a deterministic prefix, then hit it by clicking its slot.
  const cached = await page.evaluate(() => {
    const p = window.__vaultProbe;
    p.state.score = 50;
    p.forceRequest("A");
    const index = p.state.slots.findIndex((s) => s.prefix === null);
    const before = p.state.score;
    document.querySelector("#vaultCacheBtn").click();
    return { index, scoreAfterCache: p.state.score, before };
  });
  assert.ok(cached.index >= 0, "a fresh game must have an empty slot");
  assert.ok(cached.scoreAfterCache < cached.before, "filling a slot must cost tokens honestly");
  const hit = await page.evaluate((index) => {
    const p = window.__vaultProbe;
    p.forceRequest("A");
    const before = p.state.score;
    document.querySelector(`[data-slot="${index}"]`).click();
    return { before, after: p.state.score, hits: p.state.hits, combo: p.state.combo };
  }, cached.index);
  assert.equal(hit.hits, 1, "matching prefix must count as a real hit");
  assert.equal(hit.combo, 1, "a hit must build combo");
  assert.ok(hit.after > hit.before, "a hit must score above the bare request value");

  // Fill every slot, then evict the least recently used one.
  const evicted = await page.evaluate(() => {
    const p = window.__vaultProbe;
    p.state.slots = ["A", "B", "C", "D", "E", "F"].map((prefix, i) => ({ prefix, used: i }));
    p.forceRequest("Z");
    document.querySelector("#vaultEvictBtn").click();
    return p.state.slots.map((s) => s.prefix);
  });
  assert.equal(evicted[0], "Z", "eviction must replace the least recently used slot");
  assert.equal(evicted.length, 6, "slot count must stay bounded");

  // A wrong click is a miss; the last miss ends the run and records a real best.
  const ended = await page.evaluate(() => {
    const p = window.__vaultProbe;
    p.state.lives = 1;
    p.state.score = 300;
    p.state.slots[1] = { prefix: "K", used: 0 };
    p.forceRequest("K");
    p.state.request.cost = 100;
    document.querySelector('[data-slot="1"]').click(); // real hit, persists best
    const scored = p.state.score;
    p.forceRequest("Q");
    const wrong = p.state.slots.findIndex((s) => s.prefix !== "Q");
    document.querySelector(`[data-slot="${wrong}"]`).click();
    return {
      ended: p.state.ended,
      lives: p.state.lives,
      scored,
      best: Number(localStorage.getItem("minicc-vault-best")),
    };
  });
  assert.equal(ended.ended, true, "the last wrong click must end the run");
  assert.equal(ended.lives, 0, "lives must be a real number that reaches zero");
  assert.ok(ended.best >= ended.scored, "best score must persist locally through a real hit");
  assert.ok(await page.locator("#vaultOverlay").isVisible(), "game over must show the overlay");

  await page.locator("#vaultOverlayBtn").click();
  assert.equal(await page.evaluate(() => window.__vaultProbe.state.lives), 5, "restart must restore five lives");

  const visible = await page.locator("#vaultModal").innerText();
  if (expectCjk) assert.ok(CJK.test(visible), "zh mode must render Chinese vault UI");
  else assert.ok(!CJK.test(visible), "en mode must render zero CJK in vault UI");

  await page.locator("#vaultClose").click();
  assert.equal(await page.locator("#vaultModal.show").count(), 0, "close must hide vault");
  await page.close();
}

await checkMode("zh", true);
await checkMode("en", false);

if (errors.length) {
  console.error("vault smoke FAILED:");
  for (const e of errors) console.error(" ", e);
  process.exit(1);
}
console.log("vault smoke passed: picker → vault, 5-step guide, cache/hit/evict economy, last-life game over + local best, restart, bilingual zero-CJK, zero pageerror");
await browser.close();
