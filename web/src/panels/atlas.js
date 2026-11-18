/* ============================================================
   Minicc Atlas — the world map.

   A canvas-rendered chart of everything this product actually is:
   18 panes, 62 almanac chapters, 20 manual chapters — 100 charted
   coordinates on one navigable star-map. Pan by dragging, zoom with
   the wheel, click a coordinate to walk into it. Visited coordinates
   stay lit; unvisited ones stay honest about being cartography, not
   a guided tour. Ships with the same live data in both locales.
   ============================================================ */

import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { CHAPTERS as ALMANAC_CHAPTERS } from "./almanac.js";
import { CHAPTERS as MANUAL_CHAPTERS } from "./manual.js";
import { readVisited, readVisitTrail, clearVisitHistory, setStardustListener, readStardustMilestone, writeStardustMilestone } from "../core/visited.js";

const zh = () => state.locale === "zh";
const WORLD = Object.freeze({ w: 2600, h: 1600 });

/* ---------- deterministic starfield (no render-jump randomness) ---------- */
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rng = mulberry32(0x5EED);
const STARS = Array.from({ length: 520 }, () => ({
  x: rng() * WORLD.w,
  y: rng() * WORLD.h,
  r: 0.4 + rng() * 1.6,
  twinkle: rng() * Math.PI * 2,
  speed: 0.6 + rng() * 1.4,
}));

/* ---------- the twelve regions ---------- */
const REGIONS = [
  { id: "museum",    zh: "年鉴博物馆", en: "Museum of Volumes",   tint: "#f0b35e", x: 1000, y: 260,  r: 190 },
  { id: "vault",     zh: "铁律库",     en: "The Axiom Vault",     tint: "#f0b35e", x: 1750, y: 240,  r: 150 },
  { id: "overlook",  zh: "眺望塔",     en: "The Overlook",        tint: "#b39af7", x: 850,  y: 340,  r: 120 },
  { id: "gatekeeper",zh: "管理员门",   en: "The Gatekeeper Door", tint: "#b39af7", x: 2320, y: 330,  r: 150 },
  { id: "captain",   zh: "船长日志",   en: "The Captain's Log",   tint: "#f0b35e", x: 190,  y: 700,  r: 195 },
  { id: "workbench", zh: "工作台大厅", en: "The Workbench Hall",  tint: "#f0b35e", x: 760,  y: 640,  r: 210 },
  { id: "reading",   zh: "说明书阅览室",en: "The Reading Room",   tint: "#f0b35e", x: 1370, y: 620,  r: 200 },
  { id: "observatory",zh:"问仓库观测台",en: "Repo Observatory",   tint: "#b39af7", x: 2270, y: 700,  r: 160 },
  { id: "dockyard",  zh: "船坞",       en: "The Dockyard",        tint: "#8fd6a1", x: 360,  y: 1180, r: 175 },
  { id: "archive",   zh: "档案馆",     en: "Archive Shelves",     tint: "#8fd6a1", x: 1010, y: 1230, r: 170 },
  { id: "arcade",    zh: "小游戏乐园", en: "The Arcade",          tint: "#b39af7", x: 1600, y: 1170, r: 190 },
  { id: "infirmary", zh: "诊断中心",   en: "The Infirmary",       tint: "#8fd6a1", x: 2050, y: 1270, r: 150 },
  { id: "cartographer", zh: "测绘岛",   en: "The Cartographer",   tint: "#f0b35e", x: 310,  y: 230,  r: 115 },
];

