// M8-T1291 — the third arcade game: Prefix Vault (前缀密库).
//
// A side-effect module imported by game.js, folded into the same game.js
// bundle as the lawn defence and Orbit Beacon. It owns only #vaultModal and a
// small probe on window; it never touches the other two games' state.
//
// Gameplay teaches the real cache work this project does: keep a bounded set
// of stable prefixes hot, recognise when a new prefix deserves a slot, and pay
// for eviction. A "session affinity" surge makes one prefix hot for a while —
// exactly what a real batched conversation does to a prompt-cache prefix.
// Nothing here is decorative: hit rate, LRU eviction and token cost are the
// same ideas minicc/cache_keeper.py and minicc/llm/usage.py use.

const V = {
  modal: null, inited: false, timer: 0, last: 0,
  running: false, ended: false, started: false,
  slots: [], request: null, ttl: 2400, deadline: 0,
  score: 0, combo: 0, bestCombo: 0, hits: 0, misses: 0, lives: 5,
  wave: 1, served: 0, hot: "A", hotUntil: 0,
  best: (() => { const n = Number(localStorage.getItem("minicc-vault-best")); return Number.isFinite(n) && n > 0 ? n : 0; })(),
};
const VS = { SLOTS: 6, BASE_TTL: 2400, MIN_TTL: 950, WAVE_SIZE: 10, EVICT_COST: 12, CACHE_COST: 4 };
const VPREFIXES = ["A", "B", "C", "D", "E", "F"];

function vT(key) { return window.t ? window.t(key) : key; }
function vEsc(value) { return window.escapeHtml ? window.escapeHtml(String(value)) : String(value); }
function vIcon(name) { return window.icon ? window.icon(name) : ""; }
function vRefresh(root) { return window.refreshIcons?.(root); }

function vApplyDomI18n(root) {
  if (!root || !window.t) return;
  root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = window.t(el.dataset.i18n); });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = window.t(el.dataset.i18nPlaceholder); });
  root.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = window.t(el.dataset.i18nTitle); });
  root.querySelectorAll("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", window.t(el.dataset.i18nAria)); });
}

function vStatus() {
  const el = document.querySelector("#vaultStatus");
  if (el) el.textContent = vT(V.running ? "vault.running" : V.ended ? "vault.gameOver" : "vault.ready");
}

