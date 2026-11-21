// M8-T1288 — the second arcade game: Orbit Beacon (轨道信标).
//
// A standalone side-effect module imported by game.js, so esbuild folds it into
// the SAME game.js bundle. It never touches #gameModal or the `game` object of
// the lawn defence — its own modal is injected on first open. Existing arcade
// entry points (?arcade=1 and #arcadeButton) still go straight to the tower
// defence, so the three existing game smoke suites are unaffected.
//
// Gameplay: an energy core sits at the centre. Rotate a launcher around its
// orbit and fire radial bolts at debris drifting in from every direction.
// Protect the core, chain hits for a combo, grab the occasional repair mote.
// Waves escalate without bound — the world keeps coming.

const O = {
  modal: null, canvas: null, ctx: null, raf: 0,
  running: false, paused: false, started: false, ended: false,
  angle: -Math.PI / 2, keys: new Set(), pointerAngle: null,
  shield: 100, score: 0, combo: 0, bestCombo: 0,
  wave: 1, spawned: 0, waveTarget: 8, interWave: 0,
  debris: [], bolts: [], particles: [], motes: [],
  spawnTimer: 0, cooldown: 0, last: 0, elapsed: 0,
  best: (() => { const n = Number(localStorage.getItem("minicc-orbit-best")); return Number.isFinite(n) && n > 0 ? n : 0; })(),
  difficulty: (() => { const d = localStorage.getItem("minicc-orbit-difficulty"); return ["normal", "hard", "nightmare"].includes(d) ? d : "hard"; })(),
  stars: [], hudAt: 0,
};
const OC = { W: 480, H: 480, CX: 240, CY: 240, CORE: 26, ORBIT: 168, EDGE: 262, BOLT_SPEED: 360, ROT_SPEED: 2.5 };
const O_DIFF = {
  normal: { speed: .82, damage: 12, spawn: 1.18 },
  hard: { speed: 1, damage: 18, spawn: 1 },
  nightmare: { speed: 1.34, damage: 26, spawn: .72 },
};

function oEsc(value) { return window.escapeHtml ? window.escapeHtml(String(value)) : String(value); }
function oT(key) { return window.t ? window.t(key) : key; }
function oIcon(name) { return window.icon ? window.icon(name) : ""; }
function oRefresh(root) { return window.refreshIcons?.(root); }

// Dynamic DOM is injected after the page's one-shot i18n pass, so translate it
// here from the same window.t() the lawn game uses — no private applyLocale.
function oApplyDomI18n(root) {
  if (!root || !window.t) return;
  root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = window.t(el.dataset.i18n); });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = window.t(el.dataset.i18nPlaceholder); });
  root.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = window.t(el.dataset.i18nTitle); });
  root.querySelectorAll("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", window.t(el.dataset.i18nAria)); });
}

let OPicker = null;
function openArcadePicker() {
  if (!OPicker) {
    const host = document.createElement("div");
    host.innerHTML = `
    <div class="picker-modal" id="arcadePicker" aria-hidden="true">
      <div class="picker-card" role="dialog" aria-modal="true" aria-labelledby="pickerTitle">
        <div class="orbit-actions"><button class="orbit-close icon-button" id="pickerClose" type="button" aria-label="Close">${oIcon("x")}</button></div>
        <div class="orbit-kicker" data-i18n="picker.kicker">MINICC ARCADE · 选择战场</div>
        <h2 id="pickerTitle" data-i18n="picker.title">两片战场，随便挑</h2>
        <p class="picker-sub" data-i18n="picker.sub">同一个街机，两种玩法。你的最佳分数都只存在本机。</p>
        <div class="picker-grid">
          <button class="picker-option" id="pickerLawn" type="button">
            <span class="picker-glyph">🌱</span>
            <strong data-i18n="picker.lawn">草坪保卫战</strong>
            <small data-i18n="picker.lawnSub">种植物、布纵深，守住十波僵尸进屋。</small>
          </button>
          <button class="picker-option" id="pickerOrbit" type="button">
            <span class="picker-glyph">◎</span>
            <strong data-i18n="picker.orbit">轨道信标</strong>
            <small data-i18n="picker.orbitSub">旋转炮口、拦截碎片，波次无上限。</small>
          </button>
        </div>
      </div>
    </div>`;
    OPicker = host.firstElementChild;
    document.body.append(OPicker);
    OPicker.querySelector("#pickerClose").addEventListener("click", closeArcadePicker);
    OPicker.querySelector("#pickerLawn").addEventListener("click", () => { closeArcadePicker(); window.closeGame?.(); window.openGame?.(); });
    OPicker.querySelector("#pickerOrbit").addEventListener("click", () => { closeArcadePicker(); window.closeGame?.(); openOrbit(); });
    OPicker.addEventListener("click", (e) => { if (e.target === OPicker) closeArcadePicker(); });
    oRefresh(OPicker);
  }
  oApplyDomI18n(OPicker);
  OPicker.classList.add("show");
  OPicker.setAttribute("aria-hidden", "false");
}
function closeArcadePicker() {
  if (!OPicker) return;
  OPicker.classList.remove("show");
  OPicker.setAttribute("aria-hidden", "true");
}

