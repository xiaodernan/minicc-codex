// M8-T908: the prefix fingerprint strip - the task detail modal's window
// into M8-T907's diagnostic data.
//
// Every request now ships system/msgs/tools fingerprints in its usage
// record. The strip renders them per turn so a cache mystery reads
// directly: `sys` moving means the prompt is rebuilt per turn; `tools`
// moving means the schema drifted; `msgs` changing wholesale between
// turns means the history was rewritten (a compaction or a reload
// asymmetry) and the gateway's prefix cache died from that message on.
// A stable `sys` with growing `msgs` tails is the healthy shape - exactly
// what the 97.6% hit rows show.
//
// Pure module: no DOM, no state imports - the node smoke imports it
// directly. Old snapshots without fingerprints render nothing (honest
// absence, never a fabricated strip).

const CAP = 12;

function short(value) {
  const s = String(value || "");
  return s ? s.slice(0, 8) : null;
}

export function prefixRows(usageByTurn, cap = CAP) {
  const rows = Array.isArray(usageByTurn) ? usageByTurn : [];
  const out = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const sys = short(row.system_fp);
    const msgs = short(row.msgs_fp);
    const tools = short(row.tools_fp);
    if (!sys && !msgs && !tools) continue; // a pre-T907 snapshot has no story
    out.push({
      sys,
      msgs,
      tools,
      hit: Number(row.prompt_cache_hit_tokens) || 0,
      prompt: Number(row.prompt_tokens) || 0,
    });
  }
  return out.slice(-cap);
}

export function prefixStripMarkup(rows, labels) {
  const lb = labels && typeof labels === "object" ? labels : {};
  if (!Array.isArray(rows) || !rows.length) return "";
  const cells = rows.map((row, index) => {
    const rate = row.prompt > 0 ? Math.round((row.hit / row.prompt) * 100) : null;
    const tone = rate == null ? "quiet" : rate >= 70 ? "mint" : rate >= 40 ? "amber" : "rose";
    const fields = [
      `<i>sys</i>${row.sys || "—"}`,
      `<i>msgs</i>${row.msgs || "—"}`,
      `<i>tools</i>${row.tools || "—"}`,
      `<i>${String(lb.hitLabel || "hit")}</i><b data-tone="${tone}">${rate == null ? "—" : `${rate}%`}</b>`,
    ].join("");
    return `<div class="prefix-strip-row"><span class="prefix-strip-n">#${index + 1}</span>${fields}</div>`;
  }).join("");
  return `<div class="prefix-strip">${cells}</div>`;
}