function vaultModalMarkup() {
  return `
  <div class="vault-modal" id="vaultModal" aria-hidden="true">
    <div class="vault-card" role="dialog" aria-modal="true" aria-labelledby="vaultTitle">
      <div class="orbit-actions">
        <button class="orbit-tool" id="vaultBack" type="button" data-i18n-title="vault.back" title="Back to arcade">${vIcon("arrow-left")}<span data-i18n="vault.back">返回街机</span></button>
        <button class="orbit-tool" id="vaultHowBtn" type="button" data-i18n-title="vault.how" title="Guide">${vIcon("book-open")}<span data-i18n="vault.how">教程</span></button>
        <button class="orbit-close icon-button" id="vaultClose" type="button" aria-label="Close" data-i18n-aria="vault.close">${vIcon("x")}</button>
      </div>
      <div class="orbit-kicker" data-i18n="vault.kicker">MINICC ARCADE · PREFIX ECONOMY</div>
      <h2 id="vaultTitle" data-i18n="vault.title">前缀密库 · 把热上下文留在手边</h2>
      <p class="orbit-subtitle" data-i18n="vault.subtitle">每个请求带着一个前缀签名。命中已缓存的前缀得分，漏掉会掉一条命；槽位有限，你必须决定谁留下。</p>
      <div class="orbit-hud vault-hud">
        <span><span data-i18n="vault.score">得分</span> <strong id="vaultScore">0</strong></span>
        <span><span data-i18n="vault.hitRate">命中率</span> <strong id="vaultHitRate">—</strong></span>
        <span><span data-i18n="vault.wave">波次</span> <strong id="vaultWave">1</strong></span>
        <span><span data-i18n="vault.combo">连击</span> <strong id="vaultCombo">0</strong></span>
        <span><span data-i18n="vault.lives">余命</span> <strong id="vaultLives">5</strong></span>
        <span><span data-i18n="vault.best">最佳</span> <strong id="vaultBest">0</strong></span>
        <span class="orbit-status" id="vaultStatus" data-i18n="vault.ready">准备就绪</span>
      </div>
      <div class="vault-stage">
      <div class="vault-request" id="vaultRequest">
        <div class="vault-request-copy"><span data-i18n="vault.incoming">当前请求</span> <strong id="vaultRequestPrefix">—</strong><small id="vaultRequestCost">—</small></div>
        <div class="vault-request-actions">
          <button class="orbit-tool" id="vaultCacheBtn" type="button" data-i18n-title="vault.cacheHint"><span data-i18n="vault.cache">放入空槽</span></button>
          <button class="orbit-tool" id="vaultEvictBtn" type="button" data-i18n-title="vault.evictHint"><span data-i18n="vault.evict">换出最久未用</span></button>
        </div>
      </div>
      <div class="vault-timer"><span id="vaultTimerBar"></span></div>
      <div class="vault-slots" id="vaultSlots" aria-label="Cache slots"></div>
      <p class="vault-hint" data-i18n="vault.hint">点命中相同前缀的槽位得分 · 空槽放入要付 token · 槽满时换出最久未用的那个</p>
      <div class="vault-overlay" id="vaultOverlay" hidden>
        <div class="orbit-overlay-card">
          <strong id="vaultOverlayTitle">—</strong>
          <p id="vaultOverlayBody">—</p>
          <button class="send-button" id="vaultOverlayBtn" type="button" data-i18n="vault.start">开始游戏</button>
        </div>
      </div>
      </div>
      <div class="orbit-how" id="vaultHowPanel" aria-hidden="true">
       <div class="orbit-how-card">
        <h3 data-i18n="vault.howTitle">五步学会前缀密库</h3>
        <p class="orbit-how-sub" data-i18n="vault.howSub">每一条都对应真实缓存策略，玩一遍就懂。</p>
        <ol class="orbit-how-list">
          <li><strong data-i18n="vault.how1t">认前缀</strong><span data-i18n="vault.how1">请求卡上的字母是它的前缀签名。点开带有同一个字母的槽位就是命中——真实项目里，前缀逐字节稳定才能命中。</span></li>
          <li><strong data-i18n="vault.how2t">别乱点</strong><span data-i18n="vault.how2">点错前缀或让请求超时都算漏，掉一条命并清空连击。五条命用完，本局结束。</span></li>
          <li><strong data-i18n="vault.how3t">空槽不是白给的</strong><span data-i18n="vault.how3">「放入空槽」要付 token 成本，不直接得分。只有你判断这个前缀后面还会来，才值得占一个槽。</span></li>
          <li><strong data-i18n="vault.how4t">会换出才算会缓存</strong><span data-i18n="vault.how4">槽位满时点「换出最久未用」：淘汰最旧的前缀，把当前请求放进去。这就是 LRU——命中率不是靠槽多，是靠换对。</span></li>
          <li><strong data-i18n="vault.how5t">盯住会话亲和</strong><span data-i18n="vault.how5">某个字母会突然变热一阵，像真实会话连续打同一段上下文。趁它热的时候多命中，热度过去再换出。</span></li>
        </ol>
        <button class="send-button orbit-how-ready" id="vaultHowReady" type="button" data-i18n="vault.howReady">我准备好了</button>
       </div>
      </div>
    </div>
  </div>`;
}