function orbitModalMarkup() {
  return `
  <div class="orbit-modal" id="orbitModal" aria-hidden="true">
    <div class="orbit-card" role="dialog" aria-modal="true" aria-labelledby="orbitTitle">
      <div class="orbit-actions">
        <button class="orbit-tool" id="orbitBack" type="button" data-i18n-title="orbit.back" title="Back to arcade">${oIcon("arrow-left")}<span data-i18n="orbit.back">返回街机</span></button>
        <button class="orbit-tool" id="orbitHowBtn" type="button" data-i18n-title="orbit.how" title="How to play">${oIcon("book-open")}<span data-i18n="orbit.how">教程</span></button>
        <button class="orbit-close icon-button" id="orbitClose" type="button" aria-label="Close" data-i18n-aria="orbit.close">${oIcon("x")}</button>
      </div>
      <div class="orbit-kicker" data-i18n="orbit.kicker">MINICC ARCADE · INFINITE ORBIT</div>
      <h2 id="orbitTitle" data-i18n="orbit.title">轨道信标 · 无尽环绕</h2>
      <p class="orbit-subtitle" data-i18n="orbit.subtitle">旋转发射台，拦下四面逼近的碎片，守住中央能源核。波次无上限，直到护盾耗尽。</p>
      <div class="orbit-hud">
        <span><span data-i18n="orbit.shield">护盾</span> <strong id="orbitShield">100</strong></span>
        <span><span data-i18n="orbit.score">得分</span> <strong id="orbitScore">0</strong></span>
        <span><span data-i18n="orbit.wave">波次</span> <strong id="orbitWave">1</strong></span>
        <span><span data-i18n="orbit.combo">连击</span> <strong id="orbitCombo">0</strong></span>
        <span><span data-i18n="orbit.best">最佳</span> <strong id="orbitBest">0</strong></span>
        <span class="orbit-status" id="orbitStatus" data-i18n="orbit.ready">准备就绪</span>
      </div>
      <div class="orbit-stage">
        <canvas id="orbitCanvas" width="480" height="480" aria-label="Orbit Beacon playfield" data-i18n-aria="orbit.canvas"></canvas>
        <div class="orbit-overlay" id="orbitOverlay" hidden>
          <div class="orbit-overlay-card">
            <strong id="orbitOverlayTitle">—</strong>
            <p id="orbitOverlayBody">—</p>
            <button class="send-button" id="orbitOverlayBtn" type="button" data-i18n="orbit.start">开始游戏</button>
          </div>
        </div>
      </div>
      <div class="orbit-controls">
        <span class="orbit-hint" data-i18n="orbit.hint">← → / A D 旋转 · 空格或点击画布发射 · P 暂停</span>
        <label class="orbit-difficulty"><span data-i18n="orbit.difficulty">难度</span><select id="orbitDifficulty" aria-label="Difficulty" data-i18n-aria="orbit.difficulty"><option value="normal" data-i18n="orbit.normal">标准</option><option value="hard" data-i18n="orbit.hard" selected>高压</option><option value="nightmare" data-i18n="orbit.nightmare">噩梦</option></select></label>
        <button class="orbit-tool" id="orbitPause" type="button" aria-pressed="false" data-i18n="orbit.pause">暂停</button>
      </div>
    </div>
    <div class="orbit-how" id="orbitHowPanel" aria-hidden="true">
      <div class="orbit-how-card" role="dialog" aria-modal="true">
        <div class="orbit-how-head"><strong data-i18n="orbit.howTitle">六步学会轨道信标</strong><button class="orbit-close icon-button" id="orbitHowClose" type="button" aria-label="Close">${oIcon("x")}</button></div>
        <p class="orbit-how-sub" data-i18n="orbit.howSub">每一步都按真实规则写，照着做一遍就能上手。</p>
        <ol class="orbit-how-list">
          <li><strong data-i18n="orbit.how1t">先转再打</strong><span data-i18n="orbit.how1">发射台绕核心公转。用 ← → 或 A D 转到碎片飞来的方向，空格发射。也可以直接点击画布——炮口会转向点击处并立即开火。</span></li>
          <li><strong data-i18n="orbit.how2t">守住核心</strong><span data-i18n="orbit.how2">碎片撞上中央能源核会扣护盾（标准 12、高压 18、噩梦 26）。护盾归零就是终局——拦截比追分更重要。</span></li>
          <li><strong data-i18n="orbit.how3t">连击是复利</strong><span data-i18n="orbit.how3">连续命中不漏会累积连击，倍率直接乘得分。漏掉一颗碎片不会扣连击，但让它撞上核心会——别贴着核心打。</span></li>
          <li><strong data-i18n="orbit.how4t">认色分级</strong><span data-i18n="orbit.how4">青色碎片是普通货，橙色更快，紫色最硬（要两发）。越到后面越多——先看颜色再决定转向，别慌。</span></li>
          <li><strong data-i18n="orbit.how5t">捡修复光点</strong><span data-i18n="orbit.how5">击碎碎片偶尔掉落绿光点，飞向核心时点击它即可 +20 护盾。血量吃紧时，优先捡光点而不是追高分碎片。</span></li>
          <li><strong data-i18n="orbit.how6t">波次没有尽头</strong><span data-i18n="orbit.how6">清空一波立刻进入下一波，速度与数量都上涨——没有通关，只有你这一局撑到第几波。最佳分数只存在本机。</span></li>
        </ol>
        <button class="send-button orbit-how-ready" id="orbitHowReady" type="button" data-i18n="orbit.howReady">我准备好了</button>
      </div>
    </div>
  </div>`;
}

