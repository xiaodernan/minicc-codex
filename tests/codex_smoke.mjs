import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";
const plantKeys = [
  "peashooter", "sunflower", "wallnut", "repeater", "cherrybomb", "icepeashooter",
  "firepeashooter", "twinpea", "kernelpult", "pumpkin", "spikeweed", "gloomshroom",
  "potatomine", "threepeater", "jalapeno", "magnetshroom", "garlic", "squash", "gatlingpea",
];
const zombieKeys = [
  "walker", "backup", "roadblock", "conehead", "imp", "scout", "storm", "runner",
  "polevault", "bucket", "football", "miner", "flag", "dancer", "newspaper", "gargantuar",
  "witch", "dragon", "shield",
];

function assertNonEmpty(values, message) {
  assert.ok(values.length > 0, `${message}: no values`);
  values.forEach((value) => assert.ok(value.trim(), `${message}: empty value`));
}

async function openCodex(page) {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  if ((await page.evaluate(() => window.innerWidth)) <= 780) {
    await page.locator("#sidebarOpen").click();
    await page.locator(".sidebar.open").waitFor();
  }
  await page.locator("#arcadeButton").click();
  await page.locator("#gameModal.show").waitFor();
  await page.locator("#gameCodex").click();
  await page.locator("#gameCodexPanel.show").waitFor();
}

async function assertPlantEntry(page, key) {
  await page.locator(`[data-codex-entry="${key}"]`).click();
  const detail = page.locator("#codexDetail");
  const text = await detail.innerText();
  assert.ok(text.includes("植物详情"), `${key}: plant detail heading missing`);
  for (const label of ["阳光消耗", "植物生命值", "伤害", "攻击频率", "伤害类型", "攻击范围", "使用方法", "特殊效果"]) {
    assert.ok(text.includes(label), `${key}: missing plant field ${label}`);
  }
  assertNonEmpty(await detail.locator(".codex-row dd").allTextContents(), `${key}: plant stats`);
  assertNonEmpty(await detail.locator(".codex-section p").allTextContents(), `${key}: plant descriptions`);
}

async function assertZombieEntry(page, key) {
  await page.locator(`[data-codex-entry="${key}"]`).click();
  const detail = page.locator("#codexDetail");
  const text = await detail.innerText();
  assert.ok(text.includes("僵尸详情"), `${key}: zombie detail heading missing`);
  for (const label of ["基础生命值", "护甲", "移动速度", "攻击间隔", "击退积分", "移动方式", "特殊技能"]) {
    assert.ok(text.includes(label), `${key}: missing zombie field ${label}`);
  }
  assert.equal(await detail.locator(".codex-health-bar").count(), 1, `${key}: health bar missing`);
  assertNonEmpty(await detail.locator(".codex-row dd").allTextContents(), `${key}: zombie stats`);
  assertNonEmpty(await detail.locator(".codex-section p").allTextContents(), `${key}: zombie descriptions`);
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const errors = [];
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  page.on("pageerror", (error) => errors.push(error.message));

  await openCodex(page);
  assert.deepEqual(
    await page.locator(".seed-card").evaluateAll((cards) => cards.map((card) => card.dataset.plant).sort()),
    [...plantKeys].sort(),
    "codex plant keys must match the playable seed cards",
  );
  assert.equal(await page.locator("[data-codex-tab=plants]").getAttribute("aria-selected"), "true");
  assert.equal(await page.locator(".codex-entry").count(), plantKeys.length, "plant entry count");
  for (const key of plantKeys) await assertPlantEntry(page, key);

  await page.locator('[data-codex-tab="zombies"]').click();
  await page.locator('[data-codex-tab="zombies"][aria-selected="true"]').waitFor();
  assert.equal(await page.locator(".codex-entry").count(), zombieKeys.length, "zombie entry count");
  for (const key of zombieKeys) await assertZombieEntry(page, key);

  await page.locator('[data-codex-entry="walker"]').click();
  assert.equal((await page.locator("#codexDetail h4").innerText()).trim(), "普通僵尸", "first zombie selection");
  await page.locator('[data-codex-entry="shield"]').click();
  assert.equal((await page.locator("#codexDetail h4").innerText()).trim(), "护盾僵尸", "last zombie selection");

  await page.locator("#gameCodexClose").click();
  await page.locator("#gameCodexPanel").waitFor({ state: "hidden" });
  await page.locator("#gameCodex").click();
  await page.locator("#gameCodexPanel.show").waitFor();
  await page.locator("#gameCodexPanel").click({ position: { x: 4, y: 4 } });
  await page.locator("#gameCodexPanel").waitFor({ state: "hidden" });

  await page.locator("#gameCodex").click();
  await page.locator("#gameCodexPanel.show").waitFor();
  await page.evaluate(() => window.closeGame());
  await page.locator("#gameModal").waitFor({ state: "hidden" });
  await page.locator("#gameCodexPanel").waitFor({ state: "hidden" });
  assert.deepEqual(errors, [], `browser console errors: ${errors.join(" | ")}`);
  console.log(`codex smoke passed: ${plantKeys.length} plants + ${zombieKeys.length} zombies, interactions and close flows verified`);
} finally {
  await browser.close();
}
