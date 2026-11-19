import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.MINICC_WEB_URL || "http://127.0.0.1:8765";
const chapters = ["prologue", "spark", "depth", "sentry", "bloom", "hand", "gate", "mesh", "witness", "craft", "backlog", "echo", "answer", "ember", "atlas", "firstlight", "fever", "lighthouse", "gatekeeper", "meridian", "nightwatch", "fence", "compass", "deepfield", "lawn", "litmus", "harbour", "return", "steward", "relay", "tide", "lamplighter", "firefly", "candle", "newcoast", "unscathed", "slacktide", "negativespace", "greatbasin", "blackoutdrill", "quota", "arithmetic", "gathering", "oracle", "sleepless", "threshold", "remeasure", "eviction", "thewall", "livewire", "thesurge", "livecurrent", "twelfthlight", "thereckoning", "thealarm", "theledger", "thegreenline", "twoshards", "onenine", "quotation", "parallelwind", "ownscale", "forgedworld", "seventhday", "etchedwaterline", "theclick", "densemap", "oneclickmanyhands", "thelivepage", "therunnerwithoutbash", "theplanethatanswered", "thestaleassertion", "theverifierdeclines", "theredinthecapabilitylist", "theladdersnaps", "thenighttheledgerturnedgreen", "thenightthecianswered", "thequeuethatneverstops"];
const CHAPTER_MARKERS = {
  prologue: ["序章", "Prologue"],
  spark: ["火种", "The Spark"],
  depth: ["深度", "The Depth"],
  sentry: ["哨兵", "The Sentry"],
  bloom: ["盛放", "The Bloom"],
  hand: ["远行", "The Open Road"],
  gate: ["关卡", "The Gate"],
  mesh: ["星网", "The Mesh"],
  witness: ["证人", "The Witness"],
  craft: ["技艺", "The Craft"],
  backlog: ["未竟", "The Unfinished"],
  echo: ["回声", "The Echo"],
  answer: ["回问", "The Answer Back"],
  ember: ["余烬", "The Ember"],
  atlas: ["星图", "The Atlas"],
  firstlight: ["曦", "First Light"],
  fever: ["高烧", "The Fever"],
  lighthouse: ["灯塔", "The Lighthouse"],
  gatekeeper: ["守门人", "The Gatekeeper"],
  meridian: ["镜门", "The Meridian"],
  nightwatch: ["未眠", "The Night Watch"],
  fence: ["篱笆", "The Fence"],
  compass: ["罗经仪", "The Compass"],
  deepfield: ["深空", "The Deep Field"],
  lawn: ["翠茵", "The Lawn"],
  litmus: ["试纸", "The Litmus"],
  harbour: ["港灯", "The Harbour Light"],
  return: ["归航", "The Return Voyage"],
  steward: ["守望", "The Steward"],
  relay: ["驿站", "The Relay"],
  tide: ["潮汐", "The Tide"],
  lamplighter: ["灯下", "The Lamplighter"],
  firefly: ["萤", "The Firefly"],
  candle: ["烛火", "The Candle"],
  newcoast: ["新涯", "The New Coast"],
  unscathed: ["无恙", "The Unscathed"],
  slacktide: ["潮平", "The Slack Tide"],
  negativespace: ["留白", "The Negative Space"],
  greatbasin: ["归墟", "The Great Basin"],
  blackoutdrill: ["灯火管制", "The Blackout Drill"],
  quota: ["配额", "The Quota"],
  arithmetic: ["算术", "The Arithmetic"],
  gathering: ["团聚", "The Gathering"],
  oracle: ["神谕", "The Oracle"],
  sleepless: ["无眠", "The Sleepless"],
  threshold: ["进门", "The Threshold"],
  remeasure: ["复测", "The Re-Measurement"],
  eviction: ["清道夫", "The Eviction"],
  thewall: ["墙立住了", "The Wall Stood"],
  livewire: ["通缆", "The Live Wire"],
  thesurge: ["压测", "The Surge"],
  livecurrent: ["通电", "The Live Current"],
  twelfthlight: ["第十二家灯", "The Twelfth Light"],
  thereckoning: ["并账", "The Reckoning"],
  thealarm: ["警钟", "The Alarm"],
  theledger: ["会开口的账本", "The Ledger That Speaks"],
  thegreenline: ["绿线", "The Green Line"],
  twoshards: ["双峰", "The Two Shards"],
  onenine: ["现在通了", "The Now Goes Through"],
  quotation: ["破损的引号", "The Broken Quotation"],
  parallelwind: ["并发的风", "The Parallel Wind"],
  ownscale: ["按自己的尺度", "On Its Own Scale"],
  forgedworld: ["锻造的世界", "The Forged World"],
  seventhday: ["冶炼的第七日", "The Seventh Day of the Forge"],
  etchedwaterline: ["水纹的刻度", "The Etched Waterline"],
  theclick: ["回应的按键", "The Click That Answers"],
  densemap: ["密地图", "The Dense Map"],
  oneclickmanyhands: ["一键派发", "One Click, Many Hands"],
  therunnerwithoutbash: ["没有 bash 的跑道", "The Runner Without Bash"],
  theplanethatanswered: ["应声的服务面", "The Plane That Answered"],
  thestaleassertion: ["过时的断言", "The Stale Assertion"],
  theverifierdeclines: ["验证器说不行", "The Verifier Declines"],
  theredinthecapabilitylist: ["红在能力清单那一页", "The Red in the Capability List"],
  theladdersnaps: ["梯子断了，世界没断", "The Ladder Snaps, the World Does Not"],
  thenighttheledgerturnedgreen: ["全绿的那一夜", "The Night the Ledger Turned Green"],
  thenightthecianswered: ["等 ci 的那一夜", "The Night the CI Answered"],
  thequeuethatneverstops: ["排不队的队伍", "The Queue That Never Stops"],
  thelivepage: ["活的页面", "The Live Page"],
};
const CJK = /[\u4e00-\u9fff]/;

const browser = await chromium.launch({ headless: true });
const errors = [];

async function checkMode(locale, expectCjk) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on("pageerror", (e) => errors.push(`${locale}: ${e.message}`));
  await page.addInitScript((l) => localStorage.setItem("minicc-locale", l), locale);
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.locator('.nav-item[data-view="almanac"]').click();
  await page.waitForSelector(".almanac-shell");
  for (const id of chapters) {
    await page.locator(`.almanac-chapter[data-chapter="${id}"]`).click();
    await page.waitForTimeout(150);
    const canvas = await page.locator("#almanacCanvas").innerText();
    const rail = await page.locator(".almanac-rail").innerText();
    const marker = expectCjk ? CHAPTER_MARKERS[id][0] : CHAPTER_MARKERS[id][1].toLowerCase();
    assert.ok(canvas.toLowerCase().includes(marker), `${locale}/${id}: canvas must render this chapter (looked for ${marker}), first 160 chars: ${canvas.slice(0, 160).replace(/\n/g, " ")}`);
    const hit = CJK.test(`${canvas}\n${rail}`);
    if (expectCjk) {
      assert.ok(hit, `${id}: zh mode should render Chinese prose`);
    } else {
      assert.ok(!hit, `${id}: en mode rendered CJK, first 140 chars: ${canvas.slice(0, 140).replace(/\n/g, " ")}`);
    }
  }
  await page.close();
}

await checkMode("en", false);
await checkMode("zh", true);
assert.deepEqual(errors, [], `browser page errors: ${errors.join(" | ")}`);

console.log("almanac smoke passed: 78 chapters render fully bilingual, chapter switching verified, no mixed-language prose");
process.exit(0);
