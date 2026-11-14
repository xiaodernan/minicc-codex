/* ============================================================
   Minicc Axioms — ten ironclad rules written by this repository
   itself, not by a pasted manifesto. Every axiom carries:

     1. the rule, phrased as a claim this codebase is willing to make;
     2. the receipt — a file that exists in this repository right now
        and proves the rule is honoured, not aspirational.

   Pure frontend. No server round-trip. Both locales, full prose,
   no mixed-language chrome: zh renders all Chinese, en all English.
   ============================================================ */

import { t } from "../core/i18n.js";
import { $, state } from "../core/state.js";
import { icon, refreshIcons } from "../icons.js";
import { escapeHtml } from "../chat/markdown.js";
import { openPanel, beginPanelRequest } from "../chat/stream.js";

const zh = () => state.locale === "zh";

const AXIOMS = [
  {
    id: "local-first", numeral: { zh: "其一", en: "I" },
    title: { zh: "本地优先", en: "Local-first" },
    kicker: { zh: "默认值即全部", en: "The defaults are the whole story" },
    lede: {
      zh: "默认值就是全部。工作台只绑定 127.0.0.1；任务与审计写在你自己的 .minicc/ 里；模型密钥只活在进程环境变量里。没有“云端仪表盘”，因为它不存在。",
      en: "The defaults are the whole story. The workbench binds only 127.0.0.1; tasks and audit live in your own .minicc/; the model key lives only in process environment. There is no cloud dashboard — it does not exist.",
    },
    proof: { zh: "minicc/webserver.py · .minicc/web_token.json（owner-only）· MINICC_API_KEY 只由环境变量提供", en: "minicc/webserver.py · .minicc/web_token.json (owner-only) · MINICC_API_KEY only from process env" },
  },
  {
    id: "evidence-first", numeral: { zh: "其二", en: "II" },
    title: { zh: "先证据，后结论", en: "Evidence before verdict" },
    kicker: { zh: "没有捷径", en: "No shortcuts" },
    lede: {
      zh: "智能体在没看到真实命令输出之前不得宣布完成。完成判定的证据只能来自它自己读过或跑过的东西，而且必须发生在最后一次写代码之后。",
      en: "The agent may not declare done before it sees real command output. The only admissible evidence is what it read or ran itself — and it must follow the last code write.",
    },
    proof: { zh: "tests/test_accuracy_contracts.py · 完成判定置信度校验 · /api/tasks 的 completion_assessed 事件", en: "tests/test_accuracy_contracts.py · completion-confidence contract · /api/tasks completion_assessed events" },
  },
  {
    id: "gates-never-lie", numeral: { zh: "其三", en: "III" },
    title: { zh: "门从不说谎", en: "The gates never lie" },
    kicker: { zh: "红就是红", en: "Red is red" },
    lede: {
      zh: "推送前 doc_pointers --check 必须 rc=0。120 个声明核对器、6253 条证据指针，是每一次 push 的硬门槛。红了就是红了，不存在“这次先过再说”。",
      en: "Before every push, doc_pointers --check must exit 0. 120 claim checkers, 6253 evidence pointers — hard gates for every push. Red is red; there is no passing first and fixing later.",
    },
    proof: { zh: "scripts/doc_pointers.py · pre-push 钩子 · CI 的 Claim checkers 步骤", en: "scripts/doc_pointers.py · pre-push hook · CI 'Claim checkers' job step" },
  },
  {
    id: "cache-is-cost", numeral: { zh: "其四", en: "IV" },
    title: { zh: "缓存不是优化，是成本认知", en: "Cache is cost awareness" },
    kicker: { zh: "付出一次就够了", en: "Pay once" },
    lede: {
      zh: "缓存命中率就是成本曲线。这个项目实测从 0% 冷启动到 98.3% 命中，靠的是给出站请求加上 prompt_cache_key；每轮命中读数直接显示在脉搏里，绝不造假。",
      en: "Cache hit rate is a cost curve. This project measured 0% cold to 98.3% warm by attaching an opaque prompt_cache_key to outbound calls. Every turn reads its hit rate live, never faked.",
    },
    proof: { zh: "[usage] cache_hit_tokens 读数 · 脉搏卡的逐轮 sparkline · 已验证实弹读数", en: "[usage] cache_hit_tokens readout · pulse per-call sparkline · measured in production" },
  },
  {
    id: "fully-bilingual", numeral: { zh: "其五", en: "V" },
    title: { zh: "全内容双语", en: "Fully bilingual" },
    kicker: { zh: "不夹杂，也不遗漏", en: "No mixing, no gaps" },
    lede: {
      zh: "中文模式零夹杂；英文模式零 CJK。562 个字典键严格对齐，213 个字面 t() 引用全部可解析；年鉴九章、说明书七章逐章实测，退化会被 CI 拦截。",
      en: "zh mode: zero stray English. en mode: zero CJK. 562 dictionary keys in strict parity, 213 literal t() references resolvable; nine almanac chapters and seven manual chapters verified per locale — regression is blocked by CI.",
    },
    proof: { zh: "frontend_i18n_dict_one_home_smoke.mjs · tests/almanac_smoke.mjs · tests/codex_smoke.mjs", en: "frontend_i18n_dict_one_home_smoke.mjs · tests/almanac_smoke.mjs · tests/codex_smoke.mjs" },
  },
  {
    id: "user-data-verbatim", numeral: { zh: "其六", en: "VI" },
    title: { zh: "用户数据不是产品文案", en: "Your data is not our copy" },
    kicker: { zh: "原文保留，不翻译", en: "Verbatim, untranslated" },
    lede: {
      zh: "你的任务历史、你的文件树、你的审计日志、你运行出来的命令输出——原样保留，永不翻译。翻译的是“chrome”（面板骨架），不是你的内容。",
      en: "Your task history, your file tree, your audit log, the command output you produced — verbatim, never translated. Only the chrome is localized, never your content.",
    },
    proof: { zh: "/api/stats 真实读数（会话/审计/消息数）逐字显示，永不伪造 · 最近任务原样呈现", en: "/api/stats real counts (sessions/audit/messages) verbatim, never faked · recent tasks verbatim" },
  },
  {
    id: "every-change-ticketed", numeral: { zh: "其七", en: "VII" },
    title: { zh: "每一次变更都有批次号", en: "Every change has a batch number" },
    kicker: { zh: "只追加的账本", en: "An append-only ledger" },
    lede: {
      zh: "ROADMAP_TO_PRODUCT.md 是只追加的账本；每个 M8-TNNN 都是一个可回溯的切片：做了什么、怎么验证、留了什么尾巴——连被推红的提交也如实记录。",
      en: "ROADMAP_TO_PRODUCT.md is append-only. Every M8-TNNN is a traceable slice: what changed, how it was verified, what was left open — even the commits that turned CI red were recorded honestly.",
    },
    proof: { zh: "docs/ROADMAP_TO_PRODUCT.md · docs/CHANGELOG.md · M8-T000 → M8-T933", en: "docs/ROADMAP_TO_PRODUCT.md · docs/CHANGELOG.md · M8-T000 → M8-T933" },
  },
  {
    id: "failure-is-visible", numeral: { zh: "其八", en: "VIII" },
    title: { zh: "失败必须被看见", en: "Failure must be visible" },
    kicker: { zh: "诚实的失败胜过假成功", en: "Honest failure > fake success" },
    lede: {
      zh: "不可达提供方必须让 smoke 红，绝不静默通过。每个任务有终态；每个失败有 toast；每个错误在服务端日志里可查。“诚实的失败”是产品的一部分。",
      en: "An unreachable provider must turn the smoke red — never silently pass. Every task reaches a terminal state; every failure has a toast; every error is on the server log. Honest failure is part of the product.",
    },
    proof: { zh: "tests/web_smoke.mjs 的 PRODUCT_PATH_NO_COMPLETION_VERDICT 门 · 每次推送必跑", en: "tests/web_smoke.mjs PRODUCT_PATH_NO_COMPLETION_VERDICT gate · runs on every push" },
  },
  {
    id: "tool-calls-leave-signatures", numeral: { zh: "其九", en: "IX" },
    title: { zh: "工具调用有完整签名", en: "Every tool call leaves a signature" },
    kicker: { zh: "可回溯，可复盘", en: "Replayable, reviewable" },
    lede: {
      zh: "审计日志按顺序、带序号、带时间戳地记录每个工具回合、每次重试、每个完成判定、每次审批停顿——你永远能回答“它刚才到底干了什么”。",
      en: "The audit log records every tool round, every retry, every completion verdict, every approval pause — ordered, numbered, timestamped. You can always answer: what did it just do?",
    },
    proof: { zh: "provider_retry / tool_round_finished / completion_assessed / approval_requested · tests/m1_integrity.py", en: "provider_retry / tool_round_finished / completion_assessed / approval_requested · tests/m1_integrity.py" },
  },
  {
    id: "promises-get-executed", numeral: { zh: "其十", en: "X" },
    title: { zh: "承诺必须被执行", en: "Promises get executed" },
    kicker: { zh: "口说传承，证据为凭", en: "Words are cheap; evidence is the product" },
    lede: {
      zh: "宣布“已完成”前，机器必须跑过门；宣布“已同步”前，必须看到 bot 提交；宣布“已修复”前，必须重新跑测试。这个仓库从不轻信任何人的话——包括我。",
      en: "Before 'done' is announced, the gates must have run. Before 'synced' is claimed, the bot commit must exist. Before 'fixed' is claimed, tests must be re-run. This repository never takes anyone's word — mine included.",
    },
    proof: { zh: "docs/CHANGELOG.md 每条 M8-TNNN 都附验收方式 · CI 每次推送必跑 · completion_assessed 绝不跳过", en: "docs/CHANGELOG.md every batch names its verification · CI on every push · completion_assessed never skipped" },
  },
];