function orbitEnsureDom() {
  if (O.modal) return;
  const host = document.createElement("div");
  host.innerHTML = orbitModalMarkup().trim();
  O.modal = host.firstElementChild;
  document.body.append(O.modal);
  O.canvas = O.modal.querySelector("#orbitCanvas");
  O.ctx = O.canvas.getContext("2d");
  O.stars = Array.from({ length: 90 }, (_, i) => ({
    x: ((i * 73 + 19) % 480), y: ((i * 137 + 47) % 480),
    r: (i % 7 === 0) ? 1.6 : .8, a: .18 + (i % 5) * .1,
  }));
  O.modal.querySelector("#orbitDifficulty").value = O.difficulty;
  orbitBind();
  oApplyDomI18n(O.modal);
  oRefresh(O.modal);
  orbitPaintHud();
  orbitDrawIdle();
}

function orbitBind() {
  const q = (id) => O.modal.querySelector(`#${id}`);
  q("orbitClose").addEventListener("click", closeOrbit);
  q("orbitBack").addEventListener("click", () => { closeOrbit(); window.openGame?.(); });
  q("orbitHowBtn").addEventListener("click", openOrbitHow);
  q("orbitHowClose").addEventListener("click", closeOrbitHow);
  q("orbitHowReady").addEventListener("click", closeOrbitHow);
  q("orbitPause").addEventListener("click", toggleOrbitPause);
  q("orbitOverlayBtn").addEventListener("click", startOrbit);
  q("orbitDifficulty").addEventListener("change", (e) => {
    O.difficulty = ["normal", "hard", "nightmare"].includes(e.target.value) ? e.target.value : "hard";
    localStorage.setItem("minicc-orbit-difficulty", O.difficulty);
  });
  O.canvas.addEventListener("click", (event) => {
    const rect = O.canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) * (OC.W / rect.width);
    const y = (event.clientY - rect.top) * (OC.H / rect.height);
    O.pointerAngle = Math.atan2(y - OC.CY, x - OC.CX);
    fireOrbitBolt();
  });
  window.addEventListener("keydown", orbitKeyDown);
  window.addEventListener("keyup", orbitKeyUp);
}