function vInit() {
  const host = document.createElement("div");
  host.innerHTML = vaultModalMarkup();
  V.modal = host.firstElementChild;
  document.body.append(V.modal);
  vApplyDomI18n(V.modal);
  vRefresh(V.modal);

  V.modal.querySelector("#vaultClose").addEventListener("click", closeVault);
  V.modal.querySelector("#vaultBack").addEventListener("click", () => { closeVault(); window.openArcadePicker?.(); });
  V.modal.addEventListener("click", (e) => { if (e.target === V.modal) closeVault(); });
  V.modal.querySelector("#vaultCacheBtn").addEventListener("click", () => vPlace(false));
  V.modal.querySelector("#vaultEvictBtn").addEventListener("click", () => vPlace(true));
  V.modal.querySelector("#vaultOverlayBtn").addEventListener("click", () => {
    if (V.ended) vReset();
    vStart();
  });
  V.modal.querySelector("#vaultHowBtn").addEventListener("click", () => {
    const panel = V.modal.querySelector("#vaultHowPanel");
    panel.classList.add("show");
    panel.setAttribute("aria-hidden", "false");
  });
  V.modal.querySelector("#vaultHowReady").addEventListener("click", () => {
    const panel = V.modal.querySelector("#vaultHowPanel");
    panel.classList.remove("show");
    panel.setAttribute("aria-hidden", "true");
  });
  V.modal.querySelector("#vaultSlots").addEventListener("click", (e) => {
    const slot = e.target.closest("[data-slot]");
    if (slot) vClickSlot(Number(slot.dataset.slot));
  });
  document.addEventListener("keydown", (e) => {
    if (!V.modal?.classList.contains("show")) return;
    if (e.key >= "1" && e.key <= "6") vClickSlot(Number(e.key) - 1);
  });
  V.inited = true;
}

function vReset() {
  V.running = false;
  V.ended = false;
  V.started = true;
  V.slots = Array.from({ length: VS.SLOTS }, () => ({ prefix: null, used: 0 }));
  V.request = null;
  V.score = 0;
  V.combo = 0;
  V.bestCombo = 0;
  V.hits = 0;
  V.misses = 0;
  V.lives = 5;
  V.wave = 1;
  V.served = 0;
  V.hot = "A";
  V.hotUntil = 0;
  V.ttl = VS.BASE_TTL;
  if (V.timer) { clearInterval(V.timer); V.timer = 0; }
  V.modal.querySelector("#vaultOverlay").hidden = false;
  vRender();
}

function vStart() {
  if (!V.started) vReset();
  V.running = true;
  V.ended = false;
  V.modal.querySelector("#vaultOverlay").hidden = true;
  vSpawn();
  V.last = performance.now();
  if (!V.timer) V.timer = setInterval(vTick, 100);
  vStatus();
  vRender();
}

function vSpawn(forced) {
  const now = performance.now();
  if (now > V.hotUntil) {
    V.hot = VPREFIXES[Math.floor(Math.random() * VPREFIXES.length)];
    V.hotUntil = now + 4200 + Math.random() * 2600;
  }
  const prefix = forced || (Math.random() < 0.52 ? V.hot : VPREFIXES[Math.floor(Math.random() * VPREFIXES.length)]);
  V.request = { prefix, cost: 50 + Math.floor(Math.random() * 180), at: now };
  V.deadline = now + V.ttl;
  vRender();
}

function vTick() {
  if (!V.running || V.ended) return;
  const now = performance.now();
  const bar = V.modal.querySelector("#vaultTimerBar");
  if (bar) bar.style.width = `${Math.max(0, Math.min(100, ((V.deadline - now) / V.ttl) * 100))}%`;
  if (now >= V.deadline) vMiss();
}

function vScore(base) {
  V.score += Math.max(0, Math.round(base * (1 + V.combo * 0.25)));
  if (V.score > V.best) {
    V.best = V.score;
    try { localStorage.setItem("minicc-vault-best", String(V.best)); } catch { /* private mode */ }
  }
}

function vHit(index) {
  V.slots[index].used = V.served;
  V.hits += 1;
  V.combo += 1;
  V.bestCombo = Math.max(V.bestCombo, V.combo);
  vScore(V.request.cost);
  V.served += 1;
  V.request = null;
  V.wave = 1 + Math.floor(V.served / VS.WAVE_SIZE);
  V.ttl = Math.max(VS.MIN_TTL, VS.BASE_TTL - (V.wave - 1) * 140);
  vSpawn();
}