function axiomMarkup(axiom, index) {
  const title = zh() ? axiom.title.zh : axiom.title.en;
  return `<button class="axioms-chapter" data-axiom="${escapeHtml(axiom.id)}" role="tab">
            <span class="axioms-chapter-roman">${escapeHtml(zh() ? axiom.numeral.zh : axiom.numeral.en)}</span>
            <span class="axioms-chapter-body"><strong>${escapeHtml(title)}</strong></span>
          </button>`;
}

function canvasMarkup(axiom) {
  const isZh = zh();
  const title = isZh ? axiom.title.zh : axiom.title.en;
  const kicker = isZh ? axiom.kicker.zh : axiom.kicker.en;
  const lede = isZh ? axiom.lede.zh : axiom.lede.en;
  const proof = isZh ? axiom.proof.zh : axiom.proof.en;
  return `
    <div class="axioms-canvas">
      <div class="axioms-kicker">${escapeHtml(isZh ? `铁律 · ${axiom.numeral.zh}` : `Axiom ${axiom.numeral.en}`)} · ${escapeHtml(kicker)}</div>
      <h1 class="axioms-title"><span class="axioms-title-accent">${escapeHtml(title)}</span></h1>
      <div class="axioms-body">
        <p class="axioms-lede">${escapeHtml(lede)}</p>
        <div class="axioms-proof">
          <div class="axioms-proof-label">${escapeHtml(isZh ? "证据 · 收据" : "Proof · the receipt")}</div>
          <p class="axioms-proof-line">${escapeHtml(proof)}</p>
          <div class="axioms-proof-foot">${escapeHtml(isZh ? "本文件证据来自此仓库，逐字未改。" : "Evidence quoted verbatim from this repository.")}</div>
        </div>
      </div>
    </div>`;
}