/* ---------- the 18 pane coordinates ---------- */
const PANES = [
  { id: "tasks",     region: "workbench", zh: "任务",   en: "Tasks",      dx:   0,  dy:  -60, letter: "T" },
  { id: "workspaces",region: "workbench", zh: "工作区", en: "Workspaces", dx: -105, dy:   25, letter: "W" },
  { id: "activity",  region: "workbench", zh: "活动",   en: "Activity",   dx: -35,  dy:   105, letter: "A" },
  { id: "templates", region: "workbench", zh: "模板",   en: "Templates",  dx: 105,  dy:   25, letter: "T" },
  { id: "ledger",    region: "captain",   zh: "账本",   en: "Ledger",     dx:   0,  dy:  -55, letter: "L" },
  { id: "pulse",     region: "captain",   zh: "脉搏",   en: "Pulse",      dx: -80,  dy:   30, letter: "P" },
  { id: "recent",    region: "captain",   zh: "近况",   en: "Recent",     dx:   0,  dy:   95, letter: "R" },
  { id: "journal",   region: "captain",   zh: "日志",   en: "Journal",    dx:  80,  dy:   30, letter: "J" },
  { id: "almanac",   region: "museum",    zh: "年鉴",   en: "Almanac",    dx:   0,  dy:   15, letter: "A" },
  { id: "manual",    region: "reading",   zh: "说明书", en: "Manual",     dx:   0,  dy:   50, letter: "M" },
  { id: "axioms",    region: "vault",     zh: "铁律",   en: "Axioms",     dx:   0,  dy:   10, letter: "X" },
  { id: "promo",     region: "overlook",  zh: "宣传页", en: "Promo",      dx:   0,  dy:   10, letter: "P" },
  { id: "dockyard",  region: "dockyard",  zh: "船厂",   en: "Dockyard",   dx:   0,  dy:   15, letter: "D" },
  { id: "doctor",    region: "infirmary", zh: "诊断",   en: "Doctor",     dx:   0,  dy:    5, letter: "D" },
  { id: "admin",     region: "gatekeeper",zh: "管理",   en: "Admin",      dx:   0,  dy:   10, letter: "G" },
  { id: "arcade",    region: "arcade",    zh: "小游戏", en: "Arcade",     dx: -50,  dy:    0, letter: "A" },
  { id: "askdocs",   region: "observatory",zh:"问仓库", en: "Ask the Repo",dx:  0,  dy:   10, letter: "Q" },
  { id: "archive",   region: "archive",   zh: "档案馆", en: "Archive",    dx:   0,  dy:   10, letter: "X" },
];

const REGION_INDEX = new Map(REGIONS.map((r) => [r.id, r]));

const PANE_NODES = PANES.map((p) => {
  const region = REGION_INDEX.get(p.region);
  return {
    ...p,
    regionName: zh() ? region.zh : region.en,
    x: region.x + p.dx,
    y: region.y + p.dy,
    kind: "panel",
    idLabel: p.id,
    visitedKey: `panel:${p.id}`,
  };
});

/* satellites: the writings glowing around the museum and the reading room */
const ALMANAC_SATELLITES = ALMANAC_CHAPTERS.map((ch, i) => {
  const ring = i < 10 ? 268 : 345;
  const step = Math.PI * 2 / (i < 10 ? 10 : 9);
  const angle = (i < 10 ? i * step : (i - 10) * step + step / 2) - Math.PI / 2;
  const museum = REGION_INDEX.get("museum");
  return {
    id: `chapter:${ch.id}`,
    chapterId: ch.id,
    zh: ch.roman?.zh ? `${ch.roman.zh} · ${ch.title?.zh ?? ch.title}` : ch.id,
    en: ch.roman?.en ? `${ch.roman.en} · ${ch.title?.en ?? ch.title}` : ch.id,
    x: museum.x + Math.cos(angle) * ring,
    y: museum.y + Math.sin(angle) * ring,
    region: "museum",
    regionName: zh() ? "年鉴博物馆" : "Museum of Volumes",
    kind: "almanac",
    letter: String((i % 9) + 1),
    visitedKey: `chapter:${ch.id}`,
    r: 17,
  };
});

const MANUAL_SATELLITES = MANUAL_CHAPTERS.map((ch, i) => {
  const ring = 262;
  const step = Math.PI * 2 / MANUAL_CHAPTERS.length;
  const angle = i * step - Math.PI / 2 - 0.4;
  const reading = REGION_INDEX.get("reading");
  return {
    id: `manual:${ch.id}`,
    chapterId: ch.id,
    zh: `${ch.roman} · ${ch.titleZh}`,
    en: `${ch.romanEn} · ${ch.title}`,
    x: reading.x + Math.cos(angle) * ring,
    y: reading.y + Math.sin(angle) * ring,
    region: "reading",
    regionName: zh() ? "说明书阅览室" : "The Reading Room",
    kind: "manual",
    letter: String(i + 1),
    visitedKey: `manual:${ch.id}`,
    r: 16,
  };
});


