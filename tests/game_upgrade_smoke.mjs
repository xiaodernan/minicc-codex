import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";
const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("https://unpkg.com/**", (route) => route.fulfill({ status: 200, contentType: "application/javascript", body: "" }));
  await page.route("**/app.js", async (route) => {
    const response = await route.fetch();
    const body = await response.text();
    await route.fulfill({ response, body: `${body}\nwindow.__gameUpgradeProbe = { game, gameLoop, defeatZombie, rebuildGameIndexes, activateGameSkill };` });
  });

  await page.goto(`${baseUrl}/?arcade=1`, { waitUntil: "networkidle" });
  await page.locator("#gameModal.show").waitFor();
  await page.waitForFunction(() => window.__gameUpgradeProbe);

  const initial = await page.evaluate(() => ({
    mowerCount: window.__gameUpgradeProbe.game.mowers.length,
    combo: window.__gameUpgradeProbe.game.combo,
    popups: window.__gameUpgradeProbe.game.popups.length,
  }));
  assert.deepEqual(initial, { mowerCount: 5, combo: 0, popups: 0 });

  await page.locator(".game-toggle").click();
  await page.locator("#gameStart").click();
  await page.waitForFunction(() => window.__gameUpgradeProbe.game.running);

  const skillResult = await page.evaluate(() => {
    const { game, rebuildGameIndexes } = window.__gameUpgradeProbe;
    game.energy = 60;
    game.skillCooldowns = {};
    game.zombies = [{ x: 410, y: 104, row: 0, hp: 20, maxHp: 20, armor: 0, type: "walker", speed: 0, slowTimer: 0, flashTimer: 0 }];
    rebuildGameIndexes();
    return { energy: game.energy, zombieHp: game.zombies[0].hp };
  });
  await page.waitForFunction(() => !document.querySelector('[data-skill="pulse"]').disabled);
  await page.locator('[data-skill="pulse"]').click();
  const pulseAfter = await page.evaluate(() => ({
    energy: window.__gameUpgradeProbe.game.energy,
    cooldown: window.__gameUpgradeProbe.game.skillCooldowns.pulse,
    zombieHp: window.__gameUpgradeProbe.game.zombies[0]?.hp,
    slowTimer: window.__gameUpgradeProbe.game.zombies[0]?.slowTimer,
  }));
  assert.equal(skillResult.energy, 60);
  assert.equal(pulseAfter.energy, 35);
  assert.ok(pulseAfter.cooldown > 0);
  assert.equal(pulseAfter.zombieHp, 16);
  assert.ok(pulseAfter.slowTimer > 0);
  assert.equal(await page.locator('[data-skill="pulse"]').isDisabled(), true);

  await page.evaluate(() => { window.__gameUpgradeProbe.game.energy = 60; window.__gameUpgradeProbe.game.skillCooldowns = {}; });
  await page.waitForFunction(() => !document.querySelector('[data-skill="sun"]').disabled);
  const sunBeforeSkill = await page.evaluate(() => window.__gameUpgradeProbe.game.sun);
  await page.locator('[data-skill="sun"]').click();
  const sunAfterSkill = await page.evaluate(() => ({ energy: window.__gameUpgradeProbe.game.energy, sun: window.__gameUpgradeProbe.game.sun, cooldown: window.__gameUpgradeProbe.game.skillCooldowns.sun }));
  assert.equal(sunAfterSkill.energy, 25);
  assert.equal(sunAfterSkill.sun, sunBeforeSkill + 100);
  assert.ok(sunAfterSkill.cooldown > 0);

  await page.evaluate(() => { window.__gameUpgradeProbe.game.energy = 100; window.__gameUpgradeProbe.game.skillCooldowns = {}; });
  await page.waitForFunction(() => !document.querySelector('[data-skill="rally"]').disabled);
  await page.locator('[data-skill="rally"]').click();
  const rallyAfterSkill = await page.evaluate(() => ({ energy: window.__gameUpgradeProbe.game.energy, rallyTimer: window.__gameUpgradeProbe.game.rallyTimer, cooldown: window.__gameUpgradeProbe.game.skillCooldowns.rally }));
  assert.equal(rallyAfterSkill.energy, 55);
  assert.ok(rallyAfterSkill.rallyTimer > 0);
  assert.ok(rallyAfterSkill.cooldown > 0);

  await page.evaluate(() => {
    const { game } = window.__gameUpgradeProbe;
    game.energy = 100;
    game.skillCooldowns = {};
    game.zombies = [{ x: 410, y: 104, row: 0, hp: 20, maxHp: 20, armor: 0, type: "walker", speed: 1.2, slowTimer: 0, flashTimer: 0 }];
    game.plants = [];
    game.shots = [];
    game.timeStopTimer = 0;
  });
  await page.waitForFunction(() => !document.querySelector('[data-skill="timeStop"]').disabled);
  await page.locator('[data-skill="timeStop"]').click();
  const timeStopAtActivation = await page.evaluate(() => ({ x: window.__gameUpgradeProbe.game.zombies[0]?.x, hp: window.__gameUpgradeProbe.game.zombies[0]?.hp }));
  await page.waitForTimeout(140);
  const timeStopAfter = await page.evaluate(() => ({
    energy: window.__gameUpgradeProbe.game.energy,
    cooldown: window.__gameUpgradeProbe.game.skillCooldowns.timeStop,
    timer: window.__gameUpgradeProbe.game.timeStopTimer,
    x: window.__gameUpgradeProbe.game.zombies[0]?.x,
    hp: window.__gameUpgradeProbe.game.zombies[0]?.hp,
    impacts: window.__gameUpgradeProbe.game.impacts.length,
  }));
  assert.equal(timeStopAfter.energy, 45);
  assert.ok(timeStopAfter.cooldown > 0);
  assert.ok(timeStopAfter.timer > 0);
  assert.equal(timeStopAfter.x, timeStopAtActivation.x);
  assert.equal(timeStopAfter.hp, timeStopAtActivation.hp);
  assert.ok(timeStopAfter.impacts > 0);

  await page.locator("#gamePause").click();
  assert.equal(await page.evaluate(() => window.__gameUpgradeProbe.game.paused), true);
  await page.locator("#gamePause").click();
  assert.equal(await page.evaluate(() => window.__gameUpgradeProbe.game.paused), false);

  const motionResult = await page.evaluate(() => {
    const probe = window.__gameUpgradeProbe;
    const game = probe.game;
    const stop = () => { game.running = false; cancelAnimationFrame(game.frame); };
    game.running = true;
    game.paused = false;
    game.waveSpawned = game.waveTarget = 999;
    game.spawnTimer = game.skyTimer = game.dangerTimer = 0;
    game.waveClearTimer = 0;
    game.timeStopTimer = 0;
    game.plants = [{ type: "wallnut", hp: 100, row: 0, col: 2, seed: 1, age: 0, sunTimer: 0, shotTimer: 0, bombTimer: 0, disabledTimer: 0 }];
    const zombie = { x: 253, y: 104, row: 0, hp: 20, maxHp: 20, armor: 0, type: "walker", speed: 0, attackInterval: 1000, slowTimer: 0, burrowTimer: 0, seed: 2, garlicTimer: 0, vaultTimer: 0, summonTimer: 0, flashTimer: 0, attackTimer: 0, attacking: false, staggerTimer: 0 };
    game.zombies = [zombie];
    game.shots = [];
    game.particles = [];
    game.impacts = [];
    game.popups = [];
    game.defeated = [];
    game.last = 0;
    probe.rebuildGameIndexes();
    probe.gameLoop(16);
    const engaged = { attacking: zombie.attacking, attackTimer: zombie.attackTimer };
    for (let now = 96; now <= 1136; now += 80) probe.gameLoop(now);
    const attackPulse = zombie.attackFlashTimer > 0;
    game.shots = [{ x: zombie.x - 30, y: zombie.y, row: zombie.row, damage: 1, hitsLeft: 1, hit: false, color: "#b7f3a0" }];
    probe.gameLoop(1216);
    const result = { ...engaged, attackPulse, staggerTimer: zombie.staggerTimer, flashTimer: zombie.flashTimer, running: game.running, paused: game.paused, last: game.last, zombieX: zombie.x, shots: game.shots.length, zombieCount: game.zombies.length };
    stop();
    return result;
  });
  assert.equal(motionResult.attacking, true);
  assert.ok(motionResult.attackTimer > 0, `zombie should advance its attack cycle: ${JSON.stringify(motionResult)}`);
  assert.equal(motionResult.attackPulse, true, `zombie attack should show a visible strike pulse: ${JSON.stringify(motionResult)}`);
  assert.ok(motionResult.staggerTimer > 0, `projectile hit should trigger hit-stagger: ${JSON.stringify(motionResult)}`);
  assert.ok(motionResult.flashTimer > 0, `projectile hit should trigger hit feedback: ${JSON.stringify(motionResult)}`);

  await page.locator("#gameStart").click();
  await page.waitForFunction(() => window.__gameUpgradeProbe.game.running && !window.__gameUpgradeProbe.game.paused);
  await page.locator('[data-plant="peashooter"]').click();
  const canvas = page.locator("#gameCanvas");
  const box = await canvas.boundingBox();
  assert.ok(box);
  await page.mouse.move(box.x + box.width * 113 / 720, box.y + box.height * 103 / 420);
  await page.waitForFunction(() => window.__gameUpgradeProbe.game.hoverCell?.row === 0 && window.__gameUpgradeProbe.game.hoverCell?.col === 0);
  const hover = await page.evaluate(() => ({ ...window.__gameUpgradeProbe.game.hoverCell }));
  assert.deepEqual(hover, { row: 0, col: 0 });

  const mowerResult = await page.evaluate(() => {
    const probe = window.__gameUpgradeProbe;
    const game = probe.game;
    const stop = () => { game.running = false; cancelAnimationFrame(game.frame); };
    game.paused = false;
    game.pauseReasons = new Set();
    game.waveSpawned = game.waveTarget = 999;
    game.spawnTimer = game.skyTimer = game.dangerTimer = 0;
    game.zombies = [{
      x: 88, y: 0, row: 0, hp: 5, maxHp: 5, armor: 0, type: "walker", speed: 0,
      attackInterval: 1000, slowTimer: 0, burrowTimer: 0, seed: 1, garlicTimer: 0,
      vaultTimer: 0, summonTimer: 0, flashTimer: 0, dashTimer: 0, leapTimer: 0,
      chargeTimer: 0, curseTimer: 0, breathTimer: 0, smashTimer: 0, armorTimer: 0,
      guardTimer: 0, burnTimer: 0, burnTickTimer: 0, stormTimer: 0, markTimer: 0,
    }];
    game.plants = [];
    game.shots = [];
    game.suns = [];
    game.particles = [];
    game.impacts = [];
    game.popups = [];
    game.defeated = [];
    game.combo = 0;
    game.comboTimer = 0;
    game.score = 0;
    game.mowers.forEach((mower) => { mower.x = 57; mower.active = false; mower.used = false; });
    game.running = true;
    game.last = 0;
    probe.gameLoop(16);
    const result = {
      zombies: game.zombies.length,
      mowerUsed: game.mowers[0].used,
      mowerActive: game.mowers[0].active,
      combo: game.combo,
      score: game.score,
      popups: game.popups.length,
      dangerPulse: game.dangerPulse,
    };
    stop();
    return result;
  });
  assert.equal(mowerResult.zombies, 0, `mower should clear a breached lane: ${JSON.stringify(mowerResult)}`);
  assert.equal(mowerResult.mowerUsed, true);
  assert.equal(mowerResult.mowerActive, true);
  assert.equal(mowerResult.combo, 1);
  assert.equal(mowerResult.score, 1);
  assert.ok(mowerResult.popups >= 2, `kill and mower feedback should be visible: ${JSON.stringify(mowerResult)}`);
  assert.ok(mowerResult.dangerPulse > 0);

  const comboResult = await page.evaluate(() => {
    const probe = window.__gameUpgradeProbe;
    const game = probe.game;
    const makeZombie = (x) => ({ x, y: 104, row: 0, hp: 1, maxHp: 1, armor: 0, type: "walker" });
    const first = makeZombie(300);
    const second = makeZombie(330);
    game.zombies = [first, second];
    game.defeated = [];
    game.popups = [];
    game.combo = 0;
    game.comboTimer = 0;
    game.score = 0;
    probe.rebuildGameIndexes();
    const firstDefeated = probe.defeatZombie(first);
    const secondDefeated = probe.defeatZombie(second);
    return { firstDefeated, secondDefeated, combo: game.combo, bestCombo: game.bestCombo, score: game.score, zombies: game.zombies.length, popups: game.popups.length };
  });
  assert.deepEqual(comboResult, { firstDefeated: true, secondDefeated: true, combo: 2, bestCombo: 2, score: 2, zombies: 0, popups: 2 });

  await page.locator("#gameStart").click();
  await page.waitForFunction(() => window.__gameUpgradeProbe.game.running);
  await page.waitForTimeout(1200);
  const runtimeResult = await page.evaluate(() => {
    const stats = window.__gameUpgradeProbe.game.renderStats;
    return { frames: stats.frames, fps: stats.fps, maxFrameMs: stats.maxFrameMs, longFrames: stats.longFrames, indexRebuilds: stats.indexRebuilds };
  });
  assert.ok(runtimeResult.frames >= 30, `game loop should render steadily: ${JSON.stringify(runtimeResult)}`);
  assert.ok(runtimeResult.fps >= 45, `runtime FPS should stay responsive: ${JSON.stringify(runtimeResult)}`);
  assert.ok(runtimeResult.maxFrameMs < 50, `no severe frame stall expected: ${JSON.stringify(runtimeResult)}`);
  assert.ok(runtimeResult.indexRebuilds > 0, `spatial indexes should update during play: ${JSON.stringify(runtimeResult)}`);

  await page.evaluate(() => {
    const game = window.__gameUpgradeProbe.game;
    game.score = 999;
    game.wave = 8;
    game.energy = 1;
    game.zombies = [{ type: "walker", row: 0, x: 400, y: 104, hp: 2, maxHp: 2 }];
    game.paused = true;
  });
  await page.locator("#gameStart").click();
  await page.waitForFunction(() => window.__gameUpgradeProbe.game.running && !window.__gameUpgradeProbe.game.paused);
  const restarted = await page.evaluate(() => {
    const game = window.__gameUpgradeProbe.game;
    return { score: game.score, wave: game.wave, energy: game.energy, zombies: game.zombies.length, paused: game.paused };
  });
  assert.deepEqual(restarted, { score: 0, wave: 1, energy: 60, zombies: 0, paused: false });

  assert.deepEqual(errors, [], `browser errors: ${errors.join(" | ")}`);
  console.log(`game upgrade smoke passed: skills, pause/resume, mower recovery, combo, restart, and runtime performance (${JSON.stringify(runtimeResult)})`);
} finally {
  await browser.close();
}
