// NOTE: 源文件分片（web/src/）。此文件由 `npm run build:web` 按序拼接生成，勿直接编辑。
const GAME_DIFFICULTIES = {
  normal: { hpMultiplier: .9, initialSun: 200, speedMultiplier: .9, spawnDelayMultiplier: 1.16, waveBonus: -1 },
  hard: { hpMultiplier: 1, initialSun: 175, speedMultiplier: 1, spawnDelayMultiplier: 1, waveBonus: 0 },
  nightmare: { hpMultiplier: 1.58, initialSun: 110, speedMultiplier: 1.28, spawnDelayMultiplier: .56, waveBonus: 6 },
};
const savedGameDifficulty = Object.prototype.hasOwnProperty.call(GAME_DIFFICULTIES, localStorage.getItem("minicc-game-difficulty")) ? localStorage.getItem("minicc-game-difficulty") : "hard";
const WAVE_TARGET = (wave, difficulty = savedGameDifficulty) => 7 + wave * 2 + GAME_DIFFICULTIES[difficulty].waveBonus + (difficulty === "nightmare" ? wave + Math.floor((wave + 1) / 2) : 0);
const game = { running: false, paused: false, pauseReasons: new Set(), frame: 0, score: 0, sun: GAME_DIFFICULTIES[savedGameDifficulty].initialSun, wave: 1, waveTarget: WAVE_TARGET(1), waveSpawned: 0, totalSpawned: 0, waveClearTimer: 0, elapsed: 0, selected: null, hoverCell: null, shovel: false, seedCooldowns: {}, skillCooldowns: {}, energy: 60, rallyTimer: 0, timeStopTimer: 0, plants: [], zombies: [], defeated: [], suns: [], shots: [], particles: [], impacts: [], popups: [], mowers: [], combo: 0, comboTimer: 0, bestCombo: 0, bannerTimer: 0, bannerText: "", bannerColor: "#ffe27c", dangerPulse: 0, last: 0, spawnTimer: 0, skyTimer: 0, dangerTimer: 0, difficulty: savedGameDifficulty, autoSun: localStorage.getItem("minicc-game-auto-sun") !== "off", musicOn: localStorage.getItem("minicc-game-sound") !== "off", volume: Math.max(0, Math.min(100, Number(localStorage.getItem("minicc-game-volume")) || 70)), audio: null, hudAt: 0, flagRows: new Uint8Array(5), renderStats: { frames: 0, fps: 0, lastFrameMs: 0, maxFrameMs: 0, longFrames: 0, frameSamples: [], recentSamples: new Array(60), recentSampleIndex: 0, recentSampleCount: 0, recentLongFrames: 0, windowStartedAt: 0, windowFrames: 0, indexRebuilds: 0, rowQueries: 0, rowCandidates: 0, drawCalls: 0, plantDraws: 0, zombieDraws: 0, animationSwitches: 0 } };
const ZOMBIE_BODY_COLORS = { walker: "#526b5e", roadblock: "#53677d", bucket: "#566273", runner: "#9b5d4f", imp: "#b45d4e", football: "#334b68", miner: "#72574a", polevault: "#57785d", flag: "#754d6c", dancer: "#8d3f68", newspaper: "#806c50", conehead: "#b76b4d", witch: "#563d70", dragon: "#8a453f", gargantuar: "#694450", backup: "#a15c72" };
const gameLayout = { left: 78, top: 72, cellW: 70, cellH: 65, rows: 5, cols: 9 };
const GAME_LOGICAL_WIDTH = 720;
const GAME_LOGICAL_HEIGHT = 420;
const GAME_MAX_PARTICLES = 180;
const GAME_PARTICLE_DRAW_BUDGET = 120;
const GAME_MAX_POPUPS = 48;
const GAME_MOWER_TRIGGER_X = 92;
const GAME_MOWER_SPEED = .62;
const GAME_MOWER_CLEAR_RADIUS = 36;
const GAME_MOWER_EXIT_X = GAME_LOGICAL_WIDTH + 46;
const GAME_COMBO_WINDOW = 1800;
const GAME_SKILLS = {
  pulse: { cost: 25, cooldown: 7000, label: "game.skillPulse", hint: "game.skillPulseHint" },
  sun: { cost: 35, cooldown: 10000, label: "game.skillSun", hint: "game.skillSunHint" },
  rally: { cost: 45, cooldown: 14000, label: "game.skillRally", hint: "game.skillRallyHint" },
  timeStop: { cost: 55, cooldown: 18000, label: "game.skillTimeStop", hint: "game.skillTimeStopHint" },
};
const gameRows = {
  plants: Array.from({ length: gameLayout.rows }, () => []),
  zombies: Array.from({ length: gameLayout.rows }, () => []),
};
function cacheGameEntityPosition(entity) {
  const row = Number.isInteger(entity?.row) ? entity.row : -1;
  const col = Number.isInteger(entity?.col) ? entity.col : 0;
  const position = gameCellPositions[row]?.[col] || gameCellPositions[row]?.[0];
  if (position) {
    entity.cellX = position.x;
    entity.cellY = position.y;
    if (entity.type && entity.x === undefined) entity.x = position.x;
    if (entity.type && entity.y === undefined) entity.y = position.y;
  }
  return entity;
}
function rebuildGameRows(kind, entities) {
  const rows = gameRows[kind];
  rows.forEach((row) => { row.length = 0; });
  entities.forEach((entity) => {
    cacheGameEntityPosition(entity);
    if (kind === "plants" && entity.underPlant) cacheGameEntityPosition(entity.underPlant);
    const row = Number.isInteger(entity.row) ? entity.row : -1;
    if (row >= 0 && row < gameLayout.rows) rows[row].push(entity);
  });
  return rows;
}
function firstIndexedEntity(kind, predicate) {
  const rows = gameRows[kind];
  for (let row = 0; row < rows.length; row += 1) {
    const entities = rowEntities(kind, row);
    for (let index = 0; index < entities.length; index += 1) {
      if (predicate(entities[index])) return entities[index];
    }
  }
  return null;
}
function anyIndexedEntity(kind, predicate) { return Boolean(firstIndexedEntity(kind, predicate)); }
function rowEntities(kind, row) {
  const entities = gameRows[kind][row] || [];
  game.renderStats.rowQueries += 1;
  game.renderStats.rowCandidates += entities.length;
  return entities;
}
function firstRowEntity(kind, row, predicate) {
 const entities = rowEntities(kind, row);
 for (let index = 0; index < entities.length; index += 1) if (predicate(entities[index])) return entities[index];
 return null;
}
function anyRowEntity(kind, row, predicate) { return Boolean(firstRowEntity(kind, row, predicate)); }
function forEachRowEntity(kind, row, callback) {
 const entities = rowEntities(kind, row);
 for (let index = 0; index < entities.length;) {
  const entity = entities[index];
  callback(entity);
  // A callback may remove the current entity; keep the cursor in place.
  if (entities[index] === entity) index += 1;
 }
}
function trackGameAnimation(entity, state) {
 if (!entity || entity.animationState === state) return;
 entity.animationState = state;
 if (game.renderStats) game.renderStats.animationSwitches = (game.renderStats.animationSwitches || 0) + 1;
}
function removeRowEntity(kind, entity, rowOverride = null) {
 const row = Number.isInteger(rowOverride) ? rowOverride : (Number.isInteger(entity?.row) ? entity.row : -1);
 const entities = rowEntities(kind, row);
 const index = entities.indexOf(entity);
 if (index >= 0) entities.splice(index, 1);
}
function moveRowEntity(kind, entity, previousRow) {
 const nextRow = Number.isInteger(entity?.row) ? entity.row : -1;
 if (previousRow === nextRow) return;
 removeRowEntity(kind, entity, previousRow);
 if (nextRow >= 0 && nextRow < gameLayout.rows) rowEntities(kind, nextRow).push(entity);
}
function rebuildGameIndexes() {
 rebuildGameRows("plants", game.plants);
 rebuildGameRows("zombies", game.zombies);
 game.renderStats.indexRebuilds += 1;
}
const gameCellPositions = Array.from({ length: gameLayout.rows }, (_, row) =>
 Array.from({ length: gameLayout.cols }, (_, col) => ({
   x: gameLayout.left + col * gameLayout.cellW + 35,
   y: gameLayout.top + row * gameLayout.cellH + 31,
 })),
);
const gameRender = { canvas: null, ctx: null, background: null, dpr: 1, effects: "high", deviceProfile: null };
function resizeGameCanvas() {
  const canvas = gameRender.canvas || $("#gameCanvas");
  if (!canvas) return;
  gameRender.canvas = canvas;
  // Keep the logical field sharp without making high-DPR devices rasterize an oversized surface.
  const dpr = Math.min(1.75, Math.max(1, window.devicePixelRatio || 1));
  const width = Math.round(GAME_LOGICAL_WIDTH * dpr);
  const height = Math.round(GAME_LOGICAL_HEIGHT * dpr);
  if (!gameRender.ctx || canvas.width !== width || canvas.height !== height || gameRender.dpr !== dpr) {
    canvas.width = width;
    canvas.height = height;
    gameRender.dpr = dpr;
    gameRender.ctx = canvas.getContext("2d", { alpha: false, desynchronized: true }) || canvas.getContext("2d");
    gameRender.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    gameRender.ctx.imageSmoothingEnabled = true;
    gameRender.ctx.imageSmoothingQuality = "high";
    gameRender.background = null;
  }
  if (!gameRender.background) buildGameBackground();
}
function buildGameBackground() {
  const background = document.createElement("canvas");
  background.width = GAME_LOGICAL_WIDTH;
  background.height = GAME_LOGICAL_HEIGHT;
  const ctx = background.getContext("2d");
  const sky = ctx.createLinearGradient(0, 0, 0, GAME_LOGICAL_HEIGHT);
  sky.addColorStop(0, "#9bd9df"); sky.addColorStop(.35, "#d7e7b2"); sky.addColorStop(.36, "#659b58"); sky.addColorStop(1, "#315744");
  ctx.fillStyle = sky; ctx.fillRect(0, 0, GAME_LOGICAL_WIDTH, GAME_LOGICAL_HEIGHT);
  ctx.fillStyle = "rgba(255,255,255,.18)"; ctx.beginPath(); ctx.arc(605, 42, 29, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#253b45"; ctx.fillRect(0, 0, GAME_LOGICAL_WIDTH, 58);
  ctx.fillStyle = "#eef3cf"; ctx.font = "700 12px Manrope, sans-serif"; ctx.fillText("BACKYARD", 18, 23);
  ctx.fillStyle = "#d9b16e"; ctx.fillRect(48, 28, 17, 23); ctx.fillStyle = "#693f38"; ctx.beginPath(); ctx.moveTo(44, 29); ctx.lineTo(57, 16); ctx.lineTo(70, 29); ctx.fill(); ctx.fillStyle = "#f4d27a"; ctx.fillRect(53, 39, 7, 12);
  for (let row = 0; row < gameLayout.rows; row += 1) for (let col = 0; col < gameLayout.cols; col += 1) { const x = gameLayout.left + col * gameLayout.cellW, y = gameLayout.top + row * gameLayout.cellH; ctx.fillStyle = (row + col) % 2 ? "#75b866" : "#83c573"; roundedRect(ctx, x + 2, y + 2, 66, 61, 8); ctx.fill(); ctx.strokeStyle = "rgba(221, 246, 151, .18)"; ctx.stroke(); }
  const laneGlow = ctx.createLinearGradient(78, 72, 78, 397);
  laneGlow.addColorStop(0, "rgba(255,255,255,.06)"); laneGlow.addColorStop(.5, "rgba(255,255,255,0)"); laneGlow.addColorStop(1, "rgba(12,38,29,.14)");
  ctx.fillStyle = laneGlow; ctx.fillRect(78, 72, 630, 325);
  ctx.strokeStyle = "rgba(232, 250, 176, .14)"; ctx.lineWidth = 1;
  for (let row = 0; row <= gameLayout.rows; row += 1) { const y = gameLayout.top + row * gameLayout.cellH; ctx.beginPath(); ctx.moveTo(gameLayout.left, y); ctx.lineTo(708, y); ctx.stroke(); }
  ctx.fillStyle = "rgba(240, 213, 140, .28)"; ctx.fillRect(674, 60, 3, 360);
  ctx.fillStyle = "rgba(255,255,255,.07)"; ctx.fillRect(678, 60, 1, 360);
  gameRender.background = background;
}
function recordGameFrame(now, startedAt) {
  const stats = game.renderStats;
  const frameMs = Math.max(0, performance.now() - startedAt);
  const sampleIndex = stats.frames % 240;
  stats.frames += 1;
  stats.lastFrameMs = frameMs;
  stats.maxFrameMs = Math.max(stats.maxFrameMs, frameMs);
  if (frameMs > 32) stats.longFrames += 1;
  // Keep the rolling profiler allocation-free; shift() would copy up to 240 entries every frame.
  if (stats.frameSamples.length < 240) stats.frameSamples.push(frameMs);
  else stats.frameSamples[sampleIndex] = frameMs;
  const recentIndex = Number.isInteger(stats.recentSampleIndex) ? stats.recentSampleIndex : 0;
  const previousSample = stats.recentSamples?.[recentIndex];
  if (previousSample > 32) stats.recentLongFrames -= 1;
  if (!stats.recentSamples) stats.recentSamples = new Array(60);
  stats.recentSamples[recentIndex] = frameMs;
  if (frameMs > 32) stats.recentLongFrames += 1;
  stats.recentSampleIndex = (recentIndex + 1) % 60;
  stats.recentSampleCount = Math.min(60, stats.recentSampleCount + 1);
  if (stats.recentSampleCount >= 30 && stats.recentLongFrames >= 6) gameRender.effects = "low";
  else if (gameRender.effects === "low" && stats.recentSampleCount >= 30 && stats.recentLongFrames <= 1) gameRender.effects = "high";
  if (!stats.windowStartedAt) stats.windowStartedAt = now;
  stats.windowFrames += 1;
  if (now - stats.windowStartedAt >= 1000) {
    stats.fps = stats.windowFrames * 1000 / (now - stats.windowStartedAt);
    stats.windowFrames = 0;
    stats.windowStartedAt = now;
    const performanceNode = $("#gamePerformance");
    if (performanceNode) {
      $("#gameFps").textContent = String(Math.round(stats.fps));
      $("#gameFrameMs").textContent = `${stats.lastFrameMs.toFixed(1)}ms`;
      $("#gameLongFrames").textContent = String(stats.longFrames);
      $("#gameObjectCount").textContent = String(game.suns.length + game.plants.length + game.zombies.length + game.shots.length + game.particles.length + game.impacts.length);
      performanceNode.classList.toggle("warning", stats.lastFrameMs > 32 || stats.recentLongFrames > 0);
    }
  }
}
const plantCost = { peashooter: 100, sunflower: 50, wallnut: 50, repeater: 180, cherrybomb: 150, icepeashooter: 175, firepeashooter: 175, twinpea: 225, kernelpult: 100, pumpkin: 125, spikeweed: 100, gloomshroom: 150, potatomine: 25, threepeater: 325, jalapeno: 125, magnetshroom: 100, garlic: 50, squash: 50, gatlingpea: 350 };
const PLANT_TYPES = Object.keys(plantCost);
const plantHealth = { peashooter: 7, sunflower: 6, wallnut: 24, repeater: 8, cherrybomb: 4, icepeashooter: 7, firepeashooter: 7, twinpea: 10, kernelpult: 8, pumpkin: 32, spikeweed: 10, gloomshroom: 9, potatomine: 3, threepeater: 8, jalapeno: 4, magnetshroom: 7, garlic: 8, squash: 6, gatlingpea: 9 };
const plantColor = { peashooter: "#62b5a0", sunflower: "#f6c453", wallnut: "#ad7556", repeater: "#75c77b", cherrybomb: "#dd6d73", icepeashooter: "#8bc9e8", firepeashooter: "#f07855", twinpea: "#8bd15f", kernelpult: "#e8bf65", pumpkin: "#e29b45", spikeweed: "#8dbf62", gloomshroom: "#8563aa", potatomine: "#a9bd72", threepeater: "#72c789", jalapeno: "#ef765f", magnetshroom: "#b187d5", garlic: "#f3e1b4", squash: "#e2a848", gatlingpea: "#4db878" };
const plantCooldown = { peashooter: 250, sunflower: 900, wallnut: 700, repeater: 450, cherrybomb: 900, icepeashooter: 850, firepeashooter: 850, twinpea: 950, kernelpult: 700, pumpkin: 1050, spikeweed: 650, gloomshroom: 1100, potatomine: 650, threepeater: 1100, jalapeno: 1200, magnetshroom: 900, garlic: 800, squash: 800, gatlingpea: 1400 };
const plantProfiles = {
  peashooter: { interval: 1050, shots: 1, damage: 1, slow: 0 },
  repeater: { interval: 1250, shots: 2, damage: 1, slow: 0, pierce: 1 },
  icepeashooter: { interval: 1300, shots: 1, damage: 1, slow: 3200, pierce: 1 },
  firepeashooter: { interval: 1350, shots: 1, damage: 2, slow: 0, fire: true, burn: 2600, burnDamage: 3 },
  twinpea: { interval: 1450, shots: 2, damage: 2, slow: 0, pierce: 1 },
  kernelpult: { interval: 1500, shots: 1, damage: 1, slow: 0, butterChance: .28, pierce: 1 },
  threepeater: { interval: 1450, shots: 1, damage: 1, slow: 0, rows: true, pierce: 1 },
  magnetshroom: { interval: 2600, shots: 0, damage: 0, slow: 0, utility: true },
  gatlingpea: { interval: 1550, shots: 4, damage: 1, slow: 0, pierce: 1 },
  gloomshroom: { interval: 1200, shots: 1, damage: 1, slow: 900, close: true },
};
function plantHasSunlight(plant) {
  if (!plant || plant.type === "sunflower") return false;
  return game.plants.some((container) => [container, container.underPlant].filter(Boolean).some((candidate) => (
    candidate !== plant
    && candidate.type === "sunflower"
    && Math.abs(candidate.row - plant.row) <= 1
    && Math.abs(candidate.col - plant.col) <= 1
  )));
}
function plantFireInterval(plant, profile) {
  const sunlightMultiplier = plant.sunlightBoost ? .78 : 1;
  const rallyMultiplier = game.rallyTimer > 0 ? .55 : 1;
  return profile.interval * sunlightMultiplier * rallyMultiplier;
}
const zombieProfiles = {
  walker: { hp: 5, speed: .020, growth: .0010, attackInterval: 1000, score: 1 },
  backup: { hp: 4, speed: .025, growth: .0008, attackInterval: 900, score: 1 },
  roadblock: { hp: 12, speed: .013, growth: .00065, attackInterval: 670, score: 3, armor: 5, barricade: true },
  conehead: { hp: 9, speed: .021, growth: .0009, attackInterval: 900, score: 2, armor: 3, cone: true },
  imp: { hp: 3, speed: .044, growth: .0011, attackInterval: 1250, score: 2, dash: true, leap: true },
  scout: { hp: 7, speed: .030, growth: .0009, attackInterval: 820, score: 4, dash: true, mark: true },
  storm: { hp: 11, speed: .016, growth: .0006, attackInterval: 740, score: 7, storm: true },
  runner: { hp: 4, speed: .036, growth: .0008, attackInterval: 1150, score: 2, dash: true },
  polevault: { hp: 10, speed: .025, growth: .0007, attackInterval: 700, score: 5, vault: true },
  bucket: { hp: 21, speed: .011, growth: .00045, attackInterval: 620, score: 5, armor: 8, bucket: true },
  football: { hp: 18, speed: .024, growth: .00055, attackInterval: 430, score: 6, armor: 5, charge: true },
  miner: { hp: 9, speed: .018, growth: .0007, attackInterval: 850, score: 5, burrow: true },
  flag: { hp: 6, speed: .027, growth: .0010, attackInterval: 900, score: 3, banner: true },
  dancer: { hp: 13, speed: .019, growth: .00055, attackInterval: 650, score: 7, summon: true },
  newspaper: { hp: 8, speed: .017, growth: .0008, attackInterval: 760, score: 4, armor: 3, enrage: true },
  gargantuar: { hp: 48, speed: .008, growth: .00035, attackInterval: 360, score: 12, armor: 8, giant: true, smash: true },
  witch: { hp: 16, speed: .014, growth: .0005, attackInterval: 800, score: 9, curse: true },
  dragon: { hp: 26, speed: .010, growth: .00035, attackInterval: 560, score: 10, armor: 2, breath: true },
  shield: { hp: 14, speed: .016, growth: .0006, attackInterval: 720, score: 6, armor: 12, guard: true },
};
function gameDifficulty() { return GAME_DIFFICULTIES[game.difficulty] || GAME_DIFFICULTIES.hard; }
function updatePauseButton() {
  const button = $("#gamePause");
  if (!button) return;
  const paused = game.pauseReasons.has("manual");
  button.classList.toggle("active", paused);
  button.setAttribute("aria-pressed", String(paused));
  button.querySelector("strong").textContent = t(paused ? "game.resume" : "game.pause");
  button.querySelector("small").textContent = t(paused ? "game.resumeHint" : "game.pauseHint");
}
function setGamePauseReason(reason, paused) {
  if (!game.running) return;
  if (paused) game.pauseReasons.add(reason);
  else game.pauseReasons.delete(reason);
  const nextPaused = game.pauseReasons.size > 0;
  if (game.paused === nextPaused) {
    updatePauseButton();
    if (nextPaused) setGameStatus(game.pauseReasons.has("manual") ? "game.manualPaused" : "game.paused");
    return;
  }
  game.paused = nextPaused;
  cancelAnimationFrame(game.frame);
  updatePauseButton();
  if (nextPaused) {
    stopGameMusic();
    setGameStatus(reason === "manual" ? "game.manualPaused" : "game.paused");
    drawGame();
    return;
  }
  game.last = performance.now();
  setGameStatus("game.running");
  startGameMusic();
  game.frame = requestAnimationFrame(gameLoop);
}
function toggleGamePause() { setGamePauseReason("manual", !game.pauseReasons.has("manual")); }
function setGameDifficulty(value) {
  if (game.running || !Object.prototype.hasOwnProperty.call(GAME_DIFFICULTIES, value)) return;
  game.difficulty = value;
  localStorage.setItem("minicc-game-difficulty", value);
  initGame();
}
function updateShovelButton() {
  const button = $("#gameShovel");
  if (!button) return;
  button.classList.toggle("active", game.shovel);
  button.setAttribute("aria-pressed", String(game.shovel));
}
function toggleShovel() {
  game.shovel = !game.shovel;
  if (game.shovel) clearPlantSelection();
  updateShovelButton();
  drawGame();
}
function clearPlantSelection() {
  game.selected = null;
  $$(".seed-card").forEach((card) => card.classList.remove("selected"));
}
function selectPlant(card) {
  const next = card.dataset.plant;
  if ((game.seedCooldowns[next] || 0) > 0) {
    setGameStatus("game.cooldown");
    return;
  }
  if (game.shovel) {
    game.shovel = false;
    updateShovelButton();
  }
  game.selected = game.selected === next ? null : next;
  $$(".seed-card").forEach((item) => item.classList.toggle("selected", item.dataset.plant === game.selected));
  drawGame();
}
function formatGameTime(value) {
  const total = Math.max(0, Math.floor(value / 1000));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
function updateGameHud(force = true) {
  const now = performance.now();
  // HUD text is DOM work; it does not need to be synchronized with every paint.
  if (!force && now - game.hudAt < 100) return;
  game.hudAt = now;
  $("#gameSun").textContent = String(game.sun);
  $("#gameScore").textContent = String(game.score);
  $("#gameWave").textContent = `${Math.min(game.wave, MAX_WAVES)}/${MAX_WAVES}`;
  $("#gameTime").textContent = formatGameTime(game.elapsed);
  const pressure = `${t("game.threat")}: ${game.waveSpawned}/${game.waveTarget}`;
  $("#gameThreat").textContent = pressure;
  $("#gameProgressFill").style.width = `${Math.round((game.waveSpawned / Math.max(1, game.waveTarget)) * 100)}%`;
  $("#gameWaveHint").textContent = t(game.wave >= 9 ? "game.waveFinal" : game.wave >= 7 ? "game.wavePressure" : "game.waveHint");
  $("#gameMowers").textContent = String(game.mowers.filter((mower) => !mower.used).length);
  $("#gameCombo").textContent = String(game.combo || 0);
  $("#gameCombo").parentElement.classList.toggle("hot", (game.combo || 0) >= 3);
  const energy = Math.max(0, Math.min(100, Math.round(game.energy || 0)));
  const energyNode = $("#gameEnergy");
  const energyFill = $("#gameEnergyFill");
  if (energyNode) energyNode.textContent = String(energy);
  if (energyFill) energyFill.style.width = `${energy}%`;
  $$(".game-skill").forEach((button) => {
    const skill = GAME_SKILLS[button.dataset.skill];
    if (!skill) return;
    const remaining = Math.max(0, game.skillCooldowns[button.dataset.skill] || 0);
    const cooling = remaining > 0;
    const unavailable = cooling || energy < skill.cost || !game.running || game.paused;
    button.classList.toggle("cooling", cooling);
    button.classList.toggle("ready", !unavailable);
    button.classList.toggle("unaffordable", energy < skill.cost);
    button.disabled = unavailable;
    button.setAttribute("aria-disabled", String(unavailable));
    button.style.setProperty("--skill-cooldown", `${Math.ceil(remaining / 1000)}s`);
    button.title = cooling ? `${t(skill.label)} · ${Math.ceil(remaining / 1000)}s` : `${t(skill.label)} · ${energy}/${skill.cost}`;
  });
  $$(".seed-card").forEach((card) => {
    const remaining = Math.max(0, game.seedCooldowns[card.dataset.plant] || 0);
    const cooling = remaining > 0;
    const unaffordable = game.sun < (plantCost[card.dataset.plant] || Infinity);
    card.classList.toggle("cooling", cooling);
    card.classList.toggle("unaffordable", unaffordable);
    card.setAttribute("aria-disabled", String(cooling || unaffordable));
    card.style.setProperty("--seed-cooldown", `${Math.ceil(remaining / 1000)}s`);
  });
}
function activateGameSkill(type) {
  if (!game.running || game.paused) return false;
  const skill = GAME_SKILLS[type];
  if (!skill) return false;
  const remaining = Math.max(0, game.skillCooldowns[type] || 0);
  if (remaining > 0) { setGameStatus("game.skillCooldown"); return false; }
  if ((game.energy || 0) < skill.cost) { setGameStatus("game.skillNeedEnergy"); return false; }
  game.energy -= skill.cost;
  game.skillCooldowns[type] = skill.cooldown;
  const center = { x: 390, y: 230 };
  if (type === "pulse") {
    game.skillPulseFlash = 620;
    game.zombies.slice().forEach((zombie) => {
      zombie.slowTimer = Math.max(zombie.slowTimer || 0, 4200);
      zombie.flashTimer = 240;
      zombie.staggerTimer = Math.max(zombie.staggerTimer || 0, 220);
      zombie.hp -= zombie.armor > 0 ? 2.5 : 4;
      game.impacts.push({ x: zombie.x, y: zombie.y, radius: 34, color: "#bdf8ff", life: 260, maxLife: 260 });
      if (zombie.hp <= 0) defeatZombie(zombie, "skill");
    });
    addGameParticle(center.x, center.y, "#bdf8ff", 48, .34);
    announceGame(state.locale === "zh" ? "寒冰脉冲！" : "FROST PULSE!", "#bdf8ff", 900);
    playGameSound("explode");
  } else if (type === "sun") {
    game.sun += 100;
    addGameParticle(390, 88, "#ffe17b", 34, .26);
    addGamePopup(390, 112, "+100 ☀", "#ffe17b", 1000);
    announceGame(state.locale === "zh" ? "+100 阳光" : "+100 SUN", "#ffe17b", 900);
    playGameSound("collect");
  } else if (type === "rally") {
    game.rallyTimer = 8000;
    game.skillPulseFlash = 420;
    addGameParticle(390, 230, "#f5c96b", 32, .3);
    announceGame(state.locale === "zh" ? "战线超载！" : "OVERDRIVE!", "#f5c96b", 900);
    playGameSound("wave");
  } else if (type === "timeStop") {
    game.timeStopTimer = 4200;
    game.skillPulseFlash = 620;
    game.zombies.forEach((zombie) => {
      zombie.flashTimer = Math.max(zombie.flashTimer || 0, 4200);
      game.impacts.push({ x: zombie.x, y: zombie.y, radius: 28, color: "#d7c7ff", life: 4200, maxLife: 4200 });
    });
    addGameParticle(390, 230, "#d7c7ff", 56, .38);
    announceGame(state.locale === "zh" ? "时停领域！" : "TIME LOCK!", "#d7c7ff", 1100);
    playGameSound("wave");
  }
  updateGameHud(true);
  drawGame();
  return true;
}
function cellPosition(row, col) { return gameCellPositions[row]?.[col] || { x: gameLayout.left + col * gameLayout.cellW + 35, y: gameLayout.top + row * gameLayout.cellH + 31 }; }
function cachedCellPosition(entity) {
 const position = gameCellPositions[entity?.row]?.[entity?.col];
 return position || cellPosition(entity?.row, entity?.col);
}
function rowEntitiesWhere(kind, row, predicate) {
 const entities = rowEntities(kind, row);
 const matches = [];
 for (let index = 0; index < entities.length; index += 1) if (predicate(entities[index])) matches.push(entities[index]);
 return matches;
}
function addGameParticle(x, y, color, count = 6, speed = 0.08) {
  for (let i = 0; i < count; i += 1) game.particles.push({ x, y, vx: (Math.random() - .5) * speed, vy: (Math.random() - .7) * speed, life: 420 + Math.random() * 360, maxLife: 780, size: 2 + Math.random() * 3, color });
  if (game.particles.length > GAME_MAX_PARTICLES) game.particles.splice(0, game.particles.length - GAME_MAX_PARTICLES);
}
function addGamePopup(x, y, text, color = "#fff1b0", life = 850) {
  game.popups.push({ x, y, text, color, life, maxLife: life, vy: -.025 });
  if (game.popups.length > GAME_MAX_POPUPS) game.popups.splice(0, game.popups.length - GAME_MAX_POPUPS);
}
function announceGame(text, color = "#ffe27c", duration = 1500) {
  game.bannerText = text;
  game.bannerColor = color;
  game.bannerTimer = duration;
}
function gameWaveBanner(wave) {
  return state.locale === "zh" ? `第 ${wave} 波` : `WAVE ${wave}`;
}
function gameVolume() { return game.musicOn ? .1 * (game.volume / 100) : .001; }
function playGameSound(kind) {
  if (!game.musicOn || !game.volume) return;
  try {
    if (!game.audio) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext(); const master = ctx.createGain(); master.gain.value = gameVolume(); master.connect(ctx.destination);
      game.audio = { ctx, master, musicTimer: null, step: 0, lastSound: {} };
    }
    const { ctx, master } = game.audio;
    if (ctx.state === "suspended") ctx.resume();
    const sounds = {
      collect: { notes: [660, 880], type: "sine", duration: .16, step: .055, volume: .14 },
      plant: { notes: [330, 494], type: "triangle", duration: .2, step: .07, volume: .14 },
      shoot: { notes: [180, 230], type: "square", duration: .1, step: .035, volume: .08 },
      hit: { notes: [145], type: "square", duration: .08, step: 0, volume: .08 },
      explode: { notes: [130, 92, 58], type: "sawtooth", duration: .34, step: .07, volume: .2 },
      wave: { notes: [392, 523, 659], type: "triangle", duration: .42, step: .1, volume: .16 },
      victory: { notes: [523, 659, 784, 1046], type: "triangle", duration: .7, step: .11, volume: .18 },
      gameover: { notes: [220, 165, 110], type: "sawtooth", duration: .55, step: .13, volume: .16 },
      danger: { notes: [110, 98], type: "square", duration: .18, step: .08, volume: .1 },
      mower: { notes: [196, 294, 392], type: "sawtooth", duration: .36, step: .07, volume: .13 },
    };
    const sound = sounds[kind] || sounds.hit;
    const now = ctx.currentTime;
    const minInterval = { hit: .055, shoot: .08, collect: .04 }[kind] || 0;
    if (minInterval && now - (game.audio.lastSound[kind] || 0) < minInterval) return;
    game.audio.lastSound[kind] = now;
    sound.notes.forEach((frequency, index) => {
      const start = now + index * sound.step;
      const oscillator = ctx.createOscillator(); const gain = ctx.createGain();
      oscillator.type = sound.type; oscillator.frequency.setValueAtTime(frequency, start);
      gain.gain.setValueAtTime(.001, start); gain.gain.linearRampToValueAtTime(sound.volume, start + .012); gain.gain.exponentialRampToValueAtTime(.001, start + sound.duration);
      oscillator.connect(gain); gain.connect(master); oscillator.start(start); oscillator.stop(start + sound.duration + .02);
    });
  } catch { /* Audio is an enhancement, not a gameplay dependency. */ }
}
function startGameMusic() {
  if (!game.musicOn || game.audio?.musicTimer) return;
  playGameSound("plant");
  if (!game.audio) return;
  const melody = [262, 330, 392, 330, 294, 349, 440, 349, 392, 494, 587, 494];
  game.audio.musicTimer = window.setInterval(() => {
    if (!game.running || !game.musicOn || !game.audio) return;
    const { ctx, master } = game.audio; const oscillator = ctx.createOscillator(); const gain = ctx.createGain();
    const start = ctx.currentTime; oscillator.type = "triangle"; oscillator.frequency.setValueAtTime(melody[game.audio.step++ % melody.length], start); gain.gain.setValueAtTime(.001, start); gain.gain.linearRampToValueAtTime(.05, start + .02); gain.gain.exponentialRampToValueAtTime(.001, start + .3); oscillator.connect(gain); gain.connect(master); oscillator.start(start); oscillator.stop(start + .34);
  }, 560);
}
function stopGameMusic() { if (game.audio?.musicTimer) { clearInterval(game.audio.musicTimer); game.audio.musicTimer = null; } }
function updateSoundButton() { const button = $("#gameSoundToggle"); const volume = $("#gameVolume"); if (button) { button.textContent = t(game.musicOn ? "game.soundOn" : "game.soundOff"); button.classList.toggle("muted", !game.musicOn); button.setAttribute("aria-pressed", String(game.musicOn)); } if (volume) volume.value = String(game.volume); }
function setGameVolume(value) { game.volume = Math.max(0, Math.min(100, Number(value) || 0)); localStorage.setItem("minicc-game-volume", String(game.volume)); if (game.audio?.master) game.audio.master.gain.setTargetAtTime(gameVolume(), game.audio.ctx.currentTime, .02); }
function toggleGameSound() { game.musicOn = !game.musicOn; localStorage.setItem("minicc-game-sound", game.musicOn ? "on" : "off"); if (game.audio?.master) game.audio.master.gain.setTargetAtTime(gameVolume(), game.audio.ctx.currentTime, .02); if (game.musicOn && game.volume) { playGameSound("collect"); startGameMusic(); } else stopGameMusic(); updateSoundButton(); }
function setGameStatus(key) { $("#gameStatus").textContent = t(key); }
function setGamePaused(paused) { setGamePauseReason("visibility", paused); }
function finishGame(statusKey) {
  game.running = false;
  stopGameMusic();
  setGameStatus(statusKey);
  if (statusKey === "game.victory") playGameSound("victory");
  else if (statusKey === "game.gameOver") playGameSound("gameover");
  $("#gameStart").textContent = t("game.restart");
  updateGameHud();
  drawGame();
}
function initGame() {
  stopGameMusic();
  game.running = false;
  game.paused = false;
  game.pauseReasons.clear();
  game.score = 0;
  game.sun = gameDifficulty().initialSun;
  game.wave = 1;
  game.waveTarget = WAVE_TARGET(game.wave, game.difficulty);
  game.waveSpawned = 0;
  game.totalSpawned = 0;
  game.waveClearTimer = 0;
  game.elapsed = 0;
  game.shovel = false;
  game.seedCooldowns = {};
  game.skillCooldowns = {};
  game.energy = 60;
  game.rallyTimer = 0;
  game.timeStopTimer = 0;
  game.skillPulseFlash = 0;
  game.autoSun = localStorage.getItem("minicc-game-auto-sun") !== "off";
  game.plants = [];
  game.zombies = [];
  game.defeated = [];
  game.suns = [];
  game.shots = [];
  game.particles = [];
  game.impacts = [];
  game.popups = [];
  game.mowers = Array.from({ length: gameLayout.rows }, (_, row) => ({ row, x: 57, active: false, used: false, seed: Math.random() * 1000 }));
  game.combo = 0;
  game.comboTimer = 0;
  game.bestCombo = 0;
  game.bannerTimer = 0;
  game.bannerText = "";
  game.bannerColor = "#ffe27c";
  game.dangerPulse = 0;
  game.hoverCell = null;
  game.last = 0;
  game.hudAt = 0;
  game.renderStats = { frames: 0, fps: 0, lastFrameMs: 0, maxFrameMs: 0, longFrames: 0, frameSamples: [], recentSamples: new Array(60), recentSampleIndex: 0, recentSampleCount: 0, recentLongFrames: 0, windowStartedAt: 0, windowFrames: 0, indexRebuilds: 0, rowQueries: 0, rowCandidates: 0, drawCalls: 0, plantDraws: 0, zombieDraws: 0, animationSwitches: 0 };
  resizeGameCanvas();
  game.spawnTimer = 0;
  game.skyTimer = 0;
  game.dangerTimer = 0;
  $("#gameAutoSun").checked = game.autoSun;
  $("#gameDifficulty").value = game.difficulty;
  clearPlantSelection();
  updateShovelButton();
  updatePauseButton();
  updateSoundButton();
  updateGameHud();
  setGameStatus("game.ready");
  $("#gameStart").textContent = t("game.start");
  drawGame();
}
function roundedRect(ctx, x, y, width, height, radius) { ctx.beginPath(); ctx.roundRect(x, y, width, height, radius); }
function drawSun(ctx, sun) { const pulse = 1 + Math.sin(sun.age / 230) * .08; const glow = gameRender.effects === "low" ? 0 : 18; ctx.save(); ctx.translate(sun.x, sun.y); ctx.scale(pulse, pulse); ctx.shadowColor = "rgba(255, 215, 84, .75)"; ctx.shadowBlur = glow; ctx.fillStyle = "#ffd75b"; ctx.beginPath(); ctx.arc(0, 0, 15, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0; ctx.strokeStyle = "#fff3a5"; ctx.lineWidth = 3; for (let i = 0; i < 8; i += 1) { const angle = i * Math.PI / 4; ctx.beginPath(); ctx.moveTo(Math.cos(angle) * 19, Math.sin(angle) * 19); ctx.lineTo(Math.cos(angle) * 25, Math.sin(angle) * 25); ctx.stroke(); } ctx.fillStyle = "#fff4a8"; ctx.beginPath(); ctx.arc(-4, -4, 4, 0, Math.PI * 2); ctx.fill(); ctx.restore(); }
function drawMower(ctx, mower, now) {
  if (!mower || mower.used && !mower.active) return;
  const y = cellPosition(mower.row, 0).y + 22;
  const vibration = mower.active ? Math.sin((now + mower.seed) / 34) * 1.8 : Math.sin((now + mower.seed) / 480) * .6;
  ctx.save();
  ctx.translate(mower.x, y + vibration);
  if (gameRender.effects !== "low" && mower.active) {
    ctx.shadowColor = "rgba(255, 180, 83, .72)";
    ctx.shadowBlur = 13;
  }
  ctx.fillStyle = "#c96545";
  roundedRect(ctx, -18, -13, 34, 18, 4);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.fillStyle = "#e9c06b";
  ctx.fillRect(-11, -25, 5, 14);
  ctx.strokeStyle = "#e9c06b";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(-8, -25);
  ctx.lineTo(6, -34);
  ctx.lineTo(12, -33);
  ctx.stroke();
  ctx.fillStyle = "#202f32";
  ctx.beginPath();
  ctx.arc(-10, 8, 6, 0, Math.PI * 2);
  ctx.arc(11, 8, 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#91a8a0";
  ctx.beginPath();
  ctx.arc(-10, 8, 2, 0, Math.PI * 2);
  ctx.arc(11, 8, 2, 0, Math.PI * 2);
  ctx.fill();
  if (mower.active) {
    ctx.fillStyle = "#ffe28a";
    ctx.beginPath();
    ctx.arc(20, -3, 3 + Math.abs(Math.sin(now / 50)) * 2, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}
function drawPlacementPreview(ctx, now) {
  const cell = game.hoverCell;
  if (!game.running || !cell || (!game.selected && !game.shovel)) return;
  const existing = game.plants.find((plant) => plant.row === cell.row && plant.col === cell.col);
  const covering = game.selected === "pumpkin" && existing && existing.type !== "pumpkin";
  const valid = game.shovel
    ? Boolean(existing)
    : Boolean(game.selected && (!existing || covering) && game.sun >= (plantCost[game.selected] || Infinity) && !(game.seedCooldowns[game.selected] > 0));
  const x = gameLayout.left + cell.col * gameLayout.cellW + 2;
  const y = gameLayout.top + cell.row * gameLayout.cellH + 2;
  ctx.save();
  ctx.fillStyle = valid ? "rgba(184, 245, 170, .18)" : "rgba(244, 120, 100, .2)";
  ctx.strokeStyle = valid ? "rgba(237, 255, 178, .9)" : "rgba(255, 145, 124, .9)";
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 4]);
  roundedRect(ctx, x, y, 66, 61, 8);
  ctx.fill();
  ctx.stroke();
  ctx.setLineDash([]);
  if (!game.shovel && game.selected && valid) {
    const preview = { type: game.selected, row: cell.row, col: cell.col, hp: plantHealth[game.selected], seed: 1, age: now, sunTimer: 0, shotTimer: 0, bombTimer: 0, disabledTimer: 0, armed: game.selected !== "potatomine" };
    ctx.globalAlpha = .46;
    drawPlant(ctx, preview, now);
  }
  ctx.restore();
}
function drawGamePopup(ctx, popup) {
  const alpha = Math.max(0, Math.min(1, popup.life / popup.maxLife));
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.font = "700 11px DM Mono, Consolas, monospace";
  ctx.textAlign = "center";
  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(22, 39, 32, .7)";
  ctx.strokeText(popup.text, popup.x, popup.y);
  ctx.fillStyle = popup.color;
  ctx.fillText(popup.text, popup.x, popup.y);
  ctx.restore();
}
function drawPlant(ctx, plant, now) {
  if (plant.type === "pumpkin" && plant.underPlant) drawPlant(ctx, plant.underPlant, now);
  const { x, y } = cellPosition(plant.row, plant.col);
  const breathe = 1 + Math.sin((now + plant.seed) / 620) * .025;
  const bob = Math.sin((now + plant.seed) / 430) * (plant.type === "spikeweed" ? .7 : 1.8);
  const leaf = (lx, ly, angle, color = "#3d9b5c") => { ctx.save(); ctx.translate(lx, ly); ctx.rotate(angle); ctx.fillStyle = color; ctx.beginPath(); ctx.ellipse(0, 0, 12, 5, 0, 0, Math.PI * 2); ctx.fill(); ctx.restore(); };
  const stem = (height = 24, color = "#2f744d") => { ctx.strokeStyle = color; ctx.lineWidth = 5; ctx.lineCap = "round"; ctx.beginPath(); ctx.moveTo(0, 21); ctx.lineTo(0, 21 - height); ctx.stroke(); };
  const peaFace = (color, mouth = 10) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(0, -17, 15, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#193c32"; ctx.beginPath(); ctx.arc(10, -17, mouth, -.45, .45); ctx.fill(); ctx.fillStyle = "#f3f4ca"; ctx.beginPath(); ctx.arc(13, -17, 3, 0, Math.PI * 2); ctx.fill(); };
  ctx.save(); ctx.translate(x, y + bob); ctx.scale(breathe, breathe);
  if (plant.sunlightBoost && gameRender.effects !== "low") {
    const pulse = 1 + Math.sin((now + plant.seed) / 180) * .08;
    ctx.save();
    ctx.globalAlpha = .42;
    ctx.strokeStyle = "#ffe58a";
    ctx.lineWidth = 2;
    ctx.shadowColor = "#ffd76a";
    ctx.shadowBlur = 10;
    ctx.beginPath();
    ctx.arc(0, -8, 28 * pulse, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }
  ctx.fillStyle = "rgba(17, 51, 32, .3)"; ctx.beginPath(); ctx.ellipse(0, 25, 24, 7, 0, 0, Math.PI * 2); ctx.fill();
  switch (plant.type) {
    case "sunflower": stem(); leaf(-12, 13, -.45); leaf(12, 15, .45); for (let i = 0; i < 10; i += 1) { const a = i * Math.PI / 5; ctx.fillStyle = i % 2 ? "#f4b83f" : "#ffd966"; ctx.beginPath(); ctx.ellipse(Math.cos(a) * 15, -8 + Math.sin(a) * 15, 7, 13, a, 0, Math.PI * 2); ctx.fill(); } ctx.fillStyle = "#75482d"; ctx.beginPath(); ctx.arc(0, -8, 11, 0, Math.PI * 2); ctx.fill(); break;
    case "wallnut": ctx.fillStyle = "#a66a45"; ctx.beginPath(); ctx.ellipse(0, -3, 23, 29, 0, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#70452f"; ctx.lineWidth = 2; ctx.stroke(); ctx.fillStyle = "#1d302c"; ctx.beginPath(); ctx.arc(-7, -11, 2, 0, Math.PI * 2); ctx.arc(7, -11, 2, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#1d302c"; ctx.beginPath(); ctx.arc(0, -2, 8, .15, Math.PI - .15); ctx.stroke(); break;
    case "pumpkin": ctx.fillStyle = "#e27d31"; ctx.beginPath(); ctx.ellipse(0, -4, 24, 27, 0, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#a94f29"; ctx.lineWidth = 3; ctx.beginPath(); ctx.ellipse(-9, -4, 9, 25, 0, 0, Math.PI * 2); ctx.ellipse(9, -4, 9, 25, 0, 0, Math.PI * 2); ctx.stroke(); ctx.fillStyle = "#28352e"; ctx.beginPath(); ctx.arc(-8, -7, 4, 0, Math.PI * 2); ctx.arc(8, -7, 4, 0, Math.PI * 2); ctx.fill(); ctx.fillRect(-8, 3, 16, 3); break;
    case "cherrybomb": ctx.strokeStyle = "#4a744a"; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(0, -20); ctx.quadraticCurveTo(4, -34, 14, -36); ctx.stroke(); ctx.fillStyle = "#c94556"; ctx.beginPath(); ctx.arc(-10, -7, 14, 0, Math.PI * 2); ctx.arc(10, -7, 14, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#ffb08b"; ctx.beginPath(); ctx.arc(-14, -12, 4, 0, Math.PI * 2); ctx.arc(6, -12, 4, 0, Math.PI * 2); ctx.fill(); break;
    case "potatomine": ctx.fillStyle = "#ad844e"; ctx.beginPath(); ctx.ellipse(0, 5, 23, 16, 0, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#db5a4d"; ctx.beginPath(); ctx.arc(0, -13, 6, Math.PI, 0); ctx.fill(); ctx.fillStyle = "#2d382e"; ctx.beginPath(); ctx.arc(-8, 1, 3, 0, Math.PI * 2); ctx.arc(8, 1, 3, 0, Math.PI * 2); ctx.fill(); break;
    case "spikeweed": ctx.fillStyle = "#4f9c55"; ctx.beginPath(); ctx.moveTo(-25, 19); ctx.lineTo(-15, -6); ctx.lineTo(-7, 17); ctx.lineTo(0, -11); ctx.lineTo(8, 17); ctx.lineTo(17, -6); ctx.lineTo(25, 19); ctx.closePath(); ctx.fill(); ctx.fillStyle = "#d8eb9c"; for (let i = -18; i <= 18; i += 9) { ctx.beginPath(); ctx.arc(i, 13, 2, 0, Math.PI * 2); ctx.fill(); } break;
    case "gloomshroom": stem(23, "#624478"); ctx.fillStyle = "#7750a0"; ctx.beginPath(); ctx.arc(0, -17, 21, Math.PI, Math.PI * 2); ctx.lineTo(17, -9); ctx.quadraticCurveTo(0, -1, -17, -9); ctx.closePath(); ctx.fill(); ctx.fillStyle = "#d4a9ef"; ctx.beginPath(); ctx.arc(-9, -16, 3, 0, Math.PI * 2); ctx.arc(5, -21, 3, 0, Math.PI * 2); ctx.arc(12, -10, 2, 0, Math.PI * 2); ctx.fill(); break;
    case "jalapeno": ctx.fillStyle = "#ef654d"; ctx.beginPath(); ctx.moveTo(-4, 20); ctx.bezierCurveTo(-23, 5, -19, -22, 3, -28); ctx.bezierCurveTo(24, -23, 22, 9, 5, 20); ctx.closePath(); ctx.fill(); ctx.fillStyle = "#3c824d"; ctx.fillRect(-4, -31, 9, 7); ctx.fillStyle = "#fff0b0"; ctx.beginPath(); ctx.arc(-8, -8, 3, 0, Math.PI * 2); ctx.arc(7, -8, 3, 0, Math.PI * 2); ctx.fill(); break;
    case "garlic": ctx.fillStyle = "#f1e5bc"; ctx.beginPath(); ctx.moveTo(0, -30); ctx.bezierCurveTo(-22, -23, -20, 11, 0, 20); ctx.bezierCurveTo(20, 11, 22, -23, 0, -30); ctx.fill(); ctx.strokeStyle = "#c7b886"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(0, -27); ctx.lineTo(0, 15); ctx.moveTo(-2, -22); ctx.quadraticCurveTo(-11, -4, -7, 10); ctx.moveTo(2, -22); ctx.quadraticCurveTo(11, -4, 7, 10); ctx.stroke(); break;
    case "squash": ctx.fillStyle = "#e5ad43"; ctx.beginPath(); ctx.ellipse(0, -1, 25, 17, -.1, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#9a6434"; ctx.lineWidth = 2; ctx.beginPath(); ctx.ellipse(-10, -1, 9, 16, 0, 0, Math.PI * 2); ctx.ellipse(10, -1, 9, 16, 0, 0, Math.PI * 2); ctx.stroke(); ctx.fillStyle = "#25382e"; ctx.beginPath(); ctx.arc(-8, -4, 3, 0, Math.PI * 2); ctx.arc(8, -4, 3, 0, Math.PI * 2); ctx.fill(); break;
    case "kernelpult": stem(20); leaf(-13, 13, -.5); leaf(13, 14, .5); ctx.fillStyle = "#e8c54f"; ctx.beginPath(); ctx.ellipse(0, -18, 15, 18, -.2, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#6aa84f"; ctx.fillRect(-7, -35, 13, 5); break;
    case "magnetshroom": stem(21, "#704c80"); ctx.fillStyle = "#bd79b9"; ctx.beginPath(); ctx.arc(0, -14, 20, Math.PI, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#303a4d"; ctx.fillRect(-10, -9, 20, 5); break;
    case "icepeashooter": stem(); leaf(-12, 13, -.45, "#5da6ba"); leaf(12, 14, .45, "#5da6ba"); peaFace("#87d8e9"); ctx.strokeStyle = "#e9ffff"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(0, -17, 19, 0, Math.PI * 2); ctx.stroke(); break;
    case "firepeashooter": stem(); leaf(-12, 13, -.45); leaf(12, 14, .45); peaFace("#e65e49"); ctx.fillStyle = "#ffbf4f"; ctx.beginPath(); ctx.moveTo(-8, -31); ctx.lineTo(0, -43); ctx.lineTo(5, -30); ctx.lineTo(13, -39); ctx.lineTo(11, -22); ctx.closePath(); ctx.fill(); break;
    case "twinpea": stem(); leaf(-12, 13, -.45); leaf(12, 14, .45); ctx.fillStyle = "#7bc65c"; ctx.beginPath(); ctx.arc(-8, -16, 12, 0, Math.PI * 2); ctx.arc(8, -16, 12, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#193c32"; ctx.beginPath(); ctx.arc(-18, -16, 7, -.4, .4); ctx.arc(18, -16, 7, Math.PI - .4, Math.PI + .4); ctx.fill(); break;
    case "repeater": case "threepeater": case "gatlingpea": case "peashooter": stem(); leaf(-12, 13, -.45); leaf(12, 14, .45); peaFace(plant.type === "gatlingpea" ? "#45a86b" : plant.type === "threepeater" ? "#77c979" : plant.type === "repeater" ? "#70c77b" : "#61b59d", plant.type === "gatlingpea" ? 13 : 10); if (plant.type === "threepeater") { ctx.fillStyle = "#74c979"; ctx.beginPath(); ctx.arc(-12, -13, 10, 0, Math.PI * 2); ctx.arc(12, -13, 10, 0, Math.PI * 2); ctx.fill(); } if (plant.type === "gatlingpea") { ctx.fillStyle = "#214c3e"; ctx.fillRect(5, -28, 25, 7); ctx.fillRect(5, -18, 27, 7); ctx.fillRect(5, -8, 23, 7); } break;
    default: stem(); leaf(-12, 13, -.45); leaf(12, 14, .45); peaFace(plantColor[plant.type] || "#62b5a0");
  }
  if (plant.hp < plantHealth[plant.type]) { ctx.fillStyle = "rgba(18, 28, 24, .8)"; ctx.fillRect(-20, 30, 40, 4); ctx.fillStyle = plant.hp / plantHealth[plant.type] > .4 ? "#78d69b" : "#f6a45e"; ctx.fillRect(-20, 30, 40 * Math.max(0, plant.hp / plantHealth[plant.type]), 4); }
  ctx.restore();
}
function drawZombie(ctx, zombie, now) {
  const giant = zombie.type === "gargantuar";
  const cycle = (zombie.age || 0) + zombie.seed;
  const fast = zombie.type === "runner" || zombie.type === "imp";
  const gait = Math.sin(cycle / (fast ? 70 : 145));
  const stride = gait * (fast ? 6 : 4);
  const bob = Math.abs(gait) * (giant ? 2.4 : 1.6);
  const attackProgress = zombie.attacking ? (zombie.attackTimer || 0) / Math.max(1, zombie.attackInterval) : 0;
  const attackWindup = zombie.attacking && attackProgress > .52 ? Math.sin(Math.min(1, (attackProgress - .52) / .48) * Math.PI) : 0;
  const hitStagger = zombie.staggerTimer > 0 ? Math.min(1, zombie.staggerTimer / 180) : 0;
  const dashPose = ["runner", "imp", "scout"].includes(zombie.type) && zombie.dashTimer > 0 ? 1 : 0;
  const chargePose = zombie.type === "football" && zombie.chargeTimer > 0 ? 1 : 0;
  const leapPose = zombie.leapTimer > 0 ? Math.sin(Math.min(1, zombie.leapTimer / 1800) * Math.PI) : 0;
  const burrowed = zombie.type === "miner" && zombie.burrowTimer > 0;
  const armSwing = Math.sin(cycle / (fast ? 70 : 145) + Math.PI) * (fast ? 8 : 5);
  const actionPulse = zombie.flashTimer > 0 ? Math.sin(now / 18) * 3 : 0;
  const skillPulse = (zombie.breathTimer > 0 && zombie.breathTimer < 520) || (zombie.smashTimer > 0 && zombie.smashTimer < 520) || (zombie.curseTimer > 0 && zombie.curseTimer < 520) || (zombie.stormTimer > 0 && zombie.stormTimer < 520) || (zombie.summonTimer > 0 && zombie.summonTimer < 520);
  const scale = giant ? 1.32 : zombie.type === "imp" ? .78 : 1;
  const body = ZOMBIE_BODY_COLORS[zombie.type] || ZOMBIE_BODY_COLORS.walker;
  const lean = attackWindup * -.13 + dashPose * .08 + chargePose * .12 + hitStagger * .1;
  const burrowOffset = burrowed ? 10 + Math.sin(cycle / 90) * 2 : 0;
  ctx.save();
  ctx.translate(zombie.x + hitStagger * 6 - dashPose * 4, zombie.y - bob - burrowOffset + actionPulse - leapPose * 13);
  ctx.rotate(lean);
  ctx.scale(scale * (1 + chargePose * .04), scale * (1 - chargePose * .025));
  if (burrowed) ctx.globalAlpha = .62;
  ctx.fillStyle = "rgba(20, 27, 29, .32)"; ctx.beginPath(); ctx.ellipse(0, 27 + bob + leapPose * 13, 24 + Math.abs(stride) * .25, 7, 0, 0, Math.PI * 2); ctx.fill();
  const legLift = leapPose * 8 + dashPose * 3;
  const legSwing = stride + leapPose * 9;
  ctx.strokeStyle = "#26333a"; ctx.lineWidth = 5; ctx.lineCap = "round"; ctx.beginPath(); ctx.moveTo(-7, 14); ctx.lineTo(-12 + legSwing, 30 - legLift); ctx.moveTo(7, 14); ctx.lineTo(12 - legSwing, 30 - legLift * .55); ctx.stroke();
  const reach = attackWindup * 15 + chargePose * 7;
  const poseArmSwing = armSwing - attackWindup * 12 + dashPose * 5;
  ctx.strokeStyle = body; ctx.lineWidth = giant ? 6 : 4; ctx.beginPath(); ctx.moveTo(-13, 3); ctx.lineTo(-23 - poseArmSwing - reach, 15 - attackWindup * 5); ctx.moveTo(13, 3); ctx.lineTo(23 + poseArmSwing + reach, 15 - attackWindup * 5); ctx.stroke();
  if (dashPose && gameRender.effects !== "low") { ctx.globalAlpha = .22; ctx.strokeStyle = zombie.type === "scout" ? "#f5cf63" : "#e57b70"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(-10, 10); ctx.lineTo(-42, 16); ctx.moveTo(2, 16); ctx.lineTo(-28, 25); ctx.stroke(); ctx.globalAlpha = 1; }
  if (zombie.elite && gameRender.effects !== "low") { const elitePulse = 1 + Math.sin((now + zombie.seed) / 160) * .08; ctx.globalAlpha = .2 + Math.abs(Math.sin((now + zombie.seed) / 260)) * .18; ctx.strokeStyle = "#ffcf6b"; ctx.lineWidth = 2; ctx.shadowColor = "#ff9b5f"; ctx.shadowBlur = 12; ctx.beginPath(); ctx.arc(0, -12, 31 * elitePulse, 0, Math.PI * 2); ctx.stroke(); ctx.shadowBlur = 0; ctx.globalAlpha = 1; }
  if (zombie.attackFlashTimer > 0) { ctx.globalAlpha = Math.min(1, zombie.attackFlashTimer / 90); ctx.strokeStyle = "#ffd47a"; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(19 + reach, 12 - attackWindup * 5, 8 + attackWindup * 8, -.7, .7); ctx.stroke(); ctx.globalAlpha = 1; }
  if (skillPulse) { ctx.strokeStyle = zombie.type === "dragon" ? "rgba(255,145,84,.72)" : "rgba(195,168,255,.62)"; ctx.lineWidth = 2; ctx.globalAlpha = .45 + Math.abs(Math.sin(now / 90)) * .4; ctx.beginPath(); ctx.arc(0, -8, 28 + Math.abs(gait) * 4, 0, Math.PI * 2); ctx.stroke(); ctx.globalAlpha = 1; }
  ctx.fillStyle = body; roundedRect(ctx, -16, -1, giant ? 34 : 31, 27, 8); ctx.fill(); ctx.fillStyle = zombie.flashTimer > 0 ? "#fff7d7" : "#b9c7a9"; ctx.beginPath(); ctx.arc(0, -17, giant ? 18 : 15, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#29303d"; ctx.beginPath(); ctx.arc(-5, -18, 3, 0, Math.PI * 2); ctx.arc(6, -18, 3, 0, Math.PI * 2); ctx.fill();
  if (zombie.type === "roadblock") { ctx.fillStyle = "#efbd62"; ctx.fillRect(-20, -33, 40, 7); ctx.fillStyle = "#b95942"; ctx.fillRect(-15, -38, 30, 5); } if (zombie.type === "bucket") { ctx.fillStyle = "#aab4bd"; ctx.fillRect(-18, -34, 36, 16); ctx.fillStyle = "#65717d"; ctx.fillRect(-21, -20, 42, 4); } if (zombie.type === "conehead") { ctx.fillStyle = "#eb873e"; ctx.beginPath(); ctx.moveTo(0, -48); ctx.lineTo(-15, -27); ctx.lineTo(15, -27); ctx.closePath(); ctx.fill(); ctx.fillStyle = "#f4c15f"; ctx.fillRect(-17, -29, 34, 5); } if (zombie.type === "football") { ctx.fillStyle = "#c76c50"; ctx.beginPath(); ctx.ellipse(0, -33, 21, 8, 0, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#dbe4ed"; ctx.fillRect(-14, -35, 28, 3); } if (zombie.type === "miner") { ctx.fillStyle = "#d59c3d"; ctx.beginPath(); ctx.arc(0, -32, 18, Math.PI, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#fff0a0"; ctx.beginPath(); ctx.arc(0, -37, 5, 0, Math.PI * 2); ctx.fill(); } if (zombie.type === "flag") { ctx.strokeStyle = "#e0b26e"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(17, 16); ctx.lineTo(17, -40); ctx.stroke(); ctx.fillStyle = "#ef786c"; ctx.beginPath(); ctx.moveTo(18, -39); ctx.lineTo(36, -32); ctx.lineTo(18, -25); ctx.fill(); } if (zombie.type === "polevault") { ctx.strokeStyle = "#dfad70"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(-20, 20); ctx.lineTo(23, -40); ctx.stroke(); } if (zombie.type === "dancer") { ctx.strokeStyle = "#f2c2dd"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(-17, 4); ctx.lineTo(-31, -12); ctx.moveTo(17, 4); ctx.lineTo(31, -12); ctx.stroke(); } if (zombie.type === "newspaper") { ctx.fillStyle = "#f4e2b0"; ctx.fillRect(-24, -3, 15, 20); } if (zombie.type === "witch") { ctx.fillStyle = "#30233d"; ctx.beginPath(); ctx.moveTo(-19, -29); ctx.lineTo(0, -53); ctx.lineTo(19, -29); ctx.closePath(); ctx.fill(); ctx.fillStyle = "#dcb5ff"; ctx.beginPath(); ctx.arc(0, -32, 5, 0, Math.PI * 2); ctx.fill(); } if (zombie.type === "dragon") { ctx.fillStyle = "#d49b50"; ctx.beginPath(); ctx.moveTo(-18, -2); ctx.lineTo(-34, -18); ctx.lineTo(-25, 6); ctx.lineTo(-15, 7); ctx.moveTo(18, -2); ctx.lineTo(34, -18); ctx.lineTo(25, 6); ctx.lineTo(15, 7); ctx.fill(); } if (zombie.type === "gargantuar") { ctx.fillStyle = "#b8c4d1"; ctx.fillRect(17, -2, 8, 31); ctx.fillStyle = "#d99a5e"; ctx.beginPath(); ctx.arc(21, 31, 9, 0, Math.PI * 2); ctx.fill(); }
  if (zombie.slowTimer > 0) { ctx.strokeStyle = "#a7e8f3"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(0, -3, 25, 0, Math.PI * 2); ctx.stroke(); } if (zombie.armor > 0) { ctx.strokeStyle = "#e4c36b"; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(0, -17, 20, Math.PI, Math.PI * 2); ctx.stroke(); } if (zombie.hp < zombie.maxHp) { ctx.fillStyle = "rgba(25, 33, 26, .8)"; ctx.fillRect(-21, 35, 42, 4); ctx.fillStyle = zombie.armor > 0 ? "#e9c66a" : "#e48374"; ctx.fillRect(-21, 35, 42 * Math.max(0, zombie.hp / zombie.maxHp), 4); }
  ctx.restore();
}
function drawShot(ctx, shot, now) {
  const bob = shot.kind === "kernel" ? Math.sin((now + shot.seed) / 80) * 3 : 0;
  ctx.save();
  ctx.translate(shot.x, shot.y + bob);
  ctx.rotate(shot.angle || 0);
  ctx.globalAlpha = .3;
  ctx.strokeStyle = shot.color;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(-Math.min(30, shot.distance || 12), 0);
  ctx.lineTo(-5, 0);
  ctx.stroke();
  ctx.globalAlpha = 1;
  if (gameRender.effects !== "low") {
    ctx.shadowColor = shot.glow || shot.color;
    ctx.shadowBlur = shot.kind === "fire" ? 18 : 11;
  }
  ctx.fillStyle = shot.color;
  if (shot.kind === "kernel") ctx.fillRect(-7, -5, 13, 10);
  else if (shot.kind === "ice") {
    ctx.beginPath(); ctx.moveTo(8, 0); ctx.lineTo(0, -8); ctx.lineTo(-8, 0); ctx.lineTo(0, 8); ctx.closePath(); ctx.fill();
  } else {
    ctx.beginPath(); ctx.arc(0, 0, shot.kind === "fire" ? 7 : 6, 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();
}
function drawImpact(ctx, impact) { const progress = 1 - impact.life / impact.maxLife; const radius = impact.radius * (.35 + progress * .9); ctx.save(); ctx.globalAlpha = Math.max(0, impact.life / impact.maxLife); ctx.strokeStyle = impact.color; ctx.lineWidth = Math.max(1, 4 - progress * 3); ctx.beginPath(); ctx.arc(impact.x, impact.y, radius, 0, Math.PI * 2); ctx.stroke(); ctx.restore(); }
function drawGame() {
  if (!gameRender.ctx || !gameRender.background) resizeGameCanvas();
  const canvas = gameRender.canvas;
  const ctx = gameRender.ctx;
  if (!canvas || !ctx || !gameRender.background) return;
  const startedAt = performance.now();
  const now = startedAt;
  ctx.drawImage(gameRender.background, 0, 0);
  ctx.fillStyle = "#a8d5a1";
  ctx.font = "10px DM Mono, monospace";
  ctx.fillText(game.running ? "DEFEND THE LAWN" : "READY FOR BATTLE", 18, 42);
  game.suns.forEach((sun) => drawSun(ctx, sun));
  game.plants.forEach((plant) => drawPlant(ctx, plant, now));
  game.shots.forEach((shot) => drawShot(ctx, shot, now));
  game.zombies.forEach((zombie) => drawZombie(ctx, zombie, now));
  // The mower is a foreground lane object, so it visibly passes over zombies.
  game.mowers.forEach((mower) => drawMower(ctx, mower, now));
  game.impacts.forEach((impact) => drawImpact(ctx, impact));
  const particleStride = gameRender.effects === "low" ? 2 : 1;
  for (let index = 0; index < game.particles.length; index += particleStride) {
    const particle = game.particles[index];
    ctx.globalAlpha = Math.max(0, particle.life / particle.maxLife);
    ctx.fillStyle = particle.color;
    ctx.beginPath();
    ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  drawPlacementPreview(ctx, now);
  game.popups.forEach((popup) => drawGamePopup(ctx, popup));
  if (game.bannerTimer > 0 && game.bannerText) {
    const alpha = Math.min(1, game.bannerTimer / 260);
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.fillStyle = "rgba(23, 42, 40, .88)";
    roundedRect(ctx, 250, 10, 220, 34, 9);
    ctx.fill();
    ctx.strokeStyle = game.bannerColor;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.fillStyle = game.bannerColor;
    ctx.font = "700 12px DM Mono, Consolas, monospace";
    ctx.textAlign = "center";
    ctx.fillText(game.bannerText, 360, 32);
    ctx.restore();
  }
  if (game.dangerPulse > 0) {
    ctx.save();
    const alpha = .16 + Math.abs(Math.sin(now / 85)) * .18;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = "#ef725f";
    ctx.fillRect(0, 60, 65, GAME_LOGICAL_HEIGHT - 60);
    ctx.strokeStyle = "#ff9a77";
    ctx.lineWidth = 3;
    ctx.strokeRect(4, 64, 56, GAME_LOGICAL_HEIGHT - 69);
    ctx.restore();
  }
  if (game.skillPulseFlash > 0) {
    ctx.save();
    const pulseAlpha = Math.min(.34, game.skillPulseFlash / 620 * .34);
    ctx.globalAlpha = pulseAlpha;
    ctx.fillStyle = game.rallyTimer > 0 ? "#f5c96b" : "#bdf8ff";
    ctx.fillRect(68, 58, GAME_LOGICAL_WIDTH - 68, GAME_LOGICAL_HEIGHT - 58);
    ctx.globalAlpha = Math.min(.8, pulseAlpha * 2.4);
    ctx.strokeStyle = game.rallyTimer > 0 ? "#ffe49a" : "#d9fbff";
    ctx.lineWidth = 4;
    ctx.strokeRect(72, 62, GAME_LOGICAL_WIDTH - 78, GAME_LOGICAL_HEIGHT - 68);
    ctx.restore();
  }
  recordGameFrame(now, startedAt);
}
function zombieTypeForWave() {
  const roll = Math.random();
  const pressure = game.difficulty === "nightmare" ? 1.25 : game.difficulty === "normal" ? .82 : 1;
  const nightmare = game.difficulty === "nightmare";
  const choices = [
    [10, Math.min(.18, .07 + (game.wave - 9) * .035) * pressure, "gargantuar"],
    [8, Math.min(.18, (.035 + game.wave * .012) * pressure), "dragon"],
    [7, Math.min(.22, (.04 + game.wave * .014) * pressure), "witch"],
    [6, Math.min(.24, (.05 + game.wave * .016) * pressure), "shield"],
    [3, Math.min(.24, (.04 + game.wave * .012) * pressure), "conehead"],
    [2, Math.min(.28, (.07 + game.wave * .016) * pressure), "imp"],
    [4, Math.min(.18, (.025 + game.wave * .011) * pressure), "scout"],
    [6, Math.min(.16, (.02 + game.wave * .009) * pressure), "storm"],
    [4, Math.min(.20, (.05 + game.wave * .01) * pressure), "newspaper"],
    [7, Math.min(.16, (.025 + game.wave * .01) * pressure), "dancer"],
    [5, Math.min(.30, (.045 + game.wave * .018) * pressure), "football"],
    [4, Math.min(.22, (.04 + game.wave * .014) * pressure), "polevault"],
    [4, Math.min(.25, (.035 + game.wave * .014) * pressure), "miner"],
    [3, Math.min(.22, (.045 + game.wave * .01) * pressure), "flag"],
    [3, Math.min(.38, (.11 + game.wave * .014) * pressure), "bucket"],
    [2, Math.min(.52, (.25 + game.wave * .018) * pressure), "runner"],
    [2, Math.min(.82, (.42 + game.wave * .022) * pressure), "roadblock"],
  ];
  if (nightmare && game.wave >= 6 && game.waveSpawned % 5 === 4) return ["shield", "witch", "dragon", "gargantuar"][game.wave % 4];
  let threshold = 0;
  for (const [minimumWave, chance, type] of choices) {
    if (game.wave < minimumWave) continue;
    threshold += chance;
    if (roll < threshold) return type;
  }
  return "walker";
}
function spawnZombie() {
  if (game.waveSpawned >= game.waveTarget) return;
  const row = Math.floor(Math.random() * gameLayout.rows);
  const type = zombieTypeForWave();
  const profile = zombieProfiles[type];
  const difficulty = gameDifficulty();
  const hpGrowth = type === "gargantuar" ? 2.2 : type === "dragon" ? 1.55 : type === "witch" ? 1.2 : type === "shield" ? 1.25 : type === "football" ? 1.35 : type === "bucket" ? 1.2 : type === "miner" ? 1 : type === "roadblock" ? .85 : .7;
  const nightmareElite = game.difficulty === "nightmare" && game.wave >= 6 && ["dragon", "witch", "shield", "football", "gargantuar"].includes(type);
  const hp = Math.max(1, Math.round((profile.hp + Math.floor(game.wave * hpGrowth)) * difficulty.hpMultiplier * (nightmareElite ? 1.18 : 1)));
  game.zombies.push({
    x: 704,
    y: cellPosition(row, 0).y,
    row,
    hp,
    maxHp: hp,
    armor: profile.armor || 0,
    type,
    speed: (profile.speed + game.wave * profile.growth) * difficulty.speedMultiplier,
    attackInterval: profile.attackInterval,
    slowTimer: 0,
    burrowTimer: profile.burrow ? 1000 : 0,
    seed: Math.random() * 1000,
    age: 0,
    garlicTimer: 0,
    vaultTimer: 0,
    summonTimer: 0,
    flashTimer: 0,
    dashTimer: 0,
    leapTimer: 0,
    chargeTimer: 0,
    curseTimer: 0,
    breathTimer: 0,
    smashTimer: 0,
    armorTimer: 0,
    guardTimer: 0,
    burnTimer: 0,
    burnTickTimer: 0,
    stormTimer: 0,
    markTimer: 0,
    attackTimer: 0,
    attacking: false,
    staggerTimer: 0,
    elite: nightmareElite,
  });
  game.waveSpawned += 1;
  game.totalSpawned += 1;
  if (game.wave > 1 && game.waveSpawned === 1) setGameStatus("game.running");
  if (game.waveSpawned === game.waveTarget) {
    playGameSound("wave");
    addGameParticle(360, 60, "#ffe27c", 18, .18);
  }
  updateGameHud(true);
}
function produceSun(plant) {
  const position = cellPosition(plant.row, plant.col);
  game.suns.push({ x: position.x + (Math.random() - .5) * 24, y: position.y - 28, age: 0, targetY: position.y - 5 });
  addGameParticle(position.x, position.y - 22, "#ffe17b", 8, .12);
}
function collectSunAt(index, x, y) {
  if (index < 0 || !game.suns[index]) return false;
  game.suns.splice(index, 1);
  game.sun += 25;
  updateGameHud(true);
  addGameParticle(x, y, "#ffe17b", 12, .16);
  playGameSound("collect");
  return true;
}
function collectAutomaticSuns() {
  if (!game.autoSun) return;
  for (let index = game.suns.length - 1; index >= 0; index -= 1) {
    const sun = game.suns[index];
    if (sun.age > 650) collectSunAt(index, sun.x, sun.y);
  }
}
function firePlantShots(plant, profile) {
  const position = cachedCellPosition(plant);
  const rows = profile.rows ? [plant.row, plant.row - 1, plant.row + 1].filter((row) => row >= 0 && row < gameLayout.rows) : [plant.row];
  rows.forEach((row) => {
    const shotY = gameCellPositions[row]?.[plant.col]?.y || cellPosition(row, plant.col).y;
    for (let index = 0; index < profile.shots; index += 1) {
      game.shots.push({ x: position.x + 20 + index * 8, y: shotY - 5, row, damage: profile.damage, slow: profile.slow, fire: Boolean(profile.fire), burn: profile.burn || 0, burnDamage: profile.burnDamage || 0, butter: profile.butterChance ? Math.random() < profile.butterChance : false, kind: profile.fire ? "fire" : plant.type === "icepeashooter" ? "ice" : plant.type === "kernelpult" ? "kernel" : "pea", glow: profile.fire ? "#ffb347" : profile.slow ? "#bdf8ff" : "#80ed9a", color: plant.type === "icepeashooter" ? "#c9f6ff" : plant.type === "firepeashooter" ? "#ff815f" : plant.type === "kernelpult" ? "#f3cf63" : "#b5f0a2", angle: profile.fire ? -.12 : 0, seed: Math.random() * 1000, hitsLeft: 1 + (profile.pierce || 0), hitTargets: [], hit: false });
    }
  });
  playGameSound("shoot");
}
function explodeCherryBomb(plant) {
  const position = cachedCellPosition(plant);
  // Bombs can be triggered immediately after a click, before the next frame
  // rebuilds the row index. Read the authoritative array for this one-shot.
  const defeated = game.zombies.filter((zombie) => zombie.row === plant.row && Math.abs(zombie.x - position.x) < 145);
  defeated.forEach((zombie) => defeatZombie(zombie));
  removeGamePlant(plant);
  addGameParticle(position.x, position.y - 5, "#ff8d73", 34, .3);
  playGameSound("explode");
  updateGameHud();
}
function defeatZombie(zombie, source = "combat") {
  if (!zombie || zombie.defeated) return false;
  zombie.defeated = true;
  const index = game.zombies.indexOf(zombie);
  if (index >= 0) {
    removeRowEntity("zombies", zombie);
    game.zombies.splice(index, 1);
  }
  const points = zombieProfiles[zombie.type]?.score || 1;
  game.score += points;
  game.energy = Math.min(100, (game.energy || 0) + (source === "skill" ? 1 : 4));
  game.defeated.push({ type: zombie.type || "walker", points, source, at: game.elapsed });
  if (game.defeated.length > 64) game.defeated.splice(0, game.defeated.length - 64);
  game.combo = game.comboTimer > 0 ? game.combo + 1 : 1;
  game.comboTimer = GAME_COMBO_WINDOW;
  game.bestCombo = Math.max(game.bestCombo, game.combo);
  const x = Number.isFinite(zombie.x) ? zombie.x : cellPosition(zombie.row, 0).x;
  const y = Number.isFinite(zombie.y) ? zombie.y : cellPosition(zombie.row, 0).y;
  const comboText = game.combo > 1
    ? (state.locale === "zh" ? `+${points} · ${game.combo} 连击` : `+${points} · x${game.combo}`)
    : `+${points}`;
  addGamePopup(Math.max(78, Math.min(GAME_LOGICAL_WIDTH - 20, x)), y - 35, comboText, source === "mower" ? "#ffcf70" : "#fff1b0");
  if (source === "mower") addGamePopup(Math.max(78, Math.min(GAME_LOGICAL_WIDTH - 20, x)), y - 52, state.locale === "zh" ? "防线车" : "MOWER", "#ff9b70", 650);
  if (game.combo >= 3 && (game.combo === 3 || game.combo % 5 === 0)) {
    announceGame(state.locale === "zh" ? `${game.combo} 连击` : `${game.combo} COMBO`, "#ffcf70", 900);
  }
  updateGameHud(false);
  return true;
}
function triggerMower(mower) {
  if (!mower || mower.used || mower.active) return false;
  mower.used = true;
  mower.active = true;
  mower.x = 57;
  game.dangerPulse = Math.max(game.dangerPulse, 700);
  announceGame(state.locale === "zh" ? `${mower.row + 1} 行防线车出动` : `LANE ${mower.row + 1} MOWER`, "#ffb16c", 1200);
  addGameParticle(mower.x + 12, cellPosition(mower.row, 0).y + 18, "#ffb16c", 16, .22);
  playGameSound("mower");
  updateGameHud(false);
  return true;
}
function updateMowers(dt) {
  for (const mower of game.mowers) {
    if (!mower || mower.row < 0 || mower.row >= gameLayout.rows) continue;
    if (!mower.used && !mower.active && anyRowEntity("zombies", mower.row, (zombie) => !zombie.defeated && zombie.x < GAME_MOWER_TRIGGER_X)) {
      triggerMower(mower);
    }
    if (!mower.active) continue;
    mower.x += GAME_MOWER_SPEED * dt;
    const caught = rowEntitiesWhere(
      "zombies",
      mower.row,
      (zombie) => !zombie.defeated && zombie.x >= 0 && zombie.x <= mower.x + GAME_MOWER_CLEAR_RADIUS,
    );
    caught.forEach((zombie) => defeatZombie(zombie, "mower"));
    if (mower.x >= GAME_MOWER_EXIT_X) {
      mower.active = false;
      mower.x = GAME_MOWER_EXIT_X;
      addGamePopup(GAME_LOGICAL_WIDTH - 70, cellPosition(mower.row, 0).y - 12, state.locale === "zh" ? "已清场" : "CLEAR", "#9fe0b4", 700);
    }
  }
}
function updateGameEffects(dt) {
  const comboWasActive = game.comboTimer > 0;
  game.comboTimer = Math.max(0, game.comboTimer - dt);
  if (comboWasActive && game.comboTimer === 0) {
    game.combo = 0;
    updateGameHud(false);
  }
  game.bannerTimer = Math.max(0, game.bannerTimer - dt);
  game.dangerPulse = Math.max(0, game.dangerPulse - dt);
  game.skillPulseFlash = Math.max(0, (game.skillPulseFlash || 0) - dt);
  let alive = 0;
  for (const popup of game.popups) {
    popup.life -= dt;
    popup.y += (popup.vy || 0) * dt;
    popup.vy = (popup.vy || 0) - .000015 * dt;
    if (popup.life > 0) game.popups[alive++] = popup;
  }
  game.popups.length = alive;
}
function advanceWave(dt) {
  if (game.waveSpawned < game.waveTarget || game.zombies.length) {
    game.waveClearTimer = 0;
    return false;
  }
  game.waveClearTimer += dt;
  if (game.waveClearTimer < 1400) return false;
  if (game.wave >= MAX_WAVES) {
    finishGame("game.victory");
    return true;
  }
  game.wave += 1;
  game.waveTarget = WAVE_TARGET(game.wave, game.difficulty);
  game.waveSpawned = 0;
  game.waveClearTimer = 0;
  game.spawnTimer = 0;
  setGameStatus("game.waveIncoming");
  announceGame(gameWaveBanner(game.wave), "#ffe27c", 1650);
  playGameSound("wave");
  addGameParticle(360, 60, "#ffe27c", 18, .18);
  updateGameHud();
  return false;
}
function plantContainer(plant) {
  const entities = rowEntities("plants", plant?.row);
  for (let index = 0; index < entities.length; index += 1) {
    const candidate = entities[index];
    if (candidate === plant || candidate.underPlant === plant) return candidate;
  }
  // A click may add or replace a plant between animation frames. Fall back to
  // the authoritative list instead of treating that plant as nonexistent.
  return game.plants.find((candidate) => candidate === plant || candidate.underPlant === plant) || null;
}
function removeGamePlant(plant) {
  const container = plantContainer(plant);
  if (!container) return false;
  if (container === plant) {
    const index = game.plants.indexOf(container);
    if (index < 0) return false;
    const replacement = container.underPlant || null;
    removeRowEntity("plants", container);
    if (replacement) {
      game.plants.splice(index, 1, replacement);
      rowEntities("plants", replacement.row).push(replacement);
    } else game.plants.splice(index, 1);
  } else {
    container.underPlant = null;
  }
  return true;
}
function damagePlant(plant, amount, color = "#c78363") {
  const container = plant && plantContainer(plant);
  if (!container) return false;
  const target = container.type === "pumpkin" ? container : plant;
  const effectiveAmount = target.type === "pumpkin" ? amount * .5 : amount;
  target.hp -= effectiveAmount;
  const position = cellPosition(target.row, target.col);
  addGameParticle(position.x, position.y - 8, color, 4, .1);
  if (target.hp > 0) return false;
  removeGamePlant(target);
  addGameParticle(position.x, position.y, color, 12, .16);
  return true;
}
function curseNearestPlant(zombie, duration = 3000) {
  const plants = rowEntities("plants", zombie.row);
  let target = null;
  let targetX = -Infinity;
  for (let index = 0; index < plants.length; index += 1) {
    const plant = plants[index];
    const position = cachedCellPosition(plant);
    if (position.x < zombie.x && position.x > targetX) { target = plant; targetX = position.x; }
  }
  if (!target) return false;
  target.disabledTimer = Math.max(target.disabledTimer || 0, duration);
  const position = cachedCellPosition(target);
  addGameParticle(position.x, position.y - 24, "#c99be8", 14, .14);
  return true;
}
function gameLoop(now = 0) {
  if (!game.running || game.paused) return;
  const dt = Math.min(80, Math.max(8, now - game.last || 16));
  rebuildGameIndexes();
  game.last = now;
  game.elapsed += dt;
  updateGameEffects(dt);
  game.rallyTimer = Math.max(0, (game.rallyTimer || 0) - dt);
  game.timeStopTimer = Math.max(0, (game.timeStopTimer || 0) - dt);
  for (const type of Object.keys(GAME_SKILLS)) {
    if (game.skillCooldowns[type] > 0) game.skillCooldowns[type] = Math.max(0, game.skillCooldowns[type] - dt);
  }
  for (const type of PLANT_TYPES) {
    if (game.seedCooldowns[type] > 0) game.seedCooldowns[type] = Math.max(0, game.seedCooldowns[type] - dt);
  }
  updateGameHud(false);
  game.spawnTimer += dt;
  game.skyTimer += dt;
  game.dangerTimer += dt;
  const nearHouse = anyIndexedEntity("zombies", (zombie) => !zombie.defeated && zombie.x < 165);
  if (nearHouse) game.dangerPulse = Math.max(game.dangerPulse, 260);
  if (nearHouse && game.dangerTimer > 850) {
    game.dangerTimer = 0;
    playGameSound("danger");
  } else if (!nearHouse) {
    game.dangerPulse = Math.max(0, game.dangerPulse - dt);
  }
  const spawnDelay = Math.max(780, (3300 - game.wave * 240) * gameDifficulty().spawnDelayMultiplier);
  if (game.waveSpawned < game.waveTarget && ((game.waveSpawned === 0 && game.spawnTimer > 1800) || game.spawnTimer > spawnDelay)) {
    spawnZombie();
    game.spawnTimer = 0;
  }
  if (game.skyTimer > 4800 && game.suns.length < 10) {
    game.skyTimer = 0;
    game.suns.push({ x: 105 + Math.random() * 535, y: 88 + Math.random() * 270, age: 0, targetY: 80 + Math.random() * 240 });
  }
  game.suns.forEach((sun) => { sun.age += dt; if (sun.y < sun.targetY) sun.y = Math.min(sun.targetY, sun.y + dt * .05); });
  collectAutomaticSuns();
  const plantsThisFrame = game._plantsFrame || (game._plantsFrame = []);
  plantsThisFrame.length = 0;
  game.plants.forEach((plant) => {
    plantsThisFrame.push(plant);
    if (plant.underPlant) plantsThisFrame.push(plant.underPlant);
  });
  plantsThisFrame.forEach((plant) => {
    if (!plantContainer(plant)) return;
    plant.sunlightBoost = plantHasSunlight(plant);
    plant.age += dt;
    plant.disabledTimer = Math.max(0, (plant.disabledTimer || 0) - dt);
    if (plant.disabledTimer > 0) return;
    if (plant.type === "sunflower") {
      plant.sunTimer += dt;
      if (plant.sunTimer > 4800 && game.suns.length < 12) { plant.sunTimer = 0; produceSun(plant); }
      return;
    }
    if (plant.type === "cherrybomb") {
      plant.bombTimer += dt;
      if (plant.bombTimer > 950) explodeCherryBomb(plant);
      return;
    }
    if (plant.type === "jalapeno") {
      plant.bombTimer += dt;
      if (plant.bombTimer > 850) {
        const position = cachedCellPosition(plant);
        forEachRowEntity("zombies", plant.row, (zombie) => defeatZombie(zombie));
        removeGamePlant(plant);
        addGameParticle(position.x + 180, position.y, "#ff784e", 40, .35);
        playGameSound("explode");
        updateGameHud();
      }
      return;
    }
    if (plant.type === "potatomine") {
      plant.bombTimer += dt;
      if (!plant.armed && plant.bombTimer >= 1800) {
        plant.armed = true;
        addGameParticle(cellPosition(plant.row, plant.col).x, cellPosition(plant.row, plant.col).y - 18, "#e7c875", 8, .08);
      }
      const target = plant.armed && game.zombies.find((zombie) => zombie.row === plant.row && zombie.x < cellPosition(plant.row, plant.col).x + 30);
      if (target) {
        game.zombies.filter((zombie) => zombie.row === plant.row && Math.abs(zombie.x - target.x) < 90).forEach((zombie) => defeatZombie(zombie));
        removeGamePlant(plant);
        addGameParticle(cellPosition(plant.row, plant.col).x, cellPosition(plant.row, plant.col).y, "#e7c875", 26, .25);
        playGameSound("explode");
        updateGameHud();
      }
      return;
    }
    if (plant.type === "spikeweed") {
      plant.shotTimer += dt;
      const position = cellPosition(plant.row, plant.col);
      const target = game.zombies.find((zombie) => zombie.row === plant.row && Math.abs(zombie.x - position.x) < 44);
      if (target) { target.hp -= dt / 720; if (target.hp <= 0) { defeatZombie(target); updateGameHud(); } }
    }
    if (plant.type === "gloomshroom") {
      plant.shotTimer += dt;
      const position = cellPosition(plant.row, plant.col);
      if (plant.shotTimer > 1050) { plant.shotTimer = 0; const targets = game.zombies.filter((zombie) => Math.abs(zombie.row - plant.row) <= 1 && Math.hypot(zombie.x - position.x, (zombie.row - plant.row) * gameLayout.cellH) < 140); targets.forEach((target) => { target.hp -= 1; addGameParticle(target.x, target.y - 12, "#c79be8", 4, .1); if (target.hp <= 0) defeatZombie(target); }); if (targets.length) playGameSound("shoot"); }
      return;
    }
    if (plant.type === "pumpkin") return;
    if (plant.type === "squash") {
      plant.bombTimer += dt;
      const position = cellPosition(plant.row, plant.col);
      const target = game.zombies.find((zombie) => zombie.row === plant.row && zombie.x > position.x - 82 && zombie.x < position.x + 130);
      if (plant.bombTimer > 450 && target) { defeatZombie(target); removeGamePlant(plant); addGameParticle(target.x, target.y, "#f0b653", 28, .28); playGameSound("explode"); updateGameHud(); }
      return;
    }
    const profile = plantProfiles[plant.type];
    if (!profile) return;
    plant.shotTimer += dt;
    const position = cellPosition(plant.row, plant.col);
    const rowThreat = profile.rows
      ? anyRowEntity("zombies", plant.row, (zombie) => zombie.x > position.x)
        || (plant.row > 0 && anyRowEntity("zombies", plant.row - 1, (zombie) => zombie.x > position.x))
        || (plant.row + 1 < gameLayout.rows && anyRowEntity("zombies", plant.row + 1, (zombie) => zombie.x > position.x))
      : anyRowEntity("zombies", plant.row, (zombie) => zombie.x > position.x);
    const fireInterval = plantFireInterval(plant, profile);
    if (plant.shotTimer > fireInterval && rowThreat) {
      plant.shotTimer = 0;
      if (profile.utility) {
        const armored = firstRowEntity("zombies", plant.row, (zombie) => zombie.x > position.x && zombie.armor > 0);
        if (armored) {
          armored.armor = 0;
          armored.hp = Math.max(1, armored.hp - 2);
          addGameParticle(armored.x, armored.y - 20, "#dcb7ff", 15, .15);
          playGameSound("hit");
        }
      } else firePlantShots(plant, profile);
    }
  });
  game.flagRows.fill(0);
  game.zombies.forEach((zombie) => { if (zombie.type === "flag") game.flagRows[zombie.row] = 1; });
  const zombiesThisFrame = game._zombiesFrame || (game._zombiesFrame = []);
  zombiesThisFrame.length = 0;
  zombiesThisFrame.push(...game.zombies);
  zombiesThisFrame.forEach((zombie) => {
    zombie.y = cellPosition(zombie.row, 0).y;
    zombie.age = (zombie.age || 0) + dt;
    zombie.slowTimer = Math.max(0, zombie.slowTimer - dt);
    zombie.flashTimer = Math.max(0, (zombie.flashTimer || 0) - dt);
    if (zombie.burrowTimer > 0) zombie.burrowTimer -= dt;
    const burrowed = zombie.type === "miner" && zombie.burrowTimer > 0;
    zombie.garlicTimer = Math.max(0, (zombie.garlicTimer || 0) - dt);
    zombie.dashTimer = Math.max(0, (zombie.dashTimer || 0) - dt);
    zombie.leapTimer = Math.max(0, (zombie.leapTimer || 0) - dt);
    zombie.chargeTimer = Math.max(0, (zombie.chargeTimer || 0) - dt);
    zombie.curseTimer = Math.max(0, (zombie.curseTimer || 0) - dt);
    zombie.breathTimer = Math.max(0, (zombie.breathTimer || 0) - dt);
    zombie.smashTimer = Math.max(0, (zombie.smashTimer || 0) - dt);
    zombie.armorTimer = Math.max(0, (zombie.armorTimer || 0) - dt);
    zombie.guardTimer = Math.max(0, (zombie.guardTimer || 0) - dt);
    zombie.stormTimer = Math.max(0, (zombie.stormTimer || 0) - dt);
    zombie.markTimer = Math.max(0, (zombie.markTimer || 0) - dt);
    zombie.staggerTimer = Math.max(0, (zombie.staggerTimer || 0) - dt);
    zombie.burnTimer = Math.max(0, (zombie.burnTimer || 0) - dt);
    zombie.burnTickTimer = Math.max(0, (zombie.burnTickTimer || 0) - dt);
    if (game.timeStopTimer > 0) return;
    if (zombie.burnTimer > 0 && zombie.burnTickTimer <= 0) {
      zombie.burnTickTimer = 500;
      zombie.hp -= Math.max(1, zombie.burnDamage || 1);
      addGameParticle(zombie.x, zombie.y - 18, "#ff815f", 4, .08);
      if (zombie.hp <= 0) { defeatZombie(zombie); updateGameHud(); return; }
    }
    if (["runner", "imp", "scout"].includes(zombie.type) && zombie.dashTimer <= 0 && zombie.x < 650) {
      zombie.dashTimer = zombie.type === "imp" ? 2100 : 3000;
      zombie.x += zombie.type === "imp" ? 38 : 28;
      zombie.flashTimer = 140;
      addGameParticle(zombie.x, zombie.y - 22, zombie.type === "scout" ? "#f5cf63" : "#e57b70", 8, .14);
    }
    if (zombie.type === "football" && zombie.chargeTimer <= 0) {
      zombie.chargeTimer = 3000;
      zombie.flashTimer = 160;
      addGameParticle(zombie.x, zombie.y - 20, "#d56c58", 8, .13);
    }
    if (zombie.type === "witch" && zombie.curseTimer <= 0) {
      zombie.curseTimer = 4300;
      curseNearestPlant(zombie, zombie.elite ? 4200 : 3000);
    }
    if (zombie.type === "dragon" && zombie.breathTimer <= 0) {
      zombie.breathTimer = 3600;
      game.plants.filter((plant) => plant.row === zombie.row && cellPosition(plant.row, plant.col).x < zombie.x + 20).forEach((plant) => damagePlant(plant, zombie.elite ? 3 : 2, "#ff815f"));
      addGameParticle(zombie.x - 34, zombie.y - 12, "#ff9b5f", 18, .22);
    }
    if (zombie.type === "shield" && zombie.armorTimer <= 0) {
      zombie.armorTimer = 4200;
      zombie.armor = Math.min(zombieProfiles.shield.armor, zombie.armor + (zombie.elite ? 5 : 3));
      addGameParticle(zombie.x, zombie.y - 24, "#9bdcf5", 12, .14);
    }
    if (zombie.type === "storm" && zombie.stormTimer <= 0) {
      zombie.stormTimer = 4000;
      game.plants.filter((plant) => plant.row === zombie.row).forEach((plant) => { plant.disabledTimer = Math.max(plant.disabledTimer || 0, 1200); });
      addGameParticle(zombie.x - 24, zombie.y - 28, "#a9c8e8", 20, .2);
    }
    if (zombie.type === "scout" && zombie.markTimer <= 0) {
      zombie.markTimer = 3500;
      curseNearestPlant(zombie, 1400);
    }
    if (zombie.type === "dancer") { zombie.summonTimer += dt; if (zombie.summonTimer > 4200) { zombie.summonTimer = 0; const allyRow = (zombie.row + 1) % gameLayout.rows; const ally = zombieProfiles.backup; game.zombies.push({ x: zombie.x + 34, y: cellPosition(allyRow, 0).y, row: allyRow, hp: ally.hp, maxHp: ally.hp, armor: 0, type: "backup", speed: ally.speed, attackInterval: ally.attackInterval, slowTimer: 0, burrowTimer: 0, seed: Math.random() * 1000, garlicTimer: 0, vaultTimer: 0, summonTimer: 0, flashTimer: 0, attackTimer: 0, attacking: false, staggerTimer: 0 }); addGameParticle(zombie.x, zombie.y - 28, "#ef7892", 16, .18); playGameSound("wave"); } }
    const blocker = burrowed ? null : game.plants.find((plant) => plant.type !== "spikeweed" && plant.row === zombie.row && Math.abs(cellPosition(plant.row, plant.col).x - zombie.x) < 30);
    if (blocker) {
      zombie.attacking = true;
      zombie.attackTimer = (zombie.attackTimer || 0) + dt;
      const attackCycle = Math.max(240, zombie.attackInterval || 900);
      if (zombie.attackTimer >= attackCycle) {
        zombie.attackTimer -= attackCycle;
        zombie.attackFlashTimer = 180;
        zombie.flashTimer = Math.max(zombie.flashTimer || 0, 90);
      }
    } else {
      zombie.attacking = false;
      zombie.attackTimer = 0;
    }
    zombie.attackFlashTimer = Math.max(0, (zombie.attackFlashTimer || 0) - dt);
    if (zombie.type === "imp" && blocker && zombie.leapTimer <= 0) { zombie.x = cellPosition(blocker.row, blocker.col).x - 44; zombie.leapTimer = 1800; addGameParticle(zombie.x, zombie.y - 25, "#e57b70", 12, .16); return; }
    if (blocker?.type === "spikeweed") { zombie.hp -= dt / 720; if (zombie.hp <= 0) { defeatZombie(zombie); updateGameHud(); return; } }
    if (zombie.type === "polevault" && blocker && !zombie.vaultTimer) { zombie.x = cellPosition(blocker.row, blocker.col).x - 44; zombie.vaultTimer = 1; addGameParticle(zombie.x, zombie.y - 25, "#d5a15e", 12, .16); return; }
    if (blocker?.type === "garlic" && zombie.garlicTimer <= 0) { zombie.row = (zombie.row + 1) % gameLayout.rows; zombie.x += 22; zombie.garlicTimer = 3200; addGameParticle(zombie.x, zombie.y, "#f3e1b4", 14, .16); playGameSound("hit"); return; }
    if (zombie.type === "gargantuar" && blocker && zombie.smashTimer <= 0) {
      zombie.smashTimer = zombie.elite ? 2200 : 3000;
      damagePlant(blocker, zombie.elite ? 10 : 7, "#d99a5e");
      addGameParticle(zombie.x, zombie.y - 20, "#d99a5e", 18, .22);
      playGameSound("explode");
      return;
    }
    if (blocker) {
      if (damagePlant(blocker, dt / zombie.attackInterval)) playGameSound("hit");
    } else {
      const bannerBoost = game.flagRows[zombie.row] ? 1.18 : 1;
      const enragedBoost = zombie.type === "newspaper" && zombie.armor <= 0 ? 1.65 : 1;
      const dashBoost = ["runner", "imp", "scout"].includes(zombie.type) && zombie.dashTimer > 0 ? (zombie.type === "imp" ? 1.45 : 1.3) : 1;
      const chargeBoost = zombie.type === "football" && zombie.chargeTimer > 0 ? 1.85 : 1;
      const giantSlow = zombie.type === "gargantuar" ? .72 : 1;
      zombie.x -= zombie.speed * bannerBoost * enragedBoost * dashBoost * chargeBoost * giantSlow * dt * (zombie.slowTimer > 0 ? .48 : 1);
    }
  });
  // Mowers are a last-resort lane defense. Resolve them after zombie movement
  // but before projectiles and the house breach check.
  updateMowers(dt);
  game.shots.forEach((shot) => {
    shot.x += .34 * dt;
    const hit = game.zombies.find((zombie) => zombie.row === shot.row && zombie.x > shot.x - 12 && zombie.x < shot.x + 23 && !(zombie.type === "miner" && zombie.burrowTimer > 0) && !(shot.hitTargets || []).includes(zombie));
    if (!hit) return;
    shot.hitTargets = shot.hitTargets || [];
    shot.hitTargets.push(hit);
    shot.hitsLeft = Math.max(0, (shot.hitsLeft || 1) - 1);
    shot.hit = shot.hitsLeft <= 0;
    const rawDamage = shot.damage || 1;
    if (hit.armor > 0) {
      hit.armor = Math.max(0, hit.armor - rawDamage);
      hit.hp -= rawDamage * .35;
    } else hit.hp -= rawDamage;
    if (shot.fire && shot.burn) {
      hit.burnTimer = Math.max(hit.burnTimer || 0, shot.burn);
      hit.burnDamage = Math.max(hit.burnDamage || 0, shot.burnDamage || 1);
    }
    if (shot.slow) hit.slowTimer = Math.max(hit.slowTimer, shot.slow);
    if (shot.butter) hit.slowTimer = Math.max(hit.slowTimer, 3200);
    hit.flashTimer = 120;
    hit.staggerTimer = Math.max(hit.staggerTimer || 0, shot.fire ? 150 : 110);
    game.impacts.push({ x: shot.x, y: shot.y, radius: shot.butter ? 24 : shot.fire ? 20 : 16, color: shot.butter ? "#f4d37d" : shot.color || "#b7f3a0", life: 180, maxLife: 180 });
    addGameParticle(shot.x, shot.y, shot.color || "#b7f3a0", 5, .1);
    playGameSound("hit");
    if (hit.hp <= 0) {
      defeatZombie(hit);
      updateGameHud();
      addGameParticle(hit.x, hit.y, "#f6d681", 18, .2);
    }
  });
  game.shots = game.shots.filter((shot) => !shot.hit && shot.x < 735);
  let alive = 0;
  for (const particle of game.particles) {
    particle.x += particle.vx * dt;
    particle.y += particle.vy * dt;
    particle.vy += .00025 * dt;
    particle.life -= dt;
    if (particle.life > 0) game.particles[alive++] = particle;
  }
  game.particles.length = alive;
  alive = 0;
  for (const impact of game.impacts) {
    impact.life -= dt;
    if (impact.life > 0) game.impacts[alive++] = impact;
  }
  game.impacts.length = alive;
  if (game.zombies.some((zombie) => zombie.x < 61)) {
    addGameParticle(55, 180, "#ff9f83", 24, .22);
    finishGame("game.gameOver");
    return;
  }
  if (advanceWave(dt)) return;
  drawGame();
  if (game.running) game.frame = requestAnimationFrame(gameLoop);
}
function startGame() { cancelAnimationFrame(game.frame); initGame(); game.running = true; game.paused = false; game.last = performance.now(); setGameStatus("game.running"); $("#gameStart").textContent = t("game.restart"); startGameMusic(); game.frame = requestAnimationFrame(gameLoop); }
function canvasPoint(event) { const canvas = gameRender.canvas || $("#gameCanvas"), rect = canvas.getBoundingClientRect(); return { x: (event.clientX - rect.left) * GAME_LOGICAL_WIDTH / rect.width, y: (event.clientY - rect.top) * GAME_LOGICAL_HEIGHT / rect.height }; }
function updateGameHover(event) {
  if (!game.running) return;
  const point = canvasPoint(event);
  const next = gameCellAt(point.x, point.y);
  if (next?.row === game.hoverCell?.row && next?.col === game.hoverCell?.col) return;
  game.hoverCell = next;
  drawGame();
}
function clearGameHover() {
  if (!game.hoverCell) return;
  game.hoverCell = null;
  drawGame();
}
function collectSun(event) { const { x, y } = canvasPoint(event); const hit = game.suns.findIndex((sun) => Math.hypot(sun.x - x, sun.y - y) < 32); if (hit < 0) return false; const sun = game.suns[hit]; collectSunAt(hit, sun.x, sun.y); drawGame(); return true; }
function gameCellAt(x, y) { if (y < gameLayout.top || x < gameLayout.left) return null; const col = Math.floor((x - gameLayout.left) / gameLayout.cellW), row = Math.floor((y - gameLayout.top) / gameLayout.cellH); return col >= 0 && col < gameLayout.cols && row >= 0 && row < gameLayout.rows ? { row, col } : null; }
function plantAt(event) {
  if (!game.running) return false;
  const point = canvasPoint(event);
  const cell = gameCellAt(point.x, point.y);
  if (!cell) return false;
  const existing = game.plants.find((plant) => plant.row === cell.row && plant.col === cell.col);
  if (game.shovel) {
    if (!existing) return false;
    const position = cellPosition(existing.row, existing.col);
    removeGamePlant(existing);
    game.shovel = false;
    updateShovelButton();
    addGameParticle(position.x, position.y, "#e7d7a0", 12, .14);
    playGameSound("hit");
    drawGame();
    return true;
  }
  const type = game.selected;
  const covering = type === "pumpkin" && existing && existing.type !== "pumpkin";
  if (!type || (existing && !covering)) return false;
  const cost = plantCost[type];
  if (game.sun < cost) { setGameStatus("game.noSun"); return false; }
  if ((game.seedCooldowns[type] || 0) > 0) { setGameStatus("game.cooldown"); return false; }
  game.sun -= cost;
  game.seedCooldowns[type] = plantCooldown[type] || 0;
  const planted = { type, hp: plantHealth[type], row: cell.row, col: cell.col, seed: Math.random() * 1000, age: 0, sunTimer: 0, shotTimer: 0, bombTimer: 0, disabledTimer: 0, armed: type !== "potatomine" };
  if (covering) game.plants.splice(game.plants.indexOf(existing), 1, { ...planted, underPlant: existing });
  else game.plants.push(planted);
  const position = cellPosition(cell.row, cell.col);
  updateGameHud();
  clearPlantSelection();
  addGameParticle(position.x, position.y, plantColor[type] || "#fff", 12, .12);
  playGameSound("plant");
  drawGame();
  return true;
}