/* v M8-T1039 — the islands ledger. Thirteen islands exactly, counted honestly. */
const ISLAND_ORDER = ["workbench", "captain", "museum", "reading", "vault", "overlook", "dockyard", "infirmary", "gatekeeper", "arcade", "observatory", "archive", "cartographer"];
const ISLAND_LORE = [
  { region: "cartographer", zhName: "测绘岛", enName: "The Cartographer", zhLore: "每一处坐标先勘探，后安放——这一岛只认数字，不认情绪。", enLore: "Every coordinate surveyed before it was named — the one island that only reads numbers.", tint: "#f0b35e" },
  { region: "workbench",  zhName: "工作台大厅", enName: "The Workbench Hall", zhLore: "任务、工作区、动态、模板——长椅上的每一块木头都留着你的指纹。", enLore: "Tasks, workspaces, activity, templates — every plank on these benches carries your fingerprints.", tint: "#f0b35e" },
  { region: "captain",    zhName: "船长日志",   enName: "The Captain's Log", zhLore: "账本、脉搏、近况、日志——这艘船唯一从不掩饰自己的地方。", enLore: "Ledger, pulse, recent and journal — the one place on this ship that never flatters itself.", tint: "#f0b35e" },
  { region: "museum",     zhName: "年鉴博物馆", enName: "Museum of Volumes", zhLore: "二十二卷每一页都来自仓库自己说的话，读它们等于审计你的坚持。", enLore: "Twenty-two volumes of the repo's own voice — reading them is auditing your own persistence.", tint: "#f0b35e" },
  { region: "reading",    zhName: "说明书阅览室", enName: "The Reading Room", zhLore: "怎么打开、怎么用、怎么退出——写在纸上永远比在外头猜来得快。", enLore: "How to open, how to use, how to leave — paper told you sooner than the room would have.", tint: "#f0b35e" },
  { region: "vault",      zhName: "铁律库",     enName: "The Axiom Vault", zhLore: "十条铁律，每一条都被质疑过、也都被证明了自己。", enLore: "Ten laws here, each one once questioned — and each one proved itself anyway.", tint: "#b39af7" },
  { region: "overlook",   zhName: "瞭望塔",     enName: "The Overlook", zhLore: "免费入场。世界在这个高度开始给自己打广告——心甘情愿地。", enLore: "Free of charge. The world advertises itself up here — quite happily.", tint: "#b39af7" },
  { region: "dockyard",   zhName: "船厂",       enName: "The Dockyard", zhLore: "每一笔提交都钉在墙上——给你自己看的。", enLore: "Every commit nailed to the wall — for your eyes only.", tint: "#8fd6a1" },
  { region: "infirmary",  zhName: "诊断中心",   enName: "The Infirmary", zhLore: "对外给出真实的回声，对内给出真实的压力。", enLore: "A real echo to the outside world; a real load on the inside.", tint: "#8fd6a1" },
  { region: "gatekeeper", zhName: "管理员门",   enName: "The Gatekeeper Door", zhLore: "密码 123——所有人都知道，所以它摆在边界上反而成了检查站。", enLore: "Password 123 — everyone knows it, which is exactly why it stands at the border.", tint: "#b39af7" },
  { region: "arcade",     zhName: "小游戏乐园", enName: "The Arcade", zhLore: "边守阵线边等构建结束——工作不塌方，生活也能塌方。", enLore: "Hold the line while the build finishes — the only siege here that pays off.", tint: "#b39af7" },
  { region: "observatory",zhName: "问仓库观测台", enName: "Repo Observatory", zhLore: "BM25 只是一双词典级别的耳朵，但对这个仓库，够用。", enLore: "BM25 is a dictionary-grade ear — and more than enough for this repository.", tint: "#b39af7" },
  { region: "archive",    zhName: "档案馆",     enName: "Archive Shelves", zhLore: "每一笔提交都钉在墙上，但没人真去数数——直到你打开这个房间。", enLore: "Every commit nailed to the shelf — nobody ever counted them until you walked in here.", tint: "#8fd6a1" },
];

const ALL_NODES = [...PANE_NODES, ...ALMANAC_SATELLITES, ...MANUAL_SATELLITES];
const ATLAS_TOTAL = ALL_NODES.length;