function orbitKeyDown(event) {
  if (!O.modal?.classList.contains("show")) return;
  if (event.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
  const k = event.key.toLowerCase();
  if (["arrowleft", "arrowright", "a", "d", " "].includes(k)) event.preventDefault();
  O.keys.add(k);
  if (k === " " && !event.repeat) fireOrbitBolt();
  if (k === "p" && !event.repeat) toggleOrbitPause();
  if (k === "escape") { closeOrbitHow(); closeOrbit(); }
}
function orbitKeyUp(event) { O.keys.delete(event.key.toLowerCase()); }

function orbitSetStatus(text) {
  const el = O.modal?.querySelector("#orbitStatus");
  if (el) el.textContent = text;
}
function orbitPaintHud() {
  if (!O.modal) return;
  const set = (id, v) => { const el = O.modal.querySelector(`#${id}`); if (el) el.textContent = String(v); };
  set("orbitShield", Math.max(0, Math.round(O.shield)));
  set("orbitScore", O.score);
  set("orbitWave", O.wave);
  set("orbitCombo", O.combo);
  set("orbitBest", O.best);
}
function orbitShowOverlay(title, body, button, onStart = true) {
  const ov = O.modal.querySelector("#orbitOverlay");
  O.modal.querySelector("#orbitOverlayTitle").textContent = title;
  O.modal.querySelector("#orbitOverlayBody").textContent = body;
  const btn = O.modal.querySelector("#orbitOverlayBtn");
  btn.textContent = button;
  btn.dataset.action = onStart ? "start" : "again";
  ov.hidden = false;
}
function orbitHideOverlay() { O.modal.querySelector("#orbitOverlay").hidden = true; }

function openOrbit() {
  orbitEnsureDom();
  oApplyDomI18n(O.modal);
  O.modal.classList.add("show");
  O.modal.setAttribute("aria-hidden", "false");
  if (!O.started) {
    orbitReset();
    orbitShowOverlay(oT("orbit.title"), oT("orbit.welcome"), oT("orbit.start"));
    orbitSetStatus(oT("orbit.ready"));
  }
}
function closeOrbit() {
  if (!O.modal) return;
  cancelAnimationFrame(O.raf);
  O.running = false;
  O.modal.classList.remove("show");
  O.modal.setAttribute("aria-hidden", "true");
  O.keys.clear();
}
function openOrbitHow() { orbitEnsureDom(); O.modal.querySelector("#orbitHowPanel").classList.add("show"); O.modal.querySelector("#orbitHowPanel").setAttribute("aria-hidden", "false"); }
function closeOrbitHow() { if (!O.modal) return; O.modal.querySelector("#orbitHowPanel").classList.remove("show"); O.modal.querySelector("#orbitHowPanel").setAttribute("aria-hidden", "true"); }

function orbitReset() {
  cancelAnimationFrame(O.raf);
  O.running = false; O.paused = false; O.ended = false; O.started = false;
  O.shield = 100; O.score = 0; O.combo = 0; O.bestCombo = 0;
  O.wave = 1; O.spawned = 0; O.waveTarget = 8; O.interWave = 0;
  O.debris = []; O.bolts = []; O.particles = []; O.motes = [];
  O.spawnTimer = 0; O.cooldown = 0; O.elapsed = 0; O.angle = -Math.PI / 2;
  O.modal.querySelector("#orbitPause").setAttribute("aria-pressed", "false");
  orbitPaintHud();
  orbitDrawIdle();
}

function startOrbit() {
  if (!O.modal) return;
  if (O.ended || !O.started) {
    if (O.ended) orbitReset();
    O.started = true; O.ended = false;
  }
  orbitHideOverlay();
  O.running = true; O.paused = false; O.last = 0;
  orbitSetStatus(oT("orbit.running"));
  cancelAnimationFrame(O.raf);
  O.raf = requestAnimationFrame(orbitLoop);
}

function toggleOrbitPause() {
  if (!O.started || O.ended) return;
  O.paused = !O.paused;
  O.modal.querySelector("#orbitPause").setAttribute("aria-pressed", String(O.paused));
  orbitSetStatus(O.paused ? oT("orbit.paused") : oT("orbit.running"));
}

function orbitSpawnDebris(kindOverride) {
  const a = Math.random() * Math.PI * 2;
  const roll = Math.random();
  const kind = kindOverride || (roll > .9 ? "tough" : roll > .68 ? "fast" : "normal");
  const spec = { normal: { hp: 1, speed: 34, r: 11, color: "#5eead4" },
                 fast: { hp: 1, speed: 62, r: 9, color: "#fbbf24" },
                 tough: { hp: 2, speed: 26, r: 14, color: "#c084fc" } }[kind];
  const d = O_DIFF[O.difficulty];
  O.debris.push({
    x: OC.CX + Math.cos(a) * OC.EDGE, y: OC.CY + Math.sin(a) * OC.EDGE,
    a, hp: spec.hp, maxHp: spec.hp, r: spec.r, color: spec.color,
    speed: spec.speed * d.speed * (1 + (O.wave - 1) * .12), spin: Math.random() * Math.PI,
  });
  O.spawned += 1;
}

function fireOrbitBolt() {
  if (!O.running || O.paused || O.ended || O.cooldown > 0) return false;
  O.cooldown = 155;
  const a = O.pointerAngle != null ? O.pointerAngle : O.angle;
  O.bolts.push({
    x: OC.CX + Math.cos(a) * (OC.ORBIT + 10), y: OC.CY + Math.sin(a) * (OC.ORBIT + 10),
    vx: Math.cos(a) * OC.BOLT_SPEED, vy: Math.sin(a) * OC.BOLT_SPEED, life: 1.35,
  });
  O.pointerAngle = null;
  return true;
}

function orbitBurst(x, y, color, n = 10) {
  for (let i = 0; i < n; i += 1) {
    const a = Math.random() * Math.PI * 2, s = 40 + Math.random() * 130;
    O.particles.push({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: .45 + Math.random() * .4, color });
  }
}

function orbitDamageDebris(debris) {
  debris.hp -= 1;
  orbitBurst(debris.x, debris.y, debris.color, 5);
  if (debris.hp > 0) return;
  O.combo += 1;
  O.bestCombo = Math.max(O.bestCombo, O.combo);
  O.score += 10 * Math.min(5, 1 + Math.floor(O.combo / 4));
  orbitBurst(debris.x, debris.y, debris.color, 14);
  if (Math.random() < .16) {
    O.motes.push({ x: debris.x, y: debris.y, life: 5.5, spin: 0 });
  }
  const idx = O.debris.indexOf(debris);
  if (idx >= 0) O.debris.splice(idx, 1);
}

function orbitEnd() {
  O.running = false; O.ended = true; O.started = true;
  cancelAnimationFrame(O.raf);
  O.keys.clear();
  if (O.score > O.best) { O.best = O.score; localStorage.setItem("minicc-orbit-best", String(O.best)); }
  orbitPaintHud();
  orbitSetStatus(oT("orbit.gameOver"));
  orbitShowOverlay(oT("orbit.gameOver"), `${oT("orbit.score")} ${O.score} · ${oT("orbit.wave")} ${O.wave} · ${oT("orbit.combo")} ${O.bestCombo}`, oT("orbit.again"));
  O.modal.querySelector("#orbitOverlayBtn").onclick = () => { orbitReset(); startOrbit(); };
}

function orbitLoop(ts) {
  if (!O.running) return;
  if (!O.paused) {
    const dt = O.last ? Math.min(.05, (ts - O.last) / 1000) : 0;
    O.last = ts;
    O.elapsed += dt;
    O.cooldown = Math.max(0, O.cooldown - dt * 1000);

    if (O.keys.has("arrowleft") || O.keys.has("a")) O.angle -= OC.ROT_SPEED * dt;
    if (O.keys.has("arrowright") || O.keys.has("d")) O.angle += OC.ROT_SPEED * dt;

    const d = O_DIFF[O.difficulty];
    O.spawnTimer += dt;
    if (O.spawned < O.waveTarget && O.spawnTimer >= d.spawn * .85) {
      O.spawnTimer = 0; orbitSpawnDebris();
    }
    if (O.spawned >= O.waveTarget && O.debris.length === 0 && O.motes.length === 0) {
      if (O.interWave <= 0) { O.interWave = 1.6; orbitSetStatus(oT("orbit.waveClear")); }
    }
    if (O.interWave > 0) {
      O.interWave -= dt;
      if (O.interWave <= 0) {
        O.wave += 1; O.spawned = 0; O.waveTarget = 8 + O.wave * 3;
        orbitSetStatus(`${oT("orbit.wave")} ${O.wave}`);
      }
    }

    for (const b of O.bolts) { b.x += b.vx * dt; b.y += b.vy * dt; b.life -= dt; }
    O.bolts = O.bolts.filter((b) => b.life > 0 && b.x > -20 && b.x < OC.W + 20 && b.y > -20 && b.y < OC.H + 20);

    for (const deb of O.debris) {
      deb.x += Math.cos(deb.a) * deb.speed * dt;
      deb.y += Math.sin(deb.a) * deb.speed * dt;
      deb.spin += dt * 2;
    }
    for (const bolt of [...O.bolts]) {
      for (const deb of [...O.debris]) {
        const dx = bolt.x - deb.x, dy = bolt.y - deb.y;
        if (dx * dx + dy * dy < (deb.r + 5) ** 2) {
          const bi = O.bolts.indexOf(bolt); if (bi >= 0) O.bolts.splice(bi, 1);
          orbitDamageDebris(deb); break;
        }
      }
    }
    for (const deb of [...O.debris]) {
      const dx = deb.x - OC.CX, dy = deb.y - OC.CY;
      if (dx * dx + dy * dy < (OC.CORE + deb.r) ** 2) {
        O.shield -= d.damage; O.combo = 0;
        orbitBurst(deb.x, deb.y, "#fb7185", 16);
        const idx = O.debris.indexOf(deb); if (idx >= 0) O.debris.splice(idx, 1);
        if (O.shield <= 0) { orbitEnd(); return; }
      } else if (dx * dx + dy * dy > (OC.EDGE + 60) ** 2) {
        const idx = O.debris.indexOf(deb); if (idx >= 0) O.debris.splice(idx, 1);
      }
    }
    for (const m of [...O.motes]) {
      m.life -= dt; m.spin += dt * 3;
      const dx = m.x - OC.CX, dy = m.y - OC.CY;
      const dist = Math.hypot(dx, dy);
      if (dist > 1) { m.x -= (dx / dist) * 46 * dt; m.y -= (dy / dist) * 46 * dt; }
      if (dist < OC.CORE + 12 || m.life <= 0) {
        if (dist < OC.CORE + 12) { O.shield = Math.min(100, O.shield + 20); orbitBurst(m.x, m.y, "#86efac", 10); }
        const idx = O.motes.indexOf(m); if (idx >= 0) O.motes.splice(idx, 1);
      }
    }
    for (const p of O.particles) { p.x += p.vx * dt; p.y += p.vy * dt; p.life -= dt; }
    O.particles = O.particles.filter((p) => p.life > 0);
  }
  orbitDraw();
  if (ts - O.hudAt > 90) { orbitPaintHud(); O.hudAt = ts; }
  O.raf = requestAnimationFrame(orbitLoop);
}

function orbitDrawIdle() {
  if (!O.ctx) return;
  const ctx = O.ctx;
  const g = ctx.createRadialGradient(OC.CX, OC.CY, 20, OC.CX, OC.CY, 300);
  g.addColorStop(0, "#16243a"); g.addColorStop(1, "#080e1a");
  ctx.fillStyle = g; ctx.fillRect(0, 0, OC.W, OC.H);
  for (const s of O.stars) { ctx.globalAlpha = s.a; ctx.fillStyle = "#cbd5e1"; ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fill(); }
  ctx.globalAlpha = 1;
  orbitDrawCore(ctx, 0);
  orbitDrawLauncher(ctx);
}

function orbitDrawCore(ctx, pulse) {
  ctx.save();
  ctx.strokeStyle = "rgba(94,234,212,.28)"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(OC.CX, OC.CY, OC.ORBIT, 0, Math.PI * 2); ctx.stroke();
  const glow = 1 + Math.sin(pulse * 2) * .08;
  const gg = ctx.createRadialGradient(OC.CX, OC.CY, 2, OC.CX, OC.CY, OC.CORE * 2.1 * glow);
  gg.addColorStop(0, "rgba(94,234,212,.9)"); gg.addColorStop(.5, "rgba(52,211,153,.35)"); gg.addColorStop(1, "rgba(52,211,153,0)");
  ctx.fillStyle = gg; ctx.beginPath(); ctx.arc(OC.CX, OC.CY, OC.CORE * 2.1 * glow, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#0f2e2a"; ctx.strokeStyle = "#5eead4"; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.arc(OC.CX, OC.CY, OC.CORE, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.fillStyle = "#a7f3d0"; ctx.font = "700 12px Manrope, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(Math.max(0, Math.round(O.shield))), OC.CX, OC.CY);
  ctx.restore();
}
function orbitDrawLauncher(ctx) {
  const x = OC.CX + Math.cos(O.angle) * OC.ORBIT;
  const y = OC.CY + Math.sin(O.angle) * OC.ORBIT;
  ctx.save(); ctx.translate(x, y); ctx.rotate(O.angle);
  ctx.fillStyle = O.cooldown > 0 ? "#64748b" : "#fbbf24";
  ctx.beginPath(); ctx.moveTo(16, 0); ctx.lineTo(-8, 8); ctx.lineTo(-8, -8); ctx.closePath(); ctx.fill();
  ctx.fillStyle = "#fde68a"; ctx.beginPath(); ctx.arc(0, 0, 4, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}
function orbitDraw() {
  if (!O.ctx) return;
  const ctx = O.ctx, pulse = O.elapsed;
  const g = ctx.createRadialGradient(OC.CX, OC.CY, 20, OC.CX, OC.CY, 300);
  g.addColorStop(0, "#16243a"); g.addColorStop(1, "#080e1a");
  ctx.fillStyle = g; ctx.fillRect(0, 0, OC.W, OC.H);
  for (const s of O.stars) { ctx.globalAlpha = s.a; ctx.fillStyle = "#cbd5e1"; ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fill(); }
  ctx.globalAlpha = 1;
  for (const m of O.motes) {
    ctx.save(); ctx.globalAlpha = Math.min(1, m.life); ctx.fillStyle = "#86efac";
    ctx.shadowColor = "#86efac"; ctx.shadowBlur = 12;
    ctx.beginPath(); ctx.arc(m.x, m.y, 7, 0, Math.PI * 2); ctx.fill(); ctx.restore();
  }
  for (const deb of O.debris) {
    ctx.save(); ctx.translate(deb.x, deb.y); ctx.rotate(deb.spin);
    ctx.fillStyle = deb.color; ctx.shadowColor = deb.color; ctx.shadowBlur = 10;
    ctx.beginPath();
    for (let i = 0; i < 6; i += 1) {
      const a = (i / 6) * Math.PI * 2, r = deb.r;
      const px = Math.cos(a) * r, py = Math.sin(a) * r;
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    }
    ctx.closePath(); ctx.fill();
    if (deb.maxHp > 1) { ctx.shadowBlur = 0; ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5; ctx.stroke(); }
    ctx.restore();
  }
  for (const b of O.bolts) {
    ctx.strokeStyle = "#fde68a"; ctx.lineWidth = 3; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(b.x, b.y); ctx.lineTo(b.x - b.vx * .03, b.y - b.vy * .03); ctx.stroke();
  }
  for (const p of O.particles) {
    ctx.globalAlpha = Math.max(0, Math.min(1, p.life)); ctx.fillStyle = p.color;
    ctx.beginPath(); ctx.arc(p.x, p.y, 2.5, 0, Math.PI * 2); ctx.fill();
  }
  ctx.globalAlpha = 1;
  orbitDrawCore(ctx, pulse);
  orbitDrawLauncher(ctx);
}

Object.assign(window, {
  openOrbit, closeOrbit, startOrbit, toggleOrbitPause, openOrbitHow, closeOrbitHow,
  fireOrbitBolt, orbitSpawnDebris, orbitLoop, orbitReset, orbitDraw,
  openArcadePicker, closeArcadePicker,
});
window.__orbitProbe = {
  state: O, fire: fireOrbitBolt, spawn: orbitSpawnDebris, start: startOrbit,
  end: orbitEnd, open: openOrbit, close: closeOrbit,
};