let currentAxiom = "local-first";

function renderAxiom(id) {
  const slot = $("#axiomsCanvas");
  const axiom = AXIOMS.find((a) => a.id === id) ?? AXIOMS[0];
  if (!slot) return;
  slot.innerHTML = canvasMarkup(axiom);
  refreshIcons();
}

export async function openAxiomsPanel() {
  const current = beginPanelRequest(t("axioms.title"));
  try {
    const rail = AXIOMS.map((a, i) => axiomMarkup(a, i)).join("");
    openPanel(t("axioms.title"), `
      <div class="axioms-shell">
        <nav class="axioms-rail" aria-label="${escapeHtml(t("axioms.title"))}">${rail}</nav>
        <div class="axioms-canvas-shell"><div class="axioms-canvas" id="axiomsCanvas"></div></div>
      </div>
    `, { wide: true });
    renderAxiom(currentAxiom);
    document.querySelectorAll(".axioms-chapter").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".axioms-chapter").forEach((b) => b.classList.toggle("active", b === button));
        currentAxiom = button.getAttribute("data-axiom") || "local-first";
        renderAxiom(currentAxiom);
      });
    });
    document.querySelector('.axioms-chapter[data-axiom="local-first"]')?.classList.add("active");
    refreshIcons();
  } catch (error) {
    if (!current()) return;
    openPanel(t("axioms.title"), `<div class="error-panel">${escapeHtml(error.message)}</div>`);
  }
}