/* ------------------------------------------------------------------
   M8-T1035 — stardust milestones. Real gameplay on real visits:
   25 / 50 / 75 / 100 percent of the charted coordinates trigger a
   one-shot bilingual toast, persisted so the same threshold never
   toasts twice; an honest reset is part of "clear my trail".
   Fresh visitors start at zero, so nothing fires on an empty world.
   ------------------------------------------------------------------ */
const MILESTONE_KEYS = ["atlas.milestone25", "atlas.milestone50", "atlas.milestone75", "atlas.milestone100"];
const MILESTONE_THRESHOLDS = [0.25, 0.5, 0.75, 1];

function showMilestoneToast(message) {
  const toast = $("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showMilestoneToast.timer);
  showMilestoneToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3600);
}

function stardustCount() {
  const visited = readVisited();
  let count = 0;
  for (const node of ALL_NODES) if (visited.has(node.visitedKey ?? node.id)) count += 1;
  return count;
}

function milestoneText(index) {
  const total = ALL_NODES.length;
  const target = Math.ceil(total * MILESTONE_THRESHOLDS[index]);
  return t(MILESTONE_KEYS[index]).replace("{n}", String(target)).replace("{total}", String(total));
}

function checkStardustMilestones() {
  const total = ALL_NODES.length;
  const count = stardustCount();
  let pending = 0;
  for (let i = 0; i < MILESTONE_THRESHOLDS.length; i += 1) {
    if (count >= Math.ceil(total * MILESTONE_THRESHOLDS[i])) pending = i + 1;
  }
  const stored = readStardustMilestone();
  if (pending <= stored) return;
  writeStardustMilestone(pending);
  showMilestoneToast(milestoneText(pending - 1));
}

setStardustListener(checkStardustMilestones);

const NODE_INDEX = new Map(ALL_NODES.map((n) => [n.visitedKey ?? n.id, n]));

/* ---------- camera ---------- */
const camera = { x: WORLD.w / 2, y: WORLD.h / 2, zoom: 0.52 };
const MIN_ZOOM = 0.42, MAX_ZOOM = 1.9;

function screenToWorld(canvas, clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  const sx = clientX - rect.left - rect.width / 2;
  const sy = clientY - rect.top - rect.height / 2;
  return {
    x: camera.x + sx / camera.zoom,
    y: camera.y + sy / camera.zoom,
  };
}
const worldToScreen = (canvas, wx, wy) => {
  const rect = canvas.getBoundingClientRect();
  return {
    x: rect.width / 2 + (wx - camera.x) * camera.zoom,
    y: rect.height / 2 + (wy - camera.y) * camera.zoom,
  };
};