function vMiss() {
  V.misses += 1;
  V.lives -= 1;
  V.combo = 0;
  V.served += 1;
  V.wave = 1 + Math.floor(V.served / VS.WAVE_SIZE);
  V.ttl = Math.max(VS.MIN_TTL, VS.BASE_TTL - (V.wave - 1) * 140);
  V.request = null;
  if (V.lives <= 0) { vEnd(); return; }
  vSpawn();
}

function vClickSlot(index) {
  if (!V.running || V.ended || !V.request || !V.slots[index]) return;
  if (V.slots[index].prefix === V.request.prefix) vHit(index);
  else vMiss();
  vRender();
}

function vPlace(evict) {
  if (!V.running || V.ended || !V.request) return;
  let target = V.slots.findIndex((s) => s.prefix === null);
  if (target < 0 && evict) {
    let oldest = Infinity;
    V.slots.forEach((s, i) => { if (s.used < oldest) { oldest = s.used; target = i; } });
  }
  if (target < 0) return;
  V.slots[target] = { prefix: V.request.prefix, used: V.served };
  V.score = Math.max(0, V.score - (evict ? VS.EVICT_COST : VS.CACHE_COST));
  V.request = null;
  V.served += 1;
  V.wave = 1 + Math.floor(V.served / VS.WAVE_SIZE);
  vSpawn();
  vRender();
}

function vEnd() {
  V.running = false;
  V.ended = true;
  if (V.timer) { clearInterval(V.timer); V.timer = 0; }
  const total = V.hits + V.misses;
  const rate = total ? Math.round((V.hits / total) * 100) : 0;
  const overlay = V.modal.querySelector("#vaultOverlay");
  V.modal.querySelector("#vaultOverlayTitle").textContent = vT("vault.gameOver");
  V.modal.querySelector("#vaultOverlayBody").textContent =
    `${vT("vault.score")} ${V.score} · ${vT("vault.hitRate")} ${rate}% · ${vT("vault.wave")} ${V.wave}`;
  V.modal.querySelector("#vaultOverlayBtn").textContent = vT("vault.again");
  overlay.hidden = false;
  vRender();
}

function vRender() {
  if (!V.modal) return;
  const set = (id, value) => {
    const el = V.modal.querySelector(`#${id}`);
    if (el) el.textContent = String(value);
  };
  set("vaultScore", V.score);
  set("vaultHitRate", (V.hits + V.misses) ? `${Math.round((V.hits / (V.hits + V.misses)) * 100)}%` : "—");
  set("vaultWave", V.wave);
  set("vaultCombo", V.combo);
  set("vaultLives", V.lives);
  set("vaultBest", V.best);
  set("vaultRequestPrefix", V.request ? V.request.prefix : "—");
  set("vaultRequestCost", V.request ? `${vT("vault.token")} ${V.request.cost}` : "—");
  const slots = V.modal.querySelector("#vaultSlots");
  if (slots) {
    slots.innerHTML = V.slots.map((s, i) =>
      `<button class="vault-slot ${s.prefix ? "filled" : "empty"}" data-slot="${i}" type="button" aria-label="${vEsc(vT("vault.slot"))} ${i + 1}">
         <b>${i + 1}</b><strong>${s.prefix ? vEsc(s.prefix) : "·"}</strong>
         <small>${s.prefix ? `${vEsc(vT("vault.used"))} ${s.used}` : vEsc(vT("vault.empty"))}</small>
       </button>`).join("");
  }
  vStatus();
}

export function openVault() {
  if (!V.inited) vInit();
  vApplyDomI18n(V.modal);
  V.modal.classList.add("show");
  V.modal.setAttribute("aria-hidden", "false");
  if (!V.started) vReset();
  else vRender();
  window.__vaultProbe = {
    state: V,
    forceRequest: (prefix) => vSpawn(prefix),
    tick: () => vTick(),
    clickSlot: (i) => vClickSlot(i),
    start: () => vStart(),
  };
}

export function closeVault() {
  if (!V.modal) return;
  V.running = false;
  if (V.timer) { clearInterval(V.timer); V.timer = 0; }
  V.modal.classList.remove("show");
  V.modal.setAttribute("aria-hidden", "true");
}

window.openVault = openVault;
window.closeVault = closeVault;
