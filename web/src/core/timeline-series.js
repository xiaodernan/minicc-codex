// M8-T904: task timeline — the pure shape behind the pulse card's epoch strip.
//
// The workspace pulse already lists the last 12 tasks as archive rows, but a
// list answers "what ran" while a timeline answers "what ran *when*, how big,
// and how did it end". The strip plots one node per task, oldest on the left,
// newest on the right; node height follows tokens on a log scale (task sizes
// span orders of magnitude, a linear scale would flatten the small ones to
// invisibility), and the tone follows the terminal status with the same
// vocabulary the archive rows already use (completed=mint, failed=rose,
// cancelled/interrupted=amber).
//
// Pure module: no DOM, no state imports — the node smoke test imports it
// directly, exactly like cache-series.js stays importable. Labels come in as
// an argument so no i18n import crosses this boundary either.

export function taskTimelineTone(status) {
  const s = String(status || "");
  if (s === "completed") return "mint";
  if (s === "failed") return "rose";
  if (s === "cancelled" || s === "interrupted") return "amber";
  if (s) return "pulse"; // running / planning / anything still live
  return "quiet";
}

export function taskTimelineHeight(tokens, maxTokens) {
  const t = Number(tokens) || 0;
  const max = Number(maxTokens) || 0;
  if (max <= 0) return 0;
  if (t <= 0) return 8; // a zero-token run still happened - show a stub, not silence
  const ratio = Math.log1p(t) / Math.log1p(max);
  // 12% floor keeps tiny runs visible; the log scale keeps a 1M-token giant
  // from flattening a 2k-token run.
  return Math.round((0.12 + 0.88 * Math.max(0, Math.min(1, ratio))) * 100);
}

export function compactTokens(value) {
  const n = Number(value) || 0;
  if (n <= 0) return "0";
  if (n >= 1e6) return `${(n / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1).replace(/\.0$/, "")}k`;
  return String(n);
}

export function taskTimelineSeries(tasks, cap = 12) {
  const rows = Array.isArray(tasks) ? tasks : [];
  const parsed = [];
  for (const task of rows) {
    if (!task || typeof task !== "object") continue;
    const tokens = Number(task?.tokens_used?.total_tokens ?? task?.metrics?.budget?.tokens ?? 0) || 0;
    parsed.push({
      id: String(task.task_id || ""),
      status: String(task.status || ""),
      tone: taskTimelineTone(task.status),
      tokens,
      cost: Number(task.cost_usd) || 0,
      duration: Number(task.duration_seconds) || 0,
      preview: String(task.preview || task.task_id || "").slice(0, 60),
      created: Number(task.created_at_epoch) || 0,
    });
  }
  // Input arrives newest-first (the /api/tasks projection sorts that way);
  // the strip runs oldest-left, so reverse after capping to the newest N.
  const capped = parsed.slice(0, cap).reverse();
  const maxTokens = capped.reduce((acc, item) => Math.max(acc, item.tokens), 0);
  return capped.map((item) => ({ ...item, height: taskTimelineHeight(item.tokens, maxTokens) }));
}

export function taskTimelineMarkup(series, labels) {
  const lb = labels && typeof labels === "object" ? labels : {};
  const empty = String(lb.empty || "");
  if (!Array.isArray(series) || !series.length) {
    return empty ? `<div class="pulse-timeline-empty">${empty}</div>` : "";
  }
  const nodes = series.map((item) => {
    const tipTitle = item.preview.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const tokensLabel = item.tokens > 0 ? `${compactTokens(item.tokens)} ${String(lb.tokensUnit || "tokens")}` : String(lb.noTokens || "");
    const tip = [tipTitle, tokensLabel].filter(Boolean).join(" · ");
    const created = item.created > 0 ? ` title="${new Date(item.created * 1000).toISOString()}"` : "";
    const taskId = item.id.replace(/"/g, "&quot;");
    return `<button type="button" class="pulse-timeline-node" data-tone="${item.tone}" data-open-task="${taskId}" style="--tl-h:${item.height}%"${created} aria-label="${tip}"><span class="pulse-timeline-bar"></span><span class="pulse-timeline-tip">${tip}</span></button>`;
  }).join("");
  const axis = lb.old || lb.new
    ? `<div class="pulse-timeline-axis"><span>${String(lb.old || "")}</span><span>${String(lb.new || "")}</span></div>`
    : "";
  return `<div class="pulse-timeline-track">${nodes}</div>${axis}`;
}