/* ---------- drawing helpers ---------- */
function drawNode(ctx, node, visited, hovered, dpr) {
  const r = (node.r ?? 30);
  const { x, y } = node;
  const lit = visited.has(node.visitedKey ?? node.id);
  const color = lit ? "#fbbf24" : "#7d8694";
  // outer ring
  ctx.lineWidth = 2.2;
  ctx.strokeStyle = lit ? "rgba(251,191,36,0.95)" : "rgba(148,163,184,0.55)";
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.stroke();
  // filled body
  ctx.fillStyle = lit ? "rgba(251,191,36,0.22)" : "rgba(30,41,59,0.9)";
  ctx.beginPath();
  ctx.arc(x, y, r - 2, 0, Math.PI * 2);
  ctx.fill();
  // glyph
  ctx.fillStyle = lit ? "#fde68a" : "#cbd5e1";
  ctx.font = `600 ${Math.max(10, Math.round(r * 0.72))}px 'DM Mono', monospace`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(node.letter ?? "?", x, y + 1);
  if (hovered) {
    ctx.lineWidth = 1.6;
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = "#fde68a";
    ctx.beginPath();
    ctx.arc(x, y, r + 5, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
  }
}

function drawIsland(ctx, region, time) {
  const { x, y, r, tint, zh: nameZh, en: nameEn } = region;
  // soft nebula pool beneath the island
  const grad = ctx.createRadialGradient(x, y, 8, x, y, r * 1.55);
  grad.addColorStop(0, `${tint}26`);
  grad.addColorStop(1, `${tint}00`);
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(x, y, r * 1.55, 0, Math.PI * 2);
  ctx.fill();
  // irregular island body
  ctx.beginPath();
  const pts = 14;
  for (let i = 0; i <= pts; i++) {
    const a = (i / pts) * Math.PI * 2;
    const wob = 1 + 0.10 * Math.sin(i * 2.35 + region.id.length);
    const px = x + Math.cos(a) * r * wob;
    const py = y + Math.sin(a) * r * wob;
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  }
  ctx.closePath();
  ctx.fillStyle = "rgba(23,32,45,0.92)";
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.setLineDash([10, 7]);
  ctx.strokeStyle = `${tint}66`;
  ctx.stroke();
  ctx.setLineDash([]);
  // bobbing beacon
  ctx.fillStyle = tint;
  ctx.beginPath();
  ctx.arc(x, y - r * 0.52, 4.6 + Math.sin(time * 0.002 + region.id.length) * 1.4, 0, Math.PI * 2);
  ctx.fill();
  // label sits just below the island outline, map-legend style
  ctx.fillStyle = "rgba(230,237,247,0.92)";
  ctx.font = "700 15px 'Manrope', system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(zh() ? nameZh : nameEn, x, y + r + 18);
}

/* ---------- state ---------- */
const stateRef = { canvas: null, raf: 0, hovered: null, dragging: false, panned: 0, lastX: 0, lastY: 0, visited: new Set() };

function render(time = 0) {
  const canvas = stateRef.canvas;
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  ctx.setTransform(window.devicePixelRatio || 1, 0, 0, window.devicePixelRatio || 1, 0, 0);
  ctx.clearRect(0, 0, width, height);
  // deep-space backdrop (screen space gradient)
  const bg = ctx.createLinearGradient(0, 0, 0, height);
  bg.addColorStop(0, "#0b1016");
  bg.addColorStop(0.5, "#101a26");
  bg.addColorStop(1, "#0b1016");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  ctx.save();
  ctx.translate(width / 2, height / 2);
  ctx.scale(camera.zoom, camera.zoom);
  ctx.translate(-camera.x, -camera.y);

  // nebulas (world space)
  const nebulas = [
    { x: 700, y: 300, r: 620, c: "240,179,94", a: 0.055 },
    { x: 1800, y: 500, r: 720, c: "143,214,161", a: 0.05 },
    { x: 1250, y: 1150, r: 700, c: "179,154,247", a: 0.05 },
  ];
  for (const n of nebulas) {
    const g = ctx.createRadialGradient(n.x, n.y, 40, n.x, n.y, n.r);
    g.addColorStop(0, `rgba(${n.c},${n.a})`);
    g.addColorStop(1, `rgba(${n.c},0)`);
    ctx.fillStyle = g;
    ctx.fillRect(n.x - n.r, n.y - n.r, n.r * 2, n.r * 2);
  }

  // starfield with twinkle
  for (const s of STARS) {
    const tw = 0.55 + 0.45 * Math.sin(time * 0.001 * s.speed + s.twinkle);
    ctx.globalAlpha = tw;
    ctx.fillStyle = "#e8edf5";
    ctx.beginPath();
    ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  // dashed coordinate grid
  ctx.lineWidth = 1;
  ctx.setLineDash([2, 14]);
  ctx.strokeStyle = "rgba(148,163,184,0.13)";
  for (let x = 200; x < WORLD.w; x += 200) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, WORLD.h); ctx.stroke(); }
  for (let y = 200; y < WORLD.h; y += 200) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(WORLD.w, y); ctx.stroke(); }
  ctx.setLineDash([]);

  // isobath curves (the "sea" boundary of the world)
  ctx.setLineDash([14, 10]);
  ctx.strokeStyle = "rgba(143,214,161,0.28)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(60, 60);
  ctx.bezierCurveTo(700, 10, 1400, 120, 2540, 40);
  ctx.bezierCurveTo(2580, 700, 2520, 1200, 2500, 1560);
  ctx.bezierCurveTo(1500, 1620, 800, 1520, 60, 1560);
  ctx.bezierCurveTo(10, 1100, 30, 500, 60, 60);
  ctx.closePath();
  ctx.stroke();
  ctx.setLineDash([]);

  // islands
  for (const region of REGIONS) drawIsland(ctx, region, time);

  // almanac satellite orbit ring
  ctx.setLineDash([4, 9]);
  ctx.strokeStyle = "rgba(240,179,94,0.35)";
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  ctx.arc(REGION_INDEX.get("museum").x, REGION_INDEX.get("museum").y, 268, 0, Math.PI * 2);
  ctx.beginPath();
  ctx.arc(REGION_INDEX.get("museum").x, REGION_INDEX.get("museum").y, 345, 0, Math.PI * 2);
  ctx.stroke();
  // manual satellite orbit ring
  ctx.strokeStyle = "rgba(240,179,94,0.3)";
  ctx.beginPath();
  ctx.arc(REGION_INDEX.get("reading").x, REGION_INDEX.get("reading").y, 262, 0, Math.PI * 2);
  ctx.stroke();
  ctx.setLineDash([]);

  // the trail the visitor walked — amber thread through visited coordinates, oldest first
  const trail = readVisitTrail()
    .map((id) => NODE_INDEX.get(id))
    .filter(Boolean);
  if (trail.length >= 2) {
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "rgba(251,191,36,0.22)";
    ctx.lineWidth = 6;
    ctx.shadowColor = "rgba(251,191,36,0.55)";
    ctx.shadowBlur = 12;
    ctx.beginPath();
    ctx.moveTo(trail[0].x, trail[0].y);
    for (const node of trail.slice(1)) ctx.lineTo(node.x, node.y);
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = "rgba(251,191,36,0.85)";
    ctx.lineWidth = 1.6;
    ctx.setLineDash([7, 7]);
    ctx.lineDashOffset = -time * 0.012;
    ctx.beginPath();
    ctx.moveTo(trail[0].x, trail[0].y);
    for (const node of trail.slice(1)) ctx.lineTo(node.x, node.y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(251,191,36,0.85)";
    for (let i = 0; i < trail.length; i++) {
      ctx.beginPath();
      ctx.arc(trail[i].x, trail[i].y, 3.6 + (i === trail.length - 1 ? 1.8 : 0), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  // Stardust inventory — one shard per charted coordinate (visited set length)
  updateShardsHUD();

  // nodes
  for (const node of ALL_NODES) drawNode(ctx, node, stateRef.visited, stateRef.hovered === node, 1);

  ctx.restore();

  // vignette (screen space)
  const v = ctx.createRadialGradient(width / 2, height / 2, height * 0.45, width / 2, height / 2, height * 0.95);
  v.addColorStop(0, "rgba(5,8,12,0)");
  v.addColorStop(1, "rgba(5,8,12,0.55)");
  ctx.fillStyle = v;
  ctx.fillRect(0, 0, width, height);

  stateRef.raf = requestAnimationFrame(render);
}

function fitCamera(canvas) {
  const rect = canvas.getBoundingClientRect();
  camera.x = WORLD.w / 2;
  camera.y = WORLD.h / 2;
  camera.zoom = Math.min(rect.width / WORLD.w, rect.height / WORLD.h) * 0.97;
}

function hitNode(canvas, clientX, clientY) {
  const p = screenToWorld(canvas, clientX, clientY);
  let best = null, bestD = Infinity;
  for (const node of ALL_NODES) {
    const r = (node.r ?? 30) + 2;
    const d = Math.hypot(node.x - p.x, node.y - p.y);
    if (d <= r && d < bestD) { best = node; bestD = d; }
  }
  return best;
}

export async function openAtlas() {
  const modal = $("#atlasStage");
  if (!modal) return;
  stateRef.visited = readVisited();
  modal.setAttribute("aria-hidden", "false");
  if (!stateRef.canvas) {
    stateRef.canvas = $("#atlasCanvas");
    wireAtlas(stateRef.canvas);
    fitCamera(stateRef.canvas);
    stateRef.fitted = true;
  }
  const closeBtn = $("#atlasClose");
  if (closeBtn) { closeBtn.onclick = () => closeAtlas(); }
  const resetBtn = $("#atlasReset");
  if (resetBtn) { resetBtn.onclick = () => { const c = stateRef.canvas; if (c) fitCamera(c); }; }
  const clearBtn = $("#atlasClearTrail");
  if (clearBtn) { clearBtn.onclick = () => { clearVisitHistory(); stateRef.visited = new Set(); updateHUD(); }; }
  const islandsToggle = $("#atlasIslandsToggle");
  if (islandsToggle) islandsToggle.onclick = () => toggleIslands();
  const islandsPanel = $("#atlasIslands");
  if (islandsPanel) islandsPanel.setAttribute("hidden", "");
  resizeAtlas();
  updateHUD();
  refreshIcons();
  cancelAnimationFrame(stateRef.raf);
  stateRef.raf = requestAnimationFrame(render);
}

export function closeAtlas() {
  const modal = $("#atlasStage");
  if (!modal) return;
  modal.setAttribute("aria-hidden", "true");
  const islandsPanel = $("#atlasIslands");
  if (islandsPanel) islandsPanel.setAttribute("hidden", "");
  cancelAnimationFrame(stateRef.raf);
}

function renderIslands() {
  const panel = $("#atlasIslands");
  const list = $("#atlasIslandsList");
  const summary = $("#atlasIslandsCharted");
  if (!panel || !list || !summary) return;
  if (panel.getAttribute("hidden") === "true" || panel.hasAttribute("hidden")) return;
  const visited = readVisited();
  let total = 0;
  let charted = 0;
  const zhFlag = zh();
  const rows = [];
  for (const regionId of ISLAND_ORDER) {
    const lore = ISLAND_LORE.find((entry) => entry.region === regionId);
    const nodes = ALL_NODES.filter((node) => node.region === regionId);
    const done = nodes.filter((node) => visited.has(node.visitedKey ?? node.id)).length;
    total += nodes.length;
    charted += done;
    const pct = nodes.length > 0 ? Math.round((done / nodes.length) * 100) : 0;
    const status = done === nodes.length && nodes.length > 0
      ? (zhFlag ? t("atlas.islandsDone") : t("atlas.islandsDone"))
      : (done > 0 ? (zhFlag ? t("atlas.islandsProgress") : t("atlas.islandsProgress")) : (zhFlag ? "未触及" : "uncharted"));
    rows.push(`<li class="atlas-island-row${done === nodes.length ? " atlas-island-complete" : done === 0 ? " atlas-island-dim" : ""}">
      <span class="atlas-island-dot" style="--island-tint:${lore.tint}"></span>
      <span class="atlas-island-body">
        <span class="atlas-island-name">${escapeTip(zhFlag ? lore.zhName : lore.enName)}
          <span class="atlas-island-count">${done} / ${nodes.length}</span>
        </span>
        <span class="atlas-island-lore">${escapeTip(zhFlag ? lore.zhLore : lore.enLore)}</span>
        <span class="atlas-island-bar"><i style="width:${pct}%"></i></span>
      </span>
      <span class="atlas-island-status">${escapeTip(status)}</span>
    </li>`);
  }
  summary.textContent = `${charted} / ${total}`;
  list.innerHTML = rows.join("");
}

function toggleIslands(forceOpen) {
  const panel = $("#atlasIslands");
  if (!panel) return;
  const open = forceOpen ?? panel.hasAttribute("hidden");
  if (open) {
    panel.removeAttribute("hidden");
    renderIslands();
  } else {
    panel.setAttribute("hidden", "");
  }
}

function updateShardsHUD() {
  const visited = readVisited();
  const wrapped = $("#atlasShards");
  const label = $("#atlasShardsCount");
  if (!wrapped || !label) return;
  const count = ALL_NODES.filter((n) => visited.has(n.visitedKey ?? n.id)).length;
  if (count <= 0) {
    wrapped.setAttribute("hidden", "");
    return;
  }
  wrapped.removeAttribute("hidden");
  label.textContent = `${count} / ${ALL_NODES.length}`;
}

function updateHUD() {
  const visited = readVisited();
  let charted = 0;
  for (const node of ALL_NODES) if (visited.has(node.visitedKey ?? node.id)) charted += 1;
  const el = $("#atlasCharted");
  if (el) el.textContent = t("atlas.charted").replace("{n}", String(charted)).replace("{total}", String(ATLAS_TOTAL));
}

function wireAtlas(canvas) {
  const tooltip = $("#atlasTooltip");
  const showTip = (clientX, clientY, node) => {
    if (!tooltip) return;
    const visited = readVisited();
    const name = zh() ? node.zh : node.en;
    const region = node.regionName;
    const tag = visited.has(node.visitedKey ?? node.id) ? (zh() ? "已探索" : "charted") : (zh() ? "未探索" : "uncharted");
    tooltip.innerHTML = `<strong>${escapeTip(name)}</strong><span>${escapeTip(region)} · ${escapeTip(tag)}</span>`;
    tooltip.style.left = `${clientX + 14}px`;
    tooltip.style.top = `${clientY + 14}px`;
    tooltip.hidden = false;
  };
  const hideTip = () => { if (tooltip) tooltip.hidden = true; };

  canvas.addEventListener("pointerdown", (ev) => {
    stateRef.dragging = true;
    stateRef.panned = 0;
    stateRef.lastX = ev.clientX;
    stateRef.lastY = ev.clientY;
    canvas.setPointerCapture(ev.pointerId);
  });
  canvas.addEventListener("pointermove", (ev) => {
    if (stateRef.dragging) {
      const dx = ev.clientX - stateRef.lastX;
      const dy = ev.clientY - stateRef.lastY;
      stateRef.panned += Math.abs(dx) + Math.abs(dy);
      camera.x -= dx / camera.zoom;
      camera.y -= dy / camera.zoom;
      camera.x = Math.max(-200, Math.min(WORLD.w + 200, camera.x));
      camera.y = Math.max(-160, Math.min(WORLD.h + 160, camera.y));
      stateRef.lastX = ev.clientX;
      stateRef.lastY = ev.clientY;
      hideTip();
      return;
    }
    const node = hitNode(canvas, ev.clientX, ev.clientY);
    stateRef.hovered = node;
    canvas.style.cursor = node ? "pointer" : "grab";
    if (node) showTip(ev.clientX, ev.clientY, node);
    else hideTip();
  });
  const drop = (ev) => {
    if (!stateRef.dragging) return;
    stateRef.dragging = false;
    try { canvas.releasePointerCapture(ev.pointerId); } catch { /* already released */ }
    hideTip();
  };
  canvas.addEventListener("pointerup", drop);
  canvas.addEventListener("pointercancel", drop);

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("#atlasStage")?.getAttribute("aria-hidden") === "false") {
      event.preventDefault();
      closeAtlas();
    }
  });

  canvas.addEventListener("click", (ev) => {
    if (stateRef.panned > 6) return;
    const node = hitNode(canvas, ev.clientX, ev.clientY);
    if (!node) return;
    closeAtlas();
    if (node.kind === "panel") {
      window.dispatchEvent(new CustomEvent("minicc:nav", { detail: { view: node.id } }));
    } else if (node.kind === "almanac") {
      window.dispatchEvent(new CustomEvent("minicc:nav", { detail: { view: "almanac", chapter: node.chapterId } }));
    } else if (node.kind === "manual") {
      window.dispatchEvent(new CustomEvent("minicc:nav", { detail: { view: "manual", chapter: node.chapterId } }));
    }
  });

  canvas.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const pivot = screenToWorld(canvas, ev.clientX, ev.clientY);
    const factor = Math.exp(-ev.deltaY * 0.0012);
    camera.zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, camera.zoom * factor));
    const after = screenToWorld(canvas, ev.clientX, ev.clientY);
    camera.x += pivot.x - after.x;
    camera.y += pivot.y - after.y;
  }, { passive: false });

  window.addEventListener("resize", resizeAtlas);
}

const escapeTip = (value) =>
  String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// Keep the pre-rendered HUD honest before the first Atlas open: the static
// markup ships a locale-neutral placeholder, and state.locale is already loaded
// from localStorage long before this module evaluates.
try { updateHUD(); updateShardsHUD(); } catch { /* HUD not in DOM yet - fine */ }
try { checkStardustMilestones(); } catch { /* milestones must never break boot */ }
window.addEventListener("minicc:locale-changed", () => {
  try { updateHUD(); updateShardsHUD(); } catch { /* same best-effort guarantee */ }
});

export function resizeAtlas() {
  const canvas = stateRef.canvas;
  if (!canvas) return;
  const wrapper = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(320, wrapper.clientWidth);
  const h = Math.max(320, wrapper.clientHeight);
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  const ctx = canvas.getContext("2d");
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (!stateRef.fitted) { fitCamera(canvas); stateRef.fitted = true; }
  if (camera.zoom < MIN_ZOOM || camera.zoom > MAX_ZOOM) fitCamera(canvas);
}
