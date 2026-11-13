// M8-T899: per-call cache-hit series — the pure shape behind the sparkline.
//
// The task record already accumulates one usage entry per model call
// (``usage_by_turn`` — agent turns, the completion judge, merge judges,
// each tagged with a ``kind``), both live through the SSE ``usage`` event
// and in the task snapshot. Nobody rendered it: the cache ring shows one
// aggregate number, which reads as "low" whenever a cold first turn drags
// the mean down. The series below gives each call its own bar, so the
// story becomes visible: call #1 pays full price, the calls after it ride
// the prefix cache.
//
// Pure module: no DOM, no state imports — the node smoke test imports it
// directly, exactly like task-reducer.js stays importable.

const CAP = 24;

export function cacheTurnSeries(usageByTurn, cap = CAP) {
  const rows = Array.isArray(usageByTurn) ? usageByTurn : [];
  const parsed = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const prompt = Number(row.prompt_tokens) || 0;
    if (prompt <= 0) continue; // a call with no prompt has no cache story
    const hit = Number(row.prompt_cache_hit_tokens) || 0;
    const miss = Number(row.prompt_cache_miss_tokens) || 0;
    const write = Number(row.prompt_cache_write_tokens) || 0;
    // Gateways that don't report the hit/miss split leave rate null —
    // the bar renders as a quiet stub, never a fabricated zero.
    const base = hit + miss > 0 ? hit + miss : 0;
    const rate = base > 0 ? Math.min(1, hit / base) : null;
    parsed.push({
      kind: String(row.kind || "agent"),
      prompt,
      hit,
      miss,
      write,
      rate,
    });
  }
  return parsed.slice(-cap);
}

export function cacheTurnTone(rate) {
  if (rate == null || !Number.isFinite(rate)) return "quiet";
  if (rate >= 0.7) return "mint";
  if (rate >= 0.4) return "amber";
  return "rose";
}
