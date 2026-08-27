import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";
const expectedTypes = [
  "walker", "backup", "roadblock", "conehead", "imp", "scout", "storm", "runner",
  "polevault", "bucket", "football", "miner", "flag", "dancer", "newspaper", "gargantuar",
  "witch", "dragon", "shield",
];
const directTypes = expectedTypes.filter((type) => type !== "backup");

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const errors = [];
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  page.on("pageerror", (error) => errors.push(error.message));

  // Ignore the optional remote icon bundle so network availability cannot mask local game failures.
  await page.route("https://unpkg.com/**", (route) => route.fulfill({ status: 200, contentType: "application/javascript", body: "" }));
  // Expose existing lexical game functions only in this test response; production files stay unchanged.
  await page.route("**/app.js", async (route) => {
    const response = await route.fetch();
    const body = await response.text();
    await route.fulfill({ response, body: `${body}\nwindow.__zombieProbe = { game, zombieProfiles, zombieTypeForWave, spawnZombie, gameLoop, drawGame };` });
  });
  await page.goto(`${baseUrl}/?arcade=1`, { waitUntil: "networkidle" });
  await page.locator("#gameModal.show").waitFor();
  await page.waitForFunction(() => window.__zombieProbe);

  const profileKeys = await page.evaluate(() => Object.keys(window.__zombieProbe.zombieProfiles));
  assert.deepEqual([...profileKeys].sort(), [...expectedTypes].sort(), "profiles must contain exactly all codex zombie types");

  const directResults = await page.evaluate((types) => {
    const probe = window.__zombieProbe;
    const ensure = (condition, message) => { if (!condition) throw new Error(message); };
    const originalRandom = Math.random;
    const result = {};
    try {
      for (const wanted of types) {
        probe.game.difficulty = "hard";
        let chosen = null;
        for (let wave = 1; wave <= 10 && !chosen; wave += 1) {
          probe.game.wave = wave;
          for (let index = 0; index < 10000; index += 1) {
            Math.random = () => index / 10000;
            if (probe.zombieTypeForWave() === wanted) { chosen = { wave, roll: index / 10000 }; break; }
          }
        }
        ensure(chosen, `${wanted} must have a reachable wave-table roll`);
        probe.game.wave = chosen.wave;
        probe.game.waveSpawned = 0;
        probe.game.waveTarget = 999;
        const sequence = [0.5, chosen.roll, 0.5];
        Math.random = () => sequence.shift() ?? 0.5;
        probe.game.zombies = [];
        probe.game.totalSpawned = 0;
        probe.spawnZombie();
        ensure(probe.game.zombies.length === 1, `${wanted} must be pushed into game.zombies`);
        ensure(probe.game.zombies[0].type === wanted, `${wanted} spawn type`);
        result[wanted] = { wave: chosen.wave, hp: probe.game.zombies[0].hp, speed: probe.game.zombies[0].speed };
      }
    } finally {
      Math.random = originalRandom;
    }
    return result;
  }, directTypes);
  assert.equal(Object.keys(directResults).length, 18, "all direct wave-spawn types must be exercised");

  const backupResult = await page.evaluate(() => {
    const probe = window.__zombieProbe;
    const ensure = (condition, message) => { if (!condition) throw new Error(message); };
    const profile = probe.zombieProfiles.backup;
    const makeDancer = () => ({
      x: 704, y: 100, row: 0, hp: 13, maxHp: 13, armor: 0, type: "dancer",
      speed: .019, attackInterval: 650, slowTimer: 0, burrowTimer: 0, seed: 1,
      garlicTimer: 0, vaultTimer: 0, summonTimer: 4200, flashTimer: 0, dashTimer: 0,
      leapTimer: 0, chargeTimer: 0, curseTimer: 0, breathTimer: 0, smashTimer: 0,
      armorTimer: 0, guardTimer: 0, burnTimer: 0, burnTickTimer: 0, stormTimer: 0, markTimer: 0,
    });
    probe.game.running = true;
    probe.game.paused = false;
    probe.game.pauseReasons = new Set();
    probe.game.difficulty = "hard";
    probe.game.wave = 1;
    probe.game.waveSpawned = probe.game.waveTarget = 999;
    probe.game.spawnTimer = 0;
    probe.game.zombies = [makeDancer()];
    probe.game.plants = [];
    probe.game.suns = [];
    probe.game.shots = [];
    probe.game.particles = [];
    probe.game.impacts = [];
    probe.game.last = 0;
    probe.game.frame = 0;
    const beforeCanvas = document.querySelector("#gameCanvas").getContext("2d").getImageData(0, 0, 720, 420).data;
    probe.gameLoop(16); // summonTimer 4200 + dt 16 crosses the 4200ms threshold.
    const summoned = probe.game.zombies.find((zombie) => zombie.type === "backup");
    ensure(summoned, "dancer must push a backup zombie into game.zombies");
    ensure(summoned.hp === profile.hp, "backup must use zombieProfiles.backup hp");
    ensure(summoned.speed === profile.speed, "backup must use zombieProfiles.backup speed");
    const beforeX = summoned.x;
    probe.game.last = 16;
    probe.gameLoop(96); // second loop updates the newly pushed backup.
    const afterX = summoned.x;
    const afterCanvas = document.querySelector("#gameCanvas").getContext("2d").getImageData(0, 0, 720, 420).data;
    const painted = [...afterCanvas].filter((value) => value !== 0).length;
    probe.game.running = false;
    cancelAnimationFrame(probe.game.frame);
    return { beforeX, afterX, painted, beforeCanvasSample: beforeCanvas[0], afterCanvasSample: afterCanvas[0] };
  });
  assert.ok(backupResult.afterX < backupResult.beforeX, "summoned backup must pass through the game loop movement update");
  assert.ok(backupResult.painted > 1000, "game loop must draw the zombie list to Canvas");

  const interactionResult = await page.evaluate(() => {
    const probe = window.__zombieProbe;
    probe.game.running = true;
    probe.game.paused = false;
    probe.game.pauseReasons = new Set();
    probe.game.waveSpawned = probe.game.waveTarget = 999;
    probe.game.spawnTimer = 0;
    probe.game.zombies = [{
      x: 110, y: 100, row: 0, hp: 4, maxHp: 4, armor: 0, type: "backup", speed: .025,
      attackInterval: 900, slowTimer: 0, burrowTimer: 0, seed: 1, garlicTimer: 0,
      vaultTimer: 0, summonTimer: 0, flashTimer: 0, dashTimer: 0, leapTimer: 0,
      chargeTimer: 0, curseTimer: 0, breathTimer: 0, smashTimer: 0, armorTimer: 0,
      guardTimer: 0, burnTimer: 0, burnTickTimer: 0, stormTimer: 0, markTimer: 0,
    }];
    probe.game.plants = [{ type: "wallnut", hp: 10, row: 0, col: 0, seed: 1, age: 0, sunTimer: 0, shotTimer: 0, bombTimer: 0, disabledTimer: 0, armed: true }];
    probe.game.suns = [];
    probe.game.shots = [];
    probe.game.particles = [];
    probe.game.impacts = [];
    probe.game.last = 0;
    const before = probe.game.plants[0].hp;
    probe.gameLoop(80);
    const after = probe.game.plants[0].hp;
    probe.game.running = false;
    cancelAnimationFrame(probe.game.frame);
    return { before, after };
  });
  assert.ok(interactionResult.after < interactionResult.before, "backup must participate in zombie-versus-plant interaction logic");
  assert.deepEqual(errors, [], `browser errors: ${errors.join(" | ")}`);
  console.log("zombie spawn smoke passed: 18 direct wave types + dancer->backup summon + update/draw/interaction verified");
} finally {
  await browser.close();
}
