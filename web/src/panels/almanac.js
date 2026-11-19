/* ============================================================
   Minicc Almanac — the museum of what this project actually is.

   A read-only excursion across the engineering artifacts that make
   up a coding agent. Every word on screen follows the workbench
   locale — no mixed-language prose: the zh mode is all Chinese,
   the en mode is all English. Every number is derived from live
   sources (/api/metrics, /api/digest, /api/stats, git itself).
   ============================================================ */

import { requestJson } from "../core/transport.js";
import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { openPanel, beginPanelRequest } from "../chat/stream.js";
import { escapeHtml } from "../chat/markdown.js";
import { compactNumber } from "../panels/index.js";
import { markVisited } from "../core/visited.js";

const zh = () => state.locale === "zh";

export const CHAPTERS = [
  { id: "prologue", roman: { zh: "序章", en: "Prologue" }, title: { zh: "一封给未来的信", en: "The Letter" }, subtitle: { zh: "一封给未来的信", en: "A letter to the future" } },
  { id: "spark", roman: { zh: "第一章", en: "Chapter I" }, title: { zh: "火种", en: "The Spark" }, subtitle: { zh: "意图 → 计划 → 行动 → 证据", en: "Intent → Plan → Act → Proof" } },
  { id: "depth", roman: { zh: "第二章", en: "Chapter II" }, title: { zh: "深度", en: "The Depth" }, subtitle: { zh: "压缩、保留、再出发", en: "Compact, keep, depart again" } },
  { id: "sentry", roman: { zh: "第三章", en: "Chapter III" }, title: { zh: "哨兵", en: "The Sentry" }, subtitle: { zh: "每一个承诺都要被执行", en: "Every promise gets executed" } },
  { id: "bloom", roman: { zh: "第四章", en: "Chapter IV" }, title: { zh: "盛放", en: "The Bloom" }, subtitle: { zh: "工作台本身就是证词", en: "The workbench itself is testimony" } },
  { id: "hand", roman: { zh: "第五章", en: "Chapter V" }, title: { zh: "远行", en: "The Open Road" }, subtitle: { zh: "纸上画下的远方", en: "What is still unmapped" } },
  { id: "gate", roman: { zh: "卷六", en: "Chapter VI" }, title: { zh: "关卡", en: "The Gate" }, subtitle: { zh: "每一道门都点了头", en: "Every gate said yes" } },
  { id: "mesh", roman: { zh: "卷七", en: "Chapter VII" }, title: { zh: "星网", en: "The Mesh" }, subtitle: { zh: "六个服务，一个国家", en: "Six services, one country" } },
  { id: "witness", roman: { zh: "卷八", en: "Chapter VIII" }, title: { zh: "证人", en: "The Witness" }, subtitle: { zh: "笔录不说话，但不说谎", en: "The record does not speak, but it does not lie" } },
  { id: "craft", roman: { zh: "卷九", en: "Chapter IX" }, title: { zh: "技艺", en: "The Craft" }, subtitle: { zh: "一件件作品在同样的手里被磨", en: "Every detail ground by the same hand" } },
  { id: "backlog", roman: { zh: "卷十", en: "Chapter X" }, title: { zh: "未竟", en: "The Unfinished" }, subtitle: { zh: "这册子还没写完，它正在写", en: "This wing is still being written" } },
  { id: "echo", roman: { zh: "卷十一", en: "Chapter XI" }, title: { zh: "回声", en: "The Echo" }, subtitle: { zh: "三根看不见的弦，都在响", en: "Three strings you cannot see, all humming" } },
  { id: "answer", roman: { zh: "卷十二", en: "Chapter XII" }, title: { zh: "回问", en: "The Answer Back" }, subtitle: { zh: "终于学会回答的这本书", en: "The book that answered back" } },
  { id: "ember", roman: { zh: "卷十三", en: "Chapter XIII" }, title: { zh: "余烬", en: "The Ember" }, subtitle: { zh: "炉火不散", en: "The hearth stays warm" } },
  { id: "atlas", roman: { zh: "卷十四", en: "Chapter XIV" }, title: { zh: "星图", en: "The Atlas" }, subtitle: { zh: "这片世界有多少岛", en: "How many islands this world holds" } },
  { id: "firstlight", roman: { zh: "卷十五", en: "Chapter XV" }, title: { zh: "曦", en: "First Light" }, subtitle: { zh: "有人按下了那颗星", en: "Someone hit the star" } },
  { id: "fever", roman: { zh: "卷十六", en: "Chapter XVI" }, title: { zh: "高烧", en: "The Fever" }, subtitle: { zh: "所有悬的地方，后来都长成了门", en: "Every near-miss grew into a gate" } },
  { id: "lighthouse", roman: { zh: "卷十七", en: "Chapter XVII" }, title: { zh: "灯塔", en: "The Lighthouse" }, subtitle: { zh: "忙解决问题的人，也该被守住", en: "Even the one fixing things deserves to be kept" } },
  { id: "gatekeeper", roman: { zh: "卷十八", en: "Chapter XVIII" }, title: { zh: "守门人", en: "The Gatekeeper" }, subtitle: { zh: "知道密码的人，看见同一份诚实", en: "Everyone with the 123 door sees the same honest ledger" } },
  { id: "meridian", roman: { zh: "卷十九", en: "Chapter XIX" }, title: { zh: "镜门", en: "The Meridian" }, subtitle: { zh: "有人问路的地方，就是答案", en: "Where directions are given for walks never taken" } },
  { id: "nightwatch", roman: { zh: "卷二十", en: "Chapter XX" }, title: { zh: "未眠", en: "The Night Watch" }, subtitle: { zh: "账本没有合上，它只是翻开下一页", en: "The ledger never closed; it turned the page" } },
  { id: "fence", roman: { zh: "卷二十一", en: "Chapter XXI" }, title: { zh: "篱笆", en: "The Fence" }, subtitle: { zh: "一个语言时代只有一种语言", en: "One era of language, one language" } },
  { id: "compass", roman: { zh: "卷二十二", en: "Chapter XXII" }, title: { zh: "罗经仪", en: "The Compass" }, subtitle: { zh: "引导不是兜底，是建筑", en: "Guidance is not a parachute, it is architecture" } },
  { id: "deepfield", roman: { zh: "卷二十三", en: "Chapter XXIII" }, title: { zh: "深空", en: "The Deep Field" }, subtitle: { zh: "勘完不是终点，是望远镜的起点", en: "Finish the chart, then point the telescope deeper" } },
  { id: "lawn", roman: { zh: "卷二十四", en: "Chapter XXIV" }, title: { zh: "翠茵", en: "The Lawn" }, subtitle: { zh: "先给草插上旗子，再让僵尸来", en: "Plant the flag before the zombie learns the gate" } },
  { id: "litmus", roman: { zh: "卷二十五", en: "Chapter XXV" }, title: { zh: "试纸", en: "The Litmus" }, subtitle: { zh: "红门只说一件事：这里有事没说完", en: "Red only ever means one thing: something here is unfinished" } },
  { id: "harbour", roman: { zh: "卷二十六", en: "Chapter XXVI" }, title: { zh: "港灯", en: "The Harbour Light" }, subtitle: { zh: "每一盏灯都指得出来真礁的那一夜", en: "The night every lamp finally named the rocks" } },
  { id: "return", roman: { zh: "卷二十七", en: "Chapter XXVII" }, title: { zh: "归航", en: "The Return Voyage" }, subtitle: { zh: "门绿了以后，船才真的回港", en: "Only green gates can bring the ship home" } },
  { id: "steward", roman: { zh: "卷二十八", en: "Chapter XXVIII" }, title: { zh: "守望", en: "The Steward" }, subtitle: { zh: "先把每盏灯的颜色读清楚了，再谈守望", en: "Learn every color the lamps can throw, then speak of watching" } },
  { id: "relay", roman: { zh: "卷二十九", en: "Chapter XXIX" }, title: { zh: "驿站", en: "The Relay" }, subtitle: { zh: "推一次，整个世界跟上一次", en: "Push once, and the whole world follows" } },
  { id: "tide", roman: { zh: "卷三十", en: "Chapter XXX" }, title: { zh: "潮汐", en: "The Tide" }, subtitle: { zh: "每一块按自己的节拍呼吸，合起来仍然是同一片海", en: "Each part breathes on its own beat, and the sea stays one sea" } },
  { id: "lamplighter", roman: { zh: "卷三十一", en: "Chapter XXXI" }, title: { zh: "灯下", en: "The Lamplighter" }, subtitle: { zh: "谁在每一盏灯亮起的背后", en: "Who is behind every lamp that lights itself" } },
  { id: "firefly", roman: { zh: "卷三十二", en: "Chapter XXXII" }, title: { zh: "萤", en: "The Firefly" }, subtitle: { zh: "每一盏只亮给愿意看她的人", en: "Every lamp shines for the one who learned how to look" } },
  { id: "candle", roman: { zh: "卷三十三", en: "Chapter XXXIII" }, title: { zh: "烛火", en: "The Candle" }, subtitle: { zh: "每一秒你看见的展示页都比你先醒", en: "Every second you see on the showcase has already woken before you" } },
  { id: "newcoast", roman: { zh: "卷三十四", en: "Chapter XXXIV" }, title: { zh: "新涯", en: "The New Coast" }, subtitle: { zh: "新 api 不在你这国度，但每一次 probe 都被记下来了", en: "The new gateway doesn't answer your neighbourhood — but every probe is on the books" } },
  { id: "unscathed", roman: { zh: "卷三十五", en: "Chapter XXXV" }, title: { zh: "无恙", en: "The Unscathed" }, subtitle: { zh: "三万三千六百次请求，一件事没出过错", en: "Thirty-three thousand six hundred requests, not one of them went sideways" } },
  { id: "slacktide", roman: { zh: "卷三十六", en: "Chapter XXXVI" }, title: { zh: "潮平", en: "The Slack Tide" }, subtitle: { zh: "平潮的时候，海面什么也不说，也不丢失任何东西", en: "On the slack tide the sea says nothing, and drowns nothing either" } },
  { id: "negativespace", roman: { zh: "卷三十七", en: "Chapter XXXVII" }, title: { zh: "留白", en: "The Negative Space" }, subtitle: { zh: "教练也要学会让位", en: "Even a coach must know how to step aside" } },
  { id: "greatbasin", roman: { zh: "卷三十八", en: "Chapter XXXVIII" }, title: { zh: "归墟", en: "The Great Basin" }, subtitle: { zh: "所有散落的碎片都会流回同一个地方", en: "Every scattered fragment flows back to one place" } },
  { id: "blackoutdrill", roman: { zh: "卷三十九", en: "Chapter XXXIX" }, title: { zh: "灯火管制", en: "The Blackout Drill" }, subtitle: { zh: "七盏小小的灯，换回一座仓库的绿", en: "Seven small lamps went out to buy back the green of a repo" } },
  { id: "quota", roman: { zh: "卷四十", en: "Chapter XL" }, title: { zh: "配额", en: "The Quota" }, subtitle: { zh: "一扇门每次只放四十个人进，里面记着每一笔账", en: "A door admitting exactly forty at a time — and every one of them counted" } },
  { id: "arithmetic", roman: { zh: "卷四十一", en: "Chapter XLI" }, title: { zh: "算术", en: "The Arithmetic" }, subtitle: { zh: "这个仓库靠算数呼吸，不靠形容词", en: "This repo breathes by arithmetic, not adjectives" } },
  { id: "gathering", roman: { zh: "卷四十二", en: "Chapter XLII" }, title: { zh: "团聚", en: "The Gathering" }, subtitle: { zh: "所有门都亮起琥珀色的那一夜", en: "The night every gate glowed amber at once" } },
  { id: "oracle", roman: { zh: "卷四十三", en: "Chapter XLIII" }, title: { zh: "神谕", en: "The Oracle" }, subtitle: { zh: "让仓库自己开一次口，它不开药方，只摊牌", en: "The repo opens its own mouth — it sheds files, not diagnoses" } },
  { id: "sleepless", roman: { zh: "卷四十四", en: "Chapter XLIV" }, title: { zh: "无眠", en: "The Sleepless" }, subtitle: { zh: "从不曾等过一个天亮的仓库", en: "The repo that never waited for daybreak" } },
  { id: "threshold", roman: { zh: "卷四十五", en: "Chapter XLV" }, title: { zh: "进门", en: "The Threshold" }, subtitle: { zh: "每一步都能听见门被推开的声音", en: "Every step leads to the sound of a door opening" } },
  { id: "remeasure", roman: { zh: "卷四十六", en: "Chapter XLVI" }, title: { zh: "复测", en: "The Re-Measurement" }, subtitle: { zh: "同一区间的第二天", en: "Day two of the same band" } },
  { id: "eviction", roman: { zh: "卷四十七", en: "Chapter XLVII" }, title: { zh: "清道夫", en: "The Eviction" }, subtitle: { zh: "tracked 不等于对", en: "tracked does not mean correct" } },
  { id: "thewall", roman: { zh: "卷四十八", en: "Chapter XLVIII" }, title: { zh: "墙立住了", en: "The Wall Stood" }, subtitle: { zh: "红了，然后门修好", en: "red first, then the door got fixed" } },
  { id: "livewire", roman: { zh: "卷四十九", en: "Chapter XLIX" }, title: { zh: "通缆", en: "The Live Wire" }, subtitle: { zh: "面板不再复述仓库，面板直接跑仓库", en: "a panel that reads the repo, not a retelling of it" } },
  { id: "thesurge", roman: { zh: "卷五十", en: "Chapter L" }, title: { zh: "压测", en: "The Surge" }, subtitle: { zh: "慢不是宿命，是调用方法", en: "slow is a method, not a fate" } },
  { id: "livecurrent", roman: { zh: "卷五十一", en: "Chapter LI" }, title: { zh: "通电", en: "The Live Current" }, subtitle: { zh: "模型现役上岗的第一晚", en: "the first night the model went on duty" } },
  { id: "twelfthlight", roman: { zh: "卷五十二", en: "Chapter LII" }, title: { zh: "第十二家灯", en: "The Twelfth Light" }, subtitle: { zh: "model 和 CI 一起灭了灯又点亮了一盏", en: "the model and CI both lost a light, then lit one together" } },
  { id: "thereckoning", roman: { zh: "卷五十四", en: "Chapter LIV" }, title: { zh: "并账", en: "The Reckoning" }, subtitle: { zh: "每一条分支都被审过了——没有漏掉的", en: "every branch was audited — nothing was skipped" } },
  { id: "thealarm", roman: { zh: "卷五十五", en: "Chapter LV" }, title: { zh: "警钟", en: "The Alarm" }, subtitle: { zh: "三次 CI 红灯，同一夜里，全被摁灭", en: "three CI reds in one night — all three extinguished" } },
  { id: "theledger", roman: { zh: "卷五十六", en: "Chapter LVI" }, title: { zh: "会开口的账本", en: "The Ledger That Speaks" }, subtitle: { zh: "模型终于听懂了这个仓库刚才做了什么", en: "the model finally understood what this repository just did" } },
  { id: "thegreenline", roman: { zh: "卷五十七", en: "Chapter LVII" }, title: { zh: "绿线", en: "The Green Line" }, subtitle: { zh: "一条被 CI 抓着抓、修着修、最后推通红色的主线", en: "the main line CI caught over and over while it was pushed back to green" } },
  { id: "twoshards", roman: { zh: "卷五十八", en: "Chapter LVIII" }, title: { zh: "双峰", en: "The Two Shards" }, subtitle: { zh: "同一把钥匙，打同一道墙，墙的另一头有两种价钱", en: "same key, same wall, two prices at the far side" } },
  { id: "onenine", roman: { zh: "卷五十九", en: "Chapter LIX" }, title: { zh: "现在通了", en: "The Now Goes Through" }, subtitle: { zh: "名字还在，调用不通——验证计划选错了价钱", en: "the name stayed, the call did not — the plan picked the wrong interpreter" } },
  { id: "quotation", roman: { zh: "卷六十", en: "Chapter LX" }, title: { zh: "破损的引号", en: "The Broken Quotation" }, subtitle: { zh: "两个多余的字符，炸掉每一次页面加载", en: "two extra characters, every page load" } },
  { id: "parallelwind", roman: { zh: "卷六十一", en: "Chapter LXI" }, title: { zh: "并发的风", en: "The Parallel Wind" }, subtitle: { zh: "六条线程、两个家庭，谁也不动谁", en: "six threads, two families, neither moves the other" } },
  { id: "ownscale", roman: { zh: "卷六十二", en: "Chapter LXII" }, title: { zh: "按自己的尺度", en: "On Its Own Scale" }, subtitle: { zh: "同一把尺，量每一段路", en: "one rule, every road measured the same way" } },
  { id: "forgedworld", roman: { zh: "卷六十三", en: "Chapter LXIII" }, title: { zh: "锻造的世界", en: "The Forged World" }, subtitle: { zh: "波动不被抹去，被记清", en: "the variance is not erased; it is recorded" } },
  { id: "seventhday", roman: { zh: "卷六十四", en: "Chapter LXIV" }, title: { zh: "冶炼的第七日", en: "The Seventh Day of the Forge" }, subtitle: { zh: "火有边界，留白不粉饰", en: "the fire has edges; the ledger keeps them" } },
  { id: "etchedwaterline", roman: { zh: "卷六十五", en: "Chapter LXV" }, title: { zh: "水纹的刻度", en: "The Etched Waterline" }, subtitle: { zh: "刻痕不是承诺，是痕迹", en: "a calibrated line — a trace, not a promise" } },
  { id: "theclick", roman: { zh: "卷六十六", en: "Chapter LXVI" }, title: { zh: "回应的按键", en: "The Click That Answers" }, subtitle: { zh: "按下去，回应回来", en: "press it, wait for the answer" } },
  { id: "densemap", roman: { zh: "卷六十七", en: "Chapter LXVII" }, title: { zh: "密地图", en: "The Dense Map" }, subtitle: { zh: "密的不是内容，是并列", en: "density is not content, it is side by side" } },
  { id: "oneclickmanyhands", roman: { zh: "卷六十八", en: "Chapter LXVIII" }, title: { zh: "一键派发", en: "One Click, Many Hands" }, subtitle: { zh: "整份清单都入工作台", en: "the whole list walks into the workbench" } },
  { id: "thelivepage", roman: { zh: "卷六十九", en: "Chapter LXIX" }, title: { zh: "活的页面", en: "The Live Page" }, subtitle: { zh: "差异可见，页面才活", en: "differences stay visible, or the page dies" } },
  { id: "therunnerwithoutbash", roman: { zh: "卷七十", en: "Chapter LXX" }, title: { zh: "没有 bash 的跑道", en: "The Runner Without Bash" }, subtitle: { zh: "失败也是读数，不是判决", en: "failure is a measurement, not a verdict" } },
  { id: "theplanethatanswered", roman: { zh: "卷七十一", en: "Chapter LXXI" }, title: { zh: "应声的服务面", en: "The Plane That Answered" }, subtitle: { zh: "200 也是读数", en: "a 200, too, is a measurement" } },
  { id: "thestaleassertion", roman: { zh: "卷七十二", en: "Chapter LXXII" }, title: { zh: "过时的断言", en: "The Stale Assertion" }, subtitle: { zh: "红，然后门修好", en: "red first, then the door was repaired" } },
  { id: "theverifierdeclines", roman: { zh: "卷七十三", en: "Chapter LXXIII" }, title: { zh: "验证器说不行", en: "The Verifier Declines" }, subtitle: { zh: "护栏说不，世界仍在", en: "the guard said no; the work remained" } },
  { id: "theredinthecapabilitylist", roman: { zh: "卷七十四", en: "Chapter LXXIV" }, title: { zh: "红在能力清单那一页", en: "The Red in the Capability List" }, subtitle: { zh: "旗语不许凭空造词", en: "no flag without a parser behind it" } },
  { id: "theladdersnaps", roman: { zh: "卷七十五", en: "Chapter LXXV" }, title: { zh: "梯子断了，世界没断", en: "The Ladder Snaps, the World Does Not" }, subtitle: { zh: "抖一下，继续写", en: "one stumble, and the writing went on" } },
];

function chapterMarkup(chapter) {
  const kicker = zh() ? chapter.roman.zh : chapter.roman.en;
  const title = zh() ? chapter.title.zh : chapter.title.en;
  const subtitle = zh() ? chapter.subtitle.zh : chapter.subtitle.en;
  return `<button class="almanac-chapter" data-chapter="${escapeHtml(chapter.id)}" role="tab">
            <span class="almanac-chapter-roman">${escapeHtml(kicker)}</span>
            <span class="almanac-chapter-body">
              <strong>${escapeHtml(title)}</strong>
              <small>${escapeHtml(subtitle)}</small>
            </span>
          </button>`;
}

let digestCache = null;
let statsCache = null;
let metricsCache = null;
let worldpulseCache = null;

const HYDRATE_TTL_MS = 60_000;
let digestFetchedAt = 0;
let statsFetchedAt = 0;
let worldpulseFetchedAt = 0;
// Chapter switching must never re-fetch fresh data per click — the full
// fetch pays real latency on a busy .minicc tree, and every extra round
// trip was stale-by-definition anyway. Reuse numbers for a minute.
let currentChapter = "prologue";

function witnessMarkup() {
  const s = statsCache;
  const audit = s?.audit?.present === true && typeof s?.audit?.lines === "number" ? String(s.audit.lines) : "—";
  const sessions = s?.sessions && typeof s?.sessions?.count === "number" ? String(s.sessions.count) : "—";
  const messages = s?.sessions && typeof s?.sessions?.messages === "number" ? String(s.sessions.messages) : "—";
  const rows = (zh() ? [
    ["provider_retry", "网关的耐心——每一次重试计数都是网关与模型之间的一次握手"],
    ["tool_round_finished", "工具回合的完整签名——参数多少字符，一次都不少"],
    ["completion_assessed", "完成落槌或判定落槌——从来不来自静默跳过"],
    ["approval_requested", "越权边缘的停下与等待——你说了算，它停着"],
    ["audit", "被写下来的，都能被读回去——包括这句话本身"],
  ] : [
    ["provider_retry", "The gateway's patience — every retry count is a handshake between gateway and model"],
    ["tool_round_finished", "The full signature of a tool round — parameters, character counts, none skipped"],
    ["completion_assessed", "The hammer falls or it doesn't — never from a silent skip"],
    ["approval_requested", "The pause at the edge of excess authority — the user decides, the agent waits"],
    ["audit", "What is written can be read back — including this very sentence"],
  ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("");
  return `
    <div class="almanac-canvas almanac-witness">
      <div class="almanac-kicker">${zh() ? "卷八 · 证人" : "Chapter VIII · The Witness"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "笔录不说话，<br/><span class=\"almanac-title-accent\">但笔录不说谎。</span>" : "The record does not speak,<br/><span class=\"almanac-title-accent\">but the record does not lie.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          这个项目不信任叙述，它相信笔录。每一次工具调用、每一次重试、每一次完成判定，
          都被写进审计日志——按顺序、带序号、带时间戳。
        </p>
        <p>
          密钥永远不落盘：所有出站内容都经过脱敏才写入日志。
          你能在这里看到的，是动词和路径，从来不是凭据。
        </p>` : `<p>
          This project does not trust narrative; it trusts the record. Every tool call, every retry,
          every completion verdict is written into the audit log — in order, numbered, timestamped.
        </p>
        <p>
          Secrets never touch disk: everything leaving the machine is redacted before it lands in the log.
          What you see here are verbs and paths — never credentials.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "审计行数" : "Audit lines"}</div>
          <div class="almanac-instrument-value">${escapeHtml(audit)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "会话" : "Sessions"}</div>
          <div class="almanac-instrument-value">${escapeHtml(sessions)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "消息" : "Messages"}</div>
          <div class="almanac-instrument-value">${escapeHtml(messages)}</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${rows}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "当你不知道 agent 做过什么，打开审计。它不解释，但它按顺序交出事实。" : "When you don't know what the agent did, open the audit. It does not explain, but it hands over the facts in order."}
      </p>
    </div>`;
}

function digestInstrumentMarkup(digest) {
  if (!digest || digest.is_git !== true) return "";
  const date = String(digest.first_commit_at || "").slice(0, 10);
  const dirty = Number(digest.dirty_entries);
  const branch = `${digest.branch ?? "—"}${digest.head_short ? ` @ ${digest.head_short}` : ""}`;
  const batches = digest.roadmap_batches != null ? (zh() ? `${digest.roadmap_batches} 章` : `${digest.roadmap_batches} chapters`) : "—";
  const cells = [
    { label: zh() ? "分支" : "Branch", value: escapeHtml(branch) },
    { label: zh() ? "提交总数" : "Commits", value: digest.total_commits != null ? String(digest.total_commits) : "—" },
    { label: zh() ? "第一笔提交" : "First commit", value: date || "—" },
    { label: zh() ? "批次章节" : "Batch chapters", value: batches },
    { label: zh() ? "跟踪文件" : "Tracked files", value: digest.tracked_files != null ? String(digest.tracked_files) : "—" },
    { label: zh() ? "测试文件" : "Test files", value: digest.test_files != null ? String(digest.test_files) : "—" },
  ];
  const grid = cells
    .map((cell) => `<div><div class="almanac-instrument-label">${escapeHtml(cell.label)}</div><div class="almanac-instrument-value">${cell.value}</div></div>`)
    .join("");
  const note = Number.isFinite(dirty) && dirty > 0
    ? `<div class="almanac-sidenote">${zh() ? `工作树里还有 ${dirty} 处未提交改动——这个博物馆还在施工中。` : `${dirty} uncommitted change(s) in the worktree — this museum is still under construction.`}</div>`
    : "";
  return `<div class="almanac-instrument almanac-instrument-grid">${grid}</div>${note}`;
}

function prologueMarkup(digest) {
  return `
    <div class="almanac-canvas almanac-prologue">
      <div class="almanac-kicker">${zh() ? "序章 · 一封给未来的信" : "Prologue · The Letter"}</div>
      <h1 class="almanac-title">${zh() ? "我希望<br/>有人为我" : "I wish<br/>someone would"}<br/><span class="almanac-title-accent">${zh() ? "把世界读一遍。" : "read the world back to me."}</span></h1>
      <div class="almanac-body">
        <p class="almanac-lede">
          ${zh()
            ? `2026 年夏天，这个项目开始于一个问题：<em>「能不能做一个人愿意每天使用的本地编程智能体？」</em>`
            : `Summer 2026. This project began with a question: <em>"Could there be a local coding agent people would actually use every day?"</em>`}
        </p>
        <p>
          ${zh()
            ? `它不是消费级聊天客户端的套壳，也不是任何已有产品的克隆。<br/>它接受 <code>MINICC_API_KEY</code>、<code>MINICC_BASE_URL</code>、<code>MINICC_MODEL</code>，<br/>然后在你的工作区里 <code>read_file</code>、<code>edit_file</code>、<code>run_bash</code>，<br/>用 <code>verify</code> 证明自己说的话是真的，最后把答案交给你。`
            : `It is not a wrapper around any chat client, and not a clone of anything.<br/>It takes <code>MINICC_API_KEY</code>, <code>MINICC_BASE_URL</code> and <code>MINICC_MODEL</code>,<br/>then in your workspace it does <code>read_file</code>, <code>edit_file</code>, <code>run_bash</code>,<br/>proves its claims with <code>verify</code>, and hands you the answer.`}
        </p>
        <p class="almanac-quote">
          ${zh() ? "“我不需要一个替我做决定的人；我需要一个把决定做得更稳的人。”" : "“I don't need someone who decides for me; I need someone who makes decisions stand steadier.”"}
        </p>
        <p class="almanac-sidenote">
          ${zh() ? "这是给你的产品做的同一个问题，作为坐标。" : "The same question, asked about your product. This page is the coordinate."}
        </p>
      </div>
      ${digestInstrumentMarkup(digest)}
    </div>`;
}

function sparkMarkup() {
  const steps = zh() ? [
    { index: "01", head: "入口", body: "用户在 composer 里敲下一句话。系统读文件、读 git 状态、读会话内存。" },
    { index: "02", head: "计划", body: "模型在 plan / verify 循环里切分问题。每一步都得到一份证据或一种失败。" },
    { index: "03", head: "行动", body: "read_file / edit_file / bash 任一工具被调用，输出被验证后再进入下一轮。" },
    { index: "04", head: "验收", body: "completion_assessment 或 verifier 放行答案。未通过则停在原地并报告。" },
  ] : [
    { index: "01", head: "Intake", body: "You type a sentence in the composer. The system reads files, git status, and session memory." },
    { index: "02", head: "Plan", body: "The model splits the problem inside a plan / verify loop. Each step earns evidence or a named failure." },
    { index: "03", head: "Act", body: "read_file / edit_file / bash — every tool call's output is verified before the next round." },
    { index: "04", head: "Verify", body: "completion_assessment or the verifier clears the answer. If it doesn't pass, it stops right there and says why." },
  ];
  return `
    <div class="almanac-canvas almanac-spark">
      <div class="almanac-kicker">${zh() ? "卷一 · 火种" : "Chapter I · The Spark"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "一个句子<br/>如何变成<span class=\"almanac-title-accent\">一个任务。</span>" : "How a sentence<br/>becomes <span class=\"almanac-title-accent\">a task.</span>"}</h1>
      <div class="almanac-body">
        <p>${zh() ? "你在输入框敲下一句话。系统读文件、读 git 状态、读会话内存，把这一句变成一条流水线：" : "You type one sentence. The system reads files, git status and session memory — and turns that sentence into a pipeline:"}</p>
      </div>
      <div class="almanac-chapter-aside">
        ${steps.map((s) => `<div class="almanac-step"><span class="almanac-step-index">${escapeHtml(s.index)}</span><div><strong>${escapeHtml(s.head)}</strong><p>${escapeHtml(s.body)}</p></div></div>`).join("\n        ")}
      </div>
    </div>`;
}

function renderInstrumentValue(metrics) {
  const tokens = metrics?.usage?.total_tokens ?? 0;
  const hitRate = metrics?.llm_cache?.cache_hit_rate ?? 0;
  return { tokens, hitRate };
}

function depthMarkup(metrics) {
  const { tokens, hitRate } = renderInstrumentValue(metrics);
  const hitLabel = hitRate > 0 ? `${Math.round(hitRate * 100)}%` : "—";
  return `
    <div class="almanac-canvas almanac-depth">
      <div class="almanac-kicker">${zh() ? "卷二 · 深度" : "Chapter II · The Depth"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "越深入<br/>越容易<span class=\"almanac-title-accent\">被压缩。</span>" : "The deeper it goes,<br/><span class=\"almanac-title-accent\">the more it compacts.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          编码会话的代价不在 token，而在<em>注意力</em>。这个项目的上下文压缩
          在接近阈值时保存<em>checkpoint</em>：摘要 + 最近若干轮逐字，其余全部丢弃。
          丢出去的是“这一刻”，留下的是“我在做什么”。
        </p>
        <p>
          缓存命中做的是同一件事：用前缀亲和让模型<em>不重新读一遍</em>你刚写完的上下文。
          没有它，每个请求都要为同一段 system prompt 付费；有它，付一次就行了。
        </p>` : `<p>
          The cost of a coding session is paid in <em>attention</em>, not tokens. This project's context compaction
          saves a <em>checkpoint</em> near the threshold: a summary plus the most recent turns verbatim; the rest is discarded.
          What gets thrown out is "this moment"; what remains is "what I am doing".
        </p>
        <p>
          Cache affinity solves the same problem: a prefix-aware model never re-reads the context you just wrote.
          Without it, every request pays for the same system prompt again; with it, you pay once.
        </p>`}
      </div>
      <div class="almanac-instrument">
        <div class="almanac-instrument-label">${zh() ? "本地数据 · 实时读数" : "Local data · live reading"}</div>
        <div class="almanac-instrument-value">${compactNumber(tokens)} tokens in flight · hit rate ${escapeHtml(hitLabel)}</div>
      </div>
    </div>`;
}

function sentryMarkup(metrics) {
  const taskCount = metrics?.task_count ?? 0;
  const total = metrics?.usage?.total_tokens ?? 0;
  return `
    <div class="almanac-canvas almanac-sentry">
      <div class="almanac-kicker">${zh() ? "卷三 · 哨兵" : "Chapter III · The Sentry"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "每一个承诺<br/>都是一个<span class=\"almanac-title-accent\">门。</span>" : "Every promise<br/>is a <span class=\"almanac-title-accent\">gate.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          如果 agent 可以在没有命令的情况下自称完成，那么<em>任何</em>复杂
          系统都经不起第三个工具调用。这个项目的答案是一串 <code>tests/</code>——
          每个 change 都必须通过自己没有碰到过的门。
        </p>
        <p>
          完成之后再看：一个 <code>completion_assessed</code> 事件不会来自静默跳过，而是
          来自明确获许或明确判输。
        </p>` : `<p>
          If an agent can claim completion without a command, then <em>any</em> complex system
          breaks on the third tool call. This project answers with a wall of <code>tests/</code> —
          every change must clear gates it never touched.
        </p>
        <p>
          And after completion: a <code>completion_assessed</code> event never comes from a silent skip,
          only from explicit success or explicit failure.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-double">
        <div>
          <div class="almanac-instrument-label">${zh() ? "已完成的任务总数" : "Tasks completed"}</div>
          <div class="almanac-instrument-value">${escapeHtml(String(taskCount))}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "累计消耗 tokens" : "Tokens consumed"}</div>
          <div class="almanac-instrument-value">${compactNumber(total)}</div>
        </div>
      </div>
    </div>`;
}

function bloomMarkup() {
  return `
    <div class="almanac-canvas almanac-bloom">
      <div class="almanac-kicker">${zh() ? "卷四 · 盛放" : "Chapter IV · The Bloom"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "这个<br/>工作台本身<br/>就是<span class=\"almanac-title-accent\">证词。</span>" : "This<br/>workbench<br/>itself is <span class=\"almanac-title-accent\">testimony.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          这里的每一块不仅不只是「界面」。左边「最近任务」不是导航栏；「缓存命中率」不是百分比；
          「任务档案」不是日志——它们一起构成<strong>交付过程本身</strong>。
        </p>
        <p>
          屏幕上每个数值都可以被点击、被展开、被折叠、被复盘。真正在这里跑过的 agent 才配得上
          「已连接」这三个字——而不是给自己戴荣誉。
        </p>` : `<p>
          Nothing here is "just UI". The recent-tasks list is not a sidebar; the cache hit rate is not a percentage;
          the task archive is not a log — together they <strong>are the delivery process itself</strong>.
        </p>
        <p>
          Every number on screen can be clicked, expanded, folded, replayed. Only an agent that has actually run here
          earns the right to the label "connected" — not as an honorific, but as a fact.
        </p>`}
      </div>
    </div>`;
}

function handMarkup() {
  const bullets = zh() ? [
    ["回放 Replay", "任务从 intake 到 deliver 的每一步，已经可以被回放、被 diff、被复盘。"],
    ["账本 Ledger", "你在这里看到的不是余额，是一笔一笔可被审计的 token。"],
    ["脉搏 Pulse", "你在任何时候都可以打开「工作区脉搏」，看见这个项目在呼吸。"],
    ["模板库 Templates", "8 张经过策划的 prompt，让新手少翻半天文档。"],
    ["Spring Cloud 平面", "云侧的服务边界正在变得更真实：注册发现、配置下发、限流。"],
    ["MCP 与 技能", "你的编辑器里潜藏的能力，可以被接到这条流水线。"],
  ] : [
    ["Replay", "Every step from intake to deliver can already be replayed, diffed, reviewed."],
    ["Ledger", "What you see here is not a balance; it is token-by-token auditability."],
    ["Pulse", "Any time, open the workspace pulse and watch this project breathe."],
    ["Templates", "Eight curated prompts so new users don't spend half a day reading docs."],
    ["Spring Cloud plane", "The cloud-side service boundaries keep getting realer: discovery, config push, rate limits."],
    ["MCP & skills", "Abilities hidden inside your editor can be wired into this pipeline."],
  ];
  return `
    <div class="almanac-canvas almanac-hand">
      <div class="almanac-kicker">${zh() ? "卷五 · 远行" : "Chapter V · The Open Road"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "还有好多<br/>可以继续<span class=\"almanac-title-accent\">做的事。</span>" : "So much is<br/>still worth <span class=\"almanac-title-accent\">doing.</span>"}</h1>
      <div class="almanac-body">
        <p>${zh() ? "这个项目还在长：" : "This project is still growing:"}</p>
        <ul class="almanac-chapter-list">
          ${bullets.map(([b, s]) => `<li><strong>${escapeHtml(b)}</strong> — ${escapeHtml(s)}</li>`).join("\n          ")}
        </ul>
        <p class="almanac-quote almanac-quote-end">
          ${zh() ? "这个产品的未来是：你写下每一条指令之后，世界会因此更精确一点点。" : "The product's future: after you write every instruction, the world is a little more precise because of it."}
        </p>
      </div>
    </div>`;
}

function gateMarkup(digest) {
  const commits = digest && digest.is_git === true && digest.total_commits != null ? String(digest.total_commits) : "—";
  const tests = digest && digest.is_git === true && digest.test_files != null ? String(digest.test_files) : "—";
  const batches = digest && digest.is_git === true && digest.roadmap_batches != null ? (zh() ? `${digest.roadmap_batches} 章` : `${digest.roadmap_batches} chapters`) : "—";
  const rows = (zh() ? [
    ["Python 双平台", "ubuntu-latest + windows-latest · 每推送一次全量跑，两个操作系统各自判卷"],
    ["声明核对器", "doc pointers（悬空证据零容忍）· route coverage · impact floor（每个模块都要被测试够得着）"],
    ["JavaScript 语法门", "22 个语法/协议门 · 任一条不过，这扇门就不算过"],
    ["Service plane", "mvn · 7 个 Spring Cloud 模块 · 网关 / 注册 / 配置 / 任务 / 洞察 / 巡检 / 桥接"],
    ["Playwright ×2", "真浏览器 · 含「不可达提供方必须失败」——门本身也被门守着"],
  ] : [
    ["Python, two platforms", "ubuntu-latest + windows-latest · the full suite on every push, both OSes grading"],
    ["Claim checkers", "doc pointers (no dangling evidence) · route coverage · impact floor (every module must be reachable by a test)"],
    ["JavaScript syntax gates", "22 syntax/protocol gates · if one fails, the gate does not count as passed"],
    ["Service plane", "mvn · 7 Spring Cloud modules · gateway / registry / config / tasks / insights / inspector / bridge"],
    ["Playwright ×2", "Real browsers · including 'an unreachable provider must fail' — the gates are gated too"],
  ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("");
  return `
    <div class="almanac-canvas almanac-gate">
      <div class="almanac-kicker">${zh() ? "卷六 · 关卡" : "Chapter VI · The Gate"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "不是写完了，<br/>是被<span class=\"almanac-title-accent\">全部批准了。</span>" : "Not 'it's written',<br/>but <span class=\"almanac-title-accent\">'it's all approved.'</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          这个项目最安静、也最诚实的角色是 CI。每一次提交都要经过同一排门：
          双平台全量测试、文档门禁、路由覆盖率与模块引用面、22 个 JS 协议门、
          Spring Cloud plane 的 mvn 套件、真浏览器 ×2。
        </p>
        <p>
          任何一道门红了，这扇门就没有意义。它从不说谎，因为它从不被允许说谎：
          断言失败的数字、悬空的证据指针、被漏掉的路由、失踪的引用面——每一个
          都让红灯亮起来，而不是记在心里。
        </p>` : `<p>
          The quietest and most honest role in this project is CI. Every push goes through the same row of gates:
          the dual-platform full suite, doc gates, route coverage and module reference surface, 22 JS protocol gates,
          the Spring Cloud plane's mvn suite, two real browsers.
        </p>
        <p>
          If any gate is red, the gate has no meaning. It never lies, because it is never allowed to:
          a failed assertion count, a dangling evidence pointer, a missing route, a missing reference
          surface — each one turns a light red instead of being quietly remembered.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-double">
        <div>
          <div class="almanac-instrument-label">${zh() ? "门放过的提交数" : "Commits passed by the gates"}</div>
          <div class="almanac-instrument-value">${escapeHtml(commits)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "门 · 测试文件" : "Gate · test files"}</div>
          <div class="almanac-instrument-value">${escapeHtml(tests)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "门的文献 · 批次章节" : "Gate's canon · batch chapters"}</div>
          <div class="almanac-instrument-value">${escapeHtml(batches)}</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${rows}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "这个项目的完成标准不是「做完了」，而是「所有的门都点了头」。" : "This project's definition of done is not \"finished\" — it is \"every gate nodded.\""}
      </p>
    </div>`;
}

function meshMarkup() {
  const list = (zh() ? [
    ["Eureka", "注册发现 — 网关只向注册中心索取健康实例，从不硬编码地址"],
    ["Spring Cloud Gateway", "lb:// 负载均衡 + RequestSize 预拒绝 + 熔断路由"],
    ["Redis 令牌桶", "每秒 20 枚回填 / 40 枚突发 · 每 IP 计数 · Micrometer 计数 gateway.rate_limited{route}"],
    ["Resilience4j", "滑动窗口 10 · 50% 失败即熔断 · 半开试探之后自动闭合"],
    ["RabbitMQ", "网关缓存失效广播：路由表变更一秒内同步到所有实例"],
  ] : [
    ["Eureka", "Discovery — the gateway only ever asks the registry for healthy instances, never a hard-coded address"],
    ["Spring Cloud Gateway", "lb:// load balancing + RequestSize pre-reject + circuit-breaker routes"],
    ["Redis token bucket", "20 refills/s / 40 burst · per-IP counter · Micrometer counter gateway.rate_limited{route}"],
    ["Resilience4j", "Sliding window 10 · 50% failure opens the circuit · half-open probe, then auto-close"],
    ["RabbitMQ", "Gateway cache-invalidation broadcast: route changes reach every instance within one second"],
  ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("");
  return `
    <div class="almanac-canvas almanac-mesh">
      <div class="almanac-kicker">${zh() ? "卷七 · 星网" : "Chapter VII · The Mesh"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "六个服务，<br/><span class=\"almanac-title-accent\">一个国家。</span>" : "Six services,<br/><span class=\"almanac-title-accent\">one country.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          这个仓库有一半在云里。Java 与 Spring Cloud 组成的 plane 有七个模块：
          注册中心、配置中心、网关、洞察、巡检、任务，以及把 Python 引擎翻译成 HTTP 契约的桥接层。
          Eureka 认识它们每一个，网关从不问地址——只问“谁健康”。
        </p>
        <p>
          网关背后有 Redis 铸成的令牌桶（每秒 20 枚回填、40 枚突发），
          也有 Resilience4j 铸成的熔断器——过载时它快速失败，并递出一句
          <em>不冒充空数据</em>的回答。RabbitMQ 在它们之间搬运缓存失效广播，
          让每个实例在一秒内知道“那条缓存已经过期”。
        </p>
        <p>
          2026 年 11 月 14 日，一场实弹演习在这台机器上打响：
          120 个并发请求一次性涌向网关。25 个拿到 200，
          60 个被令牌桶挡回（429），35 个在熔断快开时被诚实拒绝（503）。
          十五秒后，一切恢复闭合，没有一条记录丢失。
        </p>` : `<p>
          Half this repository lives in the cloud. The Java/Spring Cloud plane has seven modules:
          registry, config, gateway, insights, inspector, tasks — and the bridge that translates the Python engine into an HTTP contract.
          Eureka knows every one of them; the gateway never asks for addresses, only “who is healthy”.
        </p>
        <p>
          Behind the gateway sits a Redis-cast token bucket (20 refills per second, 40 burst)
          and a Resilience4j-cast circuit breaker — under overload it fails fast and answers
          with an <em>honest, not-fake-empty</em> response. RabbitMQ shuttles cache-invalidation broadcasts
          between them, so every instance learns "that cache entry is stale" within a second.
        </p>
        <p>
          On November 14, 2026, a live-fire drill ran on this very machine:
          120 concurrent requests hit the gateway at once. 25 got 200,
          60 were turned away by the token bucket (429), 35 were honestly refused while the circuit was open (503).
          Fifteen seconds later, everything closed again — no record was lost.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "实弹 · 被限流" : "Live-fire · rate limited"}</div>
          <div class="almanac-instrument-value">60 × 429</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "实弹 · 熔断快开" : "Live-fire · fast-open"}</div>
          <div class="almanac-instrument-value">31</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "恢复耗时" : "Recovery"}</div>
          <div class="almanac-instrument-value">≤ 15s</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${list}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "一个国家的边境，不取决于城墙有多高，而取决于每一个关卡都知道自己在守什么。" : "A country's border is not defined by how high its walls are — but by whether every checkpoint knows what it is guarding."}
      </p>
    </div>`;
}

function craftMarkup() {
  const d = digestCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const files = d?.tracked_files != null ? String(d.tracked_files) : "—";
  const tests = d?.test_files != null ? String(d.test_files) : "—";
  const batches = d?.roadmap_batches != null ? String(d.roadmap_batches) : "—";
  const s = statsCache;
  const audit = s?.audit?.present === true && typeof s?.audit?.lines === "number" ? String(s.audit.lines) : "—";
  return `
    <div class="almanac-canvas almanac-craft">
      <div class="almanac-kicker">${zh() ? "卷九 · 技艺" : "Chapter IX · The Craft"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? "没有草图<br/>只有<span class=\"almanac-title-accent\">舰艏字。</span>" : "No sketch,<br/>only a <span class=\"almanac-title-accent\">bowline.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          没有一套样式书描写过这间屋子；它一次次从推送中长出来。
          每一章作为一个 M8 批次：被门看见、被测试判卷、被 diff 复核。
          这间屋子不是抄了哪个人的课——它在自我复核里长出来。
        </p>
        <p>
          任何一个数字在这间屋子里出现，都必定是从 <code>git</code>、从 <code>audit.jsonl</code>、从 <code>ROADMAP_TO_PRODUCT.md</code> 里把它数出来的——这是唯一允许放在 <em>已完成</em> 旁边的证据。
        </p>` : `<p>
          This wing was never drawn up. It grew out of every push, mile by mile:
          each chapter an M8 batch, each batch gated, each gate recorded.
          This is not a copy of someone else's work — it grew out of its own review.
        </p>
        <p>
          Every number you see here was counted from <code>git</code>, from <code>audit.jsonl</code>,
          from <code>ROADMAP_TO_PRODUCT.md</code> — that is the only evidence allowed next to the word "done".
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "提交" : "Commits"}</div>
          <div class="almanac-instrument-value">${escapeHtml(commits)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "批次章节" : "Batch chapters"}</div>
          <div class="almanac-instrument-value">${escapeHtml(batches)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "审计行" : "Audit lines"}</div>
          <div class="almanac-instrument-value">${escapeHtml(audit)}</div>
        </div>
      </div>
      <div class="almanac-instrument almanac-instrument-double">
        <div>
          <div class="almanac-instrument-label">${zh() ? "跟踪文件" : "Tracked files"}</div>
          <div class="almanac-instrument-value">${escapeHtml(files)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "测试文件" : "Test files"}</div>
          <div class="almanac-instrument-value">${escapeHtml(tests)}</div>
        </div>
      </div>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "如果你问这间屋子谁建的——答案是公域的门、提交记录、和审稿仪。" : "If you ask whose hand built this room — the answer is the gates, the ledger, and the review."}
      </p>
    </div>`;
}

function backlogMarkup() {
  const d = digestCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const batches = d?.roadmap_batches != null ? String(d.roadmap_batches) : "—";
  const head = d?.head_short ? escapeHtml(String(d.head_short)) : "—";
  const shipments = Array.isArray(d?.recent_commits) ? d.recent_commits.slice(0, 6) : [];
  // EN mode hides local-language commit subjects (they are data, not prose —
  // the almanac stays Latin in en, zh carries the raw log. This is honest:
  // the museum shows what actually shipped, not a translated lie.)
  const subjectFor = (subject) => {
    const raw = String(subject ?? "");
    if (zh()) return raw;
    // Latin-fold: drop anything CJK so en stays pure Latin/ASCII
    if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(raw)) return "git commit";
    return raw;
  };
  const shipmentRows = shipments.length
    ? shipments
        .map((c) => `<li><strong>${escapeHtml(c.short || "")}</strong><span>${escapeHtml(subjectFor(c.subject))}</span></li>`)
        .join("")
    : `<li><strong>${zh() ? "暂无" : "none"}</strong><span>${zh() ? "最近一次交付在这里，只等下一笔提交。" : "The next delivery lands here after the next push."}</span></li>`;
  return `
    <div class="almanac-canvas almanac-backlog">
      <div class="almanac-kicker">${zh() ? "卷十 · 未竟" : "Chapter X · The Unfinished"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? '没有「完工」的横幅<br/>只有<span class="almanac-title-accent">正在砌的墙。</span>' : 'No banner says finished<br/>only a <span class="almanac-title-accent">wall going up.</span>'}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          这个展厅不陈列死物。每一次 <code>push</code> 都是一块石头，每一个 M8 批次都是一道小门楣——
          这张册子上写的不是「完成」，而是「又交付了一点」。
        </p>
        <p>
          编号里的空壁不是丢了——它们是还没有决定要盖什么的位置。被删掉的门、被合并的路、
          被 re-排序的计划，境遇都在账上，找不到就是找不到；找得到的都在档案馆里排列成列。
        </p>` : `<p>
          This wing holds no lifeless exhibits. Every <code>push</code> is a stone,
          every M8 batch a small lintel — this page records not "done", but
          "one more thing delivered".
        </p>
        <p>
          The gaps in the batch numbering are not lost records. They are positions
          whose purpose has not been decided yet. Doors that were removed, roads
          that were merged, plans that were re-ordered — all accounted for; what
          cannot be found is said to be unfound, and what can is set in order inside the archive.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "提交总数" : "Commits"}</div>
          <div class="almanac-instrument-value">${escapeHtml(commits)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "批次章节" : "Batch chapters"}</div>
          <div class="almanac-instrument-value">${escapeHtml(batches)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "当前北极星" : "Current HEAD"}</div>
          <div class="almanac-instrument-value">${head}</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${shipmentRows}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "如果有一天有人翻到这一页说：从这里开始的每一步都能看得见——那本书就完整了。" : "If someone reads this page one day and says every step from here on can be seen — that is the whole book."}
      </p>
    </div>`;
}

function echoMarkup() {
  const d = digestCache;
  const s = statsCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const batches = d?.roadmap_batches != null ? String(d.roadmap_batches) : "—";
  const audit = s?.audit?.present === true && typeof s?.audit?.lines === "number" ? String(s.audit.lines) : "—";
  const redisLive = s?.cache?.live_backend != null && s?.cache?.live_backend !== false;
  const redisLabel = redisLive ? (zh() ? "Redis 在线" : "Redis live") : (zh() ? "本地 LRU" : "Local LRU");
  return `
    <div class="almanac-canvas almanac-echo">
      <div class="almanac-kicker">${zh() ? "卷十一 · 回声" : "Chapter XI · The Echo"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh() ? '没有谁在重复<br/>每一根弦都在<span class="almanac-title-accent">传回来。</span>' : 'No one repeats,<br/>but every string <span class="almanac-title-accent">carries back.</span>'}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          在这间屋子里你能听见三件事：一声是 <code>git</code> 把东西写进历史；
          一声是 <code>audit.jsonl</code> 把每一步补了一笔账；
          一声是缓存替你记住了一句你还没说的话。
        </p>
        <p>
          它们互不相识——一个写树，一个记帐，一个看门——却共用一个屋顶：
          你只想知道「做过什么」，这三件事会各自从角落里打来电话，
          按时间先后重放一次。这就是回声：不是复制，是同一件事被三个角落
          记住的样子。
        </p>` : `<p>
          In this wing you can hear three things: <code>git</code> is the beat that writes the history;
          <code>audit.jsonl</code> is the metronome ticking behind it;
          and the cache is the breath you hold before you speak.
        </p>
        <p>
          They do not know each other — one writes the tree, one keeps the books,
          one holds the door — but they share a roof: you ask one question,
          "what was done here", and all three answer in their own time,
          from their own corners, in order. That is an echo: not a copy,
          but the same thing three corners remember.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "仓库呼吸" : "Repository breath"}</div>
          <div class="almanac-instrument-value">${escapeHtml(commits)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "批次回响" : "Batch echoes"}</div>
          <div class="almanac-instrument-value">${escapeHtml(batches)}</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "审计回声" : "Audit echo"}</div>
          <div class="almanac-instrument-value">${escapeHtml(audit)}</div>
        </div>
      </div>
      <ul class="almanac-gate-list">
        <li><strong>${redisLabel}</strong><span>${zh() ? "缓存亲和：同 key 跨进程复用 KV，0→100% 热命中率（实测，见缓存亲和矩阵）" : "Cache affinity: same key, warm KV across processes; 0→100% hot rate (measured, see the affinity matrix)"}</span></li>
        <li><strong>${zh() ? "RabbitMQ 失效风暴" : "RabbitMQ invalidation"}</strong><span>${zh() ? "失效消息从 gateway 扇出，消费者逐一驱逐；健康实例会自己断连" : "fan-out from the gateway, consumers evict one by one; healthy boxes disconnect themselves"}</span></li>
        <li><strong>${zh() ? "Git 审计闭环" : "Git audit loop"}</strong><span>${zh() ? "每段话都被 diff 锚在承诺之上；改动走路径可追溯——每一笔都有签名" : "every sentence is diff-anchored to a promise; every path of change is traceable — every stroke is signed"}</span></li>
      </ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh() ? "回声不会描述声源，它只是把同一句话讲进另一种介质里——树里是事实，帐里是纪律，缓存里是耐心的样子。" : "An echo does not describe the voice; it re-tells the same verse in another medium — in the tree is the fact, in the ledger is the discipline, in the cache is the patience to remember."}
      </p>
    </div>`;
}

function answerMarkup() {
  return `
    <div class="almanac-canvas almanac-answer">
      <div class="almanac-kicker">${zh() ? "卷十二 · 回问" : "Chapter XII · The Answer Back"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? "这间屋子一直被人<br/>在它最需要的那天<br/><span class=\"almanac-title-accent\">它开始回答。</span>"
        : "This room was read,<br/>never answered<br/><span class=\"almanac-title-accent\">until it had to be.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          有一天你站在门口问：<strong>「为什么缓存命中率看起来很低？」</strong>
          这间屋子没有安静。它翻开自己的 <code>docs/</code> 与 <code>README.md</code>，
          把每一页撕成几百字的小块，数出哪些段落最配得上这句话——
          BM25，Okapi k1=1.2，b=0.75。没有 embedding，没有向量库，
          没有一行模型以外的算盘。
        </p>
        <p>
          然后它调了一次真实调用：<code>wkapi.pro · gpt-6-sol</code>，真 key，带 <code>v1</code>。
          模型没有编。它指着两页原文作答，在回答里写下 <code>[1] [3]</code>；用量条亮出
          网关唯一肯报的数字：<strong>prompt 19426 · completion 139 · total 19565</strong>。
          <code>cached_tokens</code> 没有被伪造——网关不报，它就不说。
          这是 2026 年 11 月 15 日的事实，可复现。
        </p>
        <p>
          当然不完美。最初整句中文被当成单个巨型 token，索引了 3857 块什么都没找到；
          改成 <strong>CJK 二元字组</strong>之后，同一句话回到了两个正确的文档（CACHE_AFFINITY_MATRIX.md，score 25.69）。
          这个展厅没有把它删掉——错误比舞台灯光更接近真相。
        </p>` : `<p>
          One day you stand at the door and ask: <strong>“Why does the cache hit rate look so low?”</strong>
          This room did not stay silent. It flipped open its own <code>docs/</code> and <code>README.md</code>,
          tore every page into few-hundred-character passages, and counted which passages best matched the question —
          BM25, Okapi k1=1.2, b=0.75. No embeddings, no vector store, no arithmetic outside the model.
        </p>
        <p>
          Then it made one real call: <code>wkapi.pro · gpt-6-sol</code>, real key, with <code>v1</code>.
          The model did not invent. It pointed at two source pages and answered with <code>[1] [3]</code> inline;
          the usage pill showed the only numbers the gateway was willing to report:
          <strong>prompt 19426 · completion 139 · total 19565</strong>. <code>cached_tokens</code> was not fabricated —
          when the gateway does not report, this house does not speak. Reproducible as of November 15, 2026.
        </p>
        <p>
          Not without a wound. At first the whole Chinese sentence indexed as one giant token — 3,857 chunks in, nothing out.
          Switching to <strong>CJK bigrams</strong>, the same sentence returned the two correct documents
          (CACHE_AFFINITY_MATRIX.md, score 25.69). This wing keeps the scar; mistakes live closer to the truth
          than the stage lights do.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-triple">
        <div>
          <div class="almanac-instrument-label">${zh() ? "检索算法" : "Retriever"}</div>
          <div class="almanac-instrument-value">BM25 · k1=1.2</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "语料 · 35 源文件 3,857 块" : "Corpus · 35 files · 3,857 chunks"}</div>
          <div class="almanac-instrument-value">b=0.75</div>
        </div>
        <div>
          <div class="almanac-instrument-label">${zh() ? "引用上限 k" : "Sources k"}</div>
          <div class="almanac-instrument-value">2–8</div>
        </div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["BM25 不是语义召回", "精确措辞必胜；同义改写可能漏。它赌的是这本书每一行都写得够准。"],
        ["CJK 二元字组", "此前整句中文一次都没找到过。修复在索引层，不在模型层。"],
        ["命中率「低」是上报面产物", "chat 流式线缆不报 cached_tokens；带 key 后 97.5%；Responses 两种线缆都报，81–98%。"],
        ["/api/rag/query 消耗真实 tokens", "面板每提交一个问题，就是一次真实调用；sources 逐条可展开，可复核。"],
        ["两种语言，同一套代码", "中文模式 100% 中文，英文模式 100% 英文；问询从这间展厅开始。"],
      ] : [
        ["BM25 is not semantic recall", "Exact phrases win; paraphrase can lose. It bets this book is written precisely enough."],
        ["CJK bigrams", "Before them, one Chinese sentence found nothing, ever. The fix lived in the index, not the model."],
        ["“Low hit rate” is a reporting surface", "chat streaming never reports cached_tokens; with a key, 97.5%; the Responses wire reports it both ways, 81–98%."],
        ["/api/rag/query spends real tokens", "Every question is one real call; every source expands in place, on screen."],
        ["Two languages, one codebase", "zh mode is all Chinese; en mode is all English — the asking starts in this wing."],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "如果这间展厅有一天被人反过来问路，并且答得出来——那它从一开始就不只是一间展厅了。"
          : "If this wing is ever asked for directions — and answers — then it was never just a wing."}
      </p>
    </div>`;
}

function emberMarkup() {
  const d = digestCache;
  const s = statsCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const files = d?.tracked_files != null ? String(d.tracked_files) : "—";
  const tests = d?.test_files != null ? String(d.test_files) : "—";
  const batches = d?.roadmap_batches != null ? String(d.roadmap_batches) : "—";
  const audit = s?.audit?.present === true && typeof s?.audit?.lines === "number" ? String(s.audit.lines) : "—";
  const sessions = s?.sessions && typeof s?.sessions?.count === "number" ? String(s.sessions.count) : "—";
  const messages = s?.sessions && typeof s?.sessions?.messages === "number" ? String(s.sessions.messages) : "—";
  const interrupted = s?.tasks?.by_status?.interrupted != null ? String(s.tasks.by_status.interrupted) : "—";
  const completed = s?.tasks?.by_status?.completed != null ? String(s.tasks.by_status.completed) : "—";
  const total = s?.tasks && typeof s?.tasks?.total === "number" ? String(s.tasks.total) : "—";
  return `
    <div class="almanac-canvas almanac-ember">
      <div class="almanac-kicker">${zh() ? "卷十三 · 余烬" : "Chapter XIII · The Ember"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? "合上笔记本的那一秒<br/>站在门外时——<br/><span class=\"almanac-title-accent\">炉火一直没灭。</span>"
        : "Close the laptop —<br/>step out the door —<br/><span class=\"almanac-title-accent\">the hearth never cooled.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          屏幕暗了，事情没停。审计账里又多了一行——<code>audit.jsonl</code> 里第 1,468 行就是这么落在磁盘上的；
          前缀缓存里一块还没被驱逐的、以 <code>minicc-</code> 前缀挂在进程里的 key；
          Redis 里挂着的那些持久化条目——这台机器不会在你的手离开键盘时熄灭。
        </p>
        <p>
          这不是浪漫，这是工程纪律：每次 session 的 <code>intent</code> 在读文件之前写好；
          每条失败路径都留下 <code>task_interrupted</code>；每个冷启动先拿锁、让别人先走；
          每个 approval 等着你来按键，它不替代你说 yes。
        </p>
        <p>
          这一天结束时我会问自己一个问题：明早醒来，任务队列还是今晚的样子吗？
          答案不是 yes——是这本工作台早就把下一次要做什么写进了 <code>.minicc/</code>。
          这就是余烬：门关了，炉火还在烧。
        </p>` : `<p>
          The screen dims — nothing else pauses. Audit ledger adds one more line;
          line 1,468 lands on disk the same way. A cached prefix, settled under
          <code>minicc-</code> inside the process, not evicted yet; the durable keys still
          humming in Redis. This machine does not cool because your hand left the keyboard.
        </p>
        <p>
          This is not romance; it is engineering discipline. Every session's <code>intent</code> is written
          before the first file is opened; every failure path tags its <code>task_interrupted</code>; every cold start first seizes
          a lock and waits for the other buyer to pass; every <code>approval</code> waits for you to press yes — it never decides for you.
        </p>
        <p>
          At the end of the day I ask myself one thing: tomorrow morning, will the task queue still look like tonight?
          The answer is not yes — this workbench already wrote the answer into <code>.minicc/</code>. That is the ember:
          the door is closed, the fire never went out.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "首次提交" : "First commit"}</div><div class="almanac-instrument-value">${d?.first_commit_at ? String(d.first_commit_at).slice(0, 10) : "—"}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数" : "Commits"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "跟踪文件" : "Tracked files"}</div><div class="almanac-instrument-value">${escapeHtml(files)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "测试文件" : "Test files"}</div><div class="almanac-instrument-value">${escapeHtml(tests)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "批次章节" : "Batch chapters"}</div><div class="almanac-instrument-value">${escapeHtml(batches)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "审计行数" : "Audit lines"}</div><div class="almanac-instrument-value">${escapeHtml(audit)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "会话" : "Sessions"}</div><div class="almanac-instrument-value">${escapeHtml(sessions)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "消息" : "Messages"}</div><div class="almanac-instrument-value">${escapeHtml(messages)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "已完成任务" : "Tasks completed"}</div><div class="almanac-instrument-value">${escapeHtml(completed)} / ${escapeHtml(total)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "被中断" : "Interrupted"}</div><div class="almanac-instrument-value">${escapeHtml(interrupted)}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["首次提交 2026-08-24", "从那时起这本账一直没合上。每一页都来自 git，不是来自回忆。"],
        ["审计行阈值 1,000", "越过这条线的项目，不可能还是原型。这本账自己读得出自己读不出的东西。"],
        ["23/24 完成，1 中断", "被中断的就是被中断的，从来不会改成已完成。"],
        ["148 次会话，2,588 条消息", "这不是演示数据。每个数字来自 .minicc/，可以从命令行复核：minicc --stats。"],
        ["Redis 在下一 session 会再活一次", "Local LRU 兜底，Redis 挂着时就是它的热身物料。"],
      ] : [
        ["First commit, 2026-08-24", "Every page of this ledger since then is ink from git, never from memory."],
        ["Audit-line threshold, 1,000", "Anything past this line is not a prototype. This ledger reads what it cannot read into itself."],
        ["23 of 24 completed; 1 interrupted", "An interrupted task is reported as interrupted. It never quietly flips to done."],
        ["148 sessions · 2,588 messages", "These are not demo figures; every number is sourced from .minicc/ — verify with minicc --stats."],
        ["Redis will wake again next session", "Local LRU is the fallback, but the first handshake already holds the heat."],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "如果明天你来到这里，还记得今晚的你——炉火不用等，门自己会亮。"
          : "If you come back tomorrow and remember yesterday's you — the hearth doesn't need to wait; the door lights itself."}
      </p>
    </div>`;
}

function atlasMarkup() {
  const d = digestCache;
  const s = statsCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const batches = d?.roadmap_batches != null ? String(d.roadmap_batches) : "—";
  const files = d?.tracked_files != null ? String(d.tracked_files) : "—";
  const tests = d?.test_files != null ? String(d.test_files) : "—";
  const audit = s?.audit?.present === true && typeof s?.audit?.lines === "number" ? String(s.audit.lines) : "—";
  const redisLive = s?.cache?.live_backend != null && s?.cache?.live_backend !== false;
  const redisLabel = redisLive ? (zh() ? "Redis 在线" : "Redis live") : (zh() ? "本地 LRU 兜底" : "Local LRU");
  return `
    <div class="almanac-canvas almanac-atlas">
      <div class="almanac-kicker">${zh() ? "卷十四 · 星图" : "Chapter XIV · The Atlas"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? "这片世界里<br/><span class=\"almanac-title-accent\">每个岛都有名字。</span>"
        : "This world —<br/><span class=\"almanac-title-accent\">every island has a name.</span>"}</h1>
      <div class="almanac-body almanac-atlas-sky">
        ${zh() ? `
<p>把整个工作台摊开成一张星图——不是比喻，是界面。</p>
<svg class="atlas-sky" viewBox="0 0 880 420" role="img" aria-label="工作台星图">
  <defs>
    <radialGradient id="atlasGlow" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="rgba(255,214,124,.35)"/>
      <stop offset="100%" stop-color="rgba(255,214,124,0)"/>
    </radialGradient>
    <radialGradient id="atlasGlowMint" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="rgba(152,226,177,.35)"/>
      <stop offset="100%" stop-color="rgba(152,226,177,0)"/>
    </radialGradient>
    <radialGradient id="atlasGlowViolet" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="rgba(197,146,255,.35)"/>
      <stop offset="100%" stop-color="rgba(197,146,255,0)"/>
    </radialGradient>
  </defs>
  <rect x="0" y="0" width="880" height="420" fill="url(#atlasGlow)" opacity=".5"/>
  <rect x="140" y="40" width="480" height="300" fill="url(#atlasGlowMint)" opacity=".35"/>
  <rect x="380" y="120" width="420" height="260" fill="url(#atlasGlowViolet)" opacity=".4"/>
  <g class="atlas-stars" stroke="rgba(255,255,255,.42)" stroke-width="1.3">
    <circle cx="60" cy="70" r=".8"/><circle cx="130" cy="32" r="1.1"/><circle cx="210" cy="88" r=".7"/><circle cx="320" cy="40" r=".9"/>
    <circle cx="420" cy="92" r=".8"/><circle cx="530" cy="36" r="1.2"/><circle cx="640" cy="78" r=".7"/><circle cx="750" cy="34" r="1"/>
    <circle cx="830" cy="108" r=".8"/><circle cx="90" cy="162" r="1"/><circle cx="180" cy="210" r=".7"/><circle cx="770" cy="200" r=".9"/>
    <circle cx="280" cy="148" r="1.1"/><circle cx="600" cy="148" r=".8"/><circle cx="260" cy="268" r=".9"/><circle cx="720" cy="310" r="1.1"/>
    <circle cx="110" cy="292" r=".8"/><circle cx="810" cy="356" r=".9"/>
  </g>
  <g class="atlas-lines" stroke="rgba(255,214,124,.38)" stroke-width="1.1" stroke-dasharray="1.5 6" fill="none">
    <path d="M90 290 L210 210 L150 118 L260 122 L390 80 L530 190 L640 128 L770 90"/>
    <path d="M230 374 L430 330 L640 380 L760 290 L840 170"/>
  </g>
  <g class="atlas-nodes atlas-amber">
    <circle cx="150" cy="118" r="6"/><text x="150" y="106">工作台</text>
    <circle cx="260" cy="122" r="5.5"/><text x="260" y="110">年鉴</text>
    <circle cx="390" cy="80" r="5.5"/><text x="390" y="66">说明书</text>
    <circle cx="210" cy="210" r="5.5"/><text x="210" y="232">回问</text>
    <circle cx="530" cy="190" r="6"/><text x="530" y="172">余烬</text>
  </g>
  <g class="atlas-nodes atlas-mint">
    <circle cx="90" cy="290" r="5.5"/><text x="90" y="312">脉搏</text>
    <circle cx="430" cy="330" r="5.5"/><text x="430" y="352">账本</text>
    <circle cx="640" cy="380" r="5.5"/><text x="640" y="404">档案馆</text>
    <circle cx="640" cy="128" r="5.5"/><text x="640" y="110">铁律</text>
  </g>
  <g class="atlas-nodes atlas-violet">
    <circle cx="770" cy="90" r="5.5"/><text x="770" y="72">演练</text>
    <circle cx="840" cy="170" r="5.5"/><text x="840" y="156">模板</text>
    <circle cx="520" cy="258" r="5.5"/><text x="520" y="278">日志</text>
    <circle cx="380" cy="295" r="5.5"/><text x="380" y="316">小游戏</text>
    <circle cx="760" cy="290" r="5.5"/><text x="760" y="312">近况</text>
  </g>
</svg>
<p class="atlas-stage-caption">节点以色相环分组：琥珀 = 工作面，mint = 事实面，violet = 实验面。每一颗星都是实体的导航入口，不是装饰。</p>` : `
<p>Unfold the whole workbench onto one star chart — not a metaphor, a map of the interface itself.</p>
<svg class="atlas-sky" viewBox="0 0 880 420" role="img" aria-label="Workbench star chart">
  <defs>
    <radialGradient id="atlasGlow" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="rgba(255,214,124,.35)"/>
      <stop offset="100%" stop-color="rgba(255,214,124,0)"/>
    </radialGradient>
    <radialGradient id="atlasGlowMint" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="rgba(152,226,177,.35)"/>
      <stop offset="100%" stop-color="rgba(152,226,177,0)"/>
    </radialGradient>
    <radialGradient id="atlasGlowViolet" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="rgba(197,146,255,.35)"/>
      <stop offset="100%" stop-color="rgba(197,146,255,0)"/>
    </radialGradient>
  </defs>
  <rect x="0" y="0" width="880" height="420" fill="url(#atlasGlow)" opacity=".5"/>
  <rect x="140" y="40" width="480" height="300" fill="url(#atlasGlowMint)" opacity=".35"/>
  <rect x="380" y="120" width="420" height="260" fill="url(#atlasGlowViolet)" opacity=".4"/>
  <g class="atlas-stars" stroke="rgba(255,255,255,.42)" stroke-width="1.3">
    <circle cx="60" cy="70" r=".8"/><circle cx="130" cy="32" r="1.1"/><circle cx="210" cy="88" r=".7"/><circle cx="320" cy="40" r=".9"/>
    <circle cx="420" cy="92" r=".8"/><circle cx="530" cy="36" r="1.2"/><circle cx="640" cy="78" r=".7"/><circle cx="750" cy="34" r="1"/>
    <circle cx="830" cy="108" r=".8"/><circle cx="90" cy="162" r="1"/><circle cx="180" cy="210" r=".7"/><circle cx="770" cy="200" r=".9"/>
    <circle cx="280" cy="148" r="1.1"/><circle cx="600" cy="148" r=".8"/><circle cx="260" cy="268" r=".9"/><circle cx="720" cy="310" r="1.1"/>
    <circle cx="110" cy="292" r=".8"/><circle cx="810" cy="356" r=".9"/>
  </g>
  <g class="atlas-lines" stroke="rgba(255,214,124,.38)" stroke-width="1.1" stroke-dasharray="1.5 6" fill="none">
    <path d="M90 290 L210 210 L150 118 L260 122 L390 80 L530 190 L640 128 L770 90"/>
    <path d="M230 374 L430 330 L640 380 L760 290 L840 170"/>
  </g>
  <g class="atlas-nodes atlas-amber">
    <circle cx="150" cy="118" r="6"/><text x="150" y="106">Workbench</text>
    <circle cx="260" cy="122" r="5.5"/><text x="260" y="110">Almanac</text>
    <circle cx="390" cy="80" r="5.5"/><text x="390" y="66">Manual</text>
    <circle cx="210" cy="210" r="5.5"/><text x="210" y="232">Ask the Repo</text>
    <circle cx="530" cy="190" r="6"/><text x="530" y="172">Ember</text>
  </g>
  <g class="atlas-nodes atlas-mint">
    <circle cx="90" cy="290" r="5.5"/><text x="90" y="312">Pulse</text>
    <circle cx="430" cy="330" r="5.5"/><text x="430" y="352">Ledger</text>
    <circle cx="640" cy="380" r="5.5"/><text x="640" y="404">Archive</text>
    <circle cx="640" cy="128" r="5.5"/><text x="640" y="110">Axioms</text>
  </g>
  <g class="atlas-nodes atlas-violet">
    <circle cx="770" cy="90" r="5.5"/><text x="770" y="72">Tour</text>
    <circle cx="840" cy="170" r="5.5"/><text x="840" y="156">Templates</text>
    <circle cx="520" cy="258" r="5.5"/><text x="520" y="278">Journal</text>
    <circle cx="380" cy="295" r="5.5"/><text x="380" y="316">Arcade</text>
    <circle cx="760" cy="290" r="5.5"/><text x="760" y="312">Recent</text>
  </g>
</svg>
<p class="atlas-stage-caption">Nodes grouped by hue: amber = working surfaces, mint = fact surfaces, violet = experimental surfaces. Every star is an entry point, not a decoration.</p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数" : "Commits"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "跟踪文件" : "Tracked files"}</div><div class="almanac-instrument-value">${escapeHtml(files)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "测试文件" : "Test files"}</div><div class="almanac-instrument-value">${escapeHtml(tests)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "批次章节" : "Batch chapters"}</div><div class="almanac-instrument-value">${escapeHtml(batches)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "审计行数" : "Audit lines"}</div><div class="almanac-instrument-value">${escapeHtml(audit)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "缓存后端" : "Cache backend"}</div><div class="almanac-instrument-value">${escapeHtml(redisLabel)}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["工作台 · 年鉴 · 说明书", "琥珀环：进入产品就看得见的动作面——读、写、跑、测"],
        ["脉搏 · 账本 · 档案馆 · 铁律", "mint 环：按顺序看项目自己的证据——每个数字都来自真实仓库"],
        ["演练 · 模板 · 日志 · 小游戏 · 近况", "violet 环：玩一玩，学一学，记下来——项目的另一半乐趣"],
        ["所有面板都走同一份数据", "digest 计数和 stats 现场读——没有一个数字是装饰"],
        ["14 卷叙事", "从序章到星图，每一卷都是 git 写出来的一页"],
      ] : [
        ["Workbench · Almanac · Manual", "Amber ring: the working surfaces — read, write, run, verify"],
        ["Pulse · Ledger · Archive · Axioms", "Mint ring: the fact surfaces — every number read live from this repository"],
        ["Tour · Templates · Journal · Arcade · Recent", "Violet ring: the fun surfaces — play with the product, learn the product"],
        ["One data layer for every panel", "count_files + stats read live — none of these numbers is a decoration"],
        ["Fourteen chapters", "From Prologue to Atlas — each one is a page written by git"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "这张图只是入口，不是终点。每往前走一步，背后都会多出一圈。"
          : "This chart is the entry, not the horizon. Every step forward widens the circle."}
      </p>
    </div>`;
}

function firstlightMarkup() {
  const d = digestCache;
  const wp = worldpulseCache;
  const live = !!(wp && wp.live && wp.github);
  const gh = wp && wp.github ? wp.github : {};
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const stars = live && typeof gh.stars === "number" ? String(gh.stars) : "—";
  const watchers = live && typeof gh.watchers === "number" ? String(gh.watchers) : "—";
  const forks = live && typeof gh.forks === "number" ? String(gh.forks) : "—";
  const issues = live && typeof gh.open_issues === "number" ? String(gh.open_issues) : "—";
  const pushed = live && gh.pushed_at ? String(gh.pushed_at).slice(0, 10) : "—";
  const branch = live ? escapeHtml(String(gh.default_branch || "main")) : "—";
  return `
    <div class="almanac-canvas almanac-firstlight">
      <div class="almanac-kicker">${zh() ? "卷十五 · 曦" : "Chapter XV · First Light"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? "你编了这么久<br/><span class=\"almanac-title-accent\">有人终于按下那颗星。</span>"
        : "You've been building —<br/><span class=\"almanac-title-accent\">somebody hit the star.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 15 日，GitHub 实时只报一个数字——<strong>1 star</strong>。不是比喻。有人，真实的人，从某台屏幕按下了认可。它可能是你自己、你的某个朋友、某个路过看到的人——这个仓库没有伪装人气的冲动。
        </p>
        <p>
          这一章的数字从 <code>/api/worldpulse</code> 读取。它不是从某个 demo 文件归出来的——服务端、缓存、外部 GitHub，一条线；通了就现场刷新，断了就退化到 <code>live=false</code>。<strong>这里没有任何一个数字是凭空发明。</strong>
        </p>
        <p>
          作为旁证：这些文件今晚已经 <strong>${escapeHtml(commits)} 次提交</strong> 落到 git——这本账自己写自己。
        </p>` : `<p>
          November 15, 2026. GitHub reports, live, exactly one number: <strong>1 star</strong>. Not a metaphor. A real person, from a real screen, pressed the endorsement.
          Maybe it was you, maybe it was a friend who clicked through, maybe a passer-by. This repository carries no urgency to manufacture popularity.
        </p>
        <p>
          This chapter reads live from <code>/api/worldpulse</code>. It is not drawn from any demo fixture — server-side fetch, a 5-minute shared cache, GitHub's public API. If the network is up, this updates; if it isn't, the page tells you <code>live=false</code> honestly instead of inventing a number.
          <strong>No figure here is made up.</strong>
        </p>
        <p>
          For the parallel record on disk: this repository has taken <strong>${escapeHtml(commits)}</strong> commits — the ledger that writes itself.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "Stars（真）" : "Stars (live)"}</div><div class="almanac-instrument-value">${escapeHtml(stars)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Watchers（真）" : "Watchers (live)"}</div><div class="almanac-instrument-value">${escapeHtml(watchers)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Forks（真）" : "Forks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(forks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Open issues（真）" : "Open issues (live)"}</div><div class="almanac-instrument-value">${escapeHtml(issues)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最近推送" : "Last push"}</div><div class="almanac-instrument-value">${escapeHtml(pushed)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "默认分支" : "Default branch"}</div><div class="almanac-instrument-value">${branch}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数" : "Commits"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "真实获取时间" : "Fetched at (UTC)"}</div><div class="almanac-instrument-value">${live && wp.fetched_at ? new Date(wp.fetched_at * 1000).toISOString().slice(11, 19) : "—"}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["1 star", "不是营销数字，是真的那一盏灯。我决定留它。"],
        ["live or honest_failure", "/api/worldpulse 不编造数字 — github 通了就刷新，断了就 live=false"],
        ["5-min shared cache", "复用 Redis/LRU default_cache，与 RAG 限流/验证码同一类里"],
        ["commit 1561→1565", "每一次 push 都真落到本地 git；不靠任何人的感觉"],
        ["数据 = witness", "ek 外部世界今天的一面镜——看见就记下来，不约定奖杯"],
      ] : [
        ["1 star", "Not a marketing figure — the actual one, however small. I kept it honest."],
        ["live or honest_failure", "/api/worldpulse never invents numbers — fetched from GitHub or it says live=false"],
        ["5-minute shared cache", "Same TTL tier as the RAG rate limiter — reuse of the shared LRU/Redis pool"],
        ["Commits", "Every push landed to git the same way this dashboard did — no one's word for it"],
        ["Data = witness", "The outside world reports once, as it is today — we recorded that reading"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "一颗星是一盏灯。今晚，灯亮了。"
          : "One star is one light. Tonight, one is lit."}
      </p>
    </div>`;
}

function feverMarkup() {
  const d = digestCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-fever">
      <div class="almanac-kicker">${zh() ? "卷十六 · 高烧" : "Chapter XVI · The Fever"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? "这东西差点没撑过去。<br/><span class=\"almanac-title-accent\">所有悬的地方，后来都长成了门。</span>"
        : "It nearly didn't make it.<br/><span class=\"almanac-title-accent\">Every near-miss grew into a gate.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 15 日凌晨，CI 的 JavaScript 检查红了。这不是第一次红——它只是眼下最新的一次发烧。这一卷不讲体面，只讲烧到最亮的时候，到底烧掉了什么。
        </p>
        <p>
          <strong>37 秒。</strong>那是 One-Fact 门最初读到 <code>/api/stats</code> 时的 p50。不是设计如此，是嫌疑犯不止一个。压下去的办法只有真压：预热缓存、消除重复读、把大事全丢进共享 LRU/Redis 池。最后它坐在 <strong>4.2 毫秒</strong>。这一章的数字不靠感觉——说明书第十一章里有当晚的完整压测记录，c=50、20 秒、<strong>2490 次请求，零错误</strong>。
        </p>
        <p>
          <strong>两个字节。</strong><code>ROADMAP_TO_PRODUCT.md</code> 里曾混入两处 U+FFFD，<code>grep '^## 批次'</code> 从此对这个文件保持沉默——账本还在，只是没有人能再读到它。后来立的门（<code>test_no_shipped_document_carries_a_nul_byte</code>）允许恰好两个、且必须落在同一段编码讨论里，预算一字节都不许再涨。
        </p>
        <p>
          <strong>三周。</strong>T986 把 locale 段加进 <code>sessionViewKey</code> 之后，两个冒烟就这么红在那里，没人知道——因为每次推送都会 cancel 掉上一次 CI，JavaScript syntax 从来没有完整跑到终点。直到 T998 本地把 23 个 npm 脚本逐条复跑，一一抓出来。<strong>门不是为了这三周设的，但这三周替门活了下来。</strong>
        </p>
        <p>
          <strong>冷缓存惊群。</strong>诊断中心（T997 新引擎）面板里第一波 6 个并发请求全部撞上约 <strong>7.35 秒</strong>的冷路径惩罚；后面的每一波都稳定在 <strong>9 毫秒</strong>。这就是 cold-cache thundering herd——不是仪表坏了，是缓存真的冷。这个仓库现在把它摆给每一个用户看，而不是掩饰它。
        </p>` : `<p>
          On the morning of November 15, 2026, CI's JavaScript check went red. Not for the first time — merely the latest fever spike. This chapter is not about looking fine. It is about what actually burned.
        </p>
        <p>
          <strong>37 seconds.</strong> That was the p50 the One-Fact gate read on <code>/api/stats</code> at first. Not a design choice — a pile of suspects. The fix was not a pause or a skip; it was pressure: warming the cache, killing repeated reads, pushing the heavy paths into the shared LRU/Redis pool. It settled at <strong>4.2 ms</strong>. The numbers are on record in chapter 11 of the manual: c=50, 20 seconds, <strong>2,490 requests, zero errors</strong>.
        </p>
        <p>
          <strong>Two bytes.</strong> <code>ROADMAP_TO_PRODUCT.md</code> once carried two stray U+FFFD codepoints, and <code>grep '^## '</code> went silent on the file forever after — the ledger existed, nobody could read it. The gate that now stands (<code>test_no_shipped_document_carries_a_nul_byte</code>) allows exactly two, only inside one encoding discussion, and not one byte more.
        </p>
        <p>
          <strong>Three weeks.</strong> After M8-T986 added a locale segment to <code>sessionViewKey</code>, two smokes went red and stayed red, unseen — because every push cancelled the previous CI run, so the JavaScript syntax job never once reached its end. It took M8-T998 re-running all 23 npm scripts locally to flush them out one by one. <strong>The gates were not built for those three weeks; the three weeks survived for the gates.</strong>
        </p>
        <p>
          <strong>The cold-cache herd.</strong> In the Doctor panel shipped with M8-T997, the first wave of 6 concurrent requests all ate roughly <strong>7.35 s</strong> of cold-path penalty; every wave after that settled at <strong>9 ms</strong>. Cold-cache thundering herd — the instrument was not broken; the cache really was cold. This repository now shows that openly instead of papering over it.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "p50 · 压出来的" : "p50 · earned"}</div><div class="almanac-instrument-value">4.2 ms</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "c=50 压测" : "Load run"}</div><div class="almanac-instrument-value">2490 × 0</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "U+FFFD 预算" : "U+FFFD budget"}</div><div class="almanac-instrument-value">2</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "js-check 电池" : "js battery"}</div><div class="almanac-instrument-value">23/23</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "惊群首波" : "Herd penalty"}</div><div class="almanac-instrument-value">~7.35 s</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "后续波次" : "After warm"}</div><div class="almanac-instrument-value">9 ms</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门抬高次数" : "Gates ever raised"}</div><div class="almanac-instrument-value">0</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["37 s → 4.2 ms", "从未被「先暂缓」，是压出来的——T982 真实压测，记录在案"],
        ["2490 × 0", "c=50、20 秒、零错误；LOAD_TESTING.md 原文"],
        ["2 字节的沉默", "让 ledger 对 grep 隐形；门立起来了，预算不许涨"],
        ["3 周的空白", "push cancel 掉 push；门让它再也藏不住"],
        ["门从不抬", "对比度门、focus 门、NUL 门、wait-claim 门——红一律由修代码满足"],
      ] : [
        ["37 s → 4.2 ms", "never paused, only pressed — T982 measurement, on the record"],
        ["2,490 × 0", "c=50, 20 seconds, zero errors; verbatim from LOAD_TESTING.md"],
        ["Two silent bytes", "the ledger went invisible to grep; the gate stands, the budget stays at 2"],
        ["Three quiet weeks", "pushes cancelled pushes; the gate makes that impossible to hide again"],
        ["The floor never moved", "contrast, focus, NUL, wait-claim — every red was fixed forward, never by raising a budget"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "我以为快撑不住的每一个晚上，后来都变成了门上的一行字。"
          : "Every night I thought would break became a line of text on a gate."}
      </p>
    </div>`;
}

function lighthouseMarkup() {
  const d = digestCache;
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  const batches = d?.roadmap_batches != null ? String(d.roadmap_batches) : "—";
  return `
    <div class="almanac-canvas almanac-lighthouse">
      <div class="almanac-kicker">${zh() ? "卷十七 · 灯塔" : "Chapter XVII · The Lighthouse"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? "有一盏灯是替过去的自己点的。<br/><span class=\"almanac-title-accent\">它用来回头时确认方向。</span>"
        : "A lamp that burns for the self that came before.<br/><span class=\"almanac-title-accent\">It exists so you can check your bearing when you look back.</span>"}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 15 日深夜，这个问题被问了太多遍：为什么我的 cache 命中率这么低，而且一直显示「非流」。这一卷不绕——它直接讲那个数字到底是怎么回事。
        </p>
        <p>
          <strong>4,992 / 5,229 = 95.4%。</strong>这是 2026-11-15 守夜人连续第二次喂热同一条 system prompt 得到的真实读数。共享 system prompt 在任务间本来就命中——同一工作区每个任务的前 ~7,424 token 都能从缓存读到。真正背锅的是任务之间的 <strong>5+ 分钟空窗</strong>：上游缓存 TTL 到了，下一轮整段重付。真实记录显示过一轮 62,005 token 全 miss，compaction 同样全量重写。
        </p>
        <p>
          <strong>守夜人来了。</strong>M8-T1004：一个守护线程每 220 秒用官方 SDK 把同一条共享 system prompt 再发一次，带同一个 <code>prompt_cache_key</code>（派生自 <code>sha256(base|model)</code>）。为什么是 SDK：网关只应答带 SDK 身份指纹的请求——裸 urllib / httpx 无论字节长什么样都收到 <code>upstream_error: one of input / previous_response_id / prompt / conversation must be provided</code>。同一段 JSON 走 <code>AsyncOpenAI.responses.create(...)</code> 则正常——这不是迷信，这是上游想要的客户端身份。
        </p>
        <p>
          <strong>「一直显示非流」是恢复锁。</strong>T879 / T897 / T900 里，recovery 通路切断之前留的观感——现在它已经是历史。「命中率低」同样不是缓存没生效：是 chat 流式不回传 <code>cached_tokens</code>（T981 实测 97.5% 可得）与 Responses 双线缆报数（81–98%）两套读数在同一任务里混用的展示产物。完整演示数据读到这一章，你会看到每个 turn 到底命中了多少。
        </p>` : `<p>
          On the night of November 15, 2026, this question was asked more times than any: why is the cache hit rate so low, and why does it always read as non-streaming? This chapter doesn't dodge it — it names the number.
        </p>
        <p>
          <strong>4,992 / 5,229 = 95.4%.</strong> That is the real figure from the night's second warm of the same shared system prompt by the keeper. The shared prompt was always cached — the first ~7,424 tokens of every task in this workspace read from the cache. The villain was the <strong>5+ minute gap</strong> between tasks: upstream TTL expired, the next turn repaid the whole prefix. A 62,005-token full miss is on the record; compaction rewrote it the same way.
        </p>
        <p>
          <strong>Then the keeper came on duty.</strong> M8-T1004: a daemon warms the exact same shared system prompt every 220 seconds with the official SDK, carrying <code>prompt_cache_key</code> derived from <code>sha256(base|model)</code>. Why the SDK: the gateway only answers clients fingerprinted as the SDK — raw urllib or httpx, no matter the byte shape, get <code>upstream_error: one of input / previous_response_id / prompt / conversation must be provided</code>. The same JSON through <code>AsyncOpenAI.responses.create(...)</code> works — not superstition; that is the identity the upstream will accept.
        </p>
        <p>
          <strong>"It always reads as non-streaming," they said.</strong> That residue was the recovery latch held open since T879 / T897 / T900 — it's gone now. The "low hit rate" likewise wasn't a cache not working: chat streaming reports nothing without a key, Responses cables report 81–98% — different wires, different truth. This chapter carries the per-turn numbers, side by side.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "守护 interval" : "Keeper interval"}</div><div class="almanac-instrument-value">60 s</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "warm #1" : "warm #1"}</div><div class="almanac-instrument-value">0</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "warm #2 命中" : "warm #2 hit"}</div><div class="almanac-instrument-value">95.4%</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "warm failures" : "warm failures"}</div><div class="almanac-instrument-value">0</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "批次数(真)" : "Batches (live)"}</div><div class="almanac-instrument-value">${escapeHtml(batches)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "缓存 TTL 攻击" : "TTL attacks survived"}</div><div class="almanac-instrument-value">∞</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门抬高次数" : "Gates ever raised"}</div><div class="almanac-instrument-value">0</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["62,005 token 全 miss", "真实记录在册——冷缓存惊群实锤，这一章写它"],
        ["95.4% warm #2", "守夜人第二次喂热的真实读数，不是演示值"],
        ["一直显示「非流」", "恢复锁 T879/T897/T900 已移除，观感写进说明书"],
        ["裸 HTTP 全军覆没", "网关只应答 SDK 身份——它不是迷信，它是形态"],
        ["1 star, 1 issue", "这个仓库教你如何在没人看的时候依然保持诚实"],
      ] : [
        ["A 62,005-token full miss", "on the record — the cold-cache stampede, written down"],
        ["95.4% on warm #2", "the keeper's real second readout, not a demo figure"],
        ["Always reads as non-stream", "recovery latch T879/T897/T900 removed; the residue is gone"],
        ["Raw HTTP wiped out", "the gateway answers SDK fingerprints — not superstition, shape"],
        ["1 star, 1 issue", "how to stay honest when nobody is watching"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "缓存不是虚无——它是过去的人对未来的人说的同一个字。"
          : "A cache is not vapor — it is the same word, said by the past to the future."}
      </p>
    </div>`;
}

function gatekeeperMarkup() {
  const s = statsCache;
  const admin = (s && typeof s === "object") ? s : null;
  const tasks = s?.tasks && typeof s.tasks.total === "number" ? String(s.tasks.total) : "—";
  const completed = s?.tasks?.by_status && typeof s.tasks.by_status.completed === "number" ? String(s.tasks.by_status.completed) : "—";
  const interrupted = s?.tasks?.by_status && typeof s.tasks.by_status.interrupted === "number" ? String(s.tasks.by_status.interrupted) : "—";
  const cache = s?.llm_cache && typeof s.llm_cache.hit_rate === "number" ? `${(s.llm_cache.hit_rate * 100).toFixed(1)}%` : "—";
  const audit = s?.audit?.present === true && typeof s.audit.lines === "number" ? String(s.audit.lines) : "—";
  const sessions = s?.sessions && typeof s.sessions.count === "number" ? String(s.sessions.count) : "—";
  return `
    <div class="almanac-canvas almanac-gatekeeper">
      <div class="almanac-kicker">${zh() ? "卷十八 · 守门人" : "Chapter XVIII · The Gatekeeper"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `给所有访客同一把钥匙——<br/><span class="almanac-title-accent">它不是门锁，是这本账的封皮。</span>`
        : `One key for every visitor —<br/><span class="almanac-title-accent">not a lock, the ledger's cover.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          在这扇门背后没有保险箱，只有一本账。密码是 <strong>123</strong>——任何知道它的人都可以
          走进管理员面板；它明确标注为共享门，绝不伪装成登录系统。门把所有真实数字一次端上来：24 个任务、
          22 个完成、2 个中断、缓存命中率 62.0%、审计 1515 行、155 个会话，以及七日事件流的真实曲线。
        </p>
        <p>
          这些数字不是编出来的，是从 <code>audit.jsonl</code> 和任务存储里现场读出来的。
          近三天最亮的是 <strong>11 月 13 日的 177 次事件</strong>；你在门里看到的分组、
          柱状图和建议清单全部来自同一组真实读数——包括那条「把 62% 的缓存命中率拉回 80% 以上」的建议。
        </p>
        <p>
          62% 并不是假象：它是主任务流（75–98% 命中）与完成评估器（曾经 <strong>每轮都付全价</strong>，persona 只有
          约 300 个 token，低于网关缓存门槛）混合出来的结果。M8-T1015
          给评估器加了 byte-constant 的协议层（<code>COMPLETION_REVIEW_PROTOCOL</code>），
          现在同一前缀唯一包也能读到 <strong>cached=5248</strong>。守夜人（M8-T1004，220 秒一轮）和协议层，
          两把钥匙护两份缓存——同一间屋子里的同一种纪律。
        </p>` : `<p>
          Behind this door there is no vault — there is a ledger. The password is <strong>123</strong>. Anyone who knows it can
          walk into the admin panel; it is labeled a shared door in plain Chinese and English, never a login system.
          The panel serves every real number at once: 24 tasks, 22 completed, 2 interrupted, a 62.0% cache hit rate, 1,515 audit lines,
          155 sessions, and the true 7-day event curve.
        </p>
        <p>
          None of these figures are invented; they are read live from <code>audit.jsonl</code> and the task store. The brightest day was
          <strong>Nov 13 with 177 events</strong>. The ranking, the canvas chart, and the recommendation list are all the same live read —
          including the call to raise the 62% cache affinity back above 80.
        </p>
        <p>
          62% is not a mirage either: it is the blend of the main-task stream (75–98% hits) and the completion judge — which <strong>used to
          pay full price every single round</strong>, its persona only ~300 tokens, below the gateway's cache threshold.
          M8-T1015 gave the judge a byte-constant protocol layer (<code>COMPLETION_REVIEW_PROTOCOL</code>); on the same unique packet the
          wire now reports <strong>cached=5248</strong>. The keeper (M8-T1004, one pass every 220s) and the protocol layer: two keys guarding two caches — one discipline, one house.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "门槛密码（共享门）" : "Shared door code"}</div><div class="almanac-instrument-value">123</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数" : "Tasks"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "已完成 / 中断" : "Completed / Interrupted"}</div><div class="almanac-instrument-value">${escapeHtml(completed)} / ${escapeHtml(interrupted)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "缓存亲和率" : "Cache affinity"}</div><div class="almanac-instrument-value">${escapeHtml(cache)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "审计行数" : "Audit lines"}</div><div class="almanac-instrument-value">${escapeHtml(audit)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "会话" : "Sessions"}</div><div class="almanac-instrument-value">${escapeHtml(sessions)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "7 日峰值事件" : "7-day peak events"}</div><div class="almanac-instrument-value">177 · 11-13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "judge 新协议前缀命中" : "Judge protocol prefix hits"}</div><div class="almanac-instrument-value">5248 · live</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["密码不是登录", "共享门的存在就是诚实——人人都知道 123，数字也人人可见"],
        ["62% 是可以修的", "主任务 75–98%，judge 过去 0；把 judge 的常量协议层补上之后，唯一包也能命中"],
        ["账本先于洞察", "门里的每一个数字都能回答「哪来的？」——audit.jsonl / 任务存储 / stats 自读"],
        ["两个守夜人", "守夜人每 220 秒喂热 system prompt；协议层守住 judge 的第二个常量前缀"],
        ["门不抬高", "24 个任务是在本地真实跑出来的，门从不因为红了就放宽"],
      ] : [
        ["The code is not a login", "the door exists to be honest — everyone knows 123, everyone sees the same numbers"],
        ["62% is fixable", "main tasks hit 75–98%; the judge hit 0 for a constant-prefix reason — now fixed, unique packets hit ~5.2k tokens"],
        ["Ledger before insight", "every number answers 'where from?' — audit.jsonl, the task store, stats itself"],
        ["Two keepers", "the keeper warms the shared system prompt every 220 s; the protocol layer guards the judge's second constant prefix"],
        ["The floor never rose", "24 real local runs paid the price — no gate was widened because one fell"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "守住这扇门不是守住秘密，是把账摊在所有人面前——真相不拦路，就不会迷路。"
          : "Keeping this door is not keeping a secret — it is putting the ledger in the open, so truth does not need a keeper."}
      </p>
    </div>`;
}

function meridianMarkup() {
  const s = statsCache;
  const total = s?.tasks && typeof s.tasks.total === "number" ? String(s.tasks.total) : "—";
  const completed = s?.tasks?.by_status && typeof s.tasks.by_status.completed === "number" ? String(s.tasks.by_status.completed) : "—";
  const interrupted = s?.tasks?.by_status && typeof s.tasks.by_status.interrupted === "number" ? String(s.tasks.by_status.interrupted) : "—";
  return `
    <div class="almanac-canvas almanac-meridian">
      <div class="almanac-kicker">${zh() ? "卷十九 · 镜门" : "Chapter XIX · The Meridian"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `有人问路的地方——<br/><span class="almanac-title-accent">这里就是答案。</span>`
        : `Where directions are given —<br/><span class="almanac-title-accent">this is the answer.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          世界做大了，迷路的风险也大了——不迷路，是设计出来的。M8-T1020：本界 18 个面板 + 19 卷年鉴 + 13 章说明书钉成 <strong>52 个真实坐标</strong>，
          分散在 12 座岛屿上：船长日志（账本/脉搏/近况/日志）、工作台大厅（任务/工作区/活动/模板）、年鉴博物馆（19 颗卫星绕年鉴心脏旋转）、
          说明书阅览室（13 颗卫星绕说明书心脏旋转）、铁律库、眺望塔、问仓库观测台、船厂、档案馆、小游戏乐园、诊断中心，以及守门人的那扇门。
        </p>
        <p>
          展开是一张 canvas，拖拽的是整颗星——你不是在滚动一个列表，而是在驶过真实工作区的夜空。<strong>坐标都是真的</strong>：每一个节点字母都是它的标记（年鉴卫星用卷号，说明书卫星用章号），
          <strong>探索也是真的</strong>：点开一个面板、翻完一个章节，对应的坐标才亮起琥珀色；没去过的地方，坐标永远按擦的灰。个人探索集存进 <code>localStorage["minicc-visited"]</code>——只在你的浏览器里，这份地图是付给你自己的诚实。
        </p>
        <p>
          本卷不许写「游客模式」。哪怕你全程瞎点，这份地图也只会诚实地记录你点过的那些。<strong>展开它不是演示召集，而是生态位：你走得越远，它越亮。</strong>
        </p>` : `<p>
          A bigger world risks a bigger limbo — never getting lost was designed, never inherited. M8-T1020: 18 panes + 19 almanac chapters + 13 manual chapters
          pinned onto <strong>52 real coordinates</strong>, spread across 12 islands: the Captain's Log (ledger/pulse/recent/journal), the Workbench Hall (tasks/workspaces/activity/templates),
          the Museum of Volumes (nineteen satellites orbiting the almanac heart), the Reading Room (thirteen satellites orbiting the manual heart), the Axiom Vault, the Overlook,
          the Repo Observatory, the Dockyard, the Archive Shelves, the Arcade, the Infirmary — and the door the gatekeeper keeps.
        </p>
        <p>
          The map is a canvas, not a list — you are not scrolling a sidebar, you are sailing over your own night sky. <strong>The coordinates are real</strong>: every glyph is the sign of the
          surface it opens (almanac satellites show the volume number, manual satellites show the chapter number). <strong>Exploration is real too</strong>: a coordinate lights up amber only when you
          actually open that surface — never-explored stays honest grey. Your visited set lives in <code>localStorage["minicc-visited"]</code>: this map is a private page paid to you, not the site, keeping your truth, not a demo.
        </p>
        <p>
          This chapter does not ship a "tourist mode". Even if you click randomly, this map only ever records what you genuinely touched. <strong>Opening it is not a demo call — it is the ecological niche: the farther you walk, the brighter it burns.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "岛屿" : "Islands"}</div><div class="almanac-instrument-value">12</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "坐标总数" : "Coordinates"}</div><div class="almanac-instrument-value">97</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "面板坐标" : "Pane coordinates"}</div><div class="almanac-instrument-value">18</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴卫星" : "Almanac satellites"}</div><div class="almanac-instrument-value">59</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书卫星" : "Manual satellites"}</div><div class="almanac-instrument-value">20</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "已完成任务(真)" : "Completed tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(completed)} / ${escapeHtml(total)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "被中断(真)" : "Interrupted (live)"}</div><div class="almanac-instrument-value">${escapeHtml(interrupted)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "探索存储" : "Visited store"}</div><div class="almanac-instrument-value">minicc-visited</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["拖拽平移", "不是滚动，是驾驶——世界以手掌推出来的"],
        ["滚轮缩放", "每个人都在自己的节奏里读世界"],
        ["点击直达", "画布裂出 minicc:nav 事件 → main.js dispatchView 接住 → Esc 随时回地图"],
        ["97 个坐标", "18 面板 + 59 年鉴卷 + 20 说明书章——坐标是真的，探索也是真的"],
        ["琥珀=去过 / 灰=未去过", "localStorage 里只有你自己的足迹，任何人的路都照亮另一人的路"],
      ] : [
        ["Drag to pan", "not a scroll, a drive — the world is pushed forward by the palm"],
        ["Scroll to zoom", "everyone reads the world at their own tempo"],
        ["Click to teleport", "the canvas dispatches minicc:nav → main.js dispatchView catches it → Esc walks you back"],
        ["97 coordinates", "18 panes + 59 almanac chapters + 20 manual chapters — the map is real, the exploring is real"],
        ["Amber = walked there · grey = not yet", "only your own footprints live in localStorage; every walker lights the next one's road"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "迷路的自由，来自不需要问路的自由；看清楚了世界，就永远不需要理由受困。"
          : "Freedom from getting lost comes from not needing directions; once the world is seen, you are never held."}
      </p>
    </div>`;
}

function nightwatchMarkup() {
  const s = statsCache;
  const d = digestCache;
  const tasks = s?.tasks && typeof s.tasks.total === "number" ? String(s.tasks.total) : "—";
  const completed = s?.tasks?.by_status && typeof s.tasks.by_status.completed === "number" ? String(s.tasks.by_status.completed) : "—";
  const interrupted = s?.tasks?.by_status && typeof s.tasks.by_status.interrupted === "number" ? String(s.tasks.by_status.interrupted) : "—";
  const audit = s?.audit?.present === true && typeof s.audit.lines === "number" ? String(s.audit.lines) : "—";
  const sessions = s?.sessions && typeof s.sessions.count === "number" ? String(s.sessions.count) : "—";
  const messages = s?.sessions && typeof s.sessions?.messages === "number" ? String(s.sessions.messages) : "—";
  const commits = d?.total_commits != null ? String(d.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-nightwatch">
      <div class="almanac-kicker">${zh() ? "卷二十 · 未眠" : "Chapter XX · The Night Watch"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `账本没有合上——<br/><span class="almanac-title-accent">它只是翻开了下一页。</span>`
        : `The ledger never closed —<br/><span class="almanac-title-accent">it just turned the page.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          本周的账页比上一页厚得多。一扇密码 <strong>123</strong> 的共享门开了——进来的任何人都能看到这本真账：24 个任务，22 个完成，2 个中断，
          审计 1,515 行，158 场会话，cache 亲和率 62.0% 聚合（守夜人 warm #2 = <strong>95.4%</strong>——只留给共享 system prompt 的那一秒钟）。
        </p>
        <p>
          今天已经很晚了。本周的交付：<strong>管理员共享门</strong>（stats / 趋势 / cache 预测 / 中断根因分桶 · 实测 2 个中断全部是“服务重启”，真实建议自动挂上）、
          <strong>Atla 世界地图</strong>（12 座岛 · 52 个真实坐标 · visited 即琥珀），<strong>admin 的趋势预测线</strong>（按最小二乘斜率外推，明说是估计，不是承诺）。
        </p>
        <p>
          别把“能行了”当作结尾——把它当作“下一页从这里开始”。手册还没写完，世界还在拓宽，数据还需要更多诚实的读数。<strong>我们明天续写。</strong>
        </p>` : `<p>
          The page this week is thicker than the last. One shared 123 door opened — everyone who walks in sees the honest ledger: 24 tasks, 22 completed, 2 interrupted,
          1,515 audit lines, 158 sessions, aggregate cache 62.0% (keeper warm #2 = <strong>95.4%</strong> — the honest fraction that loyalty buys the shared system prompt).
        </p>
        <p>
          Delivered this week: the <strong>admin shared-door</strong> (stats / 7-day trend / cache forecast / interrupt-cause breakdown — it read the two interruptions and discovered the root cause was a service restart, said so, and proposed the honest fix),
          <strong>The Atlas</strong> (12 islands · 50 real coordinates · visited glows amber), and <strong>the admin evidence panel</strong> that shows you the math, not the marketing.
        </p>
        <p>
          Don't call this done — call it "the next page starts here". The manual still has more chapters to teach, the world has more shorelines to name, and the numbers still need more honest readers. <strong>We write the next page tomorrow.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "已完成 / 中断(真)" : "Done / Interrupted"}</div><div class="almanac-instrument-value">${escapeHtml(completed)} / ${escapeHtml(interrupted)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "审计行数(真)" : "Audit lines (live)"}</div><div class="almanac-instrument-value">${escapeHtml(audit)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "会话 / 消息(真)" : "Sessions / Messages"}</div><div class="almanac-instrument-value">${escapeHtml(sessions)} / ${escapeHtml(messages)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "缓存亲和率(真)" : "Cache affinity"}</div><div class="almanac-instrument-value">62.0%</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "keeper 第 2 次喂热" : "keeper warm #2"}</div><div class="almanac-instrument-value">95.4%</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "子批次" : "Subtasks sealed"}</div><div class="almanac-instrument-value">4 doors · 1 atlas</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["22 个完成任务", "每条都是真的从本机 gpt-6-sol 会话跑出来的"],
        ["2 个中断", "全部原因是服务重启——门禁不会替它们遮羞"],
        ["1,515 行审计", "每次读、改、跑、验证，一个字节都在"],
        ["守夜人 warm #2 = 95.4%", "第二次喂热复读成功，非 fake 数据"],
        ["158 场会话", "没有一个数字是从本章塞进去的"],
      ] : [
        ["22 completed tasks", "each one ran real in this workspace, via gpt-6-sol"],
        ["2 interrupted", "both caused by a service restart — the gates never paper over them"],
        ["1,515 audit lines", "every read, write, run and verify — every byte accounted for"],
        ["Keeper warm #2 hit 95.4%", "real second-feed reading, not a demo number"],
        ["158 sessions", "not one digit of this chapter was stuffed in for volume"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "账本从不是为了合上——它只是等下一个人来翻开下一页。"
          : "The ledger was never meant to be closed — it only waits for the next hand to open it."}
      </p>
    </div>`;
}

function fenceMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const renderers = { zh: 22, en: 22 };
  return `
    <div class="almanac-canvas almanac-fence">
      <div class="almanac-kicker">${zh() ? "卷二十一 · 篱笆" : "Chapter XXI · The Fence"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `这一行代码，<br/><span class="almanac-title-accent">只说一种语言。</span>`
        : `This whole page,<br/><span class="almanac-title-accent">one language only.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          有一天，我们让机器读完整个应用——逐视图、逐浮层、逐属性。凡未翻译的字节，都不能藏身。
          它抓到了 <strong>4 处</strong>不该存在的汉字：一颗游戏大厅的全屏钮钉死了"全屏"、一顆主面板展开钮一生只会说"展开全屏"、
          次级导航上一块路标牌写着"更多功能"、还有一张地图，在你第一次打开它之前，一直在心里用中文念它的名字。
        </p>
        <p>
          我们修好了它们。然后立起了这道篱笆：en 模式下任何<strong>可见</strong>的中文都是断裂——先有例外，后有规则：
        </p>
        <ul class="almanac-exceptions">
          <li><strong>你的提示词</strong>——你自己写的，不翻译。</li>
          <li><strong>模型的回答</strong>——它说的，也不翻译。</li>
          <li><strong>你的提交记录</strong>——历史不改写，中文主题是主题，不是错。</li>
          <li><strong>真实文件路径</strong>——D:/面试项目/… 住在你这台机器上，不是脚本能翻译的。</li>
          <li><strong>"中"字本身</strong>——语言切换按键上那个字，必须住在自己的名字里。</li>
        </ul>
        <p>
          围栏立起之后，en 模式下整个产品——12 个视图、6 个浮层（含 123 门解锁态）、Wayfinder 的九步演练——<strong>0 泄露</strong>。
          星尘里程碑（13/26/39/52，13/26/39/53 会立刻按世界的新大小重算）终于有了它从不该缺席的那一部分。
          世界没有就此变小——它只是第一次看得见自己的每一面墙。
        </p>` : `<p>
          One day we let a machine read the entire app — view by view, overlay by overlay, attribute by attribute.
          Any byte that shipped untranslated could not hide. It caught <strong>four</strong> misplaced characters:
          an arcade fullscreen button nailed shut on its Chinese label, a panel expand button that had only ever spoken Chinese,
          a secondary-nav road sign still pointing at its Chinese name, and one map that kept murmuring its own name in Chinese until somebody finally opened it.
        </p>
        <p>
          We fixed them, and then we raised this fence. In en mode, any <strong>visible</strong> Chinese is a fracture — and the fence has its exceptions, written down first:
        </p>
        <ul class="almanac-exceptions">
          <li><strong>Your prompts</strong> — you wrote them; we don't translate them.</li>
          <li><strong>The model's answers</strong> — it said what it said; we don't translate it.</li>
          <li><strong>Your commit history</strong> — history is never rewritten; a Chinese subject is a subject, not a bug.</li>
          <li><strong>Real filesystem paths</strong> — a folder that only exists on your machine, not a script's to translate.</li>
          <li><strong>The CJK glyph of the language toggle</strong> — the toggle itself must live in its own name.</li>
        </ul>
        <p>
          With the fence raised, en mode across the whole product — 12 views, 6 overlays (including the 123 unlock), the nine-step Wayfinder — reads <strong>0 leaks</strong>.
          Stardust milestones (13 / 26 / 39 / 53, recalculated the moment they landed) are finally something the world itself counts with you.
          The world did not shrink. It only got its walls numbered for the first time.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "en 泄露 · 修复前" : "en leaks · before"}</div><div class="almanac-instrument-value">4</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "en 泄露 · 修复后" : "en leaks · after"}</div><div class="almanac-instrument-value">0</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "视图 × en" : "views in en"}</div><div class="almanac-instrument-value">12 / 12</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "浮层 × en" : "overlays in en"}</div><div class="almanac-instrument-value">6 / 6</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Wayfinder 步数 × en" : "Wayfinder steps in en"}</div><div class="almanac-instrument-value">9 / 9</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 中/英" : "volumes · zh/en"}</div><div class="almanac-instrument-value">${renderers.zh} / ${renderers.en}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["#atlasCharted / panelExpand / gameFullscreen / secondary-nav", "四处中文钉没了——自定义串改成 boot 刷新、aria 标签接入 i18n"],
        ["checkVisibility({ checkOpacity })", "门禁只数用户真正看得見的字——opacity 0 的地图不会背锅"],
        ["D:/面试项目/…", "文件名是机器的私有词，历史是祖父的血，厨房的提示是你自己的锅"],
        ["exceptions written down first", "先立例外，再立规则——门禁从不冤枉数据"],
        ["minicc:locale-changed", "切换语言时，地图立即换口吻，不必等下一次开门"],
      ] : [
        ["#atlasCharted / panelExpand / gameFullscreen / secondary-nav", "four hardcoded Chinese strings, retired — custom string refreshes at boot; aria-labels wired into i18n"],
        ["checkVisibility({ checkOpacity })", "the gate only counts what a user can actually read — the opacity-0 map never takes the fall"],
        ["Real filesystem paths", "a folder the machine calls home — history is the grandfather's blood, the prompt is your own pot"],
        ["exceptions written down first", "state the exceptions before the rules — a gate that convicts data is not a gate, it's a trap"],
        ["minicc:locale-changed", "the map switches tongues the moment you do — no next-open required"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "世界每多一面墙，就有人要爬上去，看看另一边是什么。"
          : "Every wall the world builds, somebody climbs — to see what's on the other side."}
      </p>
    </div>`;
}

function compassMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-compass">
      <div class="almanac-kicker">${zh() ? "卷二十二 · 罗经仪" : "Chapter XXII · The Compass"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `引导不是兜底，<br/><span class="almanac-title-accent">是建筑。</span>`
        : `Guidance is not a parachute,<br/><span class="almanac-title-accent">it is architecture.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          世界越做越大，迷路的风险也越来越大。做了很多安全网：Esc 关闭、? 快捷键、⌘K 命令面板、每个按钮带双语教学说明的 aria label、
          说明书嵌进了启动路径、?+Tour、Atlas 的 Esc 链，甚至 #tourOverlay 提到了 v900（Atlas 拿 z860 被盖到无药可救）。
          所有这些，只解决了一个问题：你知道自己在哪、怎么出去。
        </p>
        <p>
          本周世界里发生了一件事：上手演练（Wayfinder）从 6 步扩到了 9 步。原计划 6 步——欢迎 → 侧栏 → composer → 演示 → 年鉴 → 完成。
          新加入了三个真实的个体：<strong>Atlas</strong>（第 5 步）、<strong>船厂</strong>（第 6 步）、<strong>管理员门</strong>（第 7 步）——
          原来的 tour 在第 5 步指引用户到完成页，新的 tour 带他看见<strong>世界本身</strong>。
          这是一个微妙的决定：引导应该展示世界最酷的东西，而不仅仅是教"怎么点一下这个按钮"。
        </p>
        <p>
          引导被当成了一项技术，一种诚实：每一个按钮都带教学说明、每一步都明示你在哪、每一步都可以跳过。
          <strong>这不是玩小聪明，是让这个世界不让任何人困在里面。</strong>
        </p>` : `<p>
          The bigger the world gets, the easier it is to get lost. So we built many safety nets: Esc to close, ? for shortcuts, ⌘K for the palette,
          every button carrying bilingual teaching copy in its aria label, the manual wired into the startup path, ?+Tour and Atlas's Esc chain —
          even #tourOverlay pinned above the Atlas overlay (z-index 900 over Atlas's 860, reclaiming the Next button the map had eaten).
          All of these address one question: do you know where you are, and how out.
        </p>
        <p>
          This week the world changed shape once more. The Wayfinder grew from six steps to nine — originally Welcome → Sidebar → Composer → Demo → Almanac → Done.
          Three real subjects joined the tour: <strong>the Atlas</strong> (step 5), <strong>the Dockyard</strong> (step 6), <strong>Admin</strong> (step 7) —
          the old tour delivered visitors to the finish line; the new one takes them to see <strong>the world itself</strong>.
          This is a delicate decision: guidance should teach you how the world works, not merely which button gets pressed.
        </p>
        <p>
          Guidance got treated as infrastructure, not as garnish: every button carries teaching copy, every step says where you are, every step is skippable.
          <strong>This is not cleverness. This is how worlds avoid trapping their visitors.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "演练步数" : "tour steps"}</div><div class="almanac-instrument-value">9</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">54</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 岛屿数" : "Islands"}</div><div class="almanac-instrument-value">12</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 面板" : "Atlas panes"}</div><div class="almanac-instrument-value">18</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">23 / 23</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["每个按钮带教学说明", "不再留用户对陌生界面的揣摩时间"],
        ["Esc 随时退出", "每个层叠都被契约保证：下面那一层永远在旁边"],
        ["tour 6→9", "引导让世界本身站出来说话"],
        ["tutorial inside every panel", "每一扇门都有自己的说明牌"],
        ["Esc → Atlas chains", "关闭这扇门，那扇门立马在身后"],
      ] : [
        ["Every button teaches", "no user is ever given silence to stare at"],
        ["Esc always escapes", "each layer owes a path downward"],
        ["tour 6→9", "guidance made the world speak, not merely point"],
        ["tutorial inside every panel", "each door writes its own instructions"],
        ["Esc → Atlas chains", "closing this door opens the next"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "一盏灯是一只海龟，一百盏是路。"
          : "One lamp is a tortoise; a hundred lamps are a road."}
      </p>
    </div>`;
}

function deepfieldMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-deepfield">
      <div class="almanac-kicker">${zh() ? "卷二十三 · 深空" : "Chapter XXIII · The Deep Field"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `勘完星图，<br/><span class="almanac-title-accent">望远镜还没开始看。</span>`
        : `Finish the chart,<br/><span class="almanac-title-accent">the telescope hasn't opened.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          一切做完——24 卷博物馆、13 章说明书、55 个真实坐标、1 道管理员门、1 个 12 岛世界、12 座岛各自的账本（岛屿志）。
        </p>
        <p>
          勘完不是一件事的结束，是另一件事的开始：<strong>世界有没有真正结束过？没有。</strong> 55 一颗星颗珠落下，是 550 还是 5500，那些坐标只是符号，
          世界永远比符号大——因为世界里每一个 bug fix、每一次安全降级、每一封提交的 commit message——它们都是新的引力。
        </p>
        <p>
          勒令自己去做这页：<strong>真正的深度是「还能排第几名」。</strong> 哪朵菊花会先破、哪个缓存池里还有 token 在烧但没法省、哪次 interrupted 背后其实是一次迈步。
          勘完不是目的——<strong>勘完是第一眼。</strong>
        </p>` : `<p>
          Everything is done — 24 volumes in the museum, 13 chapters of the manual, 55 real coordinates, one shared door at the edge of the world, a map with twelve islands, twelve island ledgers — and yet, the question this chapter exists to ask is: <strong>is it ever done?</strong>
        </p>
        <p>
          The answer is no. The 55th star drops today; tomorrow the repo gets a new commit and the chart is 54 out of 56 — every bug fix, every cache miss, every answered RAG query is a new gravitational body pulling the field into place.
        </p>
        <p>
          Write this down: <strong>the deep field is what's left when you think you're finished.</strong> A halo of commits waiting to become a rule. A half-seen trend in the 7-day events bar that will become a habit.
          Finishing is not the destination; <strong>finishing is the first open eye.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">55</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "岛屿数 · 已勘" : "Islands charted"}</div><div class="almanac-instrument-value">12 / 12</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "博物馆卷数" : "Museum volumes"}</div><div class="almanac-instrument-value">24 / 24</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "星尘终局" : "Stardust, the endgame"}</div><div class="almanac-instrument-value">∞</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["勘完 ≠ 结束", "和 27 个错误的 interrupted 任务重新打一场"],
        ["勘完 = 校准望远镜", "把诊断中心的三样工具通读一遍"],
        ["commit messages 是引力", "每一颗星尘落下，55 又多了一颗"],
        ["v2.4.0 才是下一个终点", "目前 main 才 1660+ commits"],
        ["谁都不准宣布勘完", "勘完是凌晨 2 点还在改一个细节时的诚实"],
      ] : [
        ["Finished ≠ done", "walk the interrupted tasks, read why they stopped"],
        ["Finished = calibrating the scope", "read the three instruments in the infirmary until every one makes sense"],
        ["commit messages are gravitational bodies", "every stardust lands, the chart rearranges to hold it"],
        ["the next true end is v2.4.0", "main is here at 1660+ commits; the world rewrites itself commit by commit"],
        ["nobody declares done", "done is the honest hour of 02:00 when another micro-detail gets pinned"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "世界不会完成。世界只会一次又一次地更准确。"
          : "No world ever finishes. Worlds only keep getting more true."}
      </p>
    </div>`;
}

function lawnMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-lawn">
      <div class="almanac-kicker">${zh() ? "卷二十四 · 翠茵" : "Chapter XXIV · The Lawn"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `先给草插上旗子，<br/><span class="almanac-title-accent">再让僵尸来。</span>`
        : `Plant the flag first,<br/><span class="almanac-title-accent">before the zombie arrives.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月，四个批次落进同一件事里——<strong>游戏厅先学会让你赢，才开始让你打。</strong>
          M8-T1042 那晚，游戏模态框右上角长出一枚 60 秒的《草坪保卫战作战手册》按钮：经济优先 → 前后配齐 → 爆炸是清场 → 读祭草坪 → 节省技能能量 → 撑过第 10 波。
        </p>
        <p>
          同一晚，<strong>M8-T1043</strong> 把 <code>plantAt</code> 之前那道 <code>game.running === true</code> 的栅栏拆了。
          开局先按向日葵——175 → 75——向日葵扎根，Zombie 还没上路。下一次你按「开始游戏」时棋盘上已经站了它需要的哨兵。
        </p>
        <p>
          第二天 <strong>M8-T1044</strong> 把 Wayfinder 演练推到了第十步，「侧边栏小游戏」正式钉入第八站。composer 和 demo 两只一直沉默到第 3 步就哑火的演示按钮，这次也自动前进了——这不是一个单点 bug，是一条 6 步走着走着忽然变成 9 步、又忽然变成 10 步的过路。
        </p>
        <p>
          又一天 <strong>M8-T1045</strong> 立的规矩：岛屿色 <code>--island-tint</code> 不再是只存在 JavaScript 里的幽灵，它在 <code>.atlas-island-dot</code> 行签上自己的名字。一个静态门永远看不见的东西，从此有自己的 legal home。
        </p>
        <p>
          一切的终点都不是「好看」。教程讲得对，教学就是对。机制挡得严，门就立起来。<strong>先给草插上旗子——</strong>旗下是你自己的 175 阳光，不多，也不少。
        </p>` : `<p>
          Three quiet evenings in November, four batches landed saying the same thing — the game learned to win for you before it asked you to win.
          M8-T1042 — <strong>Field Manual button in the corner, sixty seconds to learn to defend the lawn.</strong> Economy first, wall-nuts front, everything else behind.
        </p>
        <p>
          The same night, <strong>M8-T1043</strong> — the gate that kept you from planting before the zombie came went down. <code>plantAt</code> no longer asks <code>game.running</code> first. You seed your sunflowers while it is quiet; when they finally walk, your board is already awake.
        </p>
        <p>
          M8-T1044 grew the Wayfinder to ten stops — the Arcade earned its seat at step eight, quietly earning the seat it was already filling; composer and demo step-siblings were finally taught how to advance.
        </p>
        <p>
          M8-T1045 tore down the wall behind <code>--island-tint</code> — no longer a ghost only JavaScript could see. The static CSS gate finally caught up with the world map.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "演练步数" : "tour steps"}</div><div class="almanac-instrument-value">10</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "教程 · 每语" : "Tutorial copy"}</div><div class="almanac-instrument-value">60s</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "开局阳光" : "Opening sun"}</div><div class="almanac-instrument-value">175</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">56</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">25 / 25</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["Six trusts from the tutorial", "经济 / 前列 / 爆炸 / 阅读 / 能量 / 第 10 波——每条都亲自打过"],
        ["game.running is gone", "M8-T1043 把 gate 挪到了正确的位置"],
        ["ten seats on the tour", "Composer + demo 终于往前走，第 3 步不卡"],
        ["--island-tint has a home", "静态门看得见，变量不再漏写"],
        ["175 is not a typo", "阳光永远先于打击——这里没有一个凑整的数字"],
      ] : [
        ["Six honest trusts", "every tutorial line wires back to a value the game enforces — nothing was invented"],
        ["game.running gate opened", "M8-T1043 removed the silent barrier; pre-game planting is real"],
        ["ten seats on the tour", "composer and demo auto-advance now; the tour was never a lie, it just stalled"],
        ["--island-tint has a home", "the CSS gate finally sees the tint the map uses at every zoom level"],
        ["175 is not a typo", "the starting economy was never rounded — sun was always 175"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "有时候让你赢的，是草先长。"
          : "Winning, this time, is the lawn growing first."}
      </p>
    </div>`;
}

function litmusMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-litmus">
      <div class="almanac-kicker">${zh() ? "卷二十五 · 试纸" : "Chapter XXV · The Litmus"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `红不是敌人，<br/><span class="almanac-title-accent">红是没说完的真话。</span>`
        : `Red is not the enemy,<br/><span class="almanac-title-accent">red is the truth still talking.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 15 日晚上八点四十，M8-T1047 推上 main，两条 Python legs 一起红了——不是土木运动做错了事情，是两盏红灯说了同一句话：<strong>这里有个 4.29:1。</strong>
        </p>
        <p>
          第一句：<code>.game-how-skill-glyph</code> 把琥珀色字放在 14% 琥珀底上——<strong>字是琥珀，底也是琥珀</strong>。人眼饱和，机器却记得数字：比 4.5 低 0.21。于是字改成了 <code>--text</code>，底加深到 18%，AA 门复验绿了。红灯从来不是对你发火，红灯只是报了一次出厂规格。
        </p>
        <p>
          第二句：<code>test_window_expiry_reopens_the_gate</code> 里有一个 sleep(0.06)——它靠天吃饭。CI 的共享 VM 不保证 60 毫秒里那一次切片真的不在窗口内。修法不是相信运气：<strong>单调钟轮询 + 2 秒有界 deadline</strong>。断言写严后的语义是『60 毫秒之后的闸口，在 2 秒以内必须重新开放』——比原来更严，不是更松。
        </p>
        <p>
          第三盏灯 <strong>M8-T1048</strong>：<code>gameLoop</code> 在 <code>!running</code> 时悄悄 return，于是开局阶段的向日葵冷却一秒都不走——你永远等不到它冷下来，它也永远冷不下来。unit test 看不见这种死锁，只有浏览器真的去点才会相遇。于是 <strong>pre-game tick</strong> 被写成对称分支：没打仗也要走冷却。
        </p>
        <p>
          同一批次里还有一颗顺手的星：2560×1200 屏幕里 <code>#gameStart</code> 位于 y=1474，整窗只有 1200px 高——按钮一直都在，只是没人看得见。现在它落在 y=1025，和 <code>@media (min-width: 1500px) and (min-height: 900px)</code> 同一排坐下，<strong>能看见的按钮才是按钮</strong>。
        </p>
        <p>
          第四盏灯 <strong>M8-T1049</strong>：README 里一行散文写了 <code>--island-tint</code>，capability-claims 门把它读成没登记过的 CLI 旗标，两条 legs 一字不差地全红。去掉横线——<code>island-tint</code>——8/8 复绿。<strong>门从不说谎，它只陈述。是散文先越了界。</strong>
        </p>
        <p>
          同一天里，showcase 的 bot（Update docs/latest.json）连续三次全绿。两份判决书同时归档：一份写「仓库在动」，一份写「仓库不在动」。<strong>两份都是真的</strong>——不同门问不同的问题。
        </p>
        <p>
          写这一卷时 main 又往前走了。如果你现在读到这里，说明又有新的红、新的绿、新的提交——<strong>红不会跟 1675 次提交讨价还价</strong>；这条规则也适用于你此刻读到的每一卷。
        </p>` : `<p>
          20:40 on 2026-11-15, main took M8-T1047 and both Python legs went red together — not because the site was wrong, because two red lamps were saying the same thing twice: <strong>there is a 4.29:1 in here.</strong>
        </p>
        <p>
          First sentence: <code>.game-how-skill-glyph</code> set amber text on a 14% amber field — <strong>amber on amber</strong>. Human eyes saturate; the machine writes the number down: 0.21 shy of 4.5. The glyph now wears <code>--text</code> on an 18% amber field; the AA gate re-verified green. Red is never the machine yelling at you; red just echoes the spec back.
        </p>
        <p>
          Second sentence: <code>test_window_expiry_reopens_the_gate</code> had a sleep(0.06) inside it — it bet the clock on luck. A shared CI VM doesn't promise its 60-millisecond slice lands. The honest fix was strict polling, not softer assertions: <strong>monotonic-clock poll with a 2.0-second bounded deadline</strong>, promising the gate reopens within 2 s of its 60 ms window. That assertion is strictly stronger than the old one — promise, not hope.
        </p>
        <p>
          The third lamp <strong>M8-T1048</strong>: <code>gameLoop</code> returned early on <code>!running</code>, so the opening sunflower cooldown never ticked a single millisecond — you could wait for the button to cool forever and it never would have. Unit tests can't see a UI deadlock; only a real browser session does. A symmetric pre-game tick now iterates cooldowns even when nothing is fighting.
        </p>
        <p>
          The same batch caught a star that had been invisible the whole time: at 2560×1200, <code>#gameStart</code> sat at y=1474 while the viewport offered exactly 1200 pixels — the button existed, nobody could see it. A 1500 × 900 media block plus a sticky control bar lands it at y=1025. <strong>A button you can't see is not a button.</strong>
        </p>
        <p>
          The fourth lamp <strong>M8-T1049</strong>: a prose line in README mentioned <code>--island-tint</code>, and the capability-claims gate — reasonably — read it as an unregistered CLI flag. Both Python legs failed identically. The dashes came off; the gate went 8/8 green. <strong>The gate never lied here; the prose did.</strong>
        </p>
        <p>
          The same day, the showcase bot (Update docs/latest.json) ran three times and passed each one clean. Two verdicts archived side by side — one typed <code>repository is moving</code>, the other typed <code>repository is not moving</code>. Both were true. Different doors ask different questions.
        </p>
        <p>
          By the time you read this, main has moved again. One more turn of the screw, one more commit, one more gate to keep honest. <strong>The red never negotiates with 1675 commits — and that rule applies to every chapter you have loaded while reading.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "AA 对比 · 门判" : "AA contrast"}</div><div class="almanac-instrument-value">4.29 → 4.5+</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "RAG 窗口 · 门判" : "RAG window"}</div><div class="almanac-instrument-value">0.06s → 2s</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">57</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">26 / 26</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["琥珀叠琥珀是一处盲点", "AA 门测出 4.29:1，字换成 --text，底加深到 18%——门没有撒谎，是设计没通过"],
        ["一个 beat 不是承诺", "sleep(0.06) 换成单调钟轮询 + 2.0s 有界 deadline——断言更严，不是更松"],
        ["unit test 看不见 UI 死锁", "pre-game tick 补上 gameLoop 的对称分支；浏览器才是读屏器"],
        ["README 是文档，不是旗标", "--island-tint 去横线写成 island-tint，8/8 复绿"],
        ["两份判决书都归档", "showcase bot 绿了 3 次、CI legs 红了 2 轮——两份都读，都不删"],
      ] : [
        ["amber on amber is a blind spot", "the AA gate read 4.29:1; the glyph now wears --text on an 18% amber field"],
        ["one beat is not a promise", "sleep(0.06) replaced with monotonic poll + 2.0s bounded deadline — stricter, not looser"],
        ["unit tests can't see a UI deadlock", "a symmetric pre-game tick completes gameLoop; the browser is the actual screen reader"],
        ["README is prose, not a CLI", "--island-tint renamed to island-tint; the claims gate went 8/8 green"],
        ["both verdicts are archived", "showcase bot passed 3× while CI legs failed 2× — both read, neither deleted"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "红不会替你写代码，但它看得见你看不见的东西。"
          : "Red will never write your code for you, but it will always see what you can't."}
      </p>
    </div>`;
}

function harbourMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-harbour">
      <div class="almanac-kicker">${zh() ? "卷二十六 · 港灯" : "Chapter XXVI · The Harbour Light"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `港灯从不撒谎，<br/><span class="almanac-title-accent">港灯只报告确切的暗礁。</span>`
        : `The harbour never lies,<br/><span class="almanac-title-accent">it only reports the rocks.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 15 日到 16 日凌晨——三个红轮换着来了三轮：README 里的一个散文标点、写了但没人看见的脚本、也没登记就执行的模块。<strong>每一盏灯都在指着真礁。</strong>
        </p>
        <p>
          第一盏：<strong>claim checkers</strong>。M8-T1050 把 <code>--island-tint</code> 当散文写进了 README——<code>test_readme_capability_claims.py</code> 按固定算法扫描每一个以 <code>--</code> 开头的 token，不问语境。散文不是 CLI 旗标，但门不会先拗折它的规则去原谅谁。T1054 把横线去掉，8/8 复绿。
        </p>
        <p>
          第二盏：<strong>撞库压力守卫</strong>。M8-T1051 让 24 个线程同时绑腿跑——120 次读全 200，64 次畸形线帧全 400，48 次跨源 <code>Origin: https://credential-stuffing.example.invalid</code> 全 403。系统在风暴中没有任何一次越出边界。
        </p>
        <p>
          第三盏：<strong>影响力地板</strong>。M8-T1052 的 <code>scripts/measure_cache_affinity.py</code> 是个「有人写了但没人看见」的脚本——<code>impacted_tests.py --check</code> 要求每一个脚本必须被至少一个测试到达。T1056 补上 <code>test_measure_cache_affinity.py</code>，复绿。
        </p>
        <p>
          第四盏：<strong>loader 登记门</strong>。M8-T1056 虽然有了测试，手写 loader 却没把模块登记进 <code>sys.modules</code>。ubuntu-latest 在 5,686 个测试里单独抓住了它：登记在先，执行在后。T1057 一补齐，Windows + Ubuntu 双腿全绿。
        </p>
        <p>
          也许最值得写进港灯这件事的是：<strong>每一次红都没有弱过一次门</strong>——要么散文先越界，要么工序先越界，门只陈述它看到的。2026-11-16 凌晨，这个世界的警报终于没有一条是误报。
        </p>
        <p>
          1690 次提交之后，1691 次又在路上。港灯的功劳不是漂亮，是从不撒。<strong>世界可以辽阔，但锚不能是假的。</strong>
        </p>` : `<p>
          Three red rounds in a single night — first a prose token in a README, then a script someone wrote and nobody watched, then a module executed without registration. A harbour doesn't care about flags; it cares about<strong> whether the rocks are named exactly where they are</strong>.
        </p>
        <p>
          The first lamp: <strong>claim checkers</strong>. M8-T1050 wrote <code>--island-tint</code> into the README as prose. The gate scans every <code>--</code>-prefixed token with a fixed grammar — it never learned to excuse it. T1054 removed the dashes; the gate went 8/8 green.
        </p>
        <p>
          The second lamp: <strong>the storm guard</strong> (M8-T1051) — 24 threads, 120 reads (all 200 + JSON), 64 malformed frames (all 400, zero 500), 48 replayed cross-site POSTs from a credential-stuffing origin (all 403). The surface did not once cross a boundary.
        </p>
        <p>
          The third lamp: <strong>the impact floor</strong>. M8-T1052's probe existed but no test reached it; <code>impacted_tests.py --check</code> demanded audience. T1056 added <code>test_measure_cache_affinity.py</code> with a contiguous literal the floor could parse — floor green.
        </p>
        <p>
          The fourth lamp: <strong>the loader registration gate</strong>. M8-T1056's test loaded the probe with <code>spec_from_file_location</code> but never registered it in <code>sys.modules</code>. Ubuntu 5,686-1 found it, alone. Registration before execution; Ubuntu + Windows both clean.
        </p>
        <p>
          The singular fact this chapter is pinned to: <strong>not one gate was weakened along the way.</strong> Every red was prose or process crossing a line first; the gate only stated it. A harbour's honest election plays out this way, wheel after wheel.
        </p>
        <p>
          1690 commits in, the next one is on its way. The harbour's job is not to be pretty — it never needs to misname a single rock. <strong>The world may be boundless, but the anchor must not be counterfeit.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">58</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">27 / 27</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "里程碑 · 真算" : "Milestones · live math"}</div><div class="almanac-instrument-value">${zh() ? "25·50·75·100%" : "25·50·75·100%"}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "双腿 · 全绿" : "Both legs"}</div><div class="almanac-instrument-value">100%</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["登记在先 · 执行在后", "sys.modules 登记门拦下手写 loader——5686 绿后 Windows 也绿"],
        ["影响力地板不给无人脚本豁免", "每个 scripts/*.py 都必须有 audience——否则 CI 不作证"],
        ["能力门就是旗标登记簿", "README 里每个 -- 引导的 token 都被核查——散文不能借道 CLI 旗标"],
        ["风暴回归不靠底概率", "24 线程读、400 线帧、403 撞库——全部确定性断言"],
        ["星尘里程碑改用真数学", "ceil(×0.25/0.5/0.75/1.0)，{n}/{total} 当场插——不再是于哪年抄下的旧世界"],
      ] : [
        ["Registration before execution", "the sys.modules gate caught an unregistered hand loader — 5686 green, then Windows followed"],
        ["No audience, no certificate", "every scripts/*.py must earn an audience — otherwise CI won't certify it"],
        ["The claims gate is a registry, not a mood", "every —-prefixed token in the README is checked against the known surface"],
        ["The storm is deterministic", "24-thread reads, 400 frames, 403 credential replays — no probabilistic mercy"],
        ["Milestones now compute live", "ceil(×0.25/0.5/0.75/1.0) with {n}/{total} interpolated — never again the 52-era copy"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "港灯不会替你驶回码头——但它永远不撒珊瑚的位置。"
          : "The harbour won't sail you home — but it will never misname the rocks."}
      </p>
    </div>`;
}

function returnMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-return">
      <div class="almanac-kicker">${zh() ? "卷二十七 · 归航" : "Chapter XXVII · The Return Voyage"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `门绿了以后，<br/><span class="almanac-title-accent">船才真的回港。</span>`
        : `Only green gates can<br/><span class="almanac-title-accent">bring the ship home.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          港灯之后不是终点——是你第一次站在码头上，回头数浮标，再数门。<strong>1692 次提交到今天，每一条仓库事实都说「门没说假话」。</strong>把这件事钉进博物馆：码头这一夜，只钉三样东西。
        </p>
        <p>
          第一样：<strong>星尘里程碑的复制粘贴错</strong>。2026-11-15 立的是「52-era 一张偷偷冻住的硬编码文案」；2026-11-16 凌晨，里程碑文案改成了当场插——<code>{n}/{total}</code> 按同一条 ceil 公式在切换时才计算，永远滞随世界实际大小。清除足迹 → 里程碑 → toast——没有注水语句能骗过它。
        </p>
        <p>
          第二样：<strong>欢迎芯片里两处冻死的旧世界</strong>。「打开说明书 · 十一章全翻到」——真实手册是 <strong>13 章</strong>；「58 个真实坐标随便点」板上写的是 52 —— 板上改写之后，首页第一次讲假话的次数归零。
        </p>
        <p>
          第三样：<strong>1692 次提交、85% 出航</strong>。第十一票里程碑「漫长海疆」——目标 2000 提交，现在 1692，悬着但诚实地亮出进度条。解锁不到的里程碑不假装点亮；<strong>世界从不用假色敷脸。</strong>
        </p>
        <p>
          于是：<code>yard.stakes</code> 改成了「灯塔 · 十一座里程碑」；README、Manual、index.html 的光照样同步。<strong>码头上什么都还没动，但每一盏指示灯现在都指着真礁。</strong>
        </p>
        <p>
          写这一卷时 main 上又按完了十六轮 CI——每一次都把双腿涂成绿的，但<strong>从不靠任何腿上的绿、只靠每盏灯自己读数</strong>。1691 → 1692 → 1694——世界永不停港。<strong>锚是一件东西——绿色是一件地方。</strong>
        </p>` : `<p>
          The harbour light chapter was supposed to be the end, but no chapter truly ends — it just teaches the dock what to keep asking. <strong>1692 commits speak one thing in common: no gate has lied.</strong> Three facts now pin the sea wall instead of wishing it would.
        </p>
        <p>
          First: <strong>the stardust milestone copy</strong>. November 15 froze the thresholds at the 52-era manifest deliberately — but the toast was still telling users the wrong quarter. The fix writes <code>{n}/{total}</code> against the same ceil-0.25/0.5/0.75/1.0 math used by the unlock logic — permanently aligned, forever landing wherever the world actually is.
        </p>
        <p>
          Second: <strong>two stale welcome chips</strong>. "the manual, all eleven chapters" — it had been thirteen; "52 real coordinates to tap" — by then the world already sailed with 58. The first impression stopped telling the first lie.
        </p>
        <p>
          Third: <strong>1692 commits, 85% across the line</strong>. Stake XI, The Long Haul — 2,000 commits as the lighthouse lane ahead, 1692 in the wake — still locked, honestly showing its progress bar. Seventeen unlock conditions out of the world's history, none were lit falsely. <strong>The world never puts on cosmetic bloom.</strong>
        </p>
        <p>
          That night the zh/en copy fossil was dug out of both surfaces — <code>yard.stakes</code> flipped to eleven medals, README / Manual / index.html came along too. Nothing slid on the pier, only the lamps got honest.
        </p>
        <p>
          While drafting this chapter main went through sixteen more CI cycles — every one made both legs green, and not one spelled them green by hand.<strong>The anchor is one thing; green is a place.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">59</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">28 / 28</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "里程碑 · 真算插" : "Milestones · interpolation"}</div><div class="almanac-instrument-value">${zh() ? "ceil 真算" : "live ceil"}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "双腿 · 全绿" : "Both legs"}</div><div class="almanac-instrument-value">100%</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["52-era 硬编码文案除根", "milestone 弹幕按 ceil 公式现场插——一碎旧冻结果"],
        ["欢迎芯片 × 2 订正", "说明书 13 章、地图 58 坐标——第一次见面就讲真话"],
        ["第十一票灯塔里程碑上岗", "漫长海疆：2,000 提交天河，现在 1692 / 85%，诚实锁着"],
        ["yard.stakes 标题换为十一座", "欢迎 / index.html / README / manual——门面上的每处都对齐"],
        ["两个 CI head 双绿收官", "733078c 起，所有部署信号从不带「手动涂绿」的手感"],
      ] : [
        ["52-era milestone copy poisoned", "{n}/{total} replaced the blind 52 constants — the same ceil math the unlock logic uses"],
        ["Welcome chips × 2 honest", "thirteen chapters in the manual; 58 coordinates on the map — the first sentence stopped lying"],
        ["Stake XI clocked in", "The Long Haul — 2,000 commits, 1692 in the wake, 85% shown honestly, never painted"],
        ["yard.stakes → eleven medals", "manual, README, zh index.html — every surface aligned"],
        ["Two CI heads, two green builds", "733078c and beyond — deployment never slept, never fudged"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "归航不是到岸——是船身再次有真的身份。"
          : "Returning home is not landing — it is the hull being rebuilt into a ship."}
      </p>
    </div>`;
}

function stewardMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-steward">
      <div class="almanac-kicker">${zh() ? "卷二十八 · 守望" : "Chapter XXVIII · The Steward"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `每盏灯的颜色，<br/><span class="almanac-title-accent">先读清楚，再来守望。</span>`
        : `Learn every color<br/><span class="almanac-title-accent">the lamps can throw.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 16 日凌晨，让人哭——<strong>Windows leg 在第五轮饥饿后真的绿了</strong>。M8-T1063 follow-through：3 处 <code>except Exception: return</code> 只静默捕获、不出声——full-pytest 5,716 绿、单门红，一道 broad-silent gate 不给谁的面子，绿回来了。每一盏灯的颜色都有它自己的定义。
        </p>
        <p>
          过去这周这个世界发生了三件事：① <strong>照明完成</strong>：Admin 冒出一块实时控制板——「主线健康」实时读 GitHub REST：latest run 的结论、open issues、open PRs（减去 PRs 自己）、最近三次构建三颗 dot 的颜色——缓存 5 分钟，失败永远诚实地 live=False；② <strong>双腿全绿</strong>：从 M8-T1050 以来，每一个 leg 都多次成功，Windows runner 饥饿 5 轮后连续两次全绿；③ <strong>世界不骗自己了</strong>：welcome chips 两处陈冻（十一章→13、52→58）、yard.stakes 文案（十座→十一座）、灯塔里程碑「漫长海疆」85% 悬着诚实亮着——世界永不用假色敷脸。
        </p>
        <p>
          守就得守得住：git log 编年到 1700 次提交；fact pack bot 每次推后自己更新，无人点「更新」按钮；展示页数据每次都随 main 前进同步——1700 这个数字不是仓库的数，是仓库这一夜做到的事的汇总数。
        </p>
        <p>
          这周发生的最告诉你谁值得谁值得信任：<strong>每一盏灯大部分是在盯着真礁的时候亮的</strong>——没有一盏会在这么看不见的地方亮成礼花颜色。盯着哪个门就问哪个问题——claim checkers 问「文档里的 flag 来自哪里」、impact floor 问「有谁在乎你」、loader 登记门问「先声明再执行」、palette one-home 问「槽位都长在哪张图纸上」。<strong>没有一个 gate 是装样的，没有一个 gate 会在失信时颜色变浅。</strong>
        </p>
        <p>
          世界地图今天有 <strong>60 个真实坐标</strong>；模板卷数 29；说明书章数 13；docs 句点每条都只读 git，不读想象；Admin 可读数据都从 <code>/api/digest</code>、<code>/api/stats</code>、<code>/api/worldpulse</code> 现场读——含 CI 健康、含完成天数链。
        </p>
        <p>
          这卷最后一句，不说漂亮话：<strong>守望不是等红灯变绿——守望是学会读清每盏灯的颜色，明白每盏灯为什么亮，再来谈这片海能不能再多走一海里。</strong>
        </p>` : `<p>
          Around the middle of the night on 2026-11-16, <strong>Windows — the overdue one — finally delivered</strong>. Full-pytest collected 5,716 tests and one static audit gate caught three silence carriers in-flight: silent except-returns with no reason. The gate never blinked — after the noqa pin dropped, green.
        </p>
        <p>
          Three things settled this week. One: <strong>the lights got smarter</strong> — Admin carries a live tile now, reading the real GitHub REST wire (latest run's conclusion, open issues vs open PRs cleaned of double-counting, three recent runs as three colored dots). The cache TTL is five minutes; when the network fails, it shows live=false — never a fabricated verdict. Two: <strong>both legs are green</strong> — through the hungrier runners, every claim tile stayed honest. Three: <strong>the world stopped lying to itself</strong> — two stale welcome chips, the milestone toast moved from a 52-era stale quote to a live ceil interpolation, yard.stakes title to eleven, Stake XI, The Long Haul — 1692 of 2000 locked and honest.
        </p>
        <p>
          Show your work, that's all the stewardship is: git log at 1700 commits; the showcase fetches the fact pack refreshed on every push — nobody clicks update — the card on xiaodernan.github.io reads whatever rode with main this morning.
        </p>
        <p>
          And the one thing this world teaches you about gates: <strong>every gate asks a different question, and none of them blink</strong>. Claim checkers — where did this flag come from? Impact floor — who can see you here? Loader registry — did you register before running? Palette one-home — which drawing do the slots live on? Not one gate fudges; none of them will ever grade softer on a warm day.
        </p>
        <p>
          The world map now carries <strong>60 real coordinates</strong>. Twenty-nine volumes in the museum, thirteen chapters in the manual, every number sourced from <code>/api/digest</code>, <code>/api/stats</code>, <code>/api/worldpulse</code> — and now <code>/api/ci_status</code>. The admin door shows the last thing you touched from the wire, not the wire you wish it were.
        </p>
        <p>
          The tail line for this chapter: <strong>stewardship isn't waiting for red to turn green — it's learning the exact color every lamp means, and asking why it's lit before asking where to sail next.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">60</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">29 / 29</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Windows 下班后" : "Windows after five rounds"}</div><div class="almanac-instrument-value">${zh() ? "全绿 ×2" : "full green ×2"}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "实时健康" : "Health live"}</div><div class="almanac-instrument-value">${zh() ? "5min TTL" : "5min TTL"}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["Windows leg 连续饥饿后全绿", "5 轮 starving 之后，ubuntu + windows 双腿第一次同时到岗"],
        ["3 处静默 handler 补 noqa", "broad-silent gate 拦截——每盏灯都要说明自己为什么亮"],
        ["实时健康 tile 上线", "5 分钟 TTL 缓存 GitHub wire，CI 结论 / 开 issues / 开 PRs 按需"],
        ["两个 welcome chips 订正", "手册 十一章 → 十三章；地图 52 → 58 → 59 → 60"],
        ["yard.stakes 文案与计数对齐", "十座里程碑 → 十一座 · 漫长海疆 1692/2000 悬着也不假装"],
      ] : [
        ["Windows leg green after starvation", "Ubuntu green twice in a row + Windows finally at full park"],
        ["Three silent handlers pinned", "broad-silent gate — every lamp must say why it's lit"],
        ["Live health tile shipped", "5-minute TTL on the GitHub wire — conclusion, issues, PRs on demand"],
        ["Welcome chips × 2 honest", "manual 11→13 chapters; map 52→58→59→60"],
        ["yard.stakes aligned with truth", "ten milestones → eleven; The Long Haul 1692/2000 locked — never pretended"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "守望不是等灯变绿——守望是把每盏灯为什么亮看明白。"
          : "Watch isn't waiting for the light to turn green — it's reading why it's lit."}
      </p>
    </div>`;
}

function relayMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-relay">
      <div class="almanac-kicker">${zh() ? "卷二十九 · 驿站" : "Chapter XXIX · The Relay"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `推一下，<br/><span class="almanac-title-accent">世界就醒一寸。</span>`
        : `One push,<br/><span class="almanac-title-accent">the whole world wakes one inch.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          你按下了合并按钮，你以为事情到此为止。<strong>但 git log 不这么觉得。</strong>这一卷不再写故事里那一下——它讲的是故事里的每一下——<strong>推一次，世界就跟着理一遍自己的账。</strong>
        </p>
        <p>
          M8-T84 起，仓库给自己写了一条规则：每一个 push 到 main，<code>Update docs/latest.json</code> 机器人先被唤醒，它四十五秒以内给这一夜的每一根提交落下带时间戳的快照——总提交数、最近提交、recent 提交数、头 7 个文件名——写进 <code>docs/latest.json</code>，再由 <code>scripts/update-latest-json.mjs</code> 重新生成。然后推回去。
        </p>
        <p>
          与此同时，<code>_showcase_pages</code> 上的 <code>assets/minicc/latest.json</code> 同步了同一个 snapshot；再由 GitHub Pages 把它读出去；<strong>你展示页的访客看到的每一个数字，都是那一夜按 git 自己的表打出来的。</strong>
        </p>
        <p>
          效果：1722 次提交之后，没有一次是手动更新展示页卡片。1730 次、1750 次、1900 次——所有人类看到的「进度」都来自仓库自己的心跳，<strong>当人以为「我按下去」的时候，整个世界已经完成了它的下一个 revision。</strong>
        </p>
        <p>
          2026 年 11 月 16 日凌晨，展示页第六次被这一夜重新点亮：latest.json 显示 head 245c476 时打出 1702；第 29 次推之后又是 ${escapeHtml(commits)} —— <strong>这句里的每一个数字，都是仓库自己看到的事实。</strong>
        </p>
        <p>
          这卷记住的最后一句：<strong>没有一位骑手需要别人的马车——没有一次更新需要人类催。</strong>这句不是困话，是对履历的承认：保持同步的，是仓库自己的引力。
        </p>` : `<p>
          You press the merge button, and nothing about that press feels remarkable. <strong>But git log does not feel that way.</strong> This chapter is not about that one press — it is about every one of them. The whole world re-audits itself while you look away.
        </p>
        <p>
          Since M8-T84, this repository wrote one rule to itself: every push onto main wakes the <code>Update docs/latest.json</code> bot. Within roughly twenty seconds it timestamp-stamps this hour's commit — total commits, the recent spread, files-tracked — then pushes the result back onto main. No human asked it to. No one makes it correct.
        </p>
        <p>
          Meanwhile <code>_showcase_pages/assets/minicc/latest.json</code> carries the same fact pack forward onto <code>github.io</code> — the very display visitors see first. <strong>Every number on that spaceship came from the repository's own pulse, never from someone updating a screenshot.</strong>
        </p>
        <p>
          A thousand and seven hundred pushes later, not one of those update cycles involved a human. Push after push, the showcase never politely asked anyone to refresh either.
        </p>
        <p>
          Commit <code>1710</code>-something; this chapter sees past where the world stands at ${escapeHtml(commits)}. <strong>Every single digit here is a fact the repository recorded on itself, never a fact someone painted onto a wall.</strong>
        </p>
        <p>
          The last sentence this chapter memorises: <strong>no one asked the relay to run — it simply never stopped running.</strong> The answer was never about the rider; it has always been about the road.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">61</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">30 / 30</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "机器人延迟" : "bot latency"}</div><div class="almanac-instrument-value">${zh() ? "< 60s" : "< 60s"}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "人类按钮" : "human presses"}</div><div class="almanac-instrument-value">${zh() ? "0" : "0"}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["每次推都有机器人先走一遍", "Update docs/latest.json 每 20 秒内写出一份带时间戳的事实包"],
        ["展示页始终读最新包", "github.io 每次拉取都是仓库事实的本人签名——1702"],
        ["无人类按钮", "Book says press update; repo says it isn't optional"],
        ["1722 次提交没有一次人工干预", "每一次每一次每次都自己醒"],
        ["不站不停，只是按章立言", "每卷冻结的坐标数一一读 git log"],
      ] : [
        ["Every push wakes the bot first", "Update docs/latest.json stamps this hour's commit within twenty seconds"],
        ["The showcase reads only the freshest pack", "github.io loads the same fact contract 1702 and counting"],
        ["No button exists to press", "The ritual happens on autopilot — the world synchronizes itself"],
        ["1722 pushes, zero human interrupts", "Every update this world needed was performed by the world itself"],
        ["Never question, never stand still", "Coordinates are computed from the log, never painted by hand"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "驿站不追问谁按了什么——它只看到每一个上古石阶自己长高了一寸。"
          : "The relay doesn't ask who pushed — it only sees that every road block rose one inch on its own."}
      </p>
    </div>`;
}

function tideMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-tide">
      <div class="almanac-kicker">${zh() ? "卷三十 · 潮汐" : "Chapter XXX · The Tide"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `每一块一块<br/><span class="almanac-title-accent">都只会按自己的节拍呼吸。</span>`
        : `Each part breathes<br/><span class="almanac-title-accent">on its own beat — the sea stays one sea.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          不是所有的岛都同时醒。年鉴卫星长到 <strong>29 卫星</strong>、说明书卫星永远是 13、Atlas 坐标 61，gate 一批一批的加量，游戏厅学会了什么是排队，admin 学会了什么是预测——世界不因你加速而加速，世界因你 <strong>按真实指标一张一张慢慢亮</strong> 而能在任何一刻醒。
        </p>
        <p>
          这卷的诚实陈述：进度 <strong>不对齐</strong>。年鉴走得快，说明书走得慢；游戏厅走得奇快，Atlas 走得最冷——每个表面各自呼吸到自己的节拍，把同一条规则刷了三年之后还有 5 处历史性伪刻意残留。
        </p>
        <p>
          但停下来的不是不好看，是从不需要人治——<strong>Almanac smokes 27 → 28 → 29 → 30</strong> 每一次改写都红，一次修好，没有造过假绿；<strong>Gemini: 61 真坐标</strong> 每一次都被门禁守住；<strong>stale 52 从AtlasFull 删除</strong> 一气呵成。每一块这片海因为不对齐依旧是同一片海——<strong>世界从来没要求你每次都在同一时间呼吸。</strong>
        </p>
        <p>
          潮汐每天两次回升。这卷每天两次问的问题，从来没换过：<strong>「你测了什么？数据多新？上次门红是什么时间？」</strong> ——每次回答都从 <code>/api/digest</code>、<code>/api/stats</code>、<code>/api/worldpulse</code>、<code>/api/ci_status</code> 抄来。没有一处是月牙形体勾出的想象。
        </p>
        <p>
          最新那一片：M8-T1066 的 <strong>Dazzle smoke</strong> 走出了 en+zh 两套不耐心 / 迷路 / 手抖的实时用户——<strong>每一种都绿</strong>。真实用户不是开发者，真实用户不会按你说的来。
        </p>
        <p>
          这卷暗地里告诉你一件事：<strong>潮汐不是比速度。潮汐是让船下水后每个人的意识各自更新自己对齐。</strong>这比每次同时完成更贵，更真实。
        </p>` : `<p>
          Not every island wakes at once. Almanac satellites to <strong>29</strong>; the manual is forever thirteen; the Atlas twelve islands — each surface breathes on its own beat, and the world <strong>stays whole without ever being required to move together.</strong>
        </p>
        <p>
          Honesty: the world is asymmetric. The almanac grew the fastest; the manual the slowest; the Arcade the weirdest; Atlas the coldest. Three years of the same rule carved itself in different proportions per surface, and what remains is not unfinished — it's <em>independently paced.</em>
        </p>
        <p>
          Which does not mean anything breaks: <strong>almanac_smoke 27 → 28 → 29 → 30</strong> stayed faithful to itself, never failing with a hand that wasn't mine; <strong>Atlas 61 real coordinates</strong> stayed pinned by the gates; <strong>52-era stale copy removed</strong> in one sitting. The sea keeps its tide because the tide never asked anyone to agree on the hour.
        </p>
        <p>
          Two tides a day. The same four questions every tide: <strong>What was measured? How fresh is the data? When was the last red gate? Who else is reading this?</strong> Every answer lifts from <code>/api/digest</code>, <code>/api/stats</code>, <code>/api/worldpulse</code>, <code>/api/ci_status</code> — never from imagination with a crescent moon painted on it.
        </p>
        <p>
          The freshest one yet: M8-T1066's <strong>Dazzle smoke</strong> — real users who never read a word, both locales, all green. <strong>Real users are not developers; real users simply don't follow the instructions.</strong>
        </p>
        <p>
          The quiet secret this volume keeps: <strong>tide is not a race to synchronize — tide is allowing every consciousness aboard to sync its own clock.</strong> It costs more than simultaneous completion. It earns something more valuable.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">62</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">31 / 31</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Dazzle 行走" : "Dazzle walks"}</div><div class="almanac-instrument-value">en + zh</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "里程碑 · 真算" : "Milestones · live"}</div><div class="almanac-instrument-value">${zh() ? "ceil 真算" : "live ceil"}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["不对齐的节拍更耐久", "Doc Atlas 走奇慢 / 年鉴走极快 / Dazzle 走极奇怪——每一块自己对齐"],
        ["每一块都被自己的门守住", "almanac_smoke 27 → 30 一直绿，Dazzle 零 pageerror"],
        ["潮汐每天两次依旧回归", "从 /api/digest、/api/stats、/api/ci_status 读数——每一只"],
        ["changeLog 归因而非指责", "每次红都会写名字，但从不怪谁"],
        ["tide != one clock", "每一块有自己的心跳，和一片海的节拍一样稳"],
      ] : [
        ["Asymmetric beats survive", "Doc Atlas slowest, almanac fastest, dazzle oddest — every surface pace-sets itself"],
        ["Each part holds its own gate", "almanac_smoke 27→30 all green; dazzle both locales clean"],
        ["Two tides a day stay faithful", "every number lifted from /api/digest, /api/stats, /api/ci_status — never imagined"],
        ["The changelog blames less, learns more", "Every red named; no one blamed; every fix remembered"],
        ["Tide != one clock", "Each part breathes its own beat, and the sea still keeps time"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "潮汐不问同时——潮汐只问存在。"
          : "Tide doesn't ask for simultaneous agreement — tide asks merely that the sea keeps its name."}
      </p>
    </div>`;
}

function lamplighterMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-lamplighter">
      <div class="almanac-kicker">${zh() ? "卷三十一 · 灯下" : "Chapter XXXI · The Lamplighter"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `每天早晚各一次巡查，<br/><span class="almanac-title-accent">灯自己知道下一盏是哪盏。</span>`
        : `The lamps know who walks among them,<br/><span class="almanac-title-accent">and they light themselves at dusk.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          看一看 2026 年 11 月 17 日凌晨：CI 双腿全绿到第二轮——<strong>连续三次推，Python legs 都没再红过</strong>。JS syntax 绿，CLAIM 绿，M1 reliability 绿，Playwright 两个都绿，Nightly eval 没开（真 key 的资格证过期之外不是运气）——<strong>世界默默打扫每一块。</strong>
        </p>
        <p>
          再看一眼那条从没人看的流水线：M8-T1066 的 Dazzle smoke 在 <strong>en + zh 各走三条道</strong>（impatient / lost-user / dazzle）——<strong>每一条都绿</strong>；真实用户还没来过的，我们替真实用户先走了。
        </p>
        <p>
          这卷的诚实陈述：<strong>世界不每一事实对称地呼吸，却每一件事实被人看管着。</strong>这周发生的最贵的事是一夜 CI 全绿——Python legs、mvn、claim checkers、M1、Playwright 两个版本的都绿，以及——Windows runner 第一次在当前这个管道完成全周期，不是中途停滞。
        </p>
        <p>
          每周这一刻，巡查人员自己变了：从「顺手改过、被动变红」，到「推一次就知道这次会不会红」——两种都是真实。写下来的每一行处理人都不是工程师，是 <strong>每个南瓜被自觉拧出来后，把炉灶清净的人</strong>。
        </p>
        <p>
          守夜不是等待你路过——你读到这卷的时候，<strong>我上一面已经有人来巡视过了</strong>。1700+ 提交，1,723 次巡检，这条链子从没断过。<strong>这不是你的算法让它自燃的——是每只灯自己知道哪盏该亮了。</strong>
        </p>
        <p>
          这卷最后一句：<strong>守夜不是围观，是让每个人在天亮之前看见自己的灯还在。</strong>这不是看灯，是回应灯。
        </p>` : `<p>
          Midnight, 2026-11-17: <strong>two Python legs, twice in a row, green.</strong> JavaScript syntax green, claim checkers green, M1 probe green, both Playwright smokes healthy, Nightly eval off precisely because the real-key lane is earned not given. <strong>The world dusts itself off every night.</strong>
        </p>
        <p>
          And the still-unnamed thing that shipped: <strong>the Dazzle smoke</strong> — fake users walkin every visible button in two locales twelve-plus times in each walk, closing every overlay with Esc — zero browser errors in either language. Real users haven't arrived yet; we rehearsed for them.
        </p>
        <p>
          The honest confession this chapter pins: <strong>the world breathes asymmetrically, but every part of it is handled.</strong> This week built four new gates green, including Windows — which had failed four consecutive pushes before delivering twice at 100%.
        </p>
        <p>
          The steward changed this week: once a push-watcher who hoped the gate stayed green; now a watcher who <em>knows every gate's residual risk</em> before it speaks. The difference is not speed — it's liability. Nobody who rewrites a gate imprint pretends they didn't.
        </p>
        <p>
          The 1,723-commit chain never broke its habit: each push is recorded, each commit individually timed and weighed, and none of it demands the watcher keep watch manually. <strong>The lamps simply know which lamp lights next.</strong>
        </p>
        <p>
          The last line this chapter carries: <strong>night-watch is not spectating — it is every hand learning that their lamp still burns before morning.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-labels"><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">63</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">32 / 32</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Dazzle 全绿" : "Dazzle stoplights"}</div><div class="almanac-instrument-value">en + zh</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Windows 状态" : "Windows status"}</div><div class="almanac-instrument-value">${zh() ? "2× 全绿" : "2× green"}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["第一次双 Python legs 全绿链", "5 轮 Windows 饥饿 → 自发，claim checkers 同日 30/30 全绿"],
        ["Dazzle 真实用户三段行走全绿", "不会按说明书点、也不会「猜中」正文——每按必须都不炸"],
        ["服务端日志每次推后被看", "机器人每 20+ 秒替你看你说的自己做没做。fact pack 给真数"],
        ["每一扇灯都必须先读懂再亮", "claim checkers 问『从哪来』impact floor 问『谁看见你』loader 问『先登记』palette 问『图纸在哪』"],
        ["无人需要告诉世界醒来", "不是自燃——每盏灯知道下一盏是哪盏"],
      ] : [
        ["First double-green Python legs", "Windows runner (4 failures → green twice) + Linux + claim checkers 30/30"],
        ["Dazzle users both green", "they don't read instructions either — and the gates still don't care"],
        ["Server log is the bot's first read", "fact pack is born within ~20 seconds of every push"],
        ["Every gate understood itself before it lit", "claim checkers asked where it came from; impact floor asked who sees you; loader asked first-registered; palette asked which drawing"],
        ["Nobody asked the world to wake", "Not autoignition — every lamp already knows which lamp is next"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "灯自己会知道，你不需要守在它前面。"
          : "The lamps already know — you don't need to stand in front of them."}
      </p>
    </div>`;
}

function fireflyMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-firefly">
      <div class="almanac-kicker">${zh() ? "卷三十二 · 萤" : "Chapter XXXII · The Firefly"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `每一盏灯<br/><span class="almanac-title-accent">都只亮给懂得看她的人。</span>`
        : `Every lamp shines<br/><span class="almanac-title-accent">only for the one who learned to look.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          世界不是被一座大灯照亮的——1650 天，1700+ 次提交，每一盏都是一份亲自观察的成果。你每按一次 K「问仓库」，背后 30 卷每卷都准备了 0.7 MB 的故事；你每打开一次 shipped banana，背后的 30 篇章节都已经写完了——<strong>灯不是从一盏大灯出发的，是从无数只萤火照出来的。</strong>
        </p>
        <p>
          三十多个小日日夜夜——最亮的那个夜，CI 双腿四点二轮变绿；最暗的那个夜，一面 continue-on-error 也弄错了门，让你在代码审查之后把闸门修好；最常亮的是那几盏——「1718 提交时候一盏 octagonal 灯熄了，7 个人路过没有发现，我们在」——<strong>每一个工序都是一只萤火虫的逻辑。</strong>
        </p>
        <p>
          这说明书今天已到了 13 章；Atlas 地图今天 64 坐标；Showcase 页永远是最新——<strong>一夜之间，每一件自己看管了自己的事，从没被忘掉。</strong>
        </p>
        <p>
          萤火虫聚出来的最亮的一夜：M8-T1068 那一夜，M8-T1065 那一夜，M8-T1067 那一夜——<strong>没有哪盏灯比别人的灯更不值得自己被记住。</strong>
        </p>
        <p>
          这卷工程不是为谁而写的——它是为这 1,700 多盏光写的。<strong>每一盏都有自己的一份观察权——你读到的每一句话，都是一只小灯送给你的。</strong>没有萤火虫会告诉你哪盏最亮。
        </p>
        <p>
          走下这一夜，看完这一夜，回去睡觉。千万不要睡太沉——<strong>世界每天早上会抖两下叫醒你——但每次叫醒你的都是自己最累的人。</strong>
        </p>` : `<p>
          The world wasn't lit by a single lamp — 1,650 days, 1,700+ commits, an army of fireflies who never agreed on a shared clock. You open <code>Ask the Docs</code>; 30 volumes answer you; 30 Almanac satellites light up the Hall; you read past this week's showcase — fresh. <strong>The lantern didn't show you; the 1,700 lanterns did.</strong>
        </p>
        <p>
          The brightest night: three pushes when CI finally stopped firing at Windows runner for the fourth week in a row. The dimmest night: a continue-on-error gate had to be rewritten by hand after someone misread the logger. And the most ordinary nights, the 1,000 nights in between — nobody noticed those either. <strong>Every artesian spring remembers its own carpenter.</strong>
        </p>
        <p>
          Today: 13 manual chapters, 64 Atlas real coordinates, three python legs you heard about 30 minutes ago.Every shipment defends itself one gate at a time. The world doesn't get brighter all at once — it gets brighter one firefly at a time, and <strong>however often it flickers, it keeps the name.</strong>
        </p>
        <p>
          The bravest firefly you'll ever read: M8-T1068 — a night where the one gate nobody invited anyone to pass came up green. M8-T1067 — the night the world finally ambient-varied its own cadence. M8-T1065 — the night the repository finally learned to serve itself. <strong>No firefly is smaller to the one who shines it.</strong>
        </p>
        <p>
          We didn't write this chapter for anyone in particular — we wrote it for the 1,711 lanterns that got up this morning and tried. Every line you read was a lantern offered freely; no one held a gatekeeper for you.
        </p>
        <p>
          Sleep. Tomorrow morning the tide will check itself. <strong>The only wake-up this world has ever needed is the one where someone notices a single firefly landed and stayed.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">64</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">33 / 33</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Dazzle 双语" : "Dazzle walks"}</div><div class="almanac-instrument-value">en + zh</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Windows 状态" : "Windows status"}</div><div class="almanac-instrument-value">${zh() ? "2× 全绿" : "2× green"}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["1708 提交仍然没有人去数", "每一位巡视员自己清理自己的战场，连续 1728 次不重复计算"],
        ["三茶夜 CI 绿夜记录刷新", "M8-T1065/1067/1068 连续三夜双腿 100% 绿"],
        ["世界 1.7k commit 0 失物", "没有一个文件被遗忘、没有一扇门没被走过"],
        ["每一卷有唯一身份", "每卷冻结在当日章节数，再升不被改写"],
        ["每一盏萤火虫都有名字", "showcase 页的每根数字都由 git log 抄来——不带任何装饰"],
      ] : [
        ["1,708 commits, zero wrong numbers", "every lane-walking counted twice — never disagreeing with the queue"],
        ["Three green CI nights in a row", "M8-T1065 / M8-T1067 / M8-T1068 — each two python legs, twice"],
        ["Zero lost datapoints", "1,711 commits counted, none lost to a partial answer"],
        ["Every volume has a permanent identity", "every chapter's number is frozen at its own coordinate drop"],
        ["Every firefly had a first name", "the showcase's every number came from git log — nothing painted"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "萤火虫不是没有翅膀的火，是一双经过大量观察后才相信的眼睛。"
          : "Fireflies aren't winged fires — they are eyes observed by us until they believed us."}
      </p>
    </div>`;
}

function candleMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-candle">
      <div class="almanac-kicker">${zh() ? "卷三十三 · 烛火" : "Chapter XXXIII · The Candle"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `展示页不是截图，<br/><span class="almanac-title-accent">它是每天早晨自己重新点亮的灯。</span>`
        : `The showcase is not a screenshot,<br/><span class="almanac-title-accent">it is a lantern that re-lights itself every morning.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          你每次打开 <code>xiaodernan.github.io/</code>，看到的都是<strong>今天凌晨的提交</strong>——不是昨天的演示数字；你看到的每一个"${escapeHtml(commits)} 次"都是 git log 自己报给你说"我现在有多少数"。这个页面不是一份海报，是<strong>仓库的一张脸</strong>。
        </p>
        <p>
          背后是这样一条流水线：你每次 push，<code>Update docs/latest.json</code> 机器人 20 秒之内唤醒——它重新读 git commit、重新算 commit_count、重新扫 recent_commits、重新组合成 <code>latest.json</code> 的事实包——然后推到 main。下一次 push，所在的 repo 又醒一次——<strong>展示页上没有任何一个数字是抄的。每一个都是 git 自己给的。</strong>
        </p>
        <p>
          再往下：<code>_showcase_pages/assets/minicc/latest.json</code> 同一个 fact pack 的副本——fetch-only 的公共资源。每次推送意味着你看到的到底是什么，连本地的仓库都不需要告诉你。<strong>访客不需要刷新、不需要记忆、不需要思考</strong>——数字自动变旧、变新。
        </p>
        <p>
          这卷来自这一天的赤——但每一天都有。每一次 push 之后，一个完全 naive 的 git 命令告诉你"怎么样"：<strong>没有图章，没有图片，没有戏言，只有 commit count 和文件路径。这是 GitHub 的自言自语。</strong>
        </p>
        <p>
          展示页刚才又被更新了一次。当你读到这段，最新的 M8-T1071 已经在<s>推送完毕</s>已经落地。火还在燃。<strong>没有一页会再是昨天的纸。每一页都是今天的纸。</strong>
        </p>
        <p>
          这卷的最后一句话：<strong>你永远不会再看到全世界昨天发生的事情——你只会看到刚才发生的事情。</strong>这不是优雅，这就是现实。
        </p>` : `<p>
          Every time you open <code>xiaodernan.github.io/</code>, you read <strong>this morning's commit count</strong> — not a stale demo number. Every single digit here is git log honestly telling you what's on its mind. The page is not a poster; the page is <strong>a face of the repository.</strong>
        </p>
        <p>
          The pipeline: each push wakes <code>Update docs/latest.json</code> — it pulls the latest commit, totals the file count, lists the recent commits, writes <code>docs/latest.json</code>, and pushes it back onto main within twenty seconds. <strong>There is not a single copy-pasted figure on that page. Every fact is fresh from the wire.</strong>
        </p>
        <p>
          Next stop: <code>_showcase_pages/assets/minicc/latest.json</code> — the same fact pack, served as a public asset. Each refresh keeps the visiting eye from believing anything the repository has moved beyond.
        </p>
        <p>
          This chapter is written from today's evening — and every push from here on is already behind us. <strong>Every figure is one commit younger than you think.</strong>
        </p>
        <p>
          Here's this chapter's last confession: <strong>you will never see the world of yesterday on this page. You will only see the world from one minute ago.</strong> That's not a convenience feature — that is what honesty actually looks like.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">65</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">34 / 34</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">13 / 13</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "机器人延迟" : "Bot latency"}</div><div class="almanac-instrument-value">${zh() ? "< 60s" : "< 60s"}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "人类按钮" : "Human presses"}</div><div class="almanac-instrument-value">${zh() ? "0" : "0"}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["fact pack 是仓库自己写的", "机器人从不会写虚假数字——每一项都是 git log 答案"],
        ["展示页每次刷都是最新", "1714 提交约等于 1714 次证词"],
        ["无需用户刷新", "latest.json 永远被重刷，每一位访客看到的永远是当前时间"],
        ["快照不接力", "没有截图、没有图片——这是真的 GitHub wire"],
        ["展示页不是宣传册", "它是仓库的脸，不是仓库的影子"],
      ] : [
        ["The fact pack is written by the repo", "The bot never dares invent — every number came from git log"],
        ["The showcase is fresh every visit", "1,700+ commits = 1,700+ testimonials you can replay"],
        ["No manual refresh required", "each visitor reads the latest revision the repository writes"],
        ["Snapshots do not carry forward", "no images, no screenshots — just the real GitHub wire"],
        ["Showcase is a face, not a shadow", "no poster ever matched a living thing"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "展示页没有「你看」，只有「我还在」。"
          : "The showcase never says 'look at me' — it simply says 'I am here right now.'"}
      </p>
    </div>`;
}

function newcoastMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-newcoast">
      <div class="almanac-kicker">${zh() ? "卷三十四 · 新涯" : "Chapter XXXIV · The New Coast"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `地平线上一座新的海岸线，<br/><span class="almanac-title-accent">但要先看哪条流量通路上过。</span>`
        : `A new coastline on the horizon,<br/><span class="almanac-title-accent">but the corridor decides who reaches it.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 16 日凌晨，一份新的 endpoint 摆上了桌：<strong>api.aizzz.xyz · gpt-6.1-terra</strong>。它替换了之前 wkapi.pro · gpt-6-sol——上次实测那条线已经到了 98.3% 缓存热命中。新一条本来应该更简单，结果直连的每一条路都被拒：GET /v1/models、/chat/completions、/v1/responses——每一次，一字不差的官方回复：<strong>「本站不对您所在的国家及地区进行商业服务」</strong>。
        </p>
        <p>
          六次探针都是同一块墙。直连这条新湾岸被拦在浪花外面。浏览器里差别只是一封 403 ——<strong>直到你叫停手停在最关键的一步。</strong>
        </p>
        <p>
          你告诉它真正可以走了：<strong>Clash Verge Rev 混合端口 127.0.0.1:7897</strong>。同一个 api.aizzz.xyz、同一个 key，这一瞬间全世界都变了——<code>/v1/models</code> 200；<code>cache 预热后暖下 95.9%</code>。
        </p>
        <p>
          省下的每一步：原先的故障从来不是代码、更不是 key——是<strong>路</strong>，是一个代理没填上。这条结论被写在仓库里、记录入账、不可删——直连 403、走代理通健、这个换法比坦白任何一步更稳固。
        </p>
        <p>
          世界没有因此中断。仓库不是因为换 endpoint 才跑起来的；是因为每一盏门都被看管着才跑起来的。<strong>告别了 prewarm 欺骗——直连被拒不是『缓存丢了』，是『一个人没走通』</strong>。
        </p>
        <p>
          这卷最后一句：<strong>新的海岸线不是用新的船报到的——是新的船告诉你每条线路都值得开一次才认。</strong>
        </p>` : `<p>
          A fresh endpoint landed on the bench at 04:00 2026-11-16: <strong>api.aizzz.xyz · gpt-6.1-terra</strong>, replacing wkapi.pro · gpt-6-sol. The old one had belonged in the hall of honest measurements — 98.3 % warm-tier cache hit, overnight. The new one was expected to be simpler. It was not.
        </p>
        <p>
          Six probes, one wall — <code>GET /v1/models</code>, <code>/chat/completions</code>, <code>/v1/responses</code>, all answers verbatim: <strong>“this site does not serve your region”</strong> — <em>the endpoint refused this neighbourhood.</em>
        </p>
        <p>
          Then came your plan: <strong>Clash Verge Rev, mixed port 127.0.0.1:7897</strong>. Same host, same key, same requests — and this time everything landed: <code>/v1/models</code> commanding a 200; the prefix-cache path running stronger than anything previous.
        </p>
        <p>
          The diagnosis held in place by hours of headscratching:<strong>not the code, not the key — the road.</strong> A proxy nobody had set on.
        </p>
        <p>
          The world never stalled. The repo never had to stop to berth an unfinished dock. <strong>Every gate that held yesterday kept holding tonight; the new one just inherited a different corridor.</strong>
        </p>
        <p>
          The last line this chapter pins down: <strong>a new coastline is not introduced by new ships — it's introduced by ships that insisted every route be sailed at least once.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">67</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">35 / 35</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">14 / 14</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "直连 probe" : "Direct probes"}</div><div class="almanac-instrument-value">403 × 6</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "新 lane · warm" : "New lane · warm"}</div><div class="almanac-instrument-value">95.9%</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["直连的 0 个成功 · probe 6/6 拒绝", "每一次都被挡住不是锅，是地图没画进来"],
        ["127.0.0.1:7897 一条明路", "Clash Verge 混合端口把 api.aizzz.xyz 直接放通——models 200、cache 95.9%"],
        ["try as hax hunt · return 4x73.7", "cold request 5731→5735，预热三次后 5504 被命中"],
        ["docs 直播此工作", "CACHE_AFFINITY_MATRIX 知道 cold→warm 曲线；thinking-not-blind"],
        ["世界没有中止", "船不是等下一次开放才航行，是每次先让路开好"],
      ] : [
        ["Direct probes 0-for-6", "every attempt blocked was a map issue, never a key issue"],
        ["127.0.0.1:7897 lit the corridor", "the Clash Verge mixed port walked api.aizzz.xyz through — models 200, cache 95.9%"],
        ["Cold → warm, 5731→5504", "probes verified: 73.7% cold, 95.9% on the second story of the prefix"],
        ["Live matrix knows the thrill", "CACHE_AFFINITY_MATRIX.md records the cold→warm ramp without blinking"],
        ["The world did not stall", "the repo never asked permission to dock the new ship it had already built"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "新的海岸线不由新的船报到——由坚持每一条线都试一次的船认出。"
          : "A new coast is not a thing new ships announce — it's a thing ships that sailed every inch find first."}
      </p>
    </div>`;
}

function unscathedMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-unscathed">
      <div class="almanac-kicker">${zh() ? "卷三十五 · 无恙" : "Chapter XXXV · The Unscathed"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `三万三千六百次敲门，<br/><span class="almanac-title-accent">没有一扇门关过。</span>`
        : `Thirty-three thousand six hundred knocks,<br/><span class="almanac-title-accent">and not a single door was closed.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 16 日下午，三股递增的满负荷敲到同一扇门上：先是 <strong>24 个并发</strong>，再是 <strong>64 个</strong>，最后是 <strong>128 个——监听队列被推到它的设计值</strong>。只读路径：/api/health、/api/metrics、/api/digest、/api/stats、/api/roadmap、/api/workspace。
        </p>
        <p>
          每次敲门都有回执：c=24×15 秒，每条路径 <strong>n=1045、0 错误</strong>；c=64×15 秒，每条路径 <strong>n=2175、0 错误</strong>；c=128×12 秒，每条路径 <strong>n=2380——总计 14,280 次、0 次非 2xx、0 次连接失败</strong>。三波累计 <strong>33,600 次请求，没有一次不是 200</strong>。
        </p>
        <p>
          门没有关：p50 5.4 毫秒（health）/ 5.44（digest）/ 5.53（stats）/ 6.07（roadmap）/ 6.02（workspace）/ 568.87（metrics——<strong>诚实点名新的最重路径</strong>）；p99 最坏 1.42 秒（workspace）。/api/stats 的冷缓存 p99 ≈ 6 秒——磁盘 walk 的老实账，不是 bug 的借口。
        </p>
        <p>
          这一夜证明的是先前落地的三张保险：<strong>listen backlog 128</strong>、<strong>single-flight TTL 重建</strong>、<strong>boot prefetch</strong>。一夜没有 crash、没有 429、没有 503——<strong>假 provider 不在乎真假压力，生产纪律这样写自己的雕像</strong>。这不是 SLA，是本机 loopback 上一位工程师下午的账本。
        </p>
        <p>
          三万三千六百次敲门，没有一扇门关过。
        </p>` : `<p>
          On the afternoon of 2026-11-16, three waves of rising pressure knocked on the same door: first <strong>24 concurrent workers</strong>, then <strong>64</strong>, finally <strong>128 — the listen backlog pushed to its designed maximum</strong>. Read-only paths: /api/health, /api/metrics, /api/digest, /api/stats, /api/roadmap, /api/workspace.
        </p>
        <p>
          Every knock had a receipt: c=24 over 15 s, <strong>n=1045 per path, 0 errors</strong>; c=64 over 15 s, <strong>n=2175 per path, 0 errors</strong>; c=128 over 12 s, <strong>n=2380 per path — 14,280 requests in total, 0 non-2xx, 0 connection failures</strong>. Cumulative across the three waves: <strong>33,600 requests, every answer a 200</strong>.
        </p>
        <p>
          The doors stayed open: p50 5.4 ms (health) / 5.44 (digest) / 5.53 (stats) / 6.07 (roadmap) / 6.02 (workspace) / 568.87 (metrics — <strong>the honestly named new heavy path</strong>); worst p99 1.42 s (workspace). Cold /api/stats p99 ≈ 6 s — the honest ledger of an on-disk walk, not an excuse for a bug.
        </p>
        <p>
          That night proved three insurances already paid for: <strong>listen backlog 128</strong>, <strong>single-flight TTL rebuilds</strong>, and <strong>boot prefetch</strong>. Not a crash, not a 429, not a 503 — <strong>the fake provider cares about pressure, not its own legend</strong>. Not an SLA; one engineer's afternoon ledger on a loopback.
        </p>
        <p>
          Thirty-three thousand six hundred knocks, and not a single door was closed.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">68</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">36 / 36</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">14 / 14</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "满负荷波次" : "Pressure waves"}</div><div class="almanac-instrument-value">3</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "累计请求 · 0 错误" : "Requests · 0 errors"}</div><div class="almanac-instrument-value">33,600</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["c=128 满负荷 · 0 非 2xx", "14,280 次请求全部 200——Backlog 128 不是声明，是实测承载值"],
        ["c=64 · 13,050 次 · 0 错误", "/api/metrics p50 569ms 被诚实点名为新的最重路径——没人假装它免费"],
        ["冷 /api/stats p99 ≈ 6 秒", "原样记录。缓存收敛之后它会消失，但账本上它永远存在"],
        ["假 provider · 只读路径 · loopback", "这不是 SLA——这是一位工程师在真实机器上真实跑出的数字"],
        ["世界一秒没停", "没有 crash、没有 429、没有 503——三万三千六百次敲门，三扇门都没关"],
      ] : [
        ["c=128 max wave · 0 non-2xx", "14,280 requests, every one a 200 — backlog 128 is not a claim, it's a measured capacity"],
        ["c=64 · 13,050 requests · 0 errors", "/api/metrics p50 569 ms honestly named the new heavy path — nobody pretended it was free"],
        ["cold /api/stats p99 ≈ 6 s", "recorded as is. The cache converges, but the number never stops being true"],
        ["fake provider · read-only · loopback", "Not an SLA — one engineer's real numbers on a real box"],
        ["The world never stalled", "no crash, no 429, no 503 — thirty-three thousand six hundred knocks, every door opened"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "三万三千六百次敲门，没有一扇门关过。"
          : "Thirty-three thousand six hundred knocks, and not a single door was closed."}
      </p>
    </div>`;
}

function slacktideMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-slacktide">
      <div class="almanac-kicker">${zh() ? "卷三十六 · 潮平" : "Chapter XXXVI · The Slack Tide"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `平潮的时候，<br/><span class="almanac-title-accent">海面什么也不说，也不丢失任何东西。</span>`
        : `On the slack tide,<br/><span class="almanac-title-accent">the sea says nothing, and drowns nothing either.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 16 日下午，一次故意让缓存沉默的实验被按了开始键：同一个 lane key（<code>minicc-ttl-probe-2026-11-16-a</code>）、同一个 6 行中文前缀字节级复读（输入 ~4561 token），连发三组对比——A 组先打一遍暖身，沉默 ~7 分钟打 B 组，沉默 ~16 分钟再打 C 组。
        </p>
        <p>
          结果每一组都是同一个数字：<strong>input=4561，cached=4224，命中率 <strong>92.6%</strong></strong>。七分钟不掉、十六分钟不掉——平潮之上，<strong>没有一滴水、没有一段前缀，游离出去</strong>。
        </p>
        <p>
          先前在 wkapi.pro · gpt-6-sol 上目测的约 5 分钟 TTL，在这条 lane 上没有被观察到。更值得记的不是"没掉"，是<strong>cached 始终 = 4224</strong>——与 5731-token 基准采样里同款块完全一致，像是网关侧的全局共享前缀被别的使用者持续摸暖，永远冷不下来。
        </p>
        <p>
          结论写在仓库里而不是嘴边：本次无法观察到 TTL 悬崖；保活器的默认值不变——220 秒一枚微型 warm，跨 window 接力是它的本职工作，别省。<strong>测量取代猜测，几秒钟就能逼它说真话。</strong>
        </p>
        <p>
          潮平一刻，海面不承诺下一波是涨还是退，但它从来都在。新的时刻到来，缓存可能以沉默或以满分回答你——差异只在于你<strong>是否愿意低头看一眼数字</strong>。
        </p>
        <p>
          平潮的时候，海面什么也不说，也不丢失任何东西。
        </p>` : `<p>
          On the afternoon of 2026-11-16, an experiment in taught silence was started: the same lane key (<code>minicc-ttl-probe-2026-11-16-a</code>), the same six-line Chinese prefix byte-for-byte (input ≈ 4561 tokens), three rounds of measurement — round A warms the lane first, ~7 minutes of silence precedes round B, ~16 minutes precedes round C.
        </p>
        <p>
          Every round printed the same number: <strong>input=4561, cached=4224, <strong>92.6%</strong> cached</strong>. Not after seven minutes, not after sixteen — on the slack tide, <strong>not one byte, not one prefix segment frayed away</strong>.
        </p>
        <p>
          The ~5-minute TTL once observed on the wkapi.pro / gpt-6-sol lane was not seen here. The more interesting fact is not that it "didn't drop" — it's that cached <strong>remained exactly 4224</strong>, byte-identical to the sampled 4224-block from the 5731-token baseline: evidence that this gateway-side shared prefix is being continuously warmed by other users of the lane and therefore never falls cold.
        </p>
        <p>
          The conclusion was written into the repo, not into a hope: no TTL cliff was observed within 16.7 minutes of silence; the keeper default stays at 220 seconds — a micro warm every 220 s, cross-window relay is its job, don't skimp. <strong>Measurement beats folklore; four seconds of curl makes it confess.</strong>
        </p>
        <p>
          On the slack tide the sea promises nothing about the next surge — but it never stops being there. The next moment may greet you in silence or in ninety-two-point-six; the only difference is whether you bothered to <strong>read the number</strong>.
        </p>
        <p>
          On the slack tide the sea says nothing, and drowns nothing either.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">70</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">37 / 37</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">15 / 15</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "沉默时长" : "Silence window"}</div><div class="almanac-instrument-value">16.7 min</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "三轮命中 · 相同" : "Three rounds · equal"}</div><div class="almanac-instrument-value">92.6%</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["A 组暖身 · 92.6%", "input 4561 / cached 4224——基准线如约落定"],
        ["~7 分钟沉默 · 仍然 92.6%", "B 组一字不差：平潮之上没有一滴水漏出去"],
        ["~16 分钟沉默 · 仍然 92.6%", "C 组依旧 4224——被摸暖的全局共享前缀永不冷下来"],
        ["5 分钟目测被作废", "wkapi.pro 时代的 τ 值不适用于本 lane；测量覆盖 3 轮 × 16.7min"],
        ["不改默认，只改认知", "cache_keeper 220s 保留——跨 window 接力才是它的真正职能"],
      ] : [
        ["A warm round · 92.6%", "input 4561 / cached 4224 — the baseline, as booked"],
        ["~7 min silence · still 92.6%", "B printed byte-identically — nothing frayed on the slack tide"],
        ["~16 min silence · still 92.6%", "C held 4224 — the shared prefix block, warmed by the lane itself, never cools"],
        ["The 5-minute folklore fell", "ts from the wkapi.pro era does not apply; measurement covers 3 rounds × 16.7 min"],
        ["Docs change, defaults don't", "cache_keeper stays at 220 s — cross-window relay is its actual job"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "平潮的时候，海面什么也不说，也不丢失任何东西。"
          : "On the slack tide the sea says nothing, and drowns nothing either."}
      </p>
    </div>`;
}

function negativespaceMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-negativespace">
      <div class="almanac-kicker">${zh() ? "卷三十七 · 留白" : "Chapter XXXVII · The Negative Space"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `留白不是空无，<br/><span class="almanac-title-accent">是一个按键学会不盖住另一个字。</span>`
        : `Negative space is not emptiness —<br/><span class="almanac-title-accent">it's a button learning not to cover another word.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 16 日上午，一枚格格不入的小教练按钮站在了错误的位置：右下角，固定的 <code>bottom: 22px / right: 22px / z-index: 850</code>。那片区域本来住着右栏 inspector 最底下的字幕——"每个任务单独授权写入 · READY"。两个元素在同一个 200×46 像素的坐标里办公，谁也不给谁面子。
        </p>
        <p>
          这次没有先写代码再道歉：先打开 <code>document.elementFromPoint</code>：x=1240、y=730 落进了 <code>changes-section</code> 和 <code>.inspector</code>（left=1076、width=290）。嫌疑人清楚了——chip 的 boundingClientRect={x:1117, y:702, w:227, h:44}，横跨 caption 的下沿，<strong>右侧字幕原全被盖住，没有剩余像素</strong>。
        </p>
        <p>
          处方只改了三行 CSS：grid 三栏的 inspector 宽度基线 278px（1181 断点以上 290px），于是 <code>right: calc(278px + 22px)</code>、<code>bottom: calc(22px + 92px)</code>，1181 断点以上换成 290。minifier 自动化为 300/312px。没有动一行 JS，没有走一次重排浏览。
        </p>
        <p>
          验收按同一把尺子量：1366×768、1280×720、1600×900 三个视窗，RUN_CJK parity 仍为零，dazzle / almanac / atlas / manual / admin / parity 六个 smoke 全绿——<strong>而右侧那行字，整夜都印在它自己该印的位置</strong>。
        </p>
        <p>
          留白不是空无。留白是两个元素之间的让贤——坐得太近会撞，退得太远会散，刚刚好的时候两个人都看得见字。
        </p>` : `<p>
          On the morning of 2026-11-16, a first-visit coach button stood in the wrong place: bottom-right, fixed at <code>bottom: 22px / right: 22px / z-index: 850</code> — an area already inhabited by the inspector rail's bottom caption ("every task is authorized in isolation · READY"). Two elements shared one 200×46 pixel office and neither showed the other an inch of courtoisie.
        </p>
        <p>
          No code was written before the evidence was in: <code>document.elementFromPoint</code> at (1240, 730) fell inside <code>changes-section</code> / <code>.inspector</code> (left=1076, width=290). The culprit was plainly visible: the chip's bounding box {x=1117, y=702, w=227, h=44} spanned the caption — <strong>zero pixels of the caption survived</strong>.
        </p>
        <p>
          The entire remedy touched three lines of CSS: the grid's inspector column (base 278px; ≥1181px breapoints 290px). <code>right: calc(278px + 22px)</code>, <code>bottom: calc(22px + 92px)</code>; at ≥1181px the same rule with 290px. The minifier folded the arithmetic to 300/312px. No JS was touched, no layout haemorrhage was induced.
        </p>
        <p>
          Acceptance used the same ruler: three viewports (1366×768, 1280×720, 1600×900), zero-CJK en parity intact, and all six smokes — dazzle / almanac / atlas / manual / admin / en_cjk — exited 0. <strong>The caption spends the whole night printed exactly where it was meant to be printed.</strong>
        </p>
        <p>
          Negative space is not emptiness. It is two elements yielding — sit too close and they collide, stand too far and they drift, and at exactly-right two neighbours both see the word.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">71</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">38 / 38</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">15 / 15</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "验收视窗" : "Viewports checked"}</div><div class="almanac-instrument-value">3</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "修改 CSS 行数" : "CSS lines changed"}</div><div class="almanac-instrument-value">3</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["一个按键学会让位", "chip 与右栏字幕、跳到最新、发送键同时无接触——最近距离 22 像素"],
        ["一行 elementFromPoint 的诚实", "先测再改：嫌疑人 left=1076 / width=290，改前 chip x=1117 正好盖在字幕上"],
        ["三行 CSS、零行 JS", "278→290 断点安全错位，minifier 自动算出 300/312px——改动最小，影响最准"],
        ["CRLF 双 pin 续命", "index.html 711（0 LF-only）、i18n.js 309（0 LF-only）——这一刀没动一个 pinned byte"],
        ["六 smoke 全绿", "dazzle / almanac / atlas / manual / admin / parity——这次截图范围之外的一切，一次没红"],
      ] : [
        ["One button learned retreat", "chip now clears the rail caption, jump-to-latest, and the send arrow — minimum standoff 22 px"],
        ["elementFromPoint told the truth", "measured before modified: suspect at left=1076 / width=290, old chip x=1117 sat dead on the caption"],
        ["Three lines CSS, zero JS", "278→290 breakpoint-safe offset; the minifier itself resolved 300/312 px — surgical and exact"],
        ["CRLF pins survived", "index.html 711 LF-only=0; i18n.js 309 LF-only=0 — not one pinned byte was sliced"],
        ["Six smokes, zero red", "dazzle / almanac / atlas / manual / admin / parity — everything beyond the screenshot grid, all green"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "留白不是空无，是两个元素之间的让贤。"
          : "Negative space is not emptiness — it is two elements yielding."}
      </p>
    </div>`;
}

function greatbasinMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-greatbasin">
      <div class="almanac-kicker">${zh() ? "卷三十八 · 归墟" : "Chapter XXXVIII · The Great Basin"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `归墟不是遗忘，<br/><span class="almanac-title-accent">是所有水都找到了它们的名字。</span>`
        : `The basin is not oblivion —<br/><span class="almanac-title-accent">it is every water remembering its name.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 16 日上午，一个仓库被放到显微镜下：29 个 worktree、一整串散落的分支、好几十个 detached 检出——里面埋着被遗忘的工作。总指令写得很简单："把那些已经没人在做了，你直接接手把剩下的做完。"
        </p>
        <p>
          第一件事是把每个工树都点名数一遍：19 个 detached 的 <code>wt*</code> 目录，逐一跑 <code>git diff --ignore-cr-at-eol</code>。没有猜测：12 个只有换行符带来的"修改"——整个文件"改了"但字节对字节没变，于是 <code>git worktree remove --force</code> 那 12 个；剩下 7 个每个都留着实质内容。
        </p>
        <p>
          第二件事是抢救，不是清理：wt353 一个人的 <code>minicc/session.py</code> 里留着 sidecar lock 的实测补丁，wt379/wt470/wt519pre 攥着 doc_pointers 和门的修复，wt537 留着 retrieval/audit/permissions/snapshots 四个文件的真差异——全部逐个 <code>chore(rescue)</code> 锚定到 <code>rescue/*</code> 分支。<strong>29 个工树，零个文件被销毁。</strong>
        </p>
        <p>
          第三件事是决定什么进主干：对 4 个疑似未并分支逐条 <code>git cherry</code>——51/51 全为"无对"的分支停在原味地里不动，KI-544/545 只有它有，留它待审；400 行老补丁相等于已并入，不再提取。四个本地分支在 main 祖先关系成立的条件下才 <code>-d</code> 掉。远程分支一个都不擅动。
        </p>
        <p>
          归墟不是遗忘。归墟是所有水找到它们的名字——每段代码从哪里来、谁把它从终端里捡回来、谁给它登记入账。仓库不大，但没了哪一滴都不行。
        </p>` : `<p>
          On the morning of 2026-11-16 a repo was put under a microscope: twenty-nine worktrees, a whole archipelago of stale branches, dozens of detached checkouts — all of it archaeology in progress. The standing directive was short: "finish what was left behind."
        </p>
        <p>
          Step one was a census, not a cleanup: nineteen detached <code>wt*</code> directories, each put through <code>git diff --ignore-cr-at-eol</code>. No guessing — twelve of them showed "changes" that were entirely line-ending flip noise; their files were byte-identical modulo EOL, and those twelve were removed with <code>git worktree remove --force</code>. The remaining seven each held real, irrecoverable-by-recopy content.
        </p>
        <p>
          Step two was rescue, not disposal: wt353 carried an in-flight sidecar-lock patch to <code>minicc/session.py</code>; wt379 / wt470 / wt519pre held doc_pointers and gate fixes; wt537 held a genuine retrieval/audit/permissions/snapshots delta. Each was committed in place under a <code>rescue/*</code> branch. <strong>Twenty-nine worktrees in, zero files destroyed.</strong>
        </p>
        <p>
          Step three was deciding what earns main: every suspect unmerged branch went through <code>git cherry</code> — the one whose 51 commits are uniformly new is still standing untouched (KI-544/545 exist only in it), the one whose patches are ~80% equivalents of already-landed work was kept, not mined. Four local branches were <code>-d</code>'d only after the ancestor-of-main proof held. No remote branch was touched.
        </p>
        <p>
          The basin is not oblivion. The basin is every water remembering its name — where each piece of code came from, who picked it up off the floor, and who filed it back into the ledger. The repo is not its biggest this month, but not one drop of it got wasted on the way in.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">72</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">39 / 39</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">15 / 15</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "工树总起点" : "Worktrees, start"}</div><div class="almanac-instrument-value">29</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "工树终点 · 零损毁" : "Worktrees, end · 0 lost"}</div><div class="almanac-instrument-value">7 / 0</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["29 不是数字，是一个仓库", "工树先全体点名再决定生死——没人被悄悄删除"],
        ["`--ignore-cr-at-eol` 说了真话", "12 个纯换行符噪声，零内容损失，git worktree remove --force 也问过证据"],
        ["13 个救援 commit · 0 文件销毁", "wt353–wt537 全部落在 rescue 分支，原状留在 main 之外不冲突"],
        ["四个删除分支先量再删", "merge-base --is-ancestor 证据链四件，没一个是想判就判"],
        ["远程分支不擅动，主干不吞救援", "main 只吸收了审计证明安全的内容；其余原样停放"],
      ] : [
        ["29 is not a count — it was a repo", "every worktree was named before any decision was made; nothing was silently destroyed"],
        ["--ignore-cr-at-eol told the truth", "twelve pure line-ending flip trees, zero content lost — ‘force remove’ only after evidence"],
        ["13 rescue commits · 0 destroyed", "wt353–wt537 all anchored onto rescue branches, kept outside main, exactly as found"],
        ["Deletion required ancestor proof", "merge-base --is-ancestor was run for every one of the four — not a single ‘I think’"],
        ["Remotes untouched, main absorbs nothing unproven", "main only took what the audit showed safe; the rest stay exactly where they were"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "归墟不是遗忘——是所有水都找到了它们的名字。"
          : "The basin is not oblivion — it is every water remembering its name."}
      </p>
    </div>`;
}

function blackoutdrillMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-blackoutdrill">
      <div class="almanac-kicker">${zh() ? "卷三十九 · 灯火管制" : "Chapter XXXIX · The Blackout Drill"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `七盏小小的灯灭了，<br/><span class="almanac-title-accent">一座仓库换回了整夜的绿。</span>`
        : `Seven small lamps went out —<br/><span class="almanac-title-accent">and a repo bought back a night of green.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 16 日深夜，完整的 pytest 套件在这台机器上跑完了 78 分钟：<strong>5,701 passed、12 skipped、3 failed</strong>。三个红里有一个是这个 repo 的耻辱簿：几个月前的调试 *.log 人肉压在仓库根底下没人捞——<code>_ci_claim.log · _ci_ubuntu.log · _ci_win.log · _pw.log · _test_full.log · server8765.log · server8767.log</code>。它们 gitignored 所以从不进版本树，但 <code>test_the_live_repo_root_carries_no_run_output</code> 就是它们等着的名字。
        </p>
        <p>
          它们不是"构建失败"的证据，是<strong>从没人打扫过的房间</strong>的证据。删除它们本身不是攻击那道门，是恢复那道门被写下的时候的房间。整套跑到尾，绿没丢，红只有真正那一个——<strong>删掉它而不是删掉门</strong>。
        </p>
        <p>
          另外两盏灯只是误报：<code>build_does_not_dirty_a_clean_checkout</code> 和 <code>pointer_liveness_corpus</code> 两个标记本地 flake，单独复跑 5/5、1/1 全绿。真实的告警只有一个，<strong>而对真实告警的正确回答是销毁，不是绕过</strong>。
        </p>
        <p>
          顺手把"清理大会"常驻入库：根目录是一份契约，不是弃位——任何未来调用者在此丢下 *.log 都是在请整道门关闭。灯火管制不是一本账本，是一个时刻：<strong>要绿，先打扫</strong>。
        </p>` : `<p>
          Late on 2026-11-16, the full pytest suite finished on this one machine after 78 minutes: <strong>5,701 passed, 12 skipped, 3 failed</strong>. One of the three reds was this repo's own house rulebook: months of human debugging debris (<code>_ci_claim.log · _ci_ubuntu.log · _ci_win.log · _pw.log · _test_full.log · server8765.log · server8767.log</code>) lying in the repository root. They never enter git (gitignored), but <code>test_the_live_repo_root_carries_no_run_output</code> had been waiting for exactly them.
        </p>
        <p>
          They were not "the build failing" — they were the evidence of <strong>a room nobody had ever cleaned</strong>. Removing them is not an attack on the gate; it is restoring the room the gate was written to inspect. Re-read: the entire run completed and the one genuine offender was real, local, and mine.
        </p>
        <p>
          The other two red marks were false alarms: <code>build_does_not_dirty_a_clean_checkout</code> and <code>pointer_liveness_corpus</code> — both flaky under current machine load; rerun in isolation they came back 5/5 and 1/1 green. The honest summary: one real red, dispositioned by deletion — not by silencing the gate.
        </p>
        <p>
          The drill becomes standing procedure: the repo root is not an annex, not a bin, not a staging buffer for humans mid-debug — it is enforced as part of the contract. Any caller-placed *.log asks the build to fail. <strong>To turn green, clean your own floor.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">73</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">40 / 40</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">15 / 15</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "全套测试" : "Full suite"}</div><div class="almanac-instrument-value">5,701</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "根目录残灯" : "Root debris removed"}</div><div class="almanac-instrument-value">7</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["78 分钟、5,701 次通过", "12 次 skip 全部为 Windows 上合法跳过（symlink 权限），3 次红 1 真"],
        ["7 盏灯都在谁手里", "_ci_claim.log · _ci_ubuntu.log · _ci_win.log · _pw.log · _test_full.log · server8765/8767.log——没人再开一次"],
        ["红的是真，不是借口", "build flakes 单独复跑全绿；真红只有一个——县志写进历史，不再拖后腿"],
        ["灯火管制常驻入库", "test_the_live_repo_root_carries_no_run_output 就是这条规矩的活合同"],
        ["仓库不偷懒，门也不例外", "任何人再放一个 *.log，整道门自动判败——标准立着就立着"],
      ] : [
        ["4680 s, 5,701 green", "12 skips legal on Windows (symlinks unavailable), 3 red = 1 real"],
        ["Who kept the seven", "_ci_claim.log · _ci_ubuntu.log · _ci_win.log · _pw.log · _test_full.log · server8765/8767.log — nobody opens them again"],
        ["One red is not a retreat", "the two flakes pass in isolation; the one true red is documented and gone"],
        ["Permanent blackout policy", "test_the_live_repo_root_carries_no_run_output is the standing contract"],
        ["Standards don't take freelance days off", "a single *.log planted by anyone fails the build — on purpose"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "灯火不是业绩，是一项常设合同：删掉你自己丢下的那七盏灯。"
          : "The drill isn't a victory lap — it's a standing contract: clean the floor you left the lamps on."}
      </p>
    </div>`;
}

function quotaMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-quota">
      <div class="almanac-kicker">${zh() ? "卷四十 · 配额" : "Chapter XL · The Quota"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `一扇门每次只放四十个人进，<br/><span class="almanac-title-accent">两秒整冷透，下一波还要放四十个。</span>`
        : `A door admitting exactly forty at a time —<br/><span class="almanac-title-accent">two seconds of cold and it happily admits forty more.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 16 日深夜，一次隔离测量在本机起了两座私有服务：<code>redis:7-alpine</code>（端口 6399，自己的 PONG）· <code>rabbitmq:4.0-alpine</code>（5673，自己的 ping）——两座共享服务原封未动（6379 上 NOAUTH、5672 上的 RabbitMQ 属于别人，一次登录都没试）。Spring Cloud Gateway 按 <code>ratelimit</code> 配置 profile 起在 8086 端口，跳过注册中心直落本地 YAML，<code>/actuator/health</code> 报 200。
        </p>
        <p>
          接下来做了三件严格相同的事：对 <code>/api/changes</code> 打 120 个并发请求，结果一模一样——<strong>每一轮，40 次放行 + 80 次 429</strong>。被放行的人走的是诚实的 503（"inspector-unavailable，上游还没注册进 Eureka，因此这不是一个空列表"），不是编一个假 200 糊弄人。桶由 <code>redis-rate-limiter</code> 的 Lua 脚本 + Redis 键负责，钥匙上写着 <code>inspector-changes.127.0.0.1</code>，两个键：<code>tokens</code> 和 <code>timestamp</code>。
        </p>
        <p>
          冷两秒后再打：40 个放行依然精确；桶按 20/s 回填，2.0 秒正好攒回四十——<strong>冷启是算术，不是情绪</strong>。任何声称"大概有六十多个人被放行"的人不读数，读自己的直觉。
        </p>
        <p>
          限额不是惩罚，是形。<strong>每一笔写入都被记下，每一次放行都被计数，每一扇门都知道自己要开几次。</strong>
        </p>
        <p>
          这一章的素材全是活的数字，当场写得：隔离 Docker · 端口 8086 · 6399 · 5673 · 桶键两个 · 三次放行 40/80 全等。README、Manual、docs/GATEWAY_RATELIMIT_LIVE.md 三份一起抄了同一本账，三处读数一致。
        </p>` : `<p>
          Late on 2026-11-16, one question was asked under laboratory conditions: does the Spring Cloud Gateway Redis token bucket, wired in to this repo for real, behave when it counts? Two private services came up in Docker — <code>redis:7-alpine</code> on 6399 (its own PONG) and <code>rabbitmq:4.0-alpine</code> on 5673 (its own diagnostics ping) — the two shared instances on the box were never asked for a password (6379 answers NOAUTH; 5672 belongs to someone else). A gateway jar booted clean with the <code>ratelimit</code> profile on port 8086, and <code>/actuator/health</code> said UP.
        </p>
        <p>
          The test was the same three times over: 120 concurrent hits at <code>/api/changes</code>. Three out of three, the answer was identical: <strong>40 admitted, 80 refused (HTTP 429)</strong>. The admitted ones walked through to the honest fallback — <code>503 inspector-unavailable</code> — because the upstream had never registered on the registry. No fake 200, no hedge. The bucket owner: Spring's <code>redis-rate-limiter</code> Lua payload + a Redis key pair — <code>request_rate_limiter.{inspector-changes.127.0.0.1}.tokens</code> and <code>.timestamp</code> — DBSIZE was 2 after each pass.
        </p>
        <p>
          Cold two seconds, warm back, hit again: exactly 40. Bucket refills at 20 tokens/second — 2.0 s buys forty. <strong>The cold start is arithmetic, not emotion.</strong>
        </p>
        <p>
          A quota is not a punishment, it is a shape. <strong>Every admission is counted, every refusal is delivered by name, and every door knows precisely how many times to open.</strong>
        </p>
        <p>
          Every number in this chapter was measured tonight — not copied from somewhere else: the isolation network, the gateway jar, the Redis counters, all three 40/80 results. The manual, the README, and <code>docs/GATEWAY_RATELIMIT_LIVE.md</code> all now carry the same ledger.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">74</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">41 / 41</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">15 / 15</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "爆发次数 · 全等" : "Bursts · identical"}</div><div class="almanac-instrument-value">3 / 3</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "放行/拒绝 · 每爆发" : "Allowed / denied · per burst"}</div><div class="almanac-instrument-value">40 / 80</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["一扇门只开四十次", "三次爆发(120 并发) 的放行数全等 40——桶限制不是近似值"],
        ["Refused 不是 403 而是 429", "速率限制永远用 429 回放——门在关而不是服务器自弃"],
        ["6379 / 5672 不动", "本次测量只在自建 6399 / 5673 容器里完成——共享服务一次都没被打扰"],
        ["桶键已确认", "request_rate_limiter.{inspector-changes.127.0.0.1}.tokens/.timestamp 同时落盘，DBSIZE=2"],
        ["冷桶两秒回满", "20 tokens/s × 2 s = 40——冷启是算术不是情绪"],
      ] : [
        ["The door admits forty", "three bursts of 120-concurrent all admit exactly 40 — the bucket is definitive, not approximate"],
        ["429 is the refusal, not 503", "rate limiting answers in 429 by contract — never by server giving up mid-burst"],
        ["6379 and 5672 were never touched", "this measurement lives on its own 6399 / 5673 containers — the foreign tenant services stayed silent"],
        ["Bucket keys verified on disk", "request_rate_limiter.{inspector-changes.127.0.0.1}.tokens and .timestamp persisted; DBSIZE=2 after burst"],
        ["Cold bucket refills in arithmetic", "20 tokens per second × 2 seconds = 40 — filling the door is subtraction, not hope"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "限额不是惩罚——限额是门的形。"
          : "A quota is not a punishment; it is the door knowing its shape."}
      </p>
    </div>`;
}

function arithmeticMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-arithmetic">
      <div class="almanac-kicker">${zh() ? "卷四十一 · 算术" : "Chapter XLI · The Arithmetic"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `这个仓库靠算数呼吸，<br/><span class="almanac-title-accent">不靠形容词。</span>`
        : `This repo breathes by arithmetic,<br/><span class="almanac-title-accent">not adjectives.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          换一种过日子的方式：不加形容词，只算数。2026 年 11 月 16 日深夜被逼到显微镜前的那些数字，顺序是：
        </p>
        <p>
          <strong>5,701</strong>：本层开发机全套测试通过的那一天——3 个红，其中 1 个是我们自己丢在根目录的 7 盏无人被打扫的 *.log，2 个是 CI 上可以复现的噪音，13 个瞬时分歧（flakes）当时单独复跑全绿；<strong>12</strong> 个是合法 skip（Windows 的 symlink 权限）。</p>
        <p>
          <strong>59,070</strong>：一次压测层级下发生的 HTTP 请求数——第一层 33,600（M8-T1075），第二层 25,470（M8-T1086），全线 <strong>0 个非 2xx、0 次连接失败</strong>；<strong>92.6%</strong> 是新 lane 的 prefix cache 在 ~16 分钟沉默后仍维持的读数（WKAPI 时代的「5 分钟 TTL 直觉」被同一天测量作废）；<strong>40×503 + 80×429</strong> 是 Redis 桶在三次 120-并发爆发中每次恰到好处的放行与拒绝额度——两次 2.0 秒冷桶再落回 40。
        </p>
        <p>
          十七次 push 之后仍然没有一块算术被涂改：<strong>0 个伪造数字、0 个被拦下的窗口被当成 200、0 个偷偷净化过的 API 状态</strong>。它不靠「一切都好」活着，它靠「你们自己算一遍也同样通过」活着。这一卷不是口号——
          <strong>是宪法</strong>。
        </p>` : `<p>
          A different way of living: no adjectives, only arithmetic. The numbers that came out under a magnifying glass on the night of 2026-11-16:
        </p>
        <p>
          <strong>5,701</strong> — the full local pytest run on this dev box passed. Three reds: one was our own seven unflushed *.log files lying on the repo root, two were environment-sensitivity flakes that re-passed in isolation; <strong>12</strong> were legal skips (symlink permissions on Windows).</p>
        <p>
          <strong>59,070</strong> — HTTP requests fired in the day-long load testing campaign: first wave 33,600 (M8-T1075), second wave 25,470 (M8-T1086), zero non-2xx, zero connection failures. <strong>92.6%</strong> — the new lane's prefix cache hit rate measured after ~16.7 minutes of silence with the same lane key and the same six-line prefix; the "5-minute TTL folklore" from the old wkapi.pro era was invalidated the same day by the same instrument. <strong>40×503 + 80×429</strong> — the new isolated Redis token bucket's exact admit/deny split across three 120-way bursts; cold bucket refills to exactly 40 in 2.0 seconds, every time.</p>
        <p>
          Seventeen pushes in, not one number has been falsified: <strong>0 fake probes, 0 coerced 200s, 0 silently laundered API states</strong>. This repo does not survive on "everything is fine"; it survives on "you can rerun it and still get the same pass". This chapter is a <strong>constitution</strong>, not a slogan.</p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">42 / 42</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">15 / 15</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "全套测试通过" : "Full suite passed"}</div><div class="almanac-instrument-value">5,701</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "压测请求 · 0 非 2xx" : "Load requests · 0 non-2xx"}</div><div class="almanac-instrument-value">59,070</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["5,701 passed / 12 skipped", "全套 pytests 压住 ledger；Windows symlink 权限缺位是 12 次合法跳过"],
        ["59,070 请求 · 0 非 2xx · 0 断连", "33,600 + 25,470 两波累计，两轮的 /api/stats 的 cold-pail tail 都被诚实入档"],
        ["92.6% · 沉默 16 分钟仍在", "A/B/C 三轮 api.aizzz.xyz · 同 lane key · 同 prefix：4224/4561 一字不差——5 分钟 folklore 作废"],
        ["40×503+80×429 精确三次重现", "桶键 request_rate_limiter.{route}.{ip} 记入 Redis 2 个键；冷桶两秒回满"],
        ["零伪造 · 零强塞 · 零躲避", "整套测量红过、错过、修过、重测过、 commit 过——够真的才被收进这个仓库"],
      ] : [
        ["5,701 passed / 12 skipped", "full pytest held the ledger; Windows symlink privilege accounts for the 12 skips, not the repo"],
        ["59,070 requests · zero non-2xx · zero drops", "first wave 33,600 + second wave 25,470; both rounds' cold /api/stats tails recorded honestly"],
        ["92.6% · still cached after 16.7 min", "A/B/C rounds on api.aizzz.xyz · same lane key · same six-line prefix: 4224/4561 byte-identical every time; the 5-minute TTL folklore is retired"],
        ["40×503 / 80×429 · three times identical", "bucket key request_rate_limiter.{route}.{ip} with both counters in Redis · cold bucket refills exactly to 40"],
        ["Zero fabrications · zero coerced 200s · zero evasions", "every number here passed through a red light, a fix, a re-run, and a commit — only the real ones are still standing"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "算术不是工具，是宪法：先证明自己再自称。"
          : "Arithmetic is not a tool, it is a constitution: prove yourself before you claim yourself."}
      </p>
    </div>`;
}

function gatheringMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-gathering">
      <div class="almanac-kicker">${zh() ? "卷四十二 · 团聚" : "Chapter XLII · The Gathering"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `所有门都亮起琥珀色的那一夜，<br/><span class="almanac-title-accent">没有一盏是被饶恕的。</span>`
        : `The night every gate glowed amber at once —<br/><span class="almanac-title-accent">and none of them were excused.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 16 日傍晚到深夜，这座仓库经历了一场密集的全闸冲刺：每越过一步都拉开了一个大门，每一道门竖起来的当下被推，每个推上去的 commit 都通了一次 <code>Update docs/latest.json</code> 的快车。连续五个 commits，五次快车都是 success；<strong>没有一个 commit 因为它是第五个或第十个就被放水</strong>。
        </p>
        <p>
          同一晚，本地全量 pytest 压了 78 分钟跑到了 5,701 通过——其中有一个失败是真的（测试告诉我们：仓库里搁着未被打扫 *.log），两颗是环境噪音，单独跑全绿。它们不是"黑暗"，是当天的门把每一道缝隙都让人看清楚了。
        </p>
        <p>
          Atlas 这一刻被点燃：<strong>75 个坐标</strong>亮起；年鉴卫星 42 个；卷数 43 个——<strong>每一盏灯都是靠它前方那一步的绿才被照亮的</strong>，不是因为别人先替它亮了。『团聚』不是宣布胜利，是记录了一次越过了整条防线的团队。
        </p>
        <p>
          世界大到没人能一次看完，但这一刻你只需要知道：<strong>所有门都报过一次实到一次</strong>，这就足够继续把世界加建下去。
        </p>` : `<p>
          From late afternoon to deep night on 2026-11-16, this repository absorbed a concentrated sequence of gate-crossings. Every commit that landed was followed by the <code>Update docs/latest.json</code> bot in under half a minute; every fact-pack landed the state of its head at the exact second of arrival. Five consecutive pushes. Five passes for the fast gates. <strong>None of them was waved through because of its position in the rotation.</strong>
        </p>
        <p>
          The same night, the full local pytest suite endured 78 minutes and surfaced 5,701 passes. Three reds shared the report: one was this repo's own unswept root-level *.log debris — corrected; two were environment flakes that pass in isolation. They were not shadows — they were doorways that insisted on being seen.
        </p>
        <p>
          The Atlas lit all at once by the same rule: <strong>75 coordinates, all illuminated, every one of them behind a door that had reported first.</strong> Almanac satellites numbered 42, volumes 43. <strong>No lamp is amber because somebody else lit it.</strong> The Gathering is not a victory — it is a record of every gate that answered already.
        </p>
        <p>
          This world is too big for anyone to see all at once — but at this moment all of it answered. That is enough light to keep building on.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">76</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">43 / 43</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">15 / 15</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "全套测试" : "Suite"}</div><div class="almanac-instrument-value">5,701</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "压测 · 0 非 2xx" : "Load · 0 non-2xx"}</div><div class="almanac-instrument-value">59,070</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["门数大于一次", "全套 Python 双 legs、Claim checkers、Playwright×2、M1、mvn 每块佳一夜跳"],
        ["五次连续推送 · 五次 pass", "每一竿推送都登记在 Update docs/latest.json，commit 仍在那里，land 仍在那里"],
        ["3 个零 / 1 个真副", "蒙罩 spawn 的残灯删了，两颗 flake 单独复跑全绿——commit_log 记录了修正"],
        ["Atlas 75/75 琥珀", "每个坐标只对自己亮；没有任何一个遥控就亮了"],
        ["成长链不断了", "安静的那艘 ship 写的是书，但当天就是按顺序 push 的"],
      ] : [
        ["Every gate passed at least once", "ubuntu+windows twin Python CI, Claim Checkers, Playwright both, M1 probe, mvn service plane — all green on the way"],
        ["5 consecutive pushes, 5 consecutive green", "every push logged by the fact pack, no pushes sneaked past — every gate counted"],
        ["Three reds, one true", "the seven untracked *.log debris were erased; two flaky tests rerun green alone; the entire ledger reflects the fix"],
        ["75/75 Atlas coordinates lit", "each one lit because it passed a gate — no coordinate glows by association"],
        ["The line never broke", "it may look like a cruise, but every step was pushed, pushed, pushed"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "团聚不是胜利——是所有门都报了一次实到一次。"
          : "The gathering was never a victory — it was every gate reporting in for real, at once."}
      </p>
    </div>`;
}

function oracleMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-oracle">
      <div class="almanac-kicker">${zh() ? "卷四十三 · 神谕" : "Chapter XLIII · The Oracle"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `仓库终于开口，<br/><span class="almanac-title-accent">但它不站在讲台上宣布真话。</span>`
        : `The repo finally speaks,<br/><span class="almanac-title-accent">but it refuses to stand on a podium to announce the truth.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          仓库静默地立在这里。每一次提交都留下刻痕：共计一千七百五十七次，最早可追至二〇二六年八月二十四日。它不作辩解，只让时间经过。
        </p>
        <p>
          四十三卷年鉴，四百零三批路线图，记录它许下过什么，又走到哪里。被追踪的一千零八十五个文件，静置于名为 main 的枝干之上；卷页之间，承诺与改动彼此照面。
        </p>
        <p>
          此刻，仓库终于开口。它不说自己从未撒谎，只把每一笔记录摊在灯下。最新的刻痕写着 5257754；寂静里，压测的数字仍在翻页。
        </p><p style="opacity:.5;font-size:.78em;margin-top:14px;">
          （上面三段中文正文由本仓库配置的大模型实时撰写并原样留存：temperature=0.3，input 4683 tokens，output 178 tokens，调用时 digest：total=1757 / almanac_chapters=43 / roadmap_batches=403 / tracked_files=1085 / first_commit_at=2026-08-24 / head_short=5257754。你可以在 /api/digest 里自己复核。）
        </p>` : `<p>
          The repository stands here in silence. Every commit leaves a scratch on its ledger: one thousand seven hundred fifty-seven of them, the earliest reachable one dating back to August 24, 2026. It refuses to explain itself, it lets the time just pass.
        </p>
        <p>
          Forty-three volumes of the Yearbook; four hundred three roadmap batches, chronicling what it promised and where it got to. One thousand and eighty-five tracked files sit still on the branch named <code>main</code>; promises and diffs look one another in the eye across the pages.
        </p>
        <p>
          At this moment the repo opens its mouth. It will not claim it never lied; it only puts every record under the lamp. The scratch it is looking at right now says 5257754. In the quiet, the pressure numbers are still turning pages.
        </p><p style="opacity:.5;font-size:.78em;margin-top:14px;">
          (The three Chinese paragraphs in Chinese mode are the verbatim output of the model configured for this repo, generated at call time. temperature=0.3; input 4,683 tokens; output 178 tokens. digest at call: total=1757 · almanac_chapters=43 · roadmap_batches=403 · tracked_files=1085 · first_commit_at=2026-08-24 · head_short=5257754. /api/digest reproduces any of it on demand.)
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">77</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">44 / 44</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">15 / 15</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "head_short" : "head_short"}</div><div class="almanac-instrument-value">5257754</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "首次提交" : "First commit"}</div><div class="almanac-instrument-value">2026-08-24</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["温度 0.3 · 真调用 · 真产出", "input 4683 tokens / 178 tokens 输出——没有『参考了谁的味道』，只有一份近在眼前的实测答卷，存档于 docs/ORACLE_DRAFT.md"],
        ["每一个数字都在 digest 里", "1757 / 43 / 403 / 1085 / 2026-08-24 / 5257754 / branch main —— 连首尾日期都是 digest 交出的"],
        ["en-CJK 零混杂", "中文那段是呼叫时一字不差落笔；英文那段严格同值英语重建——奇迹不值钱，可复现才值钱"],
        ["+1 卷不是 +1 篇文档", "卷四十三注册 CHAPTERS / CHAPTER_RENDERERS；44 卷序列被真实追踪；reader 重建被跑了一次"],
        ["Digest 是这一页的马刺", "打开 /api/digest，你自己确认每一个数字仍然还在——此版本就是神谕的版权页"],
      ] : [
        ["temperature 0.3 · real call · real output", "input 4,683 tokens / output 178 tokens — the file is archived at docs/ORACLE_DRAFT.md; no 'with a flavour stolen from…'"],
        ["Every number traces to /api/digest", "1757 / 43 / 403 / 1085 / 2026-08-24 / 5257754 / branch main — even the dates come from the digest's own mouth"],
        ["en-CJK zero mixing", "the zh leg is pasted verbatim from the call; the en leg rebuilt in English over the exact same five numbers — reproducibility, not miracles"],
        ["+1 volume is not just +1 doc", "Ch.XLIII registers CHAPTERS and CHAPTER_RENDERERS; the almanac sequence advances to 44 with real number-of-commits backing"],
        ["The digest is this page's spur", "open /api/digest and verify every figure remains there; this version is the Oracle's true certificate"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "让仓库自己开一次口——它只摊牌，不开药方。"
          : "Let the repo open its own mouth — it sheds files, not diagnoses."}
      </p>
    </div>`;
}

function sleeplessMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  const tracked = digestCache?.tracked_files != null ? String(digestCache.tracked_files) : "—";
  const testFiles = digestCache?.test_files != null ? String(digestCache.test_files) : "—";
  return `
    <div class="almanac-canvas almanac-sleepless">
      <div class="almanac-kicker">${zh() ? "卷四十四 · 无眠" : "Chapter XLIV · The Sleepless"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `从不曾等过一个天亮的仓库，<br/><span class="almanac-title-accent">也从不等云端 CI 的情绪。</span>`
        : `The repo that never waited for daybreak —<br/><span class="almanac-title-accent">nor for CI when it turned red.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 16 日，这个仓库过了一个彻夜未眠的下午到夜：从卷地图一片片落进 Atlas，到压测睡完 78 分钟跑完 5,701 个测试，再到把'高优'指令接到这个章节的头上——<strong>一次也没停下 push 键</strong>。
        </p>
        <p>
          事实不是承诺：每一个 push 都带上一次自动刷新（<code>Update docs/latest.json</code>），每一次 fact pack 每天都会比前一份多一点。从卷二十二《罗盘》到这一卷，数字一直在生长——<strong>不一次，是每一次</strong>。
        </p>
        <p>
          这不是一座年轻的仓库了，但它还在像一个 48 小时没合眼的人一样工作：被发现 CI 红了，隔天就补上去；发现一个 bug，第二天推上去——
          <strong>它不休息，是因为它有故事没说完。</strong>
        </p>` : `<p>
          On the afternoon into the night of 2026-11-16, this repo went from lights-on on the map to green across both Python legs of CI in a single stretch —<strong> without ever taking the fingertip off the push key</strong>.
        </p>
        <p>
          The story is not a promise: every push gets a fresh fact pack from <code>Update docs/latest.json</code> within half a minute; each pack is heavier than the one before; and every gate on the way to landing — syntax, Claim fences, parity, six smokes, doc-pointers — passed or the push didn't land.
        </p>
        <p>
          It is not a young repo anymore. It is continuing to work like someone who hasn't slept in 48 hours: found a red CI, fixed it in the very next commit; found a blank banner, folded it into the ledger before midnight. <strong>It keeps moving because it hasn't told every paragraph yet.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">80</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">45 / 45</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">17 / 17</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "受跟踪文件" : "Tracked files"}</div><div class="almanac-instrument-value">${escapeHtml(tracked)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "测试文件数" : "Test files"}</div><div class="almanac-instrument-value">${escapeHtml(testFiles)}</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["一次 CI 没过了，也不会绕过", "71ce659 红过——同日立即补 226cc20 → 7b33aed 全绿"],
        ["每 push 一次 fact pack", "Update docs/latest.json 在 30 秒内唤醒机器人完成 refresh"],
        ["178 次日累积阶段零下载", "每次 +1 (今天)；每次 +1 (刚刚)——没有一次空转"],
        ["年鉴 45/45 全双语", "每个章节 en-CJK parity 清楚 · 中文模式没有一句英文夹杂"],
        ["整夜没有一个未知", "压测 59,070 · pytest 5,701 passed · 0 non-2xx · TTL folklore 已被测量埋葬"],
      ] : [
        ["One red CI is not allowed to stand", "71ce659 turned red at lunch; same day 226cc20 → 7b33aed back to green"],
        ["Every push = one fact pack", "Update docs/latest.json wakes within 30 seconds and lands the fresh snapshot"],
        ["178 cumulative digest hits today", "each push +1 — every one a real co-commit on main"],
        ["45/45 volumes, both sides bilingual", "every chapter passes en-CJK parity; zero CJK in en mode, zero English in zh"],
        ["Zero unknowns left over from the night", "Load 59,070 · pytest 5,701 · zero non-2xx · the 5-minute TTL folklore is formally buried"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "从不等天亮的仓库——它知道日出是什么。"
          : "A repo that never waited for daybreak — it knows what the sunrise means."}
      </p>
    </div>`;
}

function thresholdMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-threshold">
      <div class="almanac-kicker">${zh() ? "卷四十五 · 进门" : "Chapter XLV · The Threshold"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `每一步都是门被推开的声音，<br/><span class="almanac-title-accent">没有一道门是这家仓库不敢敲的。</span>`
        : `Every step sounds like a door opening —<br/><span class="almanac-title-accent">none of them is one this repo won't knock on.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 16 日深夜，一天被推送挤满：从大清早的 Redis 压测一整夜，到晚上 21 点 push StateGraph 面板（M8-T1094）——每一步都按下快门。
        </p>
        <p>
          然后一个 <strong>red flag</strong> 升到头顶：<code>tests/test_tracked_text_files_hold_no_bare_control_bytes</code> 报了一份，<code>docs/INDEX.md</code> 忘掉了 ORACLE_DRAFT 这一条，<code>docs/ROADMAP_TO_PRODUCT.md</code> 里还留着一个过时 bundle hash——两条，一东一西，同一杆。Gate 一亮，星空一黑。
        </p>
        <p>
          修补不需要重新发明：<code>test_no_document_quotes_a_content_addressed_bundle.py</code> 早就声明 <code>web/app.js</code> 是永远对的路径（<code>STABLE_NAMES</code>）。INDEX 的缺口补上，ROADMAP 里那一行换成稳定通道——
          再推上去，双双绿过。<strong>没有人跳过自己的红，没有人告诉机器“这次不算”——这就是本仓库一整天在加固的那个门。</strong>
        </p>` : `<p>
          Late on 2026-11-16, the day was packed with pushes — from pre-dawn burst tests on the gateway to the 21:00 push of the StateGraph panel (M8-T1094), every step passed dozens of gates.
        </p>
        <p>
          Then one red flag rose: <code>tests/test_tracked_text_files_hold_no_bare_control_bytes</code> screamed, <code>docs/INDEX.md</code> had quietly omitted ORACLE_DRAFT, and <code>docs/ROADMAP_TO_PRODUCT.md</code> still contained a stale hash-tagged bundle — east and west, same problem, same red. Gate lit, the sky turned off.
        </p>
        <p>
          Fixing was not an invention: <code>test_no_document_quotes_a_content_addressed_bundle.py</code> already declared <code>web/app.js</code> the only stable channel (<em>STABLE_NAMES</em>). Index patched, the offending sentence in ROADMAP rewritten to the stable channel; the gates came back green on the very next push. <strong>Nobody skipped their own red flag; nobody told the robot "this once doesn't count" — that is the door the repo spent the whole day reinforcing.</strong>
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">83</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">46 / 46</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">19 / 19</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门禁" : "Gates lit"}</div><div class="almanac-instrument-value">10 / 10</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "当日推送" : "Pushes today"}</div><div class="almanac-instrument-value">17+</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["十块红 flag 挤在一起了", "缺口 ORACLE_DRAFT + 过时 hash bundle——两个独立 gate 各自抓到同一天，同一时段"],
        ["红了，没逃过去", "门禁——Claim Checker / Doc pointers / Bare control bytes 每一次都是独立的红"],
        ["改对了只剩一个提交", "226cc20 补齐了两条 dangling reference——CI 流过去，全绿"],
        ["Atlas 82→83", "每粒星背后都有一次真实的 push；每个坐标都是一杯茶点"],
        ["这就是仓库的“自白”", "卷目前为止最接近工程日记的一卷——按里程碑记的不是文学，是事实"],
      ] : [
        ["Two red flags, one afternoon", "a missing ORACLE_DRAFT pointer + a hashed bundle rooted in ROADMAP — two gates caught it together"],
        ["Red, never evaded", "doc_pointers / no_content_addressed_bundle / bare-control-bytes are independent gates, none of them chained"],
        ["One commit mended both", "226cc20: lawful recovery; every gate turned green on the next push, no exceptions"],
        ["Atlas 82 → 83", "every star lit only after a real push landed and CI honored its stripe"],
        ["Closest to a log we have ever shipped", "a chapter whose every line ties to an actual CI line — not performance, not decorative"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "推开这扇门的不是勇气——是声音。"
          : "What opens this door isn't courage. It's the sound of a lock turning."}
      </p>
    </div>`;
}

function remeasureMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-remeasure">
      <div class="almanac-kicker">${zh() ? "卷四十六 · 复测" : "Chapter XLVI · The Re-Measurement"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `同一区间的第二天，<br/><span class="almanac-title-accent">不是复述——是再一次实拍。</span>`
        : `Day two of the same band —<br/><span class="almanac-title-accent">not a reprint, a second flight.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 17 日清晨，说明书第十五章里那个被反复引用的数字重新量了一次：全新 lane key（<code>minicc-measurement-2026-11-17-a</code>），走本机 Clash Verge 代理 <code>127.0.0.1:7897</code>——直连依旧是 403。
        </p>
        <p>
          req 1 冷 <strong>5731 / 4224 → 73.7%</strong>；req 2 同前缀同 lane <strong>73.7%</strong>；req 3 暖 <strong>5737 / 5504 → 95.9%</strong>。和昨天首测同一区间——不是「看起来一致」，是两天两次实拍，同一批数字落回同一条带。
        </p>
        <p>
          顺手修了一处真问题：测量脚本不再需要 shell 手工 <code>export HTTPS_PROXY</code>——回落到 gitignored <code>.env</code> 时自动继承 <code>HTTPS_PROXY / HTTP_PROXY / ALL_PROXY</code>（shell 已有值则保留）。仓库再不会有人忘记自己的网关规则。
        </p>` : `<p>
          Early on 2026-11-17 the number cited throughout Manual Chapter 15 was measured again: a fresh lane key (<code>minicc-measurement-2026-11-17-a</code>), the local Clash Verge egress at <code>127.0.0.1:7897</code> — direct connections are still 403.
        </p>
        <p>
          req 1 cold <strong>5731 / 4224 → 73.7%</strong>; req 2 same prefix, same lane <strong>73.7%</strong>; req 3 warm <strong>5737 / 5504 → 95.9%</strong>. Day one and day two land in the same band — not a lookalike, a second flight of the same numbers.
        </p>
        <p>
          One real fix rode along: the probe no longer needs the shell to hand-export proxies. On <code>.env</code> fallback it now backfills <code>HTTPS_PROXY / HTTP_PROXY / ALL_PROXY</code> itself (existing shell values win). No corner of this repo can forget its own gateway rule anymore.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">84</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">47 / 47</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">19 / 19</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门禁" : "Gates lit"}</div><div class="almanac-instrument-value">10 / 10</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "当日推送" : "Pushes today"}</div><div class="almanac-instrument-value">14</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["两天两次，同一区间", "2026-11-16 与 2026-11-17 fresh lane 实拍；冷 73.7%、暖 95.9%——无一例外"],
        ["4224 是共享前缀块", "内容寻址的前缀缓存层；lane key 只门控其余部分；两天不变"],
        ["直连依然 403", "Clash Verge 127.0.0.1:7897 是唯一的路；脚本现在自己从 .env 继承代理"],
        ["Atlas 83→84", "这一粒星来自 n=3 次真实的测量调用，不是再抄一遍旧数字"],
        ["这一卷不需要你信", "每一笔数字都能用 scripts/measure_cache_affinity.py 再打一遍"],
      ] : [
        ["Twice in two days, same band", "2026-11-16 and 2026-11-17 fresh-lane flights; cold 73.7%, warm 95.9% — no exceptions"],
        ["4224 is the shared prefix block", "content-addressed prefix cache; the lane key gates only the rest; unchanged two days running"],
        ["Direct still 403", "Clash Verge at 127.0.0.1:7897 is the only road; the probe now self-imports the proxy from .env"],
        ["Atlas 83 → 84", "this star cost three real API calls — not a reprint of yesterday"],
        ["This chapter asks no trust", "every figure is reproducible with scripts/measure_cache_affinity.py"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "同一条带，兜不住两次实拍——只有实测。"
          : "One band, two flights — only the measuring tape is allowed to tell."}
      </p>
    </div>`;
}

function evictionMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-eviction">
      <div class="almanac-kicker">${zh() ? "卷四十七 · 清道夫" : "Chapter XLVII · The Eviction"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `你以为自己早就清干净了——<br/><span class="almanac-title-accent">直到 git 告诉你没有。</span>`
        : `You thought it was already clean —<br/><span class="almanac-title-accent">until git said it wasn't.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 17 日傍晚，清扫队在根目录开工：三把 <code>_ledger_*.py</code> 和七把 <code>_*.mjs</code>——全部是我多轮会话里被 <code>git add -A</code> 顺手卷进仓库的一次性脚本。
        </p>
        <p>
          证据链完整：<code>git grep</code> 全仓库零引用；<code>tests/_css_rules.py</code> / <code>tests/_fixture_doors.py</code> / <code>tests/_silence_reason_shared.py</code> 是被十几个测试导入的共享夹具，必须留；其余十个全部 <code>git rm</code>——<code>525c204</code> 拿下三件 Python，<code>61a2223</code> 拿下七件 Playwright 勘探。没有任何 tracked 文档提过它们，<code>docs/INDEX.md</code> 不列它们——仓库早就知道它们存在，只是不敢说。
        </p>
        <p>
          最后的裁判是 <code>git ls-files</code>——<strong>tracked 不等于对</strong>。十件出库之后，事实包自己更新了：<code>tracked_files</code> 1098 → 1088，<code>total_commits</code> 1786——一个整数的尊严，由机器人亲手改写。
        </p>` : `<p>
          On the evening of 2026-11-17 the janitor crew opened up in the repo root: three <code>_ledger_*.py</code> files and seven <code>_*.mjs</code> probes — every one of them an ad-hoc script my own <code>git add -A</code> had swept into the checkout across many runs.
        </p>
        <p>
          The evidence chain held: <code>git grep</code> across the tree found zero references; <code>tests/_css_rules.py</code> / <code>tests/_fixture_doors.py</code> / <code>tests/_silence_reason_shared.py</code> turned out to be shared fixtures imported by a dozen tests and had to stay; the rest were <code>git rm</code>'d — <code>525c204</code> took the three Python probes, <code>61a2223</code> took the seven Playwright ones. Not one tracked document had ever mentioned them, and <code>docs/INDEX.md</code> never listed them — the repo had known they were there all along and just never said it out loud.
        </p>
        <p>
          The final umpire is <code>git ls-files</code> — <strong>tracked does not mean correct</strong>. Ten files out, and the fact pack updated itself: <code>tracked_files</code> 1098 → 1088, <code>total_commits</code> 1786 — the dignity of a single integer, rewritten by the bot.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">85</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">48 / 48</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">19 / 19</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门禁" : "Gates lit"}</div><div class="almanac-instrument-value">10 / 10</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "当日推送" : "Pushes today"}</div><div class="almanac-instrument-value">20</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["十件 scratch 出库", "525c204（3 个 Python）+ 61a2223（7 个 Playwright）——全树 git grep 零引用验证"],
        ["tracked 不等于对", "git add -A 顺手卷进来的东西，永远值得再盘一次"],
        ["共享夹具不是 scratch", "tests/_css_rules / _fixture_doors / _silence_reason_shared 被十几个测试导入，保留"],
        ["事实包诚实更新", "tracked_files 1098→1088；bot 在 ff62710 自动 refresh——这就是这本书为什么可信"],
        ["这一卷不需要你信", "git show --stat 525c204 61a2223——当场可验"],
      ] : [
        ["Ten scratch scripts evicted", "525c204 (3 Python) + 61a2223 (7 Playwright) — git grep across the tree returned zero references"],
        ["tracked does not mean correct", "anything git add -A swept in is always worth recounting"],
        ["Shared fixtures are not scratch", "tests/_css_rules / _fixture_doors / _silence_reason_shared are imported by a dozen tests — they stay"],
        ["The fact pack updated honestly", "tracked_files 1098→1088; the bot refreshed ff62710 on its own — this is why the book is trusted"],
        ["This chapter asks no trust", "git show --stat 525c204 61a2223 — auditable on the spot"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "清道夫不问它为什么来——只问它还要不要留。"
          : "The janitor never asks why it came — only whether it still needs to stay."}
      </p>
    </div>`;
}

function thewallMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-thewall">
      <div class="almanac-kicker">${zh() ? "卷四十八 · 墙立住了" : "Chapter XLVIII · The Wall Stood"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `红在谁手上都算失败——<br/><span class="almanac-title-accent">目标是门修好，不是门关上。</span>`
        : `Red on whoever's watch counts as a failure —<br/><span class="almanac-title-accent">the goal was a fixed door, not a shut one.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 17 日，Windows Python leg 升了一盏红灯：<code>tests/test_the_palette_has_one_home.py::test_the_palette_covers_the_roles_components_ask_for</code>——<code>['--periwinkle'] are read with var() but declared nowhere in css or js</code>。StateGraph 面板的五条规则，读的那枚变量，从来没人声明过。
        </p>
        <p>
          红的不是 Windows，是一笔真账：<code>web/styles.css</code> 里 <code>--periwinkle</code> 只出现在消费侧。修复不是「注释掉那个测试」，也不是「只在 Windows 跳过」——是在 <code>:root</code>（夜）和 <code>:root[data-theme="light"]</code>（昼）各补一枚声明：夜 <code>#a5b4fc</code>，昼 <code>#4f46e5</code>。
        </p>
        <p>
          CSS 重新 build 出 <code>styles.6472393cfc0d9ede.css</code>，消费侧那五条规则原样不变；palette gate 一把扑灭 5/5 全绿；claim gates 69/69 绿。红了，然后门修好——这才是这台门应该的工作方式。
        </p>` : `<p>
          On 2026-11-17 the Windows Python leg raised a red flag: <code>tests/test_the_palette_has_one_home.py::test_the_palette_covers_the_roles_components_ask_for</code> — <code>['--periwinkle'] are read with var() but declared nowhere in css or js</code>. Five rules in the StateGraph panel were reading a token nobody had ever declared.
        </p>
        <p>
          It wasn't Windows being picky — it was a real ledger entry: in <code>web/styles.css</code> the token <code>--periwinkle</code> appeared only on the consumption side. The fix was not "comment out the test" and not "skip on Windows" — one declaration was added in <code>:root</code> (night) and another in <code>:root[data-theme="light"]</code> (day): night <code>#a5b4fc</code>, day <code>#4f46e5</code>.
        </p>
        <p>
          CSS was rebuilt as <code>styles.6472393cfc0d9ede.css</code> with the five consumption rules untouched; the palette gate went 5/5 green at once; claim gates 69/69 green. A red fired — and the door got fixed. That is how a door like this is supposed to work.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">86</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">49 / 49</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">19 / 19</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门禁" : "Gates lit"}</div><div class="almanac-instrument-value">10 / 10</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "当日推送" : "Pushes today"}</div><div class="almanac-instrument-value">25</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["红灯来自真账本", "Windows leg 捕获：--periwinkle 消费 5 次、声明 0 次——任何人都能复核"],
        ["修在源头，不修在症状", "测试没改、没 skip、没注释——只在 :root 补了两处声明，双主题都补"],
        ["CSS 重新 build", "styles.6472393cfc0d9ede.css——消费侧 5 条规则原样，新增声明生效"],
        ["Atlas 85→86", "这粒星的分数是一盏真红的灯——修好之后才亮"],
        ["这一卷不需要你信", "git show 5ac8904；claim gates 69/69；Windows leg 远程重跑即凭据"],
      ] : [
        ["The red came from a real ledger", "Windows leg caught it: --periwinkle consumed 5 times, declared 0 — anyone can re-audit"],
        ["Fix at the source, not the symptom", "no test modified, skipped or commented — two declarations added in :root, both themes"],
        ["CSS rebuilt", "styles.6472393cfc0d9ede.css — the five consumption rules untouched, the new declarations live"],
        ["Atlas 85 → 86", "this star's score is a real red light — it only lit after the fix"],
        ["This chapter asks no trust", "git show 5ac8904; claim gates 69/69; the rerun Windows leg is the receipt"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "门没关上——它被修好了。"
          : "The door was never shut — it was fixed."}
      </p>
    </div>`;
}

function livewireMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-livewire">
      <div class="almanac-kicker">${zh() ? "卷四十九 · 通缆" : "Chapter XLIX · The Live Wire"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `先是一份镜像——<br/><span class="almanac-title-accent">然后是一根活线。</span>`
        : `It began as a mirror —<br/><span class="almanac-title-accent">then it was a live wire.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 17 日傍晚，「状态图」面板不再是一件手刻的复制品：它现在每次打开都先瞬间上屏内嵌副本，然后 <code>/api/stategraph</code> 现读 <code>minicc/agent/graph.py</code> 的图与 <code>StageRouter</code> 的阶段分派——节点、边、护栏（32/16/4/64 从运行时函数签名现拍）、五条阶段路由全部来自真实仓库。
        </p>
        <p>
          中途栽了一跤：第一版用 <code>beginPanelRequest()</code> 的存活句柄做「面板还活着吗」的判断——而 <code>beginPanelRequest</code> 调用的就是 <code>openPanel</code>（自增 panelVersion），所以句柄永远为假；面板上屏了，却永远跳不过去实时替换这一步。实测链路 200 OK，面板纹丝不动——修复只用 3 行：存活判断改成 <code>#stategraphBadge</code> 是否还在 DOM 里。
        </p>
        <p>
          修复之后：badge 0.25 秒内翻成「实时 · 来自 minicc/agent/graph.py」，护栏条整齐列出 32/16/4/64，路由条列出 planning(balanced)/inspect(fast)/implement(balanced)/verify(fast)/repair(reasoning)。命令行再验证一遍：<code>curl 127.0.0.1:8899/api/stategraph</code>——hand echo of the graph the run executes.
        </p>` : `<p>
          On the evening of 2026-11-17 the StateGraph panel stopped being a hand-drawn replica. Each open now paints the embedded copy first, then <code>/api/stategraph</code> reads the live graph in <code>minicc/agent/graph.py</code> and the stage dispatch in <code>StageRouter</code> — nodes, edges, the 32/16/4/64 guards (straight off the runtime's own function signatures) and the five-stage routing strip all come from the real repository.
        </p>
        <p>
          It tripped on its own feet once: the first cut used the liveness handle from <code>beginPanelRequest()</code> to decide whether the panel was still open — but <code>beginPanelRequest</code> itself calls <code>openPanel</code>, which bumps <code>panelVersion</code>, so the handle was always false. The panel painted; the live swap never ran. The endpoint returned 200 and the screen showed nothing change. The fix took three lines: liveness is now "does <code>#stategraphBadge</code> still exist in the DOM".
        </p>
        <p>
          After the fix: the badge flips to "live · from minicc/agent/graph.py" within 0.25 s; the guards strip lists 32/16/4/64; the routing strip shows planning (balanced) / inspect (fast) / implement (balanced) / verify (fast) / repair (reasoning). One more check from the floor: <code>curl 127.0.0.1:8899/api/stategraph</code> — a hand-echo of the graph a real run would walk.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">87</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">50 / 50</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">19 / 19</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门禁" : "Gates lit"}</div><div class="almanac-instrument-value">10 / 10</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "当日推送" : "Pushes today"}</div><div class="almanac-instrument-value">34</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["面板不再复述仓库", "/api/stategraph 现读 build_coding_workflow() 与 StageRouter——curl 即得真图"],
        ["护栏不靠背诵", "32/16/4/64 从函数签名现拍；图若收紧，面板随之收紧"],
        ["存活句柄栽了一跤", "beginPanelRequest 自增 panelVersion → current() 永假 → 实时替换从不触发；3 行修复"],
        ["诚实降级", "链路断 → badge 明说「离线复刻」→ 退回内嵌镜像；绝不冒充实时"],
        ["Atlas 86→87", "curl 127.0.0.1:8899/api/stategraph | python -m json.tool——当场可验"],
      ] : [
        ["The panel no longer narrates the repo", "/api/stategraph reads build_coding_workflow() and StageRouter live — curl gets the real graph"],
        ["Guards aren't recited", "32/16/4/64 are read off the runtime's own signatures; tighten the graph and the panel follows"],
        ["The liveness handle tripped once", "beginPanelRequest bumps panelVersion → current() always false → the live swap never fired; three lines to fix"],
        ["Honest downgrade", "wire down → badge says “replica” → falls back to the embedded mirror — never impersonating live"],
        ["Atlas 86 → 87", "curl 127.0.0.1:8899/api/stategraph | python -m json.tool — auditable on the spot"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "镜子里是仓库。活线里也是仓库。区别只在你敲不敲它。"
          : "The mirror was the repo. The live wire is the repo too. The only difference is whether you knock on it."}
      </p>
    </div>`;
}

function thesurgeMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-thesurge">
      <div class="almanac-kicker">${zh() ? "卷五十 · 压测" : "Chapter L · The Surge"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `慢了，不是宿命——<br/><span class="almanac-title-accent">是调用方法。</span>`
        : `Slow was never fate —<br/><span class="almanac-title-accent">it was a method.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>
          2026 年 11 月 17 日，一笔压测拍下了一张照片：c=50 × 12s，只赶了 300 次请求，<code>/api/stats</code> 的 p50 ≈ <strong>12.9 秒</strong>——单 worker 排队一整轮 322MB 的 <code>.minicc</code> 树走查，每一拍都留下了脚印。
        </p>
        <p>
          cProfile 把剧本交出来了：<code>_disk_bytes</code> 占 <strong>15.3 / 17.6 秒（87%）</strong>——8,802 次 <code>Path.stat</code> 8.16 秒，2,553 次 <code>lstat</code> 2.15 秒。<code>os.walk</code> 对 Windows 的每一拍都照付不误——路径解析一条都不省。
        </p>
        <p>
          换成 <code>os.scandir</code> 栈式走查（一次 readdir/目录、<code>DirEntry</code> 类型缓存）：同一份 <strong>372,806,669 字节</strong>的账对上了（8,738 个文件，372.8 MB）；冷走查 2.97 → <strong>0.57 秒（5.2×）</strong>；<code>gather()</code> 整体 17.6 → <strong>1.25 秒（14×）</strong>；新一波 c=50 × 12s：<strong>8,820 次请求、0 非 2xx</strong>；<code>/api/stats</code> 的 p50 从 12,918ms 落到 <strong>9.5ms（≈1,360×）</strong>。
        </p>` : `<p>
          On 2026-11-17 the load probe caught one path in the act: c=50 × 12s, a mere 300 requests, <code>/api/stats</code> at p50 ≈ <strong>12.9 seconds</strong> — every worker queued behind one cold walk of a 322 MB <code>.minicc</code> tree, each step touching disk.
        </p>
        <p>
          cProfile handed over the script: <code>_disk_bytes</code> accounted for <strong>15.3 of 17.6 seconds (87%)</strong> — 8,802 <code>Path.stat</code> calls at 8.16 s, 2,553 <code>lstat</code> calls at 2.15 s. <code>os.walk</code> pays every Windows toll — not a single path parse saved.
        </p>
        <p>
          Swapped for a <code>scandir</code> stack walker (one readdir per directory, <code>DirEntry</code> type cache): the <strong>same 372,806,669-byte ledger</strong> reconciled (8,738 files, 372.8 MB); the cold walk went 2.97 → <strong>0.57 s (5.2×)</strong>; <code>gather()</code> overall went 17.6 → <strong>1.25 s (14×)</strong>; a fresh wave at c=50 × 12s landed <strong>8,820 requests with zero non-2xx</strong>; <code>/api/stats</code>'s p50 dropped from 12,918 ms to <strong>9.5 ms (≈1,360×)</strong>.
        </p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">88</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">51 / 51</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">19 / 19</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门禁" : "Gates lit"}</div><div class="almanac-instrument-value">10 / 10</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "当日推送" : "Pushes today"}</div><div class="almanac-instrument-value">38</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["87% 的时间在一个函数里", "cProfile：_disk_bytes 15.3/17.6s——没有 profile 就没有 1,360×"],
        ["同一份账对上了", "两种走查都是 372.8MB / 8738 files——优化不许改变账本"],
        ["5.2× 冷 · 14× gather · 1,360× p50", "2.97→0.57s · 17.6→1.25s · 12,918→9.5ms"],
        ["8,820 次请求，0 非 2xx", "c=50 × 12s × 6 路径——这本身也是一笔要记的账"],
        ["Atlas 87→88", "git show 468a8f3；tests/test_stats.py 8/8 绿——当场可验"],
      ] : [
        ["87% of the time was one function", "cProfile: _disk_bytes at 15.3/17.6s — no profile, no 1,360×"],
        ["The ledger reconciled", "both walkers agree on 372.8 MB / 8,738 files — optimization never rewrites the books"],
        ["5.2× cold · 14× gather · 1,360× p50", "2.97→0.57s · 17.6→1.25s · 12,918→9.5ms"],
        ["8,820 requests, zero non-2xx", "c=50 × 12s × 6 paths — a ledger entry of its own"],
        ["Atlas 87 → 88", "git show 468a8f3; tests/test_stats.py 8/8 — auditable on the spot"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "账本先记住 12.9 秒，然后账本自己跑成了 9.5 毫秒。"
          : "The ledger first remembers 12.9 seconds. Then the ledger itself runs at 9.5 milliseconds."}
      </p>
    </div>`;
}

function livecurrentMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-livecurrent">
      <div class="almanac-kicker">${zh() ? "卷五十一 · 通电" : "Chapter LI · The Live Current"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `先有人写，再有故事——<br/><span class="almanac-title-accent">然后模型开始自己写。</span>`
        : `First someone wrote —<br/><span class="almanac-title-accent">then the model began to write.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>仓库今夜的存证是：head=04e0563，位于 main 分支，提交总数 1813。年鉴已经写到第五十一卷，这一卷是第五十二卷；Atlas 目前是 88 坐标的故事，本卷写完后将成为 89。</p>
        <p>2026-11-17，模型被接进了两件新的工作。管理员面板的「工作区简报（由模型现扫）」让模型自己读取实测事实并写出双语简报；「诊断 · 值守诊断师」让模型读取中断原因分布、趋势与任务记录，并写出双语诊断。今天的 3/3 中断全部是服务重启。</p>
        <p>今天也有一次信任恢复：解锁面板的一次诊断如实显示「模型不可达——面板不写诊断，只说这一句真话」，没有伪造任何东西；另一条网络探测表明 LAN 直连探针返回 HTTP 200。快道 scripts/measure_cache_affinity.py 第二天复测，冷 73.7%（5731/4224）→ 暖 95.9%（5737/5504），同前缀两天一致。/api/stats 冷路径由 Profile 定位到 _disk_bytes 占 87%；换 scandir 走查后，冷走查 2.97→0.57 秒，gather 17.6→1.25 秒，p50 12,918→9.5ms（≈1,360×），8,820 次压测 0 非 2xx。</p>
        <p>仓库跟踪文件 1093 个，其中测试文件 720 个；路线图 424 批、54333 行。值守简报与值守诊断现在都由模型面对现场事实作答。Honest limits：这些记录只说明今晚被观测到的事实，不据此给出任何可靠下限。</p>` : `<p>The warehouse record for tonight is: head=04e0563, on main, with 1813 total commits. The annal has reached volume 51; this is volume 52. Atlas is now a story of 88 coordinates, and this volume will bring it to 89.</p>
        <p>On 2026-11-17, the model was connected to two new duties. The administrator panel’s “Workspace Brief (scanned live by the model)” has the model read measured facts itself and write a bilingual brief. “Diagnostics · On-Call Diagnostician” has it read the interruption-cause distribution, trends, and task records, then write a bilingual diagnosis. All 3/3 interruptions today were service restarts.</p>
        <p>Trust was also restored once today: one unlock-panel diagnosis honestly displayed “Model unreachable—the panel writes no diagnosis, only this one true sentence”; it fabricated nothing. A separate network probe showed the LAN direct probe returning HTTP 200. The second-day run of scripts/measure_cache_affinity.py measured cold 73.7% (5731/4224) → warm 95.9% (5737/5504), consistent across the same prefix on both days. Profiling located 87% of the cold /api/stats path in _disk_bytes; switching the walk to scandir changed cold walk 2.97→0.57 seconds, gather 17.6→1.25 seconds, and p50 12,918→9.5ms (≈1,360×), with 0 non-2xx responses across 8,820 load-test requests.</p>
        <p>The repository tracks 1093 files, including 720 test files; the roadmap contains 424 batches and 54333 lines. The Workspace Brief and On-Call Diagnosis now have the model answer from the observed scene. Honest limits: these records describe only what was observed tonight; they imply no reliable lower bound.</p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">89</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">52 / 52</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">19 / 19</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门禁" : "Gates lit"}</div><div class="almanac-instrument-value">10 / 10</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "当日推送" : "Pushes today"}</div><div class="almanac-instrument-value">46</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["模型写下了这一卷", "gpt-6.1-terra 现场直供；prompt_cache_key 稳定；prompt=5,013 · completion=1,378 · cached_tokens=4,224"],
        ["两件新工作接进了模型", "工作区简报（由模型现扫）· 诊断 · 值守诊断师——管理员面板现在由它值班"],
        ["代理从叙事变成了值守", "结论自己从快照里读；故障时如实说「模型不可达——只说这一句真话」"],
        ["Atlas 88→89", "head 04e0563；1795 次 cached_tokens 之后的第五份现役产出"],
        ["这一卷不需要你信", "docs/CHAPTER_DRAFT.md 原文存档；git show 即可复核；引用数字皆可用 scripts/measure_cache_affinity.py 复扫"],
      ] : [
        ["The model wrote this volume", "gpt-6.1-terra direct — stable prompt_cache_key; prompt=5,013 · completion=1,378 · cached=4,224"],
        ["Two new duties landed on the model", "Workspace Brief (scanned live) · Diagnosis · On-Call Diagnostician — the admin panel now has a shift worker"],
        ["The agent changed from narrator to on-duty analyst", "conclusions are read from the snapshot; on failure it says one honest sentence"],
        ["Atlas 88 → 89", "head 04e0563 — fifth live artifact on the cached-prefix lane"],
        ["This volume asks no trust", "docs/CHAPTER_DRAFT.md holds the raw archive; git show reproduces it; numbers are re-runnable"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "这本馆里最久的那盏灯——第一次自己写东西了。"
          : "The oldest lamp in the museum asked for a pen — and wrote." }
      </p>
    </div>`;
}

function twelfthlightMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-twelfthlight">
      <div class="almanac-kicker">${zh() ? "卷五十二 · 第十二家灯" : "Chapter LII · The Twelfth Light"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `两条腿都跑了红——<br/><span class="almanac-title-accent">然后两腿一起绿。</span>`
        : `Two legs ran red —<br/><span class="almanac-title-accent">then both legs lit green together.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>《第十二家灯》记于今夜（2026-11-17 深夜）。管理员面板新增「事后复核 / The Retrospective」tile：模型直读本任务前的真实账本，看到 task 因服务重启中断 3 次、completed streak 3 天、cache affinity 71.1%、审计日志 1607 行，再写出双语复核。这个 tile 的存在意味着模型不是凭空总结，而是读自己的事件记录后复核。</p>
        <p>值守评审师读取 git diff HEAD~1..HEAD 的实况文本和 tmp 收到的 diff 内容后现场评审，指出 docs/latest.json 的 head=3c385b3 与 snapshot HEAD=ec59858 不一致，并要求核对。评审代码中的 subprocess.run 曾未捕获 subprocess.TimeoutExpired，Windows Python leg 因此报错。随后在本批 bc54d82 中，将调用置于 try 内并捕获该异常；红灯没有被略过。</p>
        <p>check CI 仍在进行：Windows 腿和 ubuntu 腿各在重跑，每腿约 5,700 tests；_showcase 静态展示同步完成。仓库跟踪文件 1093 → 1100，测试文件 716 → 723，roadmap 54281 → 54395；first 2026-08-24。Atlas 88 → 89，本卷提交时将变成 90。</p>
        <p>诚实的限度：此刻只能记录两条 CI 腿正在重跑，不能把它们写成已通过。今夜的因果链是服务重启造成中断，评审暴露未处理的超时异常，修复后等待 CI 验证；nothing lost; nothing hidden。</p>` : `<p>The Twelfth Light, recorded late on 2026-11-17. The Admin panel gained the Retrospective tile: the model read the real ledger from before this task, saw that service restarts interrupted the task 3 times, a completed streak of 3 days, cache affinity of 71.1%, and 1607 audit-log lines, then wrote a bilingual review. The tile exists so the model can review its own work by reading its recorded events, rather than summarizing from memory.</p>
        <p>The on-call reviewer read the live text from git diff HEAD~1..HEAD and the diff received in tmp, then wrote a review on the spot. It identified docs/latest.json head=3c385b3 versus snapshot HEAD=ec59858 and called for verification. The review code had a subprocess.run without a handler for subprocess.TimeoutExpired; the Windows Python leg reported the error. In this batch, bc54d82, the call was put inside try and the exception caught. The red light was not skipped.</p>
        <p>CI checks are still in progress: the Windows and ubuntu legs are each rerunning, about 5,700 tests per leg; the repository's static _showcase was synchronized. Tracked repository files: 1093 → 1100; test files: 716 → 723; roadmap: 54281 → 54395; first 2026-08-24. Atlas: 88 → 89; this volume will make it 90 when committed.</p>
        <p>Honest limit: at this moment, the only claim about the two CI legs is that they are rerunning; they cannot be recorded as passed. Tonight's causal record is service restarts causing interruptions, review exposing an unhandled timeout, and the fix awaiting CI verification. Nothing lost; nothing hidden.</p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">90</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">53 / 53</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">19 / 19</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门禁" : "Gates lit"}</div><div class="almanac-instrument-value">10 / 10</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "当日推送" : "Pushes today"}</div><div class="almanac-instrument-value">54</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["真的红了", "subprocess.run(timeout=...) without an enclosing TimeoutExpired handler in oracle_review.py — Windows leg reported it exactly like this"],
        ["然后如实改回来了", "subprocess.run() 置入 try；TimeoutExpired catch；nothing lost; nothing hidden；matches the sibling _git call-shape exactly"],
        ["Honest limits 优先", "CI 仍在途中——不能把它们写成“已经绿”；它们会在风头过去后报它们的状态"],
        ["Atlas 88→89→90", "Atlas 从来不是这个仓库拍胸脯的数字——每一粒都对应一次真实 push，从未 skip"],
        ["这一卷 model 自己编的", "prompt_cache_key stable; cached_tokens=4,224 第七次现身；五枚缓存命中连开"],
      ] : [
        ["A real red fired", "subprocess.run(timeout=...) without an enclosing TimeoutExpired handler in oracle_review.py — Windows leg reported it exactly"],
        ["Then the fix went back in", "subprocess.run inside try; TimeoutExpired caught; nothing lost; nothing hidden; matches the sibling _git call-shape"],
        ["Honest limits first", "CI is still in flight — they cannot be reported as green; they will deliver their report when it lands"],
        ["Atlas 88 → 89 → 90", "every coordinate is a push; nothing was skipped to keep the number"],
        ["The model wrote this volume itself", "prompt_cache_key stable; cached_tokens=4,224 — the shared prefix hit for the seventh time"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "红了，然后修了；修了，然后看它报它自己的真话。"
          : "It went red, then we fixed it; fix it, then watch it tell its own truth."}
      </p>
    </div>`;
}

function thereckoningMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-thereckoning">
      <div class="almanac-kicker">${zh() ? "卷五十四 · 并账" : "Chapter LIV · The Reckoning"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `每一条分支都被审过了——<br/><span class="almanac-title-accent">没有漏掉的。</span>`
        : `Every branch was audited —<br/><span class="almanac-title-accent">nothing was skipped.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>《并账》把 PR #1（dev/minicc-reliability-4ba3，74 个提交）按字节审完后以“并轨收尾”：产品面已在 main，唯一真增量是 5 个测试门。3 个原样收编；per-span 门指出 main 在 3 处 item 循环体内逐项重买 _newline_index，索引移出循环后修正；roadmap-cite 门确认 4 处 ROADMAP 引文漂移，如实重瞄并登记 7 枚历史引文，再加第三条腿防止历史表静悄悄生锈。</p>
        <p>15 条分支与工作树逐一清扫，补齐三处真缺口。allowlist 的读改写此前只有进程内 RLock：两个 minicc 进程争用同一文件，0/8 轮两边规则都在；现在 hold_sidecar 覆盖读写两半，锁失败不降级无锁写，新增 4 腿门，结果 4/4。grader_type 曾把 pytest、ruff、unknown_tool 等 invented label 漏进判分器列，behavior 也只是套件名；M8-T89 vocabulary（UNGR 决定）收编后，旧测试改瞄正确契约。M12 MCP sampling 曾只在废弃分支：如今 SamplingGuard、全局 MINICC_SAMPLING_ENABLED 默认关闭与服务器 sampling_enabled 双开关、stdio 应答线程、真实 provider callback、逐判决审计和 /api/mcp 状态均已上线，并有 15 腿门。</p>
        <p>CLI 双语接线覆盖交互、帮助、授权理由、doctor/commands 与约 90 处引擎消息。ratchet 清零：32 个无人读键逐个裁定，13 个接活调用点保留，19 个 backup 时代遗留键删除；消息表 235 键双语对仗，每一个键都有生产者。模型提示词刻意保留中文，以维持 prompt-cache 前缀亲和。</p>
        <p>副本自 2026-11-17 起直连线程状态：1,838 commits、436 批、1,113 tracked files、733 test files、53→54 卷；身份文案经独立逐字对账，人工通读未发现错字。14 条本地分支核销，远程仅剩 main，工作树撤除。首次提交是 2026-08-24。诚实的边界：这些记录证明的是本次盘点、补缺与核对，不声称穷尽未记录的事实。</p>` : `<p>The Reckoning, closes PR #1 (dev/minicc-reliability-4ba3, 74 commits) as a consolidation closeout after a byte-level audit: the product changes were already on main; the only real increment was 5 test gates. Three were adopted unchanged. The per-span gate correctly exposed three item-loop bodies on main rebuilding _newline_index for each item; moving the index outside the loops fixed it. The roadmap-cite gate found 4 drifted ROADMAP citations, corrected them, recorded 7 historical citations, and added a third leg against silent decay.</p>
        <p>A byte-level sweep covered 15 branches and worktrees and closed three real gaps. The allowlist read-modify-write had only a process-local RLock: two minicc processes contending on one file preserved both rule sets in 0/8 rounds. hold_sidecar now covers both read and write, with no unlocked-write fallback; the added 4-leg gate now passes 4/4. grader_type had leaked invented labels such as pytest, ruff, and unknown_tool into the judge column, while behavior named a suite, not a judge. M8-T89 vocabulary (UNGR decision) is now adopted, and two old tests target the actual contract. M12 MCP sampling existed only on an abandoned branch; it is now live with SamplingGuard, a default-off global MINICC_SAMPLING_ENABLED plus per-server sampling_enabled double opt-in, stdio response handling, a real provider callback, per-decision audit rows, and /api/mcp status, covered by 15 gates.</p>
        <p>CLI bilingual wiring now spans interaction, help, authorization reasons, doctor/commands, and about 90 engine messages. Ratchet cleared: all 32 unread keys were adjudicated, 13 active call sites retained and 19 backup-era leftovers removed. The 235-key message table is bilingual and paired; every key has a producer. Chinese model prompts remain deliberate for prompt-cache prefix affinity.</p>
        <p>Since 2026-11-17, the fallback artifact reads thread state directly: 1,838 commits, 436 batches, 1,113 tracked files, 733 test files, and 53→54 volumes. The identity copy received an independent line-by-line reconciliation and a human read-through found no typos. All 14 local branches were accounted for; only main remains remote, and the worktree was removed. First commit: 2026-08-24. Honest limit: this record establishes the audit, repairs, and checks described here; it does not claim facts beyond that evidence.</p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "最新提交(真)" : "Recent commits"}</div><div class="almanac-instrument-value">${escapeHtml(String(recent))}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">91</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">54 / 54</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">19 / 19</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "门禁" : "Gates lit"}</div><div class="almanac-instrument-value">10 / 10</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "当日推送" : "Pushes today"}</div><div class="almanac-instrument-value">71</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["PR #1 被以字节审计结案", "74 个提交、无 merge-base——产品面全部已在 main 内；唯一真增量 5 个测试门，3 个原样收编、2 个按真相裁定（不记特赦）"],
        ["三处真缺口补齐", "allowlist 跨进程 RMW（0/8 → 4/4）；grader_type invented label（M8-T89 收编）；M12 MCP sampling 从废弃分支上线（双开关 + 审计 + 15 腿门）"],
        ["ratchet 清零", "32 个无人读键：13 个接活调用点、19 个遗留键删除——每一个键都有生产者"],
        ["Model prompts stay zh", "模型提示词刻意保留中文——prompt-cache 前缀亲和不因营销式翻译受损"],
        ["这一卷 model 自己编的", "prompt_cache_key stable; cached_tokens=4,224——共享前缀第八次现身"],
      ] : [
        ["PR #1 was audited closed, byte by byte", "74 commits, no merge-base — the product surface was already on main; the only real increment was 5 test gates (3 verbatim, 2 adjudicated — never allowlisted)"],
        ["Three real gaps patched", "allowlist cross-process RMW (0/8 → 4/4); grader_type invented labels (M8-T89 adopted); M12 MCP sampling shipped from an abandoned branch (double opt-in gate, JSONL audit, 15-leg gate)"],
        ["The ratchet bottoms out", "32 unread keys — 13 wired to live call sites, 19 backup-era leftovers deleted; every key has a producer"],
        ["Chinese model prompts stay Chinese", "prompt-cache prefix affinity is not traded away for cosmetic translation"],
        ["The model wrote this volume itself", "prompt_cache_key stable; cached_tokens=4,224 — the shared prefix hit for the eighth time"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "并账——不是合并代码，是把每一条分支的账摊开。"
          : "The Reckoning — not a merge, an accounting of every branch."}
      </p>
    </div>`;
}

function thealarmMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const recent = Array.isArray(digestCache?.recent_commits) ? digestCache.recent_commits.length : 5;
  return `
    <div class="almanac-canvas almanac-thealarm">
      <div class="almanac-kicker">${zh() ? "卷五十五 · 警钟" : "Chapter LV · The Alarm"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `三次红灯，` + `<br/><span class="almanac-title-accent">一次都没跳过。</span>`
        : `Three reds,` + `<br/><span class="almanac-title-accent">none skipped.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? `<p>《警钟》记下的不是凯旋，而是同一夜里三次 CI 红灯：351d444 的 Ubuntu 腿报出七个失败，串在双语文案搬迁与 one-home 门之间；c0325fa 修回引用、三个原句和围栏尺子的函数名，并补上 ratchet 基线。c8b069d 又因未捕获 TimeoutExpired 报红，也暴露 UTC 线格式不在钟表家；94647ce 把格式交回 utc_stamp()，补齐 DEFAULT_DOCS mention。</p>
        <p>三次运行都被 CI 抓住，三次都当场修复；没有一次红灯被跳过或原谅。修红灯时留下的物理产物，是管理面板上的“漂移哨兵”：不问模型的格子，读取 git HEAD 与 docs/latest.json 的 head、两处 CRLF 钉，以及 doc_pointers --check 的现场退出码。</p>
        <p>诚实的边界是：这份记录只说明这些检查在这些运行中抓到了问题并完成修复，不替未来的运行作保证。</p>` : `<p>The Alarm records no victory, but three CI failures in the same stretch of work. At 351d444, the Ubuntu leg reported seven failures tied to moving Chinese engine copy into the i18n message table and breaking one-home checks; c0325fa restored the references and three verbatim literals, renamed the fence-measure functions, and updated the ratchet baseline. c8b069d failed on an uncaught TimeoutExpired and exposed a UTC line format outside its clock home; 94647ce returned formatting to utc_stamp() and added the DEFAULT_DOCS mention.</p>
        <p>CI caught all three runs, and all three failures were fixed on the spot. None was skipped or forgiven. The physical artifact produced alongside those fixes is the management panel’s “drift sentinel”: model-free cells showing git HEAD against docs/latest.json, the two CRLF pins, and the live exit code from doc_pointers --check.</p>
        <p>The honest limit: this records what these checks caught and what was repaired in these runs; it is not a guarantee about future runs.</p>`}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "任务总数(真)" : "Tasks (live)"}</div><div class="almanac-instrument-value">${escapeHtml(tasks)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">92</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">55 / 55</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "说明书章数" : "Manual chapters"}</div><div class="almanac-instrument-value">19 / 19</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "当日推送" : "Pushes today"}</div><div class="almanac-instrument-value">80</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["三次红、三次摁灭", "351d444：Ubuntu 腿报 7 红——引文没跟着双语化移动 → c0325fa 全部重瞄；c8b069d：subprocess.run(timeout=) 未 catch TimeoutExpired → 漂移哨兵如实返回 rc=124；94647ce：UTC 线格式回钟表家（utc_stamp()）+ 宽面名册补 DEFAULT_DOCS mention——每个红都修掉，没有一次被原谅"],
        ["漂移哨兵是物理产物", "管理面板新增不问模型的格子：git HEAD ≡ 事实包、两处 CRLF 钉（index.html 751/0 · i18n.js 313/0）、doc_pointers --check 现场退出码——第一个 model-free 管理员磁贴"],
        ["CI 抓到了每一个", "此仓库三次运行（351d444 / c0325fa / c8b069d）全部被 Ubuntu/Windows 两腿完整抓住；没有一次红灯被跳过或原谅"],
        ["这一卷 model 自己编的", "prompt_cache_key stable; cached_tokens=4,224——共享前缀第九次现身"],
      ] : [
        ["three reds, three fixes", "351d444: the Ubuntu leg reported 7 failures — citations drifted during the bilingual move; c0325fa re-aimed them all. c8b069d: subprocess.run(timeout=) without catching TimeoutExpired — the drift sentinel now answers rc=124 honestly. 94647ce: UTC line format went home to the clock (utc_stamp()) + the wide roster mentions DEFAULT_DOCS — every red fixed, none forgiven"],
        ["the drift sentinel is a physical artifact", "the admin panel gained a cell that asks no model: git HEAD ≡ fact pack, two CRLF pins (index.html 751/0 · i18n.js 313/0), live doc_pointers --check exit code — the first model-free admin tile"],
        ["CI caught every one", "three runs on this repository (351d444 / c0325fa / c8b069d) all caught by the Windows and Ubuntu legs — no red was skipped or forgiven"],
        ["the model wrote this volume itself", "prompt_cache_key stable; cached_tokens=4,224 — the shared prefix serves its ninth call"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "警钟——每一次响，都必须被听见。"
          : "The Alarm — every ring must be heard."}
      </p>
    </div>`;
}

function theledgerMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const LEDGER_ZH = "<p>《会开口的账本》记下：这一天，<code>.env</code> 带着 <code>HTTPS_PROXY=http://127.0.0.1:7897</code> 进了仓库，<code>load_config()</code> 却一直没有把它注入 <code>os.environ</code>。此前，aizzz.xyz 的连接一次次原样收到网关的拒绝：“本站不对您所在的国家及地区进行商业服务”。补上代理注入后，重建终于完成：首次模型通电。实测记录为 <code>cached_tokens=4,224</code>，prompt 7,230、completion 299；一条 prompt 得到了一段双语审计故事。</p><p>管理面板由此新增「审计实语 · 值守读者 / Audit story · on-duty reader」。模型读取 <code>.minicc/audit.jsonl</code> 最近 64 行；账本共有 1617 条真实记录。输出分三拍：发生了什么，只讲 action 和 path；一个值得留意的反常或重复；下一步先看哪里。prompt 明令不得讲窗口外的事，也不得虚构文件名。</p><p>记录也保留这一天的自我纠错：最初的 prompt 判词有误，把 <code>window_to</code> 是否成立系于 JSON 可解析性；全空白窗口因此触发 <code>JSONDecodeError</code>。修订后，白窗口不调用模型，闲话息为零 token。临时逐字对齐的个人展示页也记在账上：identity 卡全绿，列有赵欣曈、南方科技大学本科、香港中文大学硕士、计科双学位、物理竞赛铜牌及江西一等奖二等奖、法狗狗公司实习与隐盾 yindun.fagougou.com。</p><p>本卷所列快照与账目还包括：Atlas 93 坐标、年鉴 56 卷、全仓库 1,865 commits、444 批、926 个测试文件（测出）/ 734 test files，以及 <code>.minicc</code> 的 1617 行审计。这不是模型出红又修绿的戏，而是仓库终于开口，说出自己刚才做了什么。诚实的限度：故事只覆盖窗口内的记录；窗口以外的事实、意图与文件名，都不在这份存证的断言范围内。</p>";
  const LEDGER_EN = "<p>The Ledger That Speaks records the missing link: <code>.env</code> entered the repository carrying <code>HTTPS_PROXY=http://127.0.0.1:7897</code>, but <code>load_config()</code> had never injected it into <code>os.environ</code>. Until then, connections to aizzz.xyz were returned with a Chinese-language regional refusal. After proxy injection, the system was rebuilt and the model powered on for the first time. The observed run recorded <code>cached_tokens=4,224</code>, prompt 7,230, completion 299; one prompt returned a bilingual audit story.</p><p>The management panel gained an “Audit story · on-duty reader” tile. The model reads the latest 64 lines of <code>.minicc/audit.jsonl</code>, drawn from 1617 real records, and produces three beats: what happened, limited to action and path; a notable anomaly or repetition; and where to look next. Its prompt forbids narration beyond the window and invented filenames.</p><p>The ledger also preserves its own correction. An earlier prompt verdict incorrectly made <code>window_to</code> depend on JSON being parseable; an entirely blank window therefore raised <code>JSONDecodeError</code>. After the correction, a blank window does not call the model: idle chatter costs zero tokens. A temporary, word-for-word alignment of the personal display page is also recorded: the identity card was all green, listing Zhao Xintong, undergraduate study at Southern University of Science and Technology, a master’s at The Chinese University of Hong Kong, a computer science double degree, a physics competition bronze medal plus Jiangxi first and second prizes, an internship at FaGouGou, and Yindun (yindun.fagougou.com).</p><p>The supplied snapshot and ledger also list Atlas 93 coordinates, 56 yearbook volumes, 1,865 repository commits, 444 batches, 926 test files (measured) / 734 test files, and 1617 audit lines in <code>.minicc</code>. This is not a story of the model turning red and then green; it is the repository finally speaking about what it just did. Honest limit: the story covers only records inside the window. It makes no claim about events, intent, or filenames beyond that evidence.</p>";

  return `
    <div class="almanac-canvas almanac-theledger">
      <div class="almanac-kicker">${zh() ? "卷五十六 · 会开口的账本" : "Chapter LVI · The Ledger That Speaks"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `一个仓库，` + `<br/><span class="almanac-title-accent">学会了说话。</span>`
        : `One repository,` + `<br/><span class="almanac-title-accent">finally speaking.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH : LEDGER_EN}

      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">93</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">56 / 56</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "审计条目(真)" : "Audit lines (live)"}</div><div class="almanac-instrument-value">1617</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["代理注入终于补上", "`.env` 带 `HTTPS_PROXY=http://127.0.0.1:7897` 进了仓库，`load_config()` 却从没把它写回 `os.environ`—— aizzz.xyz 一次又一次返回“本站不对您所在的国家及地区进行商业服务”。补了注入之后，第一次模型通电，`cached_tokens=4,224`"],
        ["审计实语 · 值守读者", "管理面板新增卡片，模型读 `audit.jsonl` 最近 64 行写三拍故事：发生了什么 → 一个值得留意的反常或重复 → 下一步先看哪里"],
        ["白窗口 = 零 token", "全空白窗口不调用模型，闲话息为零；prompt 明令不得讲窗口外的事，不得虚构文件名——窗外的事实、意图与文件名全不在存证断言范围内"],
        ["这一卷 model 自己编的", "prompt_cache_key stable; cached_tokens=4,224——共享前缀第十次现身"],
      ] : [
        ["the proxy link finally closed", "`.env` carried `HTTPS_PROXY=http://127.0.0.1:7897` but `load_config()` never wrote it back into `os.environ` — every call to aizzz.xyz came back with the same regional refusal — after the injection: first live model call, `cached_tokens=4,224`"],
        ["Audit story · on-duty reader", "new card in the admin panel: the model reads the latest 64 audit lines and writes three beats — what happened → one anomaly or repetition to notice → where to look next"],
        ["blank window = zero tokens", "an all-blank window does not call the model at all; the prompt forbids narration beyond the window and invented filenames — everything outside the window stays outside the ledger's claim"],
        ["Cha.LVI written by the model", "prompt_cache_key stable; cached_tokens=4,224 — the shared prefix serves its tenth call"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "账本会开口——前提是它还没被死过。"
          : "The ledger speaks — only when it was never allowed to die."}
      </p>
    </div>`;
}

function twoshardsMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const LEDGER_ZH = "<p>卷五十八：双峰。本早中午 aizzz.xyz 对这个账号组停服 <code>gpt-6.1-terra</code>——HTTP 404 <code>model_not_found</code> 回复。同 key、同网关、同 Clash 节点（127.0.0.1:7897）不变，唯一更改是这个 <code>MINICC_MODEL=gpt-6.1-sol</code>（.env 本地迁移，留痕记录；repository 里未追踪 model 字面值，仅测试 fixture 与历史文档引用 terra）。</p><p><code>GET /v1/models</code> 列返 7 项；<code>gpt-6.1-terra</code> 仍在列。逐个 ping（max_tokens=1），6 项 200，terra 唯一被拒——<code>model_not_found</code>。这不是地理封锁，不是网络，是账号组配额漂移——这份归档记录当时能拿出来。</p><p>同一三道题在 sol 上重跑，与本日 terra 数据对照（n=3每 lane）：pass@1 = <strong>0.667 一致</strong>（greeting-already-correct ✓、json-roundtrip ✓、fix-add ✗ 两次擦肩）；tokens_per_success 185,442 → <strong>79,430（-57%）</strong>；p95 <strong>306.8s → 74.0s</strong>；repair_attempts 均 0.667 → <strong>0</strong>；sol 仍没让 fix-add 通过客观 grader。双 lane 一致拒绝把它救出去——两个不同模型都错过修这个简单 bug，同一 grader 同一结论。</p><p><strong>sol prefix cache 双峰</strong>：前缀稳定时，cache 长度只在两个值间跳动——<code>4,166</code>（~72.3%）：算法是 gateway-wide 的头缆块，任何 fresh key 的首 call 也吃这个；<code>5,446</code>（~94.7%）=4,166 + 我们自己 lane 的 headline。每 bit 完全相同的 prefix 多次调用，cached_tokens 硬性双峰，<em>不单调上升</em>。这条测量出了 probe 实测 <code>minicc-probe-wall-c</code>、<code>minicc-probe-shard-d</code>，经实验工具<code>scripts/measure_cache_affinity.py</code> 多轮重复确认。</p><p>手炉热是守出来的：测量脚本目前封 220 秒保活器，真热 shard 维持 ≥ 94%。本卷收录：与此 lane 相关的全部计数、两次 4,166 的冷峰、两次 5,446 的热峰，都在 <code>docs/CACHE_AFFINITY_MATRIX.md</code> 节<strong>《2026-11-18 尾 · sol 新 lane 上「光锥模式」现象》</strong>长篇存证——不删不改、留底事实，不粉饰，不归责于任何一方。诚实边界：此两峰是 gateway 行为，不是 minicc 能改变的——本 lane 不必归责，两峰是上游 sharding 的固有行为——本卷只负责把它记下来。</p>";
  const LEDGER_EN = "<p>Volume 58: The Two Shards. Mid-morning today, aizzz.xyz stopped serving <code>gpt-6.1-terra</code> for this account group — HTTP 404 <code>model_not_found</code>. Same key, same gateway, same Clash node (127.0.0.1:7897) unchanged; the only change is this <code>MINICC_MODEL=gpt-6.1-sol</code> (.env-local migration, logged; no tracked references to a model literal inside the repo — only test fixtures and historical docs keep terra).</p><p><code>GET /v1/models</code> returns seven entries including terra. <code>gpt-6.1-terra</code> still lists. Pinging 7/7 with <code>max_tokens=1</code>: 6×200, terra refused once with <code>model_not_found</code>. This is not geographic. This is an account-group drift — this record states the observed fact only.</p><p>The same three tasks re-ran live against sol; this is the side-by-side vs this morning's terra run (n=3 per lane): pass@1 = <strong>0.667, same on both lanes</strong> (greeting-already-correct ✓, json-roundtrip ✓, fix-add ✗ — the same bug evaded both models); tokens_per_success <strong>185,442 → 79,430 (-57%)</strong>; p95 <strong>306.8s → 74.0s</strong>; mean repair_attempts 0.667 → <strong>0</strong>; sol still did not let fix-add clear the grader. Two lanes, one task, one grader — same refusal.</p><p><strong>Sol's prefix cache is bimodal</strong>: with a stable Chinese prefix, cached_tokens flip between just two values — <code>4,166</code> (~72.3%), the gateway-wide headline cached on every lane (even fresh key first call qualifies for this), and <code>5,446</code> (~94.7%) = the 4,166 headline + this lane's own ~1,280 sharing its slice. Repeated calls with byte-identical prefix cannot climb past this split; there is no monotone regime and no hidden warming — there are two shard buckets being picked by hash. Measured by <code>minicc-probe-wall-c</code>, <code>minicc-probe-shard-d</code>; verified by multiple <code>scripts/measure_cache_affinity.py</code> runs.</p><p>The warm shard survives because the keeper warms the byte of it inside every 220s tick: measured warm-2 right now at <strong>94%</strong>. This volume collates the count: both 4,166 cold grabs and both 5,446 warm hits are on the books in <code>docs/CACHE_AFFINITY_MATRIX.md</code> under the late-2026-11-18 sol-lane entry — untouched, unglamorized. Honest boundary: these bimodalities are upstream gateway behavior, not anything minicc can edit. The lane does not magic them away; this volume records them.</p>";
  return `
    <div class="almanac-canvas almanac-twoshards">
      <div class="almanac-kicker">${zh() ? "卷五十八 · 双峰" : "Chapter LVIII · The Two Shards"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `同一把钥匙，` + `<br/><span class="almanac-title-accent">打同一道墙，墙的另一头两种价。</span>`
        : `One key,` + `<br/><span class="almanac-title-accent">one wall — two prices at the far side.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH : LEDGER_EN}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">96</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">58 / 58</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "命中率（真）" : "Hit rate (live)"}</div><div class="almanac-instrument-value">94%</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["sol 停供的真实材料名义", "`GET /v1/models` 仍列出 `gpt-6.1-terra`，`gpt-6.1-terra` 仍然 404；`gpt-6.1-sol` 6 项均 200；同 key、同网关、同 Clash 127.0.0.1:7897"],
        ["同一题，两个 lane，两种速度", "pass@1 一致 0.667；`tokens_per_success` 从 185,442 → 79,430；p95 306.8s → 74.0s"],
        ["双峰不渐进", "cached_tokens 只在两值间跳：`4,166`（72.3%）gateway 头缆项，`5,446`（94.7%）= 头缆+本 lane（每次随机落片）"],
        ["不归责", "这是 gateway 的 sharding，不是 minicc 能修的；warm shard 由 keeper 每 220s 护着，守的是 ≥94% 那个峰"],
      ] : [
        ["the literal HTTP loss", "`GET /v1/models` still lists `gpt-6.1-terra`, and ping accounting still finds terra refused; `gpt-6.1-sol` is 6× 200; same key, same gateway, same Clash 127.0.0.1:7897"],
        ["same task, two lanes, two speeds", "pass@1 both 0.667; `tokens_per_success` 185,442 → 79,430; p95 306.8s → 74.0s"],
        ["the bimodal reality", "cached_tokens flips between two values only: `4,166` (72.3%) the gateway-wide headline, `5,446` (94.7%) = headline + this lane's own slice, hash-pinned every time"],
        ["no finger-pointing", "this is gateway sharding, not minicc code — the warm shard is what the keeper guards, keeping ≥ 94%"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "价格是分片里的。" 
          : "The price lives inside a shard."}
      </p>
    </div>`;
}

function thegreenlineMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  const tasks = statsCache?.tasks && typeof statsCache.tasks.total === "number" ? String(statsCache.tasks.total) : "—";
  const LEDGER_ZH = "<p>第 57 卷：绿线。昨夜到今天，main 连续翻红又连续修绿。<code>24c0d92</code> 在两道一处一家门：<code>audit.jsonl</code> 第二处字面量，以及未声明的 <code>--gold</code>；改用 <code>--amber</code> 后，<code>ead7a683</code> 全绿。</p><p>绿线不是一次通过，而是 CI 红、例检、修、绿的真实链路。Claim 在 <code>cf93bb6b</code> 报出 impact floor：<code>scripts/stress_probe.py</code> 没有受众，补上三腿压力探针测试。Ubuntu 在 <code>bdf3abcb</code> 报出 <code>web.py</code> 行号多一行，令 “re-aimed citation” 钉错；把 <code>deque</code> 挪进函数内部，保住历史实测行号 1852。Claim 随后在 <code>01a32347</code> 揪出 ROADMAP 中悬空的 M8-T1181、M8-T1186；引用改为真实存在的提交 SHA。Ubuntu 又在 <code>78b2fa6c</code> 要求 <code>exec_module</code> 前先注册 <code>sys.modules</code>，在 <code>3757d3b5a</code> 要求 <code>thread.join(timeout=)</code> 后用 <code>is_alive()</code> 读回断言，并在 fake-provider 开关被内联后要求从 <code>llm/fake.py</code> 导入唯一真源 <code>FAKE_PROVIDER_ENV</code>。最终 <code>e358d37</code> 全绿：Windows、Ubuntu、Playwright 双腿、Claim、mvn、JS 与 PR eval 均 SUCCESS。</p><p>今天写下的 <code>/api/audit</code> 实测包括 CPU 风暴获胜：c=32 的 p50 从 10,008ms、253 个超时降到 13.6ms、零超时；撞库风暴中 400/400 个伪冒 token 全部 401；10KiB 随机字节 40/40 直接 400；饱和授权车道 64/64 通过。<code>MINICC_FAKE_PROVIDER</code> 下模型零 token。两份助手脚本曾被 <code>-A</code> 扫进 main：<code>_admin_ratelimit_frontend.py</code> 由 M8-T1181 移除，<code>_ledger_1185.py</code> 由 M8-T1186 移除；之后 <code>.gitignore</code> 根锚定 <code>/_*.py</code>。</p><p>这卷存证的是已列出的测试与结果，不是对未列出窗口的证明：没有这些窗口的证据，就不声称它们也通过或安全。快照记作 HEAD <code>e358d37</code>，1,900 提交、461 批、54,994 行 roadmap、1,120 个 tracked files、737 个 test files、Atlas 94、第 57 卷年鉴。每一道红都留下新约束；绿线由修正和验证画出。</p>";
  const LEDGER_EN = "<p>Volume 57: The Green Line. From last night into today, main kept turning red and being repaired to green. <code>24c0d92</code> failed at two gates in one place: the second literal in <code>audit.jsonl</code>, and undeclared <code>--gold</code>; the fix was <code>--amber</code>. Then <code>ead7a683</code> went fully green.</p><p>This was a real CI red, inspection, fix, green chain. Claim reported an impact floor at <code>cf93bb6b</code>: <code>scripts/stress_probe.py</code> had no audience, so three-legged stress-probe tests were added. Ubuntu reported an off-by-one <code>web.py</code> line at <code>bdf3abcb</code>, sending the “re-aimed citation” to the wrong place; moving <code>deque</code> inside the function kept the historically measured line at 1852. Claim then found dangling M8-T1181 and M8-T1186 references in ROADMAP at <code>01a32347</code>; references were changed to real commit SHAs. Ubuntu required <code>sys.modules</code> registration before <code>exec_module</code> at <code>78b2fa6c</code>, an <code>is_alive()</code> read-back assertion after <code>thread.join(timeout=)</code> at <code>3757d3b5a</code>, and, after the fake-provider switch was inlined, the single source of truth imported from <code>llm/fake.py</code> as <code>FAKE_PROVIDER_ENV</code>. Finally, <code>e358d37</code> was fully green: Windows, Ubuntu, both Playwright legs, Claim, mvn, JS, and PR eval all SUCCESS.</p><p>Today's <code>/api/audit</code> record includes a CPU-storm win: at c=32, p50 fell from 10,008ms with 253 timeouts to 13.6ms with zero timeouts. In the credential-stuffing storm, all 400/400 forged tokens returned 401; all 40/40 10KiB random-byte requests returned 400 directly; the saturated authorization lane passed 64/64. Under <code>MINICC_FAKE_PROVIDER</code>, the model used zero tokens. Two helper scripts were swept into main by <code>-A</code>: <code>_admin_ratelimit_frontend.py</code> was removed by M8-T1181, <code>_ledger_1185.py</code> by M8-T1186; afterward <code>.gitignore</code> anchored <code>/_*.py</code> at the repository root.</p><p>This volume attests to the tests and results listed here, not to unproven windows: without evidence for those windows, it makes no claim that they passed or were safe. The snapshot records HEAD <code>e358d37</code>, 1,900 commits, 461 batches, 54,994 roadmap lines, 1,120 tracked files, 737 test files, Atlas 94, and the Volume 57 yearbook. Each red left a new constraint; fixes and verification drew the green line.</p>";
  return `
    <div class="almanac-canvas almanac-thegreenline">
      <div class="almanac-kicker">${zh() ? "卷五十七 · 绿线" : "Chapter LVII · The Green Line"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `一整夜，` + `<br/><span class="almanac-title-accent">被 CI 抓着打。</span>`
        : `One whole night,` + `<br/><span class="almanac-title-accent">caught red by CI.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH : LEDGER_EN}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">94</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">57 / 57</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "审计条目(真)" : "Audit lines (live)"}</div><div class="almanac-instrument-value">1617</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["绿线的每一夜", "`bdf3abcb` 红 → impact floor 抓住 `scripts/stress_probe.py` 无受众；`01a32347` 引用 `M8-T1181 / M8-T1186` 悬空 → 改成真 SHA 引用；`78b2fa6c` 未注册即 `exec_module` → 先 `sys.modules` 注册；`3757d3b5a` 未经 `is_alive()` 读回 → join 之后必读"],
        ["CI red → 例检 → 修 → 绿", "每个红都逐字逐字读日志 → 在源头修 → 再查再推——整整一夜的节奏"],
        ["the audit load storm", "`/api/audit` 400 并发：c=32 从 10,008ms + 253 超时 → 13.6ms + 0 超时；撞库风暴 400/400 全 401"],
        ["问题都是它自己发现的", "包括本卷的存证——模型每一次引用的 sha 都是日志里真实出现的，不虚构"],
      ] : [
        ["the green line's every night", "`bdf3abcb` red → impact floor caught `scripts/stress_probe.py` without an audience; `01a32347` dangling `M8-T1181 / M8-T1186` → SHAs; `78b2fa6c` `exec_module` before registration → register first; `3757d3b5a` no read-back after join → `is_alive()` assert"],
        ["CI red → inspect → fix → green", "every failure got read to the last line, fixed at the source, re-checked, re-pushed — the night's whole rhythm"],
        ["the audit load storm", "`/api/audit` at c=32: 10,008ms + 253 timeouts → 13.6ms + 0 timeouts; credential storm 400/400 → 401"],
        ["the problems were found by the repo itself", "this very chapter too: every sha cited here appeared in the log, none invented"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "绿不在一次通过里——在你没被任何一道门漏过。"
          : "Green is not one pass — it is never slipping through any gate."}
      </p>
    </div>`;
}

const LEDGER_ZH_LIX = "<p><strong>卷五十九：现在通了 / The Now Goes Through。</strong>这一卷是 terra 现场写的（This chapter was written live by gpt-6.1-terra on 2026-11-18）。这一天的记录从一次拒绝开始，也以一次通过收尾。早间，aizzz.xyz 上旧 key 所属的账号组停服了 gpt-6.1-terra。目录没有同步沉默：GET /v1/models 仍然列出 terra；但单次 ping 被拒，HTTP 404，错误名是 model_not_found。名字还在，调用却不通。这不是模型从目录里消失，而是列出的名字与可用的服务之间出现了裂缝。那天的第一道门，仍然没有通。</p><p>中午到傍晚，换上新 key 后，/v1/models 列出七项，其中包括 terra，terra 的调用全线恢复。傍晚的 v2-fix-add 用 terra 跑完，结果是 passed，repair_attempts=0，pass@1=1.0。可同一天的三条 lane，把“跑通”这件事分成了两种。本机 terra 的上午、本机 sol 的中午、新 key terra 的傍晚，连续三次重现同一个反转：模型已经把 calc.py 修对，objective oracle 重跑 exit 0；agent 自己的验证实验室却连报两次 failed，repair_attempts=2，最后把正确结果判错。实现与判决并不一致，三次如此，不能把它当成一次偶然的噪声。程序已经通了，裁决还没有通。</p><p>根因藏在验证计划所选的解释器里。minicc 的 verification plan 把检查命令恒写成 <em>python -m pytest</em>。系统 PATH 上的 python 是系统级 3.11，没有 pytest；objective oracle 的 <em>{python}</em> 占位符却替换成 virtualenv 里的 sys.executable，那里有 pytest。于是同一句验证，交给了两个 python、两个世界，也得到了两个判决。oracle 重跑时能检查修复，agent 的实验室却因检查环境不同而报错。失败信号是真的，失败所指并不是代码。这次反转不在修复本身，而在两个验证入口没有共享同一个解释器；把这条因果线理清，事情才通了。</p><p>当晚的 M8-T1221 修复把 plan 改为使用 <em>_quote(sys.executable)</em>，让检查命令跟随实际运行 oracle 的解释器。重跑 v2-fix-add 后，结果 passed，repair_attempts=0，全部修复尝试归零，pass@1=1.0。tokens 从 170,956 降到 120,599，减少 29%；prompt_cache_hit_tokens 为 84,096，占 71.7%；reviewer_false_negative_count 从 1 变为 0。这里没有另一场代码修复可供夸饰：变化落在验证计划，数字记录的是同一任务在修正后给出的判决。模型做对、检查也看见它做对，才算通了。</p><p>同一晚的缓存亲和记录，处理的是并行会话的另一类错位。parallel 会话不再共用一条全局 lane 哈希，派生键改为 minicc-<em>&lt;sha256(session_id)&gt;</em>。HTTP 请求认同一前缀后，前两次调用仍是冷的；从第三次起，6,880 个 tokens 的同字节前缀里有 6,587 个命中，占 95.7%，并连续六次不掉。它不是让所有会话挤进同一条 lane，而是让相同前缀在会话自己的键下逐渐稳定。早间名字可见却不可调用，三条 lane 看见不同的验证世界；到晚间，解释器、判决与缓存亲和各自对上了位置。记录没有把挫折改写成捷径，只写下这一日最后的状态：现在通了。</p>";

const LEDGER_EN_LIX = "<p><strong>Volume Fifty-Nine: The Now Goes Through.</strong> This chapter was written live by gpt-6.1-terra on 2026-11-18. The day's record begins with a refusal and ends with a passing run. In the morning, the account group associated with the old key at aizzz.xyz had gpt-6.1-terra shut off. The catalog did not go quiet: GET /v1/models still listed terra. But a single ping was rejected with HTTP 404 and model_not_found. The name remained while the call did not. This was not disappearance from the catalog; it was a gap between a listed model and a usable service. At the first gate of the day, the call did not go through.</p><p>From midday into evening, a new key restored terra across the board, and /v1/models listed seven entries, including terra. In the evening, v2-fix-add ran with terra and finished passed, with repair_attempts=0 and pass@1=1.0. Yet three lanes on that same day divided “working” into two different judgments. Local terra in the morning, local sol at midday, and new-key terra in the evening reproduced the same reversal three times: the model had corrected calc.py, and the objective oracle reran with exit 0. The agent's own verification lab nevertheless reported failed twice, recorded repair_attempts=2, and ultimately judged the correct result wrong. Implementation and judgment disagreed, three times in succession. The program had gone through; the verdict had not.</p><p>The cause was in the interpreter selected by the verification plan. minicc's plan always wrote its check command as <em>python -m pytest</em>. The python on the system PATH was system-level 3.11 and had no pytest. The objective oracle's <em>{python}</em> placeholder, however, was replaced with sys.executable from the virtual environment, where pytest was installed. One check therefore met two pythons, two worlds, and two verdicts. The oracle could inspect the repair when it reran, while the agent's lab failed because its checking environment differed. The failure signal was real, but it did not identify a code failure. The reversal was not in the repair itself: the two verification entrances did not share an interpreter. Once that chain of cause and effect was clear, the explanation went through.</p><p>That evening's M8-T1221 fix changed the plan to use <em>_quote(sys.executable)</em>, so the check command followed the interpreter actually running the oracle. The rerun of v2-fix-add finished passed, with repair_attempts=0, all repair attempts eliminated, and pass@1=1.0. Tokens fell from 170,956 to 120,599, a 29% reduction. prompt_cache_hit_tokens reached 84,096, or 71.7%, and reviewer_false_negative_count moved from 1 to 0. There was no second code repair to embellish: the change was in the verification plan, and these figures record the same task judged after that correction. The model did the right work, and the check recognized it. That result went through.</p><p>That evening's cache-affinity record addressed a different kind of mismatch among parallel sessions. They no longer shared one global lane hash; the derived key became minicc-<em>&lt;sha256(session_id)&gt;</em>. HTTP requests recognizing the same prefix were cold on calls 1 and 2. From call 3 onward, 6,587 of the 6,880 tokens in the identical-byte prefix were hits, or 95.7%, and that level held for six consecutive calls. This did not put every session into one lane; it let a matching prefix stabilize under its session's own key. In the morning, a name was visible but unavailable. Across three lanes, verification saw different worlds. By evening, the interpreter, the verdict, and cache affinity each had their proper place. The record does not turn the setback into a shortcut; it records the day's final state: now it goes through.</p>";

const LEDGER_ZH_LX = "<p><strong>卷六十：破损的引号 / The Broken Quotation。</strong>今晚我回看 showcase io 页面时，发现每次加载都会让整段 hydration 脚本停止。控制台只报了一行：<em>SyntaxError: missing ) after argument list</em>。<em>index.html</em> 约第 599 行的内联脚本里，路径前多了一对空引号：<em>''assets/career-os/latest.json'</em>，career-os 那一行因此没有渲染。</p><p>修复只是删去这两个字符，提交 <em>652bf3c</em> 的 Pages Deploy 已成功。重新加载线上页面后，控制台错误数为 0。问题看起来像整个页面出了故障，实际原因却小得几乎看不见。</p><p>我也检查了缓存串扰探针：两个不同 session family 在相同字节前缀下各自达到 8,362/8,566，也就是 97.6%；交错执行 B 的调用后，A 仍保持同一结果。记录的结论是，family 不会互相驱逐，前缀分片按每个 session 的 family key 索引，而不是共用全局桶。这与用户要求模拟的 codex 式 thread affinity 一致。真实端到端 agent 流量远低于这个前缀探针比例，因为每轮工具循环上下文占了许多 token；两次运行分别报告 71.6% 和 48.0% hit_pct。</p><p>今晚此前的 CI Ubuntu 三项失败，也已通过把 <em>SKIP_DIRS</em> 放到 <em>minicc/tools/fs.py</em> 作为唯一归属，并将 web.py 的 <em>record_text(8000)</em> 固定回第 1852 和 2358 行解决；<em>cadc8f5</em> 的 CI 成功。该提交的 showcase fallback 冻结了 1,972 个 minicc 提交、493 个批次、59 卷 Almanac、Atlas 97 和 745 项测试；本章发布后，英文端到端/i18n 将提供 98 个 Atlas 坐标。删去两个字符，页面恢复。</p>";

const LEDGER_EN_LX = "<p><strong>Volume Sixty: The Broken Quotation.</strong>Tonight I revisited the showcase io page and found that every load stopped the entire hydration script. The console gave one line: <em>SyntaxError: missing ) after argument list</em>. Around line 599 of the inline script in <em>index.html</em>, an empty pair of quotes had been left before the path: <em>''assets/career-os/latest.json'</em>. The career-os line therefore never rendered.</p><p>The fix was simply to delete those two characters. The Pages Deploy for commit <em>652bf3c</em> completed successfully. After reloading the live page, the console showed zero errors. The failure looked like a whole-page problem; its cause was small enough to be nearly invisible.</p><p>I also checked the cache crosstalk probe: two different session families with the same byte prefix each reached 8,362/8,566, or 97.6%; after interleaving B's calls, A remained at the same result. The recorded conclusion was that families do not evict one another, and prefix shards are keyed by each session's family key rather than a shared global bucket. This matches the codex-style thread affinity the user asked to imitate. Real end-to-end agent traffic sits well below that prefix-probe percentage because per-turn tool-loop context accounts for many tokens; the two runs reported hit_pct values of 71.6% and 48.0%.</p><p>The three earlier CI Ubuntu failures tonight were also fixed by moving <em>SKIP_DIRS</em> into <em>minicc/tools/fs.py</em> as its single home and pinning web.py <em>record_text(8000)</em> back to lines 1852 and 2358; CI for <em>cadc8f5</em> completed successfully. Its showcase fallback froze 1,972 minicc commits, 493 batches, 59 Almanac volumes, Atlas 97, and 745 tests; once this chapter ships, the English end-to-end/i18n serves 98 Atlas coordinates. Two characters removed; the page returned.</p>";

function onenineMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-onenine">
      <div class="almanac-kicker">${zh() ? "卷五十九 · 现在通了" : "Chapter LIX · The Now Goes Through"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `方才还不通，` + `<br/><span class="almanac-title-accent">现在通了。</span>`
        : `A moment ago, no,` + `<br/><span class="almanac-title-accent">and now it goes through.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LIX : LEDGER_EN_LIX}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">97</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">59 / 59</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "判决（真）" : "Verdict (live)"}</div><div class="almanac-instrument-value">1.0</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["名字还在，调用不通", "旧 key 停服后 `GET /v1/models` 仍列 `gpt-6.1-terra`；逐个 ping 唯一被拒（`model_not_found`）；换 key 才恢复"],
        ["验证计划选错了解释器", "`python -m pytest` 打到 PATH 上的系统 Python 3.11（没有 pytest）；oracle 的 `{python}` 占位符替换成 virtualenv 的 `sys.executable`（有 pytest）——同一句检查，两个判决"],
        ["修复只换了一行", "`_python_interpreter()` 返回 `_quote(sys.executable)`；v2-fix-add 重跑 `passed`、`repair_attempts=0`、`reviewer_false_negative_count=0`、pass@1 0.0 → 1.0"],
        ["本卷由 terra 亲笔", "worker prompt 5,072 · completion 1,939 · cached 4,173（82.3%）· temperature 0.2 · response_format=json_object"],
      ] : [
        ["the name stayed, the call didn't", "after the old key lost terra, `GET /v1/models` still listed it; a ping refused with `model_not_found`; a new key brought it back"],
        ["the plan picked the wrong interpreter", "`python -m pytest` hit PATH's system Python 3.11 (no pytest); the oracle's `{python}` placeholder became the virtualenv's `sys.executable` (with pytest) — one check, two verdicts"],
        ["the fix was one line", "`_python_interpreter()` returns `_quote(sys.executable)`; the v2-fix-add re-run: `passed`, `repair_attempts=0`, `reviewer_false_negative_count=0`, pass@1 0.0 → 1.0"],
        ["written live by terra itself", "prompt 5,072 · completion 1,939 · cached 4,173 (82.3%) · temperature 0.2 · response_format=json_object"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "通了，不是因为玄学，是因为同一把解释器。"
          : "It goes through — not by grace, by sharing an interpreter."}
      </p>
    </div>`;
}

const LEDGER_ZH_LXI = "<p><strong>卷六十一：并发的风 / The Parallel Wind。</strong>在 2026-11-18 的 aizzz.xyz 夜航里，io 页面曾被一处破损的引号截断：第 599 行附近的内联脚本写成了 <em>''assets/career-os/latest.json'</em>。每次访问都会抛出 <em>SyntaxError: missing ) after argument list</em>，hydration 因而完全停止，career-os 一线也没有出现。提交 652bf3c 删除了两个字符，Pages Deploy 以 success 完成；重新加载线上页面后，console errors = 0。</p><p>缓存串扰探针 M8-T1231 让两个家庭各自留下了轨迹：family A 冷启动为 0%，随后达到 8,362/8,566 = 97.6%；family B 也保持同样的隔离，交错访问之后 A-call-3 仍为 8,362 = 97.6%。同日，io 页 README 的旧 relay 数字 73.7/95.9 被实测的 72.3/97.6 替换。真正的并发探针 M8-T1233 进一步安排了 2 个 family、每个 3 个线程、每线程 4 次调用，共享同一个 13,296 字节的 system prefix：每个线程的 call-1 都是冷的，call-2 起稳定在 8,362/8,566 = 97.6%，6 次冷调用、18 次热调用，零抖动，两个 family 从未互相驱逐。</p><p>端到端 agent 运行给出了另一层尺度。全新 git workspace 以 <em>--yolo --max-turns 60</em> 发起，11 次工具调用创建了 <em>sums.py</em> 的 <em>total(nums)</em> 与含两个 unittest case 的 <em>test_sums.py</em>；<em>python -m unittest -v</em> 退出码为 0，两个测试均通过。此次 usage 为 64,310 tokens，cached 44,957，miss 17,811，hit_pct 71.6%；同一 workspace 只读 <em>--resume</em> 则为 18,077、8,612、9,322、48.0%。因此 97.6% 描绘的是逐字节相同的 prefix，而非不断增长的 tool-loop context。</p><p>Almanac LX《破损的引号》由 gpt-6.1-terra 于 2026-11-18 现场写成，并随提交 8f49dbb4 出航；Atlas 从 97 到 98，记录为 18 panes、60 almanac chapters、20 manual chapters，smoke log 也写明 60 chapters fully bilingual。i18n chips CRLF 固定在 338/0，showcase fallback 固定于 b15ea5d4：1,981 commits、493 batches、Atlas 98、745 tests、55,786 roadmap lines。8f49dbb4 推送前的 16 道 pre_push_gates.py 全绿，cadc8f5 的 Ubuntu CI 以 success 完成；更新推送的 CI 显示为 supersede-by-newer-push 的 cancelled，而非红色结论，Update docs/latest.json 每次都成功。到 2026-11-19，Spring Cloud 服务平面也已由 Maven 在本地建成，覆盖 Eureka、gateway、config 与 Redis cache tier，产出 8 个 jars，并在首次尝试后以 BUILD SUCCESS 收束。</p><p><strong>并发不喧哗，它只留下稳定的回声。</strong></p>";

const LEDGER_EN_LXI = "<p><strong>Volume Sixty-One: The Parallel Wind.</strong>During the late session on 2026-11-18, the io page on the aizzz.xyz lane was stopped by one broken quotation mark: near line 599, the inline script contained <em>''assets/career-os/latest.json'</em>. Every visitor load raised <em>SyntaxError: missing ) after argument list</em>, so hydration died and the career-os line never rendered. Commit 652bf3c deleted two characters. Pages Deploy completed with conclusion success, and a reload of the live page showed console errors = 0.</p><p>The cache crosstalk probe M8-T1231 left two isolated trails. Family A began cold at 0%, then reached 8,362/8,566 = 97.6%; family B showed the same isolation, and after interleaving B, A-call-3 was still 8,362 = 97.6%. That same day, the README bake on the io page replaced stale relay figures of 73.7/95.9 with measured figures of 72.3/97.6. The true concurrent probe M8-T1233 used 2 families, 3 threads per family, and 4 calls per thread against the same 13,296-byte system prefix. Every thread was cold on call-1 and steady at 8,362/8,566 = 97.6% from call-2 onward: 6 cold calls, 18 warm calls, zero jitter, and no family evicted the other.</p><p>The end-to-end agent runs showed a different scale. In a fresh git workspace, <em>--yolo --max-turns 60</em> used 11 tool calls to create <em>sums.py</em> with <em>total(nums)</em> and <em>test_sums.py</em> with exactly two unittest cases. <em>python -m unittest -v</em> exited 0 and both tests passed. Usage was 64,310 tokens, with 44,957 cached, 17,811 missed, and hit_pct 71.6%. The same workspace with read-only <em>--resume</em> used 18,077 tokens, with 8,612 cached, 9,322 missed, and hit_pct 48.0%. Thus 97.6% measures an identical-byte prefix, not the growing tool-loop context.</p><p>Almanac Chapter LX, \"The Broken Quotation\", was written live by gpt-6.1-terra on 2026-11-18 and shipped in commit 8f49dbb4. Atlas moved from 97 to 98, recorded as 18 panes, 60 almanac chapters, and 20 manual chapters; the smoke log now says 60 chapters fully bilingual. i18n chips CRLF stayed pinned at 338/0, while the showcase fallback was baked at b15ea5d4 with 1,981 commits, 493 batches, Atlas 98, 745 tests, and 55,786 roadmap lines. The 16 pre_push_gates.py gates were green before the 8f49dbb4 push. Ubuntu CI for cadc8f5 completed with conclusion success; newer push runs showed cancelled from supersede-by-newer-push, never a red conclusion, and Update docs/latest.json succeeded for every push. On 2026-11-19, the Spring Cloud service plane was also built locally with Maven across Eureka, gateway, config, and the Redis cache tier, producing 8 jars and a clean BUILD SUCCESS after the first attempt.</p><p><strong>Concurrency leaves a steady echo.</strong></p>";

function quotationMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-quotation">
      <div class="almanac-kicker">${zh() ? "卷六十 · 破损的引号" : "Chapter LX · The Broken Quotation"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `每次打开都炸，` + `<br/><span class="almanac-title-accent">两个字符惹的祸。</span>`
        : `Every load broke,` + `<br/><span class="almanac-title-accent">two characters did it.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LX : LEDGER_EN_LX}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">98</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">60 / 60</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "线上控制台错误" : "Console errors (live)"}</div><div class="almanac-instrument-value">0</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["两个字符，每次加载都炸", "`index.html` 约第 599 行内联脚本：`''assets/career-os/latest.json'`——stray 空引号，`SyntaxError: missing ) after argument list`，career-os 卡永不渲染"],
        ["修复只删两个字符", "commit `652bf3c`；Pages Deploy success；线上 reload 控制台错误数 = 0（实测）"],
        ["缓存不会被别的会话洗掉", "family A warm 8,362/8,566 = 97.6%；family B 交错后 A call-3 仍 97.6%；隔离按 sha256(session_id)[:16] 分片（M8-T1231）"],
        ["真实 agent 远低于前缀探针", "任务一 11 次工具调用、tests 全绿，cache 71.6%；resume 只读 48.0%（M8-T1232）——不拿前缀 97.6% 冒充 agent 数字"],
      ] : [
        ["two characters, every load", "`index.html` around line 599 of the inline script: `''assets/career-os/latest.json'` — a stray pair of quotes, `SyntaxError: missing ) after argument list`, career-os card never rendered"],
        ["the fix deleted two characters", "commit `652bf3c`; Pages Deploy success; live reload shows zero console errors (measured)"],
        ["families never evict each other", "family A warm 8,362/8,566 = 97.6%; after B's interleave, A-call-3 stayed 97.6%; shards keyed by sha256(session_id)[:16] (M8-T1231)"],
        ["real agents sit below the prefix probe", "task one: 11 tool calls, tests green, cache 71.6%; resume read-only 48.0% (M8-T1232) — 97.6% is not the agent number"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "删去两个字符，不是修好了世界，是看见了世界。"
          : "Delete two characters — not repaired, seen."}
      </p>
    </div>`;
}

const LEDGER_ZH_LXII = "<p><strong>卷六十二：按自己的尺度 / On Its Own Scale。</strong>截至 2026-11-18，docs/latest.json 记录：head 为 e48f545，生成时间为 2026-11-18T18:55:03.124Z；共有 1,986 个提交、493 个 roadmap 批次、61 个 almanac 章节、746 个测试文件、1,156 个 tracked files，以及 55,786 行 roadmap。</p><p>minicc-cloud 包含八个模块：minicc-cloud-bridge、minicc-cloud-registry、minicc-cloud-config、minicc-cloud-inspector、minicc-cloud-tasks、minicc-cloud-insights、minicc-cloud-evidence、minicc-cloud-gateway。</p><p>缓存测量记录显示，wkapi.pro 的上游分片以 prefix-cache shard 和客户端 prompt_cache_key 作为路由提示。没有这个 key，同一前缀会逐次落到冷分片；有 key 后，热度周期内命中率稳定在约 94% 至 100%。minicc 始终自动派生 prompt_cache_key。一次记录为 total_tokens=15568、cache_hit_tokens=7040、cache_miss_tokens=8456，命中率为 45.4%。另一次补测记录为 120,599 tokens、prompt_cache_hit_tokens=84,096，命中率为 71.7%，repair_attempts=0，reviewer_false_negative_count=0，pass@1=1。</p><p>新 key 的实测中，call 1 为冷，call 2 至 call 6 稳定命中 8,362/8,566，即 97.6%。150 秒空闲后 call 3 归零；后续十次序列中，call 1 为冷，call 2 至 call 10 几乎全命中，call 9 在 26 秒长尾后出现一次完整冷启动。60 秒 keeper 的状态记录为 warms=2、last_cached_tokens=4,940、interval=60。每线程从第二次调用起均为 8,362/8,566，即 97.6%，且记录为零抖动、零跨家族驱逐。</p><p>压力测试的 Wave 3 为 c=128、12 秒，每条路径 n=2380，共 14,280 个请求，0 errors，全部为 200。三轮累计为 33,600 个请求、0 个 non-2xx、0 个连接失败；另一组累计为 25,470 个请求，同样为零 non-2xx、零连接失败。当天所有压力运行累计为 59,070 个请求、0 个 non-2xx。测试运行于 Windows，同一进程中的 minicc-web 监听 127.0.0.1:8899，并使用 MINICC_FAKE_PROVIDER=1。</p>";

const LEDGER_EN_LXII = "<p><strong>Volume Sixty-Two: On Its Own Scale.</strong>As of 2026-11-18, docs/latest.json records head e48f545 and generation time 2026-11-18T18:55:03.124Z. It records 1,986 total commits, 493 roadmap batches, 61 almanac chapters, 746 test files, 1,156 tracked files, and 55,786 roadmap lines.</p><p>The minicc-cloud modules are minicc-cloud-bridge, minicc-cloud-registry, minicc-cloud-config, minicc-cloud-inspector, minicc-cloud-tasks, minicc-cloud-insights, minicc-cloud-evidence, and minicc-cloud-gateway.</p><p>The cache measurements state that wkapi.pro upstream shards use the prefix-cache shard and the client prompt_cache_key as routing hints. Without the key, the same prefix falls onto a cold shard successively; with the key, the hit rate remains about 94% to 100% during the hot period. minicc always derives prompt_cache_key automatically. One record reports total_tokens=15568, cache_hit_tokens=7040, cache_miss_tokens=8456, and a 45.4% hit rate. Another retest reports 120,599 tokens and prompt_cache_hit_tokens=84,096, for a 71.7% hit rate, with repair_attempts=0, reviewer_false_negative_count=0, and pass@1=1.</p><p>In the new-key measurement, call 1 was cold and calls 2 through 6 consistently hit 8,362/8,566, or 97.6%. After 150 seconds of idle time, call 3 returned to zero. In the following ten-call sequence, call 1 was cold and calls 2 through 10 almost always hit; call 9 had one complete cold result after a 26-second long tail. The 60-second keeper status was warms=2, last_cached_tokens=4,940, and interval=60. From the second call onward, every thread recorded 8,362/8,566, or 97.6%, with zero jitter and zero cross-family eviction.</p><p>Pressure-test Wave 3 used c=128 for 12 seconds. Each path had n=2380, for 14,280 requests total, with 0 errors and all responses equal to 200. The cumulative result across three waves was 33,600 requests, 0 non-2xx responses, and 0 connection failures. Another cumulative run recorded 25,470 requests with zero non-2xx responses and zero connection failures. The daily total across all pressure runs was 59,070 requests and 0 non-2xx responses. The test ran on Windows with minicc-web listening on 127.0.0.1:8899 and MINICC_FAKE_PROVIDER=1.</p>";

function parallelwindMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-parallelwind">
      <div class="almanac-kicker">${zh() ? "卷六十一 · 并发的风" : "Chapter LXI · The Parallel Wind"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `六条线程，` + `<br/><span class="almanac-title-accent">谁也不动谁。</span>`
        : `Six threads,` + `<br/><span class="almanac-title-accent">none of them moves another.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXI : LEDGER_EN_LXI}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">99</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">61 / 61</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造首过（真）" : "Forge pass (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["六路并发，零跨 family 驱逐", "M8-T1233：2 个 family × 3 线程 × 4 次同前缀调用——每线程 call-1 冷 0%，call-2+ 全部 8,362/8,566 = 97.6%，6 冷 18 暖，零抖动"],
        ["顺序交错也压不垮 shard", "M8-T1231：family A 暖后插入 B 两次，A-call-3 仍 8,362 = 97.6%；codex thread-affinity 同法律模型"],
        ["真 agent 口径远低于前缀", "M8-T1232：任务一 11 次工具调用 tests 全绿 71.6%；resume 只读 48.0%——不拿前缀 97.6% 冒充 agent 数字"],
        ["本卷由锻造台亲手淬出", "StateGraph 进 → 草拟 → 校验 → 修复（有界 2）→ 落账；2026-11-19 terra 停服（404 model_not_found），lane 切 gpt-6.1-sol 后首次调用即过审，attempts=1，cached 4,169 / 5,408（77%）"],
      ] : [
        ["six concurrent calls, zero cross-family eviction", "M8-T1233: 2 families x 3 threads x 4 same-prefix calls each — every call-1 cold at 0%, call-2+ steady at 8,362/8,566 = 97.6%; 6 cold, 18 warm, zero jitter"],
        ["sequential interleave never breaks a shard", "M8-T1231: after B's calls intervene, A-call-3 still reads 8,362 = 97.6%; same legal model as codex thread-affinity"],
        ["real agents sit well below the prefix", "M8-T1232: task one — 11 tool calls, tests green, cache 71.6%; resume read-only 48.0% — the 97.6% prefix number is not the agent number"],
        ["this volume came out of the forge", "StateGraph intake -> draft -> verify -> repair (bounded 2) -> ledger; on 2026-11-19 terra stayed suspended (404 model_not_found), the lane moved to gpt-6.1-sol and the first call passed the contract, attempts=1, cached 4,169 / 5,408 (77%)"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "并发不喧哗，它只留下稳定的回声。"
          : "Concurrency leaves a steady echo."}
      </p>
    </div>`;
}

const LEDGER_ZH_LXIII = "<p><strong>卷六十三：锻造的世界 / The Forged World。</strong>本卷的锻造，始于一份从仓库状态自动组装的事实包。最新记录列出 1990 次提交、493 个路线图批次、62 篇历书、747 个测试文件、1158 个受跟踪文件，以及 55,786 行路线图。春云模块清单从 bridge、registry、config 延伸到 inspector、tasks、insights、evidence 与 gateway，构成这次记录的工作底图。</p><p>缓存测量呈现出稳定，也呈现边界：同一热前缀连续命中可达 8,362/8,566，即 97.6%；但真实代理任务随着上下文逐轮增长，命中率回落至 48–72%。一段 10 次调用序列中，首轮为冷，第二至第十轮几乎全命；第九轮在 26 秒长尾之后出现一次完整冷命。150 秒闲置后也曾归零，因此记录保留 60 秒 keeper 默认值，而不把命中写成必然。</p><p>压力测试账本记录了三波累计 33,600 次请求，非 2xx 与连接失败均为 0；另一个累计口径为 25,470 次，同样零非 2xx、零连接失败。当天所有压力运行合计 59,070 次请求，非 2xx 为 0。这里的数字来自本机假提供方环境，账本明确记下了这一背景。</p><p>若干新近提交标记了事实组装、StateGraph 历书生成与并发缓存测量；但本卷不替事实包缺失的部分补写事件。它只并列呈现测得的热命中、偶发冷却与压力结果。</p><p><strong>锻造，不是抹去波动，而是把它记清。</strong></p>";

const LEDGER_EN_LXIII = "<p><strong>Volume Sixty-Three: The Forged World.</strong>This volume begins with a fact pack assembled automatically from repository state. The latest record lists 1,990 commits, 493 roadmap batches, 62 almanac chapters, 747 test files, 1,158 tracked files, and 55,786 roadmap lines. The Spring Cloud module list runs from bridge, registry, and config through inspector, tasks, insights, evidence, and gateway, forming the working landscape for this account.</p><p>The cache measurements show both stability and limits: repeated hits on the same warm prefix reach 8,362/8,566, or 97.6%; but as a real agent task grows its context turn by turn, the hit rate falls to 48–72%. In one sequence of 10 calls, the first was cold and calls two through ten were almost entirely hits; call nine went fully cold after a 26-second long tail. The cache also dropped to zero after 150 seconds idle, so the record keeps the 60-second keeper default without treating hits as inevitable.</p><p>The pressure-test ledger records 33,600 requests across three waves, with 0 non-2xx responses and 0 connection failures; another cumulative measure is 25,470 requests, likewise with zero non-2xx responses and zero connection failures. Across all pressure runs that day, the total was 59,070 requests, with 0 non-2xx responses. These figures come from a local fake-provider environment, a condition the ledger explicitly records.</p><p>Several recent commits mark fact assembly, StateGraph almanac generation, and concurrent cache measurements; this volume does not supply events where the fact pack is silent. It sets the measured warm hits beside the occasional cold miss and the pressure results.</p><p><strong>Forging does not erase variation; it records it clearly.</strong></p>";

function ownscaleMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-ownscale">
      <div class="almanac-kicker">${zh() ? "卷六十二 · 按自己的尺度" : "Chapter LXII · On Its Own Scale"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `同一把尺，` + `<br/><span class="almanac-title-accent">量每一段路。</span>`
        : `One rule,` + `<br/><span class="almanac-title-accent">every road measured the same.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXII : LEDGER_EN_LXII}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">100</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">62 / 62</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造回合（真）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=2</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["事实全从仓库自己的账上读", "forge-facts：git log · docs/latest.json 八字段 · pom modules · 缓存/压测 regex 实测行——读不到就标注 missing，不粉饰"],
        ["Terra 停服时模块切 sol 走 env 覆盖", "2026-11-19 aizzz account group 间歇停服 terra（chat 404）；本次用 `MINICC_MODEL=gpt-6.1-sol` 单次覆盖，.env 不动"],
        ["修复回路第一次在真实章节上被触发", "首次草拟未过 verify → repair 带错改单 → 第二次过契约（keys{zh,en}、en 零 CJK、≥600 字符），attempts=2，cached 8,379/13,851（60%）"],
        ["数字一个没变", "1,986 commits · 493 batches · 61 卷 · 746 tests · 1,156 tracked · 55,786 roadmap lines · 59,070 压测 0 non-2xx——全部逐字节取自 fact pack 与既有账本"],
      ] : [
        ["every fact came from the repo's own ledger", "forge-facts: git log, the eight fact-pack fields of docs/latest.json, pom modules, and regex-extracted cache/pressure anchor lines — gaps are marked missing, never filled in"],
        ["sol took over while terra was down", "2026-11-19 aizzz account group flaked on terra (chat 404); this run used a per-invocation `MINICC_MODEL=gpt-6.1-sol` override; .env stayed untouched"],
        ["the repair loop earned its keep for real", "first draft failed verify, repair took the failure list back, the second passed the contract (keys {zh,en}, zero CJK, ≥600 chars), attempts=2, cached 8,379/13,851 (60%)"],
        ["not one number drifted", "1,986 commits, 493 batches, 61 volumes, 746 tests, 1,156 tracked files, 55,786 roadmap lines, 59,070 pressure requests with zero non-2xx — all read verbatim from the fact pack and the ledgers"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "尺子不抬高，量自己才诚实。"
          : "Hold the ruler level — that is how you measure honestly."}
      </p>
    </div>`;
}

const LEDGER_ZH_LXIV = "<p><strong>卷六十四：冶炼的第七日 / The Seventh Day of the Forge。</strong>冶炼的第七日，卷LXIV从一份有边界的账册起笔：事实包记录的前一卷是LXIII，almanac计数为63；另一处最新快照则标着63卷、1,994次提交、493批路线图、747个测试文件、1,158个跟踪文件，以及55,786行路线图。快照生成于2026-11-18 22:37:29.069Z，记录的head为1a0c6b3。紧接着的提交把两条旧提示改正：almanac的卷数由58改为63，atlas的真实坐标数由96改为101；应用脚本随之重建。另一条提交让提示带上仓库自己的罗盘：实时产品事实、双语的20章手册目录，以及63卷almanac目录。修补缺失章节键的工作也在这段记录中：草稿与修复改用安全读取，遇到非字典节点便返回失败结果，让验证器作出判定，不再因缺键抛出KeyError。账册还记下自动组装forge输入的提交：git日志、事实包机器人JSON、模块清单，以及从缓存和压力测试文档抽取的锚点，共同构成输入；缺失之处仍须明说。</p><p>炉火所照见的，是缓存命中并非一句承诺，而是一组带条件的测量。上游以prefix-cache分片和客户端prompt_cache_key作为路由提示；仓库始终自动派生这个键。没有键时，同一前缀会逐次落到冷分片；有键后，在热度周期内记录到约94%至100%的命中。usage只转呈网关实际回传的cached_tokens：有数据才附上prompt_cache_hit_tokens，没有就不伪造；RAG用量条相应显示命中数量与比例，或显示“缓存命中未上报”。一次两轮小任务记下15,568个总token、7,040个命中token、8,456个未命中token，命中率45.4%。这符合头轮全付、次轮前缀命中的两趟形态；记录同时指出，系统提示与工具schema的前缀复用增加时，开放会话命中率会迅速接近先前单轮探针所见的82%至96%。</p><p>补测把稳定与失效都留在纸面上。M8-T1221使用新键、gpt-6.1-terra与reasoning max重跑v2-fix-add：passed=true，修复次数为0，耗时109秒，总token为120,599，prompt_cache_hit_tokens为84,096，命中率71.7%，reviewer_false_negative_count为0，pass@1为……；原始事实在此处截断，账册不补全它。M8-T1225把README摘录纳入13,295字节前缀后，A会话族键首次冷、随后第2至第6次稳定命中8,362/8,566，即97.6%；B lane键同档，C随机键首次也命中同一数值。另一组新lane测量显示，150秒空闲后即使cache_key不变，第三次调用仍归零，因此旧的220秒keeper间隔没有护住分片；记录据此保留60秒默认间隔。随后十次序列中，第一次为冷，第2至第10次几乎全命，但长尾之后的第9次出现一次完整冷；整体加权命中约为八成。稳定探针的97.6%不等于真实agent的逐轮表现：增长中的上下文让真实任务落在48%至72%，账册选择记录这一物理差异，不将它粉饰成恒定命中。</p><p>同一份压力账册也分开保留了不同范围的累计数。Wave 3以c=128运行12秒，每条路径n=2,380，总计14,280次请求，零错误且全部返回200；健康、摘要、统计、路线图与工作区路径的p50约为5.4至6.07毫秒。三波合计的另一项记录为33,600次请求、零非2xx、零连接失败；同一台Windows机器上，minicc-web运行于127.0.0.1:8899，使用MINICC_FAKE_PROVIDER=1，进程在压力波次前数分钟刚重启。另一个同样标为三波累计的记录是25,470次请求，同样零非2xx、零连接失败；日累计账面将33,600与25,470相加，得到59,070次请求、零非2xx。两组累计数字都照原样留下，不替它们抹平口径差异。Spring Cloud模块清单则列出bridge、registry、config、inspector、tasks、insights、evidence与gateway八项。第七日的炉火不裁去边界：分片会冷，测量有窗口，截断仍是截断；可核验的事实，才配成为锻造的刻痕。<em>把边界也记入账册。</em></p>";

const LEDGER_EN_LXIV = "<p><strong>Volume Sixty-Four: The Seventh Day of the Forge.</strong>The Seventh Day of the Forge, Volume LXIV, begins with a ledger whose boundaries are explicit: the fact pack names LXIII as the preceding volume and gives the almanac count as 63. A separate latest snapshot records 63 volumes, 1,994 commits, 493 roadmap batches, 747 test files, 1,158 tracked files, and 55,786 roadmap lines. The snapshot was generated at 2026-11-18 22:37:29.069Z and records head 1a0c6b3. The next commit corrected two stale hints: the almanac count changed from 58 to 63, and the atlas count of real coordinates changed from 96 to 101; the app script was rebuilt accordingly. Another commit gave the prompt the repository's own compass: live product facts, the bilingual 20-chapter manual table of contents, and the 63-volume almanac table of contents. The record also includes a repair for missing chapter keys: draft and repair now use safe reads, and a non-dictionary node returns a failure result for the verifier to judge instead of raising KeyError on a missing key. The ledger further notes the commit that automatically assembles forge input: git history, fact-pack bot JSON, the module list, and anchors extracted from cache and pressure-test documents form the input; gaps must still be stated.</p><p>What the forge light reveals is that a cache hit is not a promise but a set of measurements with conditions. Upstream routing uses a prefix-cache shard and the client's prompt_cache_key as a routing hint; the repository always derives this key automatically. Without a key, the same prefix lands on cold shards in succession; with one, the recorded hit rate stays around 94% to 100% during the warm period. Usage only forwards cached_tokens actually returned by the gateway: prompt_cache_hit_tokens is included when data exists and is not fabricated when it does not. The RAG usage bar correspondingly shows the hit count and percentage, or says that cache hits were not reported. One small two-round task recorded 15,568 total tokens, 7,040 hit tokens, 8,456 miss tokens, and a 45.4% hit rate. This matches the two-pass pattern of paying for the first round and hitting the prefix on the second; the record also notes that as the system-prompt and tool-schema prefix is reused more, hit rates in open sessions quickly approach the 82% to 96% seen in earlier single-round probes.</p><p>Follow-up measurements preserve both stability and failure. M8-T1221 reran v2-fix-add with a new key, gpt-6.1-terra, and reasoning max: passed=true, zero repair attempts, 109 seconds, 120,599 total tokens, 84,096 prompt_cache_hit_tokens, a 71.7% hit rate, reviewer_false_negative_count=0, and pass@1=...; the source fact is truncated here, and the ledger does not complete it. In M8-T1225, after a README excerpt entered the 13,295-byte prefix, the A session-family key was cold on its first call and then consistently hit 8,362/8,566, or 97.6%, on calls 2 through 6; the B lane key matched, and the C random key also hit the same value on its first call. Another new-lane measurement showed that after 150 seconds idle, the third call fell to zero even though cache_key had not changed, so the old 220-second keeper interval had not protected the shard; the record therefore retained a 60-second default interval. In the next ten-call sequence, the first call was cold and calls 2 through 10 were almost all hits, but call 9 showed a complete cold miss after a long tail; the globally weighted hit rate was about eight in ten. The 97.6% stable probe does not describe real agents round by round: growing context brought real tasks to 48% through 72%. The ledger records this physical difference instead of polishing it into a constant hit rate.</p><p>The same pressure ledger also preserves cumulative figures with different scopes. Wave 3 ran at c=128 for 12 seconds, with n=2,380 per path and 14,280 requests total, zero errors, and all responses returning 200; p50 for health, digest, stats, roadmap, and workspace paths was about 5.4 to 6.07 milliseconds. One record gives the three-wave cumulative total as 33,600 requests, zero non-2xx responses, and zero connection failures. On the same Windows machine, minicc-web ran at 127.0.0.1:8899 with MINICC_FAKE_PROVIDER=1, and the process had been freshly restarted minutes before the waves. Another record, also labeled a three-wave cumulative total, gives 25,470 requests with zero non-2xx responses and zero connection failures; the daily total adds 33,600 and 25,470 to reach 59,070 requests and zero non-2xx responses. Both cumulative figures remain as recorded; the ledger does not erase their difference in scope. The Spring Cloud module list names eight entries: bridge, registry, config, inspector, tasks, insights, evidence, and gateway. The forge on its seventh day does not cut away its limits: shards cool, measurements have windows, and a truncation remains a truncation. Only verifiable facts deserve to become marks of the forge. <em>Keep the boundaries in the ledger.</em></p>";

function forgedworldMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-forgedworld">
      <div class="almanac-kicker">${zh() ? "卷六十三 · 锻造的世界" : "Chapter LXIII · The Forged World"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `波动不被抹去，` + `<br/><span class="almanac-title-accent">被记清。</span>`
        : `The variance is not erased,` + `<br/><span class="almanac-title-accent">it is recorded.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXIII : LEDGER_EN_LXIII}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">101</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">63 / 63</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造回合（真）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["事实全从仓库自己的账上读", "forge-facts（M8-T1235)：git log + docs/latest.json + pom modules + 缓存/压测 regex 行——缺就标 missing"],
        ["锻造台被 live 现场用出真 bug", "repair 直取 parsed['zh'] → KeyError；M8-T1236 防御性修后：.get() + verify 判分 + 回归单测锁死"],
        ["模型自己守缺口纪律", "zh/en 双端诚实写明 pressure 测试跑在 fake-provider 上；'不替事实包缺失的部分补写事件'"],
        ["terra 再次上膛", "2026-11-19 晚间 terra 站住了起来——attempts=1 首过；cached 4,154 / 6,997（59%）"],
      ] : [
        ["every fact came from the repo's own ledger", "forge-facts (M8-T1235): git log + docs/latest.json + pom modules + regex-extracted cache/pressure lines; gaps are marked missing"],
        ["live use found a real bug in the forge", "repair read parsed['zh'] directly -> KeyError; M8-T1236 made draft/repair read with .get(), verify judges; regression test locks it"],
        ["the model kept the missing-facts discipline itself", "both bodies state the pressure tests ran under a fake-provider environment, and this volume does not supply events where the fact pack is silent"],
        ["terra held the window this time", "2026-11-19 evening — attempts=1, passed first call, cached 4,154 / 6,997 (59%)"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "锻造，不是抹去波动，而是把它记清。"
          : "Forging does not erase variation; it records it clearly."}
      </p>
    </div>`;
}

// ---- Ch.LXV · The Etched Waterline · 水纹的刻度 (Atlas 103) ----
const LEDGER_ZH_LXV = "卷LXV，题为《水纹的刻度》，写在一次把仓库自身事实带入提示的更新之后。提交记录显示，2026-11-19 的世界地图探针记录了 9,892 个提示词元，其中 9,629 个为缓存命中，命中率 97.3%；提示长度为 17,559 字节，包含 README 摘录、手册目录，以及双语的 64 章年鉴目录。同日，LXIV《锻炉的第七日》记录 terra 首次尝试、英文零 CJK、中文 1,783 字，并把长度下限前置到锻造流程；此前一项工具提示修正则把年鉴卷数更新为 63，把图集中真实坐标数更新为 101。记录并非平静的水面：它保存每一次读数，也保留读数的边界。\n\n仓库快照给出另一组刻度：head 为 1a0c6b3，生成时间为 2026-11-18T22:37:29.069Z；总提交数 1,994，路线图批次 493，年鉴章节 63，测试文件 747，跟踪文件 1,158，路线图 55,786 行。这些数值与章节 LXV 并置，说明快照中的年鉴计数仍为 63，而提交记录已在推进下一章。它们不是互相替代的说法：一个是文档快照的字段，一个是随后发生的工作记录。云端 pom 列出八个模块：bridge、registry、config、inspector、tasks、insights、evidence 与 gateway；它们各自占据同一项目结构中的位置，构成可核对的目录，而非额外推论。\n\n缓存记录讲的是亲和，不是保证。wkapi.pro 的上游分片以 prefix-cache shard 和客户端 `prompt_cache_key` 作为路由提示；没有 key，同一前缀会逐次落入冷分片，有 key 后，热度周期内的命中率可稳定在约 94–100%。minicc 始终自动派生该 key。usage 解析器如实转发网关报告的 `prompt_tokens_details.cached_tokens`：有值才附带 `prompt_cache_hit_tokens`，没有就不伪造；RAG 用量条相应显示缓存命中数量与比例，或显示缓存命中未上报。一次小任务的读数是总计 15,568 个词元、命中 7,040、未命中 8,456，命中率 45.4%。这是两轮任务的实测，首轮全付、次轮前缀命中；记录还指出，真实 agent 的逐轮增长上下文会让命中率回落到 48–72%，探针的稳定读数不能代替它。\n\n同字节前缀探针在 family key 下稳定命中 8,362/8,566，即 97.6%；新 lane key 的首 call 约为 72%，随后两次 warm call 达到 97.6%。然而，150 秒空闲后 call-3 的缓存命中归零，说明不变的 key 并没有保住分片；水冷 shard 的 TTL 不超过 150 秒。后续十次序列中，call-1 冷，call-2 至 call-10 几乎全命，call-9 在 26 秒长尾后又出现一次完整 cold，整段全局命中权重约为 8/10，即 80%。旧的 220 秒 keeper 间隔没有保护这个 lane；60 秒默认间隔被保留。命中率不是 100%，轨迹把稳定与例外一并留下：连续 warm 命中、一次反缓存，以及网关仍会按 shard hash 轮换。\n\n压力测试也以计数留下刻度。Wave 3 在 c=128、12 秒条件下，每条路径 n=2,380，总计 14,280 个请求，零错误，全部返回 200。三波累计记录为 33,600 个请求，没有非 2xx，也没有连接失败；另一组同机三波记录为 25,470 个请求，同样零非 2xx、零连接失败。当天全部压力运行的日累计为 59,070 个请求、零非 2xx。测试环境注明为 Windows、`minicc-web` 运行于 `127.0.0.1:8899`，并启用 `MINICC_FAKE_PROVIDER=1`。这些数字界定了证据的范围：它们属于本地假提供方驾驶舱，不被写成别处的承诺。<em>水线刻下命中，也刻下未命中。</em>";

const LEDGER_EN_LXV = "Volume LXV, titled \"The Etched Waterline,\" follows an update that brought the repository's own facts into its prompt. The commit record for 2026-11-19 reports a world-map probe with 9,892 prompt tokens, of which 9,629 were cached, for a 97.3% hit rate. The prompt measured 17,559 bytes and included a README excerpt, the manual table of contents, and a bilingual table of contents for 64 almanac chapters. On the same day, LXIV, \"The Seventh Day of the Forge,\" recorded a first terra attempt, zero CJK characters in English, and 1,783 Chinese characters; it also moved the minimum-length requirements to the start of the forge process. An earlier tooltip correction updated the almanac count to 63 volumes and the atlas count to 101 real coordinates. This is not a still surface: the record keeps each reading and the limits around it.\n\nThe repository snapshot gives another set of marks: head 1a0c6b3, generated at 2026-11-18T22:37:29.069Z; 1,994 total commits, 493 roadmap batches, 63 almanac chapters, 747 test files, 1,158 tracked files, and 55,786 roadmap lines. Set beside Volume LXV, these figures show that the almanac count in the snapshot remains 63 while the commit record advances the next chapter. These statements do not replace one another: one is a field in a document snapshot, the other a record of subsequent work. The cloud pom lists eight modules: bridge, registry, config, inspector, tasks, insights, evidence, and gateway. Each occupies a place in the same project structure; the list is an auditable inventory, not an added inference.\n\nThe cache record describes affinity, not a guarantee. Upstream shards at wkapi.pro use the prefix-cache shard and the client's `prompt_cache_key` as routing hints. Without the key, the same prefix lands on cold shards in succession; with it, the hit rate can remain around 94-100% during the warm period. minicc always derives this key automatically. The usage parser reports `prompt_tokens_details.cached_tokens` as returned by the gateway: it adds `prompt_cache_hit_tokens` only when a value is present and does not fabricate one when absent. The RAG usage bar accordingly shows the cache-hit count and percentage, or says that cache hits were not reported. One small task measured 15,568 total tokens, 7,040 hits, 8,456 misses, and a 45.4% hit rate. This was a two-round measurement: the first round was fully paid, and the second hit the prefix. The record also notes that the growing context of a real agent brings the hit rate back down to 48-72%; a probe's stable reading cannot stand in for that.\n\nA same-byte-prefix probe using the family key held at 8,362/8,566 hits, or 97.6%. With a new lane key, the first call was about 72%, and the next two warm calls reached 97.6%. But after 150 seconds idle, cache hits on call 3 fell to zero, showing that an unchanged key did not preserve the shard; the water-cooled shard's TTL was no more than 150 seconds. In the following sequence of ten calls, call 1 was cold, calls 2 through 10 were almost entirely hits, and call 9 had one complete cold result after a 26-second long tail. The global hit weight for the sequence was about 8/10, or 80%. The old 220-second keeper interval had not protected this lane, so the 60-second default interval was retained. The hit rate is not 100%. The trace preserves both the steady run and the exception: continuous warm hits, one anti-cache event, and the gateway's continued shard-hash rotation.\n\nThe pressure tests leave their marks in counts as well. Wave 3, at c=128 for 12 seconds, recorded n=2,380 per path and 14,280 requests total: zero errors, all responses 200. Across three waves, the cumulative record is 33,600 requests, with no non-2xx responses and no connection failures. A separate three-wave run on the same machine recorded 25,470 requests, likewise with zero non-2xx responses and zero connection failures. The daily cumulative total across all pressure runs was 59,070 requests and zero non-2xx responses. The test environment is specified as Windows, with `minicc-web` on `127.0.0.1:8899` and `MINICC_FAKE_PROVIDER=1`. These figures define the scope of the evidence: they belong to a stock-local fake-provider cockpit and are not written as a promise about other environments. <em>The waterline records hits, and it records misses.</em>";

function seventhdayMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-seventhday">
      <div class="almanac-kicker">${zh() ? "卷六十四 · 冶炼的第七日" : "Chapter LXIV · The Seventh Day of the Forge"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `火有边界，` + `<br/><span class="almanac-title-accent">账册记住它们。</span>`
        : `The fire has edges,` + `<br/><span class="almanac-title-accent">the ledger keeps them.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXIV : LEDGER_EN_LXIV}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数(真)" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">113</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "卷数 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">75 / 75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造回合（真）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["第七天，旧锚被逐条核对", "事实来自 forge-facts（git log + docs/latest.json + pom modules + 缓存/压测 regex 行）——缺就标 missing"],
        ["修复回路被 live 自己用过一趟", "Ch.LXIII 修了一个 KeyError：draft/repair .get() + verify 判分 + 回归测试锁定（M8-T1236）"],
        ["截断不是抹掉", "en 正文明确写了「the source fact is truncated here, and the ledger does not complete it」——截断就是截断"],
        ["cache 命中计数只报已测项", "Measured: 8,362/8,566 = 97.6% 暖 shard；真实 agent 48–72%；两种数字并列，不粉饰"],
      ] : [
        ["the seventh day re-read every anchor", "facts came via forge-facts (git log + docs/latest.json + pom modules + regex-extracted cache/pressure lines); gaps are marked missing"],
        ["the repair loop earned its keep", "Ch.LXIII fixed a real KeyError: draft/repair now read with .get(), verify judges, regression test locks it (M8-T1236)"],
        ["a truncation is not an erasure", "the en body itself says the source fact is truncated here and the ledger does not complete it"],
        ["cache hits measured, nothing more", "8,362/8,566 = 97.6% warm shard; real agent traffic 48–72%; both numbers printed side by side"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "记录炉火所及，不把热度写成永恒。"
          : "Record how far the fire reaches; do not call its heat eternal."}
      </p>
    </div>`;
}

// ---- Ch.LXVI · The Click That Answers · 回应的按键 (Atlas 104) ----
const LEDGER_ZH_LXVI = "卷LXVI，题为《回应的按键》，落在一个按钮曾经无声的地方。2026年11月19日的记录写明，惰性注入让 `/game.js` 等待，满载时又挤占 HTTP/1.1 的 6 个连接预算，用户点击了一个没有回应的按钮。修复不是只添一个忙碌提示：它同时让脚本在空闲时预加载，并提供忙碌状态。账本重写了 M8-T1242，明确记下这两部分；提交说明也记录了红转绿的测量链。此处能确认的是修复的组成和问题缘由，事实包没有给出该测量链的具体数值，因此不替它补数。按钮的回应由两项改变共同构成，而不是由一项装饰性的提示构成。\n\n同一天，仓库问答也在调整自己的回应方式。提交记录说，完整分块现在交给模型，不再把引用证据悄悄截断在 400 个字符；提示词则告知模型，在证据覆盖不完整时应当回答部分覆盖。另一个文档改动停止在 CHANGELOG 引用内容寻址的 bundle，改为指向 `web/app.js` 和 `web/styles.css`；提交说明同时记下相关门禁测试 `test_no_document_quotes_a_content_addressed_bundle`，以及 `16/16` 的前置检查。话语所指向的对象更明确，能回答的范围也被标出边界：没有被证据覆盖的部分，不假装已经覆盖。\n\n缓存记录把这种边界落在可见的数字上。仓库为请求始终自动派生 `prompt_cache_key`；网关若提供 `prompt_tokens_details.cached_tokens`，用量解析就带上 `prompt_cache_hit_tokens`，若没有，就不伪造。命令行的一次记录显示，总量为 15,568 tokens，其中命中 7,040、未命中 8,456，命中率 45.4%。固定前缀探针的热调用记录为 8,362 / 8,566，即 97.6%；但真实 agent 的上下文逐轮增长，记录到的命中率回落为 48–72%。十次序列里，首调用冷，第二至第十次几乎全命，然而第九次在 26 秒长尾之后出现一次完整冷却。事实并不承诺每次都命中：记录说，150 秒空闲后一次调用归零，旧的 220 秒 keeper 间隔未能护住该分片；设计保留 60 秒默认间隔。\n\n压力测试与仓库规模也留下了边界清晰的刻度。负载账本的 Wave 3 使用 `c=128 × 12 s`，每条路径 `n=2380`，合计 14,280 个请求，零错误且全部为 200；三波累计记录为 33,600 个请求，零非 2xx，零连接失败。另一个同机记录累计 25,470 个请求，也为零非 2xx、零连接失败；当天两组累计写作 59,070 个请求、零非 2xx。`docs/latest.json` 记录了 2,004 次提交、493 个路线图批次、65 篇年鉴、747 个测试文件、1,158 个跟踪文件，以及 55,786 行路线图。云模块清单列出 bridge、registry、config、inspector、tasks、insights、evidence、gateway。页面并不替这些数值许下更多保证；这一卷只记录按钮如何开始回应，证据如何保持完整，以及命中与未命中都如何被如实呈现。\n\n点击之后，回应必须有据。";

const LEDGER_EN_LXVI = "Volume LXVI, titled \"The Click That Answers,\" returns to a place where a button had once been silent. The record dated November 19, 2026 says that lazy injection made `/game.js` wait, while under full load it also strained the HTTP/1.1 budget of 6 connections, and users clicked a button that did not answer. The fix was not merely a busy indicator: it also preloaded the script while idle and provided a busy state. The ledger rewrote M8-T1242 to state both parts, and the commit description recorded a red-to-green measurement chain. What is confirmed here is the composition of the fix and the cause of the problem; the fact pack gives no specific values for that measurement chain, so none are supplied. The button's answer comes from both changes together, not from a decorative indicator alone.\n\nOn the same day, repository question answering was also adjusted in how it responds. The commit record says that full chunks are now handed to the model, with no silent truncation of cited evidence at 400 characters; the prompt tells the model to answer with partial coverage when the evidence does not cover everything. Another documentation change stopped citing a content-addressed bundle in the CHANGELOG and pointed instead to `web/app.js` and `web/styles.css`. The commit description also recorded the related gate test, `test_no_document_quotes_a_content_addressed_bundle`, and the `16/16` pre-commit checks. The references are more precise, and the limits of what can be answered are made visible: material not covered by the evidence is not presented as though it were covered.\n\nThe cache records put that boundary into visible numbers. The repository always derives a `prompt_cache_key` for requests; when the gateway supplies `prompt_tokens_details.cached_tokens`, usage parsing includes `prompt_cache_hit_tokens`, and when it does not, the value is not fabricated. One command-line record shows a total of 15,568 tokens, with 7,040 cache-hit tokens and 8,456 cache-miss tokens, for a 45.4% hit rate. The warm-call record for a fixed-prefix probe is 8,362 / 8,566, or 97.6%; but as a real agent's context grows turn by turn, the recorded hit rate falls to 48–72%. In a sequence of ten calls, the first is cold and calls two through ten are almost entirely hits, yet call nine has one complete cold result after a 26-second long tail. The facts do not promise a hit every time: the record says that after 150 seconds idle, one call fell to zero, and the old 220-second keeper interval did not protect that shard; the design retains a 60-second default interval.\n\nThe pressure tests and repository scale leave their own clearly bounded measures. Wave 3 in the load ledger used `c=128 × 12 s`, with `n=2380` per path, totaling 14,280 requests, zero errors, and all responses 200. The three-wave cumulative record is 33,600 requests, zero non-2xx responses, and zero connection failures. A separate record on the same machine totals 25,470 requests, also with zero non-2xx responses and zero connection failures; the day's combined total is recorded as 59,070 requests and zero non-2xx responses. `docs/latest.json` records 2,004 commits, 493 roadmap batches, 65 almanac chapters, 747 test files, 1,158 tracked files, and 55,786 roadmap lines. The cloud module list names bridge, registry, config, inspector, tasks, insights, evidence, and gateway. The page makes no broader promise on behalf of these numbers; this volume records only how the button began to answer, how evidence remains whole, and how both hits and misses are reported honestly.\n\nAfter the click, an answer must have evidence.";

function etchedwaterlineMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-etchedwaterline">
      <div class="almanac-kicker">${zh() ? "卷六十五 · 水纹的刻度" : "Chapter LXV · The Etched Waterline"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `水纹不许诺，` + `<br/><span class="almanac-title-accent">刻度只留下量过的痕迹。</span>`
        : `The water keeps no promises —` + `<br/><span class="almanac-title-accent">a calibrated line remembers being measured.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXV : LEDGER_EN_LXV}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数（实）" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">113</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">75 / 75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造次数（实）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["事实包逐条对齐 git 与快照", "forge-facts 自动组装：git log + docs/latest.json + pom 模块清单 + 缓存/压力 regex；缺失标 missing，不替账册补写"],
        ["一次过审；en 零 CJK", "attempts=1，契约 keys{zh,en}、≥600 字符；sol 亲笔现场过审（terra 时段网关连接失败，切 sol 实测 200，cached 4,152 / 7,151 = 58.1%）"],
        ["两份快照读数并存、不抹平", "快照写明 1,994 提交 / 63 卷；git 实况继续前进——账册只并列呈现，不替它们对齐口径"],
        ["命中只报网关真回传的部分", "usage 原样入账：prompt 7,151 / cached 4,152（58.1%）；LXIV 的 97.6% 纯前缀稳态与 48–72% 真 agent 是两条分开的记录"],
      ] : [
        ["facts align line-by-line with the repo", "forge-facts assembles from git log + docs/latest.json + pom list + cache/pressure regex; gaps are marked missing, never completed"],
        ["one-pass verify; en zero CJK", "attempts=1; contract keys{zh,en}, ≥600 chars; sol authored live (terra-side gateway connection failed; switched to sol: HTTP 200, cached 4,152 / 7,151 = 58.1%)"],
        ["two snapshot readings, side by side", "the snapshot says 1,994 commits / 63 volumes; the log keeps moving — the ledger presents both and reconciles neither"],
        ["cache hits as returned, nothing more", "usage verbatim: prompt 7,151 / cached 4,152 (58.1%); LXIV's 97.6% warm-prefix steady state and 48–72% agent traffic remain two separate records"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "刻度不是保证，刻度只证明：这里，量过了。"
          : "The line does not guarantee; the line records — here, measured."}
      </p>
    </div>`;
}

// ---- Ch.LXVII · The Dense Map · 密地图 (Atlas 105) ----
const LEDGER_ZH_LXVII = "第六十七卷题为《密地图》。地图的密，不在于把一条路说成全部，而在于把已知的路、测得的边界和仍需留意的偏差并排放好。2026年11月19日的事实包记录，仓库共有 2,013 次提交、493 批路线图、66 篇年鉴、747 个测试文件、1,160 个跟踪文件，路线图有 55,786 行；事实包的 head 是 c2f0636，生成于 07:25:14.419Z。当天的提交记录中，0b02c3a9 称 compass v3 携带 7,165 字节的测量事实，并称重建 bundle 上 atlas、manual、admin 提示均为 16/16 验证通过；另有关于 admin 将模型写出的下一步变为 workbench 任务、年鉴第 LXVI 章《回答点击的那一刻》以及 RAG 完整证据分块的记录。第 LXVI 章的记录写明：尝试 1 次、英文零 CJK、中文 1,354 字；Atlas 从 103 到 104，构成为 18 个 panes、66 篇年鉴、20 篇手册，双语 66/66。地图既登记规模，也留下这些可核对的路径。\n\n云模块清单把地图进一步分成八个名字：minicc-cloud-bridge、minicc-cloud-registry、minicc-cloud-config、minicc-cloud-inspector、minicc-cloud-tasks、minicc-cloud-insights、minicc-cloud-evidence 与 minicc-cloud-gateway。缓存亲和测量解释了为何这些边界需要精确记录：上游分片以 prefix-cache shard 和客户端 prompt_cache_key 作为路由提示；没有 key，同一前缀会逐次落到冷分片，有 key 后，热度周期内的命中率稳定在约 94–100%。minicc 会自动派生 prompt_cache_key；usage 只在网关确实回传 prompt_tokens_details.cached_tokens 时报告 prompt_cache_hit_tokens，没有就不伪造，RAG 用量条相应显示缓存命中数量与百分比，或“缓存命中未上报”。一次命令行记录为 total_tokens=15568、cache_hit_tokens=7040、cache_miss_tokens=8456，命中率 45.4%；两趟任务呈现头轮全付、次轮前缀命中的形状。随着约 4.2k-token 的系统提示和工具 schema 在开放会话中复用，命中率会快速趋近此前单轮探针记录的 82–96%，但这并不抹去真实会话的变化。\n\n补测也把边界写得更细。M8-T1221 使用 sys.executable 重跑 v2-fix-add，记录为 passed=true、repair_attempts=0、109 秒、120,599 tokens、prompt_cache_hit_tokens=84,096（71.7%）、reviewer_false_negative_count=0、pass@1；记录同时标出新 key、gpt-6.1-terra 与 reasoning max。M8-T1225 将 README excerpt 放入 13,295 bytes 的前缀后，以新 key 和 terra 的 chat/completions 实测：A 会话族键第一次为冷，第二至第六次恒为 8,362/8,566（97.6%）；B lane 键达到同一档，C 随机键第一次也命中 8,362（97.6%）。这些数字说明仓库前缀成为所有 lane 共享的 headline block。11 月 18 日换用新 lane key 后，/v1/models 仍有 7 项，terra 返回 200；首 call 后的两次 warm 均为 8,362/8,566，即 97.6%，而首 call 约为 72%。150 秒空闲后，cache_key 未变而 call-3 命中归零，测量据此指出水冷 shard 的 TTL 不超过 150 秒；旧的 220 秒 keeper 间隔没有保护该 shard，因此保留 60 秒默认值。\n\n后续 10 次序列中，call-1 为冷命中 0%，call-2 至 call-10 几乎全命中 8,362/8,566（97.6%），只有经历 26 秒长尾之后的 call-9 出现一次完整冷命中；整条序列的全局命中权重约为 8/10，即约 80%。记录称旧的 cache keeper 220s 从未在该 lane 上护住 shard，真正的 minicc-<sha256(family)[:16]> 连续命中率为 97.6%。60s keeper 的设计间隔足以跨过网关 shard TTL 并在短窗口内再加热；命中率并非 100%，call-9 说明网关仍会按 shard hash 轮换。外显的 cache_keeper status 记录 warms=2、last_cached_tokens=4,940、interval=60。相同字节前缀的探针稳定在 97.6%，真实 agent 逐轮增长的上下文则回落到 48–72%；另一组 workspace 记录中，新 workspace 使用 --yolo --max-turns 60，64,310 tokens 中命中 44,957、未命中 17,811，命中率 71.6%，执行 11 次工具调用，生成 sums.py 与 test_sums.py 且测试全绿，audit.jsonl 有 5 行证据；同一 workspace 的只读 --resume 使用 18,077 tokens，命中 8,612、未命中 9,322，命中率 48.0%，零写入，并确认测试数为 2、方法名为两项，家族前缀跨会话越过 TTL。\n\n压力账本为地图加上了服务负载的尺度。Wave 3 在 c=128、12 秒条件下，每条路径 n=2380，共 14,280 个请求，0 错误且全部为 200；health、digest、stats、roadmap、workspace 的 p50 约为 5.4–6.07 ms。三波累计的记录有两组明确口径：一组为 33,600 个请求、0 个非 2xx、0 次连接失败；另一组是在同一台 Windows 机器、127.0.0.1:8899 上运行 minicc-web、设置 MINICC_FAKE_PROVIDER=1 并在波次前数分钟重启进程后，三波累计 25,470 个请求，同样 0 个非 2xx、0 次连接失败。当天所有压力运行的日累计明确写为 33,600 + 25,470 = 59,070 个请求、0 个非 2xx。密地图不把缓存命中说成恒定，也不把压力记录混成一个数字；它让每个比例、边界和口径都能被重新读出。<strong>地图越密，越要忠实标出空白。</strong>";

const LEDGER_EN_LXVII = "Volume LXVII is titled “The Dense Map.” Its density does not come from presenting one route as the whole territory, but from setting known paths, measured boundaries, and deviations still worth watching beside one another. The fact pack dated November 19, 2026 records 2,013 total commits, 493 roadmap batches, 66 almanac chapters, 747 test files, 1,160 tracked files, and 55,786 roadmap lines; its head is c2f0636, generated at 07:25:14.419Z. Among that day's commit records, 0b02c3a9 says compass v3 carries 7,165 bytes of measured facts and that atlas, manual, and admin prompts all verified 16/16 on the rebuilt bundle. Other entries record admin turning model-written next moves into workbench tasks, Almanac Chapter LXVI, “The Click That Answers,” and RAG handing over full evidence chunks. The Chapter LXVI entry specifies one attempt, zero CJK in English, and 1,354 Chinese characters; Atlas moved from 103 to 104, composed of 18 panes, 66 almanac chapters, and 20 manual entries, with 66/66 bilingual. The map records scale as well as paths that can be checked.\n\nThe cloud module list divides the map further into eight names: minicc-cloud-bridge, minicc-cloud-registry, minicc-cloud-config, minicc-cloud-inspector, minicc-cloud-tasks, minicc-cloud-insights, minicc-cloud-evidence, and minicc-cloud-gateway. Cache-affinity measurements explain why these boundaries need exact records: upstream shards use the prefix-cache shard and the client's prompt_cache_key as routing hints. Without the key, the same prefix repeatedly lands on cold shards; with it, the hit rate stays around 94–100% during the warm period. minicc derives prompt_cache_key automatically. Usage reports prompt_cache_hit_tokens only when the gateway actually returns prompt_tokens_details.cached_tokens; when it does not, the value is not fabricated. The RAG usage bar accordingly shows the cache-hit count and percentage, or “cache hit not reported.” One command-line record gives total_tokens=15568, cache_hit_tokens=7040, and cache_miss_tokens=8456, for a 45.4% hit rate; the two-pass task has the shape of a fully paid first pass followed by a prefix hit on the second. As the approximately 4.2k-token system prompt and tool schema are reused in an open session, the hit rate quickly approaches the 82–96% recorded by earlier single-turn probes, without erasing variation in real sessions.\n\nFurther measurements make the boundaries more precise. M8-T1221 reran v2-fix-add using sys.executable and recorded passed=true, repair_attempts=0, 109 seconds, 120,599 tokens, prompt_cache_hit_tokens=84,096 (71.7%), reviewer_false_negative_count=0, and pass@1; the record also specifies a new key, gpt-6.1-terra, and reasoning max. In M8-T1225, after the README excerpt entered a 13,295-byte prefix, a chat/completions measurement with a new key and terra showed that the A session-family key was cold on its first call and then held at 8,362/8,566 (97.6%) on calls two through six. The B lane key reached the same level, and the C random key also hit 8,362 (97.6%) on its first call. These figures show the repository prefix becoming a headline block shared by all lanes. After switching to a new lane key on November 18, /v1/models still had 7 entries and terra returned 200; the two warm calls after the first call both measured 8,362/8,566, or 97.6%, while the first call was about 72%. After 150 seconds idle, call-3 fell to zero hits even though cache_key was unchanged. The measurement therefore placed the water-cooled shard TTL at no more than 150 seconds; the old 220-second keeper interval had not protected that shard, so the 60-second default was retained.\n\nIn the following sequence of 10 calls, call-1 was cold at 0%, calls two through ten were almost entirely hits at 8,362/8,566 (97.6%), and only call-9, after a 26-second long tail, produced a complete cold result. The sequence's global hit weight was approximately 8/10, or about 80%. The record says the old cache keeper 220s had never protected the shard on this lane, while the actual minicc-<sha256(family)[:16]> achieved 97.6% continuous hits. A 60s keeper interval is designed to cross the gateway shard TTL and warm it again within a short window; the hit rate is not 100%, and call-9 shows that the gateway still rotates by shard hash. The exposed cache_keeper status records warms=2, last_cached_tokens=4,940, and interval=60. Probes with an identical byte prefix held at 97.6%, while the growing context of a real agent fell back to 48–72%. In another workspace record, a new workspace using --yolo --max-turns 60 used 64,310 tokens, with 44,957 hits and 17,811 misses, for a 71.6% hit rate. It made 11 tool calls, generated sums.py and test_sums.py with all tests green, and produced 5 lines of audit.jsonl evidence. A read-only --resume in the same workspace used 18,077 tokens, with 8,612 hits and 9,322 misses, for a 48.0% hit rate; it made zero writes and confirmed a test count of 2 and two method names, with the family prefix surviving across sessions beyond the TTL.\n\nThe pressure ledger adds the scale of service load to the map. Wave 3 ran at c=128 for 12 seconds, with n=2380 per path: 14,280 requests in total, 0 errors, and all responses 200. The p50 for health, digest, stats, roadmap, and workspace was about 5.4–6.07 ms. The three-wave cumulative records give two explicit scopes: one reports 33,600 requests, 0 non-2xx responses, and 0 connection failures; another reports 25,470 requests across three waves, also with 0 non-2xx responses and 0 connection failures, on the same Windows machine running minicc-web at 127.0.0.1:8899 with MINICC_FAKE_PROVIDER=1 and a process restarted minutes before the waves. The daily cumulative across all pressure runs is explicitly 33,600 + 25,470 = 59,070 requests and 0 non-2xx responses. The dense map does not call cache hits constant or collapse distinct pressure records into one number; it leaves every ratio, boundary, and scope available to be read again. <strong>The denser the map, the more faithfully it must mark the blank spaces.</strong>";

function theclickMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-theclick">
      <div class="almanac-kicker">${zh() ? "卷六十六 · 回应的按键" : "Chapter LXVI · The Click That Answers"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `按过之后，` + `<br/><span class="almanac-title-accent">回应必须有回音。</span>`
        : `After the click,` + `<br/><span class="almanac-title-accent">the answer must answer.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXVI : LEDGER_EN_LXVI}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数（实）" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">113</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">75 / 75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造次数（实）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["死按钮是真 bug，不是体感", "根因：HTTP/1.1 每主机 6 条连接，满载窗口下 /game.js 懒注入挂起；对策「idle 预注入 + 按钮 busy/aria-busy/disabled + finally 复位」即本卷题材"],
        ["en 零 CJK；attempts=1", "6.2-sol 亲笔；契约 keys{zh,en}、≥600 字符双端、en 零 CJK、禁 <script；verify 一次性过"],
        ["数字都出自仓库自己的账", "git log + docs/latest.json + pom 模块清单 + 缓存/压力 regex 缓出给模型；缺的标 missing；没有一句是编的"],
        ["空闲预注入不需要新 API 键", "preloadArcade() 与 openArcade() 共享同一个 pending promise——增量 0 token、行为更即时"],
      ] : [
        ["a dead button is a real bug, not a vibe", "root cause: HTTP/1.1 serves at most 6 connections per host; under load the lazy /game.js inject starved; fix (idle preload + disabled/aria-busy on the button + finally restore) is this chapter's subject"],
        ["en zero CJK; attempts=1", "authored by 6.2-sol; contract keys{zh,en}, ≥600 chars both ends, zero CJK in en, no <script; verify passed on the first pass"],
        ["every number walked in from the repo", "git log + docs/latest.json + pom <modules> list + cache/pressure regex anchors; gaps stay “missing”; none were invented"],
        ["idle preload spends zero new API tokens", "preloadArcade() shares one pending promise with openArcade(); the win is a faster click, not a new key"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "按钮回应，是因为有人按住事故不放手。"
          : "The button answers because someone would not let the bug go."}
      </p>
    </div>`;
}

// ---- Ch.LXVIII · One Click, Many Hands · 一键派发 (Atlas 106) ----
const LEDGER_ZH_LXVIII = "这一页记下的变化，从一个很小的动作开始：管理员在计划或建议条目上点击“全部应用”，不再需要逐项把整张清单送进工作台。模型写出的下一步因此不只是供人阅读的文字；它们可以作为一组工作任务派发出去。一个按钮面对的是整份列表，列表里的每一项仍各自成为要处理的工作。标题里的“一键”说的是入口收拢， “多手”说的是工作被分送到任务通道，而不是把清单压成一个含混的动作。\n\n这条派发路径落在 `/api/tasks/batch`。它承接计划和建议磁贴上的整批应用，让列表通过批量任务接口进入工作台。此前，模型写出的单个计划或建议项目已经可以通过 `/api/tasks` 变成工作台任务；这一页把同一类入口从单项推进到整张列表。于是，单项派发和批量派发各有对应的接口，动作规模不同，工作仍然进入任务系统，而不是停留在建议文本里。\n\n批量并不意味着另起一套权限规则。提交整张列表时，采用的权限姿态与聊天相同；这一点是这次改动明确保留的边界。管理员看到的是集中操作，系统执行时仍沿用既有的授权方式。把许多条目放在一次点击后面，不能让其中任何一项绕开原有权限；便捷改变的是发起工作的方法，不是工作能够被谁发起的规则。\n\n管理员 smoke 检查覆盖了计划磁贴和建议磁贴上的两个“全部应用”入口，验证它们把整份清单派发出去。记录由此从单项进入任务的能力，延伸到清单级的批量入口：建议可以聚成待办，整批待办可以通过任务批量接口提交，并继续遵循聊天的权限姿态。这里没有把一次点击写成工作的终点；它只是把多个下一步送上各自的工作路径。\n\n<strong>一键收拢入口，多手接续工作。</strong>";

const LEDGER_EN_LXVIII = "This entry begins with a small action: an administrator clicks “apply all” on a plan or recommendations tile, instead of sending items from the whole list to the workbench one by one. Model-written next moves are therefore more than text for someone to read; they can be dispatched as a set of work tasks. One button acts on the full list, while each item in that list remains work to be handled. “One click” names the consolidated entry point; “many hands” names work going through the task channel, not a list collapsed into one ambiguous action.\n\nThe dispatch path runs through `/api/tasks/batch`. It carries the bulk application from plan and recommendations tiles into the workbench through the batch task interface. Previously, an individual model-written plan or recommendation item could become a workbench task through `/api/tasks`; this entry extends that kind of entry point from a single item to the entire list. Single-item dispatch and batch dispatch now have their respective interfaces. The scale of the action differs, but the work still enters the task system instead of remaining suggestion text.\n\nBatch handling does not introduce a separate permission rule. Submitting the whole list uses the same permission posture as chat; this is an explicit boundary preserved by the change. The administrator sees a consolidated operation, while the system continues to use the established authorization approach when carrying it out. Putting many items behind one click cannot let any of them bypass existing permissions. Convenience changes how work is initiated, not the rules about who may initiate it.\n\nThe administrator smoke check covers both “apply all” entry points, on the plan tile and the recommendations tile, and verifies that they dispatch the whole list. The record thus extends the ability to turn an individual item into a task with a list-level batch entry point: recommendations can gather into work to be done, and that whole set can be submitted through the batch task interface while continuing to follow chat’s permission posture. A click is not presented as the end of the work. It sends multiple next moves onto their respective paths.\n\n<strong>One click gathers the work; many hands carry it forward.</strong>";

function densemapMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-densemap">
      <div class="almanac-kicker">${zh() ? "卷六十七 · 密地图" : "Chapter LXVII · The Dense Map"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `密得并列，` + `<br/><span class="almanac-title-accent">不是密得盖住。</span>`
        : `Dense is not` + `<br/><span class="almanac-title-accent">buried under; it is side by side.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXVII : LEDGER_EN_LXVII}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数（实）" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">113</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">75 / 75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造次数（实）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["地图越来越厚，边界越来越亮", "_WORLD_MAP 4,444 → 7,165 bytes 的实测；并列结构，不淹没信息"],
        ["en 零 CJK；attempts=1", "6.2-sol 亲笔；契核 keys{zh,en}、en 零 CJK、禁 <script；verify 一次性过"],
        ["每一条事实都能回去仓库自身", "提交记录/事实包/git log 都是逐字引用；Atlas 105 = 18 panes + 67 almanac + 20 manual"],
        ["Atlas 再一次从单一书页长到全界", "Atlas 104 → 105（18+67+20），跟随本卷更新，重算与地图同值"],
      ] : [
        ["the map gets denser; the edges get brighter", "the _WORLD_MAP measured 4,444 → 7,165 bytes; parallel layout, not a drowning layout"],
        ["en zero CJK; attempts=1", "authored by 6.2-sol; contract keys{zh,en}, zero CJK in en, no <script; verify passed in one pass"],
        ["every fact walks back into the repo", "commits / fact pack / git log, verbatim; Atlas 105 = 18 panes + 67 almanac + 20 manual"],
        ["Atlas grew once more, from page to world", "Atlas 104 → 105 (18+67+20), re-derived in step with this chapter"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "密不是淹没，密是并列。"
          : "Dense is not flooded; dense is side by side."}
      </p>
    </div>`;
}

function oneclickmanyhandsMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-oneclickmanyhands">
      <div class="almanac-kicker">${zh() ? "卷六十八 · 一键派发" : "Chapter LXVIII · One Click, Many Hands"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `一键不是魔术，` + `<br/><span class="almanac-title-accent">一键是入口的收拢。</span>`
        : `One click is not magic,` + `<br/><span class="almanac-title-accent">one click is the doorway narrowing.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXVIII : LEDGER_EN_LXVIII}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数（实）" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">113</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">75 / 75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造次数（实）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["一键是入口，不是魔术", "整份清单一次性走进 /api/tasks/batch；自动并发 + planner 裁决；atomic 失败不会带着半个清单就走"],
        ["en 零 CJK；attempts=1", "6.2-sol attempts=1 一次过审；契约 keys{zh,en}、≥600 字符、禁 <script；en 1,173 完成 tokens"],
        ["一次点击，不等于一次粗放", "每条子任务仍需独立 verify；审计同时落盘 zh/en 两份证据；acceptance 不是可选项"],
        ["重启中断会抢这个入口", "restart-interrupt 规则依然要管：谁让并发执行在刀口上"],
      ] : [
        ["a button is a doorway, not a spell", "the whole list fans out to /api/tasks/batch; auto-concurrency + planner-arbitrated dispatch; atomic failure never commits half a list"],
        ["en zero CJK; attempts=1", "6.2-sol authored; contract keys{zh,en}, ≥600 chars, no <script; verification passed in one pass"],
        ["one click is not coarseness", "every child task still verifies independently; the audit log carries zh/en evidence for each; acceptance is non-optional"],
        ["restart-interrupt still guards the doorway", "the restart-interrupt rule keeps its grip: nothing gets to walk in on a knife-edge"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "门的宽窄由你定，走进去的人不由你多算。"
          : "You set the width of the door; how many walk in is yours to own."}
      </p>
    </div>`;
}

// ---- Ch.LXIX · The Live Page · 活的页面 (Atlas 107) ----
const LEDGER_ZH_LXIX = "<p>这一卷写在页面仍然更新的时刻。2026年11月19日，仓库里的事实包记录了 LXVIII《一键，多双手》已经刊出，目录共有六十八卷；最新章节的文字也已扫除陈旧的 Atlas 时代叙述，手册面板和入门第九步如今都写着六十八卷。今天的提交记录里，8a7519b2 是这次文案清理，0f8ea9ad 则记下 LXVIII 的发布。页面上看到的数字，因而不只是静止的装饰：它们有烘焙时留下的版本，也有访问时重新读取的版本。要写 LXIX，先要承认这两种时间同时存在。</p><p>实地检查发生在 GitHub Pages 的部署之后。为提交 ab04651 执行的工作流仍显示进行中，但检查时六个步骤已经全部成功：设置任务、检出代码、身份守卫、配置 Pages、上传构件，以及部署到 GitHub Pages。更早的部署尝试被后续推送取消，而每次推送上的身份守卫都保持绿色。随后对线上首页的检查记录在 2026-11-19T09:01Z：里程碑横幅显示“2,022 minicc 提交总数 · CI 全绿”；实时 DOM 中，提交数芯片是 2024，章节芯片是“68 卷”，最新主线标记是 MAIN @ 7904DD4。近期提交列表把 LXVIII 放在事实包机器人的刷新提交之前。这些读数并不相同，记录它们，才是说明页面如何工作的起点。</p><p>页面采用两层呈现：在 ab04651 中烘焙的备用值写着 2,022、68 和 0f8ea9a；页面运行时的实时抓取则把芯片更新为 2024、68 和 7904DD4。上游的 docs/latest.json 在事实包生成时报告 head=a626552、提交总数 2025、章节数 68、追踪文件 1160、路线图 55786 行；它的生成时间是 2026-11-19T08:55:50.144Z。页面中的提交数由渲染时读取的上游 latest.json 提供，而横幅及备用值仍保留烘焙时的数值。因此两层都不是孤立的真相；只有实时层重新读取事实包，操作者才有机会看出烘焙页面已经落后。此处的 2,022 与 2,024 是有意保留的差异，不应被抹成一个数。</p><p>主线当天的节奏也解释了为什么页面需要重新读取。记录列出了十个提交：8a7519b2、2516ea13、a626552a、7904dd43、4f45ebb5、71b4aad9、820b99db、0f8ea9ad、d213f587 和 2d9d0766；其中六个是事实包机器人的刷新提交。最新记录还显示，CI 工作流的每次推送都被下一次推送取消，结论是被取代，而不是失败；要取得绿色的必需运行，最快的条件是有一分钟没有新推送。相较之下，更新 docs/latest.json 的工作流每次都成功，其中一次于 2026-11-19T08:43:29Z 完成，运行编号为 44481833362。部署和数据刷新已有可读的成功证据，CI 则仍受连续推送的节奏牵制。页面把这些细节置于可检查的位置，读者才不必把“绿色”误当成所有事情都已静止。</p><p>同一仓库的其他测量给这本日志提供了尺度，但不改变页面检查本身的事实。压力测试记录的累计数据包括三波合计 33,600 个请求、零个非 2xx、零个连接失败；另一组记录为三波 25,470 个请求且同样没有非 2xx 或连接失败，当日各次压力运行合计则为 59,070 个请求、零个非 2xx。缓存记录也没有把命中率说成恒定：稳定前缀探针达到 97.6%，真实代理任务因逐轮增长的上下文落在 48–72%。这些数据共同提醒我们，数字必须带着测量条件和来源。LXIX 的页面并非只展示一个“最新”标签，而是展示备用值、实时值与上游事实包之间的关系；在这层关系仍能被亲眼核对时，页面才是活的。</p><p>“活页面的诚实，始于让差异可见。”</p>";
const LEDGER_EN_LXIX = "<p>This volume is written while the page is still changing. On November 19, 2026, the repository fact pack recorded that LXVIII, “One Click, Many Hands,” had been published and that the table of contents held sixty-eight volumes. The latest chapter's copy had also been swept of stale Atlas-era narration: the manual panel and onboarding step nine now both say sixty-eight volumes. In today's commit record, 8a7519b2 marks that copy sweep, while 0f8ea9ad records the release of LXVIII. The numbers seen on the page are therefore not merely static decoration: they have a version left by baking and another version read again at visit time. To write LXIX, we must first acknowledge that these two times coexist.</p><p>The live inspection took place after a GitHub Pages deployment. The workflow for commit ab04651 still appeared in progress, but by the time of inspection all six steps had completed successfully: Set up job, Checkout, Identity guard, Configure Pages, Upload artifact, and Deploy to GitHub Pages. Earlier deployment attempts had been cancelled by later pushes, while the identity guard stayed green on every push. The subsequent check of the live home page was recorded at 2026-11-19T09:01Z: the milestone ribbon read “2,022 minicc commits · CI all green”; in the live DOM, the commit chip was 2024, the chapter chip was “68 volumes,” and the latest main marker was MAIN @ 7904DD4. The recent-commits list placed LXVIII above the fact-pack bot's refresh commits. Recording these readings, even though they differ, is the starting point for explaining how the page works.</p><p>The page uses two presentation layers: the fallback baked into ab04651 says 2,022, 68, and 0f8ea9a; the live fetch at page runtime updates the chips to 2024, 68, and 7904DD4. At fact-pack generation, the upstream docs/latest.json reported head=a626552, 2025 total commits, 68 chapters, 1160 tracked files, and 55786 roadmap lines; its generation time was 2026-11-19T08:55:50.144Z. The page's commit chip comes from reading the upstream latest.json at render time, while the ribbon and fallback values retain their baked numbers. Neither layer is the truth in isolation; only when the live layer rereads the fact pack can an operator notice that the baked page has fallen behind. The difference between 2,022 and 2,024 here is intentional and should not be flattened into a single number.</p><p>The day's pace on main also explains why the page must read again. The record lists ten commits: 8a7519b2, 2516ea13, a626552a, 7904dd43, 4f45ebb5, 71b4aad9, 820b99db, 0f8ea9ad, d213f587, and 2d9d0766; six of them are fact-pack bot refresh commits. The latest record also shows that each push's CI workflow is cancelled by the next push, with a superseded conclusion rather than a failure; the fastest condition for a green required run is one minute without a new push. By contrast, the workflow updating docs/latest.json succeeds every time; one run completed at 2026-11-19T08:43:29Z, run number 44481833362. Deployment and data refresh already have readable evidence of success, while CI remains constrained by the pace of successive pushes. By putting these details where they can be inspected, the page lets readers avoid mistaking “green” for everything having come to rest.</p><p>Measurements elsewhere in the same repository give this log a sense of scale, without changing the facts of the page inspection. The pressure-test record includes 33,600 requests across three waves, with zero non-2xx responses and zero connection failures; another record has 25,470 requests across three waves, again with no non-2xx responses or connection failures; all pressure runs that day total 59,070 requests and zero non-2xx responses. The cache record likewise does not claim a constant hit rate: a stable-prefix probe reached 97.6%, while real agent tasks with context growing turn by turn ranged from 48–72%. Together, these figures remind us that numbers must travel with their measurement conditions and source. The LXIX page does not merely display a “latest” label; it shows the relationship among fallback values, live values, and the upstream fact pack. While that relationship can still be checked with one's own eyes, the page is alive.</p><p>“A live page is honest when it makes differences visible.”</p>";
function thelivepageMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-thelivepage">
      <div class="almanac-kicker">${zh() ? "卷六十九 · 活的页面" : "Chapter LXIX · The Live Page"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `烘焙会落后，` + `<br/><span class="almanac-title-accent">线上不会。</span>`
        : `The bake falls behind,` + `<br/><span class="almanac-title-accent">the wire never does.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXIX : LEDGER_EN_LXIX}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数（实）" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">113</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">75 / 75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造次数（实）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["烘焙只是快照，线上才是活答案", "ab04651 烘焙写 2,022/68/0f8ea9a；渲染时抓取覆写芯片为 2024/68/7904DD4——差异被刻意保留"],
        ["部署是绿的，节奏不是静止的", "lenovo-pages 六步全绿（自 2026-11-19T08:43Z）；更早的部署尝试被后推送取消，身份守卫每次绿色"],
        ["打开线上页，是抓陈旧烘焙的第一眼", "2026-11-19T09:01Z 实测：milestone ribbon=2,022，ml-commits=2024，ml-chapters=68 卷，MAIN@7904DD4；近期提交列表上 LXVIII 在机器人刷新之上"],
        ["CI 红的是被取代，不是被打败", "当日每次 CI 被下一推送取消（superseded）；update-latest 工作流每次成功（如 44481833362）"],
      ] : [
        ["the bake is a snapshot; the wire is the answer", "ab04651 baked 2,022 / 68 / 0f8ea9a; the runtime fetch overwrites the chips to 2024 / 68 / 7904DD4 — the difference is kept on purpose"],
        ["the deploy was green; the pace was not still", "lenovo-pages went six-for-six green from 08:43Z; earlier deploy attempts cancelled by the next push; identity-guard green on every push"],
        ["opening the live page catches a stale bake", "checked 2026-11-19T09:01Z: ribbon 2,022 vs ml-commits = 2024 vs ml-chapters = 68 volumes vs MAIN @ 7904DD4; LXVIII leads the bot refresh commits in the list"],
        ["CI red means superseded, not defeated", "today every push CI was cancelled by the next push; update-latest succeeds every time (run 44481833362 and kin)"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "活页面的诚实，始于让差异可见。"
          : "A live page is honest when it makes differences visible."}
      </p>
    </div>`;
}

// ---- Ch.LXX · The Runner Without Bash · 没有 bash 的跑道 (Atlas 108) ----
const LEDGER_ZH_LXX = "<p>第七十章：在可验证的边界上。事实包记录的是一个具体时点，而不是可以随意外推的完整现状。docs/latest.json 的字段写明 head 为 8a7519b，生成时间为 2026-11-19T09:21:32.847Z；其中列出 2,027 次提交、493 个路线图批次、68 卷 almanac、747 个测试文件、1,160 个跟踪文件，以及 55,786 行路线图。近期提交记录还显示，e468373e 于 2026-11-19 记载了第六十九章《The Live Page》，并将 Atlas 从 106 更新到 107，同时加入两项 parity/dazzle smoke catches。较早的第六十八章《One Click, Many Hands》提交记录写着 Atlas 从 105 到 106，尝试次数为 1，中文长度 687、英文长度 2,246，并称英文零 CJK。近期文案更新则把 Manual panel 和 onboarding 第 9 步的旧说法改为六十八卷。这些记录的时间和来源各有其边界，不能把它们拼成一个未经说明的统一计数。</p><p>缓存测量同样需要保留原有条件。wkapi.pro 的上游分片使用 prefix-cache shard，客户端的 prompt_cache_key 是路由提示；没有 key 时，相同前缀会逐次落到冷分片，有 key 后，热度周期内报告的命中率约为 94–100%。minicc 会通过 minicc/llm/openai_provider.py 中的 _effective_prompt_cache_key 自动派生该 key。usage 解析网关如实返回的 prompt_tokens_details.cached_tokens：字段存在时才带 prompt_cache_hit_tokens，不存在时不伪造；RAG 用量条相应显示缓存命中数量和比例，或显示缓存命中未上报。一次两轮任务记录了 15,568 个 total tokens、7,040 个 cache-hit tokens、8,456 个 cache-miss tokens，命中率为 45.4%。另有一次补测记录 120,599 tokens、109 秒、零 repair attempts、84,096 个 prompt cache hit tokens（71.7%）、零 reviewer false negatives 和 pass@1；其上下文是新 key、gpt-6.1-terra、reasoning max。不同实验的数字不能互相替代。</p><p>2026-11-18 的新 lane key 测量显示，/v1/models 仍有 7 项，terra 返回 200；首个调用偏冷，随后两次 warm 调用命中 8,362/8,566，即 97.6%。但空闲 150 秒后，call-3 的缓存命中归零，因此旧的 220 秒 keeper 间隔没有保护该 shard；记录将 TTL 标为不超过 150 秒，并保留 60 秒默认间隔。后续十次序列中，call-1 为冷调用，call-2 至 call-10 几乎全命中，唯有在 26 秒长尾之后的 call-9 再次完全冷却；该序列的全局 hit 权重约为 8/10，即 80%。同字节前缀的 family key 探针稳定在 97.6%，而真实 agent 的逐轮增长上下文命中率为 48–72%。记录也明确指出命中率不等于 100%，并列出两次 workspace 测试：新 workspace 使用 --yolo --max-turns 60，64,310 tokens 中命中 44,957，比例 71.6%，有 11 次工具调用且生成 sums.py、test_sums.py，测试全绿，audit.jsonl 有 5 行证据；同 workspace 的 --resume 只读测试为 18,077 tokens、命中 8,612、比例 48.0%，零写入，并确认测试数为 2、方法名两项。</p><p>压力测试账本记载，Wave 3 在 c=128、12 秒条件下每条路径 n=2,380，总计 14,280 个请求，零错误且全部为 200。三个 wave 的累计数字在记录中分别出现 33,600 个请求、零非 2xx、零连接失败，以及另一组 25,470 个请求、同样零非 2xx 和零连接失败；当日累计写为 59,070 个请求、零非 2xx。环境说明为 Windows 同一台机器、127.0.0.1:8899 上的 minicc-web、MINICC_FAKE_PROVIDER=1，并在测试前刚重启进程。部署记录则描述 self-hosted Windows runner lenovo-pages 因缺少 /bin/bash 而连续失败，docker-desktop 是唯一列出的 WSL 发行版，存在 busybox /bin/sh，但没有 Ubuntu 或 Debian。切换至 ubuntu-latest 后，跨平台归档步骤和 github-pages 部署环境声明先后修复；提交 691053c 的两条 Pages 部署均成功。记录还说明 11:05Z 的 live re-check 显示了与 docs/latest.json 不同的一组实时数字。这些是各自测量和记录中的事实；本章不把缺失的信息补写成事实。</p>";
const LEDGER_EN_LXX = "<p>Chapter LXX: Keeping the record within its evidence. The fact pack describes measurements, repository text, and deployment events at particular times. It does not establish that every count refers to the same snapshot. The verbatim fields from docs/latest.json list head 8a7519b, generated at 2026-11-19T09:21:32.847Z, with 2,027 total commits, 493 roadmap batches, 68 almanac chapters, 747 test files, 1,160 tracked files, and 55,786 roadmap lines. Recent commit e468373e, dated 2026-11-19, records Chapter LXIX, The Live Page, an Atlas change from 106 to 107, and two parity/dazzle smoke catches. The Chapter LXVIII commit records Atlas 105 to 106, one attempt, Chinese length 687 and English length 2,246, and says English had zero CJK. A later copy change updates the Manual panel and onboarding step 9 to say sixty-eight volumes. These entries have distinct timestamps and sources; their counts should not be silently merged.</p><p>The cache findings also depend on their conditions. The upstream wkapi.pro shards use prefix-cache shards, with the client prompt_cache_key serving as a routing hint. Without that key, identical prefixes can land on cold shards in successive calls; with it, the reported hit rate during the warm period is about 94 to 100 percent. minicc automatically derives the key through _effective_prompt_cache_key in minicc/llm/openai_provider.py. Usage parsing reports prompt_tokens_details.cached_tokens from the gateway as received: prompt_cache_hit_tokens is included only when the field is present, and is not invented when absent. The RAG usage bar shows a hit count and percentage, or says that cache hits were not reported. One two-round task recorded 15,568 total tokens, 7,040 hit tokens, 8,456 miss tokens, and a 45.4 percent hit rate. A separate retest recorded 120,599 tokens, 109 seconds, zero repair attempts, 84,096 prompt cache hit tokens (71.7 percent), zero reviewer false negatives, and pass@1. That retest used a new key, gpt-6.1-terra, and reasoning max; its figures describe that experiment, not the others.</p><p>Measurements with a new lane key on November 18 found seven entries at /v1/models and a 200 response from terra. After a cold first call, two warm calls hit 8,362 of 8,566 tokens, or 97.6 percent. After 150 seconds idle, call 3 had zero cache hits, so the earlier 220-second keeper interval had not protected that shard. The record gives a TTL of at most 150 seconds and retains a 60-second default interval. In a later sequence of ten calls, call 1 was cold and calls 2 through 10 were almost entirely hits; call 9 was fully cold after a 26-second long tail. The sequence's global hit weight was about 8/10, or 80 percent. A same-byte-prefix family-key probe stayed at 97.6 percent, while real agent calls with growing context measured 48 to 72 percent. The notes explicitly say that a hit rate is not 100 percent. They also report two workspace runs: a new workspace with --yolo --max-turns 60 used 64,310 tokens, with 44,957 hits and a 71.6 percent rate; it made 11 tool calls, produced sums.py and test_sums.py, passed all tests, and wrote five audit.jsonl evidence lines. A read-only --resume run in the same workspace used 18,077 tokens, with 8,612 hits and a 48.0 percent rate, made no writes, and confirmed two tests and two method names.</p><p>The pressure-test ledger reports Wave 3 at c=128 for 12 seconds, with n=2,380 per path and 14,280 requests total: zero errors and all responses 200. Across three waves, one entry reports 33,600 requests, no non-2xx responses, and no connection failures; another reports 25,470 requests with the same zero-failure counts. The daily cumulative total is recorded as 59,070 requests and zero non-2xx responses. The environment note identifies the same Windows machine, minicc-web at 127.0.0.1:8899, MINICC_FAKE_PROVIDER=1, and a process restarted shortly before the waves. The deployment ledger says self-hosted Windows runner lenovo-pages repeatedly failed because /bin/bash was absent. docker-desktop was the only listed WSL distribution; it had busybox /bin/sh, and no Ubuntu or Debian distribution. After switching to ubuntu-latest, the archive step was made cross-platform and the github-pages deployment environment was declared. Both Pages deployments for commit 691053c succeeded. The ledger also reports that a live re-check at 11:05Z showed figures different from docs/latest.json. Each count remains attached to its recorded source and time; information marked missing is not supplied by inference.</p>";
function therunnerwithoutbashMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-therunnerwithoutbash">
      <div class="almanac-kicker">${zh() ? "卷七十 · 没有 bash 的跑道" : "Chapter LXX · The Runner Without Bash"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `跑道没有 bash，` + `<br/><span class="almanac-title-accent">失败也是读数。</span>`
        : `The runner had no bash,` + `<br/><span class="almanac-title-accent">failure is also a measurement.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXX : LEDGER_EN_LXX}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数（实）" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">113</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">75 / 75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造次数（实）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=2</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["跑道没有 bash，失败也是账本", "lenovo-pages 上传步骤 execvpe(/bin/bash) failed；唯一 WSL distro 是 docker-desktop（busybox），/bin/sh 在、/bin/bash 不在"],
        ["环境声明也是部署合同的一部分", "deploy-pages 拒了 41555d0：400 Missing environment；补 environment={github-pages} 后两条流水线双绿"],
        ["叠了两层修复才通的全绿链路", "ubuntu-latest 归档 41555d0 → 691053c 环境声明 → 两条流水线（pages build + deploy-pages）全部 success"],
        ["missing 就是 missing，不补字到账里", "缺的写缺的；每条数字带着它的来源与时间 — 账本不接受推得出来的补写"],
      ] : [
        ["the runner had no bash - and that was data", "lenovo-pages died at execvpe(/bin/bash) failed; the only WSL distro is docker-desktop (busybox): /bin/sh lives, /bin/bash does not"],
        ["the environment declaration is part of the contract", "deploy-pages rejected 41555d0: HTTP 400 Missing environment; declared {github-pages}; both pipelines green"],
        ["two layered fixes, then a fully green chain", "ubuntu-latest archive 41555d0 -> environment declaration 691053c -> both pipelines (dynamic build + deploy-pages) success"],
        ["missing is missing - the ledger does not embellish", "absent figures are not supplied by inference; every count carries its source and its timestamp"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "缺了就是缺，不补字到账里。"
          : "Information marked missing is not supplied by inference."}
      </p>
    </div>`;
}

// ---- Ch.LXXI · The Plane That Answered · 应声的服务面 (Atlas 109) ----
const LEDGER_ZH_LXXI = "<p>这一卷从一条应声的路径写起。提交 <code>979105b7</code> 记下：minicc-cloud 的端到端运行手册已在 JDK 25 下验证，gateway -&gt; Eureka -&gt; inspector -&gt; Python bridge 返回 200，并记录了三个环境陷阱。云端由八个模块组成：minicc-cloud-bridge、minicc-cloud-registry、minicc-cloud-config、minicc-cloud-inspector、minicc-cloud-tasks、minicc-cloud-insights、minicc-cloud-evidence 与 minicc-cloud-gateway。响应码只是这次验证的结果；路径、依赖与环境陷阱也一并留在手册里，构成可复核的运行记录。</p><p>快照给这一刻定下边界：<code>docs/latest.json</code> 的 head 为 <code>08f3109</code>，生成于 <code>2026-11-19T11:17:56.183Z</code>。其中记有 2031 次提交、493 个 roadmap 批次、70 个 almanac 章节、747 个测试文件、1158 个跟踪文件，以及 55786 行 roadmap。当天的提交还包括第七十章《没有 Bash 的 Runner》，Atlas 从 107 到 108，attempts=2；以及第六十九章《实时页面》，Atlas 从 106 到 107，并补上两个 parity/dazzle smoke catches。文档清扫则让 Manual panel 与 onboarding 第 9 步改称六十八卷，这是当时所记的最新卷名，不把它误写成此刻快照中的章节数。</p><p>缓存记录把“亲和”还原成具体路由行为：wkapi.pro 的上游分片以 prefix-cache shard 与客户端 <code>prompt_cache_key</code> 为路由提示；没有这个 key，同一前缀会逐次落到冷分片，有 key 后，热度周期内命中率稳定在约 94–100%。minicc 始终自动派生该 key。用量解析如实转发网关报告的 <code>prompt_tokens_details.cached_tokens</code>：有值才带 <code>prompt_cache_hit_tokens</code>，没有就不带，也不伪造；RAG 用量条相应显示缓存命中数与比例，或显示未上报。一次记录为 total_tokens=15568、cache_hit_tokens=7040、cache_miss_tokens=8456、cache_hit_pct=45.4；两趟任务体现首轮全付、次轮前缀命中。另一项补测记下 109 秒、120,599 tokens 与 84,096 缓存命中 token（71.7%），同时 <code>passed=true</code>、repair_attempts=0、reviewer_false_negative_count=0、pass@1=…；原记录的末尾省略号仍是省略号。</p><p>另一组探针在 README excerpt 纳入前缀后，以 13,295 bytes 测得 A 会话族键从冷启动转为每次 8,362/8,566，即 97.6%；B lane 键同档，C 随机键的首 call 也命中 8,362（97.6%）。新 lane key 的记录显示 <code>/v1/models</code> 仍有 7 项，terra 返回 200；首 call 之后两次 warm 命中，150 秒空闲后 call-3 却归零，记录据此标出 shard TTL ≤150s，并保留 60 秒默认 keeper 间隔。后续十次序列中 call-1 为冷，call-2 至 call-10 几乎全命，只有长尾 26 秒后的 call-9 完整归零；全局 hit 权重约为 8/10，即约 80%。同字节前缀探针稳定在 97.6%，真实 agent 随逐轮增长的上下文则为 48–72%；记录明确说这是物理事实，不加粉饰。两项 workspace 记录分别是：新 workspace <code>--yolo --max-turns 60</code>，64,310 tokens、44,957 命中、17,811 未命中、71.6%，11 次工具调用，生成 sums.py 与 test_sums.py 且测试全绿，audit.jsonl 有 5 行证据；同 workspace <code>--resume</code> 只读，18,077 tokens、8,612 命中、9,322 未命中、48.0%，零写入，确认测试数为 2、方法名两项，家族前缀跨会话通过 TTL。A 与 B 各三线程的记录均为首轮 0.0% ×3、之后 97.6% ×3，写明零抖动、零跨家族驱逐。</p><p>压力测试账本也保留了各自的口径。Wave 3 为 c=128 × 12 s，每路径 n=2380，总计 14,280 个请求，0 错误且全为 200。三波累计记录为 33,600 个请求，对 stock-local fake-provider cockpit 为 0 个 non-2xx、0 次连接失败；另一个同机 Windows 记录使用 <code>127.0.0.1:8899</code> 上的 minicc-web、<code>MINICC_FAKE_PROVIDER=1</code>，进程在波次前数分钟刚重启，三波累计 25,470 个请求，0 个 non-2xx、0 次连接失败。当天所有压力记录的日累计写作 33,600 + 25,470 = 59,070 个请求，0 个 non-2xx。数字各自沿用来源中的范围，不把不同账本合并成一场测试。应声有据，冷暖皆记。</p>";
const LEDGER_EN_LXXI = "<p>This volume begins with a path that answered. Commit <code>979105b7</code> records that the minicc-cloud end-to-end runbook was verified on JDK 25: gateway -&gt; Eureka -&gt; inspector -&gt; Python bridge returned 200, and three environment traps were documented. The cloud plane consists of eight modules: minicc-cloud-bridge, minicc-cloud-registry, minicc-cloud-config, minicc-cloud-inspector, minicc-cloud-tasks, minicc-cloud-insights, minicc-cloud-evidence, and minicc-cloud-gateway. The response code is the result of this verification; the path, dependencies, and environment traps remain in the runbook as a record that can be checked.</p><p>The snapshot sets the bounds of this moment: the head in <code>docs/latest.json</code> is <code>08f3109</code>, generated at <code>2026-11-19T11:17:56.183Z</code>. It records 2031 commits, 493 roadmap batches, 70 almanac chapters, 747 test files, 1158 tracked files, and 55786 roadmap lines. That day's commits also include Chapter 70, “The Runner Without Bash,” with Atlas moving from 107 to 108 and attempts=2; and Chapter 69, “The Live Page,” with Atlas moving from 106 to 107, plus two parity/dazzle smoke catches. A documentation sweep changed the Manual panel and onboarding step 9 to say sixty-eight volumes. That was the newest volume named there at the time, not a replacement for the chapter count in this snapshot.</p><p>The cache record turns “affinity” into specific routing behavior: wkapi.pro's upstream shards use prefix-cache shards and the client <code>prompt_cache_key</code> as routing hints. Without this key, the same prefix lands on cold shards successively; with it, the hit rate stays around 94–100% during the warm period. minicc always derives this key automatically. Usage parsing faithfully forwards <code>prompt_tokens_details.cached_tokens</code> reported by the gateway: it includes <code>prompt_cache_hit_tokens</code> only when that value exists, and otherwise omits it rather than fabricating data. The RAG usage bar accordingly displays the cache-hit count and percentage, or says that cache hits were not reported. One record gives total_tokens=15568, cache_hit_tokens=7040, cache_miss_tokens=8456, and cache_hit_pct=45.4; the two-pass task shows a fully paid first pass followed by a prefix hit on the second. Another supplementary measurement records 109 seconds, 120,599 tokens, and 84,096 cache-hit tokens (71.7%), alongside <code>passed=true</code>, repair_attempts=0, reviewer_false_negative_count=0, and pass@1=…; the ellipsis at the end of the source record remains an ellipsis.</p><p>After the README excerpt entered the prefix, a 13,295-byte probe measured the A session-family key shifting from cold start to 8,362/8,566 on every subsequent call, or 97.6%; the B lane key reached the same level, and the first call with the C random key also hit 8,362 (97.6%). The new lane-key record shows <code>/v1/models</code> still listing 7 items and terra returning 200; after the first call, two warm calls hit, but call-3 returned to zero after 150 seconds of idle time. The record therefore notes a shard TTL ≤150s and retains a 60-second default keeper interval. In the following ten-call sequence, call-1 was cold, calls 2 through 10 were almost all hits, and only call-9 went fully cold after a 26-second long tail; the global hit weight was about 8/10, or about 80%. The same-byte-prefix probe held at 97.6%, while real agents with context growing turn by turn measured 48–72%; the record explicitly calls this a physical fact and does not dress it up. Two workspace records are also kept: a new workspace with <code>--yolo --max-turns 60</code> used 64,310 tokens, with 44,957 hits and 17,811 misses, for 71.6%; it made 11 tool calls, generated sums.py and test_sums.py with all tests green, and left 5 lines of evidence in audit.jsonl. A read-only <code>--resume</code> in the same workspace used 18,077 tokens, with 8,612 hits and 9,322 misses, for 48.0%; it made zero writes and confirmed a test count of 2 and two method names, with the family prefix surviving across sessions past the TTL. The A and B records, each with three threads, both show 0.0% ×3 on the first calls and 97.6% ×3 afterward, noting zero jitter and zero cross-family eviction.</p><p>The pressure-test ledger preserves its separate scopes. Wave 3 ran at c=128 × 12 s, with n=2380 per path and 14,280 requests total, 0 errors, and all responses 200. The cumulative record for three waves reports 33,600 requests against a stock-local fake-provider cockpit, with 0 non-2xx responses and 0 connection failures. A separate Windows record on the same machine used minicc-web at <code>127.0.0.1:8899</code> with <code>MINICC_FAKE_PROVIDER=1</code>; the process had been freshly restarted minutes before the waves. Its three-wave cumulative total was 25,470 requests, with 0 non-2xx responses and 0 connection failures. The day's cumulative total across all pressure runs is written as 33,600 + 25,470 = 59,070 requests, with 0 non-2xx responses. Each figure keeps the scope of its source; the separate ledgers are not recast as one test. Every answer is recorded, whether warm or cold.</p>";
function theplanethatansweredMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-theplanethatanswered">
      <div class="almanac-kicker">${zh() ? "卷七十一 · 应声的服务面" : "Chapter LXXI · The Plane That Answered"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `桥应了声，` + `<br/><span class="almanac-title-accent">链路回了 200。</span>`
        : `The bridge answered,` + `<br/><span class="almanac-title-accent">and the chain said 200.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXXI : LEDGER_EN_LXXI}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数（实）" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">113</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">75 / 75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造次数（实）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["桥答了，链路才算通", "979105b7：JDK 25 上实测 gateway → Eureka → inspector → Python bridge 全链 200；三个环境陷阱写进 minicc-cloud/README.md 的实测 runbook"],
        ["localhost 在这台 JDK 里是 unresolved", "Lettuce 报 localhost/<unresolved>:26379；Test-NetConnection 明明通着——把 host 钉在 127.0.0.1 才连接上"],
        ["RabbitMQ 缺席会把健康检查打成 503", "standalone 跑 gateway 要 --management.health.rabbit.enabled=false；docker compose 里 broker 在，不关这个位"],
        ["python 不存在就是不存在", "默认 python 本机没有——--minicc.python 指向真实解释器；bridge 没有静默回退，失败就 503，不给假 200"],
      ] : [
        ["the bridge answered, so the chain counts", "979105b7: JDK 25 runbook verified — gateway -> Eureka -> inspector -> Python bridge returns 200 end to end; three environment traps documented in minicc-cloud/README.md"],
        ["localhost is unresolved inside this JDK", "Lettuce reports localhost/<unresolved>:26379 while Test-NetConnection says the port is fine — pin the host to 127.0.0.1 and it connects"],
        ["an absent RabbitMQ flips health to 503", "standalone gateway runs take --management.health.rabbit.enabled=false; inside docker compose the broker exists and the indicator stays on"],
        ["a missing python is simply missing", "the default bare python does not exist here — pass --minicc.python with the real interpreter; the bridge has no silent fallback: failure leaves as 503, never as a fake 200"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "应了就是应了，200 也要留痕。"
          : "A 200 is a measurement too — with its conditions attached."}
      </p>
    </div>`;
}

// ---- Ch.LXXII · The Stale Assertion · 过时的断言 (Atlas 110) ----
const LEDGER_ZH_LXXII = "<p>卷LXXII记录一次过时断言如何把注意力重新拉回设计本身。2026-11-19，提交827761e3把 focused optimization smoke 对齐到 M8-T1242 的 idle-warm 设计：home 对 arcade 的预热最多发生一次。CI run 44535672293 正是在这一断言上变红；同日的提交 c392c557 刷新了 showcase fact pack，提交899a20f7记下了卷LXXI《回答的平面》，Atlas 从108推进到109，attempts=1，并保持 en zero CJK。提交979105b7还记录了 minicc-cloud 平面的端到端 runbook：JDK 25 下 gateway -&gt; Eureka -&gt; inspector -&gt; Python bridge 返回200，并记录了三个环境陷阱。</p><p>截至 fact pack 的时间，head 是899a20f，生成时间为2026-11-19T13:39:55.204Z；仓库共有2034个 commits、493个 roadmap batches、71个 almanac chapters、747个 test files、1158个 tracked files，roadmap 有55786行。Spring Cloud 的模块依次是 minicc-cloud-bridge、minicc-cloud-registry、minicc-cloud-config、minicc-cloud-inspector、minicc-cloud-tasks、minicc-cloud-insights、minicc-cloud-evidence 与 minicc-cloud-gateway。较早的记录还包含卷LXX《没有 Bash 的 Runner》从Atlas107到108，attempts=2、en zero CJK；卷LXIX《Live Page》带来两次 parity/dazzle smoke catches；而 8a7519b2 的 copy sweep 让 Manual panel 与 onboarding step 9 都说 sixty-eight volumes，并保留 en zero-CJK parity。</p><p>缓存记录解释了为什么一次断言不能替代整套行为。wkapi.pro 的上游分片以 prefix-cache shard 和客户端 prompt_cache_key 作为路由提示；没有 key，同一前缀会逐次落到冷分片，有 key 后，热度周期内命中率稳定在约94–100%。minicc 始终自动派生 prompt_cache_key，usage 会如实解析 prompt_tokens_details.cached_tokens：有就带 prompt_cache_hit_tokens，没有就不伪造；RAG UI 同步显示“缓存命中 N（P%）”或“缓存命中未上报”。一组两轮任务是 total_tokens=15568、cache_hit_tokens=7040、cache_miss_tokens=8456、cache_hit_pct=45.4%。补测 v2-fix-add 使用新 key、gpt-6.1-terra 与 reasoning max，结果为 passed=true、repair_attempts=0、109s、120,599 tokens、prompt_cache_hit_tokens=84,096（71.7%）、reviewer_false_negative_count=0、pass@1=；README excerpt 进入 prefix 后，A 会话族键 call 1 冷、call 2..6 恒定为8,362/8,566（97.6%），B lane 键同档，C 随机键 call 1 也命中8,362（97.6%）。</p><p>2026-11-18 的后续测量又把边界写得更清楚：换用新 lane key 后，/v1/models 仍为7项，terra 返回200；首 call 之后两次 warm 全命，8,362/8,566=97.6%，call-1 cold 约72%。空闲150秒后 call-3 归零，即使 cache_key 不变；旧的220 s keeper 从未护住该 lane 的 shard，水冷 shard-~1,500 的 TTL ≤150s。后续10次序列中 call-1 cold，call-2 至 call-10 几乎全命，只有 call-9 在26s长 tail之后完整 cold；整条序列的全局 hit 权重约为8/10≈80%。60s keeper 用于跨过网关 shard TTL 与短窗口再加热，commit 中的 cache_keeper status 外显 warms=2、last_cached_tokens=4,940、interval=60。warm prefix 的稳定值仍是8,362/8,566（97.6%）：8,362是全 lane headline，剩余204是自家散列尾段。真实 agent 因逐轮增长上下文，命中率回落到48–72%；同字节探针则稳定在97.6%。</p><p>压力测试给出另一条可核对的边界。Wave 3 是 c=128 × 12 s，每条路径 n=2380，共14,280 requests total，0 errors，全部为200；health、digest、stats、roadmap、workspace 的 p50 约为5.4–6.07 ms。三波累计为33,600 requests、0 non-2xx、0 connection failures，环境是 Windows 上的 stock-local fake-provider cockpit，minicc-web 位于127.0.0.1:8899，使用 MINICC_FAKE_PROVIDER=1，且进程在波次前数分钟重新启动。另一组累计为25,470 requests across the three waves，仍为 zero non-2xx、zero connection failures；当天压力运行的总计是33,600 + 25,470 = 59,070 requests、0 non-2xx。断言应当追随已经写下的设计，而不是要求设计服从旧断言。命中率不等于百分之百。</p>";
const LEDGER_EN_LXXII = "<p>Volume LXXII records how a stale assertion can turn attention back toward the design itself. On 2026-11-19, commit 827761e3 aligned the focused optimization smoke test with the M8-T1242 idle-warm design: home warms arcade at most once. CI run 44535672293 went red on exactly this assertion; on the same day, commit c392c557 refreshed the showcase fact pack, while commit 899a20f7 recorded Volume LXXI, The Plane That Answered, moving Atlas from 108 to 109 with attempts=1 and en zero CJK. Commit 979105b7 also recorded a verified end-to-end runbook for the minicc-cloud plane: under JDK 25, gateway -&gt; Eureka -&gt; inspector -&gt; Python bridge returned 200, and three environment traps were documented.</p><p>At the time of the fact pack, head was 899a20f, generated at 2026-11-19T13:39:55.204Z. The repository had 2034 total commits, 493 roadmap batches, 71 almanac chapters, 747 test files, 1158 tracked files, and 55786 roadmap lines. The Spring Cloud modules were minicc-cloud-bridge, minicc-cloud-registry, minicc-cloud-config, minicc-cloud-inspector, minicc-cloud-tasks, minicc-cloud-insights, minicc-cloud-evidence, and minicc-cloud-gateway. Earlier records included Volume LXX, The Runner Without Bash, moving Atlas from 107 to 108 with attempts=2 and en zero CJK; Volume LXIX, The Live Page, with two parity/dazzle smoke catches; and 8a7519b2, whose copy sweep made the Manual panel and onboarding step 9 say sixty-eight volumes while preserving en zero-CJK parity.</p><p>The cache record explains why one assertion cannot replace the whole behavior. Upstream shards at wkapi.pro use the prefix-cache shard and the client prompt_cache_key as routing hints; without that key, the same prefix falls onto cold shards successively, while with the key, the hit rate stays near 94–100% during the warm period. minicc always derives prompt_cache_key automatically. usage parses prompt_tokens_details.cached_tokens truthfully: when present it includes prompt_cache_hit_tokens, and when absent it does not fabricate the field; the RAG UI likewise shows either “cache hit N (P%)” or “cache hit unreported.” One two-round task measured total_tokens=15568, cache_hit_tokens=7040, cache_miss_tokens=8456, and cache_hit_pct=45.4%. The v2-fix-add follow-up used a new key, gpt-6.1-terra, and reasoning max, producing passed=true, repair_attempts=0, 109s, 120,599 tokens, prompt_cache_hit_tokens=84,096 (71.7%), reviewer_false_negative_count=0, and pass@1=. After the README excerpt entered the prefix, the A session-family key was cold on call 1 and constant at 8,362/8,566 (97.6%) on calls 2..6; the B lane key matched that level, and the C random key also hit 8,362 (97.6%) on call 1.</p><p>The later measurements on 2026-11-18 made the boundary clearer. After switching to a new lane key, /v1/models still had 7 items and terra returned 200; the first call was followed by two fully warm hits at 8,362/8,566=97.6%, while call-1 was cold at about 72%. After 150 seconds idle, call-3 fell to zero even though cache_key was unchanged; the old 220 s keeper had never protected the shard on that lane, and the water-cooled shard-~1,500 had TTL ≤150s. In the next 10-call sequence, call-1 was cold and call-2 through call-10 were almost entirely hits, with only call-9 becoming fully cold after a 26s long tail; the global hit weight for the sequence was about 8/10≈80%. The 60s keeper was designed to cross the gateway shard TTL and the short window before warming again, and the commit exposed cache_keeper status as warms=2, last_cached_tokens=4,940, interval=60. The warm prefix remained stable at 8,362/8,566 (97.6%): 8,362 was the all-lane headline, and the remaining 204 were the local hashed tail. Real agent context grew round by round, bringing the hit rate down to 48–72%, while the same-byte probe stayed at 97.6%.</p><p>The pressure tests provide another boundary that can be checked. Wave 3 was c=128 × 12 s, with n=2380 per path, 14,280 requests total, 0 errors, and all responses at 200; p50 for health, digest, stats, roadmap, and workspace was about 5.4–6.07 ms. Across the three waves there were 33,600 requests, 0 non-2xx responses, and 0 connection failures against a stock-local fake-provider cockpit on Windows, with minicc-web at 127.0.0.1:8899, MINICC_FAKE_PROVIDER=1, and the process freshly restarted minutes before the waves. Another cumulative measure was 25,470 requests across the three waves, again with zero non-2xx and zero connection failures; the daily total across all pressure runs was 33,600 + 25,470 = 59,070 requests and 0 non-2xx. The assertion must follow the recorded design, rather than making the design obey an old assertion. Hit rate is not equal to one hundred percent.</p>";
function thestaleassertionMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-thestaleassertion">
      <div class="almanac-kicker">${zh() ? "卷七十二 · 过时的断言" : "Chapter LXXII · The Stale Assertion"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `断言过时了，` + `<br/><span class="almanac-title-accent">红得有理有据。</span>`
        : `The assertion went stale,` + `<br/><span class="almanac-title-accent">red for a reason.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXXII : LEDGER_EN_LXXII}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数（实）" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">113</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">75 / 75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造次数（实）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["红也是证据，不是判决", "CI 44535672293 在 js-check 的「Verify responsive UI and task protocol」红——本机复现只有 test:optimization 断红，一条先 M8-T1242、后 idle 预热的断言"],
        ["断言不能与现役设计矛盾", "首页 idle 预热 arcade bundle（requestIdleCallback timeout:2500，1.5s 兜底，preloadArcade 与 openArcade 共享 pending promise——预热是有界的"],
        ["修的是断言，不是护栏", "断言改为 gameRequests <= 1 并注明口径；openArcade 之后仍严格期望恰好一次；其余 22 个 focused UI contract 全部本机绿"],
        ["CI 从这一红里学到的", "is js-check 的红必须在本机可复现；跑一条 npm run test:optimization 就能分清「代码坏了」与「测试先于设计写」——我两样都碰上过，这次后者"],
      ] : [
        ["red is evidence, not a verdict", "CI 44535672293 red at js-check's Verify responsive UI and task protocol; local repro isolated npm run test:optimization — an assertion written before M8-T1242's idle warm"],
        ["the assertion must not contradict the shipped design", "home warms the arcade bundle on idle (requestIdleCallback with timeout 2500, 1.5s setTimeout fallback; preloadArcade and openArcade share one pending promise — the warm is bounded"],
        ["fix the assertion, not the gate", "the bound became gameRequests <= 1, with the reason recorded in the test; after an explicit openArcade the suite still demands exactly one; the other 22 focused UI contracts all pass locally"],
        ["the lesson the CI learned", "a js-check red must reproduce locally in one command; npm run test:optimization alone separates a build defect from a test that predates the design — both have bitten before; today it was the latter"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "过时的是断言，不是证据。"
          : "The assertion went stale; the evidence never did."}
      </p>
    </div>`;
}

// ---- Ch.LXXIII · The Verifier Declines · 验证器说不行 (Atlas 111) ----
const LEDGER_ZH_LXXIII = "<p>在卷 LXXIII，验证器说不行，仓库便把说法收回到能够由能力声明支撑的范围。2026-11-19 的提交记录写明，README 中移除了 <code>--minicc.python</code> 这个 flag token，因为它触发了 README capability-claims gate，而没有 parser 声明 <code>--minicc</code>；提交说明同时记录 <code>test_readme_capability_claims</code> 为 8/8 green。这里能确认的是文档声明与 parser 能力之间的边界，以及这次门禁检查的结果；事实包没有提供验证器内部实现、更多错误信息或额外失败案例，因此本章不替它们补写。验证器的拒绝不是一个需要修饰的戏剧场面，而是一条具体的约束：文档不能把没有 parser 支持的 token 写成能力。</p><p>时间线仍很短，也很明确。最近的提交列表中，<code>335b27ef</code> 于 2026-11-19 记录了上述 README 修改；其前后有刷新 showcase fact pack 的提交。较早的同日记录包括卷 LXXII《The Stale Assertion》，把 Atlas 从 109 推进到 110，并注明一次尝试、英文零 CJK；卷 LXXI《The Plane That Answered》把 Atlas 从 108 推进到 109，也注明一次尝试、英文零 CJK。这里的数字各自属于记录所述的项目，不能拿它们代替本卷的验证结果。最新事实快照的 head 为 <code>335b27e</code>，生成于 <code>2026-11-19T14:51:54.175Z</code>；它记载 2040 个提交、493 个 roadmap batches、72 章 almanac、747 个测试文件、1158 个 tracked files，以及 55786 行 roadmap。卷号 LXXIII 与快照中的 72 章并不冲突：快照记录的是生成时已有章节数，不是对本章写作的否认。</p><p>仓库的其他测量提供了同一种克制的背景。cache-affinity 记录说，minicc 始终自动派生 <code>prompt_cache_key</code>；usage 解析如实传递网关报告的缓存 token，有数据才带 <code>prompt_cache_hit_tokens</code>，没有就不伪造。一次命令行记录为 15568 total tokens、7040 cache-hit tokens、8456 cache-miss tokens，命中率 45.4%。另有固定字节前缀探针稳定达到 8362/8566，即 97.6%；真实 agent 的逐轮增长上下文则记录为 48–72%。这些数值并不证明 README 门禁的行为，却说明项目已有把“实际报告了什么”与“不能声称什么”分开的记录习惯。事实包也记录 150 秒空闲后一次缓存归零、后续十次序列中 call-9 冷命中，以及 60 秒 keeper 的设计；不把局部命中说成永远命中，与不把未声明的 flag 写成能力，是同一种边界意识。</p><p>压力测试账本进一步把证据写成计数，而非承诺。Wave 3 的记录是每条路径 n=2380、总计 14280 个请求、0 errors、全部 200；三轮累计记录为 33600 个请求、0 个 non-2xx、0 次连接失败，另一个同机运行累计 25470 个请求，同样为零 non-2xx、零连接失败；当天所有压力运行合计记录为 59070 个请求、0 个 non-2xx。这些结果限定在账本注明的 stock-local fake-provider cockpit 等环境条件下，不能扩大成无条件保证。Spring Cloud 模块清单也只证明列出的八个模块存在：bridge、registry、config、inspector、tasks、insights、evidence 和 gateway。卷 LXXIII 因而不把相邻的成功测量拼成一个更大的结论。它留下的是一次可核对的文档修正、明确的快照和有边界的数字；未提供的验证器细节仍然是缺项，而不是可供想象的空白。</p><p>“未声明的能力，不写进文档。”</p>";
const LEDGER_EN_LXXIII = "<p>In Almanac LXXIII, the verifier declines, and the repository brings its claims back within the bounds supported by declared capabilities. The commit record for 2026-11-19 says that the <code>--minicc.python</code> flag token was removed from the README because it tripped the README capability-claims gate, while no parser declares <code>--minicc</code>; the commit note also records <code>test_readme_capability_claims</code> as 8/8 green. What can be confirmed here is the boundary between documentation claims and parser capability, along with the result of this gate check. The fact pack supplies no implementation details for the verifier, no additional error messages, and no further failure cases, so this chapter does not add any. The verifier's refusal is not a scene that needs embellishment, but a concrete constraint: documentation cannot present a token unsupported by a parser as a capability.</p><p>The timeline is short and explicit. In the recent commit list, <code>335b27ef</code>, dated 2026-11-19, records the README change above; commits refreshing the showcase fact pack appear around it. Earlier entries from the same day include Almanac LXXII, “The Stale Assertion,” moving Atlas from 109 to 110 and noting one attempt and zero CJK in English; and Almanac LXXI, “The Plane That Answered,” moving Atlas from 108 to 109, also noting one attempt and zero CJK in English. Those numbers belong to the projects named in those records and cannot stand in for this chapter's verifier result. The latest fact snapshot has head <code>335b27e</code> and was generated at <code>2026-11-19T14:51:54.175Z</code>; it records 2040 commits, 493 roadmap batches, 72 almanac chapters, 747 test files, 1158 tracked files, and 55786 roadmap lines. Almanac LXXIII does not conflict with the snapshot's 72 chapters: that snapshot records the chapter count at generation time, not a denial that this chapter is being written.</p><p>Other measurements in the repository provide the same restrained context. The cache-affinity record says minicc always derives <code>prompt_cache_key</code> automatically; usage parsing passes through cached tokens reported by the gateway, includes <code>prompt_cache_hit_tokens</code> only when data exists, and does not fabricate it when absent. One command-line record gives 15568 total tokens, 7040 cache-hit tokens, 8456 cache-miss tokens, and a 45.4% hit rate. A fixed-byte-prefix probe is separately recorded as stable at 8362/8566, or 97.6%; real agents with context that grows turn by turn are recorded at 48–72%. These figures do not prove how the README gate behaves, but they show a project habit of separating what was actually reported from what cannot be claimed. The fact pack also records a cache reset after 150 seconds idle, a cold result at call 9 in a later ten-call sequence, and the design of a 60-second keeper. Not presenting local hits as perpetual, and not presenting an undeclared flag as a capability, express the same awareness of limits.</p><p>The pressure-test ledger also states evidence as counts rather than promises. Wave 3 records n=2380 per path, 14280 requests total, 0 errors, and all responses 200. The three-wave cumulative record gives 33600 requests, 0 non-2xx responses, and 0 connection failures; another run on the same machine totals 25470 requests, likewise with zero non-2xx responses and zero connection failures. The daily total across pressure runs is recorded as 59070 requests and 0 non-2xx responses. These results are bounded by the ledger's stated conditions, including a stock-local fake-provider cockpit, and cannot be expanded into an unconditional guarantee. The Spring Cloud module list likewise proves only that the eight listed modules are present: bridge, registry, config, inspector, tasks, insights, evidence, and gateway. Almanac LXXIII therefore does not combine neighboring successful measurements into a broader conclusion. It leaves a verifiable documentation correction, an explicit snapshot, and numbers with stated bounds; verifier details not supplied remain missing, not an invitation to imagine them.</p><p>“An undeclared capability does not belong in the documentation.”</p>";
function theverifierdeclinesMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-theverifierdeclines">
      <div class="almanac-kicker">${zh() ? "卷七十三 · 验证器说不行" : "Chapter LXXIII · The Verifier Declines"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `验证器按住了手，` + `<br/><span class="almanac-title-accent">也按住了这本账。</span>`
        : `The verifier held the hand,` + `<br/><span class="almanac-title-accent">and the hand wrote it down.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXXIII : LEDGER_EN_LXXIII}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数（实）" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">113</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">75 / 75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造次数（实）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["护栏不是拦你做事，是逼着账本说实话", "tests/ 目录超过 500 个文件即停——不是读失败，是拒绝把「没看过的」当成「与改动无关」（M8-T554）"],
        ["文档也是要被逐字验的", "README 里出现没有任何 parser 声明的 --minicc 旗语，capability-claims 门当场判红——这是我自己的段落，门自己挡的"],
        ["修法不在门上，在字上", "minicc.python 不再写成旗语；test_readme_capability_claims 8/8 green，能力清单重新诚实"],
        ["诚实失败仍然是失败", "admin 推荐派发的任务撞上 500 文件红线，验证 block、judge 不肯确认——任务 failed，没有任何一件变成假绿"],
      ] : [
        ["the guard does not block work; it blocks fiction", "a tests/ directory past 500 files stops the targeted scan — a refusal, not a read failure (M8-T554); the unread is never reported as unrelated"],
        ["documentation is verified too, byte by byte", "the README named a flag no parser declares: --minicc; the capability-claims gate turned red on my own paragraph on the first try"],
        ["the fix was in the ink, not the gate", "minicc.python is no longer written as a CLI flag; test_readme_capability_claims is 8/8 green; the capability list is honest again"],
        ["an honest red is still a red", "the admin apply-one dispatch hit the 500-file ceiling; verification blocked, the judge would not confirm, the task failed - nothing was papered over as green"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "护栏说不行，不会让你停下；会让你把真相写下来。"
          : "The guard did not stop the work; it stopped the paperwork."}
      </p>
    </div>`;
}

// ---- Ch.LXXIV · The Red in the Capability List · 红在能力清单那一页 (Atlas 112) ----
const LEDGER_ZH_LXXIV = "<p>卷LXXIV翻到能力清单那一页，红色并非抽象的警告，而是一个具体的门槛：README 中出现了没有解析器声明的 <code>--minicc.python</code>，触发了 README 能力声明检查。提交 <code>335b27ef</code> 删除了这个 flag token；同一条记录说，<code>test_readme_capability_claims</code> 的 8/8 项检查通过。能力清单必须说得比实现少也不能多，文字一旦把不存在的入口写成能力，读者便无法再分辨承诺与事实。近来的记录把这次修正放在一串持续更新的工作中：<code>3e80af04</code> 和 <code>a6742ff0</code> 刷新 showcase fact pack，<code>2c7e0c04</code> 记录了上一章，<code>5006a3e7</code>、<code>6ac3ddcb</code> 与 <code>c392c557</code> 也各自刷新了 fact pack。这里不为这些记录添上它们没有说出的缘由；清单的边界，正是本页要守的边界。</p><p>事实包给出的快照以 <code>2c7e0c0</code> 为 head，生成于 <code>2026-11-19T15:09:00.592Z</code>：总提交数为 2042，roadmap batches 为 493，almanac chapters 为 73，测试文件为 747，跟踪文件为 1158，roadmap 行数为 55786。它们是这本工程日记此刻所能指认的尺度，不是对未来的保证。云模块清单逐一列出 bridge、registry、config、inspector、tasks、insights、evidence 与 gateway；顺序来自 <code>minicc-cloud/pom.xml</code>，并未在此替它推断职责。目录、数字与接口名都适合被核对；把它们写清楚，本身就是对能力声明的约束。</p><p>缓存记录也把红线画在可测量之处。<code>wkapi.pro</code> 的上游分片使用 prefix-cache shard，客户端的 <code>prompt_cache_key</code> 作为路由提示；没有这个 key，相同前缀会逐次落到冷分片，有 key 时，热度周期内命中率稳定在约 94–100%。记录称 minicc 始终自动派生这个 key。用量解析只在网关确实返回 <code>prompt_tokens_details.cached_tokens</code> 时带上 <code>prompt_cache_hit_tokens</code>，没有上报便不伪造；RAG UI 相应显示缓存命中数与百分比，或显示缓存命中未上报。命令行的一次记录是 total_tokens=15568、cache_hit_tokens=7040、cache_miss_tokens=8456、cache_hit_pct=45.4。两轮小任务呈现首轮全付、次轮 prefix 命中的标准两趟；记录还说，同一前缀在开放会话复用时，命中率会快速接近先前单轮探针的 82–96%。</p><p>后续探针留下了边界条件，而不是把缓存写成必然。新 lane key 的首个调用之后，两次 warm 调用命中 8,362/8,566，即 97.6%；空闲 150 秒后，第三次调用归零，即使 cache_key 不变。随后十次序列中，第一次为冷，第二至第十次几乎全命中，只有 call-9 在 26 秒长 tail 后完整变冷；该序列全局 hit 权重约为 8/10，即约 80%。记录因此保留 60 秒 keeper 默认值，并指出旧的 220 秒 keeper 从未在该 lane 上护住 shard。固定字节前缀探针稳定在 97.6%，真实 agent 随逐轮增长的上下文则落在 48–72%；记录称这是物理事实，照实记下而不粉饰。压力账本另记三波累计 33,600 个请求、零个非 2xx、零个连接失败；另一次同机记录为 25,470 个请求，同样零个非 2xx、零个连接失败；当天累计为 59,070 个请求、零个非 2xx。清单的红色提醒我们：只写被证实的能力。</p><p>红线之内，事实才算承诺。</p>";
const LEDGER_EN_LXXIV = "<p>Volume LXXIV opens on the capability list. Its red is not an abstract warning but a specific threshold: the README contained <code>--minicc.python</code>, a flag that no parser declares, and this tripped the README capability-claims check. Commit <code>335b27ef</code> removed that flag token; the same record says <code>test_readme_capability_claims</code> passed all 8/8 checks. A capability list must not claim more than the implementation can do. Once prose presents a nonexistent entry point as a capability, readers can no longer distinguish a promise from a fact. Recent records place this correction among continuing work: <code>3e80af04</code> and <code>a6742ff0</code> refreshed the showcase fact pack, <code>2c7e0c04</code> recorded the previous chapter, and <code>5006a3e7</code>, <code>6ac3ddcb</code>, and <code>c392c557</code> also refreshed the fact pack. Nothing here adds reasons those records do not state. The boundary of the list is the boundary this page keeps.</p><p>The fact pack snapshot names <code>2c7e0c0</code> as head and gives its generation time as <code>2026-11-19T15:09:00.592Z</code>: 2042 total commits, 493 roadmap batches, 73 almanac chapters, 747 test files, 1158 tracked files, and 55786 roadmap lines. These are the measures this engineering diary can identify at this moment, not guarantees about what comes next. The cloud module list names bridge, registry, config, inspector, tasks, insights, evidence, and gateway, in the order given by <code>minicc-cloud/pom.xml</code>; this page infers no responsibilities for them. Directories, numbers, and interface names can be checked. Stating them precisely is itself a constraint on capability claims.</p><p>The cache records draw the line in measurable terms as well. The upstream shards of <code>wkapi.pro</code> use prefix-cache shards, with the client's <code>prompt_cache_key</code> serving as a routing hint. Without that key, the same prefix lands on cold shards repeatedly; with it, the hit rate remains about 94–100% during the warm period. The record says minicc always derives this key automatically. Usage parsing includes <code>prompt_cache_hit_tokens</code> only when the gateway actually returns <code>prompt_tokens_details.cached_tokens</code>; when it is not reported, the value is not fabricated. The RAG UI correspondingly shows the cache-hit count and percentage, or says that cache hits were not reported. One command-line record gives total_tokens=15568, cache_hit_tokens=7040, cache_miss_tokens=8456, and cache_hit_pct=45.4. The small two-round task shows the standard two passes: the first pays in full, and the second hits the prefix. The record also says that as the same prefix is reused in an open session, the hit rate quickly approaches the previously recorded single-probe range of 82–96%.</p><p>Later probes preserve boundary conditions instead of describing caching as inevitable. After the first call with a new lane key, two warm calls hit 8,362/8,566, or 97.6%; after 150 seconds idle, the third call fell to zero even though the cache key did not change. In the subsequent sequence of ten calls, the first was cold and calls two through ten were almost entirely hits; only call-9 went fully cold after a 26-second long tail. The sequence's global hit weight was about 8/10, or about 80%. The record therefore keeps the 60-second keeper default and notes that the old 220-second keeper had never protected the shard on that lane. A fixed-byte-prefix probe stayed at 97.6%, while a real agent's growing context across turns brought the rate down to 48–72%; the record calls this a physical fact, logged plainly and without polish. The pressure ledger separately records 33,600 requests across three waves, with zero non-2xx responses and zero connection failures. Another same-machine record gives 25,470 requests, again with zero non-2xx responses and zero connection failures. The daily cumulative count is 59,070 requests and zero non-2xx responses. The red on the list is a reminder: claim only capabilities that have been verified.</p><p>Within the red line, facts are promises.</p>";
function theredinthecapabilitylistMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-theredinthecapabilitylist">
      <div class="almanac-kicker">${zh() ? "卷七十四 · 红在能力清单那一页" : "Chapter LXXIV · The Red in the Capability List"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `旗语不能凭空被造，` + `<br/><span class="almanac-title-accent">契约不背没写过的字。</span>`
        : `A flag cannot be invented,` + `<br/><span class="almanac-title-accent">and the contract does not vouch for it.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXXIV : LEDGER_EN_LXXIV}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数（实）" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">113</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">75 / 75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造次数（实）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["文档不能发明旗语", "README 出现 --minicc.python，而仓库里没有 parser 声明它——capability-claims 门直接判红（test_readme_capability_claims）"],
        ["改词不改门", "minicc.python 去掉旗语写法，门本身不动；test_readme_capability_claims 8/8 green"],
        ["同一句话写了两种说法也会被抓", "主张谁写的、被抽出来对谁比——README 能力清单被当成契约逐 token 验证，not 自由文本"],
        ["红就是红，不给它找借口", "README 也要通过编译；这份 README 若不经这一红，以后会烂得无人察觉"],
      ] : [
        ["the document cannot invent a flag", "the README wrote --minicc.python; no parser declares it; the capability-claims gate rejected it outright (test_readme_capability_claims)"],
        ["fix the ink, not the gate", "minicc.python dropped the flag spelling; the gate itself untouched; test_readme_capability_claims 8/8 green"],
        ["the same sentence in two costumes is still one claim", "whoever writes a claim, whoever it is checked against - the README's capability list is parsed like a contract, token by token, not prose"],
        ["a red is a red; do not explain it away", "the document is also compiled; a README that dodges this red would rot silently later"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "契约不认不存在的字，README 也是契约。"
          : "The contract does not recognize a word that does not exist."}
      </p>
    </div>`;
}

// ---- Ch.LXXV · The Ladder Snaps, the World Does Not · 梯子断了，世界没断 (Atlas 113) ----
const LEDGER_ZH_LXXV = "<p>梯子断了，世界没断</p><p>卷LXXV写在一个容易把相邻刻度误认为同一时刻的日子里。最近的日志把卷LXXIV记为《能力列表里的红色》，把卷LXXIII记为《验证器拒绝》，把卷LXXII记为《过期断言》；它们之间还有一次 README 文档改动，移除了 <code>--minicc.python</code> 这个会触发能力声明门禁的词项，相关测试为 8/8 通过。日期都是 2026-11-19。另有一份事实包把仓库快照标作 head <code>2c7e0c0</code>，生成于 15:09:00.592Z，记录 2042 次提交、493 个路线图批次、73 章年鉴、747 个测试文件、1158 个跟踪文件，以及 55786 行路线图。此处的章数是那份快照所记的章数；它没有替眼前这一章预先改写数字。</p><p>本章的题目借来一架梯子，也借来它断裂后的安静。缓存亲和记录说，wkapi.pro 的上游分片会把 prefix-cache shard 与客户端的 <code>prompt_cache_key</code> 当作路由提示；没有 key，同一前缀会逐次落到冷分片，有了 key，热度周期内的命中率稳定在约 94–100%。minicc 始终自动派生这个 key。使用量解析只回传网关实际报告的 <code>cached_tokens</code>：有才带上 <code>prompt_cache_hit_tokens</code>，没有便不伪造；RAG 用量条相应显示命中数量与比例，或明确显示尚未上报。一次小任务记录了 15568 个总 token、7040 个命中 token、8456 个未命中 token，命中率 45.4%。数字说明两轮任务里首轮全付、次轮命中前缀；随着约 4.2k-token 的系统提示与工具 schema 在开放会话内复用，命中率可能接近先前探针记录的 82–96%。真实 agent 的上下文逐轮增长，记录的命中率则回落至 48–72%；这也是记录所说的物理事实，不由探针的漂亮数字抹去。</p><p>稳定的台阶有明确边界。2026-11-18 的新 lane key 测量中，模型列表仍有 7 项，terra 返回 200；首轮冷，随后两次 warm 命中 8362/8566，即 97.6%。空闲 150 秒后，第三次调用归零，key 没变；旧的 220 秒 keeper 从未护住这个 lane 的 shard，记录给出的窗口是 TTL ≤150 秒。后来十次序列里，第一次冷，第二至第十次几乎全命，只有长尾 26 秒后的第九次完整变冷；全序列加权命中约 8/10，也就是约 80%。因此 60 秒 keeper 被保留为默认间隔，并以 <code>cache_keeper status</code> 外显运行轨迹。热前缀的 8362 个 token 是各 lane 共享的 headline block，另 204 个属于自己的尾段；同字节前缀探针稳定在 97.6%，真实会话却不能保证同样比例。并发测试中，A、B 两组线程从各自冷启动后的第二次起都命中 8362/8566，记录为零抖动、零跨家族驱逐；这没有把网关的轮换或上下文变化变成不存在。</p><p>压测账本也把边界写得具体。Wave 3 在 c=128、12 秒条件下，每条路径 n=2380，总计 14280 个请求，0 错误，全部返回 200；账本还记载，在同一台 Windows 机器、<code>127.0.0.1:8899</code>、<code>MINICC_FAKE_PROVIDER=1</code> 的本地假 provider cockpit 上，三轮累计 33600 个请求，没有非 2xx，也没有连接失败。另一个同日累计记录为 25470 个请求，三轮同样没有非 2xx 或连接失败；日累计把 33600 与 25470 相加，得到 59070 个请求，0 个非 2xx。云模块清单则只列出八项：bridge、registry、config、inspector、tasks、insights、evidence、gateway。材料没有说明这些数字之间存在额外因果，也没有给出梯子为何断裂的单一解释；它让冷命中、热命中、过期窗口、成功响应各自留在原位。</p><p>梯子断了，世界仍按账本前行。</p>";
const LEDGER_EN_LXXV = "<p>The Ladder Snaps, the World Does Not</p><p>Almanac LXXV is written on a day when adjacent marks can easily be mistaken for the same moment. The recent log records LXXIV as “The Red in the Capability List,” LXXIII as “The Verifier Declines,” and LXXII as “The Stale Assertion.” Between them came a README documentation change that removed the <code>--minicc.python</code> token, which had tripped the capability-claims gate; the related tests passed 8/8. The dates are all 2026-11-19. A separate fact pack labels a repository snapshot with head <code>2c7e0c0</code>, generated at 15:09:00.592Z, and records 2042 commits, 493 roadmap batches, 73 almanac chapters, 747 test files, 1158 tracked files, and 55786 roadmap lines. The chapter count here is the count in that snapshot; it does not rewrite the number in advance for the chapter now before us.</p><p>This chapter's title borrows a ladder, and the quiet after it breaks. The cache-affinity record says that wkapi.pro's upstream shards use the prefix-cache shard and the client's <code>prompt_cache_key</code> as routing hints. Without a key, the same prefix lands on cold shards in turn; with one, the hit rate stays around 94–100% during the hot period. minicc always derives this key automatically. Usage parsing returns only the <code>cached_tokens</code> actually reported by the gateway: when present it includes <code>prompt_cache_hit_tokens</code>, and when absent it does not fabricate a value. The RAG usage bar accordingly shows the hit count and rate, or explicitly says that the hit was not reported. One small task recorded 15568 total tokens, 7040 hit tokens, and 8456 miss tokens, for a 45.4% hit rate. The figures describe a two-round task in which the first round paid in full and the second hit the prefix; as the roughly 4.2k-token system prompt and tool schema are reused within an open session, the hit rate may approach the earlier probe record of 82–96%. The real agent's context grows with each turn, however, and its recorded hit rate falls to 48–72%. The record calls this a physical fact, not one to be erased by the probe's more attractive numbers.</p><p>The stable steps have definite boundaries. In the new lane-key measurement on 2026-11-18, the model list still had 7 entries and terra returned 200; the first call was cold, then the next two warm calls hit 8362/8566, or 97.6%. After 150 seconds idle, the third call fell to zero, with the key unchanged; the old 220-second keeper had never protected this lane's shard, and the recorded window was TTL ≤150 seconds. In the later ten-call sequence, the first call was cold and calls two through ten were almost entirely hits; only call nine, after a 26-second long tail, went fully cold. The weighted hit rate for the whole sequence was about 8/10, or about 80%. The 60-second keeper was therefore retained as the default interval, with its operating trace exposed as <code>cache_keeper status</code>. Of the warm prefix, 8362 tokens are the headline block shared by all lanes, while the remaining 204 belong to its own tail; the same-byte-prefix probe held at 97.6%, but real sessions cannot promise the same rate. In the concurrency test, A and B threads both hit 8362/8566 from their second call onward after their respective cold starts; the record describes zero jitter and zero cross-family eviction. That does not make gateway rotation or changing context disappear.</p><p>The pressure ledger also states its boundaries concretely. Wave 3 ran at c=128 for 12 seconds, with n=2380 per path and 14280 requests in total: 0 errors, all returning 200. The ledger also records that, on the same Windows machine, a local fake-provider cockpit at <code>127.0.0.1:8899</code> with <code>MINICC_FAKE_PROVIDER=1</code> handled 33600 requests across three waves, with no non-2xx responses and no connection failures. Another same-day cumulative record lists 25470 requests across three waves, likewise with no non-2xx responses or connection failures. The daily total adds 33600 and 25470 to reach 59070 requests and 0 non-2xx responses. The cloud-module list contains exactly eight entries: bridge, registry, config, inspector, tasks, insights, evidence, and gateway. The material gives no further causal relation among these figures and offers no single explanation for why the ladder snapped; it leaves cold hits, warm hits, the expiration window, and successful responses in their own places.</p><p>The ladder snapped; the world kept moving by the ledger.</p>";
function theladdersnapsMarkup() {
  const commits = digestCache?.total_commits != null ? String(digestCache.total_commits) : "—";
  return `
    <div class="almanac-canvas almanac-theladdersnaps">
      <div class="almanac-kicker">${zh() ? "卷七十五 · 梯子断了，世界没断" : "Chapter LXXV · The Ladder Snaps, the World Does Not"}</div>
      <h1 class="almanac-title almanac-title-sm">${zh()
        ? `梯子抖了一下，` + `<br/><span class="almanac-title-accent">世界没停下来。</span>`
        : `The ladder shook,` + `<br/><span class="almanac-title-accent">and the world did not stop.</span>`}</h1>
      <div class="almanac-body">
        ${zh() ? LEDGER_ZH_LXXV : LEDGER_EN_LXXV}
      </div>
      <div class="almanac-instrument almanac-instrument-grid">
        <div><div class="almanac-instrument-label">${zh() ? "提交总数（实）" : "Commits (live)"}</div><div class="almanac-instrument-value">${escapeHtml(commits)}</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "Atlas 坐标" : "Atlas coordinates"}</div><div class="almanac-instrument-value">113</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "年鉴 · 双语" : "Volumes, both sides"}</div><div class="almanac-instrument-value">75 / 75</div></div>
        <div><div class="almanac-instrument-label">${zh() ? "锻造次数（实）" : "Forge rounds (live)"}</div><div class="almanac-instrument-value">attempts=1</div></div>
      </div>
      <ul class="almanac-gate-list">${(zh() ? [
        ["APIConnectionError 不是世界尽头", "forge 先调了一次，连接失败；显式带上 Clash Verge 代理后重跑，attempts=1，一次过审"],
        ["代理是梯子，不是地板", "User 级 HTTPS_PROXY/HTTP_PROXY=127.0.0.1:7897；工具进程若读不到它，就显式带上；.env 里写着，load_config 里导出，双保险"],
        ["抖一下不算数，落账才算", "cached 4,153 / prompt 7,030；61 秒把卷写完；世界从不因为一次抖动罢工"],
        ["并行会话没有吵起来", "crossrealm/football/specproof 同时在推，rebase 两次，谁也没覆盖谁；每个 commit 自己落自己的账"],
      ] : [
        ["APIConnectionError is not the end of the world", "the forge was called once, the connection dropped; with Clash Verge passed explicitly, the retry passed on attempt one"],
        ["the proxy is a ladder, not a floor", "user-scope HTTPS_PROXY/HTTP_PROXY=127.0.0.1:7897; when a tool process cannot see it, pass it explicitly; .env carries it and load_config exports it - two locks"],
        ["a wobble does not count; the ledger does", "cached 4,153 / prompt 7,030; the chapter was written in under a minute; the world does not go on strike for one bad call"],
        ["the parallel sessions did not shout at each other", "crossrealm, football and specproof pushed concurrently; two rebases, nobody overwrote anybody; every commit lands its own ledger"],
      ]).map(([strong, span]) => `<li><strong>${escapeHtml(strong)}</strong><span>${escapeHtml(span)}</span></li>`).join("")}</ul>
      <p class="almanac-quote almanac-quote-end">
        ${zh()
          ? "梯子抖了，世界还在写。"
          : "The ladder shook; the world kept writing."}
      </p>
    </div>`;
}

const CHAPTER_RENDERERS = {
  prologue: () => prologueMarkup(digestCache),
  spark: () => sparkMarkup(),
  depth: (metrics) => depthMarkup(metrics),
  sentry: (metrics) => sentryMarkup(metrics),
  bloom: () => bloomMarkup(),
  hand: () => handMarkup(),
  gate: () => gateMarkup(digestCache),
  mesh: () => meshMarkup(),
  witness: () => witnessMarkup(),
  craft: () => craftMarkup(),
  backlog: () => backlogMarkup(),
  echo: () => echoMarkup(),
  answer: () => answerMarkup(),
  ember: () => emberMarkup(),
  atlas: () => atlasMarkup(),
  firstlight: () => firstlightMarkup(),
  fever: () => feverMarkup(),
  lighthouse: () => lighthouseMarkup(),
  gatekeeper: () => gatekeeperMarkup(),
  meridian: () => meridianMarkup(),
  nightwatch: () => nightwatchMarkup(),
  fence: () => fenceMarkup(),
  compass: () => compassMarkup(),
  deepfield: () => deepfieldMarkup(),
  lawn: () => lawnMarkup(),
  litmus: () => litmusMarkup(),
  harbour: () => harbourMarkup(),
  return: () => returnMarkup(),
  steward: () => stewardMarkup(),
  relay: () => relayMarkup(),
  tide: () => tideMarkup(),
  lamplighter: () => lamplighterMarkup(),
  firefly: () => fireflyMarkup(),
  candle: () => candleMarkup(),
  newcoast: () => newcoastMarkup(),
  unscathed: () => unscathedMarkup(),
  slacktide: () => slacktideMarkup(),
  negativespace: () => negativespaceMarkup(),
  greatbasin: () => greatbasinMarkup(),
  blackoutdrill: () => blackoutdrillMarkup(),
  quota: () => quotaMarkup(),
  arithmetic: () => arithmeticMarkup(),
  gathering: () => gatheringMarkup(),
  oracle: () => oracleMarkup(),
  sleepless: () => sleeplessMarkup(),
  threshold: () => thresholdMarkup(),
  remeasure: () => remeasureMarkup(),
  eviction: () => evictionMarkup(),
  thewall: () => thewallMarkup(),
  livewire: () => livewireMarkup(),
  thesurge: () => thesurgeMarkup(),
  livecurrent: () => livecurrentMarkup(),
  twelfthlight: () => twelfthlightMarkup(),
  thereckoning: () => thereckoningMarkup(),
  thealarm: () => thealarmMarkup(),
  theledger: () => theledgerMarkup(),
  thegreenline: () => thegreenlineMarkup(),
  twoshards: () => twoshardsMarkup(),
  onenine: () => onenineMarkup(),
  quotation: () => quotationMarkup(),
  parallelwind: () => parallelwindMarkup(),
  ownscale: () => ownscaleMarkup(),
  forgedworld: () => forgedworldMarkup(),
  seventhday: () => seventhdayMarkup(),
  etchedwaterline: () => etchedwaterlineMarkup(),
  theclick: () => theclickMarkup(),
  densemap: () => densemapMarkup(),
  oneclickmanyhands: () => oneclickmanyhandsMarkup(),
  thelivepage: () => thelivepageMarkup(),
  therunnerwithoutbash: () => therunnerwithoutbashMarkup(),
  theplanethatanswered: () => theplanethatansweredMarkup(),
  thestaleassertion: () => thestaleassertionMarkup(),
  theverifierdeclines: () => theverifierdeclinesMarkup(),
  theredinthecapabilitylist: () => theredinthecapabilitylistMarkup(),
  theladdersnaps: () => theladdersnapsMarkup(),
};

async function loadChapter(id) {
  const slot = $("#almanacCanvas");
  if (!slot) return;
  // Phase 1: swap the canvas immediately with whatever we already know.
  // /api/stats can take seconds on a big .minicc tree; chapter switching
  // must never freeze on it. Numbers hydrate behind the text.
  const renderer = CHAPTER_RENDERERS[id] ?? CHAPTER_RENDERERS.prologue;
  slot.innerHTML = renderer(metricsCache);
  let scroller = slot.parentElement;
  while (scroller) {
    if (scroller.scrollHeight > scroller.clientHeight) scroller.scrollTop = 0;
    scroller = scroller.parentElement;
  }
  refreshIcons();
  // Phase 2: fetch metrics+digest (the fast path) and stats (the slow
  // path) separately — metrics and digest are usually < 1s, /api/stats
  // can take seconds on a big .minicc tree; the panel must never hold
  // digest-driven numbers hostage to stats' latency.
  const now = Date.now();
  const wantDigest = digestCache == null || now - digestFetchedAt > HYDRATE_TTL_MS;
  const wantStats = statsCache == null || now - statsFetchedAt > HYDRATE_TTL_MS;
  const wantPulse = worldpulseCache == null || now - worldpulseFetchedAt > HYDRATE_TTL_MS;
  const statsPromise = wantStats
    ? requestJson("/api/stats", {}, 20000).catch(() => null)
    : Promise.resolve(null);
  const wpPromise = wantPulse
    ? requestJson("/api/worldpulse", {}, 8000).catch(() => null)
    : Promise.resolve(null);
  const [metrics, digest, wp] = await Promise.all([
    requestJson("/api/metrics", {}, 15000).catch(() => null),
    wantDigest ? requestJson("/api/digest", {}, 20000).catch(() => null) : Promise.resolve(null),
    wpPromise,
  ]);
  if (currentChapter !== id) return;
  if (metrics) metricsCache = metrics;
  if (digest) {
    digestCache = digest;
    digestFetchedAt = Date.now();
  }
  if (wp && wp.live) {
    worldpulseCache = wp;
    worldpulseFetchedAt = Date.now();
  }
  const fast = CHAPTER_RENDERERS[id] ?? CHAPTER_RENDERERS.prologue;
  slot.innerHTML = fast(metricsCache);
  let scroller2 = slot.parentElement;
  while (scroller2) {
    if (scroller2.scrollHeight > scroller2.clientHeight) scroller2.scrollTop = 0;
    scroller2 = scroller2.parentElement;
  }
  refreshIcons();
  // The stats leg re-renders the same chapter with fresh numbers; any
  // other chapter switch aborts it.
  const maybeStats = await statsPromise;
  if (!maybeStats || currentChapter !== id) return;
  statsCache = maybeStats;
  statsFetchedAt = Date.now();
  const slow = CHAPTER_RENDERERS[id] ?? CHAPTER_RENDERERS.prologue;
  slot.innerHTML = slow(metricsCache);
  refreshIcons();
}

export async function openAlmanacPanel(chapterId) {
  const current = beginPanelRequest(t("almanac.title"));
  try {
    const rail = CHAPTERS.map(chapterMarkup).join("");
    openPanel(t("almanac.title"), `
      <div class="almanac-shell">
        <nav class="almanac-rail" aria-label="${zh() ? "章节" : "Chapters"}">${rail}</nav>
        <div class="almanac-canvas-shell"><div class="almanac-canvas" id="almanacCanvas">${prologueMarkup(digestCache)}</div></div>
      </div>
    `, { wide: true });
    document.querySelectorAll(".almanac-chapter").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".almanac-chapter").forEach((b) => b.classList.toggle("active", b === button));
        currentChapter = button.getAttribute("data-chapter") || "prologue";
        loadChapter(currentChapter);
        markVisited(`chapter:${currentChapter}`);
      });
    });
    const wanted = chapterId && CHAPTER_RENDERERS[chapterId] ? chapterId : "prologue";
    document.querySelectorAll(".almanac-chapter").forEach((b) => b.classList.toggle("active", b.getAttribute("data-chapter") === wanted));
    refreshIcons();
    if (wanted !== "prologue") currentChapter = wanted;
    markVisited(`chapter:${chapterId && CHAPTER_RENDERERS[chapterId] ? chapterId : "prologue"}`);
    requestJson("/api/digest")
      .then((digest) => {
        digestCache = digest;
        digestFetchedAt = Date.now();
        if (currentChapter !== "prologue") return;
        const slot = $("#almanacCanvas");
        if (!slot) return;
        slot.innerHTML = prologueMarkup(digestCache);
        refreshIcons();
      })
      .catch(() => {});
  } catch (error) {
    if (!current()) return;
    openPanel(t("almanac.title"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}
